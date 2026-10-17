#!/usr/bin/env python3
"""Extract local classic StarCraft unit sprites. Never commit the output."""

import argparse
import hashlib
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
MARINE_RESOURCE = "unit/terran/marine.grp"
FIREBAT_RESOURCE = "unit/terran/firebat.grp"
FIREBAT_DEATH_RESOURCE = "unit/thingy/tBangS.grp"
MEDIC_RESOURCE = "unit/terran/medic.grp"
VULTURE_RESOURCE = "unit/terran/Vulture.grp"
FLAME_RESOURCE = "unit/thingy/flamer.grp"
PALETTE = "Tileset/Badlands.wpe"
# Contact-sheet inspection of the local classic Zergling GRP: directional
# groups 0..10 form the run, while 11..16 crouch/collapse into death art.
# Each complete directional group has 17 frames (north through south via east).
FRAMES = {"idle": 0, **{f"walk{pose}": 17 * (pose + 1) for pose in range(10)},
          **{f"death{pose}": 17 * (pose + 11) for pose in range(6)}}
DIRECTIONS = {"east": (8, False), "south": (16, False),
              "west": (8, True), "north": (0, False),
              "southeast": (12, False), "southwest": (12, True),
              "northwest": (4, True), "northeast": (4, False)}


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
    for candidates in (("Patch_rt.mpq",), ("BrooDat.mpq", "Broodat.mpq"),
                       ("StarDat.mpq", "Stardat.mpq")):
        archive = next((game_dir / candidate for candidate in candidates
                        if (game_dir / candidate).is_file()), None)
        if archive is None:
            continue
        archive = archive.resolve()
        with tempfile.TemporaryDirectory(dir=target.parent) as temp:
            result = subprocess.run(["smpq", "--extract", str(archive), name],
                                    cwd=temp, capture_output=True, text=True)
            found = Path(temp) / name
            if result.returncode == 0 and found.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(found, target)
                return archive.name
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


def prepare_marine(data: bytes, wpe: bytes, output: Path, palette: list[tuple[int, int, int]]):
    """The classic Marine GRP has 13 directional groups and eight death frames."""
    count, width, height = struct.unpack_from("<HHH", data)
    if count != 229 or (width, height) != (64, 64):
        raise ValueError(f"Unexpected Marine GRP: {count} frames, {width}x{height}")
    directions = list(DIRECTIONS)
    states = {"idle": [0], "walk": [17, 34], "attack": [51, 68, 85]}
    selected = {}
    registry = {"terran_marine": {}}

    def save(frame: int, filename: str, mirror: bool = False):
        image = decode_grp(data, wpe, frame)
        if mirror:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        bbox = image.getbbox()
        if bbox is None:
            raise ValueError(f"Empty Marine frame {frame}")
        cropped = quantize(image.crop(bbox), palette)
        cropped.save(output / filename)
        selected[filename] = {"source_frame": frame, "source_group": frame // 17,
                              "mirrored": mirror, "width": cropped.width, "height": cropped.height,
                              "x": bbox[0] - width // 2, "y": bbox[1] - height // 2,
                              "visible_pixels": sum(a != 0 for a in cropped.getchannel("A").getdata())}

    for state, bases in states.items():
        frames = {}
        for direction, (direction_frame, mirror) in DIRECTIONS.items():
            names = []
            for pose, base in enumerate(bases):
                filename = f"{state}{pose}_{direction}.png"
                save(base + direction_frame, filename, mirror)
                names.append(filename)
            frames[direction] = names
        registry["terran_marine"][state] = {"frames": frames,
                                            "ticks_per_frame": 0 if state == "idle" else 4 if state == "walk" else 2}
    death = []
    for pose in range(8):
        filename = f"death{pose}.png"
        save(221 + pose, filename)
        death.append(filename)
    registry["terran_marine"]["death"] = {"frames": death, "ticks_per_frame": 2,
                                            "directional": False}
    return selected, registry, count, width, height


