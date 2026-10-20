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
            self.assertTrue(definition["park_defense"]["manual_activation"])
            self.assertTrue(definition["park_defense"]["fixed_spawn"])
            self.assertTrue(definition["unlimited_resources"])
            self.assertEqual([tier["from_wave"] for tier in definition["park_defense"]["wave_tiers"]], [1, 3, 6])

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
                with patch.object(scenario_package, "inspect_existing_park", return_value=(64, 64)) as inspect:
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
