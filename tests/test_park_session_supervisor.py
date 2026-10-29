"""Safety checks for private park selection and fresh-session transitions."""

import tempfile
import unittest
import io
import json
from pathlib import Path
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from park_session_supervisor import ParkSessionSupervisor
from load_timing import LoadTiming, STAGES


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

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=ROOT / "run-data")
        self.root = Path(self.directory.name)
        self.environment = mock.patch.dict("os.environ", {"RCT2_DATA_DIR": str(self.root / "rct2")})
        self.environment.start()
        self.library = self.root / "library"
        self.library.mkdir()
        for name in ("Park A.park", "Park B.park"):
            (self.library / name).write_bytes(b"PARKpark")
        self.supervisor = ParkSessionSupervisor(self.library, self.root / "runtime", "Park A.park",
                                                 start_browser=False)
        self.old = Process()
        self.supervisor.session = self.old
        self.supervisor.plan = {"server_data": str(self.root / "old-server")}
        self.supervisor.current = "Park A.park"
        self.supervisor.generation = "old-generation"
        self.supervisor.phase = "ready"

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

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
        plan = {"validated_source_sha256": "abc", "park": "prepared"}
        timing = self.supervisor.load_timing("Park B.park")
        with mock.patch("park_session_supervisor.prepare", return_value=plan) as prepare, \
             mock.patch("park_session_supervisor.ensure_park") as ensure, \
             mock.patch("park_session_supervisor.build_native_map") as native, \
             mock.patch.object(self.supervisor, "preflight_native_map", side_effect=RuntimeError("bad sync")):
            with self.assertRaisesRegex(RuntimeError, "bad sync") as raised:
                self.supervisor.prepare("Park B.park", timing)
        timing.finish("failed", raised.exception)
        record = self.timing_records()[0]
        self.assertEqual(record["source_sha256"], "abc")
        self.assertEqual(record["error_type"], "RuntimeError")
        self.assertEqual(record["stages"]["source_resolution"]["status"], "ok")
        self.assertEqual(record["stages"]["park_preparation"]["status"], "ok")
        self.assertEqual(record["stages"]["native_map_generation"]["status"], "ok")
        self.assertEqual(record["stages"]["isolated_preflight"]["status"], "failed")
        self.assertEqual(record["stages"]["session_startup"]["status"], "unavailable")
        self.assertTrue(record["generation"])
        prepare.assert_called_once()
        ensure.assert_called_once_with(plan)
        native.assert_called_once_with(plan)

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
