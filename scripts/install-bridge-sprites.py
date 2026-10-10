#!/usr/bin/env python3
"""Validate and stage one local sprite pack into the ignored OpenRCT2 checkout."""

import json
from pathlib import Path
import re
import shutil
import sys

from PIL import Image


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
        if len(manifest.get("frames", {})) != 88 or len(registry.get("walk", {}).get("frames", {})) != 8:
            raise SystemExit("StarCraft manifest must contain 88 frames and eight walk directions")
    sprite_list = upstream / "resources/g2/sprites.json"
    contents = sprite_list.read_text()
    enum_text = (upstream / "src/openrct2/SpriteIds.h").read_text()
    if len(re.findall(r"^\s*SPR_BRIDGE_SCOUT_(?:IDLE|WALK[0-9]+)_", enum_text, re.MULTILINE)) != 88:
        raise SystemExit("OpenRCT2 sprite ID range must contain exactly 88 bridge images")
    colours = standard_colours(upstream)
    prepared = []
    diagonals = {"southeast": "east", "southwest": "south",
                 "northwest": "west", "northeast": "north"}
    motions = ("idle", *(f"walk{index}" for index in range(10)))
    for motion in motions:
        for direction in ("east", "south", "west", "north", *diagonals):
            name = f"{motion}_{direction}.png"
            fallback_motion = motion if motion in ("idle", "walk0", "walk1") else f"walk{int(motion[4:]) % 2}"
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
                    kind = "idle" if motion == "idle" else "walk"
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
    target = upstream / "resources/g2/bridge"
    target.mkdir(parents=True, exist_ok=True)
    changed = False
    for path, name in prepared:
        destination = target / name
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
