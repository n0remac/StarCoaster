"""Render planned and observed park routes for the private artifact viewer."""

import json
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

    squad_for_id = {str(row["unit_id"]): row["squad"] for row in planned}
    observed_image = image.copy()
    observed_draw = ImageDraw.Draw(observed_image)
    for unit_id, samples in observed.items():
        points = [project(row["park_x"], row["park_y"]) for row in samples]
        if len(points) >= 2:
            observed_draw.line(points, fill=SQUAD[squad_for_id.get(unit_id, "alpha")], width=2)
    observed_image.save(output / "observed-paths.png")