def prepare_marine_pack(data: bytes, wpe: bytes, output: Path,
                         palette: list[tuple[int, int, int]], archives: dict) -> None:
    selected, registry, frame_count, canvas_width, canvas_height = prepare_marine(data, wpe, output, palette)
    manifest = {"unit": "marine", "kind": "terran_marine", "source": MARINE_RESOURCE,
                "palette": PALETTE, "archives": archives, "canvas": [canvas_width, canvas_height],
                "frame_count": frame_count, "source_sha256": hashlib.sha256(data).hexdigest(),
                "registry": registry, "frames": selected,
                "direction_convention": "N=0 NE=4 E=8 SE=12 S=16; western directions mirror eastern counterparts",
                "team_colour": "source palette indices 8..15 retained without player remap",
                "output_palette": "nearest OpenRCT2 standard palette colour, excluding special and primary remap indices"}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared {len(selected)} Marine frames in {output} from {archives}")
    return


def prepare_firebat_pack(data: bytes, wpe: bytes, output: Path,
                         palette: list[tuple[int, int, int]], archives: dict) -> None:
    """Classic Firebat has ten 17-direction banks, unlike the Marine GRP."""
    count, width, height = struct.unpack_from("<HHH", data)
    if (count, width, height) != (170, 32, 32):
        raise ValueError(f"Unexpected Firebat GRP: {count} frames, {width}x{height}")
    death = (output / ".source/death.grp").read_bytes()
    death_count, death_width, death_height = struct.unpack_from("<HHH", death)
    if death_count != 9 or (death_width, death_height) != (128, 128):
        raise ValueError("Unexpected classic small explosion GRP for Firebat death")
    selected = {}
    registry = {"terran_firebat": {}}

    def save(source: bytes, frame: int, canvas: tuple[int, int], name: str,
             mirror: bool = False) -> None:
        image = decode_grp(source, wpe, frame)
        if mirror:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        bbox = image.getbbox()
        if bbox is None:
            raise ValueError(f"Empty Firebat frame {frame}")
        cropped = quantize(image.crop(bbox), palette)
        cropped.save(output / name)
        selected[name] = {"source_frame": frame, "source": FIREBAT_RESOURCE if source is data
                          else FIREBAT_DEATH_RESOURCE, "mirrored": mirror,
                          "width": cropped.width, "height": cropped.height,
                          "x": bbox[0] - canvas[0] // 2, "y": bbox[1] - canvas[1] // 2,
                          "visible_pixels": sum(a != 0 for a in cropped.getchannel("A").getdata())}

    # Contact-sheet inspection: bank 0 is standing, banks 1-2 show the
    # flamethrower attack, and banks 3-9 contain locomotion poses.
    for state, banks in (("idle", (0,)), ("walk", (3, 5)), ("attack", (1, 2, 1))):
        frames = {}
        for direction, (facing, mirror) in DIRECTIONS.items():
            names = []
            for pose, bank in enumerate(banks):
                name = f"{state}{pose}_{direction}.png"
                save(data, bank * 17 + facing, (width, height), name, mirror)
                names.append(name)
            frames[direction] = names
        registry["terran_firebat"][state] = {"frames": frames,
                                               "ticks_per_frame": 0 if state == "idle" else 4 if state == "walk" else 2}
    death_names = []
    for pose in range(8):
        name = f"death{pose}.png"
        save(death, pose + 1, (death_width, death_height), name)
        death_names.append(name)
    registry["terran_firebat"]["death"] = {"frames": death_names,
                                             "ticks_per_frame": 2, "directional": False}
    manifest = {"unit": "firebat", "kind": "terran_firebat", "source": FIREBAT_RESOURCE,
                "death_source": FIREBAT_DEATH_RESOURCE, "palette": PALETTE,
                "archives": archives, "canvas": [width, height], "frame_count": count,
                "source_sha256": hashlib.sha256(data).hexdigest(),
                "registry": registry, "frames": selected,
                "direction_convention": "N=0 NE=4 E=8 SE=12 S=16; western directions mirror eastern counterparts",
                "output_palette": "nearest OpenRCT2 standard palette colour, excluding special and primary remap indices"}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared {len(selected)} Firebat frames in {output} from {archives}")


