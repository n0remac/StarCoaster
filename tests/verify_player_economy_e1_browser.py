"""Verify browser rendering, native SCV charge/binding and observe-only reconnect."""

import json
from pathlib import Path
import re
import sys


root = Path(sys.argv[1])
result = json.loads((root / "browser/runtime.json").read_text())
assert result["outcome"] == "passed", result["outcome"]
for name in ("final.png", "economy-reconnect.png"):
    assert (root / "browser" / name).stat().st_size > 10000, name

server = (root / "session.log").read_text(errors="replace")
browser = (root / "browser.log").read_text(errors="replace")
assert "workers=4 minerals=6 geysers=1" in browser
assert "workers=5 minerals=6 geysers=1" in browser
assert browser.count("ECONOMY_E1_TRAIN_ORDER accepted=true") == 1
assert len(re.findall(r"train command=.* accepted=1 .*unit_type=terran_scv", server)) == 1
assert len(re.findall(r"actor spawn id=openbw:3\d+ generation=1", server)) == 1
assert re.search(r"actor-bound id=openbw:3\d+ native=\d+ frame=", server)
balances = [tuple(map(int, row)) for row in re.findall(
    r"player resources owner=1 minerals=(\d+) gas=(\d+) supply_used=(\d+) supply_total=(\d+) frame=(\d+)",
    server)]
assert any(row[:4] == (50, 0, 8, 20) for row in balances), balances
assert any(row[:4] == (0, 0, 10, 20) for row in balances), balances
print(json.dumps({"browser": str(root), "balances": balances,
                  "train_orders": 1, "reconnect_capture": "economy-reconnect.png"}, indent=2))
