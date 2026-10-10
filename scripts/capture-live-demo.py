#!/usr/bin/env python3
"""Capture two real OpenRCT2 clients while the BWAPI Zergling is running."""

import os
import argparse
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from PIL import Image
from video_capture import VideoConfig, VideoRecorder, check_dependencies


ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("DEMO_OUTPUT_DIR", ROOT / "run-data/visual-demo"))
PARK = Path(os.environ.get("DEMO_PARK", ROOT / "upstream/openrct2/test/tests/testdata/parks/BigMapTest.sv6"))
OPENRCT2_DATA = ROOT / "build/openrct2-stage/usr/local/share/openrct2"
RCT2_DATA = Path(os.environ.get("RCT2_DATA_DIR", "/home/pi/games/rct2"))
SC_DATA = Path(os.environ.get("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft"))


def start(name: str, command: list[str], env: dict[str, str]) -> tuple[subprocess.Popen, object]:
    log = (OUT / f"{name}.log").open("w")
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    return process, log


def wait_for(name: str, phrase: str, process: subprocess.Popen, timeout: float = 40) -> None:
    path = OUT / f"{name}.log"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        contents = path.read_text(errors="replace")
        if phrase in contents:
            return
        if "Decompression error!" in contents:
            raise RuntimeError(f"{name} park transfer failed; see {path}")
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited; see {path}")
        time.sleep(0.2)
    raise RuntimeError(f"{name} did not report {phrase!r}; see {path}")


