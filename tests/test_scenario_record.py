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
    def test_goliath_combat_from_native_visual_snapshot(self):
        def actor(kind, motion, hp, maximum):
            return f"openbw:3001,3204,486,197,{motion},419,{kind},{hp},{maximum},1,2"
        prefix = "BridgeApplySnapshot units="
        self.assertTrue(record.goliath_damage_in_visual_snapshots(
            prefix + actor("terran_goliath", "attack", 125, 125) + ";"
            + actor("zerg_zergling", "death", 24, 35)))
        self.assertFalse(record.goliath_damage_in_visual_snapshots(
            prefix + actor("terran_goliath", "idle", 125, 125) + ";"
            + actor("zerg_zergling", "death", 24, 35)))
        self.assertFalse(record.goliath_damage_in_visual_snapshots(
            prefix + actor("terran_goliath", "attack", 125, 125) + ";"
            + actor("zerg_zergling", "idle", 35, 35)))

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
        baseline, _ = record.parse_args(["--navigation-baseline", "--no-video"])
        self.assertEqual(baseline.plan["scenario_id"], "frontier-outpost")
        for incompatible in (("--scenario", "example-defense"), ("--world-256",),
                             ("--live-construction",), ("--video-layout", "single")):
            with self.subTest(incompatible=incompatible), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                record.parse_args(["--navigation-baseline", *incompatible, "--no-video"])

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

    def test_mt_zergling_recording_accepts_six_minutes_at_normal_speed(self):
        with mock.patch.object(record, "resolve", return_value={"scenario_id": "mt-zergling"}):
            args, _ = record.parse_args(["--scenario", "mt-zergling", "--duration", "360", "--no-video"])
            playthrough, _ = record.parse_args(["--scenario", "mt-zergling", "--duration", "360",
                                                 "--no-video", "--mt-zergling-playthrough"])
        self.assertEqual(args.duration, 360)
        self.assertEqual(args.frame_ms, 42)
        self.assertTrue(playthrough.mt_zergling_playthrough)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            record.parse_args(["--scenario", "example-defense", "--mt-zergling-playthrough", "--no-video"])

    def test_navigation_baseline_requires_native_route_and_both_participants(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            for letter in "ab":
                for second in (2, 6, 10, 14):
                    (out / f"client-{letter}-t{second}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            scenes = ("under_rail", "wall_north", "around_end", "wall_south", "return")
            driver = ("NAV_BASELINE_TRIGGER time=1\n"
                      "NAV_BASELINE_WALL time=1 accepted=true reason=ok\n"
                      "NAV_BASELINE_CAMERA time=1 rotation=0\n" +
                      "".join(f"NAV_BASELINE_ORDER time={i} scene={scene} actor=openbw:1000 accepted=true\n"
                              f"NAV_BASELINE_CROSSED time={i+1} scene={scene} actor=openbw:1000 x=528 y=1008\n"
                              for i, scene in enumerate(scenes, 2)) +
                      "NAV_BASELINE_COMPLETE time=20 actor=openbw:1000'\n")
            server = ("park patch synchronized id=a revision=2 hash=0123456789abcdef frame=100\n"
                      "[world] navigation-mask hash=0123456789abcdef frame=100 accepted=1\n"
                      "[world-control] navigation-mask hash=0123456789abcdef frame=100 accepted=1\n")
            verified = record.verify_navigation_baseline(out, [driver,
                "NAV_BASELINE_CAMERA time=1 rotation=1\n"], server, {"capture_complete": True})
            self.assertTrue(verified["capture_complete"])
            self.assertEqual(verified["navigation_baseline"]["runtime_actor_ids"], ["openbw:1000"])
            (out / "video-metadata.json").write_text(json.dumps({
                "capture_start_utc": "1970-01-01T00:00:00.010+00:00",
                "capture_end_utc": "1970-01-01T00:00:00.020+00:00"}))
            early = record.verify_navigation_baseline(out, [driver,
                "NAV_BASELINE_CAMERA time=1 rotation=1\n"], server, {"capture_complete": True})
            self.assertFalse(early["navigation_baseline"]["checks"]["started_during_recording"])
            (out / "video-metadata.json").unlink()
            (out / "client-b-t6.png").unlink()
            incomplete = record.verify_navigation_baseline(out, [driver,
                "NAV_BASELINE_CAMERA time=1 rotation=1\n"], server, {"capture_complete": True})
            self.assertFalse(incomplete["capture_complete"])

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
            (out / "client-a.log").write_text(
                "WORLD_SCENARIO_STATUS scenario=example-defense wave=0/0 state= outcome=\n" + snapshot)
            self.assertTrue(generic.verify(out)["capture_complete"])
            (out / "client-b.log").unlink()
            for point in ("initial", "final"):
                (out / f"client-b-{point}.png").unlink()
            self.assertTrue(generic.verify(out)["capture_complete"])
            (out / "client-a.log").write_text("WORLD_SCENARIO_STATUS scenario=frontier-outpost wave=1/2 state=active outcome=\n"
                                             "FRONTIER_PARK_STATE carousel=true gate=true\n" + snapshot)
            self.assertFalse(generic.verify(out)["capture_complete"])
            with contextlib.redirect_stdout(io.StringIO()):
                frontier.main(out)
            single = json.loads((out / "verification.json").read_text())
            self.assertTrue(single["park_change_synchronized"])
            self.assertTrue(single["capture_complete"])

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
