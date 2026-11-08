#!/usr/bin/env python3
"""Short B3 native assault probe with an accelerated test-only countdown."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_existing_defense import prepare  # noqa: E402
from scenario_package import build_native_map, ensure_park  # noqa: E402
from test_enemy_base_bootstrap_native_live import free_ports  # noqa: E402
from test_enemy_base_production_native_live import stop  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--fail-fast-route", action="store_true", help="stop after the first native route rejection")
    args = parser.parse_args()
    source, runtime = args.source.resolve(strict=True), args.runtime.resolve()
    if not runtime.is_relative_to((ROOT / "run-data").resolve()):
        parser.error("runtime must be in ignored run-data")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    runtime.mkdir(parents=True, exist_ok=True)
    plan = prepare(str(source), runtime / "prepared")
    scenario_path = Path(plan["scenario"])
    scenario = json.loads(scenario_path.read_text())
    if scenario["enemy_base"]["layout_state"] != "ready":
        raise AssertionError("native probe requires a ready colony")
    scenario["park_defense"]["initial_delay_frames"] = 1200
    scenario_path.write_text(json.dumps(scenario, indent=2) + "\n")
    ensure_park(plan)
    build_native_map(plan)
    names = ("OPENRCT2_PORT", "STARCOASTER_BRIDGE_PORT", "BRIDGE_OPENBW_PORT",
             "BRIDGE_CONTROLLER_PORT")
    env = os.environ.copy() | dict(zip(names, map(str, free_ports(len(names)))))
    env.update({"RCT2_DATA_DIR": os.environ.get("RCT2_DATA_DIR", "/home/pi/games/rct2"),
                "STARCRAFT_DATA_DIR": os.environ.get("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft"),
                "BRIDGE_MAP_FILE": plan["native_map"], "BRIDGE_SCENARIO_CONFIG": plan["scenario"],
                "BRIDGE_RULES_CONFIG": plan["mapping"],
                "BRIDGE_SPAWN_JOURNAL": str(runtime / "spawn-queue.json"),
                "BRIDGE_RUNTIME_DIR": str(runtime / "native"),
                "BRIDGE_SERVER_DATA_DIR": str(runtime / "server"),
                "BRIDGE_LAUNCH_CLIENT": "0", "BRIDGE_FRAME_MS": "10",
                "BRIDGE_TEST_BRIDGE_PID_FILE": str(runtime / "bridge.pid")})
    log = runtime / "session.log"
    checks = {}
    with log.open("w") as stream:
        process = subprocess.Popen([str(ROOT / "scripts/run-world-session.sh"), plan["park"]],
                                   cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            deadline = time.monotonic() + 75
            content = ""
            while time.monotonic() < deadline:
                content = log.read_text(errors="replace")
                if "enemy assault receipt request=" in content and "[world] wave-rally native=" in content:
                    break
                if args.fail_fast_route and "[world] enemy assault route unavailable" in content:
                    break
                if process.poll() is not None:
                    break
                time.sleep(.25)
            receipt = re.search(r"enemy assault receipt request=(enemy-assault:[^ ]+) wave=([^ ]+) "
                                r"accepted=true reason= assigned=(\d+) frame=(\d+)", content)
            native = re.search(r"\[world\] enemy assault request=(enemy-assault:[^ ]+) "
                               r"wave=([^ ]+) accepted=1 reason= assigned=(\d+) frame=(\d+)", content)
            rallies = re.findall(r"\[world\] wave-rally native=(\d+) x=(\d+) y=(\d+) frame=(\d+)", content)
            journal = json.loads((runtime / "spawn-queue.json.scenario.json").read_text())
            waves = journal["enemy_assault"]["waves"]
            wave = waves[0] if waves else {}
            actors = wave.get("actors", [])
            checks["native_order_accepted"] = bool(receipt and native and
                receipt.group(1) == native.group(1) and receipt.group(3) == native.group(3))
            checks["durable_exact_group"] = bool(wave.get("state") == "ordered" and actors and
                len(actors) == int(receipt.group(3)) if receipt else False)
            checks["observed_completed_births"] = bool(actors and all(
                re.search(r"actor morph id=" + re.escape(actor["id"]) +
                          r" from=zerg_zergling type=zerg_zergling phase=complete", content) or
                re.search(r"actor spawn id=" + re.escape(actor["id"]) +
                          r" generation=\d+ type=zerg_zergling", content)
                for actor in actors))
            checks["real_attack_move"] = bool(rallies and any(
                int(rally[0]) in {actor["native_id"] for actor in actors} for rally in rallies))
            checks["no_free_wave"] = "scenario spawn request=" not in content
            checks["no_duplicate_assignment"] = len(re.findall(
                r"\[world\] enemy assault request=", content)) == 1 and len(waves) == 1
        finally:
            stop(process)
    checks["source_unchanged"] = hashlib.sha256(source.read_bytes()).hexdigest() == before
    result = {"checks": checks, "source_sha256": before, "scenario": plan["scenario"],
              "elapsed_native_frame": int(receipt.group(4)) if receipt else None,
              "wave": wave}
    (runtime / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(checks, indent=2))
    print("Evidence:", runtime)
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
