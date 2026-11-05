#!/usr/bin/env python3
"""Select one stock park twice through the supervisor on private test ports."""

import argparse
import json
import os
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from park_session_supervisor import ParkSessionSupervisor
from single_map_cache import SingleMapCache, sha256_file


def free_ports(count):
    probes = [socket.socket() for _ in range(count)]
    try:
        for probe in probes:
            probe.bind(("127.0.0.1", 0))
        return [probe.getsockname()[1] for probe in probes]
    finally:
        for probe in probes:
            probe.close()


def select(supervisor, name, previous):
    supervisor.request(name, "discard", previous)
    supervisor.transition_thread.join(timeout=240)
    if supervisor.transition_thread.is_alive():
        raise RuntimeError("supervisor selection did not finish within 240 seconds")
    state = supervisor.state()
    if state["phase"] != "ready" or state["current"] != name or state["error"]:
        raise RuntimeError(f"supervisor selection failed: {state['phase']} {state['error']}")
    if not state["generation"] or state["generation"] == previous:
        raise RuntimeError("supervisor did not publish a new generation")
    return state


def journal_for(plan, session_log):
    path = Path(plan["scenario"]).parent / "spawn-queue.json.scenario.json"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if path.is_file():
            data = json.loads(path.read_text())
            if data.get("session") in session_log.read_text(errors="replace"):
                return data
        time.sleep(.25)
    raise RuntimeError("new map did not publish a session-matched wave journal")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", required=True, help="installed stock scenario filename")
    parser.add_argument("--second-map", help="different installed stock scenario for fresh-session reset")
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    if not runtime.is_relative_to((ROOT / "run-data").resolve()):
        parser.error("runtime must be inside run-data")
    runtime.mkdir(parents=True, exist_ok=True)
    temporary = runtime / "tmp"
    temporary.mkdir(exist_ok=True)
    os.environ["TMPDIR"] = str(temporary)
    tempfile.tempdir = str(temporary)
    ports = free_ports(4)
    for key, port in zip(("OPENRCT2_PORT", "STARCOASTER_BRIDGE_PORT",
                          "BRIDGE_OPENBW_PORT", "BRIDGE_CONTROLLER_PORT"), ports):
        os.environ[key] = str(port)
    library = runtime / "library"
    library.mkdir(exist_ok=True)
    cache = SingleMapCache(args.cache_root)
    supervisor = ParkSessionSupervisor(library, runtime, start_browser=False, cache=cache)
    try:
        first_outcome = "hit" if cache.status(supervisor.source_for(args.map))["status"] == "ready" else "built"
        first = select(supervisor, args.map, "")
        first_plan = supervisor.plan
        source = supervisor.source_for(args.map)
        package = cache.status(source)
        if package["status"] != "ready":
            raise RuntimeError("selected park did not publish a validated cache package")
        package_park = Path(package["package"]) / next(
            name for name in package["manifest"]["files"] if name.startswith("save/"))
        cache_hash = sha256_file(package_park)
        first_process = supervisor.session
        second = select(supervisor, args.map, first["generation"])
        second_plan = supervisor.plan
        if first_process.poll() is None:
            raise RuntimeError("prior native process remained active after switching")
        records = [json.loads(line) for line in (runtime / "load-timings.jsonl").read_text().splitlines()]
        if [record["cache_outcome"] for record in records[:2]] != [first_outcome, "hit"]:
            raise RuntimeError("expected validated cache hit on second selection")
        if records[1]["stages"]["isolated_preflight"]["status"] != "skipped":
            raise RuntimeError("cached selection repeated isolated preflight")
        if any(record["stages"]["session_startup"]["status"] != "ok" for record in records):
            raise RuntimeError("a selection did not reach actual native readiness")
        if sha256_file(package_park) != cache_hash:
            raise RuntimeError("native gameplay changed the cached park")
        if (Path(first_plan["park"]).stat().st_ino == Path(second_plan["park"]).stat().st_ino
                or Path(first_plan["park"]).stat().st_ino == package_park.stat().st_ino):
            raise RuntimeError("session parks share storage")
        result = {"status": "ready", "map": args.map, "key": package["key"],
                  "first_generation": first["generation"], "second_generation": second["generation"],
                  "first_total_ms": records[0]["total_ms"], "second_total_ms": records[1]["total_ms"],
                  "first_startup_ms": records[0]["stages"]["session_startup"]["elapsed_ms"],
                  "second_startup_ms": records[1]["stages"]["session_startup"]["elapsed_ms"],
                  "timings": str(runtime / "load-timings.jsonl")}
        if args.second_map:
            if args.second_map == args.map:
                raise RuntimeError("second map must differ from first map")
            second_log = runtime / "sessions" / second["generation"] / "session.log"
            wave_deadline = time.monotonic() + 240
            prior_actors = []
            while time.monotonic() < wave_deadline:
                prior_journal = journal_for(second_plan, second_log)
                prior_actors = [unit["actor_id"] for wave in prior_journal.get("waves") or []
                                for unit in wave.get("units") or [] if unit.get("actor_id")]
                if prior_actors:
                    break
                if supervisor.session.poll() is not None:
                    raise RuntimeError("prior map exited before its automatic wave")
                time.sleep(.5)
            if not prior_actors:
                raise RuntimeError("prior map produced no native automatic wave before switching")
            second_process = supervisor.session
            third = select(supervisor, args.second_map, second["generation"])
            if second_process.poll() is None:
                raise RuntimeError("prior map's native actors remained live after switching")
            third_plan = supervisor.plan
            third_log = runtime / "sessions" / third["generation"] / "session.log"
            third_journal = journal_for(third_plan, third_log)
            if supervisor.session.poll() is not None or not third_log.is_file():
                raise RuntimeError("second map native session is unavailable")
            if ((third_journal.get("wave_difficulty") or "standard") != "standard" or
                    third_journal.get("defense_enabled") is not True or
                    third_journal.get("waves") or third_journal.get("next_wave_sequence") != 1):
                raise RuntimeError("second map inherited wave state or settings")
            if third_journal["session"] in (runtime / "sessions" / second["generation"] / "session.log").read_text(errors="replace"):
                raise RuntimeError("second map reused the prior native session")
            if second_plan["scenario_id"] == third_plan["scenario_id"]:
                raise RuntimeError("different stock maps shared a scenario identity")
            result.update({"second_map": args.second_map, "third_generation": third["generation"],
                           "third_session": third_journal["session"], "third_wave_count": 0,
                           "third_difficulty": third_journal.get("wave_difficulty") or "standard",
                           "prior_actor_ids": prior_actors})
        (runtime / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 0
    finally:
        supervisor.close()


if __name__ == "__main__":
    raise SystemExit(main())
