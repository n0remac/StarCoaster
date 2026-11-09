"""StarCraft scenery stays registered to park tiles through camera rotations."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "building_objects", ROOT / "scripts/install-starcraft-construction-object.py")
objects = importlib.util.module_from_spec(spec)
spec.loader.exec_module(objects)


def project(x, y, rotation):
    # OpenRCT2 CoordsXY.rotate and Translate3DTo2DWithZ at z=0.
    if rotation == 1:
        x, y = y, -x
    elif rotation == 2:
        x, y = -x, -y
    elif rotation == 3:
        x, y = -y, x
    return y - x, (x + y) // 2


class BuildingObjectProjectionTest(unittest.TestCase):
    def test_sprite_anchor_keeps_world_offset_from_park_building(self):
        rides = json.loads((ROOT / "scenarios/midway-junction/park-layout.json").read_text())["rides"]
        burger = next(ride for ride in rides if ride["id"] == "north-burgers")
        reference = (burger["x"] * 32 + 16, burger["y"] * 32 + 16)
        catalog = json.loads((ROOT / "bridge-protocol/starcraft-types.json").read_text())
        visuals = json.loads((ROOT / "bridge-protocol/starcraft-visuals.json").read_text())["buildings"]
        origin_tile = (36, 21)
        for building in catalog["buildings"]:
            kind = building["id"]
            if kind not in visuals:
                continue
            width, height = building["width"], building["height"]
            sprite_width, sprite_height = visuals[kind]["output_size"]
            fixed_centre = (origin_tile[0] * 32 + width * 16,
                            origin_tile[1] * 32 + height * 16)
            for rotation in range(4):
                with self.subTest(building=kind, rotation=rotation):
                    tile_x, tile_y = project(origin_tile[0] * 32, origin_tile[1] * 32,
                                             rotation)
                    image_x, image_y = objects.sprite_origin(
                        width, height, sprite_width, sprite_height, rotation)
                    painted_anchor = (tile_x + image_x + sprite_width // 2,
                                      tile_y + image_y + sprite_height)
                    ride_x, ride_y = project(*reference, rotation)
                    building_x, building_y = project(*fixed_centre, rotation)
                    self.assertEqual((painted_anchor[0] - ride_x,
                                      painted_anchor[1] - ride_y),
                                     (building_x - ride_x,
                                      building_y - ride_y + (width + height) * 8))

    def test_installed_multitile_images_share_the_fixed_anchor(self):
        for kind in ("zerg_hatchery", "zerg_spawning_pool"):
            with self.subTest(building=kind), tempfile.TemporaryDirectory() as temp:
                size = tuple(objects.BUILDING_OBJECTS[kind]["output_size"])
                sprite = Image.new("P", size, 1)
                with patch.object(objects, "building_images", return_value=[sprite]), \
                        patch.object(objects, "construction_images", return_value=[]):
                    path = objects.install(Path(temp), Path(temp), kind)
                with zipfile.ZipFile(path) as archive:
                    images = json.loads(archive.read("object.json"))["images"]
                width = objects.TYPE_DEFINITIONS[kind]["width"]
                height = objects.TYPE_DEFINITIONS[kind]["height"]
                for y in range(height):
                    for x in range(width):
                        for rotation in range(4):
                            image = images[4 + (y * width + x) * 4 + rotation]
                            tile_x, tile_y = project(x * 32, y * 32, rotation)
                            self.assertEqual((tile_x + image["x"], tile_y + image["y"]),
                                             objects.sprite_origin(width, height, *size, rotation))


if __name__ == "__main__":
    unittest.main()
