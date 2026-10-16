"""Existing OpenRCT2 builds must gain the plugin's required native API."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("openrct2_patches", ROOT / "scripts/apply-openrct2-patches.py")
patches = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patches)
PATCH = ROOT / "openrct2-patches/0001-native-bridge.patch"
SHARED_INPUT = ROOT / "openrct2-patches/0004-shared-viewport-input-upgrade.patch"
UPGRADE = ROOT / "openrct2-patches/0002-screen-selection-upgrade.patch"


class OpenRCT2PatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        checkout = ROOT / "upstream/openrct2"
        if not (checkout / ".git").exists():
            raise unittest.SkipTest("pinned OpenRCT2 checkout is unavailable")
        names = [line.split(" b/", 1)[1] for line in PATCH.read_text().splitlines()
                 if line.startswith("diff --git ")]
        cls.original = {name: subprocess.check_output(
            ["git", "-C", str(checkout), "show", "HEAD:" + name]) for name in names}

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.checkout = Path(self.temporary.name)
        for name, contents in self.original.items():
            dest = self.checkout / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(contents)
        self.source = self.checkout / "src/openrct2/scripting/ScriptEngine.cpp"

    def test_fresh_and_repeated_build_with_local_sprite_offsets(self):
        self.assertEqual(patches.ensure_bridge(self.checkout), "applied")
        self.assertIn(b'"actorScreenPosition"', self.source.read_bytes())
        sprites = self.checkout / "resources/g2/sprites.json"
        sprites.write_text(sprites.read_text().replace('"x": -16', '"x": -17'))
        expected = sprites.read_bytes()
        self.assertEqual(patches.ensure_bridge(self.checkout), "current")
        self.assertEqual(sprites.read_bytes(), expected)

    def test_upgrade_shared_input_and_keep_local_edits(self):
        patches.ensure_bridge(self.checkout)
        mouse = self.checkout / "src/openrct2-ui/input/MouseInput.cpp"
        expected = mouse.read_bytes() + b"\n// Local input edit.\n"
        subprocess.run(["git", "-C", str(self.checkout), "apply", "--reverse", str(SHARED_INPUT)], check=True)
        mouse.write_bytes(mouse.read_bytes() + b"\n// Local input edit.\n")
        self.assertEqual(patches.ensure_bridge(self.checkout), "upgraded")
        self.assertEqual(mouse.read_bytes(), expected)
        self.assertEqual(patches.ensure_bridge(self.checkout), "current")

    def test_upgrade_preserves_local_edits(self):
        patches.ensure_bridge(self.checkout)
        expected = self.source.read_bytes() + b"\n// Local unrelated edit.\n"
        subprocess.run(["git", "-C", str(self.checkout), "apply", "--reverse", str(SHARED_INPUT)], check=True)
        subprocess.run(["git", "-C", str(self.checkout), "apply", "--reverse", str(UPGRADE)], check=True)
        self.source.write_bytes(self.source.read_bytes() + b"\n// Local unrelated edit.\n")
        self.assertNotIn(b'"actorScreenPosition"', self.source.read_bytes())
        self.assertEqual(patches.ensure_bridge(self.checkout), "upgraded")
        self.assertEqual(self.source.read_bytes(), expected)
        self.assertEqual(patches.ensure_bridge(self.checkout), "current")

    def test_conflict_does_not_overwrite(self):
        patches.ensure_bridge(self.checkout)
        changed = self.source.read_bytes().replace(b"BridgeActorScreenPositionJS", b"LocalScreenPositionJS")
        self.source.write_bytes(changed)
        with self.assertRaisesRegex(RuntimeError, "unexpected source changes"):
            patches.ensure_bridge(self.checkout)
        self.assertEqual(self.source.read_bytes(), changed)

    def test_upgrade_both_missed_patch_versions(self):
        patches.ensure_bridge(self.checkout)
        expected = {name: (self.checkout / name).read_bytes() for name in self.original}
        for upgrade in (SHARED_INPUT, UPGRADE, ROOT / "openrct2-patches/0003-terrain-rendering-upgrade.patch"):
            subprocess.run(["git", "-C", str(self.checkout), "apply", "--reverse", str(upgrade)], check=True)
        self.assertEqual(patches.ensure_bridge(self.checkout), "upgraded")
        self.assertEqual({name: (self.checkout / name).read_bytes() for name in self.original}, expected)

    def test_conflict_aborts_all_pending_upgrades(self):
        patches.ensure_bridge(self.checkout)
        subprocess.run(["git", "-C", str(self.checkout), "apply", "--reverse", str(SHARED_INPUT)], check=True)
        subprocess.run(["git", "-C", str(self.checkout), "apply", "--reverse", str(UPGRADE)], check=True)
        self.source.write_bytes(self.source.read_bytes().replace(b"BridgeGetActorsJS", b"LocalGetActorsJS"))
        expected = {name: (self.checkout / name).read_bytes() for name in self.original}
        with self.assertRaisesRegex(RuntimeError, "unexpected source changes"):
            patches.ensure_bridge(self.checkout)
        self.assertEqual({name: (self.checkout / name).read_bytes() for name in self.original}, expected)
