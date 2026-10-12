import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "run-data/frontier-playable"
sys.path.insert(0, str(ROOT / "scripts"))
from frontier_geometry import validate, wall_edge  # noqa: E402


class FrontierParkGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_path = DATA / "fixture.json"
        fixture = json.loads(fixture_path.read_text()) if fixture_path.exists() else {}
        if fixture.get("layout_version") != 2:
            subprocess.run(["python3", "scripts/create-park-assault.py", "--playable"],
                           cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        cls.fixture = json.loads(fixture_path.read_text())
        cls.export = json.loads((DATA / "navigation-elements.json").read_text())

    def test_real_wall_edges_and_connected_paths(self):
        report = validate(self.export, self.fixture)
        self.assertGreaterEqual(report["wall_segments"], 100)
        self.assertGreaterEqual(report["path_tiles"], 200)

    def test_wall_connectivity_survives_four_camera_rotations(self):
        edges = [wall_edge(item) for item in self.export["elements"] if item["type"] == "wall"]
        for rotation in range(4):
            def rotate(point):
                x, y = point
                for _ in range(rotation):
                    x, y = 64 - y, x
                return x, y
            turned = [tuple(sorted((rotate(a), rotate(b)))) for a, b in edges]
            self.assertEqual(len(turned), len(set(turned)))
            self.assertTrue(all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1
                                for a, b in turned))


if __name__ == "__main__":
    unittest.main()
