"""The dedicated OpenBW fixture has one target and eight player Zerglings."""

import importlib.util
from pathlib import Path
import struct
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/create-ride-siege-map.py"
spec = importlib.util.spec_from_file_location("ride_siege_map", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RideSiegeMapTests(unittest.TestCase):
    def test_patches_only_allowed_sections(self):
        sections = [(b"OWNR", bytes(12)), (b"SIDE", bytes(12)),
                    (b"UNIT", bytes(36)), (b"TRIG", bytes(2400)),
                    (b"MTXM", b"terrain remains unchanged")]
        chk = b"".join(tag + struct.pack("<I", len(body)) + body for tag, body in sections)
        patched = module.patch_chk(chk)
        chunks = {}
        offset = 0
        while offset < len(patched):
            tag = patched[offset:offset + 4]
            size = struct.unpack_from("<I", patched, offset + 4)[0]
            chunks[tag] = patched[offset + 8:offset + 8 + size]
            offset += 8 + size
        self.assertEqual(chunks[b"MTXM"], sections[-1][1])
        self.assertEqual(chunks[b"OWNR"][:2], bytes([6, 5]))
        self.assertEqual(chunks[b"SIDE"][:2], bytes([0, 1]))
        self.assertEqual(chunks[b"TRIG"], b"")
        units = [module.UNIT.unpack_from(chunks[b"UNIT"], i)
                 for i in range(0, len(chunks[b"UNIT"]), module.UNIT.size)]
        self.assertEqual(len(units), 11)
        self.assertEqual(sum(u[3] == 124 and u[7] == 1 for u in units), 1)
        self.assertEqual(sum(u[3] == 37 and u[7] == 0 for u in units), 8)

    def test_missing_section_fails(self):
        with self.assertRaises(ValueError):
            module.patch_chk(b"UNIT" + struct.pack("<I", 0))


if __name__ == "__main__":
    unittest.main()
