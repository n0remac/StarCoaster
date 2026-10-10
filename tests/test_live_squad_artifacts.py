"""Integration assertions against an optional retained 65-second local capture."""

import itertools
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from squad_verification import compare_clients, parse_projected
from video_capture import probe_video


DEMO = ROOT / "run-data/squad-demo"


@unittest.skipUnless((DEMO / "verification.json").is_file(), "local squad demo has not been recorded")
class LiveSquadArtifactTests(unittest.TestCase):
    def test_authoritative_lifecycle_and_video(self):
        logs = {name: (DEMO / f"{name}.log").read_text(errors="replace")
                for name in ("server", "client-a", "client-b")}
        report = compare_clients(logs, 100)
        self.assertEqual(report["mismatches"], 0)
        self.assertGreater(report["eight_unit_snapshots"], 100)
        self.assertGreater(report["seven_unit_snapshots"], 5)
        self.assertGreaterEqual(report["empty_snapshots"], 2)
        self.assertEqual(len(report["sessions"]), 2)
        self.assertEqual(len(report["stable_ids"]), 8)
        video = probe_video(DEMO / "combined.mp4", (1920, 600))
        self.assertGreater(video["duration_seconds"], 65)
        self.assertEqual(video["stream_fps"], "10")

    def test_overlap_separates_and_elevation_varies(self):
        states = parse_projected((DEMO / "server.log").read_text(errors="replace"))
        heights = {actor[5] for value in states.values() for actor in value["actors"]}
        self.assertGreaterEqual(len(heights), 2)
        overlapped = set()
        separated = set()
        for (_session, _seq), value in states.items():
            for a, b in itertools.combinations(value["actors"], 2):
                pair = tuple(sorted((a[0], b[0])))
                if (a[1] // 32, a[2] // 32) == (b[1] // 32, b[2] // 32):
                    overlapped.add(pair)
                elif pair in overlapped:
                    separated.add(pair)
        self.assertTrue(separated, "two actors must share a tile and later separate")
        summary = json.loads((DEMO / "verification.json").read_text())
        self.assertEqual(summary["max_visible_in_one_capture"], {"client-a": 8, "client-b": 8})
        matched = json.loads((DEMO / "sprite-match.json").read_text())
        self.assertGreaterEqual(len(matched["exactly_matched_poses"]), 4)
        self.assertGreaterEqual(sum(item["score"] >= 0.8 for item in matched["matches"]), 4)


if __name__ == "__main__":
    unittest.main()
