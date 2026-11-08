import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "upstream/openrct2/src/openrct2/paint/Paint.Entity.cpp"


class ConstructionPaintOrderTest(unittest.TestCase):
    def test_only_active_builder_uses_construction_sort_bounds(self):
        source = SOURCE.read_text()
        for required in (
            'actor.kind == "terran_scv" && actor.motion == "construct"',
            'BridgeConstructionBuilderSortZ(actorPos, z) : z + 5',
            'frame->second <= state.frames',
            'std::abs(tileZ - actorZ) <= 8',
            'sortZ = std::max(sortZ, tileZ + 48)',
            '{ -visualType->bounds[0] / 2, -visualType->bounds[1] / 2, sortZ }',
            '{ 0, 0, z }, actorBounds',
        ):
            with self.subTest(required=required):
                self.assertTrue(required in source, required)


if __name__ == "__main__":
    unittest.main()
