#!/usr/bin/env python3
"""Render local, unredistributable Zerg animation contact sheets."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DIRECTIONS = ("east", "southeast", "south", "southwest", "west",
              "northwest", "north", "northeast")
UNITS = ("zergling", "hydralisk", "ultralisk")


def draw_sheet(unit: str, state: str, source: Path, output: Path) -> None:
    manifest = json.loads((source / "manifest.json").read_text())
    animation = manifest["registry"][f"zerg_{unit}"][state]["frames"]
    rows = [(direction, animation[direction]) for direction in DIRECTIONS] if isinstance(animation, dict) \
        else [("all facings", animation)]
    canvas_width, canvas_height = manifest["canvas"]
    tile_width, tile_height = canvas_width + 24, canvas_height + 36
    columns = max(len(names) for _, names in rows)
    sheet = Image.new("RGB", (120 + columns * tile_width, 34 + len(rows) * tile_height), "#252b35")
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 8), f"{unit.upper()} / {state.upper()}", fill="white")
    for row, (direction, names) in enumerate(rows):
        y = 34 + row * tile_height
        draw.text((8, y + tile_height // 2), direction, fill="#d6dfec")
        for column, name in enumerate(names):
            meta = manifest["frames"][name]
            x = 120 + column * tile_width
            draw.rectangle((x, y, x + tile_width - 3, y + tile_height - 3), fill="#3a4554")
            with Image.open(source / name) as sprite:
                sheet.paste(sprite, (x + tile_width // 2 + meta["x"],
                                     y + 8 + canvas_height // 2 + meta["y"]), sprite)
            draw.text((x + 4, y + tile_height - 21),
                      f"{column}: GRP {meta['source_frame']}", fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "run-data/generated-assets/starcraft")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "run-data/artifacts/zerg-animation-contact-sheets")
    args = parser.parse_args()
    for unit in UNITS:
        for state in ("idle", "walk", "attack", "death"):
            target = args.output / f"{unit}-{state}.png"
            draw_sheet(unit, state, args.source / unit, target)
            print(target)


if __name__ == "__main__":
    main()
