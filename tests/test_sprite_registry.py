import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "run-data/generated-assets/starcraft/zergling/manifest.json"


class SpriteRegistryTests(unittest.TestCase):
    @unittest.skipUnless(MANIFEST.is_file(), "local licensed sprites have not been prepared")
    def test_verified_walk_groups_and_mirror_anchors(self):
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(len(manifest["frames"]), 88)
        self.assertEqual([group["classification"] for group in manifest["source_groups"][:11]],
                         ["idle"] + ["walk"] * 10)
        self.assertEqual(manifest["source_groups"][11]["classification"], "non_locomotion")
        self.assertEqual(len(manifest["registry"]["alien_scout"]["walk"]["frames"]), 8)
        for motion in ("idle", *(f"walk{index}" for index in range(10))):
            for east, west in (("east", "west"), ("southeast", "southwest"),
                               ("northeast", "northwest")):
                a = manifest["frames"][f"{motion}_{east}.png"]
                b = manifest["frames"][f"{motion}_{west}.png"]
                self.assertEqual(a["source_frame"], b["source_frame"])
                self.assertEqual(a["x"] + b["x"] + a["width"], 0,
                                 "flipped crop must reverse x offset about the 128-pixel canvas centre")


if __name__ == "__main__":
    unittest.main()
