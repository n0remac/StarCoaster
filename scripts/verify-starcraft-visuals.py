#!/usr/bin/env python3
"""Record or verify the installed private StarCraft art used by native and WASM."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "build/openrct2-stage/usr/local/share/openrct2"
RECORD = ROOT / "run-data/generated-assets/starcraft/installed-visuals.json"


def digest(path):
    if not path.is_file() or not path.stat().st_size:
        raise RuntimeError(f"Missing StarCraft visual asset: {path}. Run scripts/project.sh start with licensed StarCraft data.")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory():
    catalog = json.loads((ROOT / "bridge-protocol/starcraft-types.json").read_text())
    visuals = json.loads((ROOT / "bridge-protocol/starcraft-visuals.json").read_text())
    assets = {visuals["units"][unit["visual"]]["asset"] for unit in catalog["units"]}
    assets |= {effect["asset"] for effect in visuals["effects"].values()}
    manifests = {f"sprites/{name}/manifest.json": digest(ROOT / "run-data/generated-assets/starcraft" / name / "manifest.json")
                 for name in sorted(assets)}
    manifests["sprites/command-icons/manifest.json"] = digest(ROOT / "run-data/generated-assets/starcraft/command-icons/manifest.json")
    buildings = {path.relative_to(STAGE).as_posix(): digest(path)
                 for path in sorted((STAGE / "object/starcoaster/scenery_large").glob("*.parkobj"))}
    expected = {item["object_id"] for item in catalog["buildings"]}
    if not expected.issubset({path.stem for path in (STAGE / "object/starcoaster/scenery_large").glob("*.parkobj")}):
        raise RuntimeError("Missing StarCraft building objects; run scripts/install-starcraft-construction-object.py --all")
    return {"source": "starcraft-local", "g2_sha256": digest(STAGE / "g2.dat"),
            "visual_registry_sha256": digest(ROOT / "upstream/openrct2/src/openrct2/paint/BridgeVisualRegistry.h"),
            "starcraft_visuals_sha256": digest(ROOT / "bridge-protocol/starcraft-visuals.json"),
            "assets": {**manifests, **buildings}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    current = inventory()
    if args.record:
        RECORD.parent.mkdir(parents=True, exist_ok=True)
        RECORD.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        print(f"Recorded StarCraft visuals: {RECORD}")
    elif not RECORD.is_file() or json.loads(RECORD.read_text()) != current:
        raise RuntimeError("Installed StarCraft visuals are missing or stale. Rebuild with scripts/project.sh start and licensed STARCRAFT_DATA_DIR.")
    else:
        print("Installed StarCraft visuals verified")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        parser.exit(1, f"StarCraft visuals: {exc}\n")
