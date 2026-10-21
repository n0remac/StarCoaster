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
    def test_fighting_keeps_native_assault_enabled(self):
        fighting = benchmark["workload_environment"]("fighting")
        self.assertNotIn("BRIDGE_DISABLE_ASSAULT_AI", fighting)
        self.assertEqual("1", fighting["BRIDGE_TEST_ASSAULT_MARINES"])
        self.assertEqual("/tmp/release", benchmark["workload_environment"]("fighting", "/tmp/release")
                         ["BRIDGE_BENCHMARK_ASSAULT_FILE"])
        self.assertIn("BRIDGE_DISABLE_ASSAULT_AI", benchmark["workload_environment"]("idle"))

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

    def test_fighting_requires_observed_native_attacks(self):
        case = {"label":"fight","count":10,"workload":"fighting","camera":"visible",
                "paint":"normal","client":"none","measure":60,"errors":[],
                "measurement_start_pi_mono_ns":1,"measurement_end_pi_mono_ns":1000000000000}
        events = [{"case":"fight","clock_domain":"pi-monotonic","mono_ns":2,
                   "source":"openbw-publisher","stage":"snapshot_publish","seq":1,
                   "unit_attacking":0,"unit_omitted":0}]
        self.assertIn("no_native_attacks_observed", benchmark["summarize_case"](events,[],[],case)["errors"])
        events[0]["unit_attacking"] = 2
        self.assertNotIn("no_native_attacks_observed", benchmark["summarize_case"](events,[],[],case)["errors"])

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
        self.assertEqual(60, result["command_to_presented_state_ms"]["median"])

    def test_offscreen_command_keeps_long_presented_delay_distinct_from_visibility(self):
        case = {"label":"offscreen","count":25,"workload":"moving","camera":"away",
                "paint":"normal","client":"local","measure":60,"errors":[],
                "browser_window":{"start":1000,"end":100000},
                "measurement_start_pi_mono_ns":1,"measurement_end_pi_mono_ns":1000000000000}
        events = [
            {"case":"offscreen","clock_domain":"browser-monotonic","wall_ms":1001,
             "stage":"command_input","request_id":7,"mono_ms":1000},
            {"case":"offscreen","clock_domain":"pi-monotonic","stage":"command_first_movement",
             "request_id":7,"seq":9,"mono_ns":2000},
            {"case":"offscreen","clock_domain":"browser-monotonic","wall_ms":39000,
             "stage":"snapshot_present","seq":9,"mono_ns":39000000000},
        ]
        result = benchmark["summarize_case"](events,[],[],case)
        self.assertEqual(38000, result["command_to_presented_state_ms"]["median"])
        self.assertEqual(0, result["command_to_visible_ms"]["count"])

    def test_command_trace_can_span_the_warmup_window(self):
        case = {"label":"warmup","count":10,"workload":"moving","camera":"visible",
                "paint":"normal","client":"local","measure":60,"errors":[],
                "browser_window":{"start":1000,"end":2000},
                "measurement_start_pi_mono_ns":1000000000,
                "measurement_end_pi_mono_ns":2000000000}
        events = [
            {"case":"warmup","clock_domain":"browser-monotonic","wall_ms":900,
             "stage":"command_input","request_id":8,"mono_ms":900},
            {"case":"warmup","clock_domain":"pi-monotonic","mono_ns":900000000,
             "stage":"command_first_movement","request_id":8,"seq":10},
            {"case":"warmup","clock_domain":"browser-monotonic","wall_ms":1100,
             "stage":"snapshot_present","seq":10,"mono_ns":1100000000},
        ]
        result = benchmark["summarize_case"](events,[],[],case)
        self.assertEqual(200, result["command_to_visible_ms"]["median"])

    def test_delayed_browser_console_delivery_uses_native_event_time(self):
        case = {"label":"delayed","count":10,"workload":"idle","camera":"visible",
                "paint":"normal","client":"local","measure":60,"errors":[],
                "measurement_start_pi_mono_ns":1,"measurement_end_pi_mono_ns":1000000000000,
                "browser_window":{"start":1000,"end":2000,"mono_start":1000,"mono_end":2000}}
        events = [{"case":"delayed","clock_domain":"browser-monotonic","wall_ms":3000,
                   "source":"openrct2","role":"browser-client","stage":"present_summary",
                   "mono_ns":1500000000,"frames":30,"elapsed_ns":1000000000},
                  {"case":"delayed","clock_domain":"pi-monotonic","mono_ms":2000000,
                   "source":"openrct2-plugin","stage":"tick_summary","mode":"server",
                   "ticks":40,"elapsed_ms":1000}]
        result = benchmark["summarize_case"](events,[],[],case)
        self.assertEqual(30, result["client_fps"]["median"])
        self.assertEqual(0, result["server_tick_rate"]["count"])

    def test_client_fps_includes_seconds_without_presented_frames(self):
        case = {"label":"stalled","count":25,"workload":"idle","camera":"visible",
                "paint":"normal","client":"local","measure":60,"errors":[],
                "measurement_start_pi_mono_ns":1,"measurement_end_pi_mono_ns":60000000001,
                "browser_window":{"start":1000,"end":61000,"mono_start":1000,"mono_end":61000}}
        events = [{"case":"stalled","clock_domain":"browser-monotonic","wall_ms":2000,
                   "source":"openrct2","role":"browser-client","stage":"present_summary",
                   "mono_ns":2000000000,"frames":30,"elapsed_ns":1000000000}]
        result = benchmark["summarize_case"](events,[],[],case)
        self.assertEqual(.5, result["client_fps"]["median"])
        self.assertEqual(30, result["client_fps_active_windows"]["median"])

    def test_overhead_pair_compares_matching_workloads(self):
        template = {"count":50,"workload":"fighting","camera":"visible","paint":"normal",
                    "client":"local","valid":True}
        baseline = {**template,"label":"u50-fighting-visible-normal-local-r1-baseline",
                    "diagnostic_level":"baseline","openbw_frame_work_p95_ms_windows":{"median":2.0}}
        full = {**template,"label":"u50-fighting-visible-normal-local-r1-full",
                "diagnostic_level":"full","openbw_frame_work_p95_ms_windows":{"median":2.08}}
        pairs = benchmark["overhead_pairs"]([baseline,full])
        self.assertEqual(1, len(pairs))
        self.assertEqual(4, pairs[0]["overhead_percent"])
        self.assertTrue(pairs[0]["within_five_percent_target"])


if __name__ == "__main__": unittest.main()
