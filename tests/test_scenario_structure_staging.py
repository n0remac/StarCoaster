"""The isolated structure stager needs its objects before OpenRCT2 starts."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("structure_staging", ROOT / "scripts/stage-scenario-structures.py")
staging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(staging)


class StructureStagingTest(unittest.TestCase):
    def test_required_objects_installed_before_launch_and_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.park"
            source.write_bytes(b"PARKoriginal")
            destination = root / "save/derived.park"
            scenario = root / "scenario.json"
            scenario.write_text(json.dumps({"initial_structures": [
                {"id": str(index), "type": kind, "faction": "zerg", "tile": [8 + index * 8, 31]}
                for index, kind in enumerate(["zerg_hatchery", "zerg_hatchery", "zerg_spawning_pool"])]}))
            data = root / "structure-stage"
            installed = []

            def install(command, **kwargs):
                self.assertEqual(command[:3], ["python3", str(ROOT / "scripts/install-starcraft-construction-object.py"), str(data)])
                self.assertEqual(command[3:5], ["--game-dir", "/licensed/starcraft"])
                self.assertEqual(command[5], "--building-type")
                self.assertTrue(kwargs["check"])
                installed.append(command[6])

            def launch(command, stdout, **kwargs):
                self.assertEqual(installed, ["zerg_hatchery", "zerg_spawning_pool"])
                self.assertIn(f"--user-data-path={data}", command)
                staged = data / "save/scenario-structures.park"
                staged.parent.mkdir()
                staged.write_bytes(b"PARKwith structures")
                stdout.write("SCENARIO_STRUCTURES_STAGED []\n")
                stdout.flush()
                return mock.Mock()

            with mock.patch.dict(staging.os.environ, {"STARCRAFT_DATA_DIR": "/licensed/starcraft"}), \
                    mock.patch.object(staging.subprocess, "run", side_effect=install), \
                    mock.patch.object(staging.subprocess, "Popen", side_effect=launch):
                staging.stage(source, destination, scenario)
            self.assertEqual(destination.read_bytes(), b"PARKwith structures")
            self.assertEqual(source.read_bytes(), b"PARKoriginal")

    def test_no_structures_copies_park_without_installing_or_launching(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination, scenario = (root / name for name in ("source.park", "save/copy.park", "scenario.json"))
            source.write_bytes(b"PARKoriginal")
            scenario.write_text("{}")
            with mock.patch.object(staging.subprocess, "run") as install, \
                    mock.patch.object(staging.subprocess, "Popen") as launch:
                staging.stage(source, destination, scenario)
            install.assert_not_called()
            launch.assert_not_called()
            self.assertEqual(destination.read_bytes(), source.read_bytes())
