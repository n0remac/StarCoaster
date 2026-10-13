#!/usr/bin/env python3
"""Capture the normal Frontier Outpost launcher with one or two graphical clients."""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time

from artifact_runs import ArtifactRun
from video_capture import VideoConfig, VideoRecorder, check_dependencies


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "build/openrct2-stage/usr/local/share/openrct2"


def wait_for(path, marker, process, seconds):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if marker in path.read_text(errors="replace"):
            return
        if process.poll() is not None:
            raise RuntimeError(f"process exited before {marker}: {path}")
        time.sleep(0.25)
    raise TimeoutError(f"missing {marker}: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=int, default=85)
    parser.add_argument("--video-layout", choices=("single", "combined", "separate"), default="combined")
    parser.add_argument("--video-fps", type=int, default=15)
    parser.add_argument("--video-width", type=int, default=960)
    parser.add_argument("--video-crf", type=int, default=30)
    parser.add_argument("--video-preset", default="ultrafast")
    parser.add_argument("--display-width", type=int, default=1280)
    parser.add_argument("--display-height", type=int, default=800)
    parser.add_argument("--graphics", choices=("software", "native"), default="software")
    parser.add_argument("--frame-ms", type=int, default=70)
    parser.add_argument("--no-video", action="store_true", help="capture screenshots and logs without FFmpeg")
    parser.add_argument("--cycle-rotations", action="store_true", help="save screenshots from all four park views")
    parser.add_argument("--ridge-probe", action="store_true", help="run the test-only cliff, slope and combat driver on client A")
    parser.add_argument("--ridge-assault", action="store_true", help="test native Zergling approach from below the saved ridge")
    args = parser.parse_args()
    if not 15 <= args.duration <= 300:
        parser.error("duration must be 15–300 seconds")
    if not 10 <= args.frame_ms <= 200:
        parser.error("frame pacing must be 10–200 ms")
    try:
        video_config = VideoConfig(args.video_layout, args.video_fps, args.video_width,
                                   args.video_crf, args.video_preset,
                                   args.display_width, args.display_height)
        if not args.no_video:
            check_dependencies()
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    rct2 = Path(os.environ.get("RCT2_DATA_DIR", "/home/pi/games/rct2"))
    starcraft = Path(os.environ.get("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft"))
    if not rct2.is_dir() or not starcraft.is_dir():
        parser.error("RCT2_DATA_DIR and STARCRAFT_DATA_DIR must point to installed game data")
    run = ArtifactRun("live-capture", "Frontier Outpost v0.3",
                      config={"scenario": "frontier-outpost", "duration": args.duration,
                              "launcher": "scripts/run-frontier-outpost.sh", "input": "X11 mouse and keyboard",
                              "video": None if args.no_video else video_config.__dict__,
                              "graphics": args.graphics, "frame_ms": args.frame_ms,
                              "ridge_probe": args.ridge_probe, "ridge_assault": args.ridge_assault})
    out = run.output
    env = os.environ.copy() | {"RCT2_DATA_DIR": str(rct2), "STARCRAFT_DATA_DIR": str(starcraft),
                               "BRIDGE_LAUNCH_CLIENT": "0", "BRIDGE_SERVER_DATA_DIR": str(out / "server-data"),
                               "SDL_AUDIODRIVER": "dummy", "BRIDGE_FRAME_MS": str(args.frame_ms)}
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
    try:
        for name, display in displays:
            start("display-" + name[-1], ["Xvfb", display, "-screen", "0",
                                           f"{args.display_width}x{args.display_height}x24", "-nolisten", "tcp"], env)
        time.sleep(1)
        if args.ridge_assault:
            scenario = json.loads((ROOT / "scenarios/frontier-outpost.json").read_text())
            scenario["starting_units"]["zerglings"] = [
                [x, y] for y in range(28, 34) for x in (26, 27)]
            test_scenario = out / "ridge-assault-scenario.json"
            test_scenario.write_text(json.dumps(scenario, indent=2) + "\n")
            test_map = out / "ridge-assault.scm"
            subprocess.run(["python3", str(ROOT / "scripts/create-world-base-map.py"),
                            "--scenario", str(test_scenario), "--output", str(test_map)],
                           cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
            env.update(BRIDGE_MAP_FILE=str(test_map), BRIDGE_SCENARIO_CONFIG=str(test_scenario),
                       BRIDGE_RULES_CONFIG=str(ROOT / "scenarios/frontier-outpost-mapping.json"))
            session_command = [str(ROOT / "scripts/run-world-session.sh"),
                               str(ROOT / "run-data/frontier-playable/save/frontier-outpost-playable.park")]
        else:
            session_command = [str(ROOT / "scripts/run-frontier-outpost.sh")]
        session = start("server", session_command, env)
        until = time.monotonic() + 25
        while time.monotonic() < until:
            try:
                with socket.create_connection(("127.0.0.1", 11753), timeout=0.2):
                    break
            except OSError:
                if session.poll() is not None:
                    raise RuntimeError("Frontier launcher exited before park hosting")
                time.sleep(0.2)
        else:
            raise TimeoutError("OpenRCT2 host did not open port 11753")
        clients = {}
        for name, display in displays:
            data_dir = out / name
            (data_dir / "plugin").mkdir(parents=True, exist_ok=True)
            source = (ROOT / "openrct2-plugin/rts-bridge.js").read_text()
            (data_dir / "plugin/rts-bridge.js").write_text("var STARCOASTER_WORLD_BRIDGE = true;\n" + source)
            if args.ridge_probe and name == "client-a":
                (data_dir / "plugin/frontier-ridge-probe.js").write_text(
                    (ROOT / "scripts/frontier-ridge-probe.js").read_text())
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
                    process.wait(timeout=5)
                    logs[-1].close()
                    (out / f"{name}.log").rename(out / f"{name}-transfer-failed-{attempt + 1}.log")
                    if not transfer_failed or attempt == 2:
                        raise
                else:
                    clients[name] = process
                    break
        wait_for(out / "server.log", "WORLD_READY", session, 45)
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
        seen_rotations = {name: set() for name, _ in displays}
        rotation_offsets = {name: len(re.findall(r"FRONTIER_CAMERA rotation=([0-3])",
                              (out / f"{name}.log").read_text(errors="replace")))
                            for name, _ in displays}
        until = time.monotonic() + args.duration
        while time.monotonic() < until:
            if recorder:
                recorder.check_alive()
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
        report = {"status": "recorded", "scenario": "frontier-outpost",
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
        (out / "scenario-config.json").write_text((ROOT / "scenarios/frontier-outpost.json").read_text())
        subprocess.run(["python3", str(ROOT / "scripts/verify-frontier-capture.py"), str(out)],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        detailed = json.loads((out / "verification.json").read_text())
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
