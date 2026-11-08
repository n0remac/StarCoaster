import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "upstream/openrct2/src/openrct2/paint/Paint.Entity.cpp"
PAINT = ROOT / "upstream/openrct2/src/openrct2/paint/Paint.cpp"
SCENERY = ROOT / "upstream/openrct2/src/openrct2/paint/tile_element/Paint.LargeScenery.cpp"


class ConstructionPaintOrderTest(unittest.TestCase):
    def test_native_paint_entries_use_authoritative_construction_bank(self):
        actor = SOURCE.read_text()
        painter = PAINT.read_text()
        self.assertIn("BridgeBuildingPaintLayer", actor)
        self.assertIn("BridgeOrderConstructionLayers", painter)
        self.assertIn("BridgeBuildingPaintLayer", SCENERY.read_text())
        self.assertIn("scv->ScreenPos.x", painter)
        self.assertIn("building->ScreenPos.x", painter)
        self.assertIn("scv->Bounds.z - 5 - building->Bounds.z", painter)
        self.assertIn("{ 0, 0, z }, actorBounds", actor,
                      "sprite coordinates must stay at native elevation")


if __name__ == "__main__":
    unittest.main()
