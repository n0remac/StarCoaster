#!/usr/bin/env python3
"""Check native economic effects in the two-participant E0 run log."""

import json
from pathlib import Path
import re
import sys


def rows(log: str, role: str, stage: str) -> list[dict[str, str]]:
    result = []
    for line in log.splitlines():
        prefix = f"[economy-e0] role={role} "
        if not line.startswith(prefix) or f" stage={stage} " not in line:
            continue
        result.append(dict(re.findall(r"(\w+)=([^ ]+)", line)))
    return result


def main() -> None:
    run = Path(sys.argv[1])
    log = (run / "session.log").read_text(errors="replace")
    c = lambda stage: rows(log, "controller", stage)
    p = lambda stage: rows(log, "publisher", stage)
    initial = c("initial")
    peer_initial = p("initial")
    deliveries = c("mineral_delivery")
    gas = c("gas_delivery")
    states = c("state")
    depot_states = [(int(row["frame"]), int(row["depot"].split(":")[2]))
                    for row in states if re.fullmatch(r"\d+:0:[1-9]\d*", row.get("depot", ""))]
    interrupted = c("interrupt_depot")
    resumed = c("resume_depot")
    paused_states = [remaining for frame, remaining in depot_states
                     if interrupted and resumed and int(interrupted[0]["frame"]) < frame
                     < int(resumed[0]["frame"])]
    controller_balances = [int(match.group(1)) for match in re.finditer(
        r"^\[economy-e0\] role=controller .*?minerals=(\d+)", log, re.M)]
    increases = [right - left for left, right in zip(controller_balances, controller_balances[1:])
                 if right > left]
    checks = {
        "both_native_participants_observe_fixture": bool(initial and peer_initial
             and all(initial[0].get(key) == peer_initial[0].get(key)
                     for key in ("center", "miner", "builder", "mineral", "geyser", "mask"))),
        "neutral_resource_amounts": bool(initial and initial[0].get("mineral_owner") == "-1"
             and initial[0].get("geyser_owner") == "-1"
             and initial[0].get("mineral_amount") == "1500"
             and initial[0].get("geyser_amount") == "5000"),
        "owned_center_and_workers": bool(initial and initial[0].get("center_owner") == "1"
             and initial[0].get("center") and initial[0].get("miner")
             and initial[0].get("builder") and initial[0]["miner"] != initial[0]["builder"]),
        "finite_initial_balance_and_base_supply": bool(initial and initial[0].get("minerals") == "400"
             and initial[0].get("gas") == "0" and initial[0].get("supply") == "4/20"),
        "confirmed_park_navigation_mask": bool(initial and initial[0].get("mask")
             and re.fullmatch(r"[0-9a-f]{16}", initial[0]["mask"])
             and log.count("navigation-mask hash=" + initial[0]["mask"]) >= 2
             and log.index("navigation-mask hash=" + initial[0]["mask"])
             < log.index("stage=gather_mineral")),
        "two_native_mineral_deliveries": len(deliveries) >= 2 and all(
             int(row["to"]) - int(row["from"]) == 8 for row in deliveries[:2])
             and int(deliveries[1]["remaining"]) <= 1484,
        "worker_mineral_cargo": any(row.get("cargo_m") == "1" for row in states),
        "depot_build_order_and_site": bool(c("build_depot") and c("build_depot")[0].get("accepted") == "1"
             and c("depot_site") and c("depot_site")[0].get("can_build") == "1"),
        "depot_incomplete_then_complete": any(re.fullmatch(r"\d+:0:[1-9]\d*", row.get("depot", ""))
             for row in states) and bool(c("depot_complete")),
        "native_depot_debit_once": bool(c("build_depot") and interrupted
             and int(c("build_depot")[0]["minerals"]) - int(interrupted[0]["minerals"]) == 100
             and len(c("build_depot")) == 1),
        "interrupted_then_resumed": bool(c("interrupt_depot") and c("resume_depot")
             and c("interrupt_depot")[0].get("accepted") == "1"
             and c("resume_depot")[0].get("accepted") == "1"),
        "progress_pauses": bool(len(paused_states) >= 2 and len(set(paused_states)) == 1),
        "native_depot_supply": bool(c("depot_complete")
             and c("depot_complete")[0].get("supply") == "36"),
        "cancelled_second_depot": bool(c("cancel_target") and c("cancel_depot")
             and c("cancel_removed") and c("cancel_depot")[0].get("accepted") == "1"),
        "native_cancel_refund": bool(c("build_cancel_depot") and c("cancel_target")
             and c("cancel_depot") and int(c("build_cancel_depot")[0]["minerals"])
             - int(c("cancel_target")[0]["minerals"]) == 100
             and int(c("cancel_depot")[0]["minerals"])
             - int(c("cancel_target")[0]["minerals"]) == 75),
        "no_periodic_mineral_grants": sorted(increases) == [8, 8, 75],
        "refinery_on_geyser": bool(c("refinery_site") and c("build_refinery")
             and c("refinery_complete") and c("refinery_site")[0].get("can_build") == "1"
             and c("build_refinery")[0].get("accepted") == "1"
             and initial and c("refinery_complete")[0].get("native")
             == initial[0].get("geyser")),
        "native_gas_delivery": bool(gas and int(gas[0]["to"]) > int(gas[0]["from"])
             and c("gather_gas") and c("gather_gas")[0].get("accepted") == "1"),
        "worker_gas_cargo": any(row.get("cargo_g") == "1" for row in states),
        "native_refinery_debit": bool(c("build_refinery") and c("refinery_complete")
             and int(c("build_refinery")[0]["minerals"])
             - int(c("refinery_complete")[0]["minerals"]) == 100),
        "geyser_after_refinery_loss": bool(c("kill_refinery") and c("geyser_restored")
             and c("geyser_restored")[0].get("native")
             != c("refinery_complete")[0].get("native")
             and c("geyser_restored")[0].get("owner") == "-1"
             and 0 < int(c("geyser_restored")[0]["amount"]) < 5000),
        "bridge_reconnect_without_reissue": (run / "bridge-restart.txt").is_file()
             and log.count("WORLD_READY entities=") >= 2
             and len(c("build_depot")) == 1 and len(c("build_refinery")) == 1,
    }
    report = {"checks": checks, "native": {stage: c(stage) for stage in (
        "initial", "mineral_delivery", "depot_site", "build_depot", "interrupt_depot",
        "resume_depot", "depot_complete", "cancel_target", "cancel_depot", "cancel_removed",
        "refinery_site", "build_refinery", "refinery_complete", "gas_delivery",
        "kill_refinery", "geyser_restored")}}
    (run / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
