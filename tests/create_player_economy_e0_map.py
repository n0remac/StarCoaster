#!/usr/bin/env python3
"""Pack a test-only native economy in the existing 256-tile park map."""

import argparse
from pathlib import Path
import runpy
import struct
import subprocess
import tempfile

from sys import path as python_path
python_path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
patch_chk = runpy.run_path(str(Path(__file__).resolve().parents[1]
                            / "scripts/create-world-base-map.py"))["patch_chk"]
from starcraft_map_pack import SOURCE, UNIT, pack_map  # type: ignore


# Frontier's park tiles 8..11 are level, open ground. Its 64-tile park is
# centered at native tile 96. These are native upper-left tiles, not centers.
SITES = {
    "command_center": (116, 104, 106),
    "scv_miner": (121, 106, 7),
    "scv_builder": (122, 106, 7),
    "mineral_a": (124, 105, 176),
    "mineral_b": (126, 105, 176),
    "geyser": (130, 104, 188),
}
RESOURCE_AMOUNT = {"mineral_a": 1500, "mineral_b": 1500, "geyser": 5000}


def fixture_unit(identifier: int, name: str) -> bytes:
    x, y, kind = SITES[name]
    # BWAPI/OpenBW CHK UNIT records use center pixels. Resource amount is
    # valid only when the UNIT valid_properties bit 0x10 is set.
    width, height = {106: (4, 3), 176: (2, 1), 188: (4, 2)}.get(kind, (1, 1))
    owner = 11 if name in RESOURCE_AMOUNT else 1
    amount = RESOURCE_AMOUNT.get(name, 0)
    return UNIT.pack(identifier, x * 32 + width * 16, y * 32 + height * 16,
                     kind, 0, 0, 0x10 if amount else 0, owner,
                     100, 100, 100, amount, 0, 0, 0, 0)


def replace_units(chk: bytes) -> bytes:
    entries = b"".join(fixture_unit(3000 + index, name)
                       for index, name in enumerate(SITES))
    result = bytearray()
    offset = 0
    replaced = False
    while offset < len(chk):
        tag = chk[offset:offset + 4]
        size = struct.unpack_from("<I", chk, offset + 4)[0]
        body = chk[offset + 8:offset + 8 + size]
        if tag == b"UNIT":
            body = entries
            replaced = True
        result += tag + struct.pack("<I", len(body)) + body
        offset += 8 + size
    if not replaced or offset != len(chk):
        raise ValueError("missing or malformed UNIT section")
    return bytes(result)


def make_chk() -> bytes:
    with tempfile.TemporaryDirectory(prefix="economy-e0-") as directory:
        subprocess.run(["smpq", "-q", "-x", str(SOURCE), "staredit/scenario.chk"],
                       cwd=directory, check=True)
        chk = (Path(directory) / "staredit/scenario.chk").read_bytes()
    return replace_units(patch_chk(chk, zerglings=0, marines=0))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(pack_map(make_chk()))
    print(args.output)


if __name__ == "__main__":
    main()
