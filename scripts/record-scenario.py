#!/usr/bin/env python3
"""Capture a packaged scenario with one or two graphical clients."""

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import time

from PIL import Image

from artifact_runs import ArtifactRun
from scenario_package import build_native_map, ensure_park, resolve, session_environment
from video_capture import VideoConfig, VideoRecorder, check_dependencies


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "build/openrct2-stage/usr/local/share/openrct2"


def process_memory(root_pid):
    """Read resident memory of the launched server and its native children."""
    rows, pending, seen = [], [root_pid], set()
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        process = Path(f"/proc/{pid}")
        try:
            children = (process / f"task/{pid}/children").read_text().split()
            pending.extend(int(child) for child in children)
            status = (process / "status").read_text()
            match = re.search(r"^VmRSS:\s+(\d+) kB", status, re.MULTILINE)
            command = (process / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            rows.append({"pid": pid, "rss_kib": int(match.group(1)) if match else 0,
                         "command": command[:240]})
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return {"total_rss_kib": sum(row["rss_kib"] for row in rows), "processes": rows}


def wait_for(path, marker, process, seconds):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if marker in path.read_text(errors="replace"):
            return
        if process.poll() is not None:
            raise RuntimeError(f"process exited before {marker}: {path}")
        time.sleep(0.25)
    raise TimeoutError(f"missing {marker}: {path}")


def prepare_packaged_session(plan, out, env):
    ensure_park(plan)
    native_map = build_native_map(plan, out / f"{plan['scenario_id']}.scm")
    env["BRIDGE_MAP_FILE"] = str(native_map)
    return [str(ROOT / "scripts/run-world-session.sh"), plan["park"]], native_map


def verify_navigation_baseline(out, client_logs, server_log, detailed):
    """Check the smoke route separately from its still-manual visual judgment."""
    driver = client_logs[0]
    expected = ["under_rail", "wall_north", "around_end", "wall_south", "return"]
    crossed = re.findall(
        r"NAV_BASELINE_CROSSED time=(\d+) scene=(\w+) actor=(\S+) x=(\d+) y=(\d+)", driver)
    orders = re.findall(
        r"NAV_BASELINE_ORDER time=(\d+) scene=(\w+) actor=(\S+) accepted=(true|false)", driver)
    complete = re.search(r"NAV_BASELINE_COMPLETE time=\d+ actor=([^\s'\x1b]+)", driver)
    trigger = re.search(r"NAV_BASELINE_TRIGGER time=(\d+)", driver)
    metadata_path = out / "video-metadata.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text())
        video_start_ms = int(datetime.fromisoformat(
            metadata["capture_start_utc"]).timestamp() * 1000)
        video_end_ms = int(datetime.fromisoformat(
            metadata["capture_end_utc"]).timestamp() * 1000)
        trigger_in_video = bool(trigger) and video_start_ms <= int(trigger.group(1)) <= video_end_ms
    else:
        trigger_in_video = bool(trigger)
    patch = re.search(
        r"park patch synchronized id=\S+ revision=(\d+) hash=([0-9a-f]{16}) frame=(\d+)", server_log)
    matched_native = bool(patch) and all(
        f"[{role}] navigation-mask hash={patch.group(2)} frame={patch.group(3)} accepted=1" in server_log
        for role in ("world", "world-control"))
    actor_ids = {row[2] for row in crossed + orders}
    checks = {
        "ordinary_wall_accepted": bool(re.search(r"NAV_BASELINE_WALL time=\d+ accepted=true", driver)),
        "started_during_recording": trigger_in_video,
        "native_waypoint_commands": [row[1] for row in orders] == expected
            and all(row[3] == "true" for row in orders),
        "native_waypoint_crossings": [row[1] for row in crossed] == expected,
        "same_runtime_actor": len(actor_ids) == 1 and bool(complete)
            and complete.group(1) in actor_ids,
        "confirmed_native_revision": matched_native,
        "two_camera_rotations": bool(re.search(r"NAV_BASELINE_CAMERA time=\d+ rotation=0", client_logs[0]))
            and bool(re.search(r"NAV_BASELINE_CAMERA time=\d+ rotation=1", client_logs[1])),
        "before_during_after_screenshots": all(
            (out / f"client-{letter}-t{second}.png").is_file()
            for letter in "ab" for second in (2, 6, 10, 14)),
    }
    detailed["navigation_baseline"] = {
        "checks": checks, "runtime_actor_ids": sorted(actor_ids),
        "orders": orders, "crossings": crossed,
        "navigation_revision": int(patch.group(1)) if patch else None,
        "navigation_hash": patch.group(2) if patch else None,
    }
    detailed["capture_complete"] = detailed["capture_complete"] and all(checks.values())
    (out / "visual-verification.json").write_text(json.dumps({
        "wall_occlusion": {"status": "untested", "reason": "requires inspected overlap frames"},
        "elevated_straight": {"status": "navigation-only", "reason": "native crossing requires visual review"},
        "camera_rotations": [0, 1],
    }, indent=2) + "\n")
    (out / "verification.json").write_text(json.dumps(detailed, indent=2) + "\n")
    return detailed


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", help="scenario package ID (default: frontier-outpost)")
    parser.add_argument("--duration", type=int, default=85)
    parser.add_argument("--video-layout", choices=("single", "combined", "separate"), default="combined")
    parser.add_argument("--video-fps", type=int, default=15)
    parser.add_argument("--video-width", type=int, default=960)
    parser.add_argument("--video-crf", type=int, default=30)
    parser.add_argument("--video-preset", default="ultrafast")
    parser.add_argument("--display-width", type=int, default=1280)
    parser.add_argument("--display-height", type=int, default=800)
    parser.add_argument("--graphics", choices=("software", "native"), default="software")
    parser.add_argument("--frame-ms", type=int,
                        help="native frame delay (Mt. Zergling defaults to normal 42 ms; other captures use 70 ms)")
    parser.add_argument("--no-video", action="store_true", help="capture screenshots and logs without FFmpeg")
    parser.add_argument("--cycle-rotations", action="store_true", help="save screenshots from all four park views")
    parser.add_argument("--ridge-probe", action="store_true", help="run the test-only cliff, slope and combat driver on client A")
    parser.add_argument("--ridge-assault", action="store_true", help="test native Zergling approach from below the saved ridge")
    parser.add_argument("--live-construction", action="store_true",
                        help="capture ordinary two-client wall construction and native rerouting")
    parser.add_argument("--mt-zergling-playthrough", action="store_true",
                        help="exercise Mt. Zergling construction and the graphical Spawn Wave button")
    parser.add_argument("--barracks-production", action="store_true",
                        help="center both graphical clients on the Barracks construction site")
    parser.add_argument("--barracks-training-probe", action="store_true",
                        help="test-only automatic Barracks build and native Marine training capture")
    parser.add_argument("--marine-screen-probe", action="store_true",
                        help="check Marine drag selection across Mt. Zergling rotations and zoom levels")
    parser.add_argument("--world-256", action="store_true", help="capture the separate 256x256 scale fixture")
    parser.add_argument("--navigation-baseline", action="store_true",
                        help="capture a close graphical audit of the layered park's wall and elevated rail")
    args = parser.parse_args(argv)
    if not 15 <= args.duration <= 900:
        parser.error("duration must be 15–900 seconds")
    scenario_id = args.scenario or "frontier-outpost"
    if args.frame_ms is None:
        args.frame_ms = 42 if scenario_id == "mt-zergling" else 70
    if not 10 <= args.frame_ms <= 200:
        parser.error("frame pacing must be 10–200 ms")
    if args.world_256 and (args.ridge_probe or args.ridge_assault):
        parser.error("--world-256 cannot be combined with a ridge probe")
    if args.world_256 and args.scenario is not None:
        parser.error("--scenario cannot be combined with --world-256")
    if args.navigation_baseline and (args.scenario is not None or args.world_256
                                     or args.ridge_probe or args.ridge_assault or args.cycle_rotations
                                     or args.live_construction):
        parser.error("--navigation-baseline cannot be combined with another scenario or probe")
    if args.navigation_baseline and args.video_layout == "single":
        parser.error("--navigation-baseline requires two clients")
    if args.live_construction and args.video_layout == "single":
        parser.error("--live-construction requires two clients")
    if args.mt_zergling_playthrough and scenario_id != "mt-zergling":
        parser.error("--mt-zergling-playthrough requires --scenario mt-zergling")
    if args.barracks_production and (scenario_id != "mt-zergling" or args.video_layout == "single"):
        parser.error("--barracks-production requires Mt. Zergling and two clients")
    if args.barracks_training_probe and not args.barracks_production:
        parser.error("--barracks-training-probe requires --barracks-production")
    if args.barracks_training_probe and args.duration < 45:
        parser.error("--barracks-training-probe requires at least 45 seconds")
    if args.marine_screen_probe and (scenario_id != "mt-zergling" or args.mt_zergling_playthrough):
        parser.error("--marine-screen-probe requires Mt. Zergling without the playthrough probe")
    if scenario_id != "frontier-outpost" and (args.ridge_probe or args.ridge_assault
                                             or args.cycle_rotations or args.live_construction):
        parser.error("Frontier visual probes require --scenario frontier-outpost")
    if not args.world_256:
        try:
            args.plan = resolve(scenario_id)
        except (ValueError, OSError, KeyError) as exc:
            parser.error(str(exc))
    else:
        args.plan = None
    try:
        video_config = VideoConfig(args.video_layout, args.video_fps, args.video_width,
                                   args.video_crf, args.video_preset,
                                   args.display_width, args.display_height)
        if not args.no_video:
            check_dependencies()
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    return args, video_config


def main():
    args, video_config = parse_args()
    rct2 = Path(os.environ.get("RCT2_DATA_DIR", "/home/pi/games/rct2"))
    starcraft = Path(os.environ.get("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft"))
    if not rct2.is_dir() or not starcraft.is_dir():
        parser.error("RCT2_DATA_DIR and STARCRAFT_DATA_DIR must point to installed game data")
    scenario_id = "world-256-scale" if args.world_256 else (
        "navigation-occlusion-baseline" if args.navigation_baseline else args.plan["scenario_id"])
    scenario_name = "World 256 Scale Fixture" if args.world_256 else (
        "Navigation Occlusion Baseline" if args.navigation_baseline else
        json.loads(Path(args.plan["scenario"]).read_text())["display_name"])
    run = ArtifactRun("live-capture", scenario_name,
                      config={"scenario": scenario_id, "display_name": scenario_name,
                              "source_scenario": None if args.world_256 else str(
                                  ROOT / "tests/fixtures/navigation-occlusion-baseline.json")
                                  if args.navigation_baseline else args.plan["scenario"],
                              "source_mapping": None if args.world_256 else args.plan["mapping"],
                              "park": None if args.world_256 else str(
                                  ROOT / "run-data/layered-navigation/layered-navigation.park")
                                  if args.navigation_baseline else args.plan["park"],
                              "duration": args.duration,
                              "launcher": "scripts/run-world-session.sh",
                              "input": "X11 mouse and keyboard",
                              "video": None if args.no_video else video_config.__dict__,
                              "graphics": args.graphics, "frame_ms": args.frame_ms,
                              "ridge_probe": args.ridge_probe, "ridge_assault": args.ridge_assault,
                              "live_construction": args.live_construction,
                              "mt_zergling_playthrough": args.mt_zergling_playthrough,
                              "barracks_production": args.barracks_production,
                              "navigation_baseline": args.navigation_baseline,
                              "world_256": args.world_256, "cycle_rotations": args.cycle_rotations})
    out = run.output
    if args.live_construction or args.navigation_baseline:
        server_plugins = out / "server-data/plugin"
        server_plugins.mkdir(parents=True, exist_ok=True)
        (server_plugins / "live-construction-permissions.js").write_text(
            (ROOT / "scripts/live-construction-permissions.js").read_text())
    overrides = {"RCT2_DATA_DIR": str(rct2), "STARCRAFT_DATA_DIR": str(starcraft),
                 "BRIDGE_LAUNCH_CLIENT": "0", "BRIDGE_SERVER_DATA_DIR": str(out / "server-data"),
                 "BRIDGE_CLIENT_DATA_DIR": str(out / "session-client-data"),
                 "BRIDGE_SPAWN_JOURNAL": str(out / "spawn-queue.json"),
                 "SDL_AUDIODRIVER": "dummy", "BRIDGE_FRAME_MS": str(args.frame_ms)}
    env = os.environ.copy() | overrides if args.world_256 else session_environment(args.plan, overrides)
    if args.graphics == "software":
        env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    else:
        env.pop("LIBGL_ALWAYS_SOFTWARE", None)
    if args.ridge_probe:
        env["BRIDGE_DISABLE_ASSAULT_AI"] = "1"
    if args.ridge_assault:
        env["BRIDGE_TEST_ASSAULT_MARINES"] = "1"
    displays = (("client-a", ":91"),) if args.video_layout == "single" else (
        ("client-a", ":91"), ("client-b", ":92"))
    processes = []
    logs = []
    recorder = VideoRecorder(video_config, out) if not args.no_video else None
    recording = False

    def start(name, command, process_env):
        log = (out / f"{name}.log").open("w")
        process = subprocess.Popen(command, cwd=ROOT, env=process_env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(process)
        logs.append(log)
        return process

    status = "failed"
    error = None
    startup_seconds = None
    ready_memory = None
    try:
        if not args.world_256 and not args.ridge_assault and not args.navigation_baseline:
            packaged_command, native_map = prepare_packaged_session(args.plan, out, env)
            run.manifest["capture_config"]["native_map"] = str(native_map)
        for name, display in displays:
            start("display-" + name[-1], ["Xvfb", display, "-screen", "0",
                                           f"{args.display_width}x{args.display_height}x24", "-nolisten", "tcp"], env)
        time.sleep(1)
        if args.world_256:
            fixture = ROOT / "run-data/world-256-park/world-256-scale.park"
            if not fixture.is_file() or fixture.stat().st_mtime < (ROOT / "scripts/world-256-park-generator.js").stat().st_mtime:
                subprocess.run(["python3", str(ROOT / "scripts/create-world-256-park.py")],
                               cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
            test_map = out / "world-256-scale.scm"
            subprocess.run(["python3", str(ROOT / "scripts/create-world-base-map.py"),
                            "--scenario", str(ROOT / "scenarios/world-256-scale-map.json"),
                            "--output", str(test_map)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
            env["BRIDGE_MAP_FILE"] = str(test_map)
            env.pop("BRIDGE_SCENARIO_CONFIG", None)
            session_command = [str(ROOT / "scripts/run-world-session.sh"), str(fixture)]
        elif args.navigation_baseline:
            subprocess.run(["python3", str(ROOT / "scripts/create-layered-navigation-park.py")],
                           cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
            test_scenario = ROOT / "tests/fixtures/navigation-occlusion-baseline.json"
            test_map = out / "navigation-occlusion-baseline.scm"
            subprocess.run(["python3", str(ROOT / "scripts/create-world-base-map.py"),
                            "--scenario", str(test_scenario), "--output", str(test_map)],
                           cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
            env.update(BRIDGE_MAP_FILE=str(test_map), BRIDGE_SCENARIO_CONFIG=str(test_scenario),
                       BRIDGE_RULES_CONFIG=str(ROOT / "scenarios/frontier-outpost/mapping.json"),
                       BRIDGE_DISABLE_ASSAULT_AI="1")
            session_command = [str(ROOT / "scripts/run-world-session.sh"),
                               str(ROOT / "run-data/layered-navigation/layered-navigation.park")]
            run.manifest["capture_config"].update(native_map=str(test_map), park=session_command[-1])
        elif args.ridge_assault:
            scenario = json.loads((ROOT / "scenarios/frontier-outpost/scenario.json").read_text())
            scenario["starting_units"]["zerglings"] = [
                [x, y] for y in range(28, 34) for x in (26, 27)]
            test_scenario = out / "ridge-assault-scenario.json"
            test_scenario.write_text(json.dumps(scenario, indent=2) + "\n")
            test_map = out / "ridge-assault.scm"
            subprocess.run(["python3", str(ROOT / "scripts/create-world-base-map.py"),
                            "--scenario", str(test_scenario), "--output", str(test_map)],
                           cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
            env.update(BRIDGE_MAP_FILE=str(test_map), BRIDGE_SCENARIO_CONFIG=str(test_scenario),
                       BRIDGE_RULES_CONFIG=str(ROOT / "scenarios/frontier-outpost/mapping.json"))
            session_command = [str(ROOT / "scripts/run-world-session.sh"),
                               str(ROOT / "run-data/frontier-playable/save/frontier-outpost-playable.park")]
        else:
            session_command = packaged_command
        session_started = time.monotonic()
        session = start("server", session_command, env)
        until = time.monotonic() + 25
        while time.monotonic() < until:
            try:
                with socket.create_connection(("127.0.0.1", 11753), timeout=0.2):
                    break
            except OSError:
                if session.poll() is not None:
                    raise RuntimeError("scenario launcher exited before park hosting")
                time.sleep(0.2)
        else:
            raise TimeoutError("OpenRCT2 host did not open port 11753")
        clients = {}
        for name, display in displays:
            data_dir = out / name
            (data_dir / "plugin").mkdir(parents=True, exist_ok=True)
            (data_dir / "object").mkdir(exist_ok=True)
            scenery_name = "starcoaster.scenery_large.terran_barracks.parkobj"
            shutil.copyfile(DATA / "object/starcoaster/scenery_large" / scenery_name,
                            data_dir / "object" / scenery_name)
            source = (ROOT / "openrct2-plugin/rts-bridge.js").read_text()
            (data_dir / "plugin/rts-bridge.js").write_text(source)
            if not args.world_256 and scenario_id == "frontier-outpost":
                (data_dir / "plugin/frontier-park-sync-probe.js").write_text(
                    (ROOT / "scripts/frontier-park-sync-probe.js").read_text())
            if args.ridge_probe and name == "client-a":
                (data_dir / "plugin/frontier-ridge-probe.js").write_text(
                    (ROOT / "scripts/frontier-ridge-probe.js").read_text())
            if args.navigation_baseline and name == "client-a":
                (data_dir / "plugin/navigation-baseline-probe.js").write_text(
                    (ROOT / "scripts/navigation-baseline-probe.js").read_text())
            if args.live_construction:
                probe = "live-construction-probe.js" if name == "client-a" else "live-construction-observer.js"
                source = (ROOT / "scripts" / probe).read_text()
                if name == "client-a":
                    source = "var STARCOASTER_VISUAL_TWO_CLIENTS = true;\n" + source
                (data_dir / "plugin" / probe).write_text(source)
            if args.mt_zergling_playthrough and name == "client-a":
                (data_dir / "plugin/mt-zergling-construction-probe.js").write_text(
                    (ROOT / "scripts/mt-zergling-construction-probe.js").read_text())
            if args.barracks_production:
                (data_dir / "plugin/barracks-production-camera.js").write_text(
                    (ROOT / "scripts/barracks-production-camera.js").read_text())
            if args.barracks_training_probe and name == "client-a":
                for probe in ("live-barracks-build-probe.js", "live-barracks-training-probe.js"):
                    (data_dir / "plugin" / probe).write_text((ROOT / "scripts" / probe).read_text())
            if args.marine_screen_probe and name == "client-a":
                (data_dir / "plugin/marine-screen-probe.js").write_text(
                    (ROOT / "scripts/marine-screen-probe.js").read_text())
            if args.navigation_baseline:
                camera = (ROOT / "scripts/navigation-baseline-camera.js").read_text()
                camera = camera.replace("var baselineRotation = 0;",
                                        "var baselineRotation = 0;" if name == "client-a" else
                                        "var baselineRotation = 1;")
                (data_dir / "plugin/navigation-baseline-camera.js").write_text(camera)
            if args.world_256 and name == "client-a":
                (data_dir / "plugin/world-256-scale-probe.js").write_text(
                    (ROOT / "scripts/world-256-scale-probe.js").read_text())
            if args.world_256:
                camera = (ROOT / "scripts/world-256-camera.js").read_text()
                if name == "client-a":
                    camera = camera.replace("var far = false;", "var far = true;")
                (data_dir / "plugin/world-256-camera.js").write_text(camera)
            if args.cycle_rotations:
                (data_dir / "plugin/frontier-camera.js").write_text(
                    (ROOT / "scripts/frontier-camera.js").read_text())
            command = [str(ROOT / "build/openrct2/openrct2"), "join", "127.0.0.1",
                       "--port=11753", f"--rct2-data-path={rct2}",
                       f"--openrct2-data-path={DATA}", f"--user-data-path={data_dir}"]
            for attempt in range(3):
                process = start(name, command, env | {"DISPLAY": display})
                try:
                    wait_for(out / f"{name}.log", "RTS Bridge apply tick=", process, 45)
                except (RuntimeError, TimeoutError):
                    transfer_failed = "Decompression error!" in (out / f"{name}.log").read_text(errors="replace")
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    logs[-1].close()
                    suffix = "transfer-failed" if transfer_failed else "startup-failed"
                    (out / f"{name}.log").rename(out / f"{name}-{suffix}-{attempt + 1}.log")
                    if attempt == 2:
                        raise
                else:
                    clients[name] = process
                    break
        wait_for(out / "server.log", "WORLD_READY", session, 120 if args.world_256 else 45)
        startup_seconds = round(time.monotonic() - session_started, 3)
        if args.world_256:
            ready_memory = process_memory(session.pid)
        time.sleep(2)
        for _, display in displays:
            subprocess.run(["xdotool", "mousemove", "1144", "112", "click", "1"],
                           env=env | {"DISPLAY": display}, check=True)
        print(f"Recording {out}; displays {[display for _, display in displays]}", flush=True)
        for name, display in displays:
            subprocess.run(["scrot", "-z", "-o", str(out / f"{name}-initial.png")],
                           env=env | {"DISPLAY": display}, check=True)
        if recorder:
            recorder.start()
            recording = True
        if args.marine_screen_probe:
            subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+shift+m"],
                           env=env | {"DISPLAY": ":91"}, check=True)
            wait_for(out / "client-a.log", "MARINE_SCREEN_PROBE_START", clients["client-a"], 12)
        if args.navigation_baseline:
            subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+shift+y"],
                           env=env | {"DISPLAY": ":91"}, check=True)
            wait_for(out / "client-a.log", "NAV_BASELINE_TRIGGER time=", clients["client-a"], 12)
            if recorder:
                recorder.event("navigation_baseline_trigger", client="client-a")
        seen_rotations = {name: set() for name, _ in displays}
        baseline_samples = {2, 4, 6, 8, 10, 12, 14, 18, 22, 26} if args.navigation_baseline else set()
        captured_baseline_samples = set()
        mt_wave_clicked = False
        mt_wave_screenshot = False
        mt_marine_clicked = False
        mt_zoomed = False
        mt_samples = set()
        barracks_samples = set()
        marine_screen_seen = 0
        rotation_offsets = {name: len(re.findall(r"FRONTIER_CAMERA rotation=([0-3])",
                              (out / f"{name}.log").read_text(errors="replace")))
                            for name, _ in displays}
        until = time.monotonic() + args.duration
        while time.monotonic() < until:
            if recorder:
                recorder.check_alive()
            if args.marine_screen_probe:
                samples = re.findall(r"MARINE_SCREEN_PROBE rotation=(\d) zoom=(-?\d+) z=(\d+)"
                                     r" x=(-?\d+) y=(-?\d+) tool=([a-z0-9.-]+)",
                                     (out / "client-a.log").read_text(errors="replace"))
                for rotation, zoom, z, x, y, tool in samples[marine_screen_seen:]:
                    marine_screen_seen += 1
                    px, py = int(x), int(y)
                    if not 250 <= px <= args.display_width - 180 or not 190 <= py <= args.display_height - 190:
                        continue
                    subprocess.run(["xdotool", "mousemove", str(px - 230), str(py - 170),
                                    "mousedown", "1", "mousemove", "--sync", str(px + 230),
                                    str(py + 170), "mouseup", "1"],
                                   env=env | {"DISPLAY": ":91"}, check=True)
                    time.sleep(0.2)
                    filename = f"marine-screen-rot{rotation}-zoom{zoom}.png"
                    subprocess.run(["scrot", "-z", "-o", str(out / filename)],
                                   env=env | {"DISPLAY": ":91"}, check=True)
                    if recorder:
                        recorder.event("marine_screen_drag", client="client-a", rotation=int(rotation),
                                       zoom=int(zoom), elevation=int(z), filename=filename)
            if args.mt_zergling_playthrough:
                elapsed = time.monotonic() - recorder.start_monotonic if recorder else args.duration - (until - time.monotonic())
                if not mt_marine_clicked and elapsed >= 5:
                    subprocess.run(["xdotool", "mousemove", "150", "174", "click", "1"],
                                   env=env | {"DISPLAY": ":91"}, check=True)
                    subprocess.run(["xdotool", "mousemove", "620", "365", "click", "1"],
                                   env=env | {"DISPLAY": ":91"}, check=True)
                    mt_marine_clicked = True
                    if recorder:
                        recorder.event("spawn_marine_tool_click", client="client-a")
                server_text = (out / "server.log").read_text(errors="replace")
                if not mt_wave_clicked and "wave=periodic-0001 state=ready" in server_text:
                    subprocess.run(["xdotool", "mousemove", "50", "245", "click", "1"],
                                   env=env | {"DISPLAY": ":91"}, check=True)
                    mt_wave_clicked = True
                    if recorder:
                        recorder.event("spawn_wave_button_click", client="client-a")
                if mt_wave_clicked and not mt_wave_screenshot and re.search(
                        r"wave=manual-\d{4} state=ready", server_text):
                    subprocess.run(["scrot", "-z", "-o", str(out / "mt-zergling-manual-wave.png")],
                                   env=env | {"DISPLAY": ":91"}, check=True)
                    mt_wave_screenshot = True
                    if recorder:
                        recorder.event("manual_wave_active_screenshot", client="client-a",
                                       filename="mt-zergling-manual-wave.png")
                if mt_wave_screenshot and not mt_zoomed:
                    subprocess.run(["xdotool", "mousemove", "114", "52", "click", "1"],
                                   env=env | {"DISPLAY": ":91"}, check=True)
                    mt_zoomed = True
                    if recorder:
                        recorder.event("combat_camera_zoom", client="client-a")
                for second in (150, 300):
                    if elapsed >= second and second not in mt_samples:
                        filename = f"mt-zergling-t{second}.png"
                        subprocess.run(["scrot", "-z", "-o", str(out / filename)],
                                       env=env | {"DISPLAY": ":91"}, check=True)
                        mt_samples.add(second)
                        if recorder:
                            recorder.event("park_defense_screenshot", client="client-a",
                                           second=second, filename=filename)
            if args.barracks_training_probe:
                elapsed = time.monotonic() - recorder.start_monotonic if recorder else args.duration - (until - time.monotonic())
                # The light is dark for five of seven banks. Subsecond samples
                # avoid accidentally capturing only the dark phase.
                for point in (*[round(2 + index * 0.7, 1) for index in range(27)], 24, 32, 40):
                    if elapsed < point or point in barracks_samples:
                        continue
                    for name, display in displays:
                        filename = f"{name}-barracks-t{point}.png"
                        subprocess.run(["scrot", "-z", "-o", str(out / filename)],
                                       env=env | {"DISPLAY": display}, check=True)
                        if recorder:
                            recorder.event("barracks_training_screenshot", client=name,
                                           second=point, filename=filename)
                    barracks_samples.add(point)
            if args.navigation_baseline and recorder:
                elapsed = time.monotonic() - recorder.start_monotonic
                for point in sorted(baseline_samples - captured_baseline_samples):
                    if elapsed < point:
                        break
                    for name, display in displays:
                        filename = f"{name}-t{point}.png"
                        subprocess.run(["scrot", "-z", "-o", str(out / filename)],
                                       env=env | {"DISPLAY": display}, check=True)
                        recorder.event("navigation_baseline_screenshot", client=name,
                                       second=point, filename=filename)
                    captured_baseline_samples.add(point)
            if args.cycle_rotations:
                for name, display in displays:
                    rotations = re.findall(r"FRONTIER_CAMERA rotation=([0-3])",
                                           (out / f"{name}.log").read_text(errors="replace"))
                    fresh = rotations[rotation_offsets[name]:]
                    rotation_offsets[name] = len(rotations)
                    if fresh:
                        rotation = fresh[-1]
                        if rotation not in seen_rotations[name]:
                            time.sleep(0.15)  # allow the viewport to repaint
                            seen_rotations[name].add(rotation)
                            filename = f"{name}-t{len(seen_rotations[name])}-rot{rotation}.png"
                            subprocess.run(["scrot", "-z", "-o", str(out / filename)],
                                           env=env | {"DISPLAY": display}, check=True)
                            if recorder:
                                recorder.event("rotation_screenshot", client=name, rotation=int(rotation), filename=filename)
            time.sleep(min(0.25, max(0, until - time.monotonic())))
        if args.cycle_rotations and any(len(values) != 4 for values in seen_rotations.values()):
            raise RuntimeError(f"not all camera rotations were captured: {seen_rotations}")
        if recorder:
            recording = False
            recorder.stop(True)
        for name, display in displays:
            subprocess.run(["scrot", "-z", "-o", str(out / f"{name}-final.png")],
                           env=env | {"DISPLAY": display}, check=True)
        snapshot = (out / "server.log").read_text(errors="replace")
        client_logs = [(out / f"{name}.log").read_text(errors="replace") for name, _ in displays]
        if args.world_256:
            measured = re.search(r"navigation initialized hash=([0-9a-f]{16}) elapsed_ms=(\d+)", snapshot)
            performance = {"startup_to_world_ready_seconds": startup_seconds,
                           "navigation_initialization_ms": int(measured.group(2)) if measured else None,
                           "navigation_hash": measured.group(1) if measured else None,
                           "memory_at_ready": ready_memory,
                           "memory_after_recording": process_memory(session.pid),
                           "client_snapshot_hz": [round(text.count("RTS Bridge apply tick=") / args.duration, 2)
                                                  for text in client_logs],
                           "recording_seconds": args.duration}
            (out / "performance.json").write_text(json.dumps(performance, indent=2) + "\n")
        report = {"status": "recorded", "scenario": scenario_id,
                  "world_ready": "navigation=native" in snapshot and "WORLD_READY" in snapshot,
                  "outcome": "defeat" if "outcome=defeat" in snapshot else "victory" if "outcome=victory" in snapshot else None,
                  "demolitions": snapshot.count("WORLD_REMOVAL id="),
                  "client_snapshots": [text.count("RTS Bridge apply tick=") for text in client_logs],
                  "client_selection": "selected Marines=openbw:" in client_logs[0],
                  "accepted_marine_order": "accepted=true reason=ok" in client_logs[0],
                  "marine_attack_frames": client_logs[0].count(",attack,112,terran_marine,"),
                  "video_layout": None if args.no_video else args.video_layout,
                  "input_method": "graphical X11 interface"}
        (out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        (out / "scenario-config.json").write_text((ROOT / "scenarios/world-256-scale-map.json"
            if args.world_256 else ROOT / "tests/fixtures/navigation-occlusion-baseline.json"
            if args.navigation_baseline else Path(args.plan["scenario"])).read_text())
        verifier = ("verify-world-256-capture.py" if args.world_256 else
                    "verify-frontier-capture.py" if scenario_id == "frontier-outpost" else
                    "verify-scenario-capture.py")
        subprocess.run(["python3", str(ROOT / "scripts" / verifier), str(out)],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        detailed = json.loads((out / "verification.json").read_text())
        if args.barracks_training_probe:
            animation_hashes = {}
            for name, _ in displays:
                frames = []
                for point in sorted(barracks_samples):
                    with Image.open(out / f"{name}-barracks-t{point}.png") as image:
                        centre_x, centre_y = image.width // 2, image.height // 2
                        # Keep the crop on the Barracks. A newly trained Marine
                        # walks just below it and must not count as animation.
                        pixels = image.crop((centre_x - 100, centre_y - 130,
                                             centre_x + 100, centre_y + 10)).tobytes()
                        frames.append(hashlib.sha256(pixels).hexdigest()[:12])
                animation_hashes[name] = frames
            checks = {
                "park_barracks_built": "BARRACKS_BUILD_PROBE_RESULT accepted=true" in client_logs[0],
                "native_train_accepted": "BARRACKS_TRAIN_PROBE_ACTION accepted=true" in client_logs[0]
                    and "[world-control] train command=" in snapshot,
                "marine_completed_and_moved": "BARRACKS_TRAIN_PROBE_MARINE id=" in client_logs[0]
                    and "BARRACKS_TRAIN_PROBE_MOVE accepted=true" in client_logs[0],
                "animation_visible_on_both_clients": all(len(set(frames)) >= 2
                                                         for frames in animation_hashes.values()),
            }
            detailed["barracks_training_probe"] = {"checks": checks,
                                                   "frame_hashes": animation_hashes}
            detailed["capture_complete"] = detailed["capture_complete"] and all(checks.values())
            detailed["status"] = "passed" if detailed["capture_complete"] else "incomplete"
            (out / "verification.json").write_text(json.dumps(detailed, indent=2) + "\n")
        if args.navigation_baseline:
            verify_navigation_baseline(out, client_logs, snapshot, detailed)
        if args.live_construction:
            driver = client_logs[0]
            observer = client_logs[1] if len(client_logs) > 1 else ""
            patches = re.findall(r"park patch synchronized id=\S+ revision=\d+ hash=([0-9a-f]{16}) frame=(\d+)", snapshot)
            publisher = set(re.findall(r"\[world\] navigation-mask hash=([0-9a-f]{16}) frame=(\d+) accepted=1", snapshot))
            controller = set(re.findall(r"\[world-control\] navigation-mask hash=([0-9a-f]{16}) frame=(\d+) accepted=1", snapshot))
            construction = {
                "ordinary_wall_actions": "LIVE_CONSTRUCTION_BUILD accepted=true" in driver
                    and "LIVE_CONSTRUCTION_REMOVE accepted=true" in driver,
                "two_confirmed_revisions": len(patches) >= 2,
                "both_native_participants": len(patches) >= 2 and
                    all(item in publisher and item in controller for item in patches[:2]),
                "second_client_saw_wall": "LIVE_OBSERVER_WALL present=true" in observer
                    and observer.count("LIVE_OBSERVER_WALL present=false") >= 2,
                "active_actor_movement": "LIVE_CONSTRUCTION_COMPLETE" in driver,
            }
            detailed["live_construction"] = construction
            detailed["capture_complete"] = detailed["capture_complete"] and all(construction.values())
            (out / "verification.json").write_text(json.dumps(detailed, indent=2) + "\n")
        if args.mt_zergling_playthrough:
            driver = client_logs[0]
            wave_instances = re.findall(r"wave=(periodic-\d{4}|manual-\d{4}) state=ready", snapshot)
            simultaneous_zerglings = any(len(re.findall(r"zerg_zergling", line)) >= 2
                                        for line in driver.splitlines() if "RTS Bridge apply tick=" in line)
            checks = {
                "marine_reinforcement": bool(re.search(r"WORLD_SPAWN_STATUS request=\S+:spawn:\d+:\d+ state=ready", snapshot)),
                "automatic_waves": len({wave for wave in wave_instances if wave.startswith("periodic-")}) >= 2,
                "manual_wave_button": mt_wave_clicked and any(wave.startswith("manual-") for wave in wave_instances)
                    and "WORLD_WAVE_STATUS_ERROR" not in snapshot,
                "construction_during_combat": bool(re.search(
                    r"MT_ZERGLING_CONSTRUCTION_BUILD x=\d+ y=\d+ accepted=true", driver))
                    and "park patch synchronized" in snapshot,
                "simultaneous_zerglings": simultaneous_zerglings,
                "normal_scenario_continues": detailed["outcome"] is None,
                "manual_wave_screenshot": mt_wave_screenshot,
            }
            detailed["mt_zergling_playthrough"] = {
                "checks": checks, "wave_instances": sorted(set(wave_instances)),
                "construction_log": re.findall(r"MT_ZERGLING_CONSTRUCTION_.*", driver),
            }
            detailed["capture_complete"] = detailed["capture_complete"] and all(checks.values())
            (out / "verification.json").write_text(json.dumps(detailed, indent=2) + "\n")
        if args.marine_screen_probe:
            projected = re.findall(r"MARINE_SCREEN_PROBE rotation=(\d) zoom=(-?\d+) z=(\d+)"
                                   r" x=(-?\d+) y=(-?\d+) tool=([a-z0-9.-]+)", client_logs[0])
            selected = re.findall(r"RTS Bridge selected Marines=([^'\x1b\r\n]+)", client_logs[0])
            marines = {f"openbw:{number}" for number in range(1000, 1005)}
            checks = {"four_rotations_and_zooms": len(projected) == 4
                      and [int(row[0]) for row in projected] == [0, 1, 2, 3]
                      and [int(row[1]) for row in projected] == [0, 1, 2, -1],
                      "elevated_projection": len(projected) == 4 and all(int(row[2]) > 112 for row in projected),
                      "park_cursor_available": len(projected) == 4
                      and all(row[5] == "none" for row in projected),
                      "all_visible_marines_selected": len(selected) >= 4
                      and all(marines.issubset(set(row.split(","))) for row in selected[-4:])}
            detailed["marine_screen_probe"] = {"checks": checks, "projected": projected, "selected": selected[-4:]}
            detailed["capture_complete"] = detailed["capture_complete"] and all(checks.values())
            detailed["status"] = "passed" if detailed["capture_complete"] else "incomplete"
            (out / "verification.json").write_text(json.dumps(detailed, indent=2) + "\n")
        if args.ridge_probe:
            with (out / "ridge-check.log").open("w") as check_log:
                subprocess.run(["python3", str(ROOT / "scripts/verify-frontier-ridge.py"), str(out)],
                               cwd=ROOT, check=True, stdout=check_log)
            (out / "ridge-verification.json").write_text((out / "verification.json").read_text())
            (out / "verification.json").write_text(json.dumps(detailed, indent=2) + "\n")
        if args.ridge_probe or args.ridge_assault:
            mode = "marine" if args.ridge_probe else "zerg"
            with (out / "elevation-check.log").open("w") as check_log:
                subprocess.run(["python3", str(ROOT / "scripts/verify-frontier-elevation-capture.py"),
                                str(out), mode], cwd=ROOT, check=True, stdout=check_log)
        status = "passed" if detailed["capture_complete"] else "failed"
        if status == "failed":
            error = "Graphical capture or client synchronization is incomplete; see verification.json"
    except Exception as exc:
        error = str(exc)
        print(error, flush=True)
    finally:
        if recording and recorder:
            try:
                recorder.stop(False, error)
            except Exception as capture_error:
                error = f"{error}; {capture_error}" if error else str(capture_error)
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in reversed(processes):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        for log in logs:
            log.close()
        run.finalize(status, error)
        print(f"Artifact: {run.directory} status={status}", flush=True)
    if status != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
