#!/usr/bin/env python3
"""Extract the original command button frames from a locally licensed StarCraft install."""

import argparse
import importlib.util
import json
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parent.parent
ICON_FRAMES = {
    "terran_marine": 0,
    "terran_vulture": 2,
    "terran_goliath": 3,
    "terran_firebat": 32,
    "terran_medic": 34,
    "zerg_zergling": 37,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("starcraft_sprites", ROOT / "scripts/prepare-starcraft-sprites.py")
    sprites = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sprites)
    output = ROOT / "run-data/generated-assets/starcraft/command-icons"
    output.mkdir(parents=True, exist_ok=True)
    grp_path = output / "cmdicons.grp"
    wpe_path = output / "Badlands.wpe"
    archive = sprites.extract(args.game_dir, "unit/cmdbtns/cmdicons.grp", grp_path)
    sprites.extract(args.game_dir, "Tileset/Badlands.wpe", wpe_path)
    grp, wpe = grp_path.read_bytes(), wpe_path.read_bytes()
    if struct.unpack_from("<H", grp)[0] < max(ICON_FRAMES.values()) + 1:
        raise SystemExit("StarCraft command icon bank is incomplete")
    manifest = {"resource": "unit/cmdbtns/cmdicons.grp", "archive": archive, "icons": {}}
    palette = sprites.openrct2_palette()
    for kind, frame in ICON_FRAMES.items():
        name = kind + ".png"
        image = sprites.quantize(sprites.decode_grp(grp, wpe, frame), palette)
        image.save(output / name)
        manifest["icons"][kind] = {"file": name, "source_frame": frame,
                                   "width": image.width, "height": image.height}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared {len(ICON_FRAMES)} original command icons from {archive}")


if __name__ == "__main__":
    main()
