"""Depth ordering for composited replay scenery, without game binaries."""

import importlib.util
from pathlib import Path
import sys
import unittest

from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/render-battle-replay.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("render_battle_replay", SCRIPT)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class BattleReplayOcclusionTests(unittest.TestCase):
    def test_tree_covers_actor_behind_but_not_actor_in_front(self):
        grass = (59, 95, 39)
        tree = (180, 90, 25)
        body = (180, 30, 180)
        background = Image.new("RGB", (1280, 800), grass)
        background.putpixel((768, 390), tree)
        background.putpixel((768, 410), tree)
        scenery = replay.foreground_trees(background)
        self.assertEqual(len(scenery), 2)
        sprite = Image.new("RGBA", (64, 64), (*body, 255))
        zerg = {("idle", direction): (sprite, -32, -64) for direction in replay.DIRS}
        outcome = {"frame": 1000, "result": "zerg"}

        def frame(x, y):
            state = {"frame": 0, "x": x, "y": y, "kind": "zerg_zergling",
                     "hp": 1, "max_hp": 1, "order": "PlayerGuard", "attacking": False,
                     "facing": 0, "id": 1}
            return replay.draw_frame(background, {1: [state]}, {}, 0, outcome,
                                     {}, zerg, 0, 10, scenery)

        behind = frame(448, 512)
        self.assertEqual(behind.getpixel((768, 390)), tree)
        self.assertEqual(behind.getpixel((770, 390)), body)
        in_front = frame(480, 544)
        self.assertEqual(in_front.getpixel((768, 410)), body)


if __name__ == "__main__":
    unittest.main()
