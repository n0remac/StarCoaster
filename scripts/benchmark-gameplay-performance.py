#!/usr/bin/env python3
"""Run native StarCoaster load cases and merge Pi/browser performance evidence.

Use --matrix for the full unit/workload/camera/paint matrix. A remote client
needs an SSH-accessible laptop checkout and the private Pi WASM HTTPS origin.
No peer address, authentication material, or licensed asset enters artifacts.
"""

import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import re
import secrets
import shlex
import signal
import socket
import statistics
import subprocess
import sys
import time

from scenario_package import ROOT, ensure_park, resolve, session_environment


PERFORMANCE_ROOT = ROOT / "run-data/performance"
COUNTS = (0, 10, 25, 50, 100, 200)
WORKLOADS = ("idle", "moving", "fighting")
LOG_EVENT = re.compile(r"STARCOASTER_PERF (\{.*\})")
PING_MS = re.compile(r"\bin ([0-9.]+)ms\b")


def fixture(count: int, workload: str, target: Path, park: str) -> Path:
    """Generate only scenario configuration; all actors are native map units."""
    if count not in COUNTS or workload not in WORKLOADS or (count == 0 and workload != "idle"):
        raise ValueError("unsupported unit count/workload")
    if count == 0:
        source = ROOT / "scenarios/wasm-mixed-client/scenario.json"
        scenario = json.loads(source.read_text())
        scenario["starting_units"] = {"marines": [], "zerglings": []}
    else:
        source = ROOT / "scenarios/example-defense/scenario.json"
        scenario = json.loads(source.read_text())
        marines = count // 2
        zerglings = count - marines
        marine_tiles = [[12 + (i % 10), 29 + (i // 10)] for i in range(marines)]
        zerg_tiles = [[35 + (i % 10), 29 + (i // 10)] for i in range(zerglings)]
        scenario["starting_units"] = {"marines": marine_tiles, "zerglings": zerg_tiles}
        # Keep the required wave defined but outside the measurement window.
        scenario["waves"] = [{"id": "after-benchmark", "trigger": {"type": "elapsed_frames", "frames": 1000000},
                              "groups": [{"unit_type": "zerg_zergling", "count": 1,
                                          "spawn_zone": "eastern-approach"}]}]
        scenario["initial_ai"]["delay_frames"] = 0
    scenario["park_file"] = park
    scenario["display_name"] = "Gameplay Performance Fixture"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(scenario, indent=2) + "\n")
    return target


def workload_environment(workload: str, release_file=None):
    if workload == "fighting":
        result = {"BRIDGE_TEST_ASSAULT_MARINES":"1"}
        if release_file: result["BRIDGE_BENCHMARK_ASSAULT_FILE"] = str(release_file)
        return result
    return {"BRIDGE_DISABLE_ASSAULT_AI":"1"}


def distribution(values):
    numbers = sorted(float(value) for value in values if value is not None and math.isfinite(float(value)))
    if not numbers:
        return {"count": 0, "min": None, "median": None, "p95": None, "p99": None, "max": None}
    def at(fraction):
        return round(numbers[min(len(numbers) - 1, math.ceil(len(numbers) * fraction) - 1)], 3)
    return {"count": len(numbers), "min": round(numbers[0], 3), "median": at(.5), "p95": at(.95), "p99": at(.99),
            "max": round(numbers[-1], 3)}


def process_ids(root_pid):
    seen, pending = set(), [root_pid]
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        try:
            children = (Path("/proc") / str(pid) / "task" / str(pid) / "children").read_text()
            pending.extend(int(item) for item in children.split())
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return seen


def role_of(pid):
    base = Path("/proc") / str(pid)
    try:
        name = (base / "comm").read_text().strip()
        if name == "BWAPILauncher" or name.startswith("openbw"):
            env = (base / "environ").read_bytes()
            return "openbw-controller" if b"BRIDGE_WORLD_ROLE=controller" in env else "openbw-publisher"
        if name == "world-bridge": return "go-bridge"
        if name == "openrct2-cli": return "openrct2-server"
        if name.startswith("openrct2"): return "native-client"
        if name == "wasm-server": return "gateway"
        if name == "chromium": return "local-chromium"
        if name == "ffmpeg": return "recorder"
    except OSError:
        pass
    return "launcher"


def background_roles():
    counts = Counter()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit(): continue
        role = role_of(int(entry.name))
        if role in ("openbw-controller","openbw-publisher","go-bridge","openrct2-server","gateway"):
            counts[role] += 1
    return dict(counts)


def sample_process(pid, previous, elapsed):
    base = Path("/proc") / str(pid)
    try:
        stat = (base / "stat").read_text().rsplit(")", 1)[1].split()
        cpu_ticks = int(stat[11]) + int(stat[12])
        rss_bytes = int(stat[21]) * os.sysconf("SC_PAGE_SIZE")
        threads = int(stat[17])
        io_values = {}
        try:
            io_values = {line.split(":", 1)[0]: int(line.split(":", 1)[1])
                         for line in (base / "io").read_text().splitlines()}
        except (FileNotFoundError, PermissionError):
            pass
        prior = previous.get(pid)
        cpu_percent = 100 * (cpu_ticks - prior) / os.sysconf("SC_CLK_TCK") / elapsed if prior is not None else None
        previous[pid] = cpu_ticks
        return {"pid": pid, "role": role_of(pid), "cpu_percent_one_core": cpu_percent,
                "cpu_seconds": cpu_ticks / os.sysconf("SC_CLK_TCK"), "rss_bytes": rss_bytes,
                "threads": threads, "read_bytes": io_values.get("read_bytes"),
                "write_bytes": io_values.get("write_bytes")}
    except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
        return None


def read_number(path, divisor=1):
    try: return int(Path(path).read_text().strip()) / divisor
    except (FileNotFoundError, PermissionError, ValueError): return None


def pi_metrics():
    result = {"temperature_c": read_number("/sys/class/thermal/thermal_zone0/temp", 1000),
              "cpu_mhz": read_number("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", 1000)}
    try:
        mem = {key: int(value.split()[0]) * 1024 for key, value in
               (line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())}
        result.update(memory_available_bytes=mem.get("MemAvailable"), swap_free_bytes=mem.get("SwapFree"),
                      swap_total_bytes=mem.get("SwapTotal"))
    except (FileNotFoundError, ValueError):
        result.update(memory_available_bytes=None, swap_free_bytes=None, swap_total_bytes=None)
    try:
        throttled = subprocess.run(["vcgencmd", "get_throttled"], text=True, capture_output=True, timeout=1)
        result["throttled_flags"] = int(throttled.stdout.split("0x")[1], 16) if "0x" in throttled.stdout else None
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError): result["throttled_flags"] = None
    return result


def network_bytes():
    try:
        received = sent = 0
        for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
            name, counters = line.split(":", 1)
            if name.strip() == "lo": continue
            values = counters.split()
            received += int(values[0])
            sent += int(values[8])
        return received, sent
    except (FileNotFoundError, ValueError, IndexError):
        return None


def tailscale_ping(peer):
    try:
        completed = subprocess.run(["tailscale", "ping", "--c=1", "--timeout=2s", peer],
                                   capture_output=True, text=True, timeout=4)
        output = completed.stdout + completed.stderr
        match = PING_MS.search(output)
        return {"rtt_ms": float(match.group(1)) if match else None,
                "loss": 0 if match and completed.returncode == 0 else 1,
                "path": "derp" if "via DERP" in output else "direct" if match else "unavailable"}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"rtt_ms": None, "loss": 1, "path": "unavailable"}


def read_events(path):
    if not path.exists(): return
    for line in path.open(errors="replace"):
        try: yield json.loads(line)
        except json.JSONDecodeError: continue


def merge_case(case_dir, run_events, run_system, run_network, label):
    raw = case_dir / "raw"
    sources = [(raw / "bridge-events.jsonl", "events"),
               (case_dir / "benchmark-events.jsonl", "events"),
               (raw / "openbw-publisher-events.jsonl", "events"),
               (raw / "openbw-controller-events.jsonl", "events"),
               (case_dir / "browser/browser-events.jsonl", "events"),
               (case_dir / "browser/browser-system.jsonl", "system"),
               (case_dir / "browser/browser-network.jsonl", "network"),
               (raw / "gateway-network.jsonl", "network"),
               (case_dir / "pi-system.jsonl", "system"),
               (case_dir / "pi-network.jsonl", "network")]
    native = case_dir / "session.log"
    if native.exists():
        for line in native.open(errors="replace"):
            found = LOG_EVENT.search(line)
            if found:
                try:
                    event = json.loads(found.group(1))
                    event["case"] = label
                    event["clock_domain"] = "pi-monotonic"
                    run_events.write(json.dumps(event) + "\n")
                except json.JSONDecodeError: pass
    native_client = case_dir / "native-client.log"
    if native_client.exists():
        for line in native_client.open(errors="replace"):
            found = LOG_EVENT.search(line)
            if found:
                try:
                    event = json.loads(found.group(1))
                    event.update(case=label, role="native-client", clock_domain="pi-monotonic")
                    run_events.write(json.dumps(event) + "\n")
                except json.JSONDecodeError: pass
    for path, channel in sources:
        output = {"events": run_events, "system": run_system, "network": run_network}[channel]
        for event in read_events(path):
            event["case"] = label
            if channel == "events":
                event["clock_domain"] = "browser-monotonic" if "browser" in str(path) else "pi-monotonic"
            output.write(json.dumps(event) + "\n")


def summarize_case(events, system, network, case):
    start, end = case.get("measurement_start_pi_mono_ns"), case.get("measurement_end_pi_mono_ns")
    browser_window = case.get("browser_window") or {}
    errors = list(case.get("errors", []))
    if not start or not end or end <= start: errors.append("missing_measurement_window")
    selected = []
    for event in events:
        if event.get("case") != case["label"]: continue
        if event.get("clock_domain") == "pi-monotonic":
            if not start or not end: continue
            tick = event.get("mono_ns")
            if tick is None and event.get("mono_ms") is not None: tick = event["mono_ms"] * 1e6
            if tick is None or not start <= tick <= end: continue
        elif event.get("clock_domain") == "browser-monotonic":
            if not browser_window: continue
            native_ms = event.get("mono_ms")
            if native_ms is None and event.get("mono_ns") is not None: native_ms = event["mono_ns"] / 1e6
            if native_ms is not None and browser_window.get("mono_start") is not None:
                if not browser_window["mono_start"] <= native_ms <= browser_window["mono_end"]: continue
            else:
                wall = event.get("wall_ms")
                if wall is None or not browser_window["start"] <= wall <= browser_window["end"]: continue
        selected.append(event)
    timing = {}
    for event in selected:
        for key in ("duration_us", "decode_us", "transform_us", "encode_us", "write_us", "build_us",
                    "serialize_us", "queue_us", "process_us", "duration_ms", "queue_ms"):
            value = event.get(key)
            if isinstance(value, (int, float)) and value >= 0:
                timing.setdefault(event.get("stage", "unknown") + "." + key, []).append(value)
    stages = {name: distribution(values) for name, values in timing.items()}
    bw = [event for event in selected if event.get("stage") == "frame_summary" and event.get("source") == "openbw-publisher"]
    client_role = "native-client" if case["client"] == "native" else "browser-client"
    render = [event for event in selected if event.get("stage") == "present_summary" and event.get("role") == client_role]
    server_ticks = [event for event in selected if event.get("stage") == "tick_summary"
                    and event.get("mode") == "server" and event.get("clock_domain") == "pi-monotonic"]
    snapshots = [event for event in selected if event.get("stage") == "snapshot_publish"]
    omitted = sum(event.get("unit_omitted", 0) for event in snapshots)
    attack_samples = [event.get("unit_attacking", 0) for event in snapshots]
    bw_fps = [event["frames"] * 1e9 / event["elapsed_ns"] for event in bw if event.get("elapsed_ns", 0) > 0]
    bw_work_p95 = [event["work_p95_us"] / 1000 for event in bw if event.get("work_p95_us") is not None]
    render_fps = [event["frames"] * 1e9 / event["elapsed_ns"] for event in render if event.get("elapsed_ns", 0) > 0]
    if case["client"] in ("local", "remote") and browser_window:
        render_window_seconds = ((browser_window.get("mono_end", browser_window["end"])
                                  - browser_window.get("mono_start", browser_window["start"])) / 1000)
    else:
        render_window_seconds = (end - start) / 1e9 if start and end and end > start else 0
    client_whole_fps = (sum(event.get("frames", 0) for event in render) / render_window_seconds
                        if render and render_window_seconds > 0 else None)
    client_frames = [event.get("frame_p95_us") / 1000 for event in render if event.get("frame_p95_us") is not None]
    net = [event for event in network if event.get("case") == case["label"] and start and end]
    rtt = [event["rtt_ms"] for event in net if event.get("stage") == "tailscale_ping" and event.get("rtt_ms") is not None]
    ping_samples = [event for event in net if event.get("stage") == "tailscale_ping"]
    pi_net = [event for event in net if event.get("source") == "pi" and event.get("stage") == "network_second"
              and event.get("elapsed_s", 0) > 0]
    browser_net = [event for event in net if event.get("source") == "browser" and event.get("stage") == "websocket_second"
                   and (not browser_window or browser_window["start"] <= event.get("wall_ms",0) <= browser_window["end"])]
    pi = [event for event in system if event.get("case") == case["label"] and event.get("source") == "pi" and start and end]
    client_system = [event for event in system if event.get("case") == case["label"]
                     and event.get("source") == "chromium" and browser_window
                     and browser_window["start"] <= event.get("wall_ms",0) <= browser_window["end"]]
    client_cpu, prior_client = [], None
    for sample in sorted(client_system, key=lambda event:event["wall_ms"]):
        if not sample.get("processes"): continue
        total = sum(process.get("cpu_seconds") or 0 for process in sample.get("processes", []))
        if prior_client and sample["wall_ms"] > prior_client[0] and total >= prior_client[1]:
            client_cpu.append(100000 * (total - prior_client[1]) / (sample["wall_ms"] - prior_client[0]))
        prior_client = (sample["wall_ms"], total)
    client_stall_ms = []
    prior_stall = None
    for sample in sorted(client_system, key=lambda event:event["wall_ms"]):
        value = sample.get("long_task_ms")
        if value is None: continue
        if prior_stall is not None and value >= prior_stall: client_stall_ms.append(value - prior_stall)
        prior_stall = value
    cpu = {}
    for sample in pi:
        by_role = {}
        for process in sample.get("processes", []):
            if process.get("cpu_percent_one_core") is not None:
                by_role[process["role"]] = by_role.get(process["role"], 0) + process["cpu_percent_one_core"]
        for role,total in by_role.items():
            cpu.setdefault(role, []).append(total)
    baseline = case.get("diagnostic_level") == "baseline"
    if omitted: errors.append("snapshot_omitted_units")
    if not baseline and case["workload"] == "fighting" and snapshots and not any(attack_samples):
        errors.append("no_native_attacks_observed")
    if not snapshots and not baseline: errors.append("missing_openbw_snapshots")
    if not bw: errors.append("missing_openbw_frame_summary")
    if case["client"] in ("local", "remote", "native") and not render and not baseline:
        errors.append("missing_client_native_presentation")
    if case["client"] == "remote" and not rtt: errors.append("missing_tailscale_rtt")
    server_snapshot = {event.get("seq"):event for event in selected if event.get("stage") == "snapshot_publish"}
    bridge_snapshot = {event.get("seq"):event for event in selected if event.get("stage") == "snapshot_transform"}
    plugin_received = {event.get("seq"):event for event in selected if event.get("stage") == "snapshot_receive"
                       and event.get("clock_domain") == "pi-monotonic"}
    snapshot_to_bridge = []
    bridge_to_plugin = []
    for seq,published in server_snapshot.items():
        transformed = bridge_snapshot.get(seq)
        received = plugin_received.get(seq)
        if transformed and transformed.get("mono_ns",0) >= published.get("mono_ns",0):
            snapshot_to_bridge.append((transformed["mono_ns"]-published["mono_ns"])/1e6)
        if received and transformed and received.get("mono_ms",0)*1e6 >= transformed.get("mono_ns",0):
            bridge_to_plugin.append(received["mono_ms"]-transformed["mono_ns"]/1e6)
    trace_events = [event for event in events if event.get("case") == case["label"]]
    command_inputs = {event.get("request_id"):event for event in trace_events
                      if event.get("stage") == "command_input" and event.get("clock_domain") == "browser-monotonic"}
    first_moves = [event for event in trace_events if event.get("stage") == "command_first_movement"]
    client_presents = [event for event in trace_events if event.get("stage") == "snapshot_present"
                       and event.get("clock_domain") == "browser-monotonic"]
    client_applied = [event for event in selected if event.get("stage") == "snapshot_action_execute"
                      and event.get("mode") == "client" and event.get("clock_domain") == "browser-monotonic"]
    latest_published = max((event.get("seq",0) for event in snapshots),default=None)
    latest_applied = max((event.get("seq",0) for event in client_applied),default=None)
    latest_presented = max((event.get("seq",0) for event in selected if event.get("stage") == "snapshot_present"
                            and event.get("clock_domain") == "browser-monotonic"),default=None)
    command_presented = []
    for move in first_moves:
        sent = command_inputs.get(move.get("request_id"))
        shown = next((event for event in client_presents if event.get("seq",0) >= move.get("seq",0)),None)
        if sent and shown:
            duration = shown.get("mono_ns",0)/1e6 - sent.get("mono_ms",0)
            if 0 <= duration < 600000: command_presented.append(duration)
    command_visible = command_presented if case["camera"] == "visible" and case["paint"] == "normal" else []
    def browser_ms(event):
        if not event: return None
        if event.get("mono_ms") is not None: return event["mono_ms"]
        if event.get("mono_ns") is not None: return event["mono_ns"] / 1e6
        return None
    def pi_between(first, last):
        if not first or not last or first.get("mono_ns") is None or last.get("mono_ns") is None:
            return None
        value = (last["mono_ns"] - first["mono_ns"]) / 1e6
        return round(value, 3) if 0 <= value < 600000 else None
    def browser_between(first, last):
        left, right = browser_ms(first), browser_ms(last)
        if left is None or right is None: return None
        value = right - left
        return round(value, 3) if 0 <= value < 600000 else None
    movement_by_request = {event.get("request_id"):event for event in first_moves}
    forward_by_request = {event.get("request_id"):event for event in trace_events
                          if event.get("stage") == "command_forward"}
    validation_by_request = {event.get("request_id"):event for event in trace_events
                             if event.get("stage") == "command_validate_end" and event.get("mode") == "server"}
    execution_by_command = {event.get("command_id"):event for event in trace_events
                            if event.get("stage") == "command_execute" and event.get("source") == "openbw-controller"}
    all_client_applied = sorted((event for event in trace_events
                                 if event.get("stage") == "snapshot_action_execute" and event.get("mode") == "client"
                                 and event.get("clock_domain") == "browser-monotonic"),
                                key=lambda event:event.get("seq",0))
    sorted_presents = sorted(client_presents,key=lambda event:event.get("seq",0))
    command_traces = []
    for request_id,sent in sorted(command_inputs.items())[:64]:
        movement = movement_by_request.get(request_id)
        forward = forward_by_request.get(request_id)
        execution = execution_by_command.get(forward.get("command_id")) if forward else None
        applied = next((event for event in all_client_applied
                        if movement and event.get("seq",0) >= movement.get("seq",0)),None)
        presented = next((event for event in sorted_presents
                          if movement and event.get("seq",0) >= movement.get("seq",0)),None)
        validated = validation_by_request.get(request_id)
        command_traces.append({"request_id":request_id,"command_id":forward.get("command_id") if forward else None,
            "native_accepted":execution.get("accepted") if execution else None,
            "bw_execute_frame":execution.get("bw_tick") if execution else None,
            "first_movement_frame":movement.get("bw_tick") if movement else None,
            "first_movement_seq":movement.get("seq") if movement else None,
            "server_validation_ms":round(validated["duration_ms"],3)
                                   if validated and validated.get("duration_ms") is not None else None,
            "forward_to_openbw_execute_ms":pi_between(forward,execution),
            "openbw_execute_to_first_movement_ms":pi_between(execution,movement),
            "browser_input_to_client_apply_ms":browser_between(sent,applied),
            "client_apply_to_present_ms":browser_between(applied,presented),
            "browser_input_to_presented_state_ms":browser_between(sent,presented),
            "browser_input_to_visible_ms":browser_between(sent,presented)
                if case["camera"] == "visible" and case["paint"] == "normal" else None})
    return {"label":case["label"],"count":case["count"],"workload":case["workload"],
            "camera":case["camera"],"paint":case["paint"],"client":case["client"],
            "diagnostic_level":case.get("diagnostic_level","full"),
            "browser_start_attempts":case.get("browser_start_attempts",0),
            "valid":not errors,"errors":errors,"timing":stages,
            "openbw_fps":distribution(bw_fps),"client_fps":distribution([client_whole_fps]),
            "client_fps_active_windows":distribution(render_fps),
            "client_presented_frames":sum(event.get("frames", 0) for event in render),
            "client_presentation_window_seconds":render_window_seconds,
            "openbw_frame_work_p95_ms_windows":distribution(bw_work_p95),
            "openbw_frame_overruns":sum(event.get("overruns", 0) for event in bw),
            "server_tick_rate":distribution([event["ticks"] * 1000 / event["elapsed_ms"] for event in server_ticks
                                             if event.get("elapsed_ms", 0) > 0]),
            "server_tick_overruns":sum(event.get("overruns", 0) for event in server_ticks),
            "client_frame_p95_ms_windows":distribution(client_frames),
            "snapshot_bytes":distribution([event.get("bytes") for event in snapshots]),
            "native_unit_count":distribution([event.get("unit_total") for event in snapshots]),
            "snapshot_rate_per_second":len(snapshots) / ((end - start) / 1e9)
                                       if start and end and end > start and not baseline else None,
            "client_snapshot_actions_per_second":len(client_applied) / render_window_seconds
                                                   if render_window_seconds > 0 and client_applied else None,
            "client_tick_rate":distribution([event["ticks"] * 1000 / event["elapsed_ms"] for event in selected
                                             if event.get("stage") == "tick_summary" and event.get("mode") == "client"
                                             and event.get("role") == client_role and event.get("elapsed_ms", 0) > 0]),
            "snapshot_to_bridge_ms":distribution(snapshot_to_bridge),
            "bridge_to_plugin_ms":distribution(bridge_to_plugin),
            "command_to_visible_ms":distribution(command_visible),
            "command_to_presented_state_ms":distribution(command_presented),
            "command_inputs_observed":len(command_inputs),
            "command_first_moves_observed":len(first_moves),
            "command_visible_observed":len(command_visible),
            "command_presented_state_observed":len(command_presented),
            "command_traces":command_traces,
            "command_traces_omitted":max(0,len(command_inputs)-len(command_traces)),
            "latest_snapshot_seq_published":latest_published,
            "latest_snapshot_seq_client_applied":latest_applied,
            "latest_snapshot_seq_client_presented":latest_presented,
            "unapplied_snapshots_at_end":max(0,latest_published-latest_applied)
                                         if latest_published is not None and latest_applied is not None else None,
            "applied_not_presented_at_end":max(0,latest_applied-latest_presented)
                                           if latest_applied is not None and latest_presented is not None else None,
            "unpresented_snapshots_at_end":max(0,latest_published-latest_presented)
                                            if latest_published is not None and latest_presented is not None else None,
            "browser_websocket_bytes_per_second":distribution([event.get("bytes_in") for event in browser_net]),
            "browser_websocket_messages_per_second":distribution([event.get("messages_in") for event in browser_net]),
            "browser_websocket_interruptions":(max(event.get("closes",0) for event in browser_net)
                                                - min(event.get("closes",0) for event in browser_net))
                                               if browser_net else None,
            "pi_network_bytes_per_second":distribution([(event["bytes_in"] + event["bytes_out"]) / event["elapsed_s"]
                                                       for event in pi_net]),
            "omitted_units":omitted,"attacking_units":distribution(attack_samples),
            "tailscale_rtt_ms":distribution(rtt),
            "tailscale_rtt_variation_ms":round(statistics.pstdev(rtt),3) if len(rtt)>1 else None,
            "tailscale_loss_samples":sum(event.get("loss", 0) for event in ping_samples),
            "tailscale_samples":len(ping_samples),
            "tailscale_paths":{path:sum(event.get("path") == path for event in ping_samples)
                               for path in ("direct","derp","unavailable")},
            "cpu_percent_one_core":{role:distribution(values) for role, values in cpu.items()},
            "client_cpu_percent_one_core":distribution(client_cpu),
            "client_rss_bytes_max":max((sum(process.get("rss_bytes") or 0 for process in sample.get("processes", []))
                                        for sample in client_system if sample.get("processes")),default=None),
            "client_js_heap_bytes_max":max((sample["js_heap_bytes"] for sample in client_system
                                            if sample.get("js_heap_bytes") is not None),default=None),
            "client_long_task_ms_per_sample":distribution(client_stall_ms),
            "max_temperature_c":max((event["temperature_c"] for event in pi
                                     if event.get("temperature_c") is not None),default=None),
            "min_memory_available_bytes":min((event["memory_available_bytes"] for event in pi
                                              if event.get("memory_available_bytes") is not None),default=None),
            "min_swap_free_bytes":min((event["swap_free_bytes"] for event in pi
                                      if event.get("swap_free_bytes") is not None),default=None),
            "thermal_throttling_observed":(any((event.get("throttled_flags") or 0) & 0x5 for event in pi)
                                           if any(event.get("throttled_flags") is not None for event in pi)
                                           else None)}


def diagnose(cases):
    findings = []
    valid = [case for case in cases if case["valid"] and case.get("diagnostic_level") != "baseline"]
    for case in valid:
        bw = case["openbw_fps"]["median"]
        if bw is not None and bw < 22:
            findings.append((max(0, 24 - bw), "simulation", f"{case['label']}: OpenBW median {bw:.1f} FPS"))
        frame = case["client_frame_p95_ms_windows"]["median"]
        if frame is not None and frame > 40:
            findings.append((frame / 10, "rendering", f"{case['label']}: native presented-frame p95 window median {frame:.1f} ms"))
        apply = case["timing"].get("snapshot_apply.duration_us", {}).get("p95")
        if apply is not None and apply > 10000:
            findings.append((apply / 10000, "synchronization", f"{case['label']}: snapshot apply p95 {apply / 1000:.1f} ms"))
        transform = case["timing"].get("snapshot_transform.transform_us", {}).get("p95")
        if transform is not None and transform > 10000:
            findings.append((transform / 10000, "synchronization",
                             f"{case['label']}: bridge actor transformation p95 {transform / 1000:.1f} ms"))
        queue = case["timing"].get("snapshot_action_execute.queue_ms", {}).get("p95")
        if queue is not None and queue > 50:
            findings.append((queue / 50, "synchronization",
                             f"{case['label']}: synchronized snapshot queue p95 {queue:.1f} ms"))
        backlog = case.get("unpresented_snapshots_at_end")
        if backlog is not None and backlog > 20:
            findings.append((backlog / 20, "synchronization",
                             f"{case['label']}: {backlog} published snapshots remained unpresented at the aligned window end"))
        if case["thermal_throttling_observed"]:
            findings.append((5, "resource saturation", f"{case['label']}: Pi reported throttling"))
        free_memory = case.get("min_memory_available_bytes")
        if free_memory is not None and free_memory < 536870912:
            findings.append((3, "resource saturation",
                             f"{case['label']}: Pi available memory fell below 512 MiB"))
    for case in valid:
        if case["camera"] != "visible" or case["paint"] != "normal": continue
        baseline = case["client_fps"]["median"]
        if baseline is None: continue
        alternatives = [other for other in valid if other["count"] == case["count"]
                        and other["workload"] == case["workload"] and other["client"] == case["client"]
                        and (other["camera"] == "away" or other["paint"] == "suppressed")]
        for other in alternatives:
            fps = other["client_fps"]["median"]
            if fps and fps > baseline * 1.15:
                findings.append((fps / max(baseline, 1), "rendering",
                                 f"{case['label']} to {other['label']}: client FPS {baseline:.1f} to {fps:.1f}"))
    for remote in (case for case in valid if case["client"] == "remote"):
        local = next((case for case in valid if case["client"] == "local"
                      and all(case[field] == remote[field] for field in ("count","workload","camera","paint"))),None)
        if not local: continue
        remote_visible = remote["command_to_visible_ms"]["median"]
        local_visible = local["command_to_visible_ms"]["median"]
        rtt = remote["tailscale_rtt_ms"]["p95"]
        remote_fps, local_fps = remote["client_fps"]["median"], local["client_fps"]["median"]
        if (remote_visible and local_visible and rtt and remote_fps and local_fps
                and remote_fps >= local_fps * .85 and remote_visible > local_visible * 1.5):
            findings.append((remote_visible / local_visible, "network",
                             f"{remote['label']}: command-to-visible {remote_visible:.1f} ms versus local "
                             f"{local_visible:.1f} ms; Tailscale RTT p95 {rtt:.1f} ms"))
    findings.sort(reverse=True)
    return [{"category":category,"evidence":evidence} for _,category,evidence in findings[:8]]


def overhead_pairs(cases):
    found = {}
    for case in cases:
        key = (case["count"],case["workload"],case["camera"],case["paint"],case["client"],
               case["label"].split("-r")[-1].split("-")[0])
        found.setdefault(key,{})[case.get("diagnostic_level","full")] = case
    pairs = []
    for variants in found.values():
        full, baseline = variants.get("full"), variants.get("baseline")
        if not full or not baseline or not full["valid"] or not baseline["valid"]: continue
        measured = full["openbw_frame_work_p95_ms_windows"]["median"]
        reference = baseline["openbw_frame_work_p95_ms_windows"]["median"]
        if measured is None or not reference: continue
        percent = round(100 * (measured / reference - 1), 2)
        pairs.append({"case":full["label"],"baseline_work_p95_ms":reference,
                      "diagnostic_work_p95_ms":measured,"overhead_percent":percent,
                      "within_five_percent_target":percent < 5})
    return pairs


def report(summary):
    lines = ["# StarCoaster gameplay performance", "", f"Run: `{summary['run_id']}`",
             f"Git revision: `{summary['git_revision']}`",
             f"Analysis revision: `{summary['analysis_revision']}`", "",
             "## Results", "",
             "| Case | Valid | OpenBW FPS median | OpenBW work p95 ms | BW overruns | Native attackers max | Client FPS whole window | Client p95 frame window ms | Snapshot bytes median | Pi °C max | RTT ms median |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    def fmt(value): return "unavailable" if value is None else f"{value:.1f}" if isinstance(value, float) else str(value)
    for case in summary["cases"]:
        lines.append("| " + " | ".join([case["label"], "yes" if case["valid"] else "no",
            fmt(case["openbw_fps"]["median"]),fmt(case["openbw_frame_work_p95_ms_windows"]["median"]),
            fmt(case["openbw_frame_overruns"]),fmt(case["attacking_units"]["max"]),
            fmt(case["client_fps"]["median"]),
            fmt(case["client_frame_p95_ms_windows"]["median"]),fmt(case["snapshot_bytes"]["median"]),
            fmt(case["max_temperature_c"]),fmt(case["tailscale_rtt_ms"]["median"])]) + " |")
    lines += ["", "## Pipeline and resources", "",
              "| Case | Server ticks/s | Client ticks/s | Tick overruns | Snapshots/s | Client actions/s | Unapplied snapshots | Applied not presented | BW→Go p95 ms | Go→plugin p95 ms | Native apply p95 ms | WS KiB/s median | Command→presented p95 ms | Command→visible p95 ms | RTT variation ms |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for case in summary["cases"]:
        apply = case["timing"].get("snapshot_apply.duration_us",{}).get("p95")
        ws = case["browser_websocket_bytes_per_second"]["median"]
        lines.append("| " + " | ".join([case["label"],fmt(case["server_tick_rate"]["median"]),
            fmt(case["client_tick_rate"]["median"]),fmt(case["server_tick_overruns"]),
            fmt(case["snapshot_rate_per_second"]),fmt(case["client_snapshot_actions_per_second"]),
            fmt(case["unapplied_snapshots_at_end"]),fmt(case["applied_not_presented_at_end"]),
            fmt(case["snapshot_to_bridge_ms"]["p95"]),fmt(case["bridge_to_plugin_ms"]["p95"]),
            fmt(apply / 1000 if apply is not None else None),fmt(ws / 1024 if ws is not None else None),
            fmt(case["command_to_presented_state_ms"]["p95"]),
            fmt(case["command_to_visible_ms"]["p95"]),fmt(case["tailscale_rtt_variation_ms"])]) + " |")
    lines += ["", "| Case | Pi process CPU median (% of one core) | Client CPU median (% of one core) | Client RSS max MiB | Pi free memory min GiB | Pi network KiB/s median | Native units min–max | Snapshot p95 bytes | Client frame window p99 ms | Omitted actors |",
              "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |"]
    for case in summary["cases"]:
        cpu = ", ".join(f"{role} {fmt(stats['median'])}" for role,stats in sorted(case["cpu_percent_one_core"].items())) or "unavailable"
        pi_bytes = case["pi_network_bytes_per_second"]["median"]
        client_rss = case["client_rss_bytes_max"]
        free_memory = case["min_memory_available_bytes"]
        unit_count = case["native_unit_count"]
        lines.append(f"| {case['label']} | {cpu} | {fmt(case['client_cpu_percent_one_core']['median'])} | "
                     f"{fmt(client_rss / 1048576 if client_rss is not None else None)} | "
                     f"{fmt(free_memory / 1073741824 if free_memory is not None else None)} | "
                     f"{fmt(pi_bytes / 1024 if pi_bytes is not None else None)} | "
                     f"{fmt(unit_count['min'])}–{fmt(unit_count['max'])} | {fmt(case['snapshot_bytes']['p95'])} | "
                     f"{fmt(case['client_frame_p95_ms_windows']['p99'])} | {case['omitted_units']} |")
    lines += ["", "| Case | Browser long-task time p95 ms/sample | Browser JS heap max MiB |",
              "| --- | ---: | ---: |"]
    for case in summary["cases"]:
        heap = case["client_js_heap_bytes_max"]
        lines.append(f"| {case['label']} | {fmt(case['client_long_task_ms_per_sample']['p95'])} | "
                     f"{fmt(heap / 1048576 if heap is not None else None)} |")
    lines += ["", "## Network diagnostics", "",
              "| Case | RTT p95 ms | RTT variation ms | Lost probes | Direct | DERP | WS interruptions | WebSocket received KiB/s median |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for case in summary["cases"]:
        ws_bytes = case["browser_websocket_bytes_per_second"]["median"]
        lines.append(f"| {case['label']} | {fmt(case['tailscale_rtt_ms']['p95'])} | "
                     f"{fmt(case['tailscale_rtt_variation_ms'])} | "
                     f"{case['tailscale_loss_samples']}/{case['tailscale_samples']} | "
                     f"{case['tailscale_paths']['direct']} | {case['tailscale_paths']['derp']} | "
                     f"{fmt(case['browser_websocket_interruptions'])} | "
                     f"{fmt(ws_bytes / 1024 if ws_bytes is not None else None)} |")
    lines += ["", "| Case | Input commands | Native first movements | State presented | Movement visible |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for case in summary["cases"]:
        lines.append(f"| {case['label']} | {case['command_inputs_observed']} | "
                     f"{case['command_first_moves_observed']} | {case['command_presented_state_observed']} | "
                     f"{case['command_visible_observed']} |")
    lines += ["", "## Command trace examples", "",
              "| Case | Request | Server validation ms | Go forward→OpenBW execute ms | OpenBW execute→movement ms | Browser input→client apply ms | Client apply→present ms | Browser input→visible ms |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for case in summary["cases"]:
        for trace in case["command_traces"][:3]:
            lines.append("| " + " | ".join([case["label"],fmt(trace["request_id"]),
                fmt(trace["server_validation_ms"]),fmt(trace["forward_to_openbw_execute_ms"]),
                fmt(trace["openbw_execute_to_first_movement_ms"]),
                fmt(trace["browser_input_to_client_apply_ms"]),fmt(trace["client_apply_to_present_ms"]),
                fmt(trace["browser_input_to_visible_ms"])]) + " |")
    lines += ["", "## Instrumentation overhead", ""]
    if summary["overhead_pairs"]:
        lines += ["| Case | Minimal timing p95 work ms | Full diagnostics p95 work ms | Additional work | Under 5% target |",
                  "| --- | ---: | ---: | ---: | --- |"]
        for pair in summary["overhead_pairs"]:
            lines.append(f"| {pair['case']} | {fmt(pair['baseline_work_p95_ms'])} | "
                         f"{fmt(pair['diagnostic_work_p95_ms'])} | {fmt(pair['overhead_percent'])}% | "
                         f"{'yes' if pair['within_five_percent_target'] else 'no'} |")
        lines.append("The baseline retains only OpenBW frame timing to provide a p95 reference; it disables snapshot, bridge, native renderer, and gateway telemetry.")
    else:
        lines.append("No matched baseline was measured. Run the same case with `--overhead-pair` before claiming the 5% target.")
    lines += ["", "## Suspected bottlenecks", ""]
    if summary["suspected_bottlenecks"]:
        lines += [f"{index}. **{item['category']}**: {item['evidence']}" for index,item in enumerate(summary["suspected_bottlenecks"],1)]
    else: lines.append("No bottleneck is ranked until valid measurements show a regression.")
    lines += ["", "## Limits", ""]
    for case in summary["cases"]:
        if case["errors"]: lines.append(f"- `{case['label']}`: {', '.join(case['errors'])}")
    if not any(case["client"] == "remote" and case["valid"] for case in summary["cases"]):
        lines.append("- No valid remote laptop run; remote Tailscale impact remains unmeasured.")
    if summary.get("background_roles"):
        roles = ", ".join(f"{role} {count}" for role,count in sorted(summary["background_roles"].items()))
        lines.append(f"- Other gameplay processes were active on the Pi at startup ({roles}); host resource comparisons include that load.")
    lines.append("- Pi stages use Linux monotonic time. Browser timings use its local monotonic clock; cross-machine one-way delay is not inferred.")
    lines.append("- Client FPS counts native presented frames over the entire measurement window, including periods with no frame.")
    lines.append("- Client frame percentiles are native presentation-interval summaries per second; the table shows the median of those p95 windows.")
    lines.append("- Command traces may span warm-up and measurement; only a command and its matched browser presentation contribute a latency sample.")
    lines.append("- Command-to-visible timing uses the first native presented frame carrying the movement snapshot when the camera is centered and painting is enabled; it does not verify individual pixels.")
    lines.append("- Screenshot and video capture were disabled for measured cases.")
    lines += ["", "## Next optimization milestone", ""]
    if summary["suspected_bottlenecks"]:
        top = summary["suspected_bottlenecks"][0]
        lines.append(f"Prioritize {top['category']} after reproducing this result. Preserve native OpenBW authority and rerun the same matrix before and after changes.")
    else:
        lines.append("Collect valid local and remote battle cases, then prioritize the largest measured stage.")
    return "\n".join(lines) + "\n"


def case_matrix(args):
    if args.matrix:
        counts, workloads = COUNTS, WORKLOADS
        cameras, paints = ("visible", "away"), ("normal", "suppressed")
        clients = ("local", "remote") if args.remote_host else ("local",)
    else:
        counts, workloads = args.counts, args.workloads
        cameras, paints, clients = args.cameras, args.painting, args.clients
    levels = ("baseline", "full") if args.overhead_pair else ("full",)
    cases = []
    for count in counts:
        for workload in workloads:
            if count == 0 and workload != "idle": continue
            for camera in cameras:
                for paint in paints:
                    for client in clients:
                        repeats = args.representative_repeats if args.matrix and (count,workload,camera,paint) == (50,"fighting","visible","normal") else args.repeats
                        for repeat in range(1, repeats+1):
                            for level in levels:
                                label = f"u{count}-{workload}-{camera}-{paint}-{client}-r{repeat}"
                                if args.overhead_pair: label += "-" + level
                                cases.append({"label":label,"count":count,"workload":workload,
                                              "camera":camera,"paint":paint,"client":client,
                                              "diagnostic_level":level,
                                              "repeat":repeat,"measure":args.measure,"errors":[]})
    return cases


def wait_marker(log_path, markers, process, timeout, disconnect_log=None, disconnect_offset=0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and process.poll() is None:
        try:
            content = log_path.read_text(errors="replace")[-500000:]
            if any(marker in content for marker in markers): return True
        except FileNotFoundError: pass
        if disconnect_log and disconnect_log.exists():
            with disconnect_log.open("rb") as gateway_file:
                gateway_file.seek(disconnect_offset)
                gateway = gateway_file.read(10000).decode(errors="replace")
            if "OpenRCT2 gateway disconnected:" in gateway or "OpenRCT2 gateway closed:" in gateway:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill()
                return False
        time.sleep(1)
    return False


def wait_port(port, process, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and process.poll() is None:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1): return True
        except OSError: time.sleep(1)
    return False


def redact_remote_artifacts(case_dir, args):
    if not args.remote_host: return
    for path in (case_dir / "browser.log", case_dir / "browser-attempt1.log",
                 case_dir / "browser/runtime.json"):
        if not path.exists(): continue
        content = path.read_text(errors="replace")
        for secret in (args.remote_url, args.remote_host, args.tailscale_peer):
            if secret: content = content.replace(secret, "<private-peer>")
        path.write_text(content)


def run_case(case, run_dir, args, plan):
    case_dir = run_dir / "cases" / case["label"]
    raw = case_dir / "raw"
    raw.mkdir(parents=True)
    scenario = fixture(case["count"], case["workload"], case_dir / "scenario.json", plan["park"])
    subprocess.run([str(ROOT / "scripts/project.sh"), "validate-scenario", str(scenario)], cwd=ROOT,
                   stdout=subprocess.DEVNULL, check=True)
    native_map = case_dir / "native.scm"
    subprocess.run([sys.executable, str(ROOT / "scripts/create-world-base-map.py"),
                    "--scenario", str(scenario), "--output", str(native_map)], cwd=ROOT,
                   stdout=subprocess.DEVNULL, check=True)
    # The OpenBW Unix socket has a 108-byte Linux path limit. Keep its runtime
    # path short while linking it from the case artifact for inspection.
    runtime = ROOT / "run-data/perf-runtime" / (run_dir.name[-6:] + "-" + hashlib.sha256(case["label"].encode()).hexdigest()[:8])
    runtime.mkdir(parents=True, exist_ok=True)
    (case_dir / "runtime").symlink_to(runtime)
    perf_env = ({"STARCOASTER_PERF_DIR":str(raw),"STARCOASTER_PERF":"1"}
                if case.get("diagnostic_level") != "baseline"
                else {"STARCOASTER_PERF_BASELINE_DIR":str(raw),"STARCOASTER_PERF":"0"})
    env = session_environment(plan, {"BRIDGE_MAP_FILE":str(native_map),
        "BRIDGE_SCENARIO_CONFIG":str(scenario),"BRIDGE_RUNTIME_DIR":str(runtime),
        "BRIDGE_SPAWN_JOURNAL":str(runtime / "spawns.json"),"BRIDGE_LAUNCH_CLIENT":"1" if case["client"] == "native" else "0",
        "BRIDGE_CLIENT_LOG_FILE":str(case_dir / "native-client.log"),
        "BRIDGE_SERVE_WASM":"1" if args.gateway == "launch" else "0",
        "BRIDGE_WASM_BUNDLE":str(ROOT / "build/wasm-client"),
        "WASM_LISTEN_ADDRESS":f"127.0.0.1:{args.wasm_port}",
        "OPENRCT2_PORT":str(args.openrct2_port),
        "STARCOASTER_BRIDGE_PORT":str(args.bridge_port_base),
        "BRIDGE_OPENBW_PORT":str(args.bridge_port_base + 1),
        "BRIDGE_CONTROLLER_PORT":str(args.bridge_port_base + 2),
        "BRIDGE_WASM_LOG_FILE":str(case_dir / "gateway.log"),
        **perf_env,
        "STARCOASTER_SUPPRESS_PAINT":"1" if case["paint"] == "suppressed" else "0",
        **workload_environment(case["workload"], runtime / "assault-enable")})
    if case.get("diagnostic_level") == "baseline": env.pop("STARCOASTER_PERF_DIR", None)
    session_log = (case_dir / "session.log").open("w")
    session = subprocess.Popen([str(ROOT / "scripts/run-world-session.sh"),plan["park"]],
        cwd=ROOT, env=env, stdout=session_log, stderr=subprocess.STDOUT, start_new_session=True)
    browser = None
    browser_log = None
    try:
        if not wait_marker(case_dir / "session.log", ("WORLD_READY", "world.ready"), session, args.ready_timeout):
            case["errors"].append("session_not_ready")
            return
        if case["client"] in ("local", "remote"):
            if args.gateway == "launch" and not wait_port(args.wasm_port,session,args.ready_timeout):
                case["errors"].append("gateway_not_ready")
                return
            browser_dir = case_dir / "browser"
            browser_dir.mkdir()
            browser_env = {"WASM_PERF_RUN":"1","WASM_PERF_CAMERA":case["camera"],
                "WASM_PERF_BASELINE":"1" if case.get("diagnostic_level") == "baseline" else "0",
                "WASM_PERF_WORKLOAD":case["workload"],
                "WASM_PERF_SUPPRESS_PAINT":"1" if case["paint"] == "suppressed" else "0",
                "WASM_LIVE_CAMERA":"0" if case["count"] == 0 else "1",
                "WASM_LIVE_RECORD":"0","WASM_LIVE_SCREENCAST":"0",
                "WASM_LIVE_DURATION_MS":str(args.measure * 1000),
                "WASM_LIVE_BOOT_TIMEOUT_MS":"420000",
                "WASM_TEST_PORT":str(args.openrct2_port),
                "WASM_PERF_WARMUP_MS":str(args.warmup * 1000),
                "WASM_LIVE_URL":args.remote_url if case["client"] == "remote" else args.browser_url,
                "WASM_PERF_ARTIFACTS":str(browser_dir)}
            if case["client"] == "remote":
                remote_dir = f"{args.remote_root}/run-data/performance/{run_dir.name}/cases/{case['label']}/browser"
                browser_env["WASM_PERF_ARTIFACTS"] = remote_dir
                browser_env["WASM_LIVE_PROFILE"] = f"{args.remote_root}/build/performance-chromium-profile"
                assignments = " ".join(f"{key}={shlex.quote(value)}" for key,value in browser_env.items())
                command = f"mkdir -p {shlex.quote(remote_dir)} && cd {shlex.quote(args.remote_root)} && {assignments} node browser/live-test.mjs"
            else:
                browser_env["WASM_LIVE_PROFILE"] = str(ROOT / "build/performance-chromium-profile")
            browser_ready = False
            for attempt in (1, 2):
                case["browser_start_attempts"] = attempt
                browser_log = (case_dir / "browser.log").open("w")
                gateway_offset = (case_dir / "gateway.log").stat().st_size if (case_dir / "gateway.log").exists() else 0
                if case["client"] == "remote":
                    browser = subprocess.Popen(["ssh","-o","BatchMode=yes",args.remote_host,command],
                        stdout=browser_log,stderr=subprocess.STDOUT)
                else:
                    browser = subprocess.Popen(["node",str(ROOT / "browser/live-test.mjs")],cwd=ROOT,
                        env={**os.environ,**browser_env},stdout=browser_log,stderr=subprocess.STDOUT)
                browser_ready = wait_marker(case_dir / "browser.log", ("CANVAS:",), browser,
                                            args.browser_timeout, case_dir / "gateway.log", gateway_offset)
                if browser_ready: break
                if browser.poll() is None or attempt == 2: break
                browser_log.close()
                browser_log = None
                (case_dir / "browser.log").rename(case_dir / "browser-attempt1.log")
            if not browser_ready:
                case["errors"].append("browser_not_ready")
                return
        time.sleep(args.warmup)
        if case["workload"] == "fighting":
            (runtime / "assault-enable").touch()
            (case_dir / "benchmark-events.jsonl").write_text(json.dumps({"source":"benchmark",
                "stage":"assault_release","mono_ns":time.monotonic_ns(),"count":case["count"]})+"\n")
        case["measurement_start_utc"] = datetime.now(timezone.utc).isoformat()
        case["measurement_start_pi_mono_ns"] = time.monotonic_ns()
        previous = {}
        previous_network = network_bytes()
        last_sample = time.monotonic()
        end = last_sample + args.measure
        ping_future = None
        with ThreadPoolExecutor(max_workers=1) as pool, (case_dir / "pi-system.jsonl").open("w") as system_file, (case_dir / "pi-network.jsonl").open("w") as network_file:
            sample_index = 0
            while time.monotonic() < end and session.poll() is None:
                now = time.monotonic()
                if browser and browser.poll() is not None and now < end - 1:
                    case["errors"].append("browser_exited_during_measurement")
                    break
                elapsed = max(.001, now - last_sample)
                last_sample = now
                pids = process_ids(session.pid)
                if case["client"] == "local" and browser and browser.poll() is None:
                    pids.update(process_ids(browser.pid))
                samples = [value for pid in pids if (value := sample_process(pid, previous, elapsed))]
                system_file.write(json.dumps({"source":"pi","wall_utc":datetime.now(timezone.utc).isoformat(),
                    "pi_mono_ns":time.monotonic_ns(),"processes":samples,**pi_metrics()}) + "\n")
                current_network = network_bytes()
                if current_network and previous_network:
                    network_file.write(json.dumps({"source":"pi","stage":"network_second",
                        "pi_mono_ns":time.monotonic_ns(),
                        "bytes_in":max(0,current_network[0]-previous_network[0]),
                        "bytes_out":max(0,current_network[1]-previous_network[1]),
                        "elapsed_s":elapsed}) + "\n")
                previous_network = current_network
                if ping_future and ping_future.done():
                    network_file.write(json.dumps({"source":"tailscale","stage":"tailscale_ping",
                        "wall_utc":datetime.now(timezone.utc).isoformat(),**ping_future.result()}) + "\n")
                    ping_future = None
                if args.tailscale_peer and sample_index % 5 == 0 and ping_future is None:
                    ping_future = pool.submit(tailscale_ping,args.tailscale_peer)
                sample_index += 1
                time.sleep(min(1, max(0, end-time.monotonic())))
            if ping_future:
                network_file.write(json.dumps({"source":"tailscale","stage":"tailscale_ping",
                    "wall_utc":datetime.now(timezone.utc).isoformat(),**ping_future.result()}) + "\n")
        case["measurement_end_pi_mono_ns"] = time.monotonic_ns()
        if session.poll() is not None: case["errors"].append("session_interrupted")
        if browser:
            try:
                browser.wait(timeout=120)
            except subprocess.TimeoutExpired:
                case["errors"].append("browser_completion_timeout")
                browser.terminate()
                try: browser.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    browser.kill()
                    browser.wait()
            if browser.returncode != 0: case["errors"].append("browser_failed")
            if case["client"] == "remote":
                source = f"{args.remote_host}:{args.remote_root}/run-data/performance/{run_dir.name}/cases/{case['label']}/browser/."
                copied = subprocess.run(["scp","-q","-r",source,str(case_dir / "browser")],
                                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                if copied.returncode: case["errors"].append("remote_artifacts_missing")
            runtime_path = case_dir / "browser/runtime.json"
            if runtime_path.exists():
                try:
                    result = json.loads(runtime_path.read_text())
                    metrics = result.get("metrics", {})
                    if metrics.get("clientHardware"): case["client_hardware"] = metrics["clientHardware"]
                    if metrics.get("measureStartWallMs") and metrics.get("measureEndWallMs"):
                        case["browser_window"] = {"start":metrics["measureStartWallMs"],"end":metrics["measureEndWallMs"]}
                        if metrics.get("measureStartBrowserMonoMs") and metrics.get("measureEndBrowserMonoMs"):
                            case["browser_window"].update(mono_start=metrics["measureStartBrowserMonoMs"],
                                                          mono_end=metrics["measureEndBrowserMonoMs"])
                    if case["count"]:
                        expected = next((event.get("session") for event in read_events(raw / "bridge-events.jsonl")
                                         if event.get("stage") == "snapshot_transform"),None)
                        actual = next((match.group(1) for record in result.get("records", [])
                                       if (match := re.search(r"WASM_CAMERA_SESSION session=([a-f0-9]+)",
                                                             record.get("text", "")))),None)
                        if expected and actual and expected != actual:
                            case["errors"].append("browser_joined_different_session")
                except (json.JSONDecodeError,OSError): pass
    finally:
        if browser and browser.poll() is None: browser.terminate()
        if browser_log: browser_log.close()
        if case["client"] == "remote": redact_remote_artifacts(case_dir,args)
        if session.poll() is None:
            os.killpg(session.pid, signal.SIGTERM)
            try: session.wait(timeout=10)
            except subprocess.TimeoutExpired: os.killpg(session.pid, signal.SIGKILL); session.wait()
        session_log.close()


def analyze_run(run_dir, metadata, analysis_revision):
    events = list(read_events(run_dir / "events.jsonl"))
    system = list(read_events(run_dir / "system.jsonl"))
    network = list(read_events(run_dir / "network.jsonl"))
    results = [summarize_case(events, system, network, case) for case in metadata["cases"]]
    summary = {"run_id":metadata["run_id"],"git_revision":metadata["git_revision"],
               "analysis_revision":analysis_revision,"background_roles":metadata.get("background_roles",{}),
               "complete":all(case["valid"] for case in results),
               "cases":results,"suspected_bottlenecks":diagnose(results),
               "overhead_pairs":overhead_pairs(results)}
    (run_dir / "summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    (run_dir / "report.md").write_text(report(summary))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix",action="store_true",help="run all unit/workload/camera/paint comparisons")
    parser.add_argument("--overhead-pair",action="store_true",help="run a minimal timing baseline and full diagnostics for each case")
    parser.add_argument("--counts",nargs="+",type=int,default=[50],choices=COUNTS)
    parser.add_argument("--workloads",nargs="+",default=["fighting"],choices=WORKLOADS)
    parser.add_argument("--cameras",nargs="+",default=["visible"],choices=("visible","away"))
    parser.add_argument("--painting",nargs="+",default=["normal"],choices=("normal","suppressed"))
    parser.add_argument("--clients",nargs="+",default=["local"],choices=("local","remote","native","none"))
    parser.add_argument("--repeats",type=int,default=1)
    parser.add_argument("--representative-repeats",type=int,default=3)
    parser.add_argument("--warmup",type=int,default=15)
    parser.add_argument("--measure",type=int,default=60)
    parser.add_argument("--ready-timeout",type=int,default=180)
    parser.add_argument("--browser-timeout",type=int,default=900)
    parser.add_argument("--browser-url",default="http://127.0.0.1:8092/")
    parser.add_argument("--remote-url",help="private Pi HTTPS origin reachable by the laptop")
    parser.add_argument("--remote-host",help="SSH host for the laptop")
    parser.add_argument("--remote-root",help="StarCoaster checkout on the laptop")
    parser.add_argument("--tailscale-peer",help="laptop Tailscale peer for in-run RTT checks")
    parser.add_argument("--gateway",choices=("launch","existing"),default="launch")
    parser.add_argument("--wasm-port",type=int,default=8092)
    parser.add_argument("--openrct2-port",type=int,default=11754)
    parser.add_argument("--bridge-port-base",type=int,default=40110)
    parser.add_argument("--plan",action="store_true")
    parser.add_argument("--reanalyze-run",type=Path,help="regenerate summary and report from existing artifacts")
    args = parser.parse_args()
    if args.reanalyze_run:
        run_dir = args.reanalyze_run.resolve()
        metadata = json.loads((run_dir / "metadata.json").read_text())
        revision = subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
        summary = analyze_run(run_dir,metadata,revision)
        print(run_dir,flush=True)
        return 0 if summary["complete"] else 1
    if args.measure < 60 and not args.plan: parser.error("steady-state measurement must be at least 60 seconds")
    if args.warmup < 1 or args.repeats < 1 or args.representative_repeats < 3:
        parser.error("warmup/repeats must be positive; representative repeats must be at least three")
    cases = case_matrix(args)
    if any(case["client"] == "remote" for case in cases) and not all((args.remote_host,args.remote_root,args.remote_url,args.tailscale_peer)):
        parser.error("remote cases require --remote-host, --remote-root, --remote-url, and --tailscale-peer")
    if args.plan:
        print(json.dumps({"cases":cases,"count":len(cases)},indent=2))
        return 0
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    run_dir = PERFORMANCE_ROOT / run_id
    run_dir.mkdir(parents=True)
    plan = resolve("example-defense")
    ensure_park(plan)
    git_revision = subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    wasm_manifest_path = ROOT / "build/wasm-client/manifest.json"
    wasm_manifest = json.loads(wasm_manifest_path.read_text()) if wasm_manifest_path.exists() else {}
    metadata = {"run_id":run_id,"git_revision":git_revision,"started_utc":datetime.now(timezone.utc).isoformat(),
        "scenario":"example-defense-geometry + generated performance fixture",
        "hardware":{"model":Path("/proc/device-tree/model").read_bytes().rstrip(b"\0").decode(errors="replace")
                    if Path("/proc/device-tree/model").exists() else platform.machine(),
                    "cpu_count":os.cpu_count(),"kernel":platform.release()},
        "build_versions":{"openrct2":subprocess.check_output(["git","-C",str(ROOT/"upstream/openrct2"),"rev-parse","--short","HEAD"],text=True).strip(),
                          "openbw":subprocess.check_output(["git","-C",str(ROOT/"upstream/openbw"),"rev-parse","--short","HEAD"],text=True).strip(),
                          "wasm_patch_sha256":wasm_manifest.get("patch_sha256"),
                          "wasm_sha256":wasm_manifest.get("artifacts",{}).get("openrct2.wasm")},
        "settings":{"warmup_seconds":args.warmup,"measure_seconds":args.measure,"viewport":"1280x800",
                    "zoom":0,"camera":"test driver","video_capture":False,
                    "openbw_frame_sleep_ms":int(os.environ.get("BRIDGE_FRAME_MS","42"))},
        "clock_domains":{"pi":"Linux CLOCK_MONOTONIC","browser":"WASM steady clock, separate epoch"},
        "background_roles":background_roles(),
        "cases":[{key:value for key,value in case.items() if key != "errors"} for case in cases]}
    (run_dir / "metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
    for index,case in enumerate(cases,1):
        print(f"[{index}/{len(cases)}] {case['label']}",flush=True)
        try: run_case(case,run_dir,args,plan)
        except KeyboardInterrupt:
            case["errors"].append("runner_interrupted")
            for remaining in cases[index:]: remaining["errors"].append("not_started")
            break
        except Exception as error:
            case["errors"].append("runner_error:"+type(error).__name__)
            print(f"  failed: {error}",file=sys.stderr,flush=True)
    metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
    metadata["cases"] = cases
    (run_dir / "metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
    with (run_dir / "events.jsonl").open("w") as events_file, (run_dir / "system.jsonl").open("w") as system_file, (run_dir / "network.jsonl").open("w") as network_file:
        for case in cases: merge_case(run_dir / "cases" / case["label"],events_file,system_file,network_file,case["label"])
    summary = analyze_run(run_dir,metadata,git_revision)
    print(run_dir,flush=True)
    return 0 if summary["complete"] else 1


if __name__ == "__main__": sys.exit(main())
