"""Checks derived from generated OpenRCT2 elements, not layout intent."""
import copy
import contextlib
import io
import json
import math
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from park_navigation import ParkGrid, Point  # noqa: E402
from frontier_geometry import wall_edge  # noqa: E402
from scenario_package import resolve, ensure_park  # noqa: E402


class MidwayParkGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = resolve("midway-junction")
        if any(not Path(cls.plan[key]).is_file() for key in ("park", "fixture", "navigation")):
            raise unittest.SkipTest("generate Midway park before exported geometry checks")
        cls.fixture = json.loads(Path(cls.plan["fixture"]).read_text())
        cls.export = json.loads(Path(cls.plan["navigation"]).read_text())
        cls.scenario = json.loads(Path(cls.plan["scenario"]).read_text())
        cls.grid = ParkGrid(cls.export, cls.fixture)

    def test_identity_structures_and_flat_terrain(self):
        f, e = self.fixture, self.export
        self.assertEqual((f["name"], f["bounds"]), ("Midway Junction", {"min_x": 8, "min_y": 8, "max_x": 55, "max_y": 55}))
        self.assertEqual({t["name"] for t in f["targets"]},
                         {"Midway Ferris Wheel", "Junction Carousel", "Midway Burger Bar", "North Drink Stand"})
        wheel = next(t for t in f["targets"] if t["id"] == "midway-wheel")
        self.assertEqual(wheel["object_id"], "rct2.ride.fwh1")
        self.assertEqual(len(wheel["footprint_tiles"]), 4)
        self.assertTrue(all(height == 112 for row in e["elevation_rows"] for height in row))
        self.assertTrue(all(slope == 0 for row in e["slope_rows"] for slope in row))
        paths = {(v["x"], v["y"]) for v in e["elements"] if v["type"] == "footpath"}
        for t in f["targets"]:
            self.assertFalse(paths & {(q["x"], q["y"]) for q in t["footprint_tiles"]})

    def test_spawn_clearance_and_walkway_connections(self):
        sc = self.scenario
        sets = [sc["starting_units"]["marines"], sc["starting_units"]["zerglings"]]
        sets += [zone["tiles"] for zone in sc["spawn_zones"].values()]
        for tiles in sets:
            for x, y in tiles:
                self.grid.route_to_target(Point(x * 32 + 16, y * 32 + 16), "midway-wheel")
        paths = {(v["x"], v["y"]) for v in self.export["elements"] if v["type"] == "footpath"}
        remaining = set(paths); groups = []
        while remaining:
            pending = [remaining.pop()]; group = set(pending)
            while pending:
                x, y = pending.pop()
                for neighbor in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                    if neighbor in remaining:
                        remaining.remove(neighbor); group.add(neighbor); pending.append(neighbor)
            groups.append(group)
        self.assertEqual(len(groups), 1)

    def test_three_approaches_and_gate_shortcut(self):
        e = self.export
        walls = [item for item in e["elements"] if item["type"] == "wall"]
        edges = [wall_edge(wall) for wall in walls]
        self.assertEqual(len(edges), len(set(edges)))
        gate = [w for w in walls if w["object_id"] == "rct2.scenery_wall.wbr2"]
        self.assertEqual({(w["x"], w["y"], w["direction"]) for w in gate},
                         {(27, 30, 0)})
        sources = {"east": (50, 30), "north": (35, 15), "south": (37, 49)}
        routes = {}
        for direction, (x, y) in sources.items():
            routes[direction] = self.grid.route_to_target(Point(x*32+16, y*32+16), "midway-wheel")
        self.assertTrue(any(p.x//32 >= 43 and 29 <= p.y//32 <= 34 for p in routes["east"]))
        self.assertTrue(any(p.y//32 <= 24 and p.x//32 >= 40 for p in routes["north"]))
        self.assertTrue(any(p.y//32 >= 40 for p in routes["south"]))
        start = Point(22*32+16,30*32+16); goal = Point(34*32+16,30*32+16)
        def distance(grid):
            route = grid.route(start, {grid.cell(goal)}, smooth=False)
            return sum(math.dist((a.x,a.y),(b.x,b.y)) for a,b in zip(route,route[1:]))
        before = distance(ParkGrid(e, self.fixture, radius=8))
        demolished = copy.deepcopy(e)
        demolished["elements"] = [item for item in e["elements"] if item not in gate]
        after = distance(ParkGrid(demolished, self.fixture, radius=8))
        self.assertGreater(before, after * 1.8)

    @unittest.skipUnless(os.environ.get("STARCOASTER_REGENERATE_GEOMETRY") == "1",
                         "set STARCOASTER_REGENERATE_GEOMETRY=1 for live OpenRCT2 regeneration")
    def test_regeneration_has_equivalent_exported_geometry(self):
        before = copy.deepcopy(self.export)
        fixture = copy.deepcopy(self.fixture)
        with contextlib.redirect_stdout(io.StringIO()):
            ensure_park(self.plan, force=True)
        after = json.loads(Path(self.plan["navigation"]).read_text())
        later_fixture = json.loads(Path(self.plan["fixture"]).read_text())
        def normalized(export, metadata):
            names = {t["ride_id"]: t["name"] for t in metadata["targets"]}
            elements = [dict(item, ride_id=names[item["ride_id"]]) if item["type"] == "track" else item
                        for item in export["elements"]]
            return export["elevation_rows"], export["slope_rows"], sorted(json.dumps(e, sort_keys=True) for e in elements)
        self.assertEqual(normalized(before, fixture), normalized(after, later_fixture))


if __name__ == "__main__":
    unittest.main()
