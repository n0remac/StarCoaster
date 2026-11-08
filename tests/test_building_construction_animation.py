"""Focused checks for native-progress construction sprite banks."""

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BuildingConstructionAnimationTest(unittest.TestCase):
    def test_supported_buildings_declare_construction_art(self):
        catalog = json.loads((ROOT / "bridge-protocol/starcraft-types.json").read_text())
        for building in catalog["buildings"]:
            with self.subTest(building=building["id"]):
                self.assertIn("construction", building)
                self.assertGreaterEqual(len(building["construction"]["frames"]), 3)

    def test_native_construction_frames_are_distinct_and_stable(self):
        spec = importlib.util.spec_from_file_location(
            "building_objects", ROOT / "scripts/install-starcraft-construction-object.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        game = Path("/home/pi/games/starcraft")
        if not game.is_dir():
            self.skipTest("local StarCraft art unavailable")
        for kind in ("terran_barracks", "zerg_hatchery"):
            with self.subTest(building=kind):
                frames = module.construction_images(game, module.TYPE_DEFINITIONS[kind],
                                                    module.BUILDING_OBJECTS[kind])
                self.assertEqual(len(frames), len(module.TYPE_DEFINITIONS[kind]["construction"]["frames"]))
                self.assertEqual(len({frame.tobytes() for frame in frames}), len(frames))
                self.assertTrue(all(frame.size == tuple(module.BUILDING_OBJECTS[kind]["output_size"])
                                    for frame in frames))
