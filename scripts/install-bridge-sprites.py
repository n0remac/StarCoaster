#!/usr/bin/env python3
"""Validate and stage one local sprite pack into the ignored OpenRCT2 checkout."""

import json
from pathlib import Path
import re
import shutil
import sys

from PIL import Image


def main() -> None:
    source, upstream, pack = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    if not source.is_dir():
        raise SystemExit(f"Missing {pack} sprite pack: {source}. Run scripts/prepare-starcraft-sprites.py first.")
    manifest_path = source / "manifest.json"
    if pack == "starcraft-local" and not manifest_path.is_file():
        raise SystemExit(f"Missing StarCraft sprite manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    target = upstream / "resources/g2/bridge"
    target.mkdir(parents=True, exist_ok=True)
    sprite_list = upstream / "resources/g2/sprites.json"
    contents = sprite_list.read_text()
    changed = False
    for motion in ("idle", "walk0", "walk1"):
        for direction in ("east", "south", "west", "north"):
            name = f"{motion}_{direction}.png"
            path = source / name
            if not path.is_file():
                raise SystemExit(f"Missing required {pack} frame: {path}")
            with Image.open(path) as image:
                image.load()
                if image.mode != "RGBA" or not (1 <= image.width <= 300 and 1 <= image.height <= 300):
                    raise SystemExit(f"Incompatible sprite {path}: expected RGBA PNG up to 300x300")
                if image.getchannel("A").getbbox() is None:
                    raise SystemExit(f"Empty sprite: {path}")
                if pack == "starcraft-local":
                    meta = manifest.get("frames", {}).get(name)
                    if not meta or (meta["width"], meta["height"]) != image.size:
                        raise SystemExit(f"Sprite/manifest mismatch: {path}")
                    x, y = meta["x"], meta["y"]
                else:
                    x, y = -16, -28
            destination = target / name
            if not destination.exists() or destination.read_bytes() != path.read_bytes():
                shutil.copyfile(path, destination)
                changed = True
            pattern = re.compile(r'(\{\s*"path": "bridge/' + re.escape(name)
                                 + r'", "x": )-?\d+(, "y": )-?\d+(\s*\})')
            contents, count = pattern.subn(lambda m: f"{m[1]}{x}{m[2]}{y}{m[3]}", contents)
            if count != 1:
                raise SystemExit(f"Missing or duplicate g2 metadata entry: {name}")
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
