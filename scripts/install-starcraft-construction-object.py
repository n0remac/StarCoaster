#!/usr/bin/env python3
"""Install a supported StarCraft building object from locally licensed art."""

import argparse
import io
import json
import os
from pathlib import Path
import re
import runpy
import struct
import zipfile

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
TYPE_DEFINITIONS = {item["id"]: item for item in
                    json.loads((ROOT / "bridge-protocol/starcraft-types.json").read_text())["buildings"]}
PALETTE_RESOURCE = "Tileset/Badlands.wpe"


def image_resource(game_dir: Path, image_name: str, helpers=None) -> str:
    """Resolve the pinned image ID through classic images.dat and images.tbl."""
    helpers = helpers or runpy.run_path(str(ROOT / "scripts/prepare-starcraft-sprites.py"))
    source = ROOT / "run-data/generated-assets/starcraft/metadata/.source"
    source.mkdir(parents=True, exist_ok=True)
    images_dat, images_tbl = source / "images.dat", source / "images.tbl"
    helpers["extract"](game_dir, "arr/images.dat", images_dat)
    helpers["extract"](game_dir, "arr/images.tbl", images_tbl)
    enum_source = (ROOT / "upstream/openbw/bwenums.h").read_text()
    block = enum_source.split("enum struct ImageTypes : int {", 1)[1].split("};", 1)[0]
    names = re.findall(r"\bIMAGEID_[A-Za-z0-9_]+\b", block)
    key = "IMAGEID_" + image_name
    if key not in names:
        raise ValueError(f"Unknown pinned OpenBW image: {key}")
    data, table = images_dat.read_bytes(), images_tbl.read_bytes()
    index = names.index(key)
    if len(data) < 999 * 4 or len(table) < 4 or index >= 999:
        raise ValueError("Unexpected classic StarCraft image metadata")
    string_index = struct.unpack_from("<I", data, index * 4)[0]
    count = struct.unpack_from("<H", table)[0]
    if not 1 <= string_index <= count or 2 + count * 2 > len(table):
        raise ValueError(f"Invalid GRP path index for {key}")
    offset = struct.unpack_from("<H", table, 2 + (string_index - 1) * 2)[0]
    if offset >= len(table):
        raise ValueError(f"Invalid GRP path offset for {key}")
    end = table.find(b"\0", offset)
    if end < 0:
        raise ValueError(f"Unterminated GRP path for {key}")
    path = table[offset:end].decode("ascii").replace("\\", "/")
    if not re.fullmatch(r"[A-Za-z0-9_/.-]+\.grp", path) or ".." in path.split("/"):
        raise ValueError(f"Unsafe GRP path for {key}")
    return "unit/" + path


def light_only_frame(idle: Image.Image, illuminated: Image.Image) -> Image.Image:
    """Copy only each indicator and its two-pixel glow onto the idle shape."""
    frame = idle.copy()
    destination = frame.load()
    base = idle.load()
    source = illuminated.load()
    indicators = []
    for y in range(idle.height):
        for x in range(idle.width):
            red, green, blue, alpha = source[x, y]
            if (alpha and destination[x, y][3] and source[x, y] != destination[x, y]
                    and red >= 140 and green >= 100 and blue <= 50 and red > green * 1.1):
                indicators.append((x, y))
    for light_x, light_y in indicators:
        for y in range(max(0, light_y - 2), min(idle.height, light_y + 3)):
            for x in range(max(0, light_x - 2), min(idle.width, light_x + 3)):
                if source[x, y][3] and base[x, y][3]:
                    destination[x, y] = source[x, y]
    return frame


def barracks_images(game_dir: Path) -> list[Image.Image]:
    source = ROOT / "run-data/generated-assets/starcraft/barracks/.source"
    source.mkdir(parents=True, exist_ok=True)
    helpers = runpy.run_path(str(ROOT / "scripts/prepare-starcraft-sprites.py"))
    grp_path, wpe_path = source / "TBarrack.grp", source / "Badlands.wpe"
    helpers["extract"](game_dir, image_resource(game_dir, "Barracks", helpers), grp_path)
    helpers["extract"](game_dir, PALETTE_RESOURCE, wpe_path)
    data, wpe = grp_path.read_bytes(), wpe_path.read_bytes()
    count, width, height = struct.unpack_from("<HHH", data)
    if (count, width, height) != (9, 192, 160) or len(wpe) != 1024:
        raise ValueError("Unexpected classic StarCraft Barracks GRP or Badlands palette")
    idle = helpers["decode_grp"](data, wpe, 0)
    # The first five training banks are dark. GRP frames 2–4 also contain the
    # lift-off sequence, so never use their moving geometry during training.
    # The final two banks keep frame 0's shape and add only the light pixels
    # from GRP frames 7 and 8, preserving the existing flash cadence.
    source_images = [idle] * 6 + [light_only_frame(idle, helpers["decode_grp"](data, wpe, index))
                                  for index in (7, 8)]
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


