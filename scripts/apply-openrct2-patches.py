#!/usr/bin/env python3
"""Verify the native bridge patch and upgrade existing screen-selection builds."""

from pathlib import Path
import runpy
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
applies = runpy.run_path(str(ROOT / "scripts/apply-bwapi-patches.py"))["applies"]


def ensure_bridge(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0001-native-bridge.patch"
    # The sprite installer adjusts offsets for the selected local asset pack.
    # Verify all native code independently of that generated metadata.
    chunks = patch.read_text().split("diff --git ")
    native = "".join("diff --git " + chunk for chunk in chunks[1:]
                     if not chunk.startswith("a/resources/g2/sprites.json "))
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        native_patch = temporary / patch.name
        native_patch.write_text(native)
        if applies(checkout, native_patch, reverse=True):
            return "current"
        # Reconcile a copy first so a conflicting local edit leaves every
        # source file untouched, including when more than one upgrade is due.
        candidate = temporary / "candidate"
        candidate.mkdir()
        names = [chunk.split(" b/", 1)[1].splitlines()[0] for chunk in chunks[1:]]
        for name in names:
            destination = candidate / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((checkout / name).read_bytes())
        if applies(candidate, patch):
            subprocess.run(["git", "-C", str(candidate), "apply", str(patch)], check=True)
            result = "applied"
        else:
            for name in ("0003-terrain-rendering-upgrade.patch", "0002-screen-selection-upgrade.patch",
                         "0004-shared-viewport-input-upgrade.patch"):
                upgrade = ROOT / "openrct2-patches" / name
                if applies(candidate, upgrade):
                    subprocess.run(["git", "-C", str(candidate), "apply", str(upgrade)], check=True)
            result = "upgraded"
        if not applies(candidate, native_patch, reverse=True):
            raise RuntimeError(f"Cannot update native bridge in {checkout}: unexpected source changes; "
                               "preserve local edits and reconcile with the pinned sources.")
        for name in names:
            contents = (candidate / name).read_bytes()
            if contents != (checkout / name).read_bytes():
                (checkout / name).write_bytes(contents)
    return result


if __name__ == "__main__":
    try:
        print("OpenRCT2 native bridge patch " + ensure_bridge(ROOT / "upstream/openrct2"))
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
