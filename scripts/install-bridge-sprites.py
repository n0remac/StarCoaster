#!/usr/bin/env python3
"""Validate and stage one local sprite pack into the ignored OpenRCT2 checkout."""

import json
from pathlib import Path
import re
import shutil
import sys

from PIL import Image


MARINE_DIRECTIONS = ("east", "southeast", "south", "southwest", "west", "northwest", "north", "northeast")
MARINE_NAMES = [f"{state}{pose}_{direction}.png"
                for state, count in (("idle", 1), ("walk", 2), ("attack", 3))
                for pose in range(count) for direction in MARINE_DIRECTIONS]
MARINE_NAMES += [f"death{pose}.png" for pose in range(8)]


def placeholder_marine(destination: Path, upstream: Path) -> None:
    """Original CC0 human soldier art for machines without local StarCraft data."""
    from PIL import ImageDraw
    destination.mkdir(parents=True, exist_ok=True)
    # Use exact standard palette colours so the g2 importer does not lose pixels.
    header = upstream / "src/openrct2/drawing/ImageImporter.h"
    block = header.read_text().split("StandardPalette = { {", 1)[1].split("} };", 1)[0]
    block = re.sub(r"//[^\n]*", "", block)
    bgra = re.findall(r"\{\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\}", block)
    colours = [(int(r), int(g), int(b), 255) for b, g, r, _ in bgra]
    steel, dark, skin, visor = (colours[index] for index in (85, 42, 25, 143))
    for name in MARINE_NAMES:
        image = Image.new("RGBA", (64, 64))
        draw = ImageDraw.Draw(image)
        death = name.startswith("death")
        if death:
            pose = int(name[5:-4])
            draw.ellipse((20, 46 + min(pose, 6), 45, 53 + min(pose, 6)), fill=steel)
            draw.rectangle((18, 49 + min(pose, 6), 42, 51 + min(pose, 6)), fill=dark)
        else:
            pose = int(name[name.index("k") + 1]) if name.startswith("walk") else 0
            draw.rectangle((24, 28, 39, 47), fill=steel)
            draw.rectangle((25, 46, 30, 54 - pose * 2), fill=dark)
            draw.rectangle((35, 46, 40, 52 + pose * 2), fill=dark)
            draw.ellipse((25, 16, 39, 31), fill=skin)
            draw.rectangle((24, 15, 40, 22), fill=steel)
            draw.rectangle((26, 21, 40, 23), fill=visor)
            draw.rectangle((18, 31, 49 + (3 if name.startswith("attack") else 0), 35), fill=dark)
            draw.rectangle((19, 29, 25, 37), fill=steel)
        image.crop(image.getbbox()).save(destination / name)
    (destination / "LICENSE.txt").write_text("StarCoaster original Marine placeholder. CC0 1.0 Universal.\n")


def standard_colours(upstream: Path) -> set[tuple[int, int, int]]:
    header = upstream / "src/openrct2/drawing/ImageImporter.h"
    block = header.read_text().split("StandardPalette = { {", 1)[1].split("} };", 1)[0]
    block = re.sub(r"//[^\n]*", "", block)
    entries = re.findall(r"\{\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\}", block)
    if len(entries) != 256:
        raise SystemExit(f"Could not read OpenRCT2's 256-colour palette from {header}")
    return {(int(red), int(green), int(blue)) for blue, green, red, _ in entries}


