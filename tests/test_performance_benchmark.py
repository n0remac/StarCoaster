"""Guard the benchmark's native population and invalid-result rules."""

import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
benchmark = runpy.run_path(str(ROOT / "scripts/benchmark-gameplay-performance.py"))


class PerformanceBenchmarkTest(unittest.TestCase):
    def test_population_matrix_uses_distinct_native_start_tiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            for count in (0, 10, 25, 50, 100, 200):
                path = benchmark["fixture"](count, "idle", Path(temporary) / f"{count}.json", "park.park")
                scenario = json.loads(path.read_text())
                tiles = scenario["starting_units"]["marines"] + scenario["starting_units"]["zerglings"]
                self.assertEqual(count, len(tiles))
                self.assertEqual(count, len({tuple(tile) for tile in tiles}))
                self.assertLessEqual(len(scenario["starting_units"]["marines"]), 256)
                self.assertLessEqual(len(scenario["starting_units"]["zerglings"]), 256)

    def test_omitted_native_units_invalidate_case(self):
        case = {"label":"u200-fighting-visible-normal-none-r1","count":200,"workload":"fighting",
                "camera":"visible","paint":"normal","client":"none","measure":60,"errors":[],
                "measurement_start_pi_mono_ns":100,"measurement_end_pi_mono_ns":1000000}
        events = [{"case":case["label"],"clock_domain":"pi-monotonic","mono_ns":200,
                   "source":"openbw-publisher","stage":"snapshot_publish","seq":1,
                   "bytes":90000,"unit_omitted":1},
                  {"case":case["label"],"clock_domain":"pi-monotonic","mono_ns":300,
                   "source":"openbw-publisher","stage":"frame_summary","frames":24,
                   "elapsed_ns":1000000000}]
        result = benchmark["summarize_case"](events,[],[],case)
        self.assertFalse(result["valid"])
        self.assertIn("snapshot_omitted_units", result["errors"])

    def test_pi_and_browser_clocks_are_not_subtracted_directly(self):
        case = {"label":"remote","count":10,"workload":"moving","camera":"visible","paint":"normal",
                "client":"remote","measure":60,"errors":[],"browser_window":{"start":1000,"end":5000},
                "measurement_start_pi_mono_ns":1,"measurement_end_pi_mono_ns":1000000000000}
        events = [
            {"case":"remote","clock_domain":"browser-monotonic","wall_ms":2000,
             "stage":"command_input","request_id":7,"mono_ms":200},
            {"case":"remote","clock_domain":"pi-monotonic","stage":"command_first_movement",
             "request_id":7,"seq":9,"mono_ns":999999999999},
            {"case":"remote","clock_domain":"browser-monotonic","wall_ms":2500,
             "stage":"snapshot_present","seq":9,"mono_ns":260000000},
        ]
        result = benchmark["summarize_case"](events,[],[],case)
        self.assertEqual(60, result["command_to_visible_ms"]["median"])


if __name__ == "__main__": unittest.main()
