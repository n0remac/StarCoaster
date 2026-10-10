#!/usr/bin/env python3
"""Capture two real OpenRCT2 clients while the BWAPI Zergling is running."""

import os
import argparse
import hashlib
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from PIL import Image
from video_capture import VideoConfig, VideoRecorder, check_dependencies
from squad_verification import animation_region_hashes, compare_clients, local_purple_counts, parse_applied, parse_projected, write_summary


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


def wait_for_empty_snapshot(name: str, process: subprocess.Popen, timeout: float = 10,
                            minimum: int = 1) -> None:
    path = OUT / f"{name}.log"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if sum(not actors for actors in parse_applied(path.read_text(errors="replace")).values()) >= minimum:
            return
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited before squad despawn; see {path}")
        time.sleep(0.2)
    raise RuntimeError(f"{name} did not apply the full empty snapshot; see {path}")


def detect_actor(path: Path, fallback: bool = False) -> tuple[int, tuple[int, int, int, int] | None]:
    """Find the local Zergling purple or CC0 scout cyan in the park viewport."""
    with Image.open(path) as source:
        image = source.convert("RGB")
    points = []
    for y in range(image.height // 8, image.height * 13 // 16):
        for x in range(image.width // 8, image.width * 7 // 8):
            r, g, b = image.getpixel((x, y))
            visible = (r < 110 and g >= 130 and b >= 125 and abs(g - b) <= 45) if fallback else (
                r >= 60 and b >= r + 35 and b >= g + 25)
            if visible:
                points.append((x, y))
    if not points:
        return 0, None
    box = (min(x for x, _ in points), min(y for _, y in points),
           max(x for x, _ in points), max(y for _, y in points))
    return len(points), box


def detect_zergling(path: Path) -> tuple[int, tuple[int, int, int, int] | None]:
    return detect_actor(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=65, help="live observation after both clients join")
    parser.add_argument("--rotate-client-b", action="store_true", help="give client B an independent camera rotation")
    parser.add_argument("--cycle-rotations", action="store_true", help="cycle client B through all four rotations")
    parser.add_argument("--verify-zergling", action="store_true", help="check actual screenshot pixels for local Zergling art")
    parser.add_argument("--verify-fallback", action="store_true", help="check CC0 scout pixels in the single-unit demo")
    parser.add_argument("--demo-units", type=int, choices=(1, 8), default=1)
    parser.add_argument("--verify-units", action="store_true", help="compare complete eight-unit snapshots and projected screenshot regions")
    parser.add_argument("--verify-animation", action="store_true", help="sample the walking sequence in both clients")
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
    env["BRIDGE_DEMO_UNITS"] = str(args.demo_units)
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
        if args.sample_animation or args.verify_animation:
            shot_times += [5.1, 5.2, 5.3, 5.4, 5.5]
        if args.cycle_rotations:
            shot_times += [8, 11, 14, 17, 20, 23]
        if args.publisher_restart:
            shot_times += [20, 23, 30]
        if args.verify_units:
            shot_times += [1, 3, 4, 6, 7, 9, 10, 12, 13, 15, 16, 28, 32, 35, 38, 40,
                           42, 45, 48, 51, 54, 55, 57, 60]
        shot_times = sorted(set(t for t in shot_times if t < args.seconds) | {args.seconds})
        captured_rotations = set()
        captured_paths = {"client-a": [], "client-b": []}
        shot_states = {}
        for shot_at in shot_times:
            if recorder:
                recorder.check_alive()
            if args.publisher_restart and shot_at == 20:
                time.sleep(max(0, start_time + 18 - time.monotonic()))
                publisher.terminate()
                publisher.wait(timeout=3)
                if recorder:
                    recorder.event("publisher_stopped")
                wait_for("server", "publisher disconnected; removed actors", running[3][0], 10)
                for label in ("client-a", "client-b"):
                    wait_for_empty_snapshot(label, client_processes[label], 10)
                print("Publisher disconnected; both clients applied despawn", flush=True)
            if args.publisher_restart and shot_at == 23:
                time.sleep(max(0, start_time + 21 - time.monotonic()))
                running.append(start("bwapi-restart", [str(ROOT / "scripts/run-bwapi.sh")], env))
                publisher = running[-1][0]
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
                if args.verify_units or args.verify_animation:
                    current = parse_projected((OUT / f"{label}.log").read_text(errors="replace"))
                    shot_states[filename] = next(reversed(current.values()), {"center_z": 112, "actors": ()}) if current else {"center_z": 112, "actors": ()}
                print(f"Captured {OUT / filename}", flush=True)
            if recorder:
                recorder.check_alive()
            if args.publisher_restart and shot_at == 20 and args.demo_units == 1:
                for label in ("client-a", "client-b"):
                    screenshot = captured_paths[label][-1]
                    if detect_zergling(screenshot)[0] >= 20:
                        raise RuntimeError(f"{label} still visibly rendered the actor after despawn")
            if args.publisher_restart and shot_at == 30 and args.demo_units == 1:
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
        if args.verify_zergling or args.verify_fallback:
            for label in ("client-a", "client-b"):
                results = [(path.name, *detect_actor(path, args.verify_fallback)) for path in captured_paths[label]]
                visible = [(name, count, box) for name, count, box in results
                           if count >= 20 and box and box[2] - box[0] <= 80 and box[3] - box[1] <= 80]
                print(f"{label}: actor pixels visible in {len(visible)}/{len(results)} captures", flush=True)
                if len(visible) < 2:
                    raise RuntimeError(f"actor was not visibly rendered on {label}; inspect screenshots")
                if label == "client-a" and len({box[:2] for _, _, box in visible}) < 2:
                    raise RuntimeError("actor did not visibly move in client A captures")
        if publisher.poll() is None:
            publisher.terminate()
            publisher.wait(timeout=3)
            minimum_empty = 2 if args.publisher_restart else 1
            wait_for_empty_snapshot("server", running[3][0], 10, minimum_empty)
            for label in ("client-a", "client-b"):
                wait_for_empty_snapshot(label, client_processes[label], 10, minimum_empty)
        if args.publisher_restart:
            server_log = (OUT / "server.log").read_text(errors="replace")
            if server_log.count("RTS Bridge session ") < 2:
                raise RuntimeError("Publisher restart did not create a new session")
            for label in ("client-a", "client-b"):
                if not any(not actors for actors in parse_applied((OUT / f"{label}.log").read_text(errors="replace")).values()):
                    raise RuntimeError(f"{label} did not apply despawn")
        logs = [(OUT / f"client-{letter}.log").read_text(errors="replace") for letter in ("a", "b")]
        for letter, log in zip(("a", "b"), logs):
            count = log.count("RTS Bridge apply tick=")
            print(f"client-{letter}: {count} applied snapshots; desync={('mismatch' in log.lower())}", flush=True)
            if count < 10 or "mismatch" in log.lower():
                raise RuntimeError(f"client-{letter} failed the visual multiplayer check")
        named_logs = {name: (OUT / f"{name}.log").read_text(errors="replace")
                      for name in ("server", "client-a", "client-b")}
        summary = compare_clients(named_logs, 100 if args.verify_units and args.seconds >= 65 else 10)
        source_files = ("bridge-protocol/units.snapshot.v1.schema.json", "openbw-bwapi-module/src/BridgeAIModule.cpp",
                        "openrct2-plugin/rts-bridge.js", "openrct2-patches/0001-native-bridge.patch",
                        "scripts/prepare-starcraft-sprites.py", "scripts/install-bridge-sprites.py",
                        "scripts/capture-live-demo.py", "scripts/squad_verification.py")
        fingerprint = hashlib.sha256()
        for name in source_files:
            fingerprint.update(name.encode() + b"\0" + (ROOT / name).read_bytes())
        summary.update({"demo_units": args.demo_units, "scenario_seed": 0,
                        "commit_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                        "source_fingerprint_sha256": fingerprint.hexdigest(),
                        "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
                        "asset_source": os.environ.get("BRIDGE_SPRITE_SOURCE", "starcraft-local")})
        if args.verify_units:
            (OUT / "screenshot-states.json").write_text(json.dumps(shot_states, indent=2) + "\n")
            if len(summary["stable_ids"]) != 8 or summary["eight_unit_snapshots"] < 20:
                raise RuntimeError(f"eight stable IDs were not observed: {summary}")
            if args.publisher_restart and (summary["seven_unit_snapshots"] < 5 or summary["empty_snapshots"] < 2
                                           or len(summary["sessions"]) < 2):
                raise RuntimeError(f"squad death or session recovery was not observed: {summary}")
            pixel_summary = {}
            for label in ("client-a", "client-b"):
                for path in captured_paths[label]:
                    match = re.search(r"-rot([0-3])\.png$", path.name)
                    rotation = int(match.group(1)) if match else 0
                    if label == "client-b" and args.cycle_rotations and not match:
                        continue
                    state = shot_states.get(path.name, {"center_z": 112, "actors": ()})
                    actors = state["actors"]
                    if len(actors) == 8:
                        pixel_summary[path.name] = local_purple_counts(path, actors, rotation, state["center_z"])
            summary["projected_pixel_counts"] = pixel_summary
            summary["max_visible_in_one_capture"] = {}
            for label in ("client-a", "client-b"):
                captures = [counts for name, counts in pixel_summary.items() if name.startswith(label)]
                visible = {unit_id for counts in captures for unit_id, count in counts.items() if count >= 8}
                summary["max_visible_in_one_capture"][label] = max(
                    (sum(count >= 8 for count in counts.values()) for counts in captures), default=0)
                if len(visible) != 8:
                    raise RuntimeError(f"{label} projected pixels did not cover all eight IDs across captures: {sorted(visible)}")
        if args.verify_animation:
            manifest = json.loads((ROOT / "run-data/generated-assets/starcraft/zergling/manifest.json").read_text())
            walk_names = [f"walk{index}_east.png" for index in range(10)]
            source_dir = ROOT / "run-data/generated-assets/starcraft/zergling"
            if len({(source_dir / name).read_bytes() for name in walk_names}) < 4:
                raise RuntimeError("local GRP did not yield four distinct walk poses")
            evidence = {}
            for label in ("client-a", "client-b"):
                per_id = {}
                for path in captured_paths[label]:
                    if not re.search(r"-t5\.[1-5](?:-rot[0-3])?\.png$", path.name):
                        continue
                    state = shot_states.get(path.name, {"center_z": 112, "actors": ()})
                    actors = state["actors"]
                    match = re.search(r"-rot([0-3])\.png$", path.name)
                    rotation = int(match.group(1)) if match else 0
                    for unit_id, digest in animation_region_hashes(path, actors, rotation, state["center_z"]).items():
                        per_id.setdefault(unit_id, set()).add(digest)
                evidence[label] = {unit_id: len(hashes) for unit_id, hashes in per_id.items()}
                if max(evidence[label].values(), default=0) < 3:
                    raise RuntimeError(f"{label} did not show three changing walking regions")
            summary["animation_evidence"] = {"source_walk_poses": len(walk_names),
                                             "changing_regions": evidence,
                                             "ticks_per_frame": manifest["registry"]["alien_scout"]["walk"]["ticks_per_frame"]}
        write_summary(OUT / "verification.json", summary)
        print(f"common snapshots={summary['common_snapshots']}; authoritative mismatches=0", flush=True)
        return 0
    except BaseException as error:
        test_error = f"{type(error).__name__}: {error}"
        (OUT / "verification.json").write_text(json.dumps({"status": "failed", "error": test_error}, indent=2) + "\n")
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
