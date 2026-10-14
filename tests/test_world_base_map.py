"""Structural and reproducibility checks for the generated native OpenBW map."""

import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from starcraft_map_pack import SOURCE, UNIT  # noqa: E402

spec = importlib.util.spec_from_file_location("world_base_map", ROOT / "scripts/create-world-base-map.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sections(data):
    found = {}
    cursor = 0
    while cursor + 8 <= len(data):
        tag = data[cursor:cursor + 4]
        size = struct.unpack_from("<I", data, cursor + 4)[0]
        found[tag] = data[cursor + 8:cursor + 8 + size]
        cursor += 8 + size
    if cursor != len(data):
        raise ValueError("trailing CHK data")
    return found


class WorldBaseMapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["smpq", "-q", "-x", str(SOURCE), "staredit/scenario.chk"],
                           cwd=directory, check=True)
            cls.source = (Path(directory) / "staredit/scenario.chk").read_bytes()

    def test_all_dimensioned_sections_and_determinism(self):
        first = module.patch_chk(self.source)
        self.assertEqual(first, module.patch_chk(self.source))
        parts = sections(first)
        self.assertEqual(parts[b"DIM "], struct.pack("<HH", 256, 256))
        self.assertEqual(len(parts[b"MTXM"]), 256 * 256 * 2)
        self.assertEqual(len(parts[b"TILE"]), 256 * 256 * 2)
        self.assertEqual(len(parts[b"MASK"]), 256 * 256)
        self.assertEqual(len(parts[b"ISOM"]), (256 + 2) * (256 + 1) * 4)
        self.assertEqual(parts[b"MTXM"], parts[b"TILE"])
        self.assertEqual(parts[b"MASK"], b"\xff" * (256 * 256))

    def test_frontier_starting_units_use_map_center(self):
        parts = sections(module.patch_chk(self.source, scenario=ROOT / "scenarios/frontier-outpost/scenario.json"))
        units = [UNIT.unpack_from(parts[b"UNIT"], i) for i in range(0, len(parts[b"UNIT"]), UNIT.size)]
        scenario = json.loads((ROOT / "scenarios/frontier-outpost/scenario.json").read_text())
        offset = (module.MAP_SIZE - scenario["park_size"][0]) // 2
        first = scenario["starting_units"]["zerglings"][0]
        self.assertEqual(units[0][1:3], ((first[0] + offset) * 32 + 16,
                                          (first[1] + offset) * 32 + 16))
        self.assertEqual([row[0] for row in units],
                         list(range(10, 10 + len(scenario["starting_units"]["zerglings"]))) +
                         list(range(1000, 1000 + len(scenario["starting_units"]["marines"]))))

    def test_rejects_oversized_park(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            scenario = json.loads((ROOT / "scenarios/frontier-outpost/scenario.json").read_text())
            scenario["park_size"] = [257, 256]
            path.write_text(json.dumps(scenario))
            with self.assertRaisesRegex(ValueError, "256x256"):
                module.scenario_units(path)


if __name__ == "__main__":
    unittest.main()
