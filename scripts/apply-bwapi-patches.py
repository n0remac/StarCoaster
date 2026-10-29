#!/usr/bin/env python3
"""Apply current engine patches, upgrading known older patch versions."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def applies(checkout: Path, patch: Path, reverse: bool = False) -> bool:
    command = ["git", "-C", str(checkout), "apply", "--check"]
    if reverse:
        command.append("--reverse")
    return subprocess.run(command + [str(patch)], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def ensure_patch(checkout: Path, patch: Path, upgrade: Path | None = None) -> str:
    if applies(checkout, patch, reverse=True):
        return "current"
    if applies(checkout, patch):
        selected, result = patch, "applied"
    elif upgrade is not None and applies(checkout, upgrade):
        selected, result = upgrade, "upgraded"
    else:
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected source changes; "
                           "preserve local edits and reconcile this checkout with the pinned sources.")
    subprocess.run(["git", "-C", str(checkout), "apply", str(selected)], check=True)
    if not applies(checkout, patch, reverse=True):
        raise RuntimeError(f"Current patch verification failed: {patch.name} in {checkout}")
    return result


def main() -> int:
    patches = ROOT / "openbw-bwapi-module"
    for name, patch, upgrade in (
        ("bwapi", "0001-player-slot.patch", None),
        ("openbw", "0002-native-navigation-openbw.patch", "0004-native-navigation-upgrade-openbw.patch"),
        ("openbw", "0005-editor-building-fog-openbw.patch", None),
        ("openbw", "0006-native-production-egress-openbw.patch", "0008-native-production-egress-upgrade-openbw.patch"),
        ("openbw", "0007-scenario-spawning-pool-openbw.patch", None),
        ("openbw", "0008-native-region-capacity-openbw.patch", None),
        ("bwapi", "0003-native-navigation-bwapi.patch", None),
    ):
        if (patch == "0005-editor-building-fog-openbw.patch" and
                applies(ROOT / "upstream/openbw", patches / "0007-scenario-spawning-pool-openbw.patch", reverse=True)):
            print(f"{name}: {patch} current (extended by 0007)")
            continue
        result = ensure_patch(ROOT / "upstream" / name, patches / patch,
                              patches / upgrade if upgrade else None)
        print(f"{name}: {patch} {result}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
