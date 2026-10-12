#!/usr/bin/env python3
"""Create the 20-Zergling, three-proxy OpenBW Use Map Settings fixture."""

import argparse
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "scripts/create-ride-siege-map.py"
DEFAULT = ROOT / "run-data/park-assault/map/park-assault.scm"

spec = importlib.util.spec_from_file_location("ride_siege_map", BASE)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def positions() -> list[tuple[str, int, int]]:
    units = []
    for index in range(8):
        units.append(("alpha", 9 * 32 + 8 + index % 2 * 24,
                      20 * 32 + 8 + index // 2 * 24))
    for index in range(6):
        units.append(("beta", 29 * 32 + 8 + index % 3 * 24,
                      9 * 32 + 8 + index // 3 * 24))
    for index in range(6):
        units.append(("gamma", 33 * 32 + 8 + index % 3 * 24,
                      51 * 32 + 8 + index // 3 * 24))
    return units


def patch_chk(data: bytes, fixture: dict) -> bytes:
    offset = fixture["transform"]
    records = [base.unit(1, 320, 480, 214, 0), base.unit(2, 2200, 2200, 214, 1)]
    for index, target in enumerate(fixture["targets"]):
        world = target["proxy_world"]
        if world != target["structure_center"] or not target["footprint_tiles"]:
            raise ValueError(f"invalid proxy position or footprint: {target['id']}")
        if any((world[axis] - offset[axis]) % 16 for axis in ("x", "y")):
            raise ValueError(f"proxy position cannot be placed on the OpenBW grid: {target['id']}")
        records.append(base.unit(100 + index, world["x"] - offset["x"],
                                 world["y"] - offset["y"], target["proxy_unit_type"], 1))
    for index, (_, x, y) in enumerate(positions()):
        records.append(base.unit(200 + index, x - offset["x"], y - offset["y"], 37, 0))
    replacements = {b"OWNR": bytes([6, 5] + [0] * 10),
                    b"SIDE": bytes([0, 1] + [0] * 10),
                    b"UNIT": b"".join(records), b"TRIG": b""}
    output, cursor, seen = bytearray(), 0, set()
    while cursor + 8 <= len(data):
        tag = data[cursor:cursor + 4]
        size = struct.unpack_from("<I", data, cursor + 4)[0]
        end = cursor + 8 + size
        if end > len(data):
            raise ValueError("truncated CHK section")
        body = replacements.get(tag, data[cursor + 8:end])
        if tag in replacements:
            seen.add(tag)
        output += tag + struct.pack("<I", len(body)) + body
        cursor = end
    if cursor != len(data) or seen != replacements.keys():
        raise ValueError("missing CHK section or trailing data")
    return bytes(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT)
    args = parser.parse_args()
    fixture = json.loads((ROOT / "run-data/park-assault/fixture.json").read_text())
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="park-assault-map-") as temp:
        staging = Path(temp)
        subprocess.run(["smpq", "-q", "-x", str(base.SOURCE), "staredit/scenario.chk"],
                       cwd=staging, check=True)
        chk = patch_chk((staging / "staredit/scenario.chk").read_bytes(), fixture)
        output.write_bytes(base.pack_map(chk))
        (staging / "staredit/scenario.chk").unlink()
        subprocess.run(["smpq", "-q", "-x", str(output), "staredit/scenario.chk"],
                       cwd=staging, check=True)
        if (staging / "staredit/scenario.chk").read_bytes() != chk:
            raise RuntimeError("generated MPQ did not round-trip")
    manifest = {"map_id": "park-assault", "transform": fixture["transform"],
                "zerglings": [{"id": 200 + i, "squad": squad, "park_x": x, "park_y": y,
                                "bw_x": x - fixture["transform"]["x"],
                                "bw_y": y - fixture["transform"]["y"]}
                               for i, (squad, x, y) in enumerate(positions())],
                "proxies": [{"id": 100 + i, "target_id": target["id"], "ride_id": target["ride_id"],
                             "max_hp": target["proxy_hp"], "unit_type": target["proxy_type"],
                             "collision": target["proxy_collision"], "park_world": target["proxy_world"],
                             "bw_world": {axis: target["proxy_world"][axis] - fixture["transform"][axis]
                                          for axis in ("x", "y")}}
                            for i, target in enumerate(fixture["targets"])]}
    output.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
