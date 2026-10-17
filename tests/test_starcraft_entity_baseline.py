"""Pinned compatibility evidence captured before entity declarations were introduced."""

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads((ROOT / "tests/fixtures/starcraft_entity_baseline.json").read_text())


class EntityBaselineTests(unittest.TestCase):
    def test_catalog_semantics(self):
        for name, expected in BASELINE["catalogs"].items():
            with self.subTest(name=name):
                actual = json.loads((ROOT / "bridge-protocol" / name).read_text())
                self.assertEqual(actual, expected)

    def test_generated_language_and_protocol_bytes(self):
        for name, expected in BASELINE["generated_sha256"].items():
            with self.subTest(name=name):
                actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                self.assertEqual(actual, expected)

    def test_existing_sprite_path_indices(self):
        path = ROOT / "upstream/openrct2/resources/g2/sprites.json"
        if not path.is_file():
            self.skipTest("local OpenRCT2 G2 table unavailable")
        paths = [entry["path"] for entry in json.loads(path.read_text())]
        self.assertEqual(paths[:len(BASELINE["sprite_paths"])], BASELINE["sprite_paths"])
        self.assertEqual(len(paths), len(set(paths)))


if __name__ == "__main__":
    unittest.main()
