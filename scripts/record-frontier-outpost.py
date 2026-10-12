#!/usr/bin/env python3
"""Record the normal Frontier Outpost launcher and two graphical clients."""

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

from artifact_runs import ArtifactRun


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
    args = parser.parse_args()
    if not 15 <= args.duration <= 300:
        parser.error("duration must be 15–300 seconds")
    rct2 = Path(os.environ.get("RCT2_DATA_DIR", "/home/pi/games/rct2"))
    starcraft = Path(os.environ.get("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft"))
    if not rct2.is_dir() or not starcraft.is_dir():
        parser.error("RCT2_DATA_DIR and STARCRAFT_DATA_DIR must point to installed game data")
    run = ArtifactRun("live-capture", "Frontier Outpost first playable",
                      config={"scenario": "frontier-outpost", "duration": args.duration,
                              "launcher": "scripts/run-frontier-outpost.sh", "input": "X11 mouse and keyboard"})
    out = run.output
    env = os.environ.copy() | {"RCT2_DATA_DIR": str(rct2), "STARCRAFT_DATA_DIR": str(starcraft),
                               "BRIDGE_LAUNCH_CLIENT": "0", "BRIDGE_SERVER_DATA_DIR": str(out / "server-data"),
                               "SDL_AUDIODRIVER": "dummy", "LIBGL_ALWAYS_SOFTWARE": "1",
                               "BRIDGE_FRAME_MS": os.environ.get("BRIDGE_FRAME_MS", "70")}
    processes = []
    logs = []

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
        for name, display in (("display-a", ":91"), ("display-b", ":92")):
            start(name, ["Xvfb", display, "-screen", "0", "1280x800x24", "-nolisten", "tcp"], env)
        time.sleep(1)
        session = start("server", [str(ROOT / "scripts/run-frontier-outpost.sh")], env)
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
        for name, display in (("client-a", ":91"), ("client-b", ":92")):
            data_dir = out / name
            (data_dir / "plugin").mkdir(parents=True, exist_ok=True)
            source = (ROOT / "openrct2-plugin/rts-bridge.js").read_text()
            (data_dir / "plugin/rts-bridge.js").write_text("var STARCOASTER_WORLD_BRIDGE = true;\n" + source)
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
        for display in (":91", ":92"):
            subprocess.run(["xdotool", "mousemove", "1144", "112", "click", "1"],
                           env=env | {"DISPLAY": display}, check=True)
        print(f"Recording {out}; X11 displays :91 and :92 are live", flush=True)
        subprocess.run(["scrot", "-z", "-o", str(out / "client-a-initial.png")],
                       env=env | {"DISPLAY": ":91"}, check=True)
        subprocess.run(["scrot", "-z", "-o", str(out / "client-b-initial.png")],
                       env=env | {"DISPLAY": ":92"}, check=True)
        video = start("video-capture", ["ffmpeg", "-nostdin", "-y", "-loglevel", "warning",
                       "-f", "x11grab", "-framerate", "10", "-video_size", "1280x800", "-i", ":91",
                       "-f", "x11grab", "-framerate", "10", "-video_size", "1280x800", "-i", ":92",
                       "-filter_complex", "[0:v][1:v]xstack=inputs=2:layout=0_0|w0_0[v]",
                       "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
                       "-t", str(args.duration), str(out / "combined.mp4")], env)
        video.wait(timeout=args.duration + 30)
        for name, display in (("client-a", ":91"), ("client-b", ":92")):
            subprocess.run(["scrot", "-z", "-o", str(out / f"{name}-final.png")],
                           env=env | {"DISPLAY": display}, check=True)
        snapshot = (out / "server.log").read_text(errors="replace")
        clients = [(out / f"client-{letter}.log").read_text(errors="replace") for letter in "ab"]
        report = {"status": "recorded", "scenario": "frontier-outpost",
                  "world_ready": "navigation=native" in snapshot and "WORLD_READY" in snapshot,
                  "outcome": "defeat" if "outcome=defeat" in snapshot else "victory" if "outcome=victory" in snapshot else None,
                  "demolitions": snapshot.count("WORLD_REMOVAL id="),
                  "client_snapshots": [text.count("RTS Bridge apply tick=") for text in clients],
                  "client_selection": "selected Marines=openbw:" in clients[0],
                  "accepted_marine_order": "accepted=true reason=ok" in clients[0],
                  "marine_attack_frames": clients[0].count(",attack,112,terran_marine,"),
                  "video": "combined.mp4", "input_method": "graphical X11 interface"}
        (out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        (out / "scenario-config.json").write_text((ROOT / "scenarios/frontier-outpost.json").read_text())
        # The artifact viewer validates video metadata before listing an MP4.
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=noprint_wrappers=1:nokey=1", str(out / "combined.mp4")],
                               capture_output=True, text=True, check=True)
        (out / "video-metadata.json").write_text(json.dumps({"filename": "combined.mp4",
                    "duration_seconds": float(probe.stdout.strip()), "outputs": [{"filename": "combined.mp4",
                    "duration_seconds": float(probe.stdout.strip())}]}, indent=2) + "\n")
        subprocess.run(["python3", str(ROOT / "scripts/verify-frontier-capture.py"), str(out)],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        detailed = json.loads((out / "verification.json").read_text())
        status = "passed" if detailed["demonstration_complete"] else "failed"
        if status == "failed":
            error = "Required gameplay demonstration evidence is incomplete; see verification.json"
    except Exception as exc:
        error = str(exc)
        print(error, flush=True)
    finally:
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


if __name__ == "__main__":
    main()
