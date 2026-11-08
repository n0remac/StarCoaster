"""Clean builds must retain the sprite IDs established by incremental builds."""
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sprite_installer", ROOT / "scripts/install-bridge-sprites.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
ORDER = json.loads((ROOT / "bridge-protocol/starcraft-sprite-order.json").read_text())

class SpriteOrderTests(unittest.TestCase):
    def test_historical_baseline_and_command_ids(self):
        self.assertEqual(hashlib.sha256("\n".join(ORDER[:1092]).encode()).hexdigest(),
                         "4904158f6f070aea1d855f36c807a5fe868b68d4c6c4ba6440425325514991dc")
        self.assertEqual(29357 + ORDER.index("bridge/command/terran_marine.png"), 30698)

    def test_clean_and_incremental_orders_converge_without_changing_metadata(self):
        expected = [{"path": path, "x": -index, "y": 7} for index, path in enumerate(ORDER)]
        fresh = list(expected)
        random.Random(7).shuffle(fresh)
        self.assertEqual(installer.stable_sprite_entries(fresh), expected)
        self.assertEqual(installer.stable_sprite_entries(expected), expected)

    def test_new_paths_follow_established_ids_deterministically(self):
        known = [{"path": path} for path in ORDER]
        result = installer.stable_sprite_entries([{"path": "bridge/new/z.png"}, *known,
                                                  {"path": "bridge/new/a.png"}])
        self.assertEqual(result[:len(known)], known)
        self.assertEqual([entry["path"] for entry in result[-2:]],
                         ["bridge/new/a.png", "bridge/new/z.png"])

    def test_duplicate_path_is_rejected(self):
        with self.assertRaises(ValueError):
            installer.stable_sprite_entries([{"path": ORDER[0]}, {"path": ORDER[0]}])

    def test_retired_resource_slots_remain_in_a_clean_build(self):
        with tempfile.TemporaryDirectory() as directory:
            roots = {"mineral_field/idle0.png", "mineral_field/very_low0.png",
                     "vespene_geyser/idle0.png"}
            prepared = []
            for name in sorted(roots):
                path = Path(directory) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"sprite")
                prepared.append((path, name))
            contents = json.dumps([{"path": "bridge/" + name, "x": -12, "y": -8}
                                   for name in sorted(roots)])
            result = json.loads(installer.preserve_retired_resource_ids(contents, prepared))
            paths = {entry["path"] for entry in result}
            expected = {"bridge/" + asset + "/" + old + ".png"
                        for asset, aliases in installer.RETIRED_RESOURCE_ALIASES.items()
                        for old in aliases}
            self.assertTrue(expected <= paths)
            self.assertEqual(len(result), len(roots) + len(expected))
            self.assertEqual(len(prepared), len(roots) + len(expected))
