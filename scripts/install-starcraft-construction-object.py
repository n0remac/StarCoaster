#!/usr/bin/env python3
"""Install the 4 by 3 Barracks scenery from locally licensed StarCraft art."""

import argparse
import io
import json
import os
from pathlib import Path
import runpy
import struct
import zipfile

from PIL import Image


IDENTIFIER = "starcoaster.scenery_large.terran_barracks"
ROOT = Path(__file__).resolve().parent.parent
BARRACKS_RESOURCE = "unit/terran/TBarrack.grp"
PALETTE_RESOURCE = "Tileset/Badlands.wpe"

def barracks_images(game_dir: Path) -> list[Image.Image]:
    source = ROOT / "run-data/generated-assets/starcraft/barracks/.source"
    source.mkdir(parents=True, exist_ok=True)
    helpers = runpy.run_path(str(ROOT / "scripts/prepare-starcraft-sprites.py"))
    grp_path, wpe_path = source / "TBarrack.grp", source / "Badlands.wpe"
    helpers["extract"](game_dir, BARRACKS_RESOURCE, grp_path)
    helpers["extract"](game_dir, PALETTE_RESOURCE, wpe_path)
    data, wpe = grp_path.read_bytes(), wpe_path.read_bytes()
    count, width, height = struct.unpack_from("<HHH", data)
    if (count, width, height) != (9, 192, 160) or len(wpe) != 1024:
        raise ValueError("Unexpected classic StarCraft Barracks GRP or Badlands palette")
    source_images = [helpers["decode_grp"](data, wpe, index)
                     for index in (0, 2, 3, 4, 5, 6, 7, 8)]
    bounds = source_images[0].getbbox()
    if bounds is None:
        raise ValueError("Classic StarCraft Barracks frame is empty")
    palette = helpers["openrct2_palette"]()
    available = [i for i in range(10, 255) if not 230 <= i <= 239 and not 243 <= i <= 254]
    cache = {}
    output_images = []
    for source in source_images:
        # Keep every frame on the same canvas so moving parts do not shift the building.
        image = source.crop(bounds).resize((189, 164), Image.Resampling.NEAREST)
        output = Image.new("P", image.size, 0)
        output.putpalette([channel for colour in palette for channel in colour])
        pixels = []
        for red, green, blue, alpha in image.getdata():
            if alpha == 0:
                pixels.append(0)
                continue
            colour = (red, green, blue)
            if colour not in cache:
                cache[colour] = min(available, key=lambda i:
                    sum((colour[channel] - palette[i][channel]) ** 2 for channel in range(3)))
            pixels.append(cache[colour])
        output.putdata(pixels)
        output_images.append(output)
    return output_images


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def tile_screen(x: int, y: int, direction: int) -> tuple[int, int]:
    x, y = x * 32, y * 32
    if direction == 1:
        x, y = y, -x
    elif direction == 2:
        x, y = -x, -y
    elif direction == 3:
        x, y = -y, x
    return y - x, (x + y) // 2


def install(data_root: Path, game_dir: Path) -> Path:
    destination = data_root / "object" / "starcoaster" / "scenery_large" / (IDENTIFIER + ".parkobj")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sprites = barracks_images(game_dir)
    sprite = sprites[0]
    preview = sprite.resize((58, 50), Image.Resampling.NEAREST)
    images = []
    tiles = []
    for y in range(3):
        for x in range(4):
            tiles.append({"x": x * 32, "y": y * 32, "z": 0, "clearance": 48,
                          "corners": 15, "walls": 0, "hasSupports": False})
    # OpenRCT2 paints each scenery tile through its own viewport region. Each
    # tile therefore carries the same sprite, aligned to one screen position;
    # the regions join into one full Barracks without changing the 4x3 object.
    for _ in range(4):
        images.append({"path": "images/preview.png", "x": -29, "y": -16, "palette": "keep"})
    origins = []
    for direction in range(4):
        positions = [tile_screen(tx, ty, direction)
                     for ty in range(3) for tx in range(4)]
        centre_x = (min(p[0] for p in positions) + max(p[0] for p in positions)) // 2
        origins.append((centre_x - sprite.width // 2,
                        max(p[1] for p in positions) + 16 - sprite.height))
    # Frame 0 remains at the original image indexes for old saves and normal
    # scenery painting. Native painting selects a later 48-image bank only while
    # OpenBW reports a Marine in this Barracks' training queue.
    for frame in range(len(sprites)):
        for y in range(3):
            for x in range(4):
                for direction in range(4):
                    origin_x, origin_y = origins[direction]
                    screen_x, screen_y = tile_screen(x, y, direction)
                    images.append({"path": f"images/barracks-{frame}.png",
                                   "x": origin_x - screen_x, "y": origin_y - screen_y,
                                   "palette": "keep"})
    definition = {"id": IDENTIFIER, "authors": ["StarCoaster"], "version": "2.0",
                  "objectType": "scenery_large",
                  "properties": {"price": 1, "removalPrice": 0, "cursor": "CURSOR_STATUE_DOWN",
                                 "tiles": tiles},
                  "images": images,
                  "strings": {"name": {"en-GB": "Terran Barracks"}}}
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("object.json", json.dumps(definition, separators=(",", ":")))
        archive.writestr("images/preview.png", png_bytes(preview))
        for frame, frame_sprite in enumerate(sprites):
            archive.writestr(f"images/barracks-{frame}.png", png_bytes(frame_sprite))
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("--game-dir", type=Path,
                        default=Path(os.environ.get("STARCRAFT_DATA_DIR", str(Path.home() / "games/starcraft"))))
    args = parser.parse_args()
    print(install(args.data_root, args.game_dir))
