"""Schema coverage for typed training and native production reports."""

import json
from pathlib import Path
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(Draft202012Validator, "jsonschema is unavailable")
class StarcraftProtocolSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema = json.loads((ROOT / "bridge-protocol/world.v1.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema)

    def envelope(self, kind, payload, source="openrct2"):
        return {"v": 1, "kind": kind, "session": "session-a", "op_id": "test:1",
                "source": source, "revision": 1, "payload": payload}

    def test_train_unit_type_and_legacy_default(self):
        command = {"command_id": "session-a:1", "player_id": 1, "request_id": 1,
                   "verb": "unit.train", "unit_ids": [], "target_id": "building:1"}
        self.validator.validate(self.envelope("combat.command", command))
        command["unit_type"] = "terran_marine"
        self.validator.validate(self.envelope("combat.command", command))
        command["unit_type"] = "terran_firebat"
        self.validator.validate(self.envelope("combat.command", command))
        command["unit_type"] = "terran_medic"
        self.validator.validate(self.envelope("combat.command", command))
        command["unit_type"] = "terran_vulture"
        self.validator.validate(self.envelope("combat.command", command))
        command["unit_type"] = "terran_ghost"
        self.assertFalse(self.validator.is_valid(self.envelope("combat.command", command)))

    def test_building_and_player_reports(self):
        building = {"id": "building:1", "native_id": "openbw:8", "owner": 1,
                    "health": 1000, "max_health": 1000, "queue": 1,
                    "remaining_frames": 240,
                    "availability": {"terran_firebat": {"ready": False,
                        "reason": "requires_building", "requirement": "Terran Academy"}}}
        self.validator.validate(self.envelope("building.state", building, "bridge"))
        building["native_id"] = "not-native"
        self.assertFalse(self.validator.is_valid(self.envelope("building.state", building, "bridge")))
        resources = {"owner": 1, "minerals": 500, "gas": 250,
                     "supply_used": 12, "supply_total": 16}
        self.validator.validate(self.envelope("player.resources", resources, "bridge"))
        del resources["gas"]
        self.assertFalse(self.validator.is_valid(self.envelope("player.resources", resources, "bridge")))
        resources["gas"] = -1
        self.assertFalse(self.validator.is_valid(self.envelope("player.resources", resources, "bridge")))
        resources["gas"] = 250
        resources["minerals"] = -1
        self.assertFalse(self.validator.is_valid(self.envelope("player.resources", resources, "bridge")))

    def test_firebat_actor_identity(self):
        actor = {"id": "openbw:3001", "engine": "openbw", "type": "terran_firebat",
                 "owner": 1, "generation": 7, "session": "session-a"}
        for unit_type in ("terran_firebat", "terran_medic", "terran_vulture"):
            actor["type"] = unit_type
            self.validator.validate(self.envelope("actor.spawn", actor, "openbw"))


if __name__ == "__main__":
    unittest.main()
