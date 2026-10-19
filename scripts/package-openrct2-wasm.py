#!/usr/bin/env python3
"""Stage a private, versioned browser bundle from the patched native asset tree."""

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "upstream/openrct2"
STAGE = ROOT / "build/openrct2-stage/usr/local/share/openrct2"
PATCHES = ROOT / "openrct2-patches"
APP = ROOT / "browser"
JSZIP_SHA256 = "acc7e41455a80765b5fd9c7ee1b8078a6d160bbbca455aeae854de65c947d59e"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(path: Path) -> Path:
    if not path.is_file() or not path.stat().st_size:
        raise RuntimeError(f"Missing required WASM bundle input: {path}")
    return path


def add_zip(archive: zipfile.ZipFile, path: Path, name: str) -> None:
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, path.read_bytes(), compresslevel=6)


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: package-openrct2-wasm.py BUILD_DIR BUNDLE_DIR", file=sys.stderr)
        return 2
    build_dir, bundle = map(Path, sys.argv[1:])
    js = require(build_dir / "openrct2.js")
    wasm = require(build_dir / "openrct2.wasm")
    g2 = require(STAGE / "g2.dat")
    visual_source = __import__("os").environ.get("BRIDGE_SPRITE_SOURCE", "starcraft-local")
    visual_inventory = None
    if visual_source == "starcraft-local":
        subprocess.run(["python3", "scripts/verify-starcraft-visuals.py"], cwd=ROOT, check=True)
        visual_inventory = json.loads((ROOT / "run-data/generated-assets/starcraft/installed-visuals.json").read_text())
    native_g2 = require(ROOT / "build/openrct2/g2.dat")
    if sha256(g2) != sha256(native_g2):
        raise RuntimeError("Staged g2.dat differs from the native build; run scripts/install-openrct2-local.sh")
    require(STAGE / "language/en-GB.txt")
    for name in ("index.html", "index.js"):
        require(APP / name)

    patch_files = sorted(PATCHES.glob("[0-9][0-9][0-9][0-9]-*.patch"))
    patch_digest = hashlib.sha256()
    for patch in patch_files:
        patch_digest.update(patch.name.encode() + b"\0" + patch.read_bytes())
    upstream_commit = subprocess.check_output(
        ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True
    ).strip()
    expected = json.loads((ROOT / "dependencies.lock.json").read_text())["openrct2"]["commit"]
    if upstream_commit != expected:
        raise RuntimeError(f"OpenRCT2 checkout mismatch: {upstream_commit} != {expected}")
    cmake_cache = require(build_dir / "CMakeCache.txt").read_text()
    if "DISABLE_NETWORK:BOOL=ON" in cmake_cache:
        network_enabled = False
    elif "DISABLE_NETWORK:BOOL=OFF" in cmake_cache:
        network_enabled = True
    else:
        raise RuntimeError("Cannot determine WASM multiplayer configuration")
    script_engine = require(UPSTREAM / "src/openrct2/scripting/ScriptEngine.cpp").read_text()
    script_header = require(UPSTREAM / "src/openrct2/scripting/ScriptEngine.h").read_text()
    if ('JS_SetPropertyStr(ctx, bridge, "version", JS_NewInt32(ctx, 5))' not in script_engine
            or 'JS_SetPropertyStr(ctx, bridge, "assetVersion", JS_NewInt32(ctx, 4))' not in script_engine
            or 'kPluginApiVersion = 124' not in script_header):
        raise RuntimeError("Native bridge or plugin API versions do not match this bundle")

    bundle.mkdir(parents=True, exist_ok=True)
    executable_files = (js, wasm, *build_dir.glob("openrct2.worker*.js"), *build_dir.glob("openrct2*.data"))
    for source in executable_files:
        shutil.copy2(source, bundle / source.name)
    for name in ("index.html", "index.js"):
        shutil.copy2(APP / name, bundle / name)
    upstream_deps = UPSTREAM / "emscripten/deps.js"
    # The Emscripten JS library is linked into openrct2.js, not loaded by HTML.
    require(upstream_deps)
    jszip_dir = ROOT / "build/wasm-jszip"
    jszip = jszip_dir / "node_modules/jszip/dist/jszip.min.js"
    if not jszip.is_file():
        subprocess.run(
            ["npm", "install", "--prefix", str(jszip_dir), "--ignore-scripts", "--no-audit", "--no-fund", "--save-exact", "jszip@3.10.1"],
            check=True,
        )
    if sha256(jszip) != JSZIP_SHA256:
        raise RuntimeError("Downloaded JSZip 3.10.1 differs from the pinned browser dependency")
    shutil.copy2(require(jszip), bundle / "jszip.min.js")
    shutil.copy2(require(jszip_dir / "node_modules/jszip/LICENSE.markdown"), bundle / "jszip-LICENSE.txt")
    shutil.copy2(require(UPSTREAM / "licence.txt"), bundle / "openrct2-LICENSE.txt")
    if network_enabled:
        shutil.copy2(require(ROOT / "build/openrct2-wasm-deps/openssl/LICENSE.txt"), bundle / "openssl-LICENSE.txt")

    asset_zip = bundle / "assets.zip"
    with zipfile.ZipFile(asset_zip, "w", allowZip64=True) as archive:
        for path in sorted(STAGE.rglob("*")):
            if path.is_file():
                add_zip(archive, path, path.relative_to(STAGE).as_posix())
        add_zip(archive, require(ROOT / "openrct2-plugin/rts-bridge.js"), "plugin/rts-bridge.js")

    manifest = {
        "schema": 1,
        "openrct2_commit": upstream_commit,
        "patch_sha256": patch_digest.hexdigest(),
        "native_bridge_version": 5,
        "asset_version": 4,
        "plugin_api_version": 124,
        "network_enabled": network_enabled,
        "visual_source": visual_source,
        "visual_asset_sha256": visual_inventory["assets"] if visual_inventory else {},
        "plugin_sha256": sha256(require(ROOT / "openrct2-plugin/rts-bridge.js")),
        "g2_sha256": sha256(g2),
        "visual_registry_sha256": sha256(require(UPSTREAM / "src/openrct2/paint/BridgeVisualRegistry.h")),
        "starcraft_types_sha256": sha256(require(ROOT / "bridge-protocol/starcraft-types.json")),
        "starcraft_visuals_sha256": sha256(require(ROOT / "bridge-protocol/starcraft-visuals.json")),
        "artifacts": {name: sha256(bundle / name) for name in (
            *(source.name for source in executable_files), "index.html", "index.js",
            "assets.zip", "jszip.min.js", "jszip-LICENSE.txt", "openrct2-LICENSE.txt",
            *(("openssl-LICENSE.txt",) if network_enabled else ()))},
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Packaged {bundle} ({wasm.stat().st_size} WASM bytes, {asset_zip.stat().st_size} asset bytes)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
