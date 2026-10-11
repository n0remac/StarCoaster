import json
import importlib.util
from pathlib import Path
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "run-data/generated-assets/starcraft/zergling/manifest.json"
MARINE_MANIFEST = ROOT / "run-data/generated-assets/starcraft/marine/manifest.json"


class SpriteRegistryTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / "upstream/openrct2/src/openrct2/drawing/ImageImporter.h").is_file(),
                         "pinned OpenRCT2 checkout is not installed")
    def test_public_marine_placeholder_and_native_asset_version(self):
        installer = ROOT / "scripts/install-bridge-sprites.py"
        spec = importlib.util.spec_from_file_location("bridge_sprites", installer)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        upstream = ROOT / "upstream/openrct2"
        colours = module.standard_colours(upstream)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            module.placeholder_marine(destination, upstream)
            self.assertEqual(len(module.MARINE_NAMES), 56)
            self.assertEqual(len(list(destination.glob("*.png"))), 56)
            self.assertIn("CC0", (destination / "LICENSE.txt").read_text())
            for name in module.MARINE_NAMES:
                with Image.open(destination / name) as image:
                    self.assertEqual(image.mode, "RGBA")
                    self.assertIsNotNone(image.getchannel("A").getbbox())
                    self.assertTrue(all(tuple(pixel[:3]) in colours for pixel in image.getdata() if pixel[3]))
        native = (upstream / "src/openrct2/scripting/ScriptEngine.cpp").read_text()
        plugin = (ROOT / "openrct2-plugin/rts-bridge.js").read_text()
        self.assertIn('"version", JS_NewInt32(ctx, 4)', native)
        self.assertIn('"assetVersion", JS_NewInt32(ctx, 3)', native)
        self.assertIn('rtsBridge.version !== 4', plugin)
        self.assertIn('rtsBridge.assetVersion !== 3', plugin)

    @unittest.skipUnless(MANIFEST.is_file(), "local licensed sprites have not been prepared")
    def test_verified_walk_groups_and_mirror_anchors(self):
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(len(manifest["frames"]), 136)
        self.assertEqual([group["classification"] for group in manifest["source_groups"][:11]],
                         ["idle"] + ["walk"] * 10)
        self.assertEqual([group["classification"] for group in manifest["source_groups"][11:17]], ["death"] * 6)
        self.assertEqual(len(manifest["registry"]["alien_scout"]["walk"]["frames"]), 8)
        self.assertEqual(len(manifest["registry"]["alien_scout"]["death"]["frames"]["east"]), 6)
        for motion in ("idle", *(f"walk{index}" for index in range(10)), *(f"death{index}" for index in range(6))):
            for east, west in (("east", "west"), ("southeast", "southwest"),
                               ("northeast", "northwest")):
                a = manifest["frames"][f"{motion}_{east}.png"]
                b = manifest["frames"][f"{motion}_{west}.png"]
                self.assertEqual(a["source_frame"], b["source_frame"])
                self.assertEqual(a["x"] + b["x"] + a["width"], 0,
                                 "flipped crop must reverse x offset about the 128-pixel canvas centre")

    @unittest.skipUnless(MARINE_MANIFEST.is_file(), "local Marine art has not been prepared")
    def test_marine_animation_registry_and_anchors(self):
        manifest = json.loads(MARINE_MANIFEST.read_text())
        self.assertEqual(manifest["unit"], "marine")
        self.assertEqual(manifest["source"], "unit/terran/marine.grp")
        self.assertEqual(len(manifest["frames"]), 56)
        states = manifest["registry"]["terran_marine"]
        self.assertEqual({key: len(value["frames"]["east"]) for key, value in states.items()
                          if key != "death"}, {"idle": 1, "walk": 2, "attack": 3})
        self.assertEqual(len(states["death"]["frames"]), 8)
        for state, count in (("idle", 1), ("walk", 2), ("attack", 3)):
            for direction, frames in states[state]["frames"].items():
                self.assertEqual(len(frames), count)
                for name in frames:
                    meta = manifest["frames"][name]
                    self.assertGreater(meta["visible_pixels"], 0)
                    self.assertTrue((ROOT / "run-data/generated-assets/starcraft/marine" / name).is_file())
            for pose in range(count):
                east = manifest["frames"][f"{state}{pose}_east.png"]
                west = manifest["frames"][f"{state}{pose}_west.png"]
                self.assertEqual(east["source_frame"], west["source_frame"])
                self.assertEqual(east["x"] + west["x"] + east["width"], 0)


if __name__ == "__main__":
    unittest.main()
