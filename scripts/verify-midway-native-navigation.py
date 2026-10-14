#!/usr/bin/env python3
"""Verify the Midway gate against observed OpenBW positions and confirmations."""
import json
from pathlib import Path
import re
import sys

POSITION = re.compile(r"MIDWAY_NAV_POSITION phase=(\d+) elapsed=(\d+) units=([^'\r\n]+)")
UNIT = re.compile(r"openbw:(1\d{3}):(\d+),(\d+)")
GATE = "openrct2:wall:31:864:960:112:0#1"


def main(directory):
    run = Path(directory)
    client = (run/"client.log").read_text(errors="replace")
    server = (run/"server.log").read_text(errors="replace")
    rows = [(int(m.group(1)), {uid:(int(x),int(y)) for uid,x,y in UNIT.findall(m.group(3))})
            for m in POSITION.finditer(client)]
    before = [point for phase,units in rows if phase == 1 for point in units.values()]
    after = [point for phase,units in rows if phase == 4 for point in units.values()]
    crossings = []
    hashes = re.findall(r"navigation initialized hash=([0-9a-f]{16})", server)
    for uid in {uid for phase,units in rows if phase == 4 for uid in units}:
        points = [units[uid] for phase,units in rows if phase == 4 and uid in units]
        for (ax,ay),(bx,by) in zip(points,points[1:]):
            if ax <= 864 < bx:
                crossings.append(round(ay+(864-ax)*(by-ay)/(bx-ax)))
    checks = {
        "pre_demolition_detour": bool(before) and any(y > 1150 for x,y in before if x < 864),
        "gate_demolition_confirmed": f"WORLD_REMOVAL id={GATE} state=confirmed" in server,
        "native_navigation_updated": len(set(hashes)) >= 2 and all(
            marker in server for marker in (
                f"[world-control] navigation-mask hash={hashes[-1]}",
                f"[world] navigation-mask hash={hashes[-1]}",
                f"controller navigation hash={hashes[-1]}",
                f"publisher navigation hash={hashes[-1]}")),
        "post_demolition_direct_crossing": any(920 <= y <= 1080 for y in crossings),
        "normal_orders_accepted": "MIDWAY_NAV_ORDER phase=1 verb=move accepted=true" in client
            and "MIDWAY_NAV_ORDER phase=2 verb=attack accepted=true" in client,
        "sequence_completed": "MIDWAY_NAV_SEQUENCE_COMPLETE" in client,
    }
    report = {"source":"live OpenBW actor positions and confirmed OpenRCT2 wall removal",
              "checks":checks,"pre_samples":len(before),"post_samples":len(after),
              "post_gate_crossing_y":crossings,"navigation_hashes":hashes,
              "removed_gate_id":GATE}
    (run/"verification.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
