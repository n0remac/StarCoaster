"""Rebuilding OpenRCT2 must refresh the installed graphics used by clients."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OpenRCT2BuildStagingTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        scripts = self.root / "scripts"
        scripts.mkdir()
        for name in ("build-openrct2.sh", "install-openrct2-local.sh"):
            shutil.copy2(ROOT / "scripts" / name, scripts / name)
        checker = scripts / "check-dependencies.py"
        checker.write_text("#!/usr/bin/env python3\n")
        checker.chmod(0o755)
        patcher = scripts / "apply-openrct2-patches.sh"
        patcher.write_text("#!/bin/sh\nexit 0\n")
        patcher.chmod(0o755)
        tools = self.root / "bin"
        tools.mkdir()
        cmake = tools / "cmake"
        cmake.write_text('''#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import sys
if "--build" in sys.argv:
    if os.environ.get("TEST_BUILD_FAIL"):
        sys.exit(1)
    output = Path(sys.argv[sys.argv.index("--build") + 1]) / "g2.dat"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"rebuilt graphics")
elif "--install" in sys.argv:
    build = Path(sys.argv[sys.argv.index("--install") + 1])
    destination = Path(os.environ["DESTDIR"]) / "usr/local/share/openrct2/g2.dat"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(build / "g2.dat", destination)
''')
        cmake.chmod(0o755)
        self.env = os.environ | {"PATH": str(tools) + os.pathsep + os.environ["PATH"]}
        self.staged = self.root / "build/openrct2-stage/usr/local/share/openrct2/g2.dat"

    def build(self):
        return subprocess.run([str(self.root / "scripts/build-openrct2.sh")],
                              env=self.env, capture_output=True, text=True)

    def test_rebuild_refreshes_existing_staged_graphics(self):
        self.staged.parent.mkdir(parents=True)
        self.staged.write_bytes(b"old graphics")
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.staged.read_bytes(), b"rebuilt graphics")

    def test_fresh_build_leaves_initial_install_to_bootstrap(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.staged.exists())

    def test_failed_build_preserves_installed_graphics(self):
        self.staged.parent.mkdir(parents=True)
        self.staged.write_bytes(b"old graphics")
        self.env["TEST_BUILD_FAIL"] = "1"
        self.assertNotEqual(self.build().returncode, 0)
        self.assertEqual(self.staged.read_bytes(), b"old graphics")
