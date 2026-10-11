"""Canonical native snapshot logs and screen-space squad checks."""

from __future__ import annotations

import json
import math
import hashlib
from pathlib import Path
import re

import numpy as np
from PIL import Image


APPLY = re.compile(r"RTS Bridge apply tick=(\d+) seq=(\d+) session=([0-9a-f]{32})(?: center_z=(-?[0-9]+))? units=([^\x1b\r\n]*)")
UNIT = re.compile(r"(openbw:[0-9]+),(-?[0-9]+),(-?[0-9]+),([0-9]+),(idle|walk|attack|death)(?:,(-?[0-9]+))?")
COMBAT_UNIT = re.compile(r"(openbw:[0-9]+),(-?[0-9]+),(-?[0-9]+),([0-9]+),(idle|walk|attack|death),(-?[0-9]+),(terran_marine|zerg_zergling),([0-9]+),([0-9]+),([0-9]+),([0-9]+)")


def parse_combat_applied(text: str) -> dict[tuple[str, int], tuple[tuple, ...]]:
    snapshots = {}
    for _tick, seq, session, _center_z, body in APPLY.findall(text):
        units = tuple(sorted((unit_id, int(x), int(y), int(facing), motion, int(z), kind,
                              int(hp), int(max_hp), int(owner), int(attack_frames))
                             for unit_id, x, y, facing, motion, z, kind, hp, max_hp, owner, attack_frames
                             in COMBAT_UNIT.findall(body)))
        if body and len(units) != len(body.split(";")):
            continue
        snapshots[session, int(seq)] = units
    return snapshots


def parse_applied(text: str) -> dict[tuple[str, int], tuple[tuple[str, int, int, int, str], ...]]:
    snapshots = {}
    for _tick, seq, session, _center_z, body in APPLY.findall(text):
        records = tuple(sorted((unit_id, int(x), int(y), int(facing), motion)
                               for unit_id, x, y, facing, motion, _z in UNIT.findall(body)))
        if body and len(records) != len(body.split(";")):
            raise ValueError(f"malformed native actor log for session={session} seq={seq}")
        ids = [record[0] for record in records]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate native actor log for session={session} seq={seq}")
        key = session, int(seq)
        if key in snapshots and snapshots[key] != records:
            raise ValueError(f"conflicting native actor log for session={session} seq={seq}")
        snapshots[key] = records
    return snapshots


def parse_projected(text: str) -> dict[tuple[str, int], dict]:
    snapshots = {}
    for _tick, seq, session, center_z, body in APPLY.findall(text):
        actors = tuple(sorted((unit_id, int(x), int(y), int(facing), motion, int(z) if z else 112)
                              for unit_id, x, y, facing, motion, z in UNIT.findall(body)))
        snapshots[session, int(seq)] = {"center_z": int(center_z) if center_z else 112,
                                        "actors": actors}
    return snapshots


def compare_clients(logs: dict[str, str], minimum_common: int) -> dict:
    states = {name: parse_applied(text) for name, text in logs.items()}
    common = set.intersection(*(set(value) for value in states.values()))
    mismatches = sorted(key for key in common if len({states[name][key] for name in states}) != 1)
    counts = {name: len(value) for name, value in states.items()}
    if len(common) < minimum_common or mismatches:
        raise ValueError(f"authoritative disagreement: common={len(common)} counts={counts} mismatches={mismatches[:5]}")
    full = [key for key in common if len(states["server"][key]) == 8]
    seven = [key for key in common if len(states["server"][key]) == 7]
    empty = [key for key in common if not states["server"][key]]
    stable_ids = sorted({unit[0] for key in full for unit in states["server"][key]})
    return {"common_snapshots": len(common), "mismatches": len(mismatches),
            "applied_counts": counts, "eight_unit_snapshots": len(full),
            "seven_unit_snapshots": len(seven), "empty_snapshots": len(empty),
            "stable_ids": stable_ids, "sessions": sorted({key[0] for key in common})}


SPRITE_DIRECTIONS = ("east", "southeast", "south", "southwest", "west", "northwest", "north", "northeast")


def screen_direction(facing: int, rotation: int = 0) -> str:
    """Select the GRP view reached by projecting a BWAPI heading into the park."""
    angle = facing * math.tau / 256
    dx, dy = math.cos(angle), math.sin(angle)
    rx, ry = ((dx, dy), (dy, -dx), (-dx, -dy), (-dy, dx))[rotation & 3]
    octant = round(math.atan2((rx + ry) / 2, ry - rx) * 4 / math.pi) % 8
    return SPRITE_DIRECTIONS[octant]


def project(x: int, y: int, rotation: int, z: int = 112, center_z: int = 112) -> tuple[int, int]:
    """World feet to the 1280x800 demo viewport at zoom -1, centred on (480,480)."""
    def rotate(px: int, py: int) -> tuple[int, int]:
        return ((px, py), (py, -px), (-px, -py), (-py, px))[rotation]

    rx, ry = rotate(x, y)
    cx, cy = rotate(480, 480)
    return 640 + 2 * ((ry - rx) - (cy - cx)), 400 + 2 * (((rx + ry) // 2 - z) - ((cx + cy) // 2 - center_z))


def local_purple_counts(path: Path, actors: tuple, rotation: int, center_z: int = 112) -> dict[str, int]:
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.int16)
    purple = (rgb[:, :, 0] >= 60) & (rgb[:, :, 2] >= rgb[:, :, 0] + 35) & (rgb[:, :, 2] >= rgb[:, :, 1] + 25)
    found = {}
    for actor in actors:
        unit_id, x, y = actor[:3]
        z = actor[5] if len(actor) > 5 else 112
        px, py = project(x, y, rotation, z, center_z)
        left, right = max(0, px - 64), min(rgb.shape[1], px + 33)
        top, bottom = max(40, py - 76), min(rgb.shape[0] - 40, py + 33)
        found[unit_id] = int(purple[top:bottom, left:right].sum())
    return found


def animation_region_hashes(path: Path, actors: tuple, rotation: int, center_z: int = 112) -> dict[str, str]:
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.int16)
    purple = (rgb[:, :, 0] >= 60) & (rgb[:, :, 2] >= rgb[:, :, 0] + 35) & (rgb[:, :, 2] >= rgb[:, :, 1] + 25)
    result = {}
    for actor in actors:
        unit_id, x, y, _facing, motion = actor[:5]
        if motion != "walk":
            continue
        z = actor[5] if len(actor) > 5 else 112
        px, py = project(x, y, rotation, z, center_z)
        left, right = max(0, px - 45), min(rgb.shape[1], px + 46)
        top, bottom = max(40, py - 110), min(rgb.shape[0] - 40, py + 70)
        area = purple[top:bottom, left:right]
        if area.sum() >= 8:
            result[unit_id] = hashlib.sha256(area.tobytes()).hexdigest()[:16]
    return result


def write_summary(path: Path, summary: dict) -> None:
    path.write_text(json.dumps(summary, indent=2) + "\n")
