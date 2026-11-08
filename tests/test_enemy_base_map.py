"""Generated B1 colony CHK records are stable and absent on blocked sites."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from starcraft_map_pack import UNIT  # noqa: E402

spec = importlib.util.spec_from_file_location("world_base_map", ROOT / "scripts/create-world-base-map.py")
maps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maps)


class EnemyBaseMapTest(unittest.TestCase):
    def scenario(self, directory, ready):
        value = json.loads((ROOT / "scenarios/economy-e1/scenario.json").read_text())
        value["enemy_base"] = {"version": 1, "layout_policy": "generated",
            "layout_state": "ready" if ready else "blocked",
            "structures": [
                {"id": "enemy-hatchery", "type": "zerg_hatchery", "faction": "zerg", "tile": [8, 31]},
                {"id": "enemy-spawning-pool", "type": "zerg_spawning_pool", "faction": "zerg", "tile": [13, 32]}]
                if ready else [], "supply_tile": [16, 34] if ready else []}
        path = Path(directory) / "scenario.json"
        path.write_text(json.dumps(value))
        return path

    def test_ready_colony_has_one_completed_native_record_per_type(self):
        with tempfile.TemporaryDirectory() as directory:
            records = [UNIT.unpack(row) for row in maps.scenario_units(self.scenario(directory, True))]
        native = {kind: [row for row in records if row[3] == kind] for kind in (131, 142, 42)}
        self.assertEqual([len(native[kind]) for kind in (131, 142, 42)], [1, 1, 1])
        self.assertTrue(all(row[7] == 0 for values in native.values() for row in values))
        self.assertEqual([native[131][0][1:3], native[142][0][1:3], native[42][0][1:3]],
                         [(8 * 32 + 96 * 32 + 64, 31 * 32 + 96 * 32 + 48),
                          (13 * 32 + 96 * 32 + 48, 32 * 32 + 96 * 32 + 32),
                          (16 * 32 + 96 * 32 + 16, 34 * 32 + 96 * 32 + 16)])

    def test_blocked_colony_does_not_create_native_units(self):
        with tempfile.TemporaryDirectory() as directory:
            records = [UNIT.unpack(row) for row in maps.scenario_units(self.scenario(directory, False))]
        self.assertFalse(any(row[3] in (131, 142, 42) for row in records))


if __name__ == "__main__":
    unittest.main()
