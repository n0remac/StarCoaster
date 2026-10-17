"""The static catalog must match generated consumers and native BWAPI types."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "starcraft_type_generator", ROOT / "scripts/generate-starcraft-types.py")
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class StarcraftTypeCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / "bridge-protocol/starcraft-types.json").read_text())

    def test_generated_consumers_and_native_resolution(self):
        GENERATOR.validate(self.catalog)
        GENERATOR.replace_block(ROOT / "internal/world/starcraft_types.go",
                                GENERATOR.go_definitions(self.catalog), True)
        GENERATOR.replace_block(ROOT / "openrct2-plugin/rts-bridge.js",
                                GENERATOR.javascript_definitions(self.catalog), True)
        GENERATOR.check_native(self.catalog)
        for path, rendered in GENERATOR.schema_definitions(self.catalog).items():
            GENERATOR.write_generated(path, rendered, True)
        self.assertEqual(self.catalog["units"][0]["legacy_static_base"], 1000)
        self.assertEqual(self.catalog["units"][-1]["legacy_static_base"], 2000)

    def test_rejects_invalid_extensions(self):
        invalid = copy.deepcopy(self.catalog)
        invalid["buildings"][0]["production"] = ["terran_ghost"]
        with self.assertRaises(ValueError):
            GENERATOR.validate(invalid)
        invalid = copy.deepcopy(self.catalog)
        invalid["units"].append(copy.deepcopy(invalid["units"][0]))
        with self.assertRaises(ValueError):
            GENERATOR.validate(invalid)
        invalid = copy.deepcopy(self.catalog)
        invalid["buildings"][0]["animation"]["ticks_per_frame"] = 0
        with self.assertRaises(ValueError):
            GENERATOR.validate(invalid)
        changes = (
            ("unknown native", lambda data: data["units"][0].update(native_type="Terran_Unknown")),
            ("missing visual", lambda data: data["units"][0].update(visual="missing_visual")),
            ("duplicate object", lambda data: data["buildings"][1].update(
                object_id=data["buildings"][0]["object_id"])),
            ("bad command", lambda data: data["units"][0]["commands"].append("unit.cloak")),
            ("duplicate legacy base", lambda data: data["units"][1].update(legacy_static_base=1000)),
            ("unsupported movement", lambda data: data["units"][0].update(movement="air")),
        )
        for label, change in changes:
            with self.subTest(label=label):
                invalid = copy.deepcopy(self.catalog)
                change(invalid)
                with self.assertRaises(ValueError):
                    GENERATOR.validate(invalid)


if __name__ == "__main__":
    unittest.main()
