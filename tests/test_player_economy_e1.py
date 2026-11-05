"""Behavioral contracts for the finite authored economy bootstrap."""

import json
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("create_world_base_map", ROOT / "scripts/create-world-base-map.py")
map_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(map_module)


class EconomyE1Tests(unittest.TestCase):
    def test_sprite_ledger_appends_without_renumbering_e0(self):
        paths = json.loads((ROOT / "bridge-protocol/starcraft-sprite-order.json").read_text())
        self.assertEqual(hashlib.sha256("\n".join(paths[:1355]).encode()).hexdigest(),
                         "21887e075201da8a6fb41b113d713d20a6a6beae2949e2f42bdbb65f419ddbbe")
        for asset in ("scv", "mineral_field", "vespene_geyser"):
            self.assertIn(f"bridge/{asset}/idle0.png" if asset != "scv"
                          else "bridge/scv/idle0_east.png", paths[1355:])

    def test_declarations_include_worker_base_and_neutral_deposits(self):
        catalog = json.loads((ROOT / "bridge-protocol/starcraft-types.json").read_text())
        units = {unit["id"]: unit for unit in catalog["units"]}
        buildings = {building["id"]: building for building in catalog["buildings"]}
        resources = {resource["id"]: resource for resource in catalog["resources"]}
        self.assertTrue({"unit.move", "unit.stop", "unit.gather", "unit.return_cargo"}
                        <= set(units["terran_scv"]["commands"]))
        self.assertEqual(units["terran_scv"]["produced_at"], "terran_command_center")
        self.assertEqual(buildings["terran_command_center"]["production"], ["terran_scv"])
        self.assertEqual(resources["mineral_field"]["ownership"], "neutral")
        self.assertEqual(resources["vespene_geyser"]["ownership"], "neutral")
        self.assertEqual(resources["vespene_geyser"]["native_type"], "Resource_Vespene_Geyser")

    def test_neutral_resources_are_observable_but_not_trainable(self):
        schema = json.loads((ROOT / "bridge-protocol/world.v1.schema.json").read_text())
        command = next(row for row in schema["allOf"] if row.get("if", {}).get("properties", {})
                       .get("kind", {}).get("const") == "combat.command")
        options = command["then"]["properties"]["payload"]["properties"]["unit_type"]["enum"]
        observed = schema["$defs"]["actorIdentity"]["properties"]["type"]["enum"]
        self.assertIn("terran_scv", options)
        for resource in ("mineral_field", "vespene_geyser"):
            self.assertIn(resource, observed)
            self.assertNotIn(resource, options)

    def test_finite_fixture_has_visible_supply_and_real_deposits(self):
        scenario = ROOT / "scenarios/economy-e1/scenario.json"
        configuration = json.loads(scenario.read_text())
        self.assertEqual(configuration["economy"]["mode"], "finite")
        self.assertFalse(configuration.get("unlimited_resources", False))
        self.assertFalse(configuration.get("production_fixture"))
        records = map_module.scenario_units(scenario)
        from starcraft_map_pack import UNIT
        unpacked = [UNIT.unpack(record) for record in records]
        kinds = [record[3] for record in unpacked]
        self.assertEqual(kinds.count(106), 1)  # real Command Center supply
        self.assertEqual(kinds.count(7), 4)  # SCVs
        self.assertEqual(kinds.count(176), 6)  # mineral fields
        self.assertEqual(kinds.count(188), 1)  # geyser
        self.assertNotIn(109, kinds)  # no hidden Depot
        for record in unpacked:
            if record[3] in (176, 188):
                self.assertEqual(record[7], 11)
                self.assertEqual(record[6], 0x10)
                self.assertEqual(record[11], 1500 if record[3] == 176 else 5000)


if __name__ == "__main__":
    unittest.main()
