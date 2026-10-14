"""Recording mode and generic capture checks without launching graphical clients."""

import importlib.util
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


record = load("record_scenario", "record-scenario.py")
generic = load("verify_scenario", "verify-scenario-capture.py")
frontier = load("verify_frontier", "verify-frontier-capture.py")
world256 = load("verify_world256", "verify-world-256-capture.py")


class ScenarioRecordTest(unittest.TestCase):
    def test_modes_and_package_resolution(self):
        for args in (("--scenario", "example-defense", "--world-256"),
                     ("--scenario", "example-defense", "--ridge-probe"),
                     ("--scenario", "example-defense", "--cycle-rotations"),
                     ("--scenario", "missing")):
            with self.subTest(args=args), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                record.parse_args([*args, "--no-video"])
        with mock.patch.object(record, "check_dependencies") as dependencies:
            args, _ = record.parse_args(["--scenario", "example-defense", "--no-video"])
        dependencies.assert_not_called()
        self.assertEqual(args.plan["scenario_id"], "example-defense")
        args, _ = record.parse_args(["--world-256", "--no-video"])
        self.assertIsNone(args.plan)

    def test_session_selection_and_journal_isolation(self):
        plan = record.resolve("example-defense")
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            env = record.session_environment(plan, {"BRIDGE_LAUNCH_CLIENT": "0",
                "BRIDGE_SPAWN_JOURNAL": str(out / "spawn-queue.json"),
                "BRIDGE_SERVER_DATA_DIR": str(out / "server-data")})
            with mock.patch.object(record, "ensure_park") as park, mock.patch.object(
                    record, "build_native_map", return_value=out / "example-defense.scm") as native:
                command, result_map = record.prepare_packaged_session(plan, out, env)
            park.assert_called_once_with(plan)
            native.assert_called_once_with(plan, out / "example-defense.scm")
            self.assertEqual(command, [str(ROOT / "scripts/run-world-session.sh"), plan["park"]])
            self.assertEqual(env["BRIDGE_MAP_FILE"], str(result_map))
            self.assertEqual(env["BRIDGE_SCENARIO_CONFIG"], plan["scenario"])
            self.assertEqual(env["BRIDGE_RULES_CONFIG"], plan["mapping"])
            self.assertNotEqual(env["BRIDGE_SPAWN_JOURNAL"], plan["spawn_journal"])
            self.assertEqual(env["BRIDGE_LAUNCH_CLIENT"], "0")

    def test_generic_one_and_two_clients_and_frontier_compatibility(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "scenario-config.json").write_text(json.dumps({"scenario_id": "example-defense", "display_name": "Example Defense"}))
            (out / "server.log").write_text("WORLD_READY entities=4 navigation=native\n")
            png = b"\x89PNG\r\n\x1a\n" + b"image"
            snapshot = "".join(f"RTS Bridge apply tick={i} seq={i} session={'a'*32} center_z=112 units=openbw:1,1,1\n"
                               for i in range(1, 13))
            for letter in "ab":
                (out / f"client-{letter}.log").write_text(
                    "WORLD_SCENARIO_STATUS scenario=example-defense wave=1/2 state=active outcome=\n" + snapshot)
                for point in ("initial", "final"):
                    (out / f"client-{letter}-{point}.png").write_bytes(png)
            self.assertTrue(generic.verify(out)["capture_complete"])
            self.assertEqual(generic.verify(out)["shared_snapshot_sequences"], 12)
            (out / "client-b.log").unlink()
            for point in ("initial", "final"):
                (out / f"client-b-{point}.png").unlink()
            self.assertTrue(generic.verify(out)["capture_complete"])
            (out / "client-a.log").write_text("WORLD_SCENARIO_STATUS scenario=frontier-outpost wave=1/2 state=active outcome=\n" + snapshot)
            self.assertFalse(generic.verify(out)["capture_complete"])
            with contextlib.redirect_stdout(io.StringIO()):
                frontier.main(out)
            self.assertTrue(json.loads((out / "verification.json").read_text())["capture_complete"])

    def test_frontier_late_join_after_gate_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "server.log").write_text(
                "WORLD_READY navigation=native\nWORLD_REMOVAL id=openrct2:wall:31:896:1120:112:0#1 state=confirmed\n"
                "navigation-applied id=openrct2:wall:31:896:1120:112:0#1\n")
            snapshots = "".join(f"RTS Bridge apply tick={i} seq={i} session={'a'*32} center_z=112 units=openbw:1,1,1\n"
                                for i in range(1, 13))
            (out / "client-a.log").write_text("FRONTIER_PARK_STATE carousel=true gate=true\n" + snapshots +
                                               "FRONTIER_PARK_STATE carousel=true gate=false\n")
            (out / "client-b.log").write_text("FRONTIER_PARK_STATE carousel=true gate=false\n" + snapshots)
            with contextlib.redirect_stdout(io.StringIO()):
                frontier.main(out)
            report = json.loads((out / "verification.json").read_text())
            self.assertTrue(report["park_change_synchronized"])
            self.assertTrue(report["capture_complete"])

    def test_world_256_no_video_asset_check(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            for letter in "ab":
                for point in ("initial", "final"):
                    (out / f"client-{letter}-{point}.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")
            self.assertTrue(world256.capture_assets(out, {"video": None, "cycle_rotations": False})[0])
            self.assertFalse(world256.capture_assets(out, {"video": None, "cycle_rotations": True})[0])
            self.assertFalse(world256.capture_assets(out, {"video": {"layout": "combined"}})[0])


if __name__ == "__main__":
    unittest.main()
