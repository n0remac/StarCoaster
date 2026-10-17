"""Pinned compatibility evidence captured before entity declarations were introduced."""

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads((ROOT / "tests/fixtures/starcraft_entity_baseline.json").read_text())


class EntityBaselineTests(unittest.TestCase):
    def test_catalog_semantics(self):
        expected = BASELINE["catalogs"]["starcraft-types.json"]
        actual = json.loads((ROOT / "bridge-protocol/starcraft-types.json").read_text())
        self.assertEqual(actual["units"][:len(expected["units"])], expected["units"])
        self.assertEqual(actual["buildings"], expected["buildings"])
        expected = BASELINE["catalogs"]["starcraft-visuals.json"]
        actual = json.loads((ROOT / "bridge-protocol/starcraft-visuals.json").read_text())
        self.assertEqual(actual["directions"], expected["directions"])
        for category in ("units", "buildings", "effects"):
            for ident, profile in expected[category].items():
                with self.subTest(category=category, ident=ident):
                    self.assertEqual(actual[category][ident], profile)

    def test_existing_sprite_path_indices(self):
        path = ROOT / "upstream/openrct2/resources/g2/sprites.json"
        if not path.is_file():
            self.skipTest("local OpenRCT2 G2 table unavailable")
        paths = [entry["path"] for entry in json.loads(path.read_text())]
        self.assertEqual(paths[:len(BASELINE["sprite_paths"])], BASELINE["sprite_paths"])
        self.assertEqual(len(paths), len(set(paths)))


if __name__ == "__main__":
    unittest.main()
