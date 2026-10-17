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

    def test_rejects_invalid_extensions(self):
        invalid = copy.deepcopy(self.catalog)
        invalid["buildings"][0]["production"] = ["terran_firebat"]
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


if __name__ == "__main__":
    unittest.main()
