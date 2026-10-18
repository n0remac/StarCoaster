#!/usr/bin/env python3
"""Validate browser artifact hashes and compatibility without game files."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    bundle = Path(sys.argv[1]) if len(sys.argv) == 2 else Path("build/wasm-client")
    manifest = json.loads((bundle / "manifest.json").read_text())
    expected = (manifest.get("schema"), manifest.get("native_bridge_version"),
                manifest.get("asset_version"), manifest.get("plugin_api_version"))
    if expected != (1, 5, 4, 124):
        raise ValueError(f"Incompatible bundle versions: {expected}")
    lock = json.loads((ROOT / "dependencies.lock.json").read_text())
    if manifest.get("openrct2_commit") != lock["openrct2"]["commit"]:
        raise ValueError("OpenRCT2 revision differs from the native host")
    patches = sorted((ROOT / "openrct2-patches").glob("[0-9][0-9][0-9][0-9]-*.patch"))
    patch_digest = hashlib.sha256()
    for patch in patches:
        patch_digest.update(patch.name.encode() + b"\0" + patch.read_bytes())
    if manifest.get("patch_sha256") != patch_digest.hexdigest():
        raise ValueError("StarCoaster patch set differs from the native host")
    local_files = {
        "plugin_sha256": ROOT / "openrct2-plugin/rts-bridge.js",
        "starcraft_types_sha256": ROOT / "bridge-protocol/starcraft-types.json",
        "starcraft_visuals_sha256": ROOT / "bridge-protocol/starcraft-visuals.json",
        "g2_sha256": ROOT / "build/openrct2-stage/usr/local/share/openrct2/g2.dat",
        "visual_registry_sha256": ROOT / "upstream/openrct2/src/openrct2/paint/BridgeVisualRegistry.h",
    }
    for key, path in local_files.items():
        if not path.is_file() or manifest.get(key) != digest(path):
            raise ValueError(f"{key} differs from the native host: {path}")
    for name, expected_digest in manifest["artifacts"].items():
        path = bundle / name
        if not path.is_file() or digest(path) != expected_digest:
            raise ValueError(f"Missing or mismatched browser artifact: {path}")
    with zipfile.ZipFile(bundle / "assets.zip") as assets:
        if hashlib.sha256(assets.read("g2.dat")).hexdigest() != manifest["g2_sha256"]:
            raise ValueError("Bundled g2.dat differs from the manifest")
    if not (bundle / "index.html").is_file() or not (bundle / "index.js").is_file():
        raise ValueError("Browser launcher is missing")
    print(f"WASM bundle valid: {bundle}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"WASM bundle invalid: {error}", file=sys.stderr)
        sys.exit(1)
