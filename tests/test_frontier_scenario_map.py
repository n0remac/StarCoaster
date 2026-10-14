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
    def test_starting_units_match_saved_ridge_and_low_approach(self):
        data = ROOT / "run-data/frontier-playable"
        fixture_path = data / "fixture.json"
        fixture = json.loads(fixture_path.read_text()) if fixture_path.exists() else {}
        if fixture.get("layout_version") != 4 or fixture.get("terrain_version") != 1:
            import subprocess
            subprocess.run(["python3", "scripts/create-park-assault.py", "--playable"],
                           cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        export = json.loads((data / "navigation-elements.json").read_text())
        scenario = json.loads((ROOT / "scenarios/frontier-outpost/scenario.json").read_text())
        heights = export["elevation_rows"]
        for x, y in scenario["starting_units"]["marines"]:
            self.assertEqual(heights[y - 8][x - 8], 128)
        for x, y in scenario["starting_units"]["zerglings"]:
            self.assertFalse(14 <= x <= 24 and 30 <= y <= 34)

    def test_positions_and_ownership_are_park_relative(self):
        scenario = json.loads((ROOT / "scenarios/frontier-outpost/scenario.json").read_text())
        self.assertEqual(len(scenario["starting_units"]["marines"]), 6)
        self.assertEqual(scenario["version"], 2)
        self.assertEqual(scenario["waves"][0]["id"], "opening-zerg-wave")
        self.assertEqual(scenario["waves"][0]["groups"][0]["count"], 5)
        self.assertEqual(scenario["spawn_zones"]["east-entrance"]["tiles"][0], [44, 56])
        units = [UNIT.unpack(value) for value in scenario_units(ROOT / "scenarios/frontier-outpost/scenario.json")]
        self.assertEqual(len(units), 18)
        self.assertEqual([row[3] for row in units[:12]], [37] * 12)
        self.assertEqual([row[7] for row in units[:12]], [0] * 12)
        self.assertEqual([row[3] for row in units[12:]], [0] * 6)
        self.assertEqual([row[7] for row in units[12:]], [1] * 6)
        offset = (module.MAP_SIZE - 64) // 2
        self.assertEqual((units[0][1], units[0][2]), ((47 + offset) * 32 + 16, (57 + offset) * 32 + 16))
        self.assertEqual((units[12][1], units[12][2]), ((15 + offset) * 32 + 16, (30 + offset) * 32 + 16))

    def test_rejects_duplicate_starting_tile(self):
        scenario = json.loads((ROOT / "scenarios/frontier-outpost/scenario.json").read_text())
        scenario["starting_units"]["marines"][0] = scenario["starting_units"]["zerglings"][0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            path.write_text(json.dumps(scenario))
            with self.assertRaisesRegex(ValueError, "overlapping starting tile"):
                scenario_units(path)

    def test_other_park_size_uses_the_same_centering_rule(self):
        scenario = json.loads((ROOT / "scenarios/frontier-outpost/scenario.json").read_text())
        scenario["park_size"] = [32, 48]
        scenario["starting_units"] = {"marines": [[0, 0]], "zerglings": [[31, 47]]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            path.write_text(json.dumps(scenario))
            units = [UNIT.unpack(value) for value in scenario_units(path)]
        offset_x, offset_y = (module.MAP_SIZE - 32) // 2, (module.MAP_SIZE - 48) // 2
        self.assertEqual((units[0][1], units[0][2]), ((31 + offset_x) * 32 + 16, (47 + offset_y) * 32 + 16))
        self.assertEqual((units[1][1], units[1][2]), (offset_x * 32 + 16, offset_y * 32 + 16))

    def test_v2_uses_identical_native_tile_centering(self):
        scenario = json.loads((ROOT / "scenarios/frontier-outpost/scenario.json").read_text())
        scenario["version"] = 2
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            path.write_text(json.dumps(scenario))
            units = [UNIT.unpack(value) for value in scenario_units(path)]
        offset = (module.MAP_SIZE - 64) // 2
        self.assertEqual((units[0][1], units[0][2]), ((47 + offset) * 32 + 16, (57 + offset) * 32 + 16))


if __name__ == "__main__":
    unittest.main()
