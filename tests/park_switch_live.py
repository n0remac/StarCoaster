#!/usr/bin/env python3
"""Run two private parks through fresh native sessions in an isolated network namespace."""

import argparse
import json
import os
import socket
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from park_session_supervisor import ParkSessionSupervisor


def wait_transition(supervisor, previous, timeout=220):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = supervisor.state()
        if state["phase"] == "failed":
            raise RuntimeError(state["error"])
        if state["phase"] == "ready" and state["generation"] != previous:
            return state
        time.sleep(.5)
    raise RuntimeError("park transition did not finish")


def host_listening():
    with socket.socket() as connection:
        connection.settimeout(2)
        return connection.connect_ex(("127.0.0.1", int(os.environ.get("OPENRCT2_PORT", "11753")))) == 0


def inspect(supervisor, previous=None):
    state = supervisor.state()
    assert state["phase"] == "ready", state
    assert state["generation"] != previous, "park generation was reused"
    assert supervisor.session.poll() is None, "native session exited"
    assert host_listening(), "OpenRCT2 host is unavailable"
    scenario = json.loads(Path(supervisor.plan["scenario"]).read_text())
    assert scenario["mode"] == "park_defense"
    assert scenario["unlimited_resources"] is True
    assert scenario["park_defense"]["manual_activation"] is True
    assert all(not units for units in scenario["starting_units"].values()), "old units survived park preparation"
    return {"park": state["current"], "generation": state["generation"],
            "session_pid": supervisor.session.pid, "scenario": supervisor.plan["scenario"],
            "spawn_journal": supervisor.plan["spawn_journal"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parks", type=Path, required=True)
    parser.add_argument("--first", required=True)
    parser.add_argument("--second", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime = ROOT / "run-data" / ("park-switch-live-" + uuid.uuid4().hex[:12])
    supervisor = ParkSessionSupervisor(args.parks, runtime, args.first, start_browser=False)
    report = {"result": "failed", "runtime": str(runtime), "transitions": []}
    try:
        supervisor.start_initial()
        first = inspect(supervisor)
        report["transitions"].append(first)
        supervisor.request(args.second, "discard", first["generation"])
        wait_transition(supervisor, first["generation"])
        second = inspect(supervisor, first["generation"])
        assert second["session_pid"] != first["session_pid"]
        assert second["spawn_journal"] != first["spawn_journal"]
        report["transitions"].append(second)
        supervisor.request(args.first, "discard", second["generation"])
        wait_transition(supervisor, second["generation"])
        again = inspect(supervisor, second["generation"])
        assert again["session_pid"] != second["session_pid"]
        assert again["spawn_journal"] not in (first["spawn_journal"], second["spawn_journal"])
        report["transitions"].append(again)
        report["result"] = "passed"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        supervisor.close()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
