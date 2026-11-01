#!/usr/bin/env python3
"""Run one cached materialization through native readiness on isolated ports."""

import argparse
import json
import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from park_preparation import await_native_ready, stop_native_process
from scenario_package import session_environment
from single_map_cache import SingleMapCache
from load_timing import LoadTiming


def free_ports(count):
    sockets = [socket.socket() for _ in range(count)]
    try:
        for probe in sockets:
            probe.bind(("127.0.0.1", 0))
        return [probe.getsockname()[1] for probe in sockets]
    finally:
        for probe in sockets:
            probe.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    if not runtime.is_relative_to((ROOT / "run-data").resolve()):
        parser.error("runtime must be inside run-data")
    runtime.mkdir(parents=True, exist_ok=True)
    cache = SingleMapCache(args.cache_root)
    generation = uuid.uuid4().hex
    timing = LoadTiming(args.source.name, runtime / "timings.jsonl", "cache_native_live")
    timing.generation = generation
    process = None
    try:
        plan = cache.materialize(args.source, args.session_dir, timing)
        ports = free_ports(4)
        environment = session_environment(plan, {
            "OPENRCT2_PORT": str(ports[0]), "STARCOASTER_BRIDGE_PORT": str(ports[1]),
            "BRIDGE_OPENBW_PORT": str(ports[2]), "BRIDGE_CONTROLLER_PORT": str(ports[3]),
            "BRIDGE_RUNTIME_DIR": str(ROOT / "run-data/ps" / generation[:16]),
            "BRIDGE_SERVER_DATA_DIR": plan["server_data"],
            "BRIDGE_CLIENT_DATA_DIR": plan["client_data"],
            "BRIDGE_PARK_SUPERVISOR_SOCKET": "", "BRIDGE_PARK_GENERATION": generation,
            "BRIDGE_SERVE_WASM": "0", "BRIDGE_LAUNCH_CLIENT": "0",
        })
        log = runtime / "session.log"
        with timing.stage("session_startup"):
            with log.open("wb") as stream:
                process = subprocess.Popen([str(ROOT / "scripts/run-world-session.sh"), plan["park"]],
                                           cwd=ROOT, env=environment, stdout=stream,
                                           stderr=subprocess.STDOUT, start_new_session=True)
            await_native_ready(process, log)
        timing.finish("ready")
        print(json.dumps({"status": "ready", "key": timing.cache_key, "generation": generation,
                          "session": str(Path(args.session_dir).resolve()), "log": str(log)}))
        return 0
    except Exception as error:
        timing.finish("failed", error)
        print(f"cache native check: {error}", file=sys.stderr)
        return 1
    finally:
        stop_native_process(process)


if __name__ == "__main__":
    raise SystemExit(main())