def prepare_medic_pack(data: bytes, wpe: bytes, output: Path,
                       palette: list[tuple[int, int, int]], archives: dict) -> None:
    """Medic banks 4-5 carry the classic gold healing-gun effect."""
    count, width, height = struct.unpack_from("<HHH", data)
    if (count, width, height) != (230, 64, 64):
        raise ValueError(f"Unexpected Medic GRP: {count} frames, {width}x{height}")
    selected, registry = {}, {"terran_medic": {}}

    def save(frame: int, name: str, mirror: bool = False) -> None:
        image = decode_grp(data, wpe, frame)
        if mirror:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        bbox = image.getbbox()
        if bbox is None:
            raise ValueError(f"Empty Medic frame {frame}")
        cropped = quantize(image.crop(bbox), palette)
        cropped.save(output / name)
        selected[name] = {"source_frame": frame, "mirrored": mirror,
                          "width": cropped.width, "height": cropped.height,
                          "x": bbox[0] - width // 2, "y": bbox[1] - height // 2}

    for state, banks in (("idle", (0,)), ("walk", (6, 7)), ("heal", (4, 5, 4))):
        frames = {}
        for direction, (facing, mirror) in DIRECTIONS.items():
            names = []
            for pose, bank in enumerate(banks):
                name = f"{state}{pose}_{direction}.png"
                save(bank * 17 + facing, name, mirror)
                names.append(name)
            frames[direction] = names
        registry["terran_medic"][state] = {"frames": frames,
                                           "ticks_per_frame": 0 if state == "idle" else 4 if state == "walk" else 2}
    death = []
    for pose in range(8):
        name = f"death{pose}.png"
        save(222 + pose, name)
        death.append(name)
    registry["terran_medic"]["death"] = {"frames": death,
                                         "ticks_per_frame": 2, "directional": False}
    (output / "manifest.json").write_text(json.dumps({
        "unit": "medic", "kind": "terran_medic", "source": MEDIC_RESOURCE,
        "palette": PALETTE, "archives": archives, "canvas": [width, height],
        "frame_count": count, "source_sha256": hashlib.sha256(data).hexdigest(),
        "registry": registry, "frames": selected,
        "direction_convention": "N=0 NE=4 E=8 SE=12 S=16; west mirrors east",
        "output_palette": "nearest OpenRCT2 standard palette colour"}, indent=2) + "\n")
    print(f"Prepared {len(selected)} Medic frames in {output} from {archives}")


def prepare_vulture_pack(data: bytes, wpe: bytes, output: Path,
                         palette: list[tuple[int, int, int]], archives: dict) -> None:
    """Vulture has one 17-direction body bank; native movement rotates it."""
    count, width, height = struct.unpack_from("<HHH", data)
    if (count, width, height) != (17, 100, 100):
        raise ValueError(f"Unexpected Vulture GRP: {count} frames, {width}x{height}")
    explosion = (output / ".source/death.grp").read_bytes()
    if struct.unpack_from("<HHH", explosion) != (9, 128, 128):
        raise ValueError("Unexpected classic small explosion for Vulture death")
    selected, frames = {}, {}
    for direction, (facing, mirror) in DIRECTIONS.items():
        image = decode_grp(data, wpe, facing)
        if mirror:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        bbox = image.getbbox()
        if bbox is None:
            raise ValueError(f"Empty Vulture frame {facing}")
        name = f"idle0_{direction}.png"
        cropped = quantize(image.crop(bbox), palette)
        cropped.save(output / name)
        selected[name] = {"source_frame": facing, "source": VULTURE_RESOURCE,
                          "mirrored": mirror, "width": cropped.width,
                          "height": cropped.height, "x": bbox[0] - width // 2,
                          "y": bbox[1] - height // 2}
        frames[direction] = [name]
    death = []
    for pose in range(8):
        image = decode_grp(explosion, wpe, pose + 1)
        bbox = image.getbbox()
        if bbox is None:
            raise ValueError(f"Empty Vulture death frame {pose}")
        name = f"death{pose}.png"
        cropped = quantize(image.crop(bbox), palette)
        cropped.save(output / name)
        selected[name] = {"source_frame": pose + 1, "source": FIREBAT_DEATH_RESOURCE,
                          "width": cropped.width, "height": cropped.height,
                          "x": bbox[0] - 64, "y": bbox[1] - 64}
        death.append(name)
    registry = {"terran_vulture": {"idle": {"frames": frames, "ticks_per_frame": 0},
                                   "death": {"frames": death, "ticks_per_frame": 2,
                                             "directional": False}}}
    (output / "manifest.json").write_text(json.dumps({
        "unit": "vulture", "kind": "terran_vulture", "source": VULTURE_RESOURCE,
        "death_source": FIREBAT_DEATH_RESOURCE, "palette": PALETTE,
        "archives": archives, "canvas": [width, height], "frame_count": count,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "registry": registry, "frames": selected,
        "direction_convention": "N=0 NE=4 E=8 SE=12 S=16; west mirrors east",
        "output_palette": "nearest OpenRCT2 standard palette colour"}, indent=2) + "\n")
    print(f"Prepared {len(selected)} Vulture frames in {output} from {archives}")


def prepare_flame_pack(data: bytes, wpe: bytes, output: Path,
                       palette: list[tuple[int, int, int]], archives: dict) -> None:
    """Extract the separate directional FlameThrower thingy, not Firebat poses."""
    count, width, height = struct.unpack_from("<HHH", data)
    if (count, width, height) != (221, 224, 224):
        raise ValueError(f"Unexpected FlameThrower GRP: {count} frames, {width}x{height}")
    selected, frames = {}, {}
    # Every second 17-direction bank samples the growth and fade of the burst.
    banks = (0, 2, 4, 6, 8, 10, 12)
    for direction, (facing, mirror) in DIRECTIONS.items():
        names = []
        for pose, bank in enumerate(banks):
            frame = bank * 17 + facing
            image = decode_grp(data, wpe, frame)
            if mirror:
                image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            bbox = image.getbbox()
            if bbox is None:
                raise ValueError(f"Empty FlameThrower frame {frame}")
            name = f"burst{pose}_{direction}.png"
            cropped = quantize(image.crop(bbox), palette)
            cropped.save(output / name)
            selected[name] = {"source_frame": frame, "mirrored": mirror,
                              "width": cropped.width, "height": cropped.height,
                              "x": bbox[0] - width // 2, "y": bbox[1] - height // 2}
            names.append(name)
        frames[direction] = names
    (output / "manifest.json").write_text(json.dumps({
        "unit": "flame", "kind": "firebat_flame", "source": FLAME_RESOURCE,
        "palette": PALETTE, "archives": archives, "canvas": [width, height],
        "frame_count": count, "source_sha256": hashlib.sha256(data).hexdigest(),
        "registry": {"firebat_flame": {"burst": {"frames": frames, "ticks_per_frame": 2}}},
        "frames": selected,
        "direction_convention": "N=0 NE=4 E=8 SE=12 S=16; west mirrors east",
        "output_palette": "nearest OpenRCT2 standard palette colour"}, indent=2) + "\n")
    print(f"Prepared {len(selected)} FlameThrower frames in {output} from {archives}")

def prepare_zergling_pack(data: bytes, wpe: bytes, output: Path,
                           palette: list[tuple[int, int, int]], archives: dict) -> None:
    frame_count, canvas_width, canvas_height = struct.unpack_from("<HHH", data)
    if frame_count < 17 * 17:
        raise ValueError(f"Expected at least 17 directional groups, got {frame_count} frames")
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
            selected[filename] = {"source_frame": frame, "source_group": base // 17,
                                  "source_direction": facing, "mirrored": mirror,
                                  "width": cropped.width, "height": cropped.height,
                                  "x": bbox[0] - canvas_width // 2,
                                  "y": bbox[1] - canvas_height // 2,
                                  "visible_pixels": sum(a != 0 for a in cropped.getchannel("A").getdata())}
    groups = [{"group": group, "first_frame": group * 17,
               "last_frame": min(frame_count - 1, group * 17 + 16),
               "classification": "idle" if group == 0 else "walk" if group <= 10 else "death" if group <= 16 else "non_locomotion"}
              for group in range((frame_count + 16) // 17)]
    directions = list(DIRECTIONS)
    registry = {"zerg_zergling": {"idle": {"frames": {direction: [f"idle_{direction}.png"]
                                                   for direction in directions}, "ticks_per_frame": 0},
                                "walk": {"frames": {direction: [f"walk{pose}_{direction}.png" for pose in range(10)]
                                                    for direction in directions}, "ticks_per_frame": 4},
                                "death": {"frames": {direction: [f"death{pose}_{direction}.png" for pose in range(6)]
                                                     for direction in directions}, "ticks_per_frame": 3}}}
    manifest = {"unit": "zergling", "kind": "zerg_zergling", "source": RESOURCE, "palette": PALETTE,
                "archives": archives, "canvas": [canvas_width, canvas_height],
                "frame_count": frame_count, "source_sha256": hashlib.sha256(data).hexdigest(),
                "source_groups": groups, "registry": registry,
                "direction_convention": "N=0 NE=4 E=8 SE=12 S=16; western directions mirror eastern counterparts",
                "team_colour": "source palette indices 8..15 retained without player remap",
                "shadow": "separate StarCraft shadow artwork omitted",
                "output_palette": "nearest OpenRCT2 standard palette colour, excluding special and primary remap indices",
                "frames": selected}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared {len(selected)} frames in {output} from {archives}")


UNIT_PROFILES = {
    "marine": {"resource": MARINE_RESOURCE, "prepare": prepare_marine_pack},
    "firebat": {"resource": FIREBAT_RESOURCE, "prepare": prepare_firebat_pack},
    "medic": {"resource": MEDIC_RESOURCE, "prepare": prepare_medic_pack},
    "vulture": {"resource": VULTURE_RESOURCE, "prepare": prepare_vulture_pack},
    "flame": {"resource": FLAME_RESOURCE, "prepare": prepare_flame_pack},
    "zergling": {"resource": RESOURCE, "prepare": prepare_zergling_pack},
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path,
                        default=Path(os.environ.get("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft")))
    parser.add_argument("--unit", choices=UNIT_PROFILES, default="zergling")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if shutil.which("smpq") is None:
        parser.error("smpq is required (Debian package: smpq / StormLib)")
    output = (args.output or OUTPUT.parent / args.unit).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = output / ".source"
    source.mkdir(exist_ok=True)
    profile = UNIT_PROFILES[args.unit]
    resource = profile["resource"]
    grp_path, wpe_path = source / f"{args.unit}.grp", source / "Badlands.wpe"
    archives = {resource: extract(args.game_dir, resource, grp_path),
                PALETTE: extract(args.game_dir, PALETTE, wpe_path)}
    if args.unit in ("firebat", "vulture"):
        archives[FIREBAT_DEATH_RESOURCE] = extract(
            args.game_dir, FIREBAT_DEATH_RESOURCE, source / "death.grp")
    data, wpe = grp_path.read_bytes(), wpe_path.read_bytes()
    if len(wpe) != 1024:
        raise ValueError(f"Expected 1024-byte WPE palette, got {len(wpe)}")
    profile["prepare"](data, wpe, output, openrct2_palette(), archives)

if __name__ == "__main__":
    main()
