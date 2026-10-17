#!/usr/bin/env python3
"""Extract local classic StarCraft unit sprites. Never commit the output."""

import argparse
import hashlib
import io
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
FLAME_RESOURCE = "unit/thingy/flamer.grp"
FLAME_LIGHT_RESOURCE = "Tileset/Badlands/ofire.pcx"
PALETTE = "Tileset/Badlands.wpe"
DIRECTIONS = json.loads((ROOT / "bridge-protocol/starcraft-visuals.json").read_text())["directions"]


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


def prepare_flame_pack(data: bytes, wpe: bytes, output: Path,
                       palette: list[tuple[int, int, int]], archives: dict,
                       light_data: bytes, image_data: bytes) -> None:
    """Extract FlameThrower using the native image's orange fire remap."""
    profile = visual_profiles()["effects"]["firebat_flame"]
    count, width, height = struct.unpack_from("<HHH", data)
    if (count, width, height) != (profile["frame_count"], *profile["canvas"]):
        raise ValueError(f"Unexpected FlameThrower GRP: {count} frames, {width}x{height}")
    enum_source = (ROOT / "upstream/openbw/bwenums.h").read_text()
    image_names = re.findall(r"\bIMAGEID_[A-Za-z0-9_]+\b",
                             enum_source.split("enum struct ImageTypes : int {", 1)[1].split("};", 1)[0])
    image_index = image_names.index("IMAGEID_FlameThrower")
    if len(image_data) < 10 * 999 or (image_data[8 * 999 + image_index],
                                      image_data[9 * 999 + image_index]) != (9, 1):
        raise ValueError("Pinned FlameThrower image no longer uses orange fire remap")
    light = Image.open(io.BytesIO(light_data))
    if light.size != (256, 63):
        raise ValueError(f"Unexpected Badlands fire remap size: {light.size}")
    # images.dat gives FlameThrower modifier 9, colour shift 1. OpenBW's
    # renderer indexes ofire.pcx with source index - 1 and the background
    # palette index. OpenRCT2 cannot blend that indexed table at draw time, so
    # bake it against Badlands dark ground index 220. Damage stays in OpenBW.
    background_index = 220
    remapped = bytearray(wpe)
    for source_index in range(1, 64):
        result_index = light.getpixel((background_index, source_index - 1))
        remapped[source_index * 4:source_index * 4 + 4] = wpe[result_index * 4:result_index * 4 + 4]
    selected, frames = {}, {}
    # Every second 17-direction bank samples the growth and fade of the burst.
    banks = profile["banks"]
    for direction, (facing, mirror) in DIRECTIONS.items():
        names = []
        for pose, bank in enumerate(banks):
            frame = bank * profile["stride"] + facing
            image = decode_grp(data, remapped, frame)
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
        "registry": {"firebat_flame": {"burst": {"frames": frames, "ticks_per_frame": profile["ticks"]}}},
        "frames": selected,
        "direction_convention": "N=0 NE=4 E=8 SE=12 S=16; west mirrors east",
        "fire_remap": {"source": FLAME_LIGHT_RESOURCE, "background_index": background_index,
                        "modifier": 9, "color_shift": 1},
        "output_palette": "nearest OpenRCT2 standard palette colour"}, indent=2) + "\n")
    print(f"Prepared {len(selected)} FlameThrower frames in {output} from {archives}")

def visual_profiles() -> dict:
    return json.loads((ROOT / "bridge-protocol/starcraft-visuals.json").read_text())


