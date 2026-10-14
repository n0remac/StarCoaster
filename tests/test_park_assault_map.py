import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "run-data/park-assault"


class ParkAssaultMapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DATA / "fixture.json").is_file():
            subprocess.run(["python3", "scripts/create-park-assault.py"], cwd=ROOT, check=True)
        cls.fixture = json.loads((DATA / "fixture.json").read_text())
        cls.export = json.loads((DATA / "navigation-elements.json").read_text())

    def test_real_park_assets_and_distinct_footprints(self):
        fixture = self.fixture
        self.assertEqual(fixture["name"], "Frontier Outpost")
        self.assertEqual(fixture["bounds"], {"min_x": 8, "min_y": 8, "max_x": 55, "max_y": 55})
        targets = {target["id"]: target for target in fixture["targets"]}
        self.assertEqual(set(targets), {"carousel-1", "shop-1", "ride-2"})
        self.assertEqual([targets[id]["object_id"] for id in targets],
                         ["rct2.ride.mgr1", "rct2.ride.burgb", "rct2.ride.fwh1"])
        occupied = []
        for target in targets.values():
            self.assertEqual(target["status"], "closed")
            self.assertTrue(target["empty"])
            self.assertTrue(target["tiles"])
            occupied.extend((tile["x"], tile["y"]) for tile in target["tiles"])
        self.assertEqual(len(occupied), len(set(occupied)))
        self.assertEqual(len({target["ride_id"] for target in targets.values()}), 3)
        kinds = [element["type"] for element in self.export["elements"]]
        self.assertGreaterEqual(kinds.count("footpath"), 200)
        self.assertGreaterEqual(kinds.count("wall"), 100)
        self.assertGreaterEqual(kinds.count("small_scenery"), 15)
        self.assertEqual(kinds.count("track"), len(occupied))
        self.assertTrue(all(len(row) == 48 for row in self.export["elevation_rows"]))
        paths = {(element["x"], element["y"]) for element in self.export["elements"]
                 if element["type"] == "footpath"}
        reached, frontier = {next(iter(paths))}, [next(iter(paths))]
        while frontier:
            x, y = frontier.pop()
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in paths and neighbor not in reached:
                    reached.add(neighbor)
                    frontier.append(neighbor)
        self.assertEqual(reached, paths, "the path loop and intersections should be connected")

    def test_three_independent_native_demolition_probes(self):
        if not (DATA / "demolition-probe.json").is_file():
            subprocess.run(["python3", "scripts/create-park-assault.py", "--probe-demolition"],
                           cwd=ROOT, check=True)
        probes = json.loads((DATA / "demolition-probe.json").read_text())
        self.assertEqual({row["id"] for row in probes}, {"carousel-1", "shop-1", "ride-2"})
        self.assertTrue(all(row["error"] == 0 and row["removed"] and row["after"] == 0
                            for row in probes))



if __name__ == "__main__":
    unittest.main()
