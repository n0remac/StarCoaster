"""Assert observed fixture, native debit/training and same-session reconnect."""
import json
from pathlib import Path
import re
import sys


root = Path(sys.argv[1])
server = (root / "session.log").read_text(errors="replace")
restarted = (root / "restarted-bridge.log").read_text(errors="replace")
client = (root / "client.log").read_text(errors="replace")
assert "ECONOMY_E1_TRAIN_ORDER accepted=true" in client, "SCV order was rejected"
assert "ECONOMY_E1_TRAIN_COMPLETE workers=5" in client, "fifth SCV was not rendered"
assert re.search(r"ECONOMY_E1_CLIENT .*workers=4 minerals=6 geysers=1", client), "starting economy was not rendered"
sites = re.findall(r"resource site=([a-z-]+) generation=(\d+) type=([a-z_]+) amount=(\d+) publisher=(\d+) controller=(\d+)", server + restarted)
assert len({item[0] for item in sites}) == 7, f"resource bindings incomplete: {sites}"
assert all(int(item[1]) == 1 for item in sites), "bootstrap generation changed"
assert all(int(item[3]) == (5000 if item[0] == "geyser" else 1500) for item in sites), "resource amount changed without mining"
assert re.search(r"actor spawn id=openbw:3\d+ generation=", server), "trained SCV native identity missing"
assert re.search(r"actor-bound id=openbw:3\d+ native=\d+ frame=", server), "controller binding missing"
snapshots = list(re.finditer(r"WORLD_SNAPSHOT session=([0-9a-f]{32})", server))
assert len(snapshots) >= 2, "bridge reconnect did not request a same-session park snapshot"
assert snapshots[0].group(1) == snapshots[1].group(1), "bridge restart changed the native session"
before, after = server[:snapshots[1].start()], restarted
balance_pattern = r"player resources owner=1 minerals=(\d+) gas=(\d+) supply_used=(\d+) supply_total=(\d+) frame=(\d+)"
balances_before = [tuple(map(int, row)) for row in re.findall(balance_pattern, before)]
balances_after = [tuple(map(int, row)) for row in re.findall(balance_pattern, after)]
assert any(row[:4] == (50, 0, 8, 20) for row in balances_before), f"finite initial balance missing: {balances_before}"
assert any(row[:4] == (0, 0, 10, 20) for row in balances_before), f"native SCV cost/supply missing: {balances_before}"
assert balances_after and balances_after[0][:4] == (0, 0, 10, 20), f"bridge restart reset resources: {balances_after}"
assert not re.search(r"actor spawn id=openbw:3\d+", after), "bridge restart duplicated worker bootstrap"
assert (root / "native-client.png").stat().st_size > 10000, "native graphical capture missing"
print(json.dumps({"sites": sites, "balances_before": balances_before,
                  "balances_after": balances_after, "client_train": True,
                  "native_capture": str(root / "native-client.png")}, indent=2))
