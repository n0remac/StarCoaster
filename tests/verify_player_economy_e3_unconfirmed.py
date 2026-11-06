#!/usr/bin/env python3
"""An accepted but uncreated native order is surfaced without replay or charge."""

import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
host = (root / "session.log").read_text(errors="replace")
client = (root / "client.log").read_text(errors="replace")
assert "ECONOMY_E3_UNCONFIRMED request=93602 type=terran_academy accepted=true" in client
assert re.search(r"verb=unit\.build accepted=1.*frame=\d+", host)
assert "construction unresolved intent=build:1:93602 reason=native_creation_unconfirmed" in host
assert "construction bound intent=build:1:93602" not in host
journals = list(root.glob("spawn-queue.json.construction-*.json"))
assert len(journals) == 1
intent = json.loads(journals[0].read_text())["intents"]["build:1:93602"]
assert intent["state"] == "dispatched" and not intent.get("native_id")
assert intent["status_error"] == "native_creation_unconfirmed"
assert len(re.findall(r"command=.*verb=unit\.build accepted=1", host)) == 2
print("unconfirmed_native_creation_visible: PASS")
print("reservation_persisted_without_replay: PASS")
