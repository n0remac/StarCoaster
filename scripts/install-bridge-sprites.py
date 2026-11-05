#!/usr/bin/env python3
"""Validate and stage one local sprite pack into the ignored OpenRCT2 checkout."""

import json
from pathlib import Path
import re
import runpy
import shutil
import sys

from PIL import Image


MARINE_DIRECTIONS = ("east", "southeast", "south", "southwest", "west", "northwest", "north", "northeast")
MARINE_NAMES = [f"{state}{pose}_{direction}.png"
                for state, count in (("idle", 1), ("walk", 2), ("attack", 3))
                for pose in range(count) for direction in MARINE_DIRECTIONS]
MARINE_NAMES += [f"death{pose}.png" for pose in range(8)]
FIREBAT_DIRECTIONS = ("east", "southeast", "south", "southwest", "west", "northwest", "north", "northeast")
FIREBAT_NAMES = [f"{state}{pose}_{direction}.png"
                 for state, count in (("idle", 1), ("walk", 2), ("attack", 3))
                 for pose in range(count) for direction in FIREBAT_DIRECTIONS]
FIREBAT_NAMES += [f"death{pose}.png" for pose in range(8)]
MEDIC_NAMES = [f"{state}{pose}_{direction}.png"
               for state, count in (("idle", 1), ("walk", 2), ("heal", 3))
               for pose in range(count) for direction in MARINE_DIRECTIONS]
MEDIC_NAMES += [f"death{pose}.png" for pose in range(8)]
VULTURE_NAMES = [f"idle0_{direction}.png" for direction in MARINE_DIRECTIONS]
VULTURE_NAMES += [f"death{pose}.png" for pose in range(8)]
FLAME_NAMES = [f"burst{pose}_{direction}.png" for pose in range(7)
               for direction in MARINE_DIRECTIONS]
ROOT = Path(__file__).resolve().parents[1]
LEGACY_ASSETS = {"marine", "firebat", "medic", "vulture", "zergling"}


def stable_sprite_entries(entries: list[dict]) -> list[dict]:
    """Keep established IDs identical in clean and incrementally built checkouts.

    The compatibility ledger contains paths only, never licensed graphics.
    Append newly established paths to it; never reorder existing entries.
    """
    order = json.loads((ROOT / "bridge-protocol/starcraft-sprite-order.json").read_text())
    ranks = {path: index for index, path in enumerate(order)}
    if len(ranks) != len(order) or len({entry["path"] for entry in entries}) != len(entries):
        raise ValueError("Duplicate G2 sprite path")
    return sorted(entries, key=lambda entry: (ranks.get(entry["path"], len(order)), entry["path"]))


def registered_units() -> list[tuple[str, dict]]:
    catalog = json.loads((ROOT / "bridge-protocol/starcraft-types.json").read_text())
    visuals = json.loads((ROOT / "bridge-protocol/starcraft-visuals.json").read_text())["units"]
    return sorted(((unit["id"], visuals[unit["visual"]]) for unit in catalog["units"]),
                  key=lambda item: item[1]["g2_order"])


