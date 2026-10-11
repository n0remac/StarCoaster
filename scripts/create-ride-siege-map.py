#!/usr/bin/env python3
"""Create a small Use Map Settings OpenBW siege fixture from the pinned test map."""

import argparse
from pathlib import Path
import struct
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "upstream/bwapi/bwapi/TestAIModule/maps/TestModule/testmap1.scm"
DEFAULT_OUTPUT = ROOT / "run-data/ride-siege-map/ride-siege.scm"
UNIT = struct.Struct("<IHHHHHHBBBBIHHII")


def unit(unit_id: int, x: int, y: int, kind: int, owner: int) -> bytes:
    return UNIT.pack(unit_id, x, y, kind, 0, 0, 0, owner, 100, 100, 100, 0, 0, 0, 0, 0)


def patch_chk(data: bytes) -> bytes:
    # The pinned map is 128x128 tiles. Player 0 is the Zerg simulation player,
    # player 1 is the hostile Terran structure owner. Keep the terrain unchanged.
    records = [unit(1, 320, 480, 214, 0), unit(2, 2200, 2200, 214, 1),
               unit(3, 736, 576, 124, 1)]  # Missile Turret (BW unit type 124).
    records += [unit(10 + i, 544 + (i % 2) * 24, 488 + (i // 2) * 28, 37, 0)
                for i in range(8)]  # Zergling (BW unit type 37).
    replacements = {
        b"OWNR": bytes([6, 5] + [0] * 10),
        b"SIDE": bytes([0, 1] + [0] * 10),
        b"UNIT": b"".join(records),
        b"TRIG": b"",  # The source map's tutorial triggers end the game at frame zero.
    }
    output = bytearray()
    offset = 0
    seen = set()
    while offset + 8 <= len(data):
        tag = data[offset:offset + 4]
        size = struct.unpack_from("<I", data, offset + 4)[0]
        end = offset + 8 + size
        if end > len(data):
            raise ValueError("truncated CHK section")
        body = replacements.get(tag, data[offset + 8:end])
        if tag in replacements:
            seen.add(tag)
        output += tag + struct.pack("<I", len(body)) + body
        offset = end
    if offset != len(data) or seen != replacements.keys():
        raise ValueError("missing CHK section or trailing data")
    return bytes(output)


def crypt_table() -> list[int]:
    table = [0] * 0x500
    seed = 0x00100001
    for index in range(256):
        for row in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            high = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB
            table[row * 256 + index] = high | (seed & 0xFFFF)
    return table


CRYPT = crypt_table()


def mpq_hash(name: str, kind: int) -> int:
    seed1, seed2 = 0x7FED7FED, 0xEEEEEEEE
    for char in name.upper().replace("/", "\\").encode("ascii"):
        seed1 = (CRYPT[kind * 256 + char] ^ (seed1 + seed2)) & 0xFFFFFFFF
        seed2 = (char + seed1 + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return seed1


def encrypt_table(data: bytes, key: int) -> bytes:
    seed1, seed2 = key, 0xEEEEEEEE
    result = bytearray()
    for offset in range(0, len(data), 4):
        value = struct.unpack_from("<I", data, offset)[0]
        seed2 = (seed2 + CRYPT[0x400 + (seed1 & 0xFF)]) & 0xFFFFFFFF
        result += struct.pack("<I", value ^ ((seed1 + seed2) & 0xFFFFFFFF))
        seed1 = (((~seed1 << 21) + 0x11111111) | (seed1 >> 11)) & 0xFFFFFFFF
        seed2 = (value + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return bytes(result)


def pack_map(chk: bytes) -> bytes:
    # MPQ v1 with raw sectors under MPQ's compressed-sector layout. The pinned
    # OpenBW reader accepts raw sectors and this avoids the broken smpq writer.
    # write path on the target Pi while retaining standard StormLib readability.
    name = "staredit/scenario.chk"
    hash_count = 8
    hash_entries = [struct.pack("<IIII", 0xFFFFFFFF, 0xFFFFFFFF,
                                0xFFFFFFFF, 0xFFFFFFFF) for _ in range(hash_count)]
    hash_entries[mpq_hash(name, 0) % hash_count] = struct.pack(
        "<IIHHI", mpq_hash(name, 1), mpq_hash(name, 2), 0, 0, 0)
    hash_table = encrypt_table(b"".join(hash_entries), mpq_hash("(hash table)", 3))
    sectors = [chk[index:index + 4096]
               for index in range(0, len(chk), 4096)]
    offsets = [4 * (len(sectors) + 1)]
    for sector in sectors:
        offsets.append(offsets[-1] + len(sector))
    compressed = struct.pack("<" + "I" * len(offsets), *offsets) + b"".join(sectors)
    data_offset = 32 + len(hash_table) + 16
    block_table = encrypt_table(struct.pack("<IIII", data_offset, len(compressed), len(chk),
                                            0x80000200), mpq_hash("(block table)", 3))
    header = struct.pack("<4sIIHHIIII", b"MPQ\x1a", 32, data_offset + len(compressed),
                         0, 3, 32, 32 + len(hash_table), hash_count, 1)
    return header + hash_table + block_table + compressed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ride-siege-map-") as temporary:
        staging = Path(temporary)
        subprocess.run(["smpq", "-q", "-x", str(SOURCE), "staredit/scenario.chk"],
                       cwd=staging, check=True)
        chk = staging / "staredit/scenario.chk"
        patched = patch_chk(chk.read_bytes())
        output.write_bytes(pack_map(patched))
        extracted = staging / "verified/staredit/scenario.chk"
        extracted.parent.mkdir(parents=True)
        subprocess.run(["smpq", "-q", "-x", str(output), "staredit/scenario.chk"],
                       cwd=staging / "verified", check=True)
        if extracted.read_bytes() != patched:
            raise RuntimeError("MPQ map round-trip verification failed")
    print(output)


if __name__ == "__main__":
    main()
