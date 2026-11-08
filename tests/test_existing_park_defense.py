import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
import sys
sys.path.insert(0, str(SCRIPTS))
import prepare_existing_defense
import scenario_package


class ExistingParkDefenseTest(unittest.TestCase):
    def test_ordinary_park_uses_finite_native_economy_without_hidden_supply(self):
        class Inspection:
            economy_layout = {"policy_version": 2, "state": "ready", "seed": "source-a",
                "candidates_checked": 100, "route_checks": 1,
                "starting_entities": [
                    {"id": "base", "type": "terran_command_center", "tile": [20, 8]},
                    *[{"id": f"worker-{letter}", "type": "terran_scv", "tile": [25 + i % 2, 10 + i // 2]}
                      for i, letter in enumerate("abcd")],
                    *[{"id": f"mineral-{letter}", "type": "mineral_field", "tile": [28 + 3 * (i % 3), 9 + 4 * (i // 3)], "amount": 1500}
                      for i, letter in enumerate("abcdef")],
                    {"id": "geyser", "type": "vespene_geyser", "tile": [38, 9], "amount": 5000}],
                "defense_sites": [], "enemy_base": {"policy_version": 1, "state": "ready",
                    "structures": [
                        {"id": "enemy-hatchery", "type": "zerg_hatchery", "tile": [8, 31]},
                        {"id": "enemy-spawning-pool", "type": "zerg_spawning_pool", "tile": [13, 32]}],
                    "supply_tile": [16, 34], "assembly_tile": [12, 35],
                    "approach_tile": [12, 38], "terran_approach_tile": [24, 18]}}
            def __iter__(self):
                return iter((64, 64))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "ordinary.park"
            source.write_bytes(b"PARKsource bytes")
            with patch.object(prepare_existing_defense, "ROOT", root), \
                    patch.object(prepare_existing_defense, "inspect_existing_park", return_value=Inspection()):
                plan = prepare_existing_defense.prepare(str(source))
            scenario = json.loads(Path(plan["scenario"]).read_text())
            self.assertEqual(source.read_bytes(), b"PARKsource bytes")
            self.assertFalse(scenario.get("unlimited_resources", False))
            self.assertFalse(scenario.get("production_fixture"))
            self.assertEqual(scenario["economy"]["mode"], "finite")
            self.assertEqual(scenario["economy"]["layout_policy"], "generated")
            self.assertEqual(scenario["economy"]["layout_state"], "ready")
            self.assertEqual(scenario["economy"]["initial_balances"], {"minerals": 50, "gas": 0})
            self.assertGreaterEqual(scenario["park_defense"]["initial_delay_frames"], 7200)
            self.assertEqual([item["type"] for item in scenario["initial_structures"]],
                             ["terran_command_center", "zerg_hatchery", "zerg_spawning_pool"])
            self.assertEqual(scenario["enemy_base"]["layout_state"], "ready")
            self.assertEqual(scenario["park_defense"]["spawn_policy"], "base_production")

    def test_creates_private_package_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "Saved Park.park"
            original.write_bytes(b"PARK" + b"original park content")
            before = original.read_bytes()
            with patch.object(prepare_existing_defense, "ROOT", root), \
                    patch.object(prepare_existing_defense, "inspect_existing_park", return_value=(192, 128)):
                plan = prepare_existing_defense.prepare(str(original))
            definition = json.loads(Path(plan["scenario"]).read_text())
            self.assertEqual(original.read_bytes(), before)
            self.assertEqual(Path(plan["source"]).read_bytes(), before)
            self.assertNotEqual(Path(plan["source"]), original)
            self.assertEqual(definition["park_size"], [192, 128])
            self.assertEqual(definition["starting_units"], {"marines": [], "zerglings": []})
            self.assertEqual(definition["spawn_zones"], {})
            self.assertEqual(definition["park_defense"]["spawn_policy"], "base_production")
            self.assertEqual(definition["enemy_base"]["layout_state"], "blocked")
            self.assertFalse(definition["park_defense"].get("manual_activation", False))
            self.assertFalse(definition["park_defense"].get("fixed_spawn", False))
            self.assertFalse(definition.get("unlimited_resources", False))
            self.assertFalse(definition.get("production_fixture"))
            self.assertEqual(definition["economy"]["layout_state"], "blocked")
            self.assertEqual(definition["economy"]["blocked_reason"], "economy_geometry_unavailable")
            self.assertEqual([tier["from_wave"] for tier in definition["park_defense"]["wave_tiers"]], [1])

    def test_rejects_oversized_map(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "too-large.park"
            source.write_bytes(b"PARK")
            with patch.object(prepare_existing_defense, "inspect_existing_park", return_value=(257, 200)):
                with self.assertRaisesRegex(ValueError, "256x256"):
                    prepare_existing_defense.prepare(str(source))

    def test_managed_source_reuses_exact_inspection_only_while_bytes_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "existing.park"
            source.write_bytes(b"PARKoriginal")
            with patch.object(prepare_existing_defense, "ROOT", root), \
                    patch.object(scenario_package, "ROOT", root), \
                    patch.object(prepare_existing_defense, "inspect_existing_park", return_value=(64, 64)):
                plan = prepare_existing_defense.prepare(str(source))
                def stage(command, **_kwargs):
                    Path(command[3]).write_bytes(Path(command[2]).read_bytes())
                with patch.object(scenario_package, "inspect_existing_park", return_value=(64, 64)) as inspect, \
                        patch.object(scenario_package.subprocess, "run", side_effect=stage):
                    scenario_package.ensure_park(plan)
                    inspect.assert_not_called()
                    Path(plan["source"]).write_bytes(b"PARKchanged!")
                    scenario_package.ensure_park(plan, force=True)
                    inspect.assert_called_once_with(Path(plan["source"]))

    def test_preserves_stock_scenario_and_save_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(prepare_existing_defense, "ROOT", root), \
                    patch.object(prepare_existing_defense, "inspect_existing_park", return_value=(128, 128)):
                for suffix in (".SC6", ".SV6", ".sc4", ".sv4"):
                    source = root / f"existing{suffix}"
                    source.write_bytes(b"source data")
                    plan = prepare_existing_defense.prepare(str(source))
                    self.assertEqual(Path(plan["park"]).suffix, suffix.lower())
                    self.assertEqual(Path(plan["source"]).read_bytes(), source.read_bytes())
                    definition = json.loads(Path(plan["scenario"]).read_text())
                    self.assertEqual(Path(definition["park_file"]).suffix, suffix.lower())


if __name__ == "__main__":
    unittest.main()