def detect_zergling(path: Path) -> tuple[int, tuple[int, int, int, int] | None]:
    """Find the Zergling's purple body pixels in the park portion of a capture."""
    with Image.open(path) as source:
        image = source.convert("RGB")
    points = []
    for y in range(image.height // 8, image.height * 13 // 16):
        for x in range(image.width // 8, image.width * 7 // 8):
            r, g, b = image.getpixel((x, y))
            if r >= 60 and b >= r + 35 and b >= g + 25:
                points.append((x, y))
    if not points:
        return 0, None
    box = (min(x for x, _ in points), min(y for _, y in points),
           max(x for x, _ in points), max(y for _, y in points))
    return len(points), box


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=65, help="live observation after both clients join")
    parser.add_argument("--rotate-client-b", action="store_true", help="give client B an independent camera rotation")
    parser.add_argument("--cycle-rotations", action="store_true", help="cycle client B through all four rotations")
    parser.add_argument("--verify-zergling", action="store_true", help="check actual screenshot pixels for local Zergling art")
    parser.add_argument("--publisher-restart", action="store_true", help="capture despawn and return after a publisher restart")
    parser.add_argument("--sample-animation", action="store_true", help="capture several frames 0.1 seconds apart")
    parser.add_argument("--record-video", action="store_true", help="record the graphical clients with FFmpeg")
    parser.add_argument("--video-layout", choices=("combined", "separate"), default="combined")
    parser.add_argument("--video-fps", type=int, default=10)
    parser.add_argument("--video-width", type=int, default=960, help="even output width per client")
    parser.add_argument("--video-crf", type=int, default=32)
    parser.add_argument("--video-preset", default="veryfast")
    args = parser.parse_args()
    if args.seconds < 8:
        parser.error("--seconds must be at least 8")
    if args.publisher_restart and args.seconds < 35:
        parser.error("--publisher-restart requires --seconds of at least 35")
    video_config = None
    if args.record_video:
        try:
            video_config = VideoConfig(args.video_layout, args.video_fps, args.video_width,
                                       args.video_crf, args.video_preset)
            check_dependencies()
        except (ValueError, RuntimeError) as error:
            parser.error(str(error))
    if not (RCT2_DATA / "Data/g1.dat").is_file():
        raise RuntimeError(f"Missing RCT2 graphics at {RCT2_DATA / 'Data/g1.dat'}")
    if not all((SC_DATA / f).is_file() for f in ("StarDat.mpq", "BrooDat.mpq", "Patch_rt.mpq")):
        raise RuntimeError(f"Missing StarCraft MPQs in {SC_DATA}")
    OUT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["RCT2_DATA_DIR"] = str(RCT2_DATA)
    env["STARCRAFT_DATA_DIR"] = str(SC_DATA)
    env["SDL_AUDIODRIVER"] = "dummy"
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    running: list[tuple[subprocess.Popen, object]] = []
    recorder = VideoRecorder(video_config, OUT) if video_config else None
    recording_started = False
    test_error = None
    previous_sigterm = None
    if recorder:
        def interrupted(_signum, _frame):
            raise RuntimeError("graphical capture interrupted by SIGTERM")
        previous_sigterm = signal.signal(signal.SIGTERM, interrupted)
    try:
        for label, display in (("display-a", ":91"), ("display-b", ":92")):
            running.append(start(label, ["Xvfb", display, "-screen", "0", "1280x800x24", "-nolisten", "tcp"], env))
        time.sleep(1)
        running.append(start("bwapi", [str(ROOT / "scripts/run-bwapi.sh")], env))
        publisher = running[-1][0]
        wait_for("bwapi", "registered unit id=", running[-1][0])
        running.append(start("server", [str(ROOT / "scripts/run-openrct2-host.sh"), str(PARK)], env))
        wait_for("server", "RTS Bridge connected to BWAPI publisher", running[-1][0])
        client_processes = {}
        for label, display in (("client-a", ":91"), ("client-b", ":92")):
            client_env = env | {"DISPLAY": display}
            plugin_dir = OUT / label / "plugin"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            camera = (ROOT / "scripts/demo-camera.js").read_text()
            if args.rotate_client_b and label == "client-b":
                camera = camera.replace("var demoRotation = 0;", "var demoRotation = 1;")
            if args.cycle_rotations and label == "client-b":
                camera = camera.replace("var cycleRotations = false;", "var cycleRotations = true;")
            (plugin_dir / "demo-camera.js").write_text(camera)
            command = [
                str(ROOT / "build/openrct2/openrct2"), "join", "127.0.0.1",
                "--port=11753", f"--rct2-data-path={RCT2_DATA}",
                f"--openrct2-data-path={OPENRCT2_DATA}",
                f"--user-data-path={OUT / label}",
            ]
            for attempt in range(3):
                process, output = start(label, command, client_env)
                try:
                    wait_for(label, "[Passthrough RTS Bridge] Started", process, 60)
                    wait_for(label, "RTS Bridge apply", process, 60)
                except RuntimeError:
                    transfer_failed = "Decompression error!" in (OUT / f"{label}.log").read_text(errors="replace")
                    process.terminate()
                    process.wait(timeout=3)
                    output.close()
                    if not transfer_failed or attempt == 2:
                        raise
                    failed = OUT / f"{label}-transfer-failed-{attempt + 1}.log"
                    (OUT / f"{label}.log").rename(failed)
                    print(f"{label} map transfer failed; retrying join (log: {failed})", flush=True)
                else:
                    running.append((process, output))
                    client_processes[label] = process
                    break
        print("Both graphical clients receiving live BWAPI snapshots", flush=True)
        if recorder:
            recorder.start()
            recording_started = True
            print(f"Recording {video_config.layout} video in {OUT}", flush=True)
        start_time = recorder.start_monotonic if recorder else time.monotonic()
        shot_times = [2, 5]
        if args.sample_animation:
            shot_times += [5.1, 5.2, 5.3, 5.4, 5.5]
        if args.cycle_rotations:
            shot_times += [8, 11, 14, 17, 20, 23]
        if args.publisher_restart:
            shot_times += [20, 23, 30]
        shot_times = sorted(set(t for t in shot_times if t < args.seconds) | {args.seconds})
        captured_rotations = set()
        captured_paths = {"client-a": [], "client-b": []}
        for shot_at in shot_times:
            if recorder:
                recorder.check_alive()
            if args.publisher_restart and shot_at == 20:
                time.sleep(max(0, start_time + 18 - time.monotonic()))
                publisher.terminate()
                publisher.wait(timeout=3)
                if recorder:
                    recorder.event("publisher_stopped")
                wait_for("server", "publisher disconnected; removed actor", running[3][0], 10)
                for label in ("client-a", "client-b"):
                    wait_for(label, "despawn", client_processes[label], 10)
                print("Publisher disconnected; both clients applied despawn", flush=True)
            if args.publisher_restart and shot_at == 23:
                time.sleep(max(0, start_time + 21 - time.monotonic()))
                running.append(start("bwapi-restart", [str(ROOT / "scripts/run-bwapi.sh")], env))
                if recorder:
                    recorder.event("publisher_restart_started")
                wait_for("bwapi-restart", "registered unit id=", running[-1][0], 15)
            if args.publisher_restart and shot_at == 30:
                deadline = time.monotonic() + 20
                while (OUT / "server.log").read_text(errors="replace").count("RTS Bridge session ") < 2:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Publisher did not reconnect with a new session")
                    time.sleep(0.2)
            suffix = ("early" if shot_at == 2 else "later" if shot_at == 5 else "final"
                      if shot_at == args.seconds else f"t{shot_at:g}") if not args.cycle_rotations and not args.sample_animation else f"t{shot_at:g}"
            time.sleep(max(0, start_time + shot_at - time.monotonic()))
            for label, display in (("client-a", ":91"), ("client-b", ":92")):
                filename = f"{label}-{suffix}.png"
                if args.cycle_rotations and label == "client-b":
                    camera_log = (OUT / "client-b.log").read_text(errors="replace")
                    rotations = re.findall(r"RTS Bridge demo camera (?:centred at world \(480,480\), )?rotation=(\d)", camera_log)
                    if rotations:
                        captured_rotations.add(rotations[-1])
                        filename = f"{label}-{suffix}-rot{rotations[-1]}.png"
                subprocess.run(["scrot", "-z", "-o", str(OUT / filename)],
                               check=True, env=env | {"DISPLAY": display})
                if recorder:
                    recorder.event("screenshot", client=label, filename=filename,
                                   scheduled_seconds=shot_at)
                captured_paths[label].append(OUT / filename)
                print(f"Captured {OUT / filename}", flush=True)
            if recorder:
                recorder.check_alive()
            if args.publisher_restart and shot_at == 20:
                for label in ("client-a", "client-b"):
                    screenshot = captured_paths[label][-1]
                    if detect_zergling(screenshot)[0] >= 20:
                        raise RuntimeError(f"{label} still visibly rendered the actor after despawn")
            if args.publisher_restart and shot_at == 30:
                for label in ("client-a", "client-b"):
                    screenshot = captured_paths[label][-1]
                    if detect_zergling(screenshot)[0] < 20:
                        raise RuntimeError(f"{label} did not visibly render the restarted actor")
        if args.cycle_rotations:
            camera_log = (OUT / "client-b.log").read_text(errors="replace")
            seen = set(re.findall(r"RTS Bridge demo camera (?:centred at world \(480,480\), )?rotation=(\d)", camera_log))
            print(f"client-b camera rotations observed: {sorted(seen)}", flush=True)
            if captured_rotations != {"0", "1", "2", "3"}:
                raise RuntimeError(f"screenshots missed camera rotations: {sorted({'0','1','2','3'} - captured_rotations)}")
        if args.verify_zergling:
            for label in ("client-a", "client-b"):
                results = [(path.name, *detect_zergling(path)) for path in captured_paths[label]]
                visible = [(name, count, box) for name, count, box in results
                           if count >= 20 and box and box[2] - box[0] <= 80 and box[3] - box[1] <= 80]
                print(f"{label}: Zergling pixels visible in {len(visible)}/{len(results)} captures", flush=True)
                if len(visible) < 2:
                    raise RuntimeError(f"Zergling was not visibly rendered on {label}; inspect screenshots")
                if label == "client-a" and len({box[:2] for _, _, box in visible}) < 2:
                    raise RuntimeError("Zergling did not visibly move in client A captures")
        if args.publisher_restart:
            server_log = (OUT / "server.log").read_text(errors="replace")
            if server_log.count("RTS Bridge session ") < 2:
                raise RuntimeError("Publisher restart did not create a new session")
            for label in ("client-a", "client-b"):
                if "despawn" not in (OUT / f"{label}.log").read_text(errors="replace"):
                    raise RuntimeError(f"{label} did not apply despawn")
        logs = [(OUT / f"client-{letter}.log").read_text(errors="replace") for letter in ("a", "b")]
        for letter, log in zip(("a", "b"), logs):
            count = log.count("RTS Bridge apply tick=")
            print(f"client-{letter}: {count} applied snapshots; desync={('mismatch' in log.lower())}", flush=True)
            if count < 10 or "mismatch" in log.lower():
                raise RuntimeError(f"client-{letter} failed the visual multiplayer check")
        state_pattern = re.compile(r"RTS Bridge apply tick=(\d+) seq=(\d+) id=(\S+) x=(\d+) y=(\d+) session=(\S+) motion=(\S+)")
        all_logs = [(OUT / f"{name}.log").read_text(errors="replace") for name in ("server", "client-a", "client-b")]
        states = [
            {(session, int(seq)): (int(tick), unit_id, int(x), int(y), motion)
             for tick, seq, unit_id, x, y, session, motion in state_pattern.findall(log)}
            for log in all_logs
        ]
        common = set(states[0]).intersection(states[1], states[2])
        mismatches = [seq for seq in common if len({state[seq] for state in states}) != 1]
        print(f"common snapshots={len(common)}; tick/identity/coordinate mismatches={len(mismatches)}", flush=True)
        if len(common) < 10 or mismatches:
            raise RuntimeError("server and graphical clients disagree on applied snapshots")
        return 0
    except BaseException as error:
        test_error = f"{type(error).__name__}: {error}"
        raise
    finally:
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        # Finalize MP4 atoms while both X displays still exist, including on test failure.
        try:
            if recording_started:
                recorder.stop(test_success=test_error is None, test_error=test_error)
        finally:
            for process, _ in reversed(running):
                if process.poll() is None:
                    process.terminate()
            for process, output in reversed(running):
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                output.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