def ensure_registered_banks(contents: str, source: Path, pack: str) -> str:
    """Append new visual banks in catalog order without renumbering older G2 IDs."""
    entries = json.loads(contents)
    existing = {entry["path"] for entry in entries}
    additions = []
    for kind, profile in registered_units():
        asset = profile["asset"]
        if asset in LEGACY_ASSETS:
            continue
        local = source.parent / asset
        manifest_path = local / "manifest.json"
        if not manifest_path.is_file() and pack == "starcraft-local":
            raise SystemExit(f"Missing {asset} manifest: {manifest_path}. "
                             f"Run scripts/prepare-starcraft-sprites.py --unit {asset} first.")
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("kind") != kind:
                raise SystemExit(f"Invalid {asset} sprite manifest")
            names = list(manifest["frames"])
        else:
            # Explicit placeholder mode can build without licensed artwork.
            names = []
            for layer, prefix in [(profile, ""), *[(item, item["name"] + "_")
                                                for item in profile.get("attachments", [])]]:
                for state, animation in layer["animations"].items():
                    if "fallback" in animation:
                        continue
                    if "banks" in animation:
                        names.extend(f"{prefix}{state}{pose}_{direction}.png"
                                     for direction in MARINE_DIRECTIONS for pose in range(len(animation["banks"])))
                    else:
                        names.extend(f"{prefix}{state}{pose}.png" for pose in range(len(animation["frames"])))
        for name in names:
            path = f"bridge/{asset}/{name}"
            if path not in existing:
                additions.append({"path": path, "x": -profile.get("canvas", [64])[0] // 2,
                                  "y": -profile.get("canvas", [64, 64])[1] // 2})
                existing.add(path)
        for level in range(11):
            path = f"bridge/health/{asset}{level}.png"
            if path not in existing:
                x, y = profile["health_offset"]
                additions.append({"path": path, "x": x, "y": y})
                existing.add(path)
    if not additions:
        return contents
    rendered = ",\n".join(f'    {{\n        "path": "{item["path"]}", "x": {item["x"]}, "y": {item["y"]}\n    }}'
                           for item in additions)
    return contents.rstrip()[:-1].rstrip() + ",\n" + rendered + "\n]\n"


def ensure_zergling_extra_banks(contents: str, source: Path, pack: str) -> str:
    """Append newly declared Zergling poses after every pre-existing G2 ID."""
    entries = json.loads(contents)
    existing = {entry["path"] for entry in entries}
    profile = dict(registered_units())["zerg_zergling"]
    manifest = json.loads((source / "manifest.json").read_text()) if pack == "starcraft-local" else None
    names = list(manifest["frames"]) if manifest else [
        (f"{state}{pose}_{direction}.png" if state != "idle" else f"idle_{direction}.png")
        for state, animation in profile["animations"].items() if "banks" in animation
        for pose in range(len(animation["banks"])) for direction in MARINE_DIRECTIONS
    ] + [f"death{pose}.png" for pose in range(len(profile["animations"]["death"]["frames"]))]
    additions = []
    for name in names:
        path = f"bridge/{name}"
        if path not in existing:
            additions.append({"path": path, "x": -16, "y": -16})
            existing.add(path)
    if not additions:
        return contents
    rendered = ",\n".join(f'    {{"path": "{item["path"]}", "x": {item["x"]}, "y": {item["y"]}}}'
                           for item in additions)
    return contents.rstrip()[:-1].rstrip() + ",\n" + rendered + "\n]\n"


def stage_registered_banks(source: Path, pack: str, upstream: Path, contents: str,
                           colours: set, prepared: list) -> str:
    from PIL import ImageDraw
    for kind, profile in registered_units():
        asset = profile["asset"]
        if asset in LEGACY_ASSETS:
            continue
        local = source.parent / asset
        manifest_path = local / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if pack == "starcraft-local" and manifest_path.is_file() else None
        if pack == "starcraft-local" and (not manifest or manifest.get("kind") != kind):
            raise SystemExit(f"Missing or invalid {asset} manifest: {manifest_path}")
        if manifest is None:
            names = [entry["path"].split(f"bridge/{asset}/", 1)[1]
                     for entry in json.loads(contents) if entry["path"].startswith(f"bridge/{asset}/")]
            local = ROOT / f"run-data/generated-assets/placeholder/{asset}"
            local.mkdir(parents=True, exist_ok=True)
            colour = min(colours, key=lambda rgb: sum((rgb[index] - wanted) ** 2
                           for index, wanted in enumerate((117, 140, 154))))
            for name in names:
                image = Image.new("RGBA", (24, 30))
                draw = ImageDraw.Draw(image)
                draw.rectangle((5, 2, 18, 27), fill=colour + (255,))
                image.save(local / name)
            frame_data = {name: {"x": -12, "y": -25, "width": 24, "height": 30} for name in names}
        else:
            frame_data = manifest["frames"]
        for name, meta in frame_data.items():
            path = local / name
            if not path.is_file():
                raise SystemExit(f"Missing {asset} sprite: {path}")
            with Image.open(path) as image:
                image.load()
                if image.mode != "RGBA" or image.size != (meta["width"], meta["height"]) or any(
                        alpha not in (0, 255) or (alpha and (red, green, blue) not in colours)
                        for red, green, blue, alpha in image.getdata()):
                    raise SystemExit(f"Incompatible {asset} sprite: {path}")
            g2path = f"bridge/{asset}/{name}"
            pattern = re.compile(r'(\{\s*"path": "' + re.escape(g2path)
                                 + r'",\s*"x": )-?\d+(,\s*"y": )-?\d+(\s*\})')
            contents, count = pattern.subn(lambda match: f'{match[1]}{meta["x"]}{match[2]}{meta["y"]}{match[3]}', contents)
            if count != 1:
                raise SystemExit(f"Missing or duplicate G2 entry: {g2path}")
            prepared.append((path, f"{asset}/{name}"))
    return contents


def ensure_firebat_g2_entries(contents: str) -> str:
    """Append the independent visual bank once, retaining existing sprite IDs."""
    first = '"path": "bridge/firebat/idle0_east.png"'
    if first in contents:
        return contents
    entries = [(f"firebat/{name}", -16, -16) for name in FIREBAT_NAMES]
    entries += [(f"health/firebat{level}.png", -10, -28) for level in range(11)]
    if len(entries) != 67 or not contents.rstrip().endswith("]"):
        raise SystemExit("Invalid Firebat G2 sprite bank")
    rendered = ",\n".join(
        f'    {{\n        "path": "bridge/{name}", "x": {x}, "y": {y}\n    }}'
        for name, x, y in entries)
    return contents.rstrip()[:-1].rstrip() + ",\n" + rendered + "\n]\n"


def ensure_next_g2_entries(contents: str) -> str:
    """Append Medic, Vulture, and flame banks after the existing Firebat IDs."""
    if '"path": "bridge/medic/idle0_east.png"' in contents:
        return contents
    entries = [(f"medic/{name}", -32, -32) for name in MEDIC_NAMES]
    entries += [(f"health/medic{level}.png", -10, -42) for level in range(11)]
    entries += [(f"vulture/{name}", -50, -50) for name in VULTURE_NAMES]
    entries += [(f"health/vulture{level}.png", -10, -28) for level in range(11)]
    entries += [(f"flame/{name}", -112, -112) for name in FLAME_NAMES]
    if len(entries) != 150 or not contents.rstrip().endswith("]"):
        raise SystemExit("Invalid next StarCraft G2 banks")
    rendered = ",\n".join(
        f'    {{\n        "path": "bridge/{name}", "x": {x}, "y": {y}\n    }}'
        for name, x, y in entries)
    return contents.rstrip()[:-1].rstrip() + ",\n" + rendered + "\n]\n"


def placeholder_next(destination: Path, upstream: Path, kind: str, names: list[str]) -> None:
    """Use local CC0 placeholders when the licensed art is unavailable."""
    from PIL import ImageDraw
    marine = destination.parent / "marine"
    placeholder_marine(marine, upstream)
    destination.mkdir(parents=True, exist_ok=True)
    for name in names:
        target = destination / name
        if kind == "flame":
            image = Image.new("RGBA", (32, 32))
            colour = min(standard_colours(upstream), key=lambda rgb:
                         sum((rgb[index] - wanted) ** 2
                             for index, wanted in enumerate((235, 122, 35))))
            draw = ImageDraw.Draw(image)
            pose = int(name[5])
            draw.ellipse((12, 12 - pose // 2, 19 + pose // 2, 19 + pose // 2), fill=colour + (255,))
            image.crop(image.getbbox()).save(target)
        else:
            source_name = name.replace("heal", "attack") if kind == "medic" else name
            shutil.copyfile(marine / source_name, target)


def stage_next_bank(source: Path, pack: str, upstream: Path, contents: str,
                    colours: set, prepared: list, kind: str, names: list[str],
                    manifest_kind: str) -> str:
    local = source.parent / kind
    if pack == "starcraft-local" and not (local / "manifest.json").is_file():
        raise SystemExit(f"Missing {kind} manifest: {local / 'manifest.json'}. "
                         f"Run scripts/prepare-starcraft-sprites.py --unit {kind} first.")
    if pack != "starcraft-local":
        local = Path(__file__).resolve().parent.parent / f"run-data/generated-assets/placeholder/{kind}"
        placeholder_next(local, upstream, kind, names)
    manifest_path = local / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() and pack == "starcraft-local" else None
    if manifest and (manifest.get("kind") != manifest_kind
                     or len(manifest.get("frames", {})) != len(names)):
        raise SystemExit(f"Invalid independent {kind} visual bank")
    for name in names:
        path = local / name
        if not path.is_file():
            raise SystemExit(f"Missing {kind} frame: {path}")
        with Image.open(path) as image:
            image.load()
            if image.mode != "RGBA" or not (1 <= image.width <= 300 and 1 <= image.height <= 300):
                raise SystemExit(f"Incompatible {kind} sprite: {path}")
            if any(alpha not in (0, 255) or (alpha and (red, green, blue) not in colours)
                   for red, green, blue, alpha in image.getdata()):
                raise SystemExit(f"Incompatible {kind} palette or alpha: {path}")
        meta = manifest["frames"].get(name) if manifest else None
        if manifest and (not meta or (meta["width"], meta["height"]) != image.size):
            raise SystemExit(f"{kind} sprite/manifest mismatch: {path}")
        x, y = (meta["x"], meta["y"]) if meta else (-image.width // 2, -image.height)
        pattern = re.compile(r'(\{\s*"path": "bridge/' + re.escape(kind + "/" + name)
                             + r'", "x": )-?\d+(, "y": )-?\d+(\s*\})')
        contents, count = pattern.subn(lambda match: f"{match[1]}{x}{match[2]}{y}{match[3]}", contents)
        if count != 1:
            raise SystemExit(f"Missing or duplicate {kind} g2 entry: {name}")
        prepared.append((path, kind + "/" + name))
    return contents


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


def stage_zergling(source: Path, pack: str, manifest: dict, contents: str,
                    colours: set, prepared: list) -> str:
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
                    x, y = meta["x"], meta["y"]
                else:
                    x, y = -16, -28
            pattern = re.compile(r'(\{\s*"path": "bridge/' + re.escape(name)
                                 + r'", "x": )-?\d+(, "y": )-?\d+(\s*\})')
            contents, count = pattern.subn(lambda m: f"{m[1]}{x}{m[2]}{y}{m[3]}", contents)
            if count != 1:
                raise SystemExit(f"Missing or duplicate g2 metadata entry: {name}")
            prepared.append((path, name))
    legacy = {f"{motion}_{direction}.png" for motion in motions
              for direction in ("east", "south", "west", "north", *diagonals)}
    if pack == "starcraft-local":
        extra = [(name, source / name, meta) for name, meta in manifest["frames"].items()
                 if name not in legacy]
    else:
        placeholder = ROOT / "run-data/generated-assets/placeholder/zergling"
        placeholder.mkdir(parents=True, exist_ok=True)
        names = [entry["path"].removeprefix("bridge/") for entry in json.loads(contents)
                 if entry["path"].startswith("bridge/attack") or
                 re.fullmatch(r"bridge/death\d+\.png", entry["path"])]
        extra = []
        for name in names:
            destination = placeholder / name
            shutil.copyfile(source / "idle_east.png", destination)
            extra.append((name, destination, {"x": -16, "y": -28}))
    for name, path, meta in extra:
        with Image.open(path) as image:
            image.load()
            if image.mode != "RGBA" or not (1 <= image.width <= 300 and 1 <= image.height <= 300) \
                    or (pack == "starcraft-local" and (image.width, image.height) !=
                        (meta["width"], meta["height"])) \
                    or any(alpha not in (0, 255) or (alpha and (red, green, blue) not in colours)
                           for red, green, blue, alpha in image.getdata()):
                raise SystemExit(f"Incompatible Zergling frame: {path}")
        pattern = re.compile(r'(\{\s*"path": "bridge/' + re.escape(name)
                             + r'",\s*"x": )-?\d+(,\s*"y": )-?\d+(\s*\})')
        contents, count = pattern.subn(lambda match: f'{match[1]}{meta["x"]}{match[2]}{meta["y"]}{match[3]}', contents)
        if count != 1:
            raise SystemExit(f"Missing or duplicate Zergling G2 entry: {name}")
        prepared.append((path, name))
    return contents


def stage_marine(source: Path, pack: str, upstream: Path, contents: str,
                 colours: set, prepared: list) -> str:
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
    return contents


def stage_firebat(source: Path, pack: str, upstream: Path, contents: str,
                  colours: set, prepared: list) -> str:
    local = source.parent / "firebat"
    if pack == "starcraft-local" and not (local / "manifest.json").is_file():
        raise SystemExit(f"Missing Firebat manifest: {local / 'manifest.json'}. "
                         "Run scripts/prepare-starcraft-sprites.py --unit firebat first.")
    if pack != "starcraft-local":
        local = Path(__file__).resolve().parent.parent / "run-data/generated-assets/placeholder/firebat"
        placeholder_marine(local, upstream)
    manifest_path = local / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else None
    if manifest and (manifest.get("kind") != "terran_firebat"
                     or len(manifest.get("frames", {})) != len(FIREBAT_NAMES)
                     or set(manifest.get("registry", {}).get("terran_firebat", {}))
                     != {"idle", "walk", "attack", "death"}):
        raise SystemExit("Firebat manifest must contain its independent visual bank")
    for name in FIREBAT_NAMES:
        path = local / name
        if not path.is_file():
            raise SystemExit(f"Missing Firebat frame: {path}")
        with Image.open(path) as image:
            image.load()
            if image.mode != "RGBA" or not (1 <= image.width <= 300 and 1 <= image.height <= 300):
                raise SystemExit(f"Incompatible Firebat sprite: {path}")
            if any(alpha not in (0, 255) or (alpha and (red, green, blue) not in colours)
                   for red, green, blue, alpha in image.getdata()):
                raise SystemExit(f"Incompatible Firebat palette or alpha: {path}")
        meta = manifest["frames"].get(name) if manifest else None
        if manifest and (not meta or (meta["width"], meta["height"]) != image.size):
            raise SystemExit(f"Firebat sprite/manifest mismatch: {path}")
        x, y = (meta["x"], meta["y"]) if meta else (-image.width // 2, -image.height)
        pattern = re.compile(r'(\{\s*"path": "bridge/firebat/' + re.escape(name)
                             + r'", "x": )-?\d+(, "y": )-?\d+(\s*\})')
        contents, count = pattern.subn(lambda m: f"{m[1]}{x}{m[2]}{y}{m[3]}", contents)
        if count != 1:
            raise SystemExit(f"Missing or duplicate Firebat g2 entry: {name}")
        prepared.append((path, "firebat/" + name))
    return contents


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("pack", choices=("starcraft-local", "alien-scout"))
    parser.add_argument("--only-unit", choices=[kind for kind, _ in registered_units()] + ["firebat_flame"])
    args = parser.parse_args()
    only_unit = args.only_unit
    source, upstream, pack = args.source, args.upstream, args.pack
    if only_unit in (None, "zerg_zergling") and not source.is_dir():
        raise SystemExit(f"Missing {pack} sprite pack: {source}. Run scripts/prepare-starcraft-sprites.py first.")
    manifest_path = source / "manifest.json"
    if pack == "starcraft-local" and only_unit in (None, "zerg_zergling") and not manifest_path.is_file():
        raise SystemExit(f"Missing StarCraft sprite manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    if pack == "starcraft-local" and only_unit in (None, "zerg_zergling"):
        registry = (manifest.get("registry", {}).get("zerg_zergling")
                    or manifest.get("registry", {}).get("alien_scout", {}))
        if len(registry.get("walk", {}).get("frames", {})) != 8 \
           or len(registry.get("attack", {}).get("frames", {})) != 8 \
           or len(registry.get("death", {}).get("frames", [])) != 7:
            raise SystemExit("StarCraft Zergling manifest has invalid animation states")
    sprite_list = upstream / "resources/g2/sprites.json"
    contents = ensure_zergling_extra_banks(ensure_registered_banks(
        ensure_next_g2_entries(ensure_firebat_g2_entries(sprite_list.read_text())), source, pack), source, pack)
    enum_text = (upstream / "src/openrct2/SpriteIds.h").read_text()
    g2_base_match = re.search(r"SPR_G2_BEGIN\s*=\s*(\d+)", enum_text)
    if not g2_base_match:
        raise SystemExit("Pinned OpenRCT2 G2 sprite base is missing")
    g2_base = int(g2_base_match.group(1))
    if len(re.findall(r"^\s*SPR_BRIDGE_SCOUT_(?:IDLE|WALK[0-9]+)_", enum_text, re.MULTILINE)) != 88:
        raise SystemExit("OpenRCT2 sprite ID range must contain exactly 88 bridge images")
    if len(re.findall(r"^\s*SPR_BRIDGE_MARINE_", enum_text, re.MULTILINE)) != 56:
        raise SystemExit("OpenRCT2 sprite ID range must contain exactly 56 Marine images")
    if len(re.findall(r"^\s*SPR_BRIDGE_SCOUT_DEATH[0-5]_", enum_text, re.MULTILINE)) != 48:
        raise SystemExit("OpenRCT2 sprite ID range must contain exactly 48 scout death images")
    if len(re.findall(r"^\s*SPR_BRIDGE_HEALTH_", enum_text, re.MULTILINE)) != 55:
        raise SystemExit("OpenRCT2 sprite ID range must contain exactly 55 health bar images")
    if len(re.findall(r"^\s*SPR_BRIDGE_FIREBAT_", enum_text, re.MULTILINE)) != 56:
        raise SystemExit("OpenRCT2 sprite ID range must contain exactly 56 Firebat images")
    for prefix, expected in (("MEDIC", 56), ("VULTURE", 16), ("FLAME", 56)):
        if len(re.findall(r"^\s*SPR_BRIDGE_" + prefix + r"_", enum_text, re.MULTILINE)) != expected:
            raise SystemExit(f"OpenRCT2 sprite ID range must contain exactly {expected} {prefix} images")
    colours = standard_colours(upstream)
    prepared = []
    if only_unit in (None, "zerg_zergling"):
        contents = stage_zergling(source, pack, manifest, contents, colours, prepared)
    if only_unit in (None, "terran_marine"):
        contents = stage_marine(source, pack, upstream, contents, colours, prepared)
    if only_unit in (None, "terran_firebat"):
        contents = stage_firebat(source, pack, upstream, contents, colours, prepared)
    for requested, kind, names, manifest_kind in (
            ("terran_medic", "medic", MEDIC_NAMES, "terran_medic"),
            ("terran_vulture", "vulture", VULTURE_NAMES, "terran_vulture"),
            ("firebat_flame", "flame", FLAME_NAMES, "firebat_flame")):
        if only_unit in (None, requested):
            contents = stage_next_bank(source, pack, upstream, contents, colours, prepared,
                                       kind, names, manifest_kind)
    if only_unit is None or only_unit not in {"zerg_zergling", "terran_marine", "terran_firebat",
                                                "terran_medic", "terran_vulture", "firebat_flame"}:
        contents = stage_registered_banks(source, pack, upstream, contents, colours, prepared)
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
    for _, profile in registered_units():
        faction = profile["asset"]
        wanted = (195, 90, 225) if faction == "zergling" else (70, 220, 100)
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
            x, y = profile["health_offset"]
            contents, count = pattern.subn(lambda m: f"{m[1]}{x}{m[2]}{y}{m[3]}", contents)
            if count != 1:
                raise SystemExit(f"Missing or duplicate health g2 entry: {name}")
            prepared.append((path, "health/" + name))
    # Command icons are original GRP frames prepared from the user's local
    # installation. Append them after all actor images to keep existing IDs.
    icons_dir = ROOT / "run-data/generated-assets/starcraft/command-icons"
    icon_manifest = icons_dir / "manifest.json"
    if pack == "starcraft-local" and only_unit is None and not icon_manifest.is_file():
        raise SystemExit("Missing original command icons; run scripts/prepare-starcraft-command-icons.py")
    icon_frames = json.loads(icon_manifest.read_text())["icons"] if icon_manifest.is_file() and only_unit is None else {}
    entries = json.loads(contents)
    icon_ids = {"empty": g2_base}
    for kind, meta in sorted(icon_frames.items()):
        path = icons_dir / meta["file"]
        with Image.open(path) as icon:
            icon.load()
            if icon.mode != "RGBA" or icon.size != (meta["width"], meta["height"]) \
                    or any(alpha not in (0, 255) or (alpha and (red, green, blue) not in colours)
                           for red, green, blue, alpha in icon.getdata()):
                raise SystemExit(f"Incompatible command icon: {path}")
        key = "bridge/command/" + meta["file"]
        matches = [index for index, entry in enumerate(entries) if entry["path"] == key]
        if len(matches) > 1:
            raise SystemExit(f"Duplicate command icon G2 path: {key}")
        if matches:
            index = matches[0]
        else:
            index = len(entries)
            entries.append({"path": key, "x": 0, "y": 0})
        icon_ids[kind] = g2_base + index
        prepared.append((path, "command/" + meta["file"]))
    if icon_frames:
        # Preserve the existing hand-formatted G2 file and append only new IDs.
        for entry in entries[len(json.loads(contents)):]:
            contents = contents.rstrip()[:-1].rstrip()
            contents += ("," if not contents.endswith("[") else "") + "\n    " + json.dumps(entry) + "\n]\n"
    # A first build must reproduce the historical append-only indices,
    # including animation frames introduced after the command icons.
    ordered = stable_sprite_entries(entries)
    if ordered != entries:
        contents = "[\n" + ",\n".join("    " + json.dumps(entry) for entry in ordered) + "\n]\n"
    if icon_frames:
        indices = {entry["path"]: index for index, entry in enumerate(ordered)}
        icon_ids = {"empty": g2_base, **{
            kind: g2_base + indices["bridge/command/" + meta["file"]]
            for kind, meta in icon_frames.items()}}
        plugin = ROOT / "openrct2-plugin/rts-bridge.js"
        plugin_text = plugin.read_text()
        replacement = "    const COMMAND_ICON_IMAGES = Object.freeze(" + json.dumps(icon_ids, sort_keys=True) + ");"
        pattern = re.compile(r"^    const COMMAND_ICON_IMAGES = Object\.freeze\(.*\);$", re.MULTILINE)
        plugin_text, count = pattern.subn(replacement, plugin_text)
        if count != 1:
            raise SystemExit("Missing generated command icon mapping in plugin")
        if plugin.read_text() != plugin_text:
            plugin.write_text(plugin_text)
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
    runpy.run_path(str(ROOT / "scripts/generate-starcraft-visual-registry.py"))["generate"](upstream)
    # CMake tracks resource contents through CONFIGURE_DEPENDS; force a rebuild
    # when a selected source's bytes change while its filenames remain fixed.
    if changed:
        print(f"Staged {pack} pack; g2.dat will be rebuilt")
    else:
        print(f"Staged {pack} pack (unchanged)")


if __name__ == "__main__":
    main()
