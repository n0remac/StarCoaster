"""Navigation rasterization of exported OpenRCT2 tile elements.

The exporter is the park scripting API, not a duplicate hand-written map. The
planner uses quarter-tile cells and dilates solid geometry by the Zergling's
radius. Coordinates passed to it are OpenRCT2 world pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import json
import math
from pathlib import Path


CELL = 8
UNIT_RADIUS = 24  # 8 px Zergling radius plus 16 px steering margin


@dataclass(frozen=True)
class Point:
    x: int
    y: int


class ParkGrid:
    def __init__(self, export: dict, fixture: dict, radius: int = UNIT_RADIUS,
                 validate_approaches: bool = True):
        self.export = export
        self.fixture = fixture
        self.radius = radius
        self.bounds = export["bounds"]
        self.x0 = self.bounds["min_x"] * 4
        self.y0 = self.bounds["min_y"] * 4
        self.width = (self.bounds["max_x"] - self.bounds["min_x"] + 1) * 4
        self.height = (self.bounds["max_y"] - self.bounds["min_y"] + 1) * 4
        self.revision = 1
        self.cleared = set()
        self.targets = {target["id"]: target for target in fixture["targets"]}
        self._validate_geometry()
        self._rasterize()
        if validate_approaches:
            for target_id, target in self.targets.items():
                valid = self.attack_cells(target_id)
                if not target["attack_approaches"] or any(
                        self.cell(Point(**approach)) not in valid
                        for approach in target["attack_approaches"]):
                    raise ValueError(f"unsafe attack approach for {target_id}")

    def _validate_geometry(self) -> None:
        transform = self.fixture["transform"]
        if not all(isinstance(transform.get(axis), int) for axis in ("x", "y")):
            raise ValueError("invalid world transform")
        if len(self.targets) != len(self.fixture["targets"]):
            raise ValueError("duplicate target identity")
        for target in self.targets.values():
            occupied = {(tile["x"], tile["y"]) for tile in target["footprint_tiles"]}
            exported = {(element["x"], element["y"]) for element in self.export["elements"]
                        if element["type"] == "track" and element["ride_id"] == target["ride_id"]}
            if not occupied or occupied != exported or occupied != {
                    (tile["x"], tile["y"]) for tile in target["tiles"]}:
                raise ValueError(f"track footprint mismatch for {target['id']}")
            center = {"x": round(sum(x * 32 + 16 for x, _ in occupied) / len(occupied)),
                      "y": round(sum(y * 32 + 16 for _, y in occupied) / len(occupied))}
            if target["structure_center"] != center or target["proxy_world"] != center:
                raise ValueError(f"proxy position mismatch for {target['id']}")
            if any((center[axis] - transform[axis]) % 16 for axis in ("x", "y")):
                raise ValueError(f"proxy transform cannot round-trip for {target['id']}")
            footprint_width = (max(x for x, _ in occupied) - min(x for x, _ in occupied) + 1) * 32
            footprint_height = (max(y for _, y in occupied) - min(y for _, y in occupied) + 1) * 32
            collision = target["proxy_collision"]
            # Stock OpenBW building bounds need not match the ride pixel for
            # pixel, but they must remain within one track tile on each axis.
            if (abs(collision["width"] - footprint_width) > 32
                    or abs(collision["height"] - footprint_height) > 32):
                raise ValueError(f"proxy collision mismatch for {target['id']}")

    @classmethod
    def load(cls, elements: Path, fixture: Path, radius: int = UNIT_RADIUS) -> "ParkGrid":
        return cls(json.loads(elements.read_text()), json.loads(fixture.read_text()), radius)

    def _rasterize(self) -> None:
        cells = {}
        for y in range(self.y0, self.y0 + self.height):
            for x in range(self.x0, self.x0 + self.width):
                tile_x, tile_y = x // 4, y // 4
                height = self.export["elevation_rows"][tile_y - self.bounds["min_y"]][tile_x - self.bounds["min_x"]]
                cells[(x, y)] = {"x": x, "y": y, "elevation": height,
                                 "walkable": True, "classification": "grass",
                                 "traversal_cost": 1.0, "source": None}

        def block(x: int, y: int, kind: str, source: str) -> None:
            cell = cells.get((x, y))
            if cell is not None:
                cell.update(walkable=False, classification=kind, source=source, traversal_cost=None)

        for element in self.export["elements"]:
            x, y, kind = element["x"], element["y"], element["type"]
            base_x, base_y = x * 4, y * 4
            if kind == "footpath":
                for cy in range(base_y, base_y + 4):
                    for cx in range(base_x, base_x + 4):
                        cell = cells.get((cx, cy))
                        if cell and cell["walkable"]:
                            cell.update(classification="footpath", traversal_cost=0.85,
                                        source=f"path:{x},{y}")
            elif kind == "wall":
                # Native OpenRCT2 wall edges: 0 west, 1 south, 2 east, 3 north.
                direction = element["direction"]
                if direction % 2 == 0:
                    edge_x = base_x + (3 if direction == 2 else 0)
                    positions = ((edge_x, cy) for cy in range(base_y, base_y + 4))
                else:
                    edge_y = base_y + (3 if direction == 1 else 0)
                    positions = ((cx, edge_y) for cx in range(base_x, base_x + 4))
                for cx, cy in positions:
                    block(cx, cy, "wall", f"wall:{x},{y}:{element['direction']}:{element['object_id']}")
            elif kind == "small_scenery":
                name = element["object_id"].split(".")[-1]
                if name.startswith("tf") or name.startswith("tg"):
                    continue  # flowers and low planting remain traversable
                quadrant = element.get("quadrant", 0)
                qx, qy = quadrant % 2, quadrant // 2
                for cy in range(base_y + qy * 2, base_y + qy * 2 + 2):
                    for cx in range(base_x + qx * 2, base_x + qx * 2 + 2):
                        block(cx, cy, "tree", f"scenery:{x},{y}:{element['object_id']}")
            elif kind == "track":
                target = next((t for t in self.fixture["targets"] if t["ride_id"] == element["ride_id"]), None)
                if target is None or target["id"] in self.cleared:
                    continue
                for cy in range(base_y, base_y + 4):
                    for cx in range(base_x, base_x + 4):
                        block(cx, cy, "structure", target["id"])

        self.raw = cells
        self.clear = {}
        reach = math.ceil(self.radius / CELL)
        for (x, y), cell in cells.items():
            if not cell["walkable"]:
                self.clear[(x, y)] = False
                continue
            valid = True
            for dy in range(-reach, reach + 1):
                for dx in range(-reach, reach + 1):
                    if dx * dx + dy * dy > (self.radius / CELL) ** 2:
                        continue
                    nearby = cells.get((x + dx, y + dy))
                    if nearby is None or not nearby["walkable"]:
                        valid = False
                        break
                if not valid:
                    break
            self.clear[(x, y)] = valid

    def cell(self, point: Point) -> tuple[int, int]:
        return point.x // CELL, point.y // CELL

    @staticmethod
    def world(cell: tuple[int, int]) -> Point:
        return Point(cell[0] * CELL + CELL // 2, cell[1] * CELL + CELL // 2)

    def passable(self, cell: tuple[int, int]) -> bool:
        return self.clear.get(cell, False)

    def line_clear(self, start: tuple[int, int], end: tuple[int, int]) -> bool:
        # Sample at half-cell intervals so smoothing cannot cut a rasterized edge.
        length = math.dist(start, end)
        for step in range(math.ceil(length * 2) + 1):
            fraction = step / max(1, math.ceil(length * 2))
            x = round(start[0] + (end[0] - start[0]) * fraction)
            y = round(start[1] + (end[1] - start[1]) * fraction)
            if not self.passable((x, y)):
                return False
        return True

    def attack_cells(self, target_id: str, max_distance: int = 80) -> set[tuple[int, int]]:
        target = self.targets[target_id]
        occupied = {(t["x"], t["y"]) for t in target["tiles"]}
        cells = set()
        for tile_x, tile_y in occupied:
            for y in range(tile_y * 4 - 6, tile_y * 4 + 10):
                for x in range(tile_x * 4 - 6, tile_x * 4 + 10):
                    if not self.passable((x, y)) or (x // 4, y // 4) in occupied:
                        continue
                    point = self.world((x, y))
                    distance = min(math.dist((point.x, point.y),
                                             ((tx + 0.5) * 32, (ty + 0.5) * 32))
                                   for tx, ty in occupied)
                    if distance <= max_distance:
                        cells.add((x, y))
        return cells

    def route(self, start: Point, goals: set[tuple[int, int]], smooth: bool = True) -> list[Point]:
        origin = self.cell(start)
        if not self.passable(origin):
            raise ValueError(f"start lacks unit clearance: {start}")
        if not goals:
            raise ValueError("no reachable attack anchor candidates")
        # Multi-goal A*. A bounding-box lower bound avoids scanning every goal
        # for every expanded cell while remaining admissible.
        min_x = min(x for x, _ in goals); max_x = max(x for x, _ in goals)
        min_y = min(y for _, y in goals); max_y = max(y for _, y in goals)
        def heuristic(cell: tuple[int, int]) -> float:
            dx = max(min_x - cell[0], 0, cell[0] - max_x)
            dy = max(min_y - cell[1], 0, cell[1] - max_y)
            return math.hypot(dx, dy) * 0.85
        frontier = [(heuristic(origin), 0.0, origin)]
        previous = {origin: None}
        scores = {origin: 0.0}
        reached = None
        while frontier:
            _, score, current = heapq.heappop(frontier)
            if score != scores[current]:
                continue
            if current in goals:
                reached = current
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                neighbor = current[0] + dx, current[1] + dy
                if not self.passable(neighbor):
                    continue
                if dx and dy and (not self.passable((current[0] + dx, current[1]))
                               or not self.passable((current[0], current[1] + dy))):
                    continue
                cost = math.hypot(dx, dy) * self.raw[neighbor]["traversal_cost"]
                candidate = score + cost
                if candidate < scores.get(neighbor, math.inf):
                    scores[neighbor] = candidate
                    previous[neighbor] = current
                    heapq.heappush(frontier, (candidate + heuristic(neighbor), candidate, neighbor))
        if reached is None:
            raise ValueError(f"no route from {start} to any attack anchor")
        path = []
        while reached is not None:
            path.append(reached)
            reached = previous[reached]
        path.reverse()
        if smooth:
            result = [path[0]]
            index = 0
            while index < len(path) - 1:
                farthest = index + 1
                for candidate in range(len(path) - 1, index, -1):
                    if self.line_clear(path[index], path[candidate]):
                        farthest = candidate
                        break
                result.append(path[farthest])
                index = farthest
            path = result
        return [self.world(cell) for cell in path]

    def route_to_target(self, start: Point, target_id: str) -> list[Point]:
        target = self.targets[target_id]
        candidates = {cell for approach in target["attack_approaches"]
                      for cell in self.attack_cells(target_id)
                      if math.dist((self.world(cell).x, self.world(cell).y),
                                   (approach["x"], approach["y"])) <= 8}
        return self.route(start, candidates)

    def select_attack_approaches(self, target_id: str) -> list[dict]:
        """Pick cleared exterior points on the available sides of real track tiles."""
        target = self.targets[target_id]
        center = target["structure_center"]
        candidates = self.attack_cells(target_id)
        selected = []
        for sector in range(8):
            angle = sector * math.pi / 4
            direction = math.cos(angle), math.sin(angle)
            scored = []
            for cell in candidates:
                point = self.world(cell)
                dx, dy = point.x - center["x"], point.y - center["y"]
                distance = math.hypot(dx, dy)
                if distance == 0:
                    continue
                alignment = (dx * direction[0] + dy * direction[1]) / distance
                if alignment >= 0.9:
                    scored.append((distance, -alignment, cell))
            if scored:
                point = self.world(min(scored)[2])
                candidate = {"x": point.x, "y": point.y}
                if candidate not in selected:
                    selected.append(candidate)
        if not selected:
            raise ValueError(f"no cleared attack approaches for {target_id}")
        return selected

    def clear_target(self, target_id: str, expected_revision: int) -> dict:
        if expected_revision != self.revision:
            raise ValueError(f"stale map revision {expected_revision}; current {self.revision}")
        if target_id not in self.targets or target_id in self.cleared:
            raise ValueError(f"target unavailable: {target_id}")
        before = {key: self.clear[key] for key in self.clear}
        self.cleared.add(target_id)
        self.revision += 1
        self._rasterize()
        changed = [list(key) for key, clear in self.clear.items() if before[key] != clear]
        return {"target_id": target_id, "revision": self.revision, "changed_cells": changed}

    def to_json(self) -> dict:
        return {"version": 1, "map_id": "park-assault", "revision": self.revision,
                "bounds": self.bounds, "cell_size": CELL, "unit_radius": self.radius,
                "transform": self.fixture["transform"],
                "cells": [cell | {"walkable": self.clear[key]} for key, cell in self.raw.items()]}
