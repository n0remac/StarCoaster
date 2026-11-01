"""Safety checks for private park selection and fresh-session transitions."""

import tempfile
import unittest
import io
import json
import signal
from contextlib import contextmanager
from pathlib import Path
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from park_session_supervisor import ParkSessionSupervisor
from load_timing import LoadTiming, STAGES
from single_map_cache import SingleMapCache
import park_session_supervisor as supervisor_module
import prepare_existing_defense
import single_map_cache


class Process:
    def __init__(self):
        self.stopped = False

    def poll(self):
        return 0 if self.stopped else None


class ParkSessionSupervisorTest(unittest.TestCase):
    def timing_records(self):
        path = self.supervisor.runtime / "load-timings.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_idle_supervisor_needs_no_initial_park(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "run-data") as directory:
            root = Path(directory)
            library = root / "library"
            library.mkdir()
            with mock.patch.dict("os.environ", {"RCT2_DATA_DIR": str(root / "rct2")}):
                supervisor = ParkSessionSupervisor(library, root / "runtime", start_browser=False)
                self.assertEqual(supervisor.state()["phase"], "idle")
                self.assertEqual(supervisor.state()["current"], "")
                self.assertEqual(supervisor.state()["parks"], [])
                with mock.patch.object(supervisor, "prepare") as prepare:
                    supervisor.start_initial()
                    prepare.assert_not_called()
                self.assertFalse(supervisor.ready_session_exited())

    def test_cli_installs_termination_handler_before_browser_start(self):
        prior_handler = signal.getsignal(signal.SIGTERM)
        with mock.patch.object(supervisor_module, "ParkSessionSupervisor", return_value=self.supervisor), \
             mock.patch.object(supervisor_module, "ThreadedUnixServer") as server_type, \
             mock.patch.object(supervisor_module.os, "chmod"), \
             mock.patch.object(supervisor_module.threading, "Thread"), \
             mock.patch.object(self.supervisor, "start_wasm", side_effect=KeyboardInterrupt) as start, \
             mock.patch.object(self.supervisor, "close") as close, \
             mock.patch.object(sys, "argv", ["park_session_supervisor.py", "--parks", str(self.library),
                                             "--runtime", str(self.root / "runtime")]):
            try:
                supervisor_module.main()
            finally:
                signal.signal(signal.SIGTERM, prior_handler)
        start.assert_called_once_with()
        close.assert_called_once_with()
        server_type.return_value.shutdown.assert_called_once_with()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=ROOT / "run-data")
        self.root = Path(self.directory.name)
        self.environment = mock.patch.dict("os.environ", {"RCT2_DATA_DIR": str(self.root / "rct2")})
        self.environment.start()
        self.library = self.root / "library"
        self.library.mkdir()
        for name in ("Park A.park", "Park B.park"):
            (self.library / name).write_bytes(b"PARKpark")
        self.preflights = []
        self.native_maps = []
        self.cache = SingleMapCache(self.root / "cache", dependencies=lambda: {"fixture": "v1"},
                                    preflight=lambda generation, plan, runtime: self.preflights.append(generation))
        self.supervisor = ParkSessionSupervisor(self.library, self.root / "runtime", "Park A.park",
                                                 start_browser=False, cache=self.cache)
        self.old = Process()
        self.supervisor.session = self.old
        self.supervisor.plan = {"server_data": str(self.root / "old-server")}
        self.supervisor.current = "Park A.park"
        self.supervisor.generation = "old-generation"
        self.supervisor.phase = "ready"

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

    @contextmanager
    def fake_cache_engines(self, inspect=None):
        def native(plan):
            self.native_maps.append(plan["native_map"])
            output = Path(plan["native_map"])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"native-map")
        with mock.patch.object(prepare_existing_defense, "inspect_existing_park",
                               side_effect=inspect or (lambda source: (64, 64))), \
             mock.patch.object(single_map_cache, "build_native_map", side_effect=native):
            yield

    def test_first_selection_starts_from_idle(self):
        self.supervisor.phase = "idle"
        self.supervisor.session = None
        self.supervisor.plan = None
        self.supervisor.current = ""
        self.supervisor.generation = ""
        with mock.patch("park_session_supervisor.threading.Thread.start"):
            accepted = self.supervisor.request("Park A.park", "discard", "")
        self.assertEqual(accepted["phase"], "preparing")
        with mock.patch.object(self.supervisor, "prepare", return_value=("fresh", {"park": "fresh"})), \
             mock.patch.object(self.supervisor, "launch", return_value=(self.old, self.root / "fresh.log")), \
             mock.patch.object(self.supervisor, "await_ready"):
            self.supervisor.transition("Park A.park", "discard", "")
        self.assertEqual(self.supervisor.state()["generation"], "fresh")
        self.assertEqual(self.supervisor.state()["phase"], "ready")

    def test_first_preparation_failure_returns_to_idle(self):
        self.supervisor.phase = "preparing"
        self.supervisor.session = None
        with mock.patch.object(self.supervisor, "prepare", side_effect=RuntimeError("invalid map")):
            self.supervisor.transition("Park B.park", "discard", "")
        self.assertEqual(self.supervisor.state()["phase"], "idle")
        self.assertIn("invalid map", self.supervisor.state()["error"])

    def test_catalog_includes_licensed_formats_and_upload_is_isolated(self):
        scenarios = self.root / "rct2" / "Scenarios"
        scenarios.mkdir(parents=True)
        (scenarios / "Small.SC6").write_bytes(b"scenario")
        self.assertIn("Small.SC6", self.supervisor.state()["parks"])
        self.assertEqual(self.supervisor.source_for("Small.SC6"), scenarios / "Small.SC6")
        uploaded = self.supervisor.upload("My Save.sv6", io.BytesIO(b"saved"), 5)["park"]
        self.assertTrue((self.root / "runtime" / "uploads" / uploaded).is_file())
        with self.assertRaisesRegex(ValueError, "invalid_save_filename"):
            self.supervisor.upload("../escape.sv6", io.BytesIO(b"saved"), 5)
        with self.assertRaisesRegex(ValueError, "invalid_park_header"):
            self.supervisor.upload("bad.park", io.BytesIO(b"nope"), 4)

    def test_return_to_title_requires_current_generation(self):
        with self.assertRaisesRegex(ValueError, "stale_park_generation"):
            self.supervisor.return_to_title("older")
        with mock.patch.object(self.supervisor, "stop", side_effect=lambda process: setattr(process, "stopped", True)):
            state = self.supervisor.return_to_title("old-generation")
        self.assertEqual(state["phase"], "idle")
        self.assertEqual(state["generation"], "")

    def test_private_catalog_rejects_symlink_and_path_requests(self):
        (self.library / "link.park").symlink_to(self.library / "Park A.park")
        (self.library / "outside.txt").write_text("x")
        self.assertEqual(self.supervisor.state()["parks"], ["Park A.park", "Park B.park"])
        for name in ("../Park A.park", "link.park", "/tmp/Other.park"):
            with self.assertRaisesRegex(ValueError, "private_library"):
                self.supervisor.source_for(name)
        saved = self.supervisor.runtime / "saved"
        saved.mkdir()
        (saved / "Park A.park").symlink_to(self.library / "Park A.park")
        with self.assertRaisesRegex(ValueError, "unsafe_saved_park"):
            self.supervisor.source_for("Park A.park")
        with self.assertRaisesRegex(ValueError, "stale_park_generation"):
            self.supervisor.request("Park B.park", "discard", "older")
        with self.assertRaisesRegex(ValueError, "select_save_or_discard"):
            self.supervisor.request("Park B.park", "cancel", "old-generation")

    def test_failed_preparation_leaves_old_session_running(self):
        self.supervisor.phase = "preparing"
        with mock.patch.object(self.supervisor, "prepare", side_effect=RuntimeError("bad terrain")):
            self.supervisor.transition("Park B.park", "discard", "")
        self.assertFalse(self.old.stopped)
        self.assertEqual(self.supervisor.state()["phase"], "ready")
        self.assertEqual(self.supervisor.state()["current"], "Park A.park")
        self.assertIn("bad terrain", self.supervisor.state()["error"])

    def test_successful_transition_uses_new_generation_and_session(self):
        new = Process()
        self.supervisor.phase = "preparing"
        with mock.patch.object(self.supervisor, "prepare", return_value=("new-generation", {"park": "new"})), \
             mock.patch.object(self.supervisor, "launch", return_value=(new, self.root / "new.log")), \
             mock.patch.object(self.supervisor, "await_ready"), \
             mock.patch.object(self.supervisor, "stop", side_effect=lambda process: setattr(process, "stopped", True)):
            self.supervisor.transition("Park B.park", "discard", "")
        self.assertTrue(self.old.stopped)
        self.assertIs(self.supervisor.session, new)
        self.assertEqual(self.supervisor.state()["generation"], "new-generation")
        self.assertEqual(self.supervisor.state()["current"], "Park B.park")
        self.assertEqual(self.supervisor.state()["phase"], "ready")
        record = self.timing_records()[0]
        self.assertEqual((record["map"], record["generation"], record["outcome"]),
                         ("Park B.park", "new-generation", "ready"))
        self.assertEqual(record["stages"]["session_startup"]["status"], "ok")
        self.assertEqual(record["stages"]["client_join"]["status"], "unavailable")
        self.assertGreaterEqual(record["total_ms"], record["stages"]["session_startup"]["elapsed_ms"])

    def test_prepare_records_distinct_stages_and_preflight_failure(self):
        timing = self.supervisor.load_timing("Park B.park")
        with self.fake_cache_engines(), \
             mock.patch.object(self.cache, "preflight", side_effect=RuntimeError("bad sync")):
            with self.assertRaisesRegex(RuntimeError, "bad sync") as raised:
                self.supervisor.prepare("Park B.park", timing)
        timing.finish("failed", raised.exception)
        record = self.timing_records()[0]
        self.assertEqual(record["source_sha256"], single_map_cache.sha256_file(self.library / "Park B.park"))
        self.assertEqual(record["error_type"], "RuntimeError")
        self.assertEqual(record["stages"]["source_resolution"]["status"], "ok")
        self.assertEqual(record["stages"]["park_preparation"]["status"], "ok")
        self.assertEqual(record["stages"]["native_map_generation"]["status"], "ok")
        self.assertEqual(record["stages"]["isolated_preflight"]["status"], "failed")
        self.assertEqual(record["stages"]["session_startup"]["status"], "unavailable")
        self.assertTrue(record["generation"])
        self.assertEqual(len(self.native_maps), 1)
        self.assertEqual(self.cache.status(self.library / "Park B.park")["status"], "missing")

    def test_uncached_then_cached_selection_has_fresh_state_and_skipped_stages(self):
        with self.fake_cache_engines():
            first_timing = self.supervisor.load_timing("Park B.park")
            first_generation, first = self.supervisor.prepare("Park B.park", first_timing)
            first_timing.finish("prepared")
            second_timing = self.supervisor.load_timing("Park B.park")
            second_generation, second = self.supervisor.prepare("Park B.park", second_timing)
            second_timing.finish("prepared")
        self.assertNotEqual(first_generation, second_generation)
        self.assertEqual(len(self.native_maps), 1)
        self.assertEqual(len(self.preflights), 1)
        self.assertNotEqual(first["park"], second["park"])
        self.assertNotEqual(Path(first["park"]).stat().st_ino, Path(second["park"]).stat().st_ino)
        self.assertFalse(Path(first["spawn_journal"]).exists())
        self.assertFalse(Path(second["spawn_journal"]).exists())
        first_record, second_record = self.timing_records()
        self.assertEqual(first_record["cache_outcome"], "built")
        self.assertEqual(second_record["cache_outcome"], "hit")
        self.assertEqual(second_record["generation"], second_generation)
        self.assertEqual(second_record["stages"]["isolated_preflight"]["status"], "skipped")
        self.assertEqual(second_record["stages"]["native_map_generation"]["status"], "skipped")
        self.assertEqual(second_record["stages"]["client_join"]["status"], "unavailable")
        self.assertEqual(second_record["stages"]["materialization"]["status"], "ok")
        self.assertEqual(second_record["stages"]["cache_lookup"]["count"], 2)

    def test_initial_load_uses_cache_and_still_awaits_native_readiness(self):
        self.supervisor.session = None
        self.supervisor.phase = "preparing"
        process = Process()
        with self.fake_cache_engines(), \
             mock.patch.object(self.supervisor, "launch", return_value=(process, self.root / "initial.log")) as launch, \
             mock.patch.object(self.supervisor, "await_ready") as await_ready:
            self.supervisor.start_initial()
        launch.assert_called_once()
        await_ready.assert_called_once()
        self.assertEqual(self.supervisor.state()["phase"], "ready")
        self.assertEqual(self.supervisor.state()["current"], "Park A.park")
        self.assertEqual(self.timing_records()[0]["cache_outcome"], "built")

    def test_edited_authoritative_save_uses_new_bytes_and_geometry(self):
        saved = self.supervisor.runtime / "saved" / "Park A.park"
        def inspect(source):
            return (96, 64) if Path(source).read_bytes() == b"PARKsave" else (64, 64)
        with self.fake_cache_engines(inspect):
            first_timing = self.supervisor.load_timing("Park A.park")
            _, first = self.supervisor.prepare("Park A.park", first_timing)
            saved.parent.mkdir()
            saved.write_bytes(b"PARKsave")  # same length as the original park
            second_timing = self.supervisor.load_timing("Park A.park")
            _, second = self.supervisor.prepare("Park A.park", second_timing)
        self.assertNotEqual(first_timing.cache_key, second_timing.cache_key)
        self.assertEqual(json.loads(Path(first["scenario"]).read_text())["park_size"], [64, 64])
        self.assertEqual(json.loads(Path(second["scenario"]).read_text())["park_size"], [96, 64])
        self.assertEqual(Path(second["source"]).read_bytes(), b"PARKsave")
        self.assertEqual(second_timing.cache_outcome, "built")

    def test_corrupt_cache_is_repaired_before_selection(self):
        with self.fake_cache_engines():
            first_timing = self.supervisor.load_timing("Park A.park")
            self.supervisor.prepare("Park A.park", first_timing)
            manifest = self.cache.status(self.library / "Park A.park")["manifest"]
            map_file = self.cache.package_path(manifest["key"]) / f"map/{manifest['scenario_id']}.scm"
            map_file.chmod(0o644)
            map_file.write_bytes(b"bad map")
            second_timing = self.supervisor.load_timing("Park A.park")
            _, plan = self.supervisor.prepare("Park A.park", second_timing)
        self.assertEqual(second_timing.cache_outcome, "repaired")
        self.assertEqual(len(self.native_maps), 2)
        self.assertEqual(len(self.preflights), 2)
        self.assertEqual(Path(plan["native_map"]).read_bytes(), b"native-map")
        self.assertEqual(self.cache.status(self.library / "Park A.park")["status"], "ready")

    def test_cancelled_cached_switch_preserves_old_session(self):
        with self.fake_cache_engines():
            self.supervisor.prepare("Park B.park")
            self.supervisor.phase = "preparing"
            self.supervisor.cancel_pending = True
            with mock.patch.object(self.supervisor, "launch") as launch:
                self.supervisor.transition("Park B.park", "discard", "")
        launch.assert_not_called()
        self.assertFalse(self.old.stopped)
        self.assertEqual(self.supervisor.state()["phase"], "ready")
        self.assertEqual(self.supervisor.state()["generation"], "old-generation")
        self.assertEqual(self.timing_records()[0]["outcome"], "cancelled")
        self.assertEqual(self.timing_records()[0]["cache_outcome"], "hit")

    def test_timing_stage_failure_keeps_unreached_milestones_explicit(self):
        timing = LoadTiming("broken.sc6", self.supervisor.runtime / "load-timings.jsonl")
        with self.assertRaises(ValueError):
            with timing.stage("source_inspection"):
                raise ValueError("invalid park")
        timing.finish("failed", ValueError("invalid park"))
        timing.finish("ready")
        record, = self.timing_records()
        self.assertEqual(record["stages"]["source_inspection"]["error_type"], "ValueError")
        self.assertEqual(record["stages"]["native_map_generation"]["status"], "unavailable")
        self.assertEqual(set(record["stages"]), set(STAGES))
        self.assertEqual(record["outcome"], "failed")

    def test_stopped_old_session_does_not_restart_browser_during_transition(self):
        self.old.stopped = True
        for phase in ("preparing", "switching", "starting", "failed"):
            self.supervisor.phase = phase
            self.assertFalse(self.supervisor.ready_session_exited(), phase)
        self.supervisor.phase = "ready"
        self.assertTrue(self.supervisor.ready_session_exited())

    def test_activation_failure_starts_fresh_prior_session(self):
        failed, recovered = Process(), Process()
        self.supervisor.phase = "preparing"
        with mock.patch.object(self.supervisor, "prepare", side_effect=[
                 ("failed-generation", {"park": "bad"}), ("recovered-generation", {"park": "old"})]), \
             mock.patch.object(self.supervisor, "launch", side_effect=[
                 (failed, self.root / "bad.log"), (recovered, self.root / "old.log")]), \
             mock.patch.object(self.supervisor, "await_ready", side_effect=[
                 RuntimeError("native unavailable"), None]), \
             mock.patch.object(self.supervisor, "stop", side_effect=lambda process: setattr(process, "stopped", True)):
            self.supervisor.transition("Park B.park", "discard", "")
        self.assertTrue(self.old.stopped)
        self.assertTrue(failed.stopped)
        self.assertIs(self.supervisor.session, recovered)
        self.assertEqual(self.supervisor.state()["generation"], "recovered-generation")
        self.assertIn("restored prior park", self.supervisor.state()["error"])

    def test_recovery_failure_is_recorded_without_stale_ready_generation(self):
        failed = Process()
        self.supervisor.phase = "preparing"
        with mock.patch.object(self.supervisor, "prepare", side_effect=[
                 ("failed-generation", {"park": "bad"}), RuntimeError("recovery cache failed")]), \
             mock.patch.object(self.supervisor, "launch", return_value=(failed, self.root / "bad.log")), \
             mock.patch.object(self.supervisor, "await_ready", side_effect=RuntimeError("native unavailable")), \
             mock.patch.object(self.supervisor, "stop", side_effect=lambda process: setattr(process, "stopped", True)):
            self.supervisor.transition("Park B.park", "discard", "")
        self.assertTrue(self.old.stopped)
        self.assertTrue(failed.stopped)
        self.assertEqual(self.supervisor.state()["phase"], "failed")
        self.assertEqual(self.supervisor.state()["generation"], "old-generation")
        self.assertIn("recovery failed: recovery cache failed", self.supervisor.state()["error"])
        records = self.timing_records()
        self.assertEqual([(r["kind"], r["outcome"]) for r in records],
                         [("selection", "failed"), ("recovery", "failed")])

    def test_concurrent_request_is_rejected_before_transition_finishes(self):
        with mock.patch("park_session_supervisor.threading.Thread.start"):
            accepted = self.supervisor.request("Park B.park", "discard", "old-generation")
            self.assertEqual(accepted["phase"], "preparing")
            with self.assertRaisesRegex(ValueError, "park_transition_busy"):
                self.supervisor.request("Park A.park", "discard", "old-generation")
        self.assertFalse(self.old.stopped)

    def test_authoritative_save_is_reused_after_supervisor_restart(self):
        save_dir = Path(self.supervisor.plan["server_data"]) / "save"
        save_dir.mkdir(parents=True)
        (save_dir / "starcoaster-switch-0123456789abcdef.park").write_bytes(b"PARKsaved")
        self.supervisor.archive_save("Park A.park", "starcoaster-switch-0123456789abcdef.park")
        restarted = ParkSessionSupervisor(self.library, self.root / "runtime", "Park A.park",
                                          start_browser=False)
        self.assertEqual(restarted.source_for("Park A.park").read_bytes(), b"PARKsaved")
        self.assertEqual((self.library / "Park A.park").read_bytes(), b"PARKpark")

    def test_last_active_park_survives_supervisor_restart(self):
        self.supervisor.current = "Park B.park"
        self.supervisor.persist_current()
        restarted = ParkSessionSupervisor(self.library, self.root / "runtime", "Park A.park",
                                          start_browser=False)
        self.assertEqual(restarted.initial, "Park B.park")


if __name__ == "__main__":
    unittest.main()
