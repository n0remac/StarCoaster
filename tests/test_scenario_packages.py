import importlib.util
import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("play_scenario", ROOT / "scripts/play-scenario.py")
play = importlib.util.module_from_spec(spec)
spec.loader.exec_module(play)


class ScenarioPackageTest(unittest.TestCase):
    def test_distinct_packages_share_launcher_and_native_map_builder(self):
        frontier = play.resolve("frontier-outpost")
        example = play.resolve("example-defense")
        self.assertNotEqual(frontier["park"], example["park"])
        self.assertNotEqual(frontier["native_map"], example["native_map"])
        self.assertEqual(frontier["generator"][1], example["generator"][1])
        self.assertEqual(json.loads(Path(example["scenario"]).read_text())["version"], 2)
        self.assertEqual(json.loads(Path(frontier["scenario"]).read_text())["scenario_id"], "frontier-outpost")

    def test_compatibility_wrapper_resolves_same_frontier_package(self):
        original = subprocess.check_output(["scripts/run-frontier-outpost.sh", "--plan"], cwd=ROOT)
        generic = subprocess.check_output(["scripts/project.sh", "play", "frontier-outpost", "--plan"], cwd=ROOT)
        self.assertEqual(json.loads(original), json.loads(generic))

    def test_invalid_package_id_rejected(self):
        for value in ("../example-defense", "Frontier", "missing/package"):
            with self.assertRaises(ValueError):
                play.resolve(value)


if __name__ == "__main__":
    unittest.main()
