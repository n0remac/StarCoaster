#!/usr/bin/env python3
"""Install the original, save-embedded 4 by 3 Barracks scenery object."""

import io
import json
from pathlib import Path
import sys
import zipfile

from PIL import Image, ImageDraw


IDENTIFIER = "starcoaster.scenery_large.terran_barracks"


def tile_image(x: int, y: int) -> bytes:
    # Simple original industrial roof art. Each piece has its own iso diamond;
    # OpenRCT2 rotates the full object's positions and selects one of four views.
    image = Image.new("RGBA", (64, 72))
    draw = ImageDraw.Draw(image)
    draw.polygon([(32, 8), (61, 23), (32, 39), (3, 23)], fill=(69, 78, 87), outline=(24, 29, 36))
    draw.polygon([(3, 23), (32, 39), (32, 59), (3, 42)], fill=(47, 57, 69), outline=(24, 29, 36))
    draw.polygon([(32, 39), (61, 23), (61, 42), (32, 59)], fill=(34, 43, 55), outline=(24, 29, 36))
    draw.line([(9, 23), (32, 11), (55, 23), (32, 35), (9, 23)], fill=(127, 140, 144), width=2)
    draw.line([(32, 11), (32, 35)], fill=(111, 124, 130), width=2)
    if x in (0, 3) or y in (0, 2):
        draw.line([(11, 22), (32, 12), (53, 22)], fill=(186, 83, 64), width=3)
    if x == 1 and y == 2:
        draw.polygon([(21, 43), (32, 49), (32, 58), (21, 52)], fill=(25, 28, 31))
        draw.line([(23, 46), (29, 49)], fill=(203, 168, 74), width=2)
    if x == 2 and y == 1:
        draw.ellipse((26, 17, 38, 28), fill=(178, 70, 58), outline=(22, 26, 32))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def install(data_root: Path) -> Path:
    destination = data_root / "object" / "starcoaster" / "scenery_large" / (IDENTIFIER + ".parkobj")
    destination.parent.mkdir(parents=True, exist_ok=True)
    images = []
    tiles = []
    for y in range(3):
        for x in range(4):
            tiles.append({"x": x * 32, "y": y * 32, "z": 0, "clearance": 48,
                          "corners": 15, "walls": 0, "hasSupports": False})
    # Four preview images precede four direction images per occupied tile.
    for _ in range(4):
        images.append({"path": "images/tile_1_1.png", "x": -32, "y": -56})
    for y in range(3):
        for x in range(4):
            for _ in range(4):
                images.append({"path": f"images/tile_{x}_{y}.png", "x": -32, "y": -56})
    definition = {"id": IDENTIFIER, "authors": ["StarCoaster"], "version": "1.0",
                  "objectType": "scenery_large",
                  "properties": {"price": 1, "removalPrice": 0, "cursor": "CURSOR_STATUE_DOWN",
                                 "tiles": tiles},
                  "images": images,
                  "strings": {"name": {"en-GB": "Terran Barracks"}}}
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("object.json", json.dumps(definition, separators=(",", ":")))
        for y in range(3):
            for x in range(4):
                archive.writestr(f"images/tile_{x}_{y}.png", tile_image(x, y))
    return destination


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: install-starcraft-construction-object.py OPENRCT2_DATA_ROOT")
    print(install(Path(sys.argv[1])))
