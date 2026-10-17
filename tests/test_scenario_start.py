"""Fast parser and dispatch checks for the full bootstrap entry point."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ScenarioStartTest(unittest.TestCase):
    def run_start(self, *args, env=None):
        return subprocess.run(["scripts/project.sh", "start", *args], cwd=ROOT,
                              env=env, text=True, capture_output=True)

    def test_help_and_invalid_options_are_early(self):
        for args, expected in ((["--help"], "--scenario ID"),
                               (["--scenario"], "Missing value"),
                               (["--scenario", "missing"], "missing scenario package"),
                               (["--unknown"], "Unknown option"),
                               (["--headless", "--client"], "cannot be combined")):
            with self.subTest(args=args):
                result = self.run_start(*args, env=os.environ | {"RCT2_DATA_DIR": "/does/not/exist"})
                self.assertIn(expected, result.stdout + result.stderr)
                self.assertEqual(result.returncode == 0, args == ["--help"])
                self.assertNotIn("Fetching pinned", result.stdout)

    def test_selected_scenario_reaches_one_play_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copy(ROOT / "scripts/start.sh", scripts / "start.sh")
            (scripts / "project.sh").write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$TEST_CALLS\"\n")
            (scripts / "project.sh").chmod(0o755)
            (scripts / "play-scenario.py").write_text("import sys\nassert sys.argv[-1] == '--plan'\n")
            for name in ("fetch-upstream.py", "prepare-starcraft-sprites.py",
                         "generate-starcraft-types.py"):
                (scripts / name).write_text("")
            (scripts / "install-openrct2-local.sh").write_text("#!/bin/sh\nexit 0\n")
            (scripts / "install-openrct2-local.sh").chmod(0o755)
            rct2 = root / "rct2"
            starcraft = root / "starcraft"
            rct2.mkdir()
            starcraft.mkdir()
            for archive in ("StarDat.mpq", "BrooDat.mpq", "Patch_rt.mpq"):
                (starcraft / archive).touch()
            calls = root / "calls.txt"
            env = os.environ | {"RCT2_DATA_DIR": str(rct2), "STARCRAFT_DATA_DIR": str(starcraft),
                                "BRIDGE_SPRITE_SOURCE": "alien-scout", "TEST_CALLS": str(calls)}
            for args, selected in (([], "frontier-outpost"),
                                   (["--scenario", "example-defense", "--headless"], "example-defense")):
                calls.write_text("")
                result = subprocess.run([str(scripts / "start.sh"), *args], cwd=root, env=env,
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(calls.read_text().splitlines(), ["build", f"play {selected}"])


if __name__ == "__main__":
    unittest.main()