def academy_images(game_dir: Path) -> list[Image.Image]:
    source = ROOT / "run-data/generated-assets/starcraft/academy/.source"
    source.mkdir(parents=True, exist_ok=True)
    helpers = runpy.run_path(str(ROOT / "scripts/prepare-starcraft-sprites.py"))
    grp_path, wpe_path = source / "Academy.grp", source / "Badlands.wpe"
    helpers["extract"](game_dir, image_resource(game_dir, "Terran_Academy", helpers), grp_path)
    helpers["extract"](game_dir, PALETTE_RESOURCE, wpe_path)
    data, wpe = grp_path.read_bytes(), wpe_path.read_bytes()
    if struct.unpack_from("<HHH", data) != (2, 96, 128) or len(wpe) != 1024:
        raise ValueError("Unexpected classic StarCraft Academy GRP or Badlands palette")
    image = helpers["decode_grp"](data, wpe, 0)
    bounds = image.getbbox()
    if bounds is None:
        raise ValueError("Classic StarCraft Academy frame is empty")
    image = image.crop(bounds).resize((140, 140), Image.Resampling.NEAREST)
    palette = helpers["openrct2_palette"]()
    available = [i for i in range(10, 255) if not 230 <= i <= 239 and not 243 <= i <= 254]
    cache = {}
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
    return [output]


# Visual preparation is building-specific; tile layout and archive assembly are
# shared. The Barracks' name, image paths, and bank order are save-compatible.
BUILDING_OBJECTS = {
    "terran_barracks": {"frame_name": "barracks",
                        "prepare": lambda game_dir: barracks_images(game_dir)},
    "terran_academy": {"frame_name": "academy", "prepare": academy_images,
                        "preview_size": (52, 52), "preview_offset": (-26, -18)},
}


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


def install(data_root: Path, game_dir: Path, building_type: str = "terran_barracks") -> Path:
    if building_type not in BUILDING_OBJECTS or building_type not in TYPE_DEFINITIONS:
        raise ValueError(f"Unsupported StarCraft building: {building_type}")
    spec = BUILDING_OBJECTS[building_type]
    definition_type = TYPE_DEFINITIONS[building_type]
    width, height = definition_type["width"], definition_type["height"]
    if width < 1 or height < 1 or not definition_type["object_id"] or not definition_type["display_name"]:
        raise ValueError(f"Invalid StarCraft building definition: {building_type}")
    destination = data_root / "object" / "starcoaster" / "scenery_large" / (definition_type["object_id"] + ".parkobj")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sprites = spec["prepare"](game_dir)
    if not sprites:
        raise ValueError(f"No sprite frames for {building_type}")
    animation = definition_type.get("animation")
    if animation and len(sprites) != animation["frames"] + 1:
        raise ValueError(f"Animation bank count differs from type catalog: {building_type}")
    sprite = sprites[0]
    preview = sprite.resize(spec.get("preview_size", (58, 50)), Image.Resampling.NEAREST)
    images = []
    tiles = []
    for y in range(height):
        for x in range(width):
            tiles.append({"x": x * 32, "y": y * 32, "z": 0, "clearance": 48,
                          "corners": 15, "walls": 0, "hasSupports": False})
    # OpenRCT2 paints each scenery tile through its own viewport region. Each
    # tile therefore carries the same sprite, aligned to one screen position;
    # the regions join into one full Barracks without changing the 4x3 object.
    for _ in range(4):
        preview_x, preview_y = spec.get("preview_offset", (-29, -16))
        images.append({"path": "images/preview.png", "x": preview_x, "y": preview_y, "palette": "keep"})
    origins = []
    for direction in range(4):
        positions = [tile_screen(tx, ty, direction)
                     for ty in range(height) for tx in range(width)]
        centre_x = (min(p[0] for p in positions) + max(p[0] for p in positions)) // 2
        origins.append((centre_x - sprite.width // 2,
                        max(p[1] for p in positions) + 16 - sprite.height))
    # Frame 0 remains at the original image indexes for old saves and normal
    # scenery painting. Native painting selects a later 48-image bank only while
    # OpenBW reports a Marine in this Barracks' training queue.
    for frame in range(len(sprites)):
        for y in range(height):
            for x in range(width):
                for direction in range(4):
                    origin_x, origin_y = origins[direction]
                    screen_x, screen_y = tile_screen(x, y, direction)
                    images.append({"path": f"images/{spec['frame_name']}-{frame}.png",
                                   "x": origin_x - screen_x, "y": origin_y - screen_y,
                                   "palette": "keep"})
    definition = {"id": definition_type["object_id"], "authors": ["StarCoaster"], "version": "2.0",
                  "objectType": "scenery_large",
                  "properties": {"price": 1, "removalPrice": 0, "cursor": "CURSOR_STATUE_DOWN",
                                 "tiles": tiles},
                  "images": images,
                  "strings": {"name": {"en-GB": definition_type["display_name"]}}}
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("object.json", json.dumps(definition, separators=(",", ":")))
        archive.writestr("images/preview.png", png_bytes(preview))
        for frame, frame_sprite in enumerate(sprites):
            archive.writestr(f"images/{spec['frame_name']}-{frame}.png", png_bytes(frame_sprite))
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("--building-type", choices=BUILDING_OBJECTS, default="terran_barracks")
    parser.add_argument("--all", action="store_true", help="install every supported construction object")
    parser.add_argument("--game-dir", type=Path,
                        default=Path(os.environ.get("STARCRAFT_DATA_DIR", str(Path.home() / "games/starcraft"))))
    args = parser.parse_args()
    if args.all:
        for building_type in BUILDING_OBJECTS:
            print(install(args.data_root, args.game_dir, building_type))
    else:
        print(install(args.data_root, args.game_dir, args.building_type))
