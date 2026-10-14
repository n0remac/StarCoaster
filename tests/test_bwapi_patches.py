"""Fresh and existing OpenBW checkouts must build the same navigation code."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bwapi_patches", ROOT / "scripts/apply-bwapi-patches.py")
patches = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patches)
CURRENT = ROOT / "openbw-bwapi-module/0002-native-navigation-openbw.patch"
UPGRADE = ROOT / "openbw-bwapi-module/0004-native-navigation-upgrade-openbw.patch"


class BWAPIPatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        checkout = ROOT / "upstream/openbw"
        if not (checkout / ".git").exists():
            raise unittest.SkipTest("pinned OpenBW checkout is unavailable")
        cls.original = subprocess.check_output(["git", "-C", str(checkout), "show", "HEAD:bwgame.h"])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.checkout = Path(self.temporary.name)
        self.source = self.checkout / "bwgame.h"
        self.source.write_bytes(self.original)

    def test_fresh_checkout_and_repeated_build(self):
        self.assertEqual(patches.ensure_patch(self.checkout, CURRENT, UPGRADE), "applied")
        current = self.source.read_bytes()
        self.assertIn(b"park_overlay_variants", current)
        self.assertEqual(patches.ensure_patch(self.checkout, CURRENT, UPGRADE), "current")
        self.assertEqual(self.source.read_bytes(), current)

    def test_upgrade_old_navigation_preserves_unrelated_edits(self):
        patches.ensure_patch(self.checkout, CURRENT)
        expected = self.source.read_bytes() + b"\n// Local unrelated edit.\n"
        subprocess.run(["git", "-C", str(self.checkout), "apply", "--reverse", str(UPGRADE)], check=True)
        self.source.write_bytes(self.source.read_bytes() + b"\n// Local unrelated edit.\n")
        self.assertIn(b"park_overlay_mega_tile_index", self.source.read_bytes())
        self.assertEqual(patches.ensure_patch(self.checkout, CURRENT, UPGRADE), "upgraded")
        self.assertEqual(self.source.read_bytes(), expected)
        self.assertEqual(patches.ensure_patch(self.checkout, CURRENT, UPGRADE), "current")

    def test_conflicting_navigation_is_rejected_without_overwriting(self):
        patches.ensure_patch(self.checkout, CURRENT)
        changed = self.source.read_bytes().replace(b"bool set_park_navigation(", b"bool local_navigation(")
        self.source.write_bytes(changed)
        with self.assertRaisesRegex(RuntimeError, "unexpected source changes"):
            patches.ensure_patch(self.checkout, CURRENT, UPGRADE)
        self.assertEqual(self.source.read_bytes(), changed)
