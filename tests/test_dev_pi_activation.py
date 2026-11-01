import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "dev_activation", Path(__file__).resolve().parents[1] / "scripts/activate-dev-pi.py")
activation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(activation)


class DevActivationTests(unittest.TestCase):
    REVISION = "a" * 40

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "releases-root"
        self.candidate = self.root / "releases" / self.REVISION
        self.candidate.mkdir(parents=True)
        self.override = Path(self.temporary.name) / "old-pi.conf"
        self.override.write_text("[Service]\nWorkingDirectory=/legacy-dev\n")
        files = {
            "REVISION": self.REVISION.encode() + b"\n",
            "scripts/run-pi-game.sh": b"#!/bin/bash\n",
            "build/world-bridge": b"bridge",
            "build/wasm-server": b"server",
            "build/openrct2/openrct2-cli": b"openrct2",
            "build/bridge-module/BridgeAIModule.so": b"module",
            "run-data/wasm-deploy/current/manifest.json": b"{}",
        }
        for name, contents in files.items():
            path = self.candidate / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        (self.candidate / "SHA256SUMS").write_text("".join(
            hashlib.sha256(contents).hexdigest() + "  " + name + "\n"
            for name, contents in sorted(files.items())))

    def test_activation_switches_to_validated_dev_release(self):
        calls = []
        with patch.object(activation, "run", side_effect=lambda *args: calls.append(args)), \
             patch.object(activation, "serving_revision", return_value=True):
            activation.activate(self.REVISION, self.root, self.override)
        self.assertEqual((self.root / "current").resolve(), self.candidate)
        self.assertIn(str(self.root / "current"), self.override.read_text())
        self.assertNotIn("100.119.114.99", self.override.read_text())
        self.assertEqual(calls[-1], ("systemctl", "--user", "restart", activation.SERVICE))

    def test_failed_readiness_restores_prior_link_and_service_configuration(self):
        previous = self.root / "releases" / ("b" * 40)
        previous.mkdir()
        (self.root / "current").symlink_to(Path("releases") / previous.name)
        original = self.override.read_bytes()
        calls = []
        with patch.object(activation, "run", side_effect=lambda *args: calls.append(args)), \
             patch.object(activation, "serving_revision", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "did not serve"):
                activation.activate(self.REVISION, self.root, self.override)
        self.assertEqual((self.root / "current").resolve(), previous)
        self.assertEqual(self.override.read_bytes(), original)
        self.assertEqual(calls.count(("systemctl", "--user", "restart", activation.SERVICE)), 2)

    def test_tampering_cannot_switch_release(self):
        (self.candidate / "build/world-bridge").write_bytes(b"tampered")
        with patch.object(activation, "run") as run:
            with self.assertRaisesRegex(ValueError, "checksum"):
                activation.activate(self.REVISION, self.root, self.override)
        run.assert_not_called()
        self.assertFalse((self.root / "current").exists())
        self.assertEqual(self.override.read_text(), "[Service]\nWorkingDirectory=/legacy-dev\n")

    def test_mutable_session_data_does_not_invalidate_immutable_release(self):
        runtime = self.candidate / "run-data/park-supervisor/sessions/first"
        runtime.mkdir(parents=True)
        (runtime / "session.log").write_text("ready\n")
        activation.verify_release(self.candidate, self.REVISION)


if __name__ == "__main__":
    unittest.main()
