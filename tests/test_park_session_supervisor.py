"""Safety checks for private park selection and fresh-session transitions."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from park_session_supervisor import ParkSessionSupervisor


class Process:
    def __init__(self):
        self.stopped = False

    def poll(self):
        return 0 if self.stopped else None


class ParkSessionSupervisorTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=ROOT / "run-data")
        self.root = Path(self.directory.name)
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
        self.directory.cleanup()

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


if __name__ == "__main__":
    unittest.main()
