import struct
import unittest

from tests.create_player_economy_e0_map import SITES, RESOURCE_AMOUNT, make_chk
from scripts.starcraft_map_pack import UNIT


class EconomyE0MapTest(unittest.TestCase):
    def test_native_fixture_uses_neutral_resources_and_real_amounts(self):
        chk = make_chk()
        offset = 0
        while chk[offset:offset + 4] != b"UNIT":
            offset += 8 + struct.unpack_from("<I", chk, offset + 4)[0]
        size = struct.unpack_from("<I", chk, offset + 4)[0]
        records = [UNIT.unpack_from(chk, offset + 8 + index * UNIT.size)
                   for index in range(size // UNIT.size)]
        self.assertEqual(len(records), len(SITES))
        for index, name in enumerate(SITES):
            record = records[index]
            self.assertEqual(record[3], SITES[name][2])
            self.assertEqual(record[7], 11 if name in RESOURCE_AMOUNT else 1)
            self.assertEqual(record[6], 0x10 if name in RESOURCE_AMOUNT else 0)
            self.assertEqual(record[11], RESOURCE_AMOUNT.get(name, 0))
            self.assertEqual(record[0], 3000 + index)


if __name__ == "__main__":
    unittest.main()
