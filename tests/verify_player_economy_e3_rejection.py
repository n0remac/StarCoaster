#!/usr/bin/env python3
"""Assert native-cost and prerequisite rejection on the finite starter fixture."""

import sys
from pathlib import Path

root = Path(sys.argv[1])
client = (root / "client.log").read_text(errors="replace")
host = (root / "session.log").read_text(errors="replace")
assert "ECONOMY_E3_REJECT request=93701 type=terran_supply_depot accepted=false reason=insufficient minerals" in client
assert "ECONOMY_E3_REJECT request=93702 type=terran_academy accepted=false reason=Requires Terran Barracks" in client
assert "player resources owner=1 minerals=50 gas=0" in host
assert "verb=unit.build accepted=1" not in host
assert "construction bound intent=build:1:9370" not in host
print("native_cost_and_prerequisite_rejection: PASS")
print("no_free_build_or_debit: PASS")
