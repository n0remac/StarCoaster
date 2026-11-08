"""Original command icon extraction and append-only G2 coverage."""

import importlib.util
import json
from pathlib import Path
import re
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "run-data/generated-assets/starcraft/command-icons"


class CommandIconTests(unittest.TestCase):
    def test_scv_uses_its_original_command_frame(self):
        spec = importlib.util.spec_from_file_location(
            "command_icons", ROOT / "scripts/prepare-starcraft-command-icons.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        enum = (ROOT / "upstream/openbw/bwenums.h").read_text().split(
            "enum struct UnitTypes : int {", 1)[1].split("};", 1)[0]
        unit_names = re.findall(r"^\s*([A-Za-z0-9_]+),", enum, re.MULTILINE)
        self.assertEqual(unit_names.index("Terran_SCV"), 7)
        self.assertEqual(module.ICON_FRAMES["terran_scv"], unit_names.index("Terran_SCV"))

    def test_scv_has_a_distinct_generated_button_image(self):
        order = json.loads((ROOT / "bridge-protocol/starcraft-sprite-order.json").read_text())
        path = "bridge/command/terran_scv.png"
        self.assertEqual(order.count(path), 1)
        source = (ROOT / "openrct2-plugin/rts-bridge.js").read_text()
        match = re.search(r"const COMMAND_ICON_IMAGES = Object.freeze\((\{[^\n]+\})\);", source)
        self.assertIsNotNone(match)
        images = json.loads(match.group(1))
        self.assertEqual(images["terran_scv"], 29357 + order.index(path))
        self.assertNotEqual(images["terran_scv"], images["empty"])

    @unittest.skipUnless((ICONS / "manifest.json").is_file(),
                         "licensed original command icons are unavailable")
    def test_local_extraction_contains_scv_art(self):
        manifest = json.loads((ICONS / "manifest.json").read_text())
        self.assertEqual(manifest["icons"]["terran_scv"]["source_frame"], 7)
        image_path = ICONS / manifest["icons"]["terran_scv"]["file"]
        with Image.open(image_path) as image:
            self.assertEqual(image.size, (36, 34))
            self.assertIsNotNone(image.getchannel("A").getbbox())


if __name__ == "__main__":
    unittest.main()
