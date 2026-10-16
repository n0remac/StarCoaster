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
from park_layout import load as load_layout
spec = importlib.util.spec_from_file_location("play_scenario", ROOT / "scripts/play-scenario.py")
play = importlib.util.module_from_spec(spec)
spec.loader.exec_module(play)
park_spec = importlib.util.spec_from_file_location("park_scenario", ROOT / "scripts/park-scenario.py")
park_cli = importlib.util.module_from_spec(park_spec)
park_spec.loader.exec_module(park_cli)


class ScenarioPackageTest(unittest.TestCase):
    def test_existing_park_source_is_staged_without_fixture_exports(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(scenario_package, "ROOT", Path(directory)):
            root = Path(directory)
            package = root / "scenarios/imported"
            source = root / "run-data/imported/source/Original.park"
            package.mkdir(parents=True)
            source.parent.mkdir(parents=True)
            source.write_bytes(b"PARKoriginal park contents")
            (package / "scenario.json").write_text(json.dumps({"scenario_id": "imported",
                "park_file": "run-data/imported/save/imported.park"}))
            (package / "mapping.json").write_text("{}")
            metadata = package / "package.json"
            metadata.write_text(json.dumps({"generator": "existing-park",
                "source": "run-data/imported/source/Original.park"}))
            plan = scenario_package.resolve("imported")
            self.assertIsNone(plan["fixture"])
            self.assertIsNone(plan["navigation"])
            scenario_package.ensure_park(plan)
            staged = Path(plan["park"])
            self.assertEqual(staged.read_bytes(), source.read_bytes())
            staged.write_bytes(b"PARKsession changes")
            self.assertEqual(source.read_bytes(), b"PARKoriginal park contents")
            scenario_package.ensure_park(plan, force=True)
            self.assertEqual(staged.read_bytes(), source.read_bytes())
            source.unlink()
            with self.assertRaisesRegex(ValueError, "missing existing park"):
                scenario_package.resolve("imported")
            source.write_bytes(b"PARKpark")
            for bad in ("../outside.park", "run-data/another/source/Original.park",
                        "run-data/imported/save/imported.park"):
                metadata.write_text(json.dumps({"generator": "existing-park", "source": bad}))
                with self.assertRaisesRegex(ValueError, "source path"):
                    scenario_package.resolve("imported")
            metadata.write_text(json.dumps({"generator": "existing-park",
                "source": "run-data/imported/source/Original.park"}))
            source.unlink()
            outside = root / "outside.park"
            outside.write_bytes(b"PARKoutside")
            source.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "unsafe existing park"):
                scenario_package.resolve("imported")

    def test_fourth_independent_layout_fixture(self):
        layout = load_layout(ROOT / "tests/fixtures/fourth-layout.json")
        self.assertEqual(layout["name"], "Fourth Layout Proof")
        self.assertEqual([ride["expected"] for ride in layout["rides"]], [4, 1])

    def test_semantically_invalid_layouts(self):
        source = json.loads((ROOT / "tests/fixtures/fourth-layout.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "layout.json"
            for field, value in (("size", [63, 64]),
                                 ("rides", [{"id": "bad", "name": "Bad", "object": "rct2.ride.unknown", "x": 30, "y": 30}]),
                                 ("paths", [{"kind": "horizontal", "y": 30, "x0": 40, "x1": 20}]),
                                 ("walls", [{"x0": 20, "y0": 20, "x1": 21, "y1": 21,
                                             "direction": 4, "object": "rct2.scenery_wall.wbr2"}])):
                invalid = json.loads(json.dumps(source))
                invalid[field] = value
                path.write_text(json.dumps(invalid))
                with self.subTest(field=field), self.assertRaises(ValueError):
                    load_layout(path)

    def test_layout_validation_and_isolated_resolution(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(scenario_package, "ROOT", Path(directory)):
            root = Path(directory)
            def make(identifier):
                package = root / "scenarios" / identifier
                package.mkdir(parents=True)
                (package / "scenario.json").write_text(json.dumps({"scenario_id": identifier,
                    "park_file": f"run-data/{identifier}/save/{identifier}.park"}))
                (package / "mapping.json").write_text("{}")
                (package / "package.json").write_text(json.dumps({"generator": "layout-v1", "layout": "park-layout.json",
                    "fixture": f"run-data/{identifier}/fixture.json", "navigation": f"run-data/{identifier}/navigation-elements.json"}))
                (package / "park-layout.json").write_text(json.dumps({"version": 1, "name": identifier,
                    "size": [64, 64], "rides": [{"id": "wheel", "name": "Wheel", "object": "rct2.ride.fwh1", "x": 30, "y": 30}],
                    "paths": [{"kind": "horizontal", "y": 28, "x0": 12, "x1": 40}],
                    "walls": [{"x0": 20, "y0": 20, "x1": 20, "y1": 24, "direction": 0, "object": "rct2.scenery_wall.wbr1"}],
                    "scenery": [], "large_scenery": []}))
                return package
            a, b = make("alpha"), make("beta")
            first = scenario_package.resolve("alpha")
            second = scenario_package.resolve("beta")
            self.assertNotEqual(first["park"], second["park"])
            self.assertEqual(load_layout(a / "park-layout.json"), load_layout(a / "park-layout.json"))
            (a / "park-layout.json").unlink()
            with self.assertRaisesRegex(ValueError, "layout"):
                scenario_package.resolve("alpha")
            (a / "park-layout.json").symlink_to(b / "park-layout.json")
            with self.assertRaisesRegex(ValueError, "unsafe layout"):
                scenario_package.resolve("alpha")
            (a / "park-layout.json").unlink()
            (a / "park-layout.json").write_text("{bad")
            with self.assertRaisesRegex(ValueError, "invalid park layout"):
                scenario_package.resolve("alpha")
            (a / "package.json").write_text(json.dumps({"generator": "os.system('bad')"}))
            with self.assertRaisesRegex(ValueError, "generator"):
                scenario_package.resolve("alpha")
            (a / "park-layout.json").write_text((b / "park-layout.json").read_text())
            (a / "package.json").write_text((b / "package.json").read_text().replace("beta", "alpha"))
            (root / "run-data").mkdir()
            (root / "run-data/alpha").symlink_to(Path(directory) / "outside")
            with self.assertRaisesRegex(ValueError, "unsafe .* output"):
                scenario_package.resolve("alpha")

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

    def test_legacy_generator_cannot_claim_another_scenarios_outputs(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(scenario_package, "ROOT", Path(directory)):
            package = Path(directory) / "scenarios/other"
            package.mkdir(parents=True)
            (package / "scenario.json").write_text(json.dumps({"scenario_id": "other",
                "park_file": "run-data/frontier-playable/save/frontier-outpost-playable.park"}))
            (package / "mapping.json").write_text("{}")
            (package / "package.json").write_text(json.dumps({"generator": ["scripts/create-park-assault.py", "--playable"],
                "fixture": "run-data/frontier-playable/fixture.json",
                "navigation": "run-data/frontier-playable/navigation-elements.json"}))
            with self.assertRaisesRegex(ValueError, "belong"):
                scenario_package.resolve("other")

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

    def test_layout_change_or_missing_export_regenerates(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(scenario_package, "ROOT", Path(directory)):
            root = Path(directory)
            for name in scenario_package.GENERATOR_INPUTS:
                source = root / name
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("source")
            layout = root / "scenarios/test/park-layout.json"
            layout.parent.mkdir(parents=True)
            layout.write_text("layout")
            paths = [root / "run-data/test" / name for name in ("park", "fixture", "navigation")]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("data")
            plan = dict(zip(("park", "fixture", "navigation"), map(str, paths)))
            plan.update(scenario_id="test", layout=str(layout), generator=["python3", "generator"])
            with mock.patch.object(scenario_package.subprocess, "run") as run:
                scenario_package.ensure_park(plan)
                run.assert_not_called()
                layout.touch()
                import os
                os.utime(layout, (max(p.stat().st_mtime for p in paths) + 2,)*2)
                scenario_package.ensure_park(plan)
                run.assert_called_once()
                run.reset_mock()
                paths[2].unlink()
                with self.assertRaisesRegex(RuntimeError, "complete"):
                    scenario_package.ensure_park(plan)
                run.assert_called_once()

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
