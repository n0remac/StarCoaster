#!/usr/bin/env python3
"""Build one reusable 128x128 OpenBW base map with no park-specific objects."""

import argparse
from pathlib import Path
import struct
import subprocess
import tempfile

from starcraft_map_pack import SOURCE, unit, pack_map


def patch_chk(data: bytes, zerglings: int = 8, marines: int = 4,
              separate_armies: bool = False) -> bytes:
    # Generic players and a small attack squad. Park structures arrive only
    # through world.v1; there are no fixture targets or matching coordinates.
    units = [unit(10 + i, 352 + (i % 10) * 24,
                        352 + (i // 10) * 24, 37, 0) for i in range(zerglings)]
    marine_x = 2304 if separate_armies else 640
    units += [unit(1000 + i, marine_x + (i % 10) * 24,
                          352 + (i // 10) * 24, 0, 1) for i in range(marines)]
    # Slot 2 owns park targets so both playable factions can attack them.
    replacements = {b"OWNR": bytes([6, 6, 5] + [0] * 9),
                    b"SIDE": bytes([0, 1, 1] + [0] * 9),
                    b"UNIT": b"".join(units), b"TRIG": b""}
    result, offset, seen = bytearray(), 0, set()
    while offset + 8 <= len(data):
        tag = data[offset:offset + 4]
        size = struct.unpack_from("<I", data, offset + 4)[0]
        end = offset + 8 + size
        if end > len(data):
            raise ValueError("truncated CHK section")
        body = replacements.get(tag, data[offset + 8:end])
        if tag in replacements:
            seen.add(tag)
        result += tag + struct.pack("<I", len(body)) + body
        offset = end
    if offset != len(data) or seen != replacements.keys():
        raise ValueError("missing CHK section or trailing data")
    return bytes(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--zerglings", type=int, default=8)
    parser.add_argument("--marines", type=int, default=4)
    parser.add_argument("--separate-armies", action="store_true",
                        help="keep armies apart for snapshot capacity measurements")
    args = parser.parse_args()
    if not 0 <= args.zerglings <= 256 or not 0 <= args.marines <= 256:
        parser.error("each actor count must be between 0 and 256")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="world-base-") as name:
        temporary = Path(name)
        subprocess.run(["smpq", "-q", "-x", str(SOURCE), "staredit/scenario.chk"],
                       cwd=temporary, check=True)
        patched = patch_chk((temporary / "staredit/scenario.chk").read_bytes(),
                            args.zerglings, args.marines, args.separate_armies)
        output.write_bytes(pack_map(patched))
    print(output)


if __name__ == "__main__":
    main()
