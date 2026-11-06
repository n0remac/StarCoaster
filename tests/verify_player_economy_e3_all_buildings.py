#!/usr/bin/env python3
"""Check native outcomes of the isolated all-building player-action probe."""

import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
host = (root / "session.log").read_text(errors="replace")
client = (root / "client.log").read_text(errors="replace")
types = ["terran_barracks", "terran_academy", "terran_factory", "terran_armory",
         "terran_supply_depot", "terran_command_center", "terran_refinery"]
bindings = {}
for index, type_id in enumerate(types):
    request = 93400 + index
    assert f"ECONOMY_E3_ALL request={request} type={type_id}" in client, type_id
    assert f"ECONOMY_E3_ALL request={request} type={type_id}" in client and re.search(
        rf"ECONOMY_E3_ALL request={request} type={type_id} .*accepted=true", client), type_id
    match = re.search(
        rf"construction bound intent=build:1:{request} type={type_id} "
        rf"native_publisher=(\d+) native_controller=(\d+) tile=(\d+),(\d+) frame=(\d+)/(\d+)", host)
    assert match, f"missing exact native binding: {type_id}"
    assert match.group(1) == match.group(2), f"participants disagreed: {type_id}"
    assert match.group(5) == match.group(6), f"observation frames differed: {type_id}"
    assert f"construction completed intent=build:1:{request} native={match.group(1)}" in host, type_id
    assert f"WORLD_PATCH_SYNC revision={index + 2}" in host, type_id
    bindings[type_id] = match.group(1)
assert len(set(bindings.values())) == len(types), bindings
assert bindings["terran_refinery"] == "10", bindings
assert "player resources owner=1 minerals=3800 gas=4850" in host
assert "supply_used=8 supply_total=56" in host
assert len(re.findall(r"verb=unit\.build accepted=1", host)) == 7
print("all_seven_native_builds: PASS")
print("seven_exact_bindings_and_confirmed_revisions: PASS")
print("native_costs_prerequisites_supply: PASS")
print("native_ids:", bindings)
