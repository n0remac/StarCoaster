import json
import copy
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from park_navigation import ParkGrid, Point  # noqa: E402


DATA = ROOT / "run-data/park-assault"


class ParkAssaultNavigationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DATA / "navigation-elements.json").is_file():
            subprocess.run(["python3", "scripts/create-park-assault.py"], cwd=ROOT, check=True)
        if not (DATA / "map/park-assault.json").is_file():
            subprocess.run(["python3", "scripts/create-park-assault-map.py"], cwd=ROOT, check=True)
        cls.manifest = json.loads((DATA / "map/park-assault.json").read_text())

    def grid(self, radius=24):
        return ParkGrid.load(DATA / "navigation-elements.json", DATA / "fixture.json", radius)

    def test_all_twenty_start_to_exterior_attack_routes_clear_obstacles(self):
        grid = self.grid()
        assignment = {"alpha": "carousel-1", "beta": "shop-1", "gamma": "ride-2"}
        counts = {key: 0 for key in assignment}
        for unit in self.manifest["zerglings"]:
            counts[unit["squad"]] += 1
            target_id = assignment[unit["squad"]]
            path = grid.route_to_target(Point(unit["park_x"], unit["park_y"]), target_id)
            self.assertGreaterEqual(len(path), 2)
            self.assertTrue(all(grid.line_clear(grid.cell(a), grid.cell(b))
                                for a, b in zip(path, path[1:])))
            last = grid.cell(path[-1])
            self.assertIn(last, grid.attack_cells(target_id))
            occupied = {(tile["x"], tile["y"]) for tile in grid.targets[target_id]["tiles"]}
            self.assertNotIn((path[-1].x // 32, path[-1].y // 32), occupied)
        self.assertEqual(counts, {"alpha": 8, "beta": 6, "gamma": 6})

    def test_direct_wall_crossing_rejected_and_clearance_excludes_near_wall_cells(self):
        grid = self.grid()
        # This line crosses the real long wall placed on tile x=28.
        start, finish = Point(25 * 32 + 16, 25 * 32 + 16), Point(31 * 32 + 16, 25 * 32 + 16)
        self.assertFalse(grid.line_clear(grid.cell(start), grid.cell(finish)))
        detour = grid.route(start, {grid.cell(finish)})
        self.assertGreater(len(detour), 2)
        self.assertTrue(all(grid.line_clear(grid.cell(a), grid.cell(b))
                            for a, b in zip(detour, detour[1:])))
        self.assertTrue(min(point.y for point in detour) < finish.y - 200
                        or max(point.y for point in detour) > finish.y + 200)
        near = [cell for cell, raw in grid.raw.items() if raw["walkable"] and not grid.clear[cell]
                and any(grid.raw.get((cell[0] + dx, cell[1] + dy), {}).get("classification") == "wall"
                        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)))]
        self.assertGreater(len(near), 100)
        self.assertTrue(all(not grid.passable(cell) for cell in near))

    def test_confirmed_demolition_updates_only_target_footprint_and_revision(self):
        grid = self.grid()
        carousel = {(tile["x"], tile["y"]) for tile in grid.targets["carousel-1"]["tiles"]}
        ride = {(tile["x"], tile["y"]) for tile in grid.targets["ride-2"]["tiles"]}
        self.assertTrue(all(grid.raw[(x * 4 + 2, y * 4 + 2)]["classification"] == "structure"
                            for x, y in carousel | ride))
        update = grid.clear_target("carousel-1", 1)
        self.assertEqual(update["revision"], 2)
        self.assertTrue(update["changed_cells"])
        self.assertTrue(all(grid.raw[(x * 4 + 2, y * 4 + 2)]["walkable"] for x, y in carousel))
        self.assertTrue(all(not grid.raw[(x * 4 + 2, y * 4 + 2)]["walkable"] for x, y in ride))
        with self.assertRaises(ValueError):
            grid.clear_target("shop-1", 1)
        with self.assertRaises(ValueError):
            grid.clear_target("carousel-1", 2)

    def test_coordinate_transform_is_shared_with_openbw_fixture(self):
        grid = self.grid()
        self.assertEqual(grid.fixture["transform"], self.manifest["transform"])
        compact = (DATA / "navigation.grid").read_text().splitlines()
        self.assertEqual(int(compact[0].split()[-1]), len(grid.targets))
        self.assertEqual(sum(line.startswith("TARGET ") for line in compact), len(grid.targets))
        for unit in self.manifest["zerglings"]:
            self.assertEqual(unit["park_x"], unit["bw_x"] + grid.fixture["transform"]["x"])
            self.assertEqual(unit["park_y"], unit["bw_y"] + grid.fixture["transform"]["y"])
        self.assertEqual(compact[0].split()[1], "2")
        for target in grid.targets.values():
            center = target["structure_center"]
            self.assertEqual(center, target["proxy_world"])
            proxy = next(row for row in self.manifest["proxies"] if row["target_id"] == target["id"])
            self.assertEqual(proxy["ride_id"], target["ride_id"])
            self.assertEqual(proxy["park_world"], center)
            for axis in ("x", "y"):
                self.assertEqual(proxy["bw_world"][axis] + grid.fixture["transform"][axis], center[axis])
            occupied = {(tile["x"], tile["y"]) for tile in target["footprint_tiles"]}
            self.assertTrue(target["attack_approaches"])
            for approach in target["attack_approaches"]:
                self.assertNotIn((approach["x"] // 32, approach["y"] // 32), occupied)
                self.assertIn(grid.cell(Point(**approach)), grid.attack_cells(target["id"]))

    def test_incorrect_structure_center_footprint_and_transform_are_rejected(self):
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