def prepare_profile_pack(kind: str, profile: dict, game_dir: Path, output: Path) -> None:
    """Extract a conventional directional GRP from declarative frame groups."""
    directions = visual_profiles()["directions"]
    source = output / ".source"
    source.mkdir(exist_ok=True)
    palette_path = source / "Badlands.wpe"
    archives = {PALETTE: extract(game_dir, PALETTE, palette_path)}
    wpe = palette_path.read_bytes()
    if len(wpe) != 1024:
        raise ValueError("Expected a 1024-byte Badlands palette")
    sources = {}

    def load(resource: str, name: str, image_name: str | None = None) -> bytes:
        if image_name:
            import runpy
            resolved = runpy.run_path(str(ROOT / "scripts/install-starcraft-construction-object.py"))[
                "image_resource"](game_dir, image_name, {"extract": extract})
            if resolved.lower() != resource.lower():
                raise ValueError(f"{image_name} resolves to {resolved}, expected {resource}")
        if resource not in sources:
            path = source / name
            archives[resource] = extract(game_dir, resource, path)
            sources[resource] = path.read_bytes()
        return sources[resource]

    primary = load(profile["source"], kind + ".grp", profile.get("image"))
    count, width, height = struct.unpack_from("<HHH", primary)
    expected = profile.get("frame_count")
    if (expected is not None and count != expected) or count < profile.get("minimum_frame_count", 0):
        raise ValueError(f"Unexpected {kind} GRP frame count: {count}")
    if "canvas" in profile and (width, height) != tuple(profile["canvas"]):
        raise ValueError(f"Unexpected {kind} GRP canvas: {width}x{height}")
    canvas = [width, height]
    selected, registry = {}, {kind: {}}
    palette = openrct2_palette()

    def frame_image(data: bytes, resource: str, frame: int, frame_canvas: tuple[int, int],
                    filename: str, mirror: bool) -> None:
        image = decode_grp(data, wpe, frame)
        if mirror:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        bbox = image.getbbox()
        if bbox is None:
            raise ValueError(f"Empty {kind} frame {frame} ({filename})")
        cropped = quantize(image.crop(bbox), palette)
        cropped.save(output / filename)
        selected[filename] = {"source_frame": frame, "source": resource,
                              "source_group": frame // profile["stride"], "mirrored": mirror,
                              "width": cropped.width, "height": cropped.height,
                              "x": bbox[0] - frame_canvas[0] // 2,
                              "y": bbox[1] - frame_canvas[1] // 2,
                              "visible_pixels": sum(cropped.getchannel("A").getdata()) // 255}

    def prepare_groups(groups: dict, prefix: str, primary_resource: str,
                       default_source: bytes, default_canvas: tuple[int, int], stride: int) -> dict:
        results = {}
        for state, animation in groups.items():
            if "fallback" in animation:
                continue
            resource = animation.get("source", primary_resource)
            data = default_source if resource == primary_resource else load(resource, prefix + state + ".grp")
            frame_canvas = tuple(animation.get("canvas", default_canvas))
            actual_count, actual_width, actual_height = struct.unpack_from("<HHH", data)
            if (actual_width, actual_height) != frame_canvas:
                raise ValueError(f"Unexpected {kind} {state} source canvas")
            if "banks" in animation:
                frames = {}
                for direction, (facing, mirror) in directions.items():
                    names = []
                    for pose, bank in enumerate(animation["banks"]):
                        frame = bank * stride + facing
                        if frame >= actual_count:
                            raise ValueError(f"Invalid {kind} {state} source frame {frame}")
                        label = state if animation.get("name_without_zero") else f"{state}{pose}"
                        filename = f"{prefix}{label}_{direction}.png"
                        frame_image(data, resource, frame, frame_canvas, filename, mirror)
                        names.append(filename)
                    frames[direction] = names
                results[state] = {"frames": frames, "ticks_per_frame": animation["ticks"]}
            else:
                names = []
                for pose, frame in enumerate(animation["frames"]):
                    if frame >= actual_count:
                        raise ValueError(f"Invalid {kind} {state} source frame {frame}")
                    filename = f"{prefix}{state}{pose}.png"
                    frame_image(data, resource, frame, frame_canvas, filename, False)
                    names.append(filename)
                results[state] = {"frames": names, "ticks_per_frame": animation["ticks"],
                                  "directional": False}
        return results

    registry[kind].update(prepare_groups(profile["animations"], "", profile["source"],
                                         primary, (width, height), profile["stride"]))
    # Old G2 paths are permanent IDs. Keep producing retired frames so a clean
    # checkout can build the full, append-only atlas after a mapping correction.
    legacy_banks = {
        "zergling": {"walk": list(range(1, 11)), "death": list(range(11, 17))},
        "hydralisk": {"walk": list(range(1, 11)), "death": [15, 16]},
    }.get(profile["asset"], {})
    for state, banks in legacy_banks.items():
        for pose, bank in enumerate(banks):
            for direction, (facing, mirror) in directions.items():
                filename = f"{state}{pose}_{direction}.png"
                if filename not in selected:
                    frame_image(primary, profile["source"], bank * profile["stride"] + facing,
                                (width, height), filename, mirror)
    attachments = {}
    for attachment in profile.get("attachments", []):
        name = attachment["name"]
        data = load(attachment["source"], name + ".grp", attachment.get("image"))
        if struct.unpack_from("<HHH", data) != (attachment["frame_count"], *attachment["canvas"]):
            raise ValueError(f"Unexpected {kind} {name} attachment GRP")
        attachments[name] = prepare_groups(attachment["animations"], name + "_",
                                           attachment["source"], data,
                                           tuple(attachment["canvas"]), attachment["stride"])
    if attachments:
        registry[kind]["attachments"] = attachments
    manifest = {"unit": profile["asset"], "kind": kind, "source": profile["source"],
                "palette": PALETTE, "archives": archives, "canvas": canvas,
                "frame_count": count, "source_sha256": hashlib.sha256(primary).hexdigest(),
                "registry": registry, "frames": selected,
                "direction_convention": "N=0 NE=4 E=8 SE=12 S=16; western directions mirror eastern counterparts",
                "output_palette": "nearest OpenRCT2 standard palette colour"}
    death_source = profile["animations"].get("death", {}).get("source")
    if death_source:
        manifest["death_source"] = death_source
    if profile["asset"] == "zergling":
        manifest["source_groups"] = [
            {"group": group, "first_frame": group * profile["stride"],
             "last_frame": min(count - 1, (group + 1) * profile["stride"] - 1),
             "classification": "attack" if group <= 4 else "idle" if group == 5
                               else "walk" if group <= 11 else "burrow" if group <= 16
                               else "death"}
            for group in range((count + profile["stride"] - 1) // profile["stride"])]
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared {len(selected)} {kind} frames in {output}")


def registered_profiles() -> dict:
    catalog = json.loads((ROOT / "bridge-protocol/starcraft-types.json").read_text())
    visuals = visual_profiles()
    units = {unit["visual"]: visuals["units"][unit["visual"]] for unit in catalog["units"]}
    return {profile["asset"]: (kind, profile) for kind, profile in units.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path,
                        default=Path(os.environ.get("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft")))
    profiles = registered_profiles()
    effects = visual_profiles()["effects"]
    parser.add_argument("--unit", choices=sorted(set(profiles) | {item["asset"] for item in effects.values()}),
                        default="zergling")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if shutil.which("smpq") is None:
        parser.error("smpq is required (Debian package: smpq / StormLib)")
    output = (args.output or OUTPUT.parent / args.unit).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.unit in profiles:
        kind, profile = profiles[args.unit]
        prepare_profile_pack(kind, profile, args.game_dir, output)
        return
    # The Firebat flame uses a source palette remap. Keep that format-specific
    # decoder until another effect needs the same layout.
    effect = next(item for item in effects.values() if item["asset"] == args.unit)
    source = output / ".source"
    source.mkdir(exist_ok=True)
    grp_path, wpe_path = source / f"{args.unit}.grp", source / "Badlands.wpe"
    archives = {effect["source"]: extract(args.game_dir, effect["source"], grp_path),
                PALETTE: extract(args.game_dir, PALETTE, wpe_path),
                effect["palette_remap"]: extract(args.game_dir, effect["palette_remap"], source / "ofire.pcx"),
                "arr/images.dat": extract(args.game_dir, "arr/images.dat", source / "images.dat")}
    prepare_flame_pack(grp_path.read_bytes(), wpe_path.read_bytes(), output,
                       openrct2_palette(), archives, (source / "ofire.pcx").read_bytes(),
                       (source / "images.dat").read_bytes())

if __name__ == "__main__":
    main()
