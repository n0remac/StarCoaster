#!/usr/bin/env python3
"""Extract a local classic StarCraft Zergling pack. Never commit the output."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "run-data/generated-assets/starcraft/zergling"
RESOURCE = "unit/zerg/zergling.grp"
PALETTE = "Tileset/Badlands.wpe"
# The first three 17-direction groups are the rest and two gait poses.
# Source directions are north (0), east (8), south (16); west is mirrored east.
FRAMES = {"idle": 0, "walk0": 17, "walk1": 34}
DIRECTIONS = {"east": (8, False), "south": (16, False),
              "west": (8, True), "north": (0, False)}


def openrct2_palette() -> list[tuple[int, int, int]]:
    header = ROOT / "upstream/openrct2/src/openrct2/drawing/ImageImporter.h"
    if not header.is_file():
        raise RuntimeError("Fetch the pinned OpenRCT2 checkout before preparing sprites")
    block = header.read_text().split("StandardPalette = { {", 1)[1].split("} };", 1)[0]
    block = re.sub(r"//[^\n]*", "", block)
    bgra = re.findall(r"\{\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\}", block)
    if len(bgra) != 256:
        raise ValueError(f"Expected 256 OpenRCT2 palette entries, got {len(bgra)}")
    return [(int(red), int(green), int(blue)) for blue, green, red, _ in bgra]


def quantize(image: Image.Image, palette: list[tuple[int, int, int]]) -> Image.Image:
    # g2's default importer requires exact palette RGB values. Map locally so
    # it never silently discards non-matching StarCraft colours as transparent.
    available = [i for i in range(10, 255) if not 230 <= i <= 239 and not 243 <= i <= 254]
    cache = {}
    result = Image.new("RGBA", image.size)
    output = []
    for red, green, blue, alpha in image.getdata():
        if alpha == 0:
            output.append((0, 0, 0, 0))
            continue
        colour = (red, green, blue)
        if colour not in cache:
            index = min(available, key=lambda i: sum((colour[c] - palette[i][c]) ** 2 for c in range(3)))
            cache[colour] = palette[index] + (255,)
        output.append(cache[colour])
    result.putdata(output)
    return result


def extract(game_dir: Path, name: str, target: Path) -> str:
    for archive_name in ("Patch_rt.mpq", "BrooDat.mpq", "StarDat.mpq"):
        archive = game_dir / archive_name
        if not archive.is_file():
            continue
        with tempfile.TemporaryDirectory(dir=target.parent) as temp:
            result = subprocess.run(["smpq", "--extract", str(archive), name],
                                    cwd=temp, capture_output=True, text=True)
            found = Path(temp) / name
            if result.returncode == 0 and found.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(found, target)
                return archive_name
    raise RuntimeError(f"Could not extract {name} from MPQs in {game_dir}")


def decode_grp(data: bytes, wpe: bytes, index: int) -> Image.Image:
    count, width, height = struct.unpack_from("<HHH", data)
    if not (0 <= index < count and 0 < width <= 300 and 0 < height <= 300):
        raise ValueError(f"Invalid GRP header or frame {index}: {count}, {width}x{height}")
    left, top, frame_width, frame_height, start = struct.unpack_from("<BBBBI", data, 6 + 8 * index)
    if left + frame_width > width or top + frame_height > height or start >= len(data):
        raise ValueError(f"Invalid GRP frame bounds for frame {index}")
    image = Image.new("RGBA", (width, height))
    pixels = image.load()
    for y in range(frame_height):
        offset = start + struct.unpack_from("<H", data, start + 2 * y)[0]
        x = 0
        while x < frame_width:
            command = data[offset]
            offset += 1
            size = command & 0x7F if command & 0x80 else command & 0x3F if command & 0x40 else command
            if size == 0 or x + size > frame_width:
                raise ValueError(f"Invalid GRP RLE run in frame {index}, row {y}")
            if command & 0x80:
                x += size
                continue
            values = [data[offset]] * size if command & 0x40 else data[offset:offset + size]
            offset += 1 if command & 0x40 else size
            for dx, value in enumerate(values):
                # StarCraft remaps team colours 8..15 at runtime. Neutral red
                # is retained here; shadows are separate GRPs, not this body.
                pixels[left + x + dx, top + y] = tuple(wpe[value * 4:value * 4 + 3]) + (255,)
            x += size
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path,
                        default=Path(os.environ.get("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft")))
    parser.add_argument("--unit", choices=["zergling"], default="zergling")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if shutil.which("smpq") is None:
        parser.error("smpq is required (Debian package: smpq / StormLib)")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = output / ".source"
    source.mkdir(exist_ok=True)
    grp_path, wpe_path = source / "zergling.grp", source / "Badlands.wpe"
    archives = {RESOURCE: extract(args.game_dir, RESOURCE, grp_path),
                PALETTE: extract(args.game_dir, PALETTE, wpe_path)}
    data, wpe = grp_path.read_bytes(), wpe_path.read_bytes()
    if len(wpe) != 1024:
        raise ValueError(f"Expected 1024-byte WPE palette, got {len(wpe)}")
    frame_count, canvas_width, canvas_height = struct.unpack_from("<HHH", data)
    if frame_count < 51:
        raise ValueError(f"Expected at least 51 Zergling frames, got {frame_count}")
    palette = openrct2_palette()
    selected = {}
    for motion, base in FRAMES.items():
        for direction, (facing, mirror) in DIRECTIONS.items():
            frame = base + facing
            image = decode_grp(data, wpe, frame)
            if mirror:
                image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            bbox = image.getbbox()
            if bbox is None:
                raise ValueError(f"Selected frame {frame} is empty")
            # Crop while retaining the GRP canvas centre as the render origin.
            cropped = quantize(image.crop(bbox), palette)
            filename = f"{motion}_{direction}.png"
            cropped.save(output / filename)
            selected[filename] = {"source_frame": frame, "mirrored": mirror,
                                  "width": cropped.width, "height": cropped.height,
                                  "x": bbox[0] - canvas_width // 2,
                                  "y": bbox[1] - canvas_height // 2,
                                  "visible_pixels": sum(a != 0 for a in cropped.getchannel("A").getdata())}
    manifest = {"unit": args.unit, "source": RESOURCE, "palette": PALETTE,
                "archives": archives, "canvas": [canvas_width, canvas_height],
                "frame_count": frame_count, "direction_convention": "north=0 east=8 south=16 west=mirror(east)",
                "team_colour": "source palette indices 8..15 retained without player remap",
                "shadow": "separate StarCraft shadow artwork omitted",
                "output_palette": "nearest OpenRCT2 standard palette colour, excluding special and primary remap indices",
                "frames": selected}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared {len(selected)} frames in {output} from {archives}")


if __name__ == "__main__":
    main()
