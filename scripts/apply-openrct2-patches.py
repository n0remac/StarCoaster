#!/usr/bin/env python3
"""Verify the native bridge patch and upgrade existing screen-selection builds."""

from pathlib import Path
import os
import re
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


def ensure_starcraft_toolbar(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0005-starcraft-construction-toolbar.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected toolbar changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_barracks_animation(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0006-barracks-training-animation.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected native changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_barracks_light_only(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0007-barracks-light-only.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected native changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_actor_visual_registry(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0008-actor-visual-registry.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected actor renderer changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_building_animation_registry(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0009-building-animation-registry.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected building animation changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_firebat_visual_bank(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0010-firebat-visual-bank.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected Firebat renderer changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_medic_vulture_effects(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0011-medic-vulture-effects.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected actor renderer changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_generic_visual_registry(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0012-generic-visual-registry.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected actor renderer changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_generic_actor_validation(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0013-generic-actor-validation.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected actor validation changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_target_facing_attachments(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0014-target-facing-attachments.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected actor renderer changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_native_morph_visuals(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0015-native-morph-visuals.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected actor renderer changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_native_animation_timing(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0016-native-animation-timing.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected actor renderer changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_json_byte_vector_portability(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0017-json-byte-vector-portability.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected JSON parser changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_socket_immediate_connect(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0018-socket-immediate-connect.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected socket changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_network_future_include(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0019-network-future-include.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected network changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_bridge_clear_on_map_change(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0020-clear-bridge-on-map-change.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected map or bridge changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_authoritative_map_handoff(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0021-authoritative-map-handoff.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected map-loading changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


def ensure_performance_instrumentation(checkout: Path) -> str:
    patch = ROOT / "openrct2-patches/0022-performance-instrumentation.patch"
    if applies(checkout, patch, reverse=True):
        return "current"
    if not applies(checkout, patch):
        raise RuntimeError(f"Cannot apply {patch.name} in {checkout}: unexpected rendering changes")
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    return "applied"


if __name__ == "__main__":
    try:
        checkout = ROOT / "upstream/openrct2"
        overlays = [ROOT / "openrct2-patches/0006-barracks-training-animation.patch",
                    ROOT / "openrct2-patches/0007-barracks-light-only.patch",
                    ROOT / "openrct2-patches/0008-actor-visual-registry.patch",
                    ROOT / "openrct2-patches/0009-building-animation-registry.patch",
                    ROOT / "openrct2-patches/0010-firebat-visual-bank.patch",
                    ROOT / "openrct2-patches/0011-medic-vulture-effects.patch",
                    ROOT / "openrct2-patches/0012-generic-visual-registry.patch",
                    ROOT / "openrct2-patches/0013-generic-actor-validation.patch",
                    ROOT / "openrct2-patches/0014-target-facing-attachments.patch",
                    ROOT / "openrct2-patches/0015-native-morph-visuals.patch",
                    ROOT / "openrct2-patches/0016-native-animation-timing.patch",
                    ROOT / "openrct2-patches/0017-json-byte-vector-portability.patch",
                    ROOT / "openrct2-patches/0018-socket-immediate-connect.patch",
                    ROOT / "openrct2-patches/0019-network-future-include.patch",
                    ROOT / "openrct2-patches/0020-clear-bridge-on-map-change.patch",
                    ROOT / "openrct2-patches/0021-authoritative-map-handoff.patch",
                    ROOT / "openrct2-patches/0022-performance-instrumentation.patch"]
        # Reconciliation temporarily reverses and reapplies overlays. Keep
        # unchanged file mtimes so an ordinary rebuild does not recompile all
        # SpriteIds.h dependents merely because the check ran.
        patch_paths = [ROOT / "openrct2-patches/0001-native-bridge.patch",
                       ROOT / "openrct2-patches/0005-starcraft-construction-toolbar.patch", *overlays]
        touched = {checkout / name for patch in patch_paths for name in
                   re.findall(r"^diff --git a/\S+ b/(\S+)$", patch.read_text(), re.M)}
        original = {path: (path.read_bytes(), path.stat().st_atime_ns, path.stat().st_mtime_ns)
                    for path in touched if path.is_file()}
        reversed_overlays = []
        for overlay in reversed(overlays):
            if applies(checkout, overlay, reverse=True):
                subprocess.run(["git", "-C", str(checkout), "apply", "--reverse", str(overlay)], check=True)
                reversed_overlays.append(overlay)
        try:
            bridge_status = ensure_bridge(checkout)
        finally:
            for overlay in reversed(reversed_overlays):
                subprocess.run(["git", "-C", str(checkout), "apply", str(overlay)], check=True)
        print("OpenRCT2 native bridge patch " + bridge_status)
        print("StarCraft toolbar patch " + ensure_starcraft_toolbar(checkout))
        checks = [("Barracks training animation", ensure_barracks_animation),
                  ("Barracks light-only", ensure_barracks_light_only),
                  ("Actor visual registry", ensure_actor_visual_registry),
                  ("Building animation registry", ensure_building_animation_registry),
                  ("Firebat visual bank", ensure_firebat_visual_bank),
                  ("Medic, Vulture, and effects", ensure_medic_vulture_effects),
                  ("Generic visual registry", ensure_generic_visual_registry),
                  ("Generic actor validation", ensure_generic_actor_validation),
                  ("Target-facing attachments", ensure_target_facing_attachments),
                  ("Native morph visuals", ensure_native_morph_visuals),
                  ("Native animation timing", ensure_native_animation_timing),
                  ("JSON byte-vector portability", ensure_json_byte_vector_portability),
                  ("Socket immediate connect", ensure_socket_immediate_connect),
                  ("Network future include", ensure_network_future_include),
                  ("Bridge clear on map change", ensure_bridge_clear_on_map_change),
                  ("Authoritative map handoff", ensure_authoritative_map_handoff),
                  ("Performance instrumentation", ensure_performance_instrumentation)]
        for index, (label, ensure) in enumerate(checks):
            removed = []
            for overlay in reversed(overlays[index + 1:]):
                if applies(checkout, overlay, reverse=True):
                    subprocess.run(["git", "-C", str(checkout), "apply", "--reverse", str(overlay)], check=True)
                    removed.append(overlay)
            try:
                status = ensure(checkout)
            finally:
                for overlay in reversed(removed):
                    subprocess.run(["git", "-C", str(checkout), "apply", str(overlay)], check=True)
            print(label + " patch " + status)
        for path, (contents, atime, mtime) in original.items():
            if path.is_file() and path.read_bytes() == contents:
                os.utime(path, ns=(atime, mtime))
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
