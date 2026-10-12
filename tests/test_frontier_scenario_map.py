import json
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from starcraft_map_pack import UNIT  # noqa: E402
spec = importlib.util.spec_from_file_location("create_world_base_map", ROOT / "scripts/create-world-base-map.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
scenario_units = module.scenario_units


class FrontierScenarioMapTest(unittest.TestCase):
    def test_positions_and_ownership_are_park_relative(self):
        units = [UNIT.unpack(value) for value in scenario_units(ROOT / "scenarios/frontier-outpost.json")]
        self.assertEqual(len(units), 18)
        self.assertEqual([row[3] for row in units[:12]], [37] * 12)
        self.assertEqual([row[7] for row in units[:12]], [0] * 12)
        self.assertEqual([row[3] for row in units[12:]], [0] * 6)
        self.assertEqual([row[7] for row in units[12:]], [1] * 6)
        self.assertEqual((units[0][1], units[0][2]), ((47 + 32) * 32 + 16, (57 + 32) * 32 + 16))
        self.assertEqual((units[12][1], units[12][2]), ((15 + 32) * 32 + 16, (30 + 32) * 32 + 16))

    def test_rejects_duplicate_starting_tile(self):
        scenario = json.loads((ROOT / "scenarios/frontier-outpost.json").read_text())
        scenario["starting_units"]["marines"][0] = scenario["starting_units"]["zerglings"][0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            path.write_text(json.dumps(scenario))
            with self.assertRaisesRegex(ValueError, "overlapping starting tile"):
                scenario_units(path)

    def test_other_park_size_uses_the_same_centering_rule(self):
        scenario = json.loads((ROOT / "scenarios/frontier-outpost.json").read_text())
        scenario["park_size"] = [32, 48]
        scenario["starting_units"] = {"marines": [[0, 0]], "zerglings": [[31, 47]]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            path.write_text(json.dumps(scenario))
            units = [UNIT.unpack(value) for value in scenario_units(path)]
        self.assertEqual((units[0][1], units[0][2]), ((31 + 48) * 32 + 16, (47 + 40) * 32 + 16))
        self.assertEqual((units[1][1], units[1][2]), (48 * 32 + 16, 40 * 32 + 16))


if __name__ == "__main__":
    unittest.main()
