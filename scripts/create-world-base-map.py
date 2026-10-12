#!/usr/bin/env python3
"""Build one reusable 128x128 OpenBW base map with no park-specific objects."""

import argparse
from pathlib import Path
import struct
import subprocess
import tempfile

from starcraft_map_pack import SOURCE, unit, pack_map


def patch_chk(data: bytes) -> bytes:
    # Generic players and a small attack squad. Park structures arrive only
    # through world.v1; there are no fixture targets or matching coordinates.
    units = [unit(1, 2200, 2200, 214, 1)]
    units += [unit(10 + i, 352 + (i % 4) * 24,
                        352 + (i // 4) * 24, 37, 0) for i in range(8)]
    replacements = {b"OWNR": bytes([6, 5] + [0] * 10),
                    b"SIDE": bytes([0, 1] + [0] * 10),
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
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="world-base-") as name:
        temporary = Path(name)
        subprocess.run(["smpq", "-q", "-x", str(SOURCE), "staredit/scenario.chk"],
                       cwd=temporary, check=True)
        patched = patch_chk((temporary / "staredit/scenario.chk").read_bytes())
        output.write_bytes(pack_map(patched))
    print(output)


if __name__ == "__main__":
    main()
