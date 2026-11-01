"""Shared existing-park preparation and isolated native synchronization."""

import os
import signal
import subprocess
import time
from contextlib import nullcontext
from pathlib import Path

from scenario_package import ROOT, session_environment


def prepare_pipeline(source, workspace, generation, prepare, ensure_park, build_native_map,
                     preflight, timing=None):
    """Run the same ordered preparation for a session or a cache builder."""
    plan = prepare(str(source), workspace, timing=timing) if timing else prepare(str(source), workspace)
    if timing:
        timing.source_sha256 = plan.get("validated_source_sha256")
    with timing.stage("park_preparation") if timing else nullcontext():
        ensure_park(plan)
    with timing.stage("native_map_generation") if timing else nullcontext():
        build_native_map(plan)
    with timing.stage("isolated_preflight") if timing else nullcontext():
        preflight(generation, plan)
    return plan


def await_native_ready(process, log_path, timeout=150):
    deadline = time.monotonic() + timeout
    status_marker = b"WORLD_SCENARIO_STATUS scenario="
    ready_marker = b"WORLD_READY entities="
    while time.monotonic() < deadline:
        if process.poll() is not None:
            lines = log_path.read_text(errors="replace").splitlines()[-20:]
            errors = [line for line in lines if "Error:" in line or "WORLD_ERROR" in line]
            raise RuntimeError("native session exited before readiness: "
                               + (errors[-1] if errors else "see " + str(log_path)))
        if log_path.exists():
            output = log_path.read_bytes()
            if status_marker in output and ready_marker in output and b"navigation=native" in output:
                return
        time.sleep(.3)
    raise RuntimeError("new game session did not synchronize both OpenBW participants")


def stop_native_process(process):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=12)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def isolated_preflight(generation, plan, runtime, await_ready=await_native_ready,
                       stop=stop_native_process):
    # Native OpenBW navigation is rebuilt after the park collision mask arrives.
    preflight = dict(plan)
    directory = Path(runtime) / "sessions" / generation / "preflight"
    preflight["spawn_journal"] = str(directory / "spawn-queue.json")
    preflight["server_data"] = str(directory / "server")
    preflight["client_data"] = str(directory / "client")
    environment = session_environment(preflight, {
        "BRIDGE_RUNTIME_DIR": str(ROOT / "run-data/ps" / generation[:16] / "check"),
        "BRIDGE_SERVER_DATA_DIR": preflight["server_data"],
        "BRIDGE_CLIENT_DATA_DIR": preflight["client_data"],
        "BRIDGE_PARK_SUPERVISOR_SOCKET": "", "BRIDGE_PARK_GENERATION": "",
        "BRIDGE_SERVE_WASM": "0", "BRIDGE_LAUNCH_CLIENT": "0",
    })
    log_path = directory / "session.log"
    directory.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab", buffering=0) as log:
        process = subprocess.Popen(["unshare", "-Urn", str(ROOT / "scripts/run-isolated-world-preflight.sh"),
                                    plan["park"]], cwd=ROOT, env=environment,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        await_ready(process, log_path, timeout=150)
    finally:
        stop(process)
