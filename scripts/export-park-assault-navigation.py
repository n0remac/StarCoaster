#!/usr/bin/env python3
"""Build reusable JSON and compact OpenBW navigation data from the saved park export."""

import json
from pathlib import Path

from park_navigation import ParkGrid, Point


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "run-data/park-assault"


def export() -> dict:
    grid = ParkGrid.load(DATA / "navigation-elements.json", DATA / "fixture.json")
    (DATA / "navigation-grid.json").write_text(json.dumps(grid.to_json(), separators=(",", ":")) + "\n")
    map_manifest = json.loads((DATA / "map/park-assault.json").read_text())
    fixture = json.loads((DATA / "fixture.json").read_text())
    if not 1 <= len(fixture["targets"]) <= 8:
        raise ValueError("compact navigation grid supports one to eight targets")
    offset = fixture["transform"]
    lines = [f"PARKGRID 2 {grid.revision} {grid.x0} {grid.y0} {grid.width} {grid.height} "
             f"{offset['x']} {offset['y']} {len(fixture['targets'])}"]
    for target in fixture["targets"]:
        center = target["structure_center"]
        if target["proxy_world"] != center or not target["attack_approaches"]:
            raise ValueError(f"invalid target geometry: {target['id']}")
        collision = target["proxy_collision"]
        lines.append(f"TARGET {target['id']} {target['ride_id']} {target['proxy_unit_type']} "
                     f"{center['x'] - offset['x']} {center['y'] - offset['y']} "
                     f"{collision['width']} {collision['height']} {len(target['attack_approaches'])}")
        for approach in target["attack_approaches"]:
            cell = grid.cell(Point(**approach))
            if cell not in grid.attack_cells(target["id"]):
                raise ValueError(f"unsafe attack approach: {target['id']} {approach}")
            lines.append(f"APPROACH {approach['x'] - offset['x']} {approach['y'] - offset['y']}")
    for y in range(grid.y0, grid.y0 + grid.height):
        row = []
        for x in range(grid.x0, grid.x0 + grid.width):
            cell = grid.raw[(x, y)]
            if cell["classification"] == "structure":
                row.append(str(list(grid.targets).index(cell["source"]) + 1))
            else:
                row.append("." if cell["walkable"] else "#")
        lines.append("".join(row))
    (DATA / "navigation.grid").write_text("\n".join(lines) + "\n")

    routes = []
    assignment = {"alpha": "carousel-1", "beta": "shop-1", "gamma": "ride-2"}
    for unit in map_manifest["zerglings"]:
        target_id = assignment[unit["squad"]]
        path = grid.route_to_target(Point(unit["park_x"], unit["park_y"]), target_id)
        routes.append({"unit_id": unit["id"], "squad": unit["squad"], "target_id": target_id,
                       "park_points": [{"x": p.x, "y": p.y} for p in path],
                       "bw_points": [{"x": p.x - offset["x"], "y": p.y - offset["y"]} for p in path]})
    (DATA / "planned-paths.json").write_text(json.dumps(routes, indent=2) + "\n")
    # Standalone SVG is easy to inspect in the viewer and keeps the full grid crisp.
    colors = {"wall": "#4b5563", "tree": "#166534", "structure": "#b91c1c",
              "footpath": "#c8b58d", "grass": "#d9ead3"}
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="768" height="768" viewBox="{grid.x0} {grid.y0} {grid.width} {grid.height}">']
    for (x, y), cell in grid.raw.items():
        svg.append(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{colors[cell["classification"]]}"/>')
    squad_colors = {"alpha": "#2563eb", "beta": "#eab308", "gamma": "#a855f7"}
    for route in routes:
        points = " ".join(f'{p["x"] / 8},{p["y"] / 8}' for p in route["park_points"])
        svg.append(f'<polyline points="{points}" fill="none" stroke="{squad_colors[route["squad"]]}" stroke-width="0.35" opacity="0.7"/>')
    svg.append("</svg>")
    (DATA / "navigation-routes.svg").write_text("\n".join(svg))
    report = {"revision": grid.revision, "cells": len(grid.raw), "blocked_cells": sum(not x for x in grid.clear.values()),
              "routes": len(routes), "target_ids": list(grid.targets)}
    (DATA / "navigation-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(export(), indent=2))
