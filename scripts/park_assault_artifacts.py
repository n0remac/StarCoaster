"""Render planned and observed park routes for the private artifact viewer."""

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw

from park_navigation import ParkGrid


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "run-data/park-assault"
SCALE = 4
COLORS = {"wall": (72, 83, 98), "tree": (22, 101, 52), "structure": (185, 28, 28),
          "footpath": (200, 181, 141), "grass": (217, 234, 211)}
SQUAD = {"alpha": (37, 99, 235), "beta": (234, 179, 8), "gamma": (168, 85, 247)}


def draw_diagnostics(output: Path) -> None:
    grid = ParkGrid.load(DATA / "navigation-elements.json", DATA / "fixture.json")
    planned = json.loads((DATA / "planned-paths.json").read_text())
    observed = json.loads((output / "observed-paths.json").read_text())
    image = Image.new("RGB", (grid.width * SCALE, grid.height * SCALE))
    draw = ImageDraw.Draw(image)
    for (x, y), cell in grid.raw.items():
        px, py = (x - grid.x0) * SCALE, (y - grid.y0) * SCALE
        draw.rectangle((px, py, px + SCALE - 1, py + SCALE - 1), fill=COLORS[cell["classification"]])
    image.save(output / "navigation-grid.png")

    def project(x: int, y: int) -> tuple[int, int]:
        return (round((x / 8 - grid.x0) * SCALE), round((y / 8 - grid.y0) * SCALE))

    planned_image = image.copy()
    planned_draw = ImageDraw.Draw(planned_image)
    for route in planned:
        points = [project(p["x"], p["y"]) for p in route["park_points"]]
        if len(points) >= 2:
            planned_draw.line(points, fill=SQUAD[route["squad"]], width=2)
    planned_image.save(output / "planned-paths.png")

    bw_log = (output / "bwapi.log").read_text(errors="replace") if (output / "bwapi.log").is_file() else ""
    target_for_id = dict(re.findall(r"\[park-assault\] route id=(\d+) target=([a-z0-9-]+)", bw_log))
    squad_for_target = {"carousel-1": "alpha", "shop-1": "beta", "ride-2": "gamma"}
    squad_for_id = {unit_id: squad_for_target.get(target_id, "alpha")
                    for unit_id, target_id in target_for_id.items()}
    observed_image = image.copy()
    observed_draw = ImageDraw.Draw(observed_image)
    for unit_id, samples in observed.items():
        points = [project(row["park_x"], row["park_y"]) for row in samples]
        if len(points) >= 2:
            observed_draw.line(points, fill=SQUAD[squad_for_id.get(unit_id, "alpha")], width=2)
    observed_image.save(output / "observed-paths.png")

    fixture = grid.fixture
    offset = fixture["transform"]
    event_file = output / "target-events.json"
    events = json.loads(event_file.read_text()) if event_file.is_file() else {}
    proxies = {row[0]: row for row in events.get("created", []) if len(row) >= 8}
    overlay = image.copy()
    marks = ImageDraw.Draw(overlay)
    spatial = {"transform": offset, "targets": [], "units": []}
    for target in fixture["targets"]:
        center = target["structure_center"]
        cx, cy = project(center["x"], center["y"])
        for tile in target["footprint_tiles"]:
            ax, ay = project(tile["x"] * 32, tile["y"] * 32)
            marks.rectangle((ax, ay, ax + 16, ay + 16), outline=(255, 255, 255), width=1)
        width, height = target["proxy_collision"]["width"], target["proxy_collision"]["height"]
        half_w, half_h = round(width * SCALE / 16), round(height * SCALE / 16)
        marks.rectangle((cx - half_w, cy - half_h, cx + half_w, cy + half_h),
                        outline=(6, 182, 212), width=2)
        marks.line((cx - 5, cy, cx + 5, cy), fill=(249, 115, 22), width=2)
        marks.line((cx, cy - 5, cx, cy + 5), fill=(249, 115, 22), width=2)
        for approach in target["attack_approaches"]:
            ax, ay = project(approach["x"], approach["y"])
            marks.ellipse((ax - 3, ay - 3, ax + 3, ay + 3), fill=(250, 204, 21))
        observed_proxy = proxies.get(target["id"])
        spatial["targets"].append({"id": target["id"], "ride_id": target["ride_id"],
            "footprint_tiles": target["footprint_tiles"], "structure_center": center,
            "expected_proxy_bw": {axis: center[axis] - offset[axis] for axis in ("x", "y")},
            "observed_proxy_bw": ({"x": int(observed_proxy[3]), "y": int(observed_proxy[4])}
                                  if observed_proxy else None),
            "collision": target["proxy_collision"], "approaches": target["attack_approaches"],
            "proxy_type": target["proxy_type"]})
    targets_by_id = {target["id"]: target for target in fixture["targets"]}
    for unit_id, samples in observed.items():
        if not samples:
            continue
        last = samples[-1]
        target_id = target_for_id.get(unit_id)
        if target_id not in targets_by_id:
            continue
        target = targets_by_id[target_id]
        ax, ay = project(last["park_x"], last["park_y"])
        cx, cy = project(target["structure_center"]["x"], target["structure_center"]["y"])
        marks.line((ax, ay, cx, cy), fill=SQUAD[squad_for_id[unit_id]], width=1)
        marks.ellipse((ax - 2, ay - 2, ax + 2, ay + 2), fill=SQUAD[squad_for_id[unit_id]])
        spatial["units"].append({"id": unit_id, "target": target_id, "last": last})
    overlay.save(output / "spatial-overlay.png")
    (output / "spatial-diagnostics.json").write_text(json.dumps(spatial, indent=2) + "\n")

    paths = {(element["x"], element["y"]): element["z"]
             for element in grid.export["elements"] if element["type"] == "footpath"}
    elevations = grid.export["elevation_rows"]
    rendering = []
    for unit_id, history in observed.items():
        for sample in history[::max(1, len(history) // 12)]:
            x, y = sample["park_x"] // 32, sample["park_y"] // 32
            ground = elevations[y - grid.bounds["min_y"]][x - grid.bounds["min_x"]]
            draw_z = max(ground, paths.get((x, y), ground))
            rendering.append({"unit_id": unit_id, "frame": sample["frame"],
                "ground_z": ground, "draw_z": draw_z, "sort_bounds_z": draw_z + 5,
                "surface": "path" if (x, y) in paths else "terrain"})
    (output / "render-elevation-samples.json").write_text(json.dumps(rendering, indent=2) + "\n")
