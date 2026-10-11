"""Artifact publication never exposes stale or unfinished media."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from artifact_runs import ArtifactRun, ID_PATTERN, atomic_json, run_id


class ArtifactRunTests(unittest.TestCase):
    def test_unique_ids_and_atomic_manifest(self):
        ids = {run_id() for _ in range(1000)}
        self.assertEqual(len(ids), 1000)
        self.assertTrue(all(ID_PATTERN.fullmatch(value) for value in ids))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = ArtifactRun("live-capture", "test", root=root)
            self.assertEqual(json.loads((run.directory / "run.json").read_text())["status"], "running")
            atomic_json(run.directory / "run.json", run.manifest)
            self.assertFalse(list(run.directory.glob("*.tmp")))
            self.assertEqual(run.finalize("passed")["status"], "passed")
            self.assertTrue(run.manifest["finished_at"])

    def test_legacy_failure_copies_only_new_approved_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "legacy"
            output.mkdir()
            (output / "client-a-early.png").write_bytes(b"old")
            (output / "source.mpq").write_bytes(b"private")
            run = ArtifactRun("live-capture", "test", output, root / "artifacts")
            (output / "client-a-final.png").write_bytes(b"new")
            (output / "client-a.log").write_text("normal line\npassword=secret\n")
            (output / "verification.json").write_text('{"status":"failed"}')
            (output / "combined.mp4").write_bytes(b"unfinished")
            result = run.finalize("failed", "verification failed")
            self.assertEqual(result["status"], "failed")
            self.assertEqual([s["path"] for s in result["screenshots"]], ["client-a-final.png"])
            self.assertEqual(result["videos"], [])
            self.assertFalse((run.directory / "combined.mp4").exists())
            self.assertFalse((run.directory / "source.mpq").exists())
            self.assertFalse((run.directory / "client-a-early.png").exists())
            self.assertNotIn("secret", (run.directory / "diagnostic-client-a.log").read_text())
            self.assertEqual(json.loads((run.directory / "verification.json").read_text())["status"], "failed")

    def test_validated_video_only_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "legacy"
            first = ArtifactRun("battle-replay", "one", output, root / "artifacts")
            (output / "combined.mp4").write_bytes(b"first")
            (output / "video-metadata.json").write_text(json.dumps({"outputs": [{"filename": "combined.mp4", "duration_seconds": 1}]}))
            self.assertEqual(len(first.finalize("passed")["videos"]), 1)
            second = ArtifactRun("battle-replay", "two", output, root / "artifacts")
            (output / "combined.mp4").write_bytes(b"second longer")
            (output / "video-metadata.json").write_text(json.dumps({"outputs": [{"filename": "combined.mp4", "validation_error": "bad"}]}))
            self.assertEqual(second.finalize("failed")["videos"], [])
            self.assertNotEqual(first.directory, second.directory)
            self.assertEqual((first.directory / "combined.mp4").read_bytes(), b"first")

    def test_battle_replay_metadata_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            run = ArtifactRun("battle-replay", "replay", root=Path(temp))
            (run.output / "combined.mp4").write_bytes(b"valid")
            (run.output / "video-metadata.json").write_text(json.dumps({"filename": "combined.mp4", "duration_seconds": 5.2}))
            self.assertEqual(run.finalize("passed")["videos"][0]["path"], "combined.mp4")

    def test_siege_configuration_is_published_without_runtime_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "legacy"
            run = ArtifactRun("live-capture", "siege", output, root / "artifacts")
            (output / "scenario-config.json").write_text('{"scenario":"ride-siege"}')
            (output / "ride-siege.scm").write_bytes(b"private map data")
            result = run.finalize("failed", "example")
            self.assertEqual(result["scenario_config_file"], "scenario-config.json")
            self.assertTrue((run.directory / "scenario-config.json").is_file())
            self.assertFalse((run.directory / "ride-siege.scm").exists())


if __name__ == "__main__":
    unittest.main()
