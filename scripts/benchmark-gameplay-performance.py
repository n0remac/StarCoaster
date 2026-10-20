#!/usr/bin/env python3
"""Run native StarCoaster load cases and merge Pi/browser performance evidence.

Use --matrix for the full unit/workload/camera/paint matrix. A remote client
needs an SSH-accessible laptop checkout and the private Pi WASM HTTPS origin.
No peer address, authentication material, or licensed asset enters artifacts.
"""

import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor
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
        return {"count": 0, "median": None, "p95": None, "p99": None, "max": None}
    def at(fraction):
        return round(numbers[min(len(numbers) - 1, math.ceil(len(numbers) * fraction) - 1)], 3)
    return {"count": len(numbers), "median": at(.5), "p95": at(.95), "p99": at(.99),
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
        if name.startswith("openrct2"): return "openrct2"
        if name == "wasm-server": return "gateway"
        if name == "chromium": return "local-chromium"
        if name == "ffmpeg": return "recorder"
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        pass
    return "launcher"


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
    render = [event for event in selected if event.get("stage") == "present_summary" and event.get("role") == "browser-client"]
    server_ticks = [event for event in selected if event.get("stage") == "tick_summary"
                    and event.get("mode") == "server" and event.get("clock_domain") == "pi-monotonic"]
    snapshots = [event for event in selected if event.get("stage") == "snapshot_publish"]
    omitted = sum(event.get("unit_omitted", 0) for event in snapshots)
    attack_samples = [event.get("unit_attacking", 0) for event in snapshots]
    bw_fps = [event["frames"] * 1e9 / event["elapsed_ns"] for event in bw if event.get("elapsed_ns", 0) > 0]
    bw_work_p95 = [event["work_p95_us"] / 1000 for event in bw if event.get("work_p95_us") is not None]
    render_fps = [event["frames"] * 1e9 / event["elapsed_ns"] for event in render if event.get("elapsed_ns", 0) > 0]
    client_frames = [event.get("frame_p95_us") / 1000 for event in render if event.get("frame_p95_us") is not None]
    net = [event for event in network if event.get("case") == case["label"] and start and end]
    rtt = [event["rtt_ms"] for event in net if event.get("stage") == "tailscale_ping" and event.get("rtt_ms") is not None]
    pi_net = [event for event in net if event.get("source") == "pi" and event.get("stage") == "network_second"
              and event.get("elapsed_s", 0) > 0]
    browser_net = [event for event in net if event.get("source") == "browser" and event.get("stage") == "websocket_second"
                   and (not browser_window or browser_window["start"] <= event.get("wall_ms",0) <= browser_window["end"])]
    pi = [event for event in system if event.get("case") == case["label"] and event.get("source") == "pi" and start and end]
    cpu = {}
    for sample in pi:
        for process in sample.get("processes", []):
            if process.get("cpu_percent_one_core") is not None:
                cpu.setdefault(process["role"], []).append(process["cpu_percent_one_core"])
    if omitted: errors.append("snapshot_omitted_units")
    if case["workload"] == "fighting" and snapshots and not any(attack_samples):
        errors.append("no_native_attacks_observed")
    if not snapshots: errors.append("missing_openbw_snapshots")
    if not bw: errors.append("missing_openbw_frame_summary")
    if case["client"] in ("local", "remote") and not render: errors.append("missing_browser_native_presentation")
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
    command_inputs = {event.get("request_id"):event for event in selected
                      if event.get("stage") == "command_input" and event.get("clock_domain") == "browser-monotonic"}
    first_moves = [event for event in selected if event.get("stage") == "command_first_movement"]
    client_presents = [event for event in selected if event.get("stage") == "snapshot_present"
                       and event.get("clock_domain") == "browser-monotonic"]
    command_visible = []
    for move in first_moves:
        sent = command_inputs.get(move.get("request_id"))
        shown = next((event for event in client_presents if event.get("seq",0) >= move.get("seq",0)),None)
        if sent and shown:
            duration = shown.get("mono_ns",0)/1e6 - sent.get("mono_ms",0)
            if 0 <= duration < 30000: command_visible.append(duration)
    return {"label":case["label"],"count":case["count"],"workload":case["workload"],
            "camera":case["camera"],"paint":case["paint"],"client":case["client"],
            "valid":not errors,"errors":errors,"timing":stages,
            "openbw_fps":distribution(bw_fps),"client_fps":distribution(render_fps),
            "openbw_frame_work_p95_ms_windows":distribution(bw_work_p95),
            "openbw_frame_overruns":sum(event.get("overruns", 0) for event in bw),
            "server_tick_rate":distribution([event["ticks"] * 1000 / event["elapsed_ms"] for event in server_ticks
                                             if event.get("elapsed_ms", 0) > 0]),
            "server_tick_overruns":sum(event.get("overruns", 0) for event in server_ticks),
            "client_frame_p95_ms_windows":distribution(client_frames),
            "snapshot_bytes":distribution([event.get("bytes") for event in snapshots]),
            "snapshot_rate_per_second":len(snapshots) / ((end - start) / 1e9) if start and end and end > start else None,
            "snapshot_to_bridge_ms":distribution(snapshot_to_bridge),
            "bridge_to_plugin_ms":distribution(bridge_to_plugin),
            "command_to_visible_ms":distribution(command_visible),
            "browser_websocket_bytes_per_second":distribution([event.get("bytes_in") for event in browser_net]),
            "browser_websocket_messages_per_second":distribution([event.get("messages_in") for event in browser_net]),
            "pi_network_bytes_per_second":distribution([(event["bytes_in"] + event["bytes_out"]) / event["elapsed_s"]
                                                       for event in pi_net]),
            "omitted_units":omitted,"attacking_units":distribution(attack_samples),
            "tailscale_rtt_ms":distribution(rtt),
            "tailscale_rtt_variation_ms":round(statistics.pstdev(rtt),3) if len(rtt)>1 else None,
            "tailscale_loss_samples":sum(event.get("loss", 0) for event in net if event.get("stage") == "tailscale_ping"),
            "cpu_percent_one_core":{role:distribution(values) for role, values in cpu.items()},
            "max_temperature_c":max((event.get("temperature_c") or 0 for event in pi), default=None),
            "thermal_throttling_observed":any((event.get("throttled_flags") or 0) & 0x5 for event in pi)}


def diagnose(cases):
    findings = []
    valid = [case for case in cases if case["valid"]]
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
        if case["thermal_throttling_observed"]:
            findings.append((5, "resource saturation", f"{case['label']}: Pi reported throttling"))
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
    findings.sort(reverse=True)
    return [{"category":category,"evidence":evidence} for _,category,evidence in findings[:8]]


def report(summary):
    lines = ["# StarCoaster gameplay performance", "", f"Run: `{summary['run_id']}`",
             f"Git revision: `{summary['git_revision']}`", "",
             "## Results", "",
             "| Case | Valid | OpenBW FPS median | OpenBW work p95 ms | BW overruns | Native attackers max | Client FPS median | Client p95 frame window ms | Snapshot bytes median | Pi °C max | RTT ms median |",
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
              "| Case | Server ticks/s | Tick overruns | Snapshots/s | BW→Go p95 ms | Go→plugin p95 ms | Native apply p95 ms | WS KiB/s median | Command→visible p95 ms | RTT variation ms |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for case in summary["cases"]:
        apply = case["timing"].get("snapshot_apply.duration_us",{}).get("p95")
        ws = case["browser_websocket_bytes_per_second"]["median"]
        lines.append("| " + " | ".join([case["label"],fmt(case["server_tick_rate"]["median"]),
            fmt(case["server_tick_overruns"]),fmt(case["snapshot_rate_per_second"]),
            fmt(case["snapshot_to_bridge_ms"]["p95"]),fmt(case["bridge_to_plugin_ms"]["p95"]),
            fmt(apply / 1000 if apply is not None else None),fmt(ws / 1024 if ws is not None else None),
            fmt(case["command_to_visible_ms"]["p95"]),fmt(case["tailscale_rtt_variation_ms"])]) + " |")
    lines += ["", "| Case | Pi process CPU median (% of one core) | Pi network KiB/s median | Snapshot p95 bytes | Client frame window p99 ms | Omitted actors |",
              "| --- | --- | ---: | ---: | ---: | ---: |"]
    for case in summary["cases"]:
        cpu = ", ".join(f"{role} {fmt(stats['median'])}" for role,stats in sorted(case["cpu_percent_one_core"].items())) or "unavailable"
        pi_bytes = case["pi_network_bytes_per_second"]["median"]
        lines.append(f"| {case['label']} | {cpu} | {fmt(pi_bytes / 1024 if pi_bytes is not None else None)} | {fmt(case['snapshot_bytes']['p95'])} | "
                     f"{fmt(case['client_frame_p95_ms_windows']['p99'])} | {case['omitted_units']} |")
    lines += ["", "## Suspected bottlenecks", ""]
    if summary["suspected_bottlenecks"]:
        lines += [f"{index}. **{item['category']}**: {item['evidence']}" for index,item in enumerate(summary["suspected_bottlenecks"],1)]
    else: lines.append("No bottleneck is ranked until valid measurements show a regression.")
    lines += ["", "## Limits", ""]
    for case in summary["cases"]:
        if case["errors"]: lines.append(f"- `{case['label']}`: {', '.join(case['errors'])}")
    if not any(case["client"] == "remote" and case["valid"] for case in summary["cases"]):
        lines.append("- No valid remote laptop run; remote Tailscale impact remains unmeasured.")
    lines.append("- Pi stages use Linux monotonic time. Browser timings use its local monotonic clock; cross-machine one-way delay is not inferred.")
    lines.append("- Client frame percentiles are native presentation-interval summaries per second; the table shows the median of those p95 windows.")
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
    cases = []
    for count in counts:
        for workload in workloads:
            if count == 0 and workload != "idle": continue
            for camera in cameras:
                for paint in paints:
                    for client in clients:
                        repeats = args.representative_repeats if args.matrix and (count,workload,camera,paint) == (50,"fighting","visible","normal") else args.repeats
                        for repeat in range(1, repeats+1):
                            label = f"u{count}-{workload}-{camera}-{paint}-{client}-r{repeat}"
                            cases.append({"label":label,"count":count,"workload":workload,
                                          "camera":camera,"paint":paint,"client":client,
                                          "repeat":repeat,"measure":args.measure,"errors":[]})
    return cases


def wait_marker(log_path, markers, process, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and process.poll() is None:
        try:
            content = log_path.read_text(errors="replace")[-500000:]
            if any(marker in content for marker in markers): return True
        except FileNotFoundError: pass
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
    for path in (case_dir / "browser.log", case_dir / "browser/runtime.json"):
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
        "STARCOASTER_PERF_DIR":str(raw),"STARCOASTER_PERF":"1",
        "STARCOASTER_SUPPRESS_PAINT":"1" if case["paint"] == "suppressed" else "0",
        **workload_environment(case["workload"], runtime / "assault-enable")})
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
                "WASM_PERF_WORKLOAD":case["workload"],
                "WASM_PERF_SUPPRESS_PAINT":"1" if case["paint"] == "suppressed" else "0",
                "WASM_LIVE_CAMERA":"0" if case["count"] == 0 else "1",
                "WASM_LIVE_RECORD":"0","WASM_LIVE_SCREENCAST":"0",
                "WASM_LIVE_DURATION_MS":str(args.measure * 1000),
                "WASM_TEST_PORT":str(args.openrct2_port),
                "WASM_PERF_WARMUP_MS":str(args.warmup * 1000),
                "WASM_LIVE_URL":args.remote_url if case["client"] == "remote" else args.browser_url,
                "WASM_PERF_ARTIFACTS":str(browser_dir)}
            browser_log = (case_dir / "browser.log").open("w")
            if case["client"] == "remote":
                remote_dir = f"{args.remote_root}/run-data/performance/{run_dir.name}/cases/{case['label']}/browser"
                browser_env["WASM_PERF_ARTIFACTS"] = remote_dir
                browser_env["WASM_LIVE_PROFILE"] = f"{args.remote_root}/build/performance-chromium-profile"
                assignments = " ".join(f"{key}={shlex.quote(value)}" for key,value in browser_env.items())
                command = f"mkdir -p {shlex.quote(remote_dir)} && cd {shlex.quote(args.remote_root)} && {assignments} node browser/live-test.mjs"
                browser = subprocess.Popen(["ssh","-o","BatchMode=yes",args.remote_host,command],
                    stdout=browser_log,stderr=subprocess.STDOUT)
            else:
                browser_env["WASM_LIVE_PROFILE"] = str(ROOT / "build/performance-chromium-profile")
                browser = subprocess.Popen(["node",str(ROOT / "browser/live-test.mjs")],cwd=ROOT,
                    env={**os.environ,**browser_env},stdout=browser_log,stderr=subprocess.STDOUT)
            markers = ("CANVAS:",)
            if not wait_marker(case_dir / "browser.log", markers, browser, args.browser_timeout):
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
                elapsed = max(.001, now - last_sample)
                last_sample = now
                pids = process_ids(session.pid)
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
                    if metrics.get("measureStartWallMs") and metrics.get("measureEndWallMs"):
                        case["browser_window"] = {"start":metrics["measureStartWallMs"],"end":metrics["measureEndWallMs"]}
                        if metrics.get("measureStartBrowserMonoMs") and metrics.get("measureEndBrowserMonoMs"):
                            case["browser_window"].update(mono_start=metrics["measureStartBrowserMonoMs"],
                                                          mono_end=metrics["measureEndBrowserMonoMs"])
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix",action="store_true",help="run all unit/workload/camera/paint comparisons")
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
    args = parser.parse_args()
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
    metadata = {"run_id":run_id,"git_revision":git_revision,"started_utc":datetime.now(timezone.utc).isoformat(),
        "scenario":"example-defense-geometry + generated performance fixture",
        "hardware":{"model":Path("/proc/device-tree/model").read_bytes().rstrip(b"\0").decode(errors="replace")
                    if Path("/proc/device-tree/model").exists() else platform.machine(),
                    "cpu_count":os.cpu_count()},
        "build_versions":{"openrct2":subprocess.check_output(["git","-C",str(ROOT/"upstream/openrct2"),"rev-parse","--short","HEAD"],text=True).strip()},
        "settings":{"warmup_seconds":args.warmup,"measure_seconds":args.measure,"viewport":"1280x800",
                    "zoom":0,"camera":"test driver","video_capture":False,
                    "openbw_frame_sleep_ms":int(os.environ.get("BRIDGE_FRAME_MS","42"))},
        "clock_domains":{"pi":"Linux CLOCK_MONOTONIC","browser":"WASM steady clock, separate epoch"},
        "cases":[{key:value for key,value in case.items() if key != "errors"} for case in cases]}
    (run_dir / "metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
    for index,case in enumerate(cases,1):
        print(f"[{index}/{len(cases)}] {case['label']}",flush=True)
        try: run_case(case,run_dir,args,plan)
        except Exception as error:
            case["errors"].append("runner_error:"+type(error).__name__)
            print(f"  failed: {error}",file=sys.stderr,flush=True)
    with (run_dir / "events.jsonl").open("w") as events_file, (run_dir / "system.jsonl").open("w") as system_file, (run_dir / "network.jsonl").open("w") as network_file:
        for case in cases: merge_case(run_dir / "cases" / case["label"],events_file,system_file,network_file,case["label"])
    events = list(read_events(run_dir / "events.jsonl"))
    system = list(read_events(run_dir / "system.jsonl"))
    network = list(read_events(run_dir / "network.jsonl"))
    results = [summarize_case(events,system,network,case) for case in cases]
    summary = {"run_id":run_id,"git_revision":git_revision,"complete":all(case["valid"] for case in results),
               "cases":results,"suspected_bottlenecks":diagnose(results)}
    (run_dir / "summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    (run_dir / "report.md").write_text(report(summary))
    print(run_dir,flush=True)
    return 0 if summary["complete"] else 1


if __name__ == "__main__": sys.exit(main())
