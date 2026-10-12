#!/usr/bin/env python3
"""Build one reusable 128x128 OpenBW base map with no park-specific objects."""

import argparse
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from starcraft_map_pack import SOURCE, unit, pack_map


def scenario_units(path: Path) -> list[bytes]:
    scenario = json.loads(path.read_text())
    size = scenario.get("park_size")
    if (scenario.get("version") != 1 or not isinstance(size, list) or len(size) != 2
            or any(type(value) is not int or not 1 <= value <= 128 for value in size)):
        raise ValueError("scenario must describe a park of at most 128x128 with version 1")
    groups = scenario.get("starting_units")
    if (not isinstance(groups, dict) or any(not isinstance(groups.get(name), list)
            or not 1 <= len(groups[name]) <= 256 for name in ("marines", "zerglings"))):
        raise ValueError("scenario requires 1-256 Marines and 1-256 Zerglings")
    units = []
    occupied = set()
    for name, kind, owner, first_id in (("zerglings", 37, 0, 10), ("marines", 0, 1, 1000)):
        for index, location in enumerate(groups[name]):
            if (not isinstance(location, list) or len(location) != 2
                    or any(type(v) is not int or v < 0 or v >= size[axis] for axis, v in enumerate(location))):
                raise ValueError(f"invalid {name} starting tile: {location}")
            tile = tuple(location)
            if tile in occupied:
                raise ValueError(f"overlapping starting tile: {tile}")
            occupied.add(tile)
            x, y = (((location[0] + (128 - size[0]) // 2) * 32 + 16),
                    ((location[1] + (128 - size[1]) // 2) * 32 + 16))
            units.append(unit(first_id + index, x, y, kind, owner))
    return units


def patch_chk(data: bytes, zerglings: int = 8, marines: int = 4,
              separate_armies: bool = False, scenario: Path | None = None) -> bytes:
    # Generic players and a small attack squad. Park structures arrive only
    # through world.v1; there are no fixture targets or matching coordinates.
    if scenario is not None:
        units = scenario_units(scenario)
    else:
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
    parser.add_argument("--scenario", type=Path, help="JSON scenario with park-relative starting tiles")
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
                            args.zerglings, args.marines, args.separate_armies, args.scenario)
        output.write_bytes(pack_map(patched))
    print(output)


if __name__ == "__main__":
    main()
