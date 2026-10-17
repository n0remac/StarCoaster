"""Pin the iscript-derived Zerg poses and their local GRP extraction."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "run-data/generated-assets/starcraft"
DIRECTIONS = {"east": (8, False), "southeast": (12, False),
              "south": (16, False), "southwest": (12, True),
              "west": (8, True), "northwest": (4, True),
              "north": (0, False), "northeast": (4, False)}
SEQUENCES = {
    "zergling": {"idle": [5], "walk": [6, 7, 8, 9, 10, 11, 5],
                  "attack": [0, 1, 2, 3, 4, 5], "death": list(range(289, 296))},
    "hydralisk": {"idle": [5], "walk": [6, 7, 8, 9, 10, 11, 5],
                   "attack": [0, 1, 2, 3, 4, 3, 2, 1, 0, 5],
                   "death": list(range(204, 212))},
    "ultralisk": {"idle": [9], "walk": list(range(10)),
                   "attack": [14, 13, 12, 11, 12, 13, 14],
                   "death": list(range(255, 265))},
}
G2_BASELINE_COUNT = 1092
G2_BASELINE_SHA256 = "4904158f6f070aea1d855f36c807a5fe868b68d4c6c4ba6440425325514991dc"
GAME = Path(os.environ.get("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft"))


def iscript_frames(data: bytes, address: int, opcode_names: list[str], formats: dict) -> list[int]:
    """Follow the original script until it repeats or ends, collecting playfram operands."""
    seen, frames = set(), []
    for _ in range(100):
        if address in seen:
            break
        seen.add(address)
        name = opcode_names[data[address]]
        cursor, arguments = address + 1, []
        for field in formats[name]:
            if field == "s":
                continue  # signedness changes the value, not the operand width
            if field == "1":
                arguments.append(data[cursor]); cursor += 1
            elif field in "2jb":
                arguments.append(struct.unpack_from("<H", data, cursor)[0]); cursor += 2
            elif field == "v":
                count = data[cursor]; cursor += 1 + 2 * count
        if name in ("playfram", "playframtile"):
            frames.append(arguments[0])
        if name in ("end", "return"):
            break
        address = arguments[0] if name == "goto" else cursor
    return frames


def original_zerg_scripts(images: bytes, iscript: bytes) -> dict[str, dict[str, list[int]]]:
    enum = (ROOT / "upstream/openbw/bwenums.h").read_text().split(
        "enum struct ImageTypes : int {", 1)[1].split("};", 1)[0]
    image_names = re.findall(r"\bIMAGEID_[A-Za-z0-9_]+\b", enum)
    types = (ROOT / "upstream/openbw/data_types.h").read_text().split(
        "namespace iscript_opcodes {", 1)[1].split("};", 1)[0]
    opcode_names = re.findall(r"\bopc_(\w+)\b", types)
    loader = (ROOT / "upstream/openbw/bwgame.h").read_text().split(
        "ins_data[opc_playfram] =", 1)[1].split("a_unordered_map<int, a_vector<size_t>> animation_pc", 1)[0]
    formats = dict(re.findall(r'ins_data\[opc_(\w+)\] = "([^"]*)"',
                              'ins_data[opc_playfram] =' + loader))
    scripts = {}
    cursor = struct.unpack_from("<I", iscript)[0]
    while True:
        script_id, address = struct.unpack_from("<hH", iscript, cursor); cursor += 4
        if script_id == -1:
            break
        scripts[script_id] = address
    result = {}
    for unit in SEQUENCES:
        image = image_names.index("IMAGEID_" + unit.capitalize())
        # images.dat: one uint32 GRP array, six byte arrays, then uint32 iscript IDs.
        script_id = struct.unpack_from("<I", images, 999 * 10 + image * 4)[0]
        header = scripts[script_id]
        animation_addresses = [struct.unpack_from("<H", iscript, header + 8 + index * 2)[0]
                               for index in (0, 1, 2, 11)]
        result[unit] = dict(zip(("idle", "death", "attack", "walk"),
                                (iscript_frames(iscript, address, opcode_names, formats)
                                 for address in animation_addresses)))
    return result


class ZergAnimationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("smpq") and all(
        (GAME / archive).is_file()
        for archive in ("Patch_rt.mpq", "BrooDat.mpq")),
        "local licensed StarCraft MPQs or smpq are unavailable")
    def test_authored_sequences_match_original_iscript(self):
        game = GAME
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            for archive, resource in (("Patch_rt.mpq", "scripts/iscript.bin"),
                                      ("BrooDat.mpq", "arr/images.dat")):
                subprocess.run(["smpq", "--extract", str(game / archive), resource],
                               cwd=temporary, check=True, capture_output=True)
            original = original_zerg_scripts((temporary / "arr/images.dat").read_bytes(),
                                            (temporary / "scripts/iscript.bin").read_bytes())
        for unit, states in SEQUENCES.items():
            expected = {state: [bank * 17 for bank in sequence] if state != "death" else sequence
                        for state, sequence in states.items()}
            # Ultralisk iscript returns to idle after the seven attack poses.
            if unit == "ultralisk":
                expected["attack"].append(9 * 17)
            self.assertEqual(original[unit], expected)

    def test_authored_banks_follow_pinned_iscript(self):
        for unit, states in SEQUENCES.items():
            declaration = json.loads((ROOT / f"bridge-protocol/entities/zerg_{unit}.json").read_text())
            animations = declaration["visual"]["animations"]
            self.assertEqual(declaration["id"], f"zerg_{unit}")
            for state, sequence in states.items():
                with self.subTest(unit=unit, state=state):
                    key = "frames" if state == "death" else "banks"
                    self.assertEqual(animations[state][key], sequence)
                    self.assertGreaterEqual(animations[state]["ticks"], 0)
            self.assertTrue(set(states["attack"][:-1]).isdisjoint(range(12, 17))
                            if unit != "ultralisk" else set(states["attack"]).isdisjoint(range(15, 20)))

    @unittest.skipUnless(all((ART / unit / "manifest.json").is_file() for unit in SEQUENCES),
                         "local licensed Zerg sprites have not been prepared")
    def test_manifest_frames_facings_deaths_and_attack_motion(self):
        for unit, states in SEQUENCES.items():
            source = ART / unit
            manifest = json.loads((source / "manifest.json").read_text())
            self.assertEqual(manifest["kind"], f"zerg_{unit}")
            stride = 17
            registry = manifest["registry"][f"zerg_{unit}"]
            for state in ("idle", "walk", "attack"):
                for direction, (facing, mirror) in DIRECTIONS.items():
                    names = registry[state]["frames"][direction]
                    self.assertEqual(len(names), len(states[state]))
                    for name, bank in zip(names, states[state]):
                        with self.subTest(unit=unit, state=state, name=name):
                            meta = manifest["frames"][name]
                            self.assertEqual(meta["source_frame"], bank * stride + facing)
                            self.assertEqual(meta["mirrored"], mirror)
                            self.assertTrue((source / name).is_file())
            for state in ("idle", "walk", "attack"):
                for east, west in (("east", "west"), ("southeast", "southwest"),
                                   ("northeast", "northwest")):
                    for a, b in zip(registry[state]["frames"][east],
                                    registry[state]["frames"][west]):
                        with Image.open(source / a) as original, Image.open(source / b) as mirrored:
                            self.assertEqual(ImageOps.mirror(original).tobytes(), mirrored.tobytes())
            deaths = registry["death"]["frames"]
            self.assertIsInstance(deaths, list)
            self.assertEqual([manifest["frames"][name]["source_frame"] for name in deaths],
                             states["death"])
            self.assertTrue(all(not manifest["frames"][name]["mirrored"] for name in deaths))
            attack_names = registry["attack"]["frames"]["east"]
            idle_name = registry["idle"]["frames"]["east"][0]
            with Image.open(source / idle_name) as idle:
                idle_pixels = idle.tobytes()
            attack_pixels = [(source / name).read_bytes() for name in attack_names]
            self.assertGreaterEqual(len(set(attack_pixels)), 4, f"{unit} attack must visibly move")
            with Image.open(source / attack_names[0]) as first:
                self.assertNotEqual(first.tobytes(), idle_pixels)

    @unittest.skipUnless((ROOT / "upstream/openrct2/resources/g2/sprites.json").is_file(),
                         "pinned OpenRCT2 source has not been fetched")
    def test_existing_g2_ids_are_unchanged(self):
        sprites = json.loads((ROOT / "upstream/openrct2/resources/g2/sprites.json").read_text())
        paths = [sprite["path"] for sprite in sprites]
        self.assertEqual(len(paths), len(set(paths)))
        digest = hashlib.sha256("\n".join(paths[:G2_BASELINE_COUNT]).encode()).hexdigest()
        self.assertEqual(digest, G2_BASELINE_SHA256)
        self.assertTrue(all(path in paths[G2_BASELINE_COUNT:] for path in
                            ("bridge/attack0_east.png", "bridge/death0.png",
                             "bridge/hydralisk/death0.png", "bridge/ultralisk/attack6_east.png")))


if __name__ == "__main__":
    unittest.main()
