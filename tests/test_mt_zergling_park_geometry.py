"""Package edge placement and optional checks against the local authored park."""

from collections import deque
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios/mt-zergling/scenario.json"
PARK_DETAIL = ROOT / "run-data/mt-zergling/inspection/detail.json"


class MtZerglingGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = json.loads(SCENARIO.read_text())

    @classmethod
    def largest_wave(cls):
        defense = cls.scenario["park_defense"]
        return max((sum(group["count"] for group in tier["groups"])
                    for tier in defense.get("wave_tiers", [])),
                   default=defense.get("units_per_wave", 0))

    def test_authored_structures_are_clear_perimeter_footprints(self):
        catalog = {item["id"]: item for item in json.loads(
            (ROOT / "bridge-protocol/starcraft-types.json").read_text())["buildings"]}
        structures = self.scenario["initial_structures"]
        self.assertEqual({item["type"] for item in structures},
                         {"zerg_hatchery", "zerg_spawning_pool"})
        self.assertEqual(len({item["id"] for item in structures}), len(structures))
        width, height = self.scenario["park_size"]
        spawns = {tuple(tile) for zone in self.scenario["spawn_zones"].values()
                  for tile in zone["tiles"]}
        occupied = set()
        for item in structures:
            self.assertEqual(item["faction"], "zerg")
            building = catalog[item["type"]]
            x, y = item["tile"]
            cells = {(x + dx, y + dy) for dx in range(building["width"])
                     for dy in range(building["height"])}
            self.assertTrue(all(8 <= cx < width - 8 and 8 <= cy < height - 8
                                for cx, cy in cells))
            self.assertTrue(all(min(cx, cy, width - 1 - cx, height - 1 - cy) <= 12
                                for cx, cy in cells))
            self.assertFalse(cells & (spawns | occupied))
            occupied |= cells
        if PARK_DETAIL.is_file():
            detail = json.loads(PARK_DETAIL.read_text())
            terrain = {(tile["x"], tile["y"]): tile for tile in detail["terrain"]}
            obstructions = {(item["x"], item["y"])
                            for kind in ("scenery", "paths", "entrances")
                            for item in detail[kind]}
            self.assertFalse(occupied & obstructions)
            for item in structures:
                building = catalog[item["type"]]
                x, y = item["tile"]
                heights = {terrain[x + dx, y + dy]["z"]
                           for dx in range(building["width"])
                           for dy in range(building["height"])}
                self.assertEqual(len(heights), 1)

    def test_each_edge_has_reusable_capacity(self):
        width, height = self.scenario["park_size"]
        zones = self.scenario["spawn_zones"]
        self.assertEqual(set(zones), {"north", "south", "east", "west"})
        for side, zone in zones.items():
            tiles = {tuple(tile) for tile in zone["tiles"]}
            self.assertGreaterEqual(len(tiles), 4 * self.largest_wave())
            for x, y in tiles:
                self.assertTrue(8 <= x < width - 8 and 8 <= y < height - 8)
                self.assertTrue({"north": y <= 14, "south": y >= height - 14,
                                 "west": x <= 14, "east": x >= width - 14}[side],
                                f"{side}: {(x, y)} is not at the map edge")

    @unittest.skipUnless(PARK_DETAIL.is_file(), "local OpenRCT2 park inspection unavailable")
    def test_edges_reach_marine_plateau_on_authored_terrain(self):
        detail = json.loads(PARK_DETAIL.read_text())
        heights = {(tile["x"], tile["y"]): tile["z"] for tile in detail["terrain"]}
        # OpenRCT2 owns the terrain. Check connectivity through its inspected
        # heights; the native navigation test remains the final route check.
        start = tuple(self.scenario["starting_units"]["marines"][0])
        visited = {start}
        pending = deque([start])
        while pending:
            x, y = pending.popleft()
            for next_tile in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if (next_tile in heights and next_tile not in visited
                        and abs(heights[next_tile] - heights[x, y]) <= 2):
                    visited.add(next_tile)
                    pending.append(next_tile)
        scenery = {(item["x"], item["y"]) for item in detail["scenery"]}
        for side, zone in self.scenario["spawn_zones"].items():
            clear = {tuple(tile) for tile in zone["tiles"]} - scenery
            self.assertGreaterEqual(len(clear & visited), 4 * self.largest_wave(),
                                    f"{side} lacks enough clear connected terrain tiles")


if __name__ == "__main__":
    unittest.main()