def main() -> None:
    source, upstream, pack = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    if not source.is_dir():
        raise SystemExit(f"Missing {pack} sprite pack: {source}. Run scripts/prepare-starcraft-sprites.py first.")
    manifest_path = source / "manifest.json"
    if pack == "starcraft-local" and not manifest_path.is_file():
        raise SystemExit(f"Missing StarCraft sprite manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    if pack == "starcraft-local":
        registry = manifest.get("registry", {}).get("alien_scout", {})
        if len(manifest.get("frames", {})) != 136 or len(registry.get("walk", {}).get("frames", {})) != 8 \
           or len(registry.get("death", {}).get("frames", {}).get("east", [])) != 6:
            raise SystemExit("StarCraft manifest must contain 136 frames including six death poses")
    sprite_list = upstream / "resources/g2/sprites.json"
    contents = sprite_list.read_text()
    enum_text = (upstream / "src/openrct2/SpriteIds.h").read_text()
    if len(re.findall(r"^\s*SPR_BRIDGE_SCOUT_(?:IDLE|WALK[0-9]+)_", enum_text, re.MULTILINE)) != 88:
        raise SystemExit("OpenRCT2 sprite ID range must contain exactly 88 bridge images")
    if len(re.findall(r"^\s*SPR_BRIDGE_MARINE_", enum_text, re.MULTILINE)) != 56:
        raise SystemExit("OpenRCT2 sprite ID range must contain exactly 56 Marine images")
    if len(re.findall(r"^\s*SPR_BRIDGE_SCOUT_DEATH[0-5]_", enum_text, re.MULTILINE)) != 48:
        raise SystemExit("OpenRCT2 sprite ID range must contain exactly 48 scout death images")
    if len(re.findall(r"^\s*SPR_BRIDGE_HEALTH_", enum_text, re.MULTILINE)) != 22:
        raise SystemExit("OpenRCT2 sprite ID range must contain exactly 22 health bar images")
    colours = standard_colours(upstream)
    prepared = []
    diagonals = {"southeast": "east", "southwest": "south",
                 "northwest": "west", "northeast": "north"}
    motions = ("idle", *(f"walk{index}" for index in range(10)), *(f"death{index}" for index in range(6)))
    for motion in motions:
        for direction in ("east", "south", "west", "north", *diagonals):
            name = f"{motion}_{direction}.png"
            fallback_motion = ("idle" if motion.startswith("death") else motion
                               if motion in ("idle", "walk0", "walk1") else f"walk{int(motion[4:]) % 2}")
            source_name = (f"{fallback_motion}_{diagonals.get(direction, direction)}.png"
                           if pack == "alien-scout" else name)
            path = source / source_name
            if not path.is_file():
                raise SystemExit(f"Missing required {pack} frame: {path}")
            with Image.open(path) as image:
                image.load()
                if image.mode != "RGBA" or not (1 <= image.width <= 300 and 1 <= image.height <= 300):
                    raise SystemExit(f"Incompatible sprite {path}: expected RGBA PNG up to 300x300")
                if image.getchannel("A").getbbox() is None:
                    raise SystemExit(f"Empty sprite: {path}")
                if any(alpha not in (0, 255) or (alpha and (red, green, blue) not in colours)
                       for red, green, blue, alpha in image.getdata()):
                    raise SystemExit(f"Incompatible sprite palette or alpha in {path}; regenerate the pack")
                if pack == "starcraft-local":
                    meta = manifest.get("frames", {}).get(name)
                    if not meta or (meta["width"], meta["height"]) != image.size:
                        raise SystemExit(f"Sprite/manifest mismatch: {path}")
                    kind = "idle" if motion == "idle" else "death" if motion.startswith("death") else "walk"
                    if name not in registry[kind]["frames"][direction]:
                        raise SystemExit(f"Sprite missing from kind registry: {name}")
                    x, y = meta["x"], meta["y"]
                else:
                    x, y = -16, -28
            pattern = re.compile(r'(\{\s*"path": "bridge/' + re.escape(name)
                                 + r'", "x": )-?\d+(, "y": )-?\d+(\s*\})')
            contents, count = pattern.subn(lambda m: f"{m[1]}{x}{m[2]}{y}{m[3]}", contents)
            if count != 1:
                raise SystemExit(f"Missing or duplicate g2 metadata entry: {name}")
            prepared.append((path, name))
    local_marine = source.parent / "marine" if pack == "starcraft-local" else Path("/") / "missing-marine-pack"
    if pack == "starcraft-local" and not (local_marine / "manifest.json").is_file():
        raise SystemExit(f"Missing StarCraft Marine manifest: {local_marine / 'manifest.json'}. "
                         "Run scripts/prepare-starcraft-sprites.py --unit marine first.")
    marine_source = local_marine if (local_marine / "manifest.json").is_file() else Path(__file__).resolve().parent.parent / "run-data/generated-assets/placeholder/marine"
    if marine_source != local_marine:
        placeholder_marine(marine_source, upstream)
    marine_manifest = json.loads((marine_source / "manifest.json").read_text()) if marine_source == local_marine else None
    if marine_manifest is not None:
        registry = marine_manifest.get("registry", {}).get("terran_marine", {})
        if len(marine_manifest.get("frames", {})) != 56 or set(registry) != {"idle", "walk", "attack", "death"}:
            raise SystemExit("Marine manifest must contain 56 frames and four animation states")
    for name in MARINE_NAMES:
        path = marine_source / name
        if not path.is_file():
            raise SystemExit(f"Missing Marine frame: {path}")
        with Image.open(path) as image:
            image.load()
            if image.mode != "RGBA" or not (1 <= image.width <= 300 and 1 <= image.height <= 300):
                raise SystemExit(f"Incompatible Marine sprite: {path}")
            if any(alpha not in (0, 255) or (alpha and (red, green, blue) not in colours)
                   for red, green, blue, alpha in image.getdata()):
                raise SystemExit(f"Incompatible Marine palette or alpha: {path}")
        meta = marine_manifest["frames"].get(name) if marine_manifest else None
        if marine_manifest and (not meta or (meta["width"], meta["height"]) != image.size):
            raise SystemExit(f"Marine sprite/manifest mismatch: {path}")
        x, y = (meta["x"], meta["y"]) if meta else (-image.width // 2, -image.height)
        pattern = re.compile(r'(\{\s*"path": "bridge/marine/' + re.escape(name)
                             + r'", "x": )-?\d+(, "y": )-?\d+(\s*\})')
        contents, count = pattern.subn(lambda m: f"{m[1]}{x}{m[2]}{y}{m[3]}", contents)
        if count != 1:
            raise SystemExit(f"Missing or duplicate Marine g2 entry: {name}")
        prepared.append((path, "marine/" + name))
    # Small native overlays; each image is an exact-palette health fraction.
    health_source = Path(__file__).resolve().parent.parent / "run-data/generated-assets/bridge-health"
    health_source.mkdir(parents=True, exist_ok=True)
    from PIL import ImageDraw
    palette_header = (upstream / "src/openrct2/drawing/ImageImporter.h").read_text()
    block = re.sub(r"//[^\n]*", "", palette_header.split("StandardPalette = { {", 1)[1].split("} };", 1)[0])
    entries = re.findall(r"\{\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\}", block)
    palette = [(int(red), int(green), int(blue), 255) for blue, green, red, _ in entries]
    available = [palette[i] for i in range(10, 230)]
    def colour(wanted):
        return min(available, key=lambda value: sum((value[index] - wanted[index]) ** 2 for index in range(3)))
    outline, background = colour((18, 22, 21)), colour((62, 70, 65))
    for faction, wanted in (("marine", (70, 220, 100)), ("zergling", (195, 90, 225))):
        fill = colour(wanted)
        for level in range(11):
            name = f"{faction}{level}.png"
            image = Image.new("RGBA", (20, 4))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 19, 3), fill=outline)
            draw.rectangle((1, 1, 18, 2), fill=background)
            if level:
                draw.rectangle((1, 1, 1 + (17 * level + 9) // 10, 2), fill=fill)
            path = health_source / name
            image.save(path)
            pattern = re.compile(r'(\{\s*"path": "bridge/health/' + re.escape(name)
                                 + r'", "x": )-?\d+(, "y": )-?\d+(\s*\})')
            y = -42 if faction == "marine" else -34
            contents, count = pattern.subn(lambda m: f"{m[1]}-10{m[2]}{y}{m[3]}", contents)
            if count != 1:
                raise SystemExit(f"Missing or duplicate health g2 entry: {name}")
            prepared.append((path, "health/" + name))
    target = upstream / "resources/g2/bridge"
    target.mkdir(parents=True, exist_ok=True)
    changed = False
    for path, name in prepared:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or destination.read_bytes() != path.read_bytes():
            shutil.copyfile(path, destination)
            changed = True
    if sprite_list.read_text() != contents:
        sprite_list.write_text(contents)
        changed = True
    # CMake tracks resource contents through CONFIGURE_DEPENDS; force a rebuild
    # when a selected source's bytes change while its filenames remain fixed.
    if changed:
        print(f"Staged {pack} pack; g2.dat will be rebuilt")
    else:
        print(f"Staged {pack} pack (unchanged)")


if __name__ == "__main__":
    main()
