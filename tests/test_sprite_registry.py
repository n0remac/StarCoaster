import json
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "run-data/generated-assets/starcraft/zergling/manifest.json"
MARINE_MANIFEST = ROOT / "run-data/generated-assets/starcraft/marine/manifest.json"


class SpriteRegistryTests(unittest.TestCase):
    def test_barracks_light_overlay_keeps_structure_pixels(self):
        spec = importlib.util.spec_from_file_location(
            "barracks_object", ROOT / "scripts/install-starcraft-construction-object.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        idle = Image.new("RGBA", (9, 9), (40, 50, 60, 255))
        idle.putpixel((5, 5), (0, 0, 0, 0))
        animated = idle.copy()
        animated.putpixel((0, 0), (80, 70, 60, 255))  # moving leg
        animated.putpixel((4, 4), (176, 144, 24, 255))  # indicator light
        animated.putpixel((5, 4), (90, 90, 55, 255))  # light surround
        animated.putpixel((5, 5), (252, 204, 44, 255))  # changing silhouette
        output = module.light_only_frame(idle, animated)
        self.assertEqual(output.getpixel((0, 0)), idle.getpixel((0, 0)))
        self.assertEqual(output.getpixel((4, 4)), animated.getpixel((4, 4)))
        self.assertEqual(output.getpixel((5, 4)), animated.getpixel((5, 4)))
        self.assertEqual(output.getpixel((5, 5)), idle.getpixel((5, 5)))

    @unittest.skipUnless((ROOT / "run-data/generated-assets/starcraft/barracks/.source/TBarrack.grp").is_file(),
                         "local licensed Barracks art has not been extracted")
    def test_classic_barracks_training_changes_only_lights(self):
        spec = importlib.util.spec_from_file_location(
            "barracks_object", ROOT / "scripts/install-starcraft-construction-object.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        game = Path(os.environ.get("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft"))
        frames = module.barracks_images(game)
        self.assertEqual(len(frames), 8)
        self.assertTrue(all(frame.tobytes() == frames[0].tobytes() for frame in frames[1:6]))
        for frame in frames[6:]:
            difference = ImageChops.difference(frames[0].convert("RGB"), frame.convert("RGB"))
            self.assertIsNotNone(difference.getbbox())
            self.assertTrue(all(frame.getpixel((x, y)) == frames[0].getpixel((x, y))
                                for y in range(110, frame.height) for x in range(frame.width)),
                            "Barracks legs and silhouette must stay still during training")
            self.assertEqual([pixel == 0 for pixel in frame.getdata()],
                             [pixel == 0 for pixel in frames[0].getdata()])

    def test_barracks_animation_images_keep_idle_bank_and_footprint(self):
        spec = importlib.util.spec_from_file_location(
            "barracks_object", ROOT / "scripts/install-starcraft-construction-object.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        palette = [0, 0, 0] * 256
        frames = []
        for index in range(8):
            image = Image.new("P", (189, 164), index + 10)
            image.putpalette(palette)
            frames.append(image)
        with tempfile.TemporaryDirectory() as directory, patch.object(module, "barracks_images", return_value=frames):
            path = module.install(Path(directory), Path(directory))
            with zipfile.ZipFile(path) as archive:
                object_data = json.loads(archive.read("object.json"))
                images = object_data["images"]
                self.assertEqual(len(object_data["properties"]["tiles"]), 12)
                self.assertEqual(len(images), 4 + 8 * 12 * 4)
                self.assertEqual(images[4]["path"], "images/barracks-0.png")
                self.assertEqual(images[52]["path"], "images/barracks-1.png")
                self.assertEqual(images[-1]["path"], "images/barracks-7.png")
                self.assertEqual(len([name for name in archive.namelist()
                                      if name.startswith("images/barracks-")]), 8)

    def test_construction_object_supports_a_distinct_footprint(self):
        spec = importlib.util.spec_from_file_location(
            "starcraft_objects", ROOT / "scripts/install-starcraft-construction-object.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        image = Image.new("P", (40, 36), 10)
        module.TYPE_DEFINITIONS["synthetic"] = {
            "object_id": "starcoaster.scenery_large.synthetic", "display_name": "Synthetic",
            "width": 2, "height": 2,
        }
        module.BUILDING_OBJECTS["synthetic"] = {
            "frame_name": "synthetic",
            "prepare": lambda _: [image],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = module.install(Path(directory), Path(directory), "synthetic")
            with zipfile.ZipFile(path) as archive:
                definition = json.loads(archive.read("object.json"))
                self.assertEqual(definition["id"], "starcoaster.scenery_large.synthetic")
                self.assertEqual(len(definition["properties"]["tiles"]), 4)
                self.assertEqual(len(definition["images"]), 4 + 4 * 4)

    def test_extraction_accepts_archive_aliases_and_relative_paths(self):
        spec = importlib.util.spec_from_file_location("starcraft_sprites", ROOT / "scripts/prepare-starcraft-sprites.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for archives, expected in (
            (("Stardat.mpq",), "Stardat.mpq"),
            (("Broodat.mpq", "Stardat.mpq"), "Broodat.mpq"),
            (("StarDat.mpq", "Stardat.mpq"), "StarDat.mpq"),
            (("Patch_rt.mpq", "BrooDat.mpq", "StarDat.mpq"), "Patch_rt.mpq"),
        ):
            with self.subTest(archives=archives), tempfile.TemporaryDirectory() as directory:
                game = Path(directory) / "game"
                game.mkdir()
                for archive in archives:
                    (game / archive).touch()
                target = Path(directory) / "sprite.grp"
                def extract(command, cwd, **kwargs):
                    self.assertEqual(Path(command[2]), game / expected)
                    found = Path(cwd) / command[3]
                    found.parent.mkdir(parents=True, exist_ok=True)
                    found.write_bytes(b"fixture sprite")
                    return subprocess.CompletedProcess(command, 0)
                with patch.object(module.subprocess, "run", side_effect=extract):
                    self.assertEqual(module.extract(Path(os.path.relpath(game)),
                                                    "unit/terran/marine.grp", target), expected)
                self.assertEqual(target.read_bytes(), b"fixture sprite")

    @unittest.skipUnless(MANIFEST.is_file(), "local licensed sprites have not been prepared")
    def test_starcraft_pack_requires_marine_art(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source = temporary / "zergling"
            source.mkdir()
            for name in ["manifest.json", *json.loads(MANIFEST.read_text())["frames"]]:
                shutil.copyfile(MANIFEST.parent / name, source / name)
            upstream = temporary / "openrct2"
            for name in ("resources/g2/sprites.json", "src/openrct2/SpriteIds.h",
                         "src/openrct2/drawing/ImageImporter.h"):
                target = upstream / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / "upstream/openrct2" / name, target)
            result = subprocess.run([sys.executable, str(ROOT / "scripts/install-bridge-sprites.py"),
                                     str(source), str(upstream), "starcraft-local"],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing StarCraft Marine manifest", result.stderr)
            self.assertFalse((upstream / "resources/g2/bridge").exists())

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
        self.assertIn('"version", JS_NewInt32(ctx, 5)', native)
        self.assertIn('"assetVersion", JS_NewInt32(ctx, 3)', native)
        self.assertIn('rtsBridge.version !== 5', plugin)
        self.assertIn('rtsBridge.assetVersion !== 3', plugin)

    @unittest.skipUnless(MANIFEST.is_file(), "local licensed sprites have not been prepared")
    def test_verified_walk_groups_and_mirror_anchors(self):
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(len(manifest["frames"]), 136)
        self.assertEqual([group["classification"] for group in manifest["source_groups"][:11]],
                         ["idle"] + ["walk"] * 10)
        self.assertEqual([group["classification"] for group in manifest["source_groups"][11:17]], ["death"] * 6)
        registry = manifest["registry"].get("zerg_zergling") or manifest["registry"]["alien_scout"]
        self.assertEqual(len(registry["walk"]["frames"]), 8)
        self.assertEqual(len(registry["death"]["frames"]["east"]), 6)
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
