"""Reusable MPQ packing helpers for a fixed OpenBW base map."""

from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "upstream/bwapi/bwapi/TestAIModule/maps/TestModule/testmap1.scm"
UNIT = struct.Struct("<IHHHHHHBBBBIHHII")


def unit(unit_id: int, x: int, y: int, kind: int, owner: int) -> bytes:
    return UNIT.pack(unit_id, x, y, kind, 0, 0, 0, owner, 100, 100, 100, 0, 0, 0, 0, 0)


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
    # A reusable MPQ v1 container with raw sectors. OpenBW reads these sectors
    # directly; the map terrain and rules are fixed across all parks.
    name = "staredit/scenario.chk"
    hash_count = 8
    hash_entries = [struct.pack("<IIII", 0xFFFFFFFF, 0xFFFFFFFF,
                                0xFFFFFFFF, 0xFFFFFFFF) for _ in range(hash_count)]
    hash_entries[mpq_hash(name, 0) % hash_count] = struct.pack(
        "<IIHHI", mpq_hash(name, 1), mpq_hash(name, 2), 0, 0, 0)
    hash_table = encrypt_table(b"".join(hash_entries), mpq_hash("(hash table)", 3))
    sectors = [chk[index:index + 4096] for index in range(0, len(chk), 4096)]
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
