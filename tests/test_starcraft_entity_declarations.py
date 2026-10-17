"""One-file extension and validation tests in isolated project trees."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads((ROOT / "tests/fixtures/starcraft_entity_baseline.json").read_text())
OUTPUTS = ["bridge-protocol/starcraft-types.json", "bridge-protocol/starcraft-visuals.json",
           *BASELINE["generated_sha256"]]
INPUTS = [*OUTPUTS, "upstream/bwapi/bwapi/include/BWAPI/UnitType.h",
          "upstream/openrct2/resources/g2/sprites.json",
          "scripts/install-bridge-sprites.py", "scripts/prepare-starcraft-sprites.py",
          "scripts/generate-starcraft-visual-registry.py",
          "scripts/install-starcraft-construction-object.py"]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class EntityDeclarationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in INPUTS:
            source, destination = ROOT / name, self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        shutil.copytree(ROOT / "bridge-protocol/entities", self.root / "bridge-protocol/entities")

    def run_generator(self, *args, succeeds=True):
        process = subprocess.run([sys.executable, str(ROOT / "scripts/generate-starcraft-types.py"),
                                  "--root", str(self.root), *args], text=True, capture_output=True)
        if succeeds:
            self.assertEqual(process.returncode, 0, process.stderr)
        else:
            self.assertNotEqual(process.returncode, 0)
        return process.stderr

    def entity(self, ident):
        return self.root / "bridge-protocol/entities" / (ident + ".json")

    def write_entity(self, entity):
        self.entity(entity["id"]).write_text(json.dumps(entity, indent=2) + "\n")

    def ghost(self):
        ghost = json.loads(self.entity("terran_marine").read_text())
        declarations = [json.loads(path.read_text()) for path in
                        (self.root / "bridge-protocol/entities").glob("*.json")]
        unit_order = max(item["registry_order"] for item in declarations if item["kind"] == "unit")
        bank_order = max(item["visual"]["g2_order"] for item in declarations if item["kind"] == "unit")
        ghost.update(id="terran_ghost", native_type="Terran_Ghost", display_name="Ghost",
                     registry_order=unit_order + 10, spawnable=False, legacy_static_base=0,
                     produced_at="terran_barracks")
        ghost["visual"].update(asset="ghost", g2_order=bank_order + 1, source="unit/terran/ghost.grp")
        return ghost

    def starport(self):
        building = json.loads(self.entity("terran_academy").read_text())
        building_order = max(json.loads(path.read_text())["registry_order"] for path in
                             (self.root / "bridge-protocol/entities").glob("*.json")
                             if json.loads(path.read_text())["kind"] == "building")
        building.update(id="terran_starport", native_type="Terran_Starport",
                        display_name="Terran Starport", registry_order=building_order + 10,
                        object_id="starcoaster.scenery_large.terran_starport",
                        width=4, height=3, max_health=1300)
        building["visual"].update(image="Starport", asset="starport")
        return building

    def hashes(self):
        return {name: hashlib.sha256((self.root / name).read_bytes()).hexdigest() for name in OUTPUTS}

    def test_new_zerg_declarations_preserve_established_catalog(self):
        catalog = json.loads((self.root / OUTPUTS[0]).read_text())
        established = BASELINE["catalogs"]["starcraft-types.json"]["units"]
        self.assertEqual(catalog["units"][:len(established)], established)
        self.assertEqual([(unit["id"], unit["native_type"], unit["spawnable"], unit["legacy_static_base"])
                          for unit in catalog["units"][len(established):]],
                         [("zerg_hydralisk", "Zerg_Hydralisk", True, 0),
                          ("zerg_ultralisk", "Zerg_Ultralisk", True, 0)])
        visuals = json.loads((self.root / OUTPUTS[1]).read_text())["units"]
        for name, order in (("hydralisk", 7), ("ultralisk", 8)):
            self.assertEqual(visuals["zerg_" + name]["g2_order"], order)
            self.assertIn('"zerg_' + name + '": {ID:',
                          (self.root / "internal/world/starcraft_types.go").read_text())
            self.assertIn('BWAPI::UnitTypes::Zerg_' + name.capitalize(),
                          (self.root / "openbw-bwapi-module/src/WorldStarcraftTypes.h").read_text())
            self.assertIn('zerg_' + name + ': { name:',
                          (self.root / "openrct2-plugin/rts-bridge.js").read_text())

    def test_new_unit_from_one_declaration(self):
        self.write_entity(self.ghost())
        self.run_generator()
        catalog = json.loads((self.root / OUTPUTS[0]).read_text())
        visuals = json.loads((self.root / OUTPUTS[1]).read_text())
        ghost = next(unit for unit in catalog["units"] if unit["id"] == "terran_ghost")
        self.assertEqual((ghost["native_type"], ghost["spawnable"], ghost["legacy_static_base"]),
                         ("Terran_Ghost", False, 0))
        self.assertEqual(visuals["units"]["terran_ghost"]["asset"], "ghost")
        barracks = next(building for building in catalog["buildings"] if building["id"] == "terran_barracks")
        self.assertEqual(barracks["production"],
                         ["terran_marine", "terran_firebat", "terran_medic", "terran_ghost"])
        established = BASELINE["catalogs"]["starcraft-types.json"]["units"]
        self.assertEqual(catalog["units"][:len(established)], established)
        self.assertIn('"terran_ghost": {ID: "terran_ghost", NativeType: "Terran_Ghost"',
                      (self.root / "internal/world/starcraft_types.go").read_text())
        self.assertIn('BWAPI::UnitTypes::Terran_Ghost',
                      (self.root / "openbw-bwapi-module/src/WorldStarcraftTypes.h").read_text())
        self.assertIn('terran_ghost: { name: "Ghost"',
                      (self.root / "openrct2-plugin/rts-bridge.js").read_text())
        world = json.loads((self.root / "bridge-protocol/world.v1.schema.json").read_text())
        self.assertIn("terran_ghost", world["$defs"]["actorIdentity"]["properties"]["type"]["enum"])
        self.assertNotIn("terran_ghost", world["$defs"]["spawnRequest"]["properties"]["unit_type"]["enum"])
        snapshot = json.loads((self.root / "bridge-protocol/scenario.snapshot.v3.schema.json").read_text())
        self.assertIn("terran_ghost", snapshot["properties"]["units"]["items"]["properties"]["kind"]["enum"])

        sprites = module(self.root / "scripts/install-bridge-sprites.py", "fixture_sprites")
        self.assertIn("ghost", module(self.root / "scripts/prepare-starcraft-sprites.py",
                                      "fixture_prepare").registered_profiles())
        g2 = self.root / "upstream/openrct2/resources/g2/sprites.json"
        source = self.root / "assets/pack.json"
        extended = sprites.ensure_registered_banks(g2.read_text(), source,
                                                   "alien-scout")
        extended = sprites.stage_registered_banks(source, "alien-scout",
                                                  self.root / "upstream/openrct2", extended,
                                                  {(117, 140, 154)}, [])
        self.assertTrue((self.root / "run-data/generated-assets/placeholder/ghost/idle0_east.png").is_file())
        g2.write_text(extended)
        paths = [entry["path"] for entry in json.loads(extended)]
        self.assertEqual(paths[:len(BASELINE["sprite_paths"])], BASELINE["sprite_paths"])
        self.assertGreaterEqual(paths.index("bridge/ghost/idle0_east.png"), len(BASELINE["sprite_paths"]))
        self.assertEqual(len(paths) - paths.index("bridge/ghost/idle0_east.png"), 67)
        registry = module(self.root / "scripts/generate-starcraft-visual-registry.py", "fixture_registry")
        paint = self.root / "upstream/openrct2/src/openrct2/paint"
        paint.mkdir(parents=True)
        registry.generate(self.root / "upstream/openrct2")
        self.assertIn("kBridge_ghost_body", (paint / "BridgeVisualRegistry.h").read_text())
        self.run_generator("--check")

    def test_new_building_from_one_declaration(self):
        self.write_entity(self.starport())
        self.run_generator()
        catalog = json.loads((self.root / OUTPUTS[0]).read_text())
        visuals = json.loads((self.root / OUTPUTS[1]).read_text())
        starport = next(item for item in catalog["buildings"] if item["id"] == "terran_starport")
        self.assertEqual((starport["object_id"], starport["width"], starport["height"], starport["production"]),
                         ("starcoaster.scenery_large.terran_starport", 4, 3, []))
        self.assertEqual(visuals["buildings"]["terran_starport"]["asset"], "starport")
        self.assertEqual(catalog["buildings"][:-1], BASELINE["catalogs"]["starcraft-types.json"]["buildings"])
        self.assertIn('BWAPI::UnitTypes::Terran_Starport',
                      (self.root / "openbw-bwapi-module/src/WorldStarcraftTypes.h").read_text())
        self.assertIn('"terran_starport": {ID: "terran_starport", NativeType: "Terran_Starport"',
                      (self.root / "internal/world/starcraft_types.go").read_text())
        self.assertIn('terran_starport: { name: "Terran Starport"',
                      (self.root / "openrct2-plugin/rts-bridge.js").read_text())
        objects = module(self.root / "scripts/install-starcraft-construction-object.py", "fixture_objects")
        art = Image.new("P", (140, 140), 10)
        with patch.object(objects, "building_images", return_value=[art]):
            destination = objects.install(self.root / "objects", self.root, "terran_starport")
        with zipfile.ZipFile(destination) as archive:
            definition = json.loads(archive.read("object.json"))
            self.assertEqual(definition["id"], starport["object_id"])
            self.assertEqual(definition["strings"]["name"]["en-GB"], "Terran Starport")
            self.assertEqual(len(definition["properties"]["tiles"]), 12)
            self.assertEqual(len(definition["images"]), 4 + 12 * 4)
        self.run_generator("--check")

    def test_negative_declarations(self):
        cases = [
            ("id", lambda e: e.update(id="terran_marine"), "id:"),
            ("order", lambda e: e.update(registry_order=60), "registry_order:"),
            ("native", lambda e: e.update(native_type="Terran_Unknown"), "native_type:"),
            ("producer missing", lambda e: e.update(produced_at="terran_dropship"), "produced_at:"),
            ("producer nonbuilding", lambda e: e.update(produced_at="terran_marine"), "produced_at:"),
            ("producer disabled", lambda e: e.update(produced_at="terran_academy"), "produced_at:"),
            ("movement", lambda e: e.update(movement="air"), "movement:"),
            ("commands", lambda e: e["commands"].append("unit.cloak"), "commands"),
            ("animation", lambda e: e["visual"]["animations"]["idle"].update(banks=[99]), "visual"),
            ("attachment", lambda e: e["visual"].update(attachments=[{
                "name": "turret", "image": "Ghost", "source": "unit/terran/ghost.grp",
                "canvas": [64, 64], "frame_count": 229, "stride": 17,
                "facing": "unsupported", "layer": "above_body",
                "animations": {"idle": {"banks": [0], "ticks": 0}}}]), "visual"),
            ("effect owner", lambda e: e.update(owned_effects={"firebat_flame": json.loads(
                self.entity("terran_firebat").read_text())["owned_effects"]["firebat_flame"]}),
             "owned_effects"),
            ("field", lambda e: e.update(cloaked=True), "cloaked: unknown field"),
            ("version", lambda e: e.update(schema_version=2), "schema_version:"),
        ]
        for label, change, expected in cases:
            with self.subTest(label=label):
                entity = self.ghost()
                change(entity)
                self.entity("terran_ghost").write_text(json.dumps(entity, indent=2) + "\n")
                error = self.run_generator("--check", succeeds=False)
                self.assertIn(expected, error)
                self.entity("terran_ghost").unlink(missing_ok=True)
        building = self.starport()
        building["object_id"] = "starcoaster.scenery_large.terran_barracks"
        self.write_entity(building)
        self.assertIn("object_id:", self.run_generator("--check", succeeds=False))

    def test_determinism_and_read_only_check(self):
        self.run_generator()
        before = self.hashes()
        self.run_generator()
        self.assertEqual(self.hashes(), before)
        marine = json.loads(self.entity("terran_marine").read_text())
        marine["display_name"] = "Marine Fixture"
        self.write_entity(marine)
        self.assertIn("stale", self.run_generator("--check", succeeds=False))
        self.assertEqual(self.hashes(), before)
        self.run_generator()
        self.assertNotEqual(self.hashes(), before)
        self.run_generator("--check")


if __name__ == "__main__":
    unittest.main()
