"""Navigation geometry checks against the packaged Frontier park export."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "run-data/frontier-playable"
sys.path.insert(0, str(ROOT / "scripts"))
from park_navigation import ParkGrid, Point  # noqa: E402


class ParkNavigationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = DATA / "fixture.json"
        current = json.loads(fixture.read_text()) if fixture.is_file() else {}
        if current.get("layout_version") != 4:
            subprocess.run(["python3", "scripts/create-park-assault.py", "--playable"],
                           cwd=ROOT, check=True, stdout=subprocess.DEVNULL)

    def grid(self):
        return ParkGrid.load(DATA / "navigation-elements.json", DATA / "fixture.json")

    def test_routes_to_every_target_clear_obstacles_and_avoid_footprints(self):
        grid = self.grid()
        start = Point(15 * 32 + 16, 30 * 32 + 16)
        for target_id, target in grid.targets.items():
            with self.subTest(target=target_id):
                path = grid.route_to_target(start, target_id)
                self.assertGreaterEqual(len(path), 2)
                self.assertTrue(all(grid.line_clear(grid.cell(a), grid.cell(b))
                                    for a, b in zip(path, path[1:])))
                self.assertIn(grid.cell(path[-1]), grid.attack_cells(target_id))
                footprint = {(tile["x"], tile["y"]) for tile in target["tiles"]}
                self.assertNotIn((path[-1].x // 32, path[-1].y // 32), footprint)

    def test_wall_requires_detour_and_clearance(self):
        grid = self.grid()
        start, finish = Point(25 * 32 + 16, 25 * 32 + 16), Point(31 * 32 + 16, 25 * 32 + 16)
        self.assertFalse(grid.line_clear(grid.cell(start), grid.cell(finish)))
        detour = grid.route(start, {grid.cell(finish)})
        self.assertGreater(len(detour), 2)
        self.assertTrue(all(grid.line_clear(grid.cell(a), grid.cell(b))
                            for a, b in zip(detour, detour[1:])))
        near = [cell for cell, raw in grid.raw.items() if raw["walkable"] and not grid.clear[cell]
                and any(grid.raw.get((cell[0] + dx, cell[1] + dy), {}).get("classification") == "wall"
                        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)))]
        self.assertGreater(len(near), 100)
        self.assertTrue(all(not grid.passable(cell) for cell in near))

    def test_confirmed_demolition_changes_only_one_footprint(self):
        grid = self.grid()
        carousel = {(tile["x"], tile["y"]) for tile in grid.targets["carousel-1"]["tiles"]}
        ride = {(tile["x"], tile["y"]) for tile in grid.targets["ride-2"]["tiles"]}
        update = grid.clear_target("carousel-1", 1)
        self.assertEqual(update["revision"], 2)
        self.assertTrue(update["changed_cells"])
        self.assertTrue(all(grid.raw[(x * 4 + 2, y * 4 + 2)]["walkable"] for x, y in carousel))
        self.assertTrue(all(not grid.raw[(x * 4 + 2, y * 4 + 2)]["walkable"] for x, y in ride))
        with self.assertRaises(ValueError):
            grid.clear_target("ride-2", 1)
        with self.assertRaises(ValueError):
            grid.clear_target("carousel-1", 2)

    def test_corrupt_footprint_and_transform_are_rejected(self):
        grid = self.grid()
        for change in (lambda target: target["structure_center"].__setitem__("x", 624),
                       lambda target: target["footprint_tiles"].append({"x": 9, "y": 9}),
                       lambda target: target["proxy_world"].__setitem__("y", 688)):
            fixture = copy.deepcopy(grid.fixture)
            change(fixture["targets"][1])
            with self.assertRaises(ValueError):
                ParkGrid(grid.export, fixture)
        fixture = copy.deepcopy(grid.fixture)
        fixture["transform"]["x"] += 1
        with self.assertRaises(ValueError):
            ParkGrid(grid.export, fixture)


if __name__ == "__main__":
    unittest.main()
