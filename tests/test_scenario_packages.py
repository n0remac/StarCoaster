import importlib.util
import contextlib
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock
import tempfile
import sys



ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import scenario_package
spec = importlib.util.spec_from_file_location("play_scenario", ROOT / "scripts/play-scenario.py")
play = importlib.util.module_from_spec(spec)
spec.loader.exec_module(play)
park_spec = importlib.util.spec_from_file_location("park_scenario", ROOT / "scripts/park-scenario.py")
park_cli = importlib.util.module_from_spec(park_spec)
park_spec.loader.exec_module(park_cli)


class ScenarioPackageTest(unittest.TestCase):
    def test_distinct_packages_share_launcher_and_native_map_builder(self):
        frontier = play.resolve("frontier-outpost")
        example = play.resolve("example-defense")
        self.assertNotEqual(frontier["park"], example["park"])
        self.assertNotEqual(frontier["native_map"], example["native_map"])
        self.assertEqual(frontier["generator"][1], example["generator"][1])
        self.assertEqual(json.loads(Path(example["scenario"]).read_text())["version"], 2)
        self.assertEqual(json.loads(Path(frontier["scenario"]).read_text())["scenario_id"], "frontier-outpost")

    def test_project_play_resolves_frontier_package(self):
        output = subprocess.check_output(["scripts/project.sh", "play", "frontier-outpost", "--plan"], cwd=ROOT)
        self.assertEqual(json.loads(output), play.resolve("frontier-outpost"))

    def test_invalid_package_id_rejected(self):
        for value in ("../example-defense", "Frontier", "missing/package"):
            with self.assertRaises(ValueError):
                play.resolve(value)

    def test_missing_and_mismatched_packages(self):
        with self.assertRaisesRegex(ValueError, "missing scenario package"):
            play.resolve("does-not-exist")
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(scenario_package, "ROOT", Path(directory)):
            package = Path(directory) / "scenarios/test"
            package.mkdir(parents=True)
            (package / "mapping.json").write_text("{}")
            (package / "scenario.json").write_text(json.dumps({"scenario_id": "other", "park_file": "run-data/a.park"}))
            (package / "package.json").write_text(json.dumps({"generator": ["scripts/create-park-assault.py", "--playable"],
                "fixture": "run-data/fixture.json", "navigation": "run-data/navigation.json"}))
            with self.assertRaisesRegex(ValueError, "mismatched"):
                play.resolve("test")
            (package / "scenario.json").write_text(json.dumps({"scenario_id": "test", "park_file": "../escape.park"}))
            with self.assertRaisesRegex(ValueError, "run-data"):
                play.resolve("test")
            (package / "scenario.json").write_text(json.dumps({"scenario_id": "test", "park_file": "run-data/a.park"}))
            (package / "package.json").write_text(json.dumps({"generator": ["scripts/evil.py"],
                "fixture": "run-data/fixture.json", "navigation": "run-data/navigation.json"}))
            with self.assertRaisesRegex(ValueError, "generator"):
                play.resolve("test")

    def test_park_stale_and_force_generation(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(scenario_package, "ROOT", Path(directory)):
            root = Path(directory)
            for name in scenario_package.GENERATOR_INPUTS:
                source = root / name
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("source")
            paths = [root / "run-data" / name for name in ("park", "fixture", "navigation")]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("data")
            plan = dict(zip(("park", "fixture", "navigation"), map(str, paths)))
            plan.update(scenario_id="test", generator=["python3", "scripts/create-park-assault.py", "--playable"])
            with mock.patch.object(scenario_package.subprocess, "run") as run:
                scenario_package.ensure_park(plan)
                run.assert_not_called()
                scenario_package.ensure_park(plan, force=True)
                run.assert_called_once_with(plan["generator"], cwd=root, check=True)

    def test_park_rejects_unknown_flags_before_gameplay(self):
        result = subprocess.run(["scripts/project.sh", "park", "--not-a-scenario"], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_play_dispatches_one_world_session_with_package_environment(self):
        plan = play.resolve("example-defense")
        with mock.patch.object(sys, "argv", ["play-scenario.py", "example-defense"]), \
             mock.patch.object(play, "ensure_park") as park, \
             mock.patch.object(play, "build_native_map") as native, \
             mock.patch.object(play.os, "execvpe") as launch:
            play.main()
        park.assert_called_once_with(plan)
        native.assert_called_once_with(plan)
        launch.assert_called_once()
        command, arguments, environment = launch.call_args.args
        self.assertEqual(command, str(ROOT / "scripts/run-world-session.sh"))
        self.assertEqual(arguments, [command, plan["park"]])
        self.assertEqual(environment["BRIDGE_SCENARIO_CONFIG"], plan["scenario"])
        self.assertEqual(environment["BRIDGE_RULES_CONFIG"], plan["mapping"])
        self.assertEqual(environment["BRIDGE_MAP_FILE"], plan["native_map"])
        self.assertEqual(environment["BRIDGE_SPAWN_JOURNAL"], plan["spawn_journal"])

    def test_park_command_only_generates_selected_package(self):
        plan = play.resolve("example-defense")
        with mock.patch.object(sys, "argv", ["park-scenario.py", "example-defense"]), \
             mock.patch.object(park_cli, "resolve", return_value=plan) as resolve, \
             mock.patch.object(park_cli, "ensure_park") as generate, \
             contextlib.redirect_stdout(io.StringIO()):
            park_cli.main()
        resolve.assert_called_once_with("example-defense")
        generate.assert_called_once_with(plan, force=True)


if __name__ == "__main__":
    unittest.main()
