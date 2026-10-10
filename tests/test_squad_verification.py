import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from squad_verification import compare_clients, parse_applied, parse_projected, project


class SquadVerificationTests(unittest.TestCase):
    def test_canonical_sets_ignore_actor_order(self):
        first = "RTS Bridge apply tick=10 seq=1 session=" + "a" * 32 + " units=openbw:1,320,480,0,walk;openbw:2,350,480,32,idle\n"
        second = "RTS Bridge apply tick=11 seq=1 session=" + "a" * 32 + " units=openbw:2,350,480,32,idle;openbw:1,320,480,0,walk\n"
        result = compare_clients({"server": first, "client-a": second, "client-b": first}, 1)
        self.assertEqual(result["common_snapshots"], 1)
        self.assertEqual(result["mismatches"], 0)

    def test_duplicate_and_mismatch(self):
        line = "RTS Bridge apply tick=10 seq=1 session=" + "a" * 32 + " units=openbw:1,320,480,0,walk"
        with self.assertRaises(ValueError):
            parse_applied(line + ";openbw:1,321,480,0,walk")
        with self.assertRaises(ValueError):
            compare_clients({"server": line, "client-a": line.replace("320", "321"), "client-b": line}, 1)

    def test_projection_rotations(self):
        self.assertEqual(project(480, 480, 0), (640, 400))
        self.assertEqual(project(480, 480, 1), (640, 400))
        self.assertNotEqual(project(512, 480, 0), project(512, 480, 1))

    def test_projected_height_and_lifecycle(self):
        session = "b" * 32
        lines = [
            f"RTS Bridge apply tick=1 seq=1 session={session} center_z=112 units=openbw:1,320,480,0,walk,128",
            f"RTS Bridge apply tick=2 seq=2 session={session} center_z=112 units=",
        ]
        projected = parse_projected("\n".join(lines))
        self.assertEqual(projected[session, 1]["actors"][0][-1], 128)
        self.assertEqual(projected[session, 2]["actors"], ())
        summary = compare_clients({name: "\n".join(lines) for name in ("server", "client-a", "client-b")}, 2)
        self.assertEqual(summary["empty_snapshots"], 1)


if __name__ == "__main__":
    unittest.main()
