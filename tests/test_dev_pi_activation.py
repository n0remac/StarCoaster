import hashlib
import importlib.util
import os
import subprocess
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
        (self.root / "hold").write_text("old pause\n")
        with patch.object(activation, "run", side_effect=lambda *args: calls.append(args)), \
             patch.object(activation, "serving_revision", return_value=True):
            activation.activate(self.REVISION, self.root, self.override)
        self.assertEqual((self.root / "current").resolve(), self.candidate)
        self.assertFalse((self.root / "hold").exists())
        self.assertIn(str(self.root / "current"), self.override.read_text())
        self.assertEqual((self.root / "legacy-service-override.conf").read_text(),
                         "[Service]\nWorkingDirectory=/legacy-dev\n")
        self.assertNotIn("100.119.114.99", self.override.read_text())
        self.assertEqual(calls[-1], ("systemctl", "--user", "restart", activation.SERVICE))

    def test_manual_rollback_restores_legacy_dev_service(self):
        original = self.override.read_bytes()
        with patch.object(activation, "run"), patch.object(activation, "serving_revision", return_value=True):
            activation.activate(self.REVISION, self.root, self.override)
            activation.rollback(self.root, self.override)
        self.assertFalse((self.root / "current").is_symlink())
        self.assertEqual(self.override.read_bytes(), original)
        self.assertTrue((self.root / "hold").is_file())

    def test_manual_rollback_selects_previous_versioned_release(self):
        previous = self.root / "releases" / ("b" * 40)
        previous.mkdir()
        (self.root / "current").symlink_to(Path("releases") / self.REVISION)
        (self.root / "previous").symlink_to(Path("releases") / previous.name)
        self.override.write_text(activation.override_text(self.root))
        with patch.object(activation, "run"), patch.object(activation, "serving_revision", return_value=True), \
             patch.object(activation, "verify_release"):
            activation.rollback(self.root, self.override)
        self.assertEqual((self.root / "current").resolve(), previous)
        self.assertTrue((self.root / "hold").is_file())

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

    def test_failed_rollback_snapshot_restores_legacy_service(self):
        original = self.override.read_bytes()
        replace = activation.replace_file

        def fail_snapshot(path, data):
            if path.name == "legacy-service-override.conf":
                raise OSError("snapshot failed")
            replace(path, data)

        with patch.object(activation, "run"), patch.object(activation, "serving_revision", return_value=True), \
             patch.object(activation, "replace_file", side_effect=fail_snapshot):
            with self.assertRaisesRegex(OSError, "snapshot failed"):
                activation.activate(self.REVISION, self.root, self.override)
        self.assertFalse((self.root / "current").is_symlink())
        self.assertEqual(self.override.read_bytes(), original)

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

    def test_worker_override_routes_automatic_release_to_dev_builder(self):
        config = (Path(__file__).resolve().parents[1] /
                  "deploy/starcoaster-dev-worker.conf").read_text()
        self.assertIn("/media/pi/media1/starcoaster-dev-build/scripts/update-dev-pi-game.sh", config)
        self.assertNotIn("update-pi-game.sh", config)
        self.assertNotIn("100.119.114.99", config)

    def test_manual_rollback_refuses_non_dev_host(self):
        fake_bin = Path(self.temporary.name) / "bin"
        fake_bin.mkdir()
        hostname = fake_bin / "hostname"
        hostname.write_text("#!/bin/sh\necho not-dev\n")
        hostname.chmod(0o755)
        script = Path(__file__).resolve().parents[1] / "scripts/deploy-dev-pi.sh"
        for action in ("--rollback", "--resume"):
            result = subprocess.run(["bash", str(script), action],
                                    env={**os.environ, "PATH": str(fake_bin) + ":" + os.environ["PATH"]},
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Refusing non-DEV host", result.stderr)


if __name__ == "__main__":
    unittest.main()
