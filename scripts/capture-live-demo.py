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
from artifact_runs import ArtifactRun
from squad_verification import animation_region_hashes, compare_clients, local_purple_counts, parse_applied, parse_projected, parse_combat_applied, write_summary
from park_assault_artifacts import draw_diagnostics
from park_assault_verification import analyze as analyze_park_assault


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


def capture_ride_siege(args: argparse.Namespace, video_config: VideoConfig | None) -> int:
    """Start from a clean park; start OpenBW only after both clients and video are ready."""
    global OUT
    park = Path(os.environ.get("DEMO_PARK", ROOT / "run-data/ride-siege-generator/save/bridge-ride-siege.park"))
    if not park.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts/create-render-test-park.py"),
                        "--scenario", "ride-siege"], cwd=ROOT, check=True)
    default_out = ROOT / "run-data/visual-demo"
    chosen_output = OUT if "DEMO_OUTPUT_DIR" in os.environ or OUT != default_out else None
    artifact_run = ArtifactRun("live-capture", "Live ride siege: Frontier Carousel",
                               chosen_output, config=vars(args) | {"park": str(park),
                                                                    "simulation": "OpenBW weapon damage",
                                                                    "demolition": "OpenRCT2 ridedemolish"})
    OUT = artifact_run.output
    env = os.environ.copy() | {"RCT2_DATA_DIR": str(RCT2_DATA),
                               "STARCRAFT_DATA_DIR": str(SC_DATA),
                               "SDL_AUDIODRIVER": "dummy", "LIBGL_ALWAYS_SOFTWARE": "1",
                               "BRIDGE_SCENARIO": "ride_siege", "BRIDGE_SIEGE_START_FRAME": "96"}
    (OUT / "scenario-config.json").write_text(json.dumps({
        "scenario": "ride-siege", "park": str(park), "target": "carousel-1",
        "proxy": "Terran_Missile_Turret", "zerglings": 8,
        "bw_to_park_offset": {"x": -128, "y": -96}, "attack_start_bw_frame": 96,
    }, indent=2) + "\n")
    running = []
    recorder = VideoRecorder(video_config, OUT) if video_config else None
    recording_started = False
    error_text = None
    status = "failed"
    def take_stage(stage: str) -> None:
        for label, display in (("client-a", ":91"), ("client-b", ":92")):
            filename = f"{label}-{stage}.png"
            subprocess.run(["scrot", "-z", "-o", str(OUT / filename)], check=True,
                           env=env | {"DISPLAY": display})
            if recorder:
                recorder.event("screenshot", client=label, filename=filename, stage=stage)
            print(f"Captured {OUT / filename}", flush=True)
    try:
        for label, display in (("display-a", ":91"), ("display-b", ":92")):
            running.append(start(label, ["Xvfb", display, "-screen", "0", "1280x800x24", "-nolisten", "tcp"], env))
        time.sleep(1)
        running.append(start("server", [str(ROOT / "scripts/run-openrct2-host.sh"), str(park)], env))
        server = running[-1][0]
        wait_for("server", "RIDE_SIEGE_READY", server)
        clients = {}
        for label, display in (("client-a", ":91"), ("client-b", ":92")):
            client_env = env | {"DISPLAY": display}
            plugin_dir = OUT / label / "plugin"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            camera = (ROOT / "scripts/demo-camera.js").read_text().replace(
                "var siegeCamera = false;", "var siegeCamera = true;")
            if label == "client-b" and args.rotate_client_b:
                camera = camera.replace("var demoRotation = 0;", "var demoRotation = 1;")
            if label == "client-b" and args.cycle_rotations:
                camera = camera.replace("var cycleRotations = false;", "var cycleRotations = true;")
            (plugin_dir / "demo-camera.js").write_text(camera)
            command = [str(ROOT / "build/openrct2/openrct2"), "join", "127.0.0.1",
                       "--port=11753", f"--rct2-data-path={RCT2_DATA}",
                       f"--openrct2-data-path={OPENRCT2_DATA}",
                       f"--user-data-path={OUT / label}"]
            for attempt in range(3):
                process, output = start(label, command, client_env)
                try:
                    wait_for(label, "[Passthrough RTS Bridge] Started", process, 60)
                    wait_for(label, "RIDE_SIEGE_CLIENT_BEFORE", process, 60)
                except RuntimeError:
                    transfer_failed = "Decompression error!" in (OUT / f"{label}.log").read_text(errors="replace")
                    process.terminate(); process.wait(timeout=3); output.close()
                    if not transfer_failed or attempt == 2:
                        raise
                    (OUT / f"{label}.log").rename(OUT / f"{label}-transfer-failed-{attempt + 1}.log")
                else:
                    running.append((process, output))
                    clients[label] = process
                    break
        if recorder:
            recorder.start()
            recording_started = True
        running.append(start("bwapi", [str(ROOT / "scripts/run-bwapi.sh")], env))
        publisher = running[-1][0]
        wait_for("bwapi", "attack orders scheduled for BW frame 96", publisher)
        wait_for("server", "RTS Bridge connected to BWAPI publisher", server)
        for label in clients:
            wait_for(label, "RTS Bridge apply tick=", clients[label])
        take_stage("early")
        if recorder: recorder.event("siege_approach", approximate=True)
        wait_for("bwapi", "[siege] target-damage", publisher, 30)
        take_stage("later")
        if recorder: recorder.event("siege_damage", approximate=True)
        wait_for("server", "RIDE_SIEGE_DEMOLITION_SUCCEEDED", server, 30)
        for label in clients:
            wait_for(label, "RIDE_SIEGE_CLIENT_AFTER", clients[label], 20)
        if recorder: recorder.event("carousel_destroyed", approximate=True)
        time.sleep(1)
        take_stage("final")
        bwlog = (OUT / "bwapi.log").read_text(errors="replace")
        serverlog = (OUT / "server.log").read_text(errors="replace")
        initial = re.search(r"target-created id=(\d+) owner=(\d+) kind=Terran_Missile_Turret hp=(\d+)", bwlog)
        destroyed = re.search(r"target-destroyed id=(\d+) frame=(\d+)", bwlog)
        orders = re.findall(r"attack-order id=(\d+) target=(\d+) accepted=1", bwlog)
        damage = re.findall(r"target-damage id=(\d+) from=(\d+) to=(\d+) frame=(\d+)", bwlog)
        if not initial or not destroyed or int(initial[3]) != 200 or len({x[0] for x in orders}) != 8 or not damage:
            raise RuntimeError("OpenBW siege combat verification failed")
        if bwlog.count("[siege] target-destroyed id=") != 1 or serverlog.count("RIDE_SIEGE_DEMOLITION_SUCCEEDED") != 1:
            raise RuntimeError("target destruction or native demolition was not exactly once")
        client_results = {}
        for label in clients:
            log = (OUT / f"{label}.log").read_text(errors="replace")
            before = re.search(r"RIDE_SIEGE_CLIENT_BEFORE (\{[^}]+\})", log)
            after = re.search(r"RIDE_SIEGE_CLIENT_AFTER (\{[^}]+\})", log)
            if not before or not after:
                raise RuntimeError(f"{label} did not report both park states")
            before_state, after_state = json.loads(before[1]), json.loads(after[1])
            if (before_state["tracks"], after_state["tracks"]) != (9, 0) or \
               before_state["rides"] != after_state["rides"] + 1 or \
               not before_state["tree"] or not after_state["tree"] or \
               before_state["otherRideIds"] != after_state["otherRideIds"] or \
               before_state["scenery"] != after_state["scenery"]:
                raise RuntimeError(f"{label} park state changed unexpectedly")
            client_results[label] = {"before": before_state, "after": after_state,
                                     "applied_snapshots": log.count("RTS Bridge apply tick=")}
            if client_results[label]["applied_snapshots"] < 10:
                raise RuntimeError(f"{label} received too few Zergling snapshots")
        report = {"status": "passed", "scenario": "ride-siege", "live_openrct2": True,
                  "target": {"id": "carousel-1", "proxy_unit_id": initial[1],
                             "owner": int(initial[2]), "initial_hp": int(initial[3]),
                             "damage_events": len(damage), "destroyed_bw_frame": int(destroyed[2])},
                  "zergling_ids": sorted({int(x[0]) for x in orders}),
                  "demolition": {"ride_id": 100, "action": "ridedemolish", "success": True},
                  "clients": client_results}
        (OUT / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)
        status = "passed"
        return 0
    except BaseException as error:
        status = "interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "failed"
        error_text = str(error)
        (OUT / "verification.json").write_text(json.dumps({"status": status, "error": error_text}, indent=2) + "\n")
        raise
    finally:
        recorder_failure = None
        try:
            if recording_started:
                recorder.stop(test_success=status == "passed", test_error=error_text)
        except BaseException as error:
            recorder_failure = error
            status = "failed"
            error_text = (error_text + "; " if error_text else "") + f"recording: {error}"
            (OUT / "verification.json").write_text(json.dumps({"status": status, "error": error_text}, indent=2) + "\n")
        finally:
            for process, _ in reversed(running):
                if process.poll() is None: process.terminate()
            for process, output in reversed(running):
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
                output.close()
            artifact_run.finalize(status, error_text)
        if recorder_failure is not None:
            raise recorder_failure


def capture_frontier_defense(args: argparse.Namespace, video_config: VideoConfig | None) -> int:
    """Record one real park server, two OpenBW faction controllers and two graphical clients."""
    global OUT
    subprocess.run([sys.executable, str(ROOT / "scripts/create-ride-siege-map.py"),
                    "--scenario", "frontier-defense", "--output",
                    str(ROOT / "run-data/frontier-defense-map/frontier-defense.scm")], cwd=ROOT, check=True)
    park = Path(os.environ.get("DEMO_PARK", ROOT / "run-data/frontier-defense-generator/save/bridge-frontier-defense.park"))
    if not park.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts/create-render-test-park.py"),
                        "--scenario", "frontier-defense"], cwd=ROOT, check=True)
    default_out = ROOT / "run-data/visual-demo"
    chosen_output = OUT if "DEMO_OUTPUT_DIR" in os.environ or OUT != default_out else None
    artifact_run = ArtifactRun("live-capture", "Live Frontier defense: Marines and Zerglings",
                               chosen_output, config=vars(args) | {"park": str(park),
                                                                    "simulation": "two synchronized OpenBW BWAPI players"})
    OUT = artifact_run.output
    env = os.environ.copy() | {"RCT2_DATA_DIR": str(RCT2_DATA), "STARCRAFT_DATA_DIR": str(SC_DATA),
                               "SDL_AUDIODRIVER": "dummy", "LIBGL_ALWAYS_SOFTWARE": "1",
                               "BRIDGE_SCENARIO": "frontier_defense"}
    (OUT / "scenario-config.json").write_text(json.dumps({
        "scenario": "frontier-defense", "park": str(park), "map": "frontier-defense.scm",
        "marines": 4, "zerglings": 8, "carousel_proxy": "Terran_Missile_Turret",
        "openbw_transport": "LOCAL", "bw_to_park_offset": {"x": -128, "y": -96}
    }, indent=2) + "\n")
    running = []
    recorder = VideoRecorder(video_config, OUT) if video_config else None
    recording_started = False
    status = "failed"
    error_text = None

    def shot(stage: str) -> None:
        for label, display in (("client-a", ":91"), ("client-b", ":92")):
            filename = f"{label}-{stage}.png"
            subprocess.run(["scrot", "-z", "-o", str(OUT / filename)], check=True,
                           env=env | {"DISPLAY": display})
            if recorder: recorder.event("screenshot", client=label, filename=filename, stage=stage)

    try:
        for label, display in (("display-a", ":91"), ("display-b", ":92")):
            running.append(start(label, ["Xvfb", display, "-screen", "0", "1280x800x24", "-nolisten", "tcp"], env))
        time.sleep(1)
        running.append(start("server", [str(ROOT / "scripts/run-openrct2-host.sh"), str(park)], env))
        server = running[-1][0]
        wait_for("server", "RIDE_SIEGE_READY", server)
        clients = {}
        for label, display in (("client-a", ":91"), ("client-b", ":92")):
            client_env = env | {"DISPLAY": display}
            plugin_dir = OUT / label / "plugin"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            camera = (ROOT / "scripts/demo-camera.js").read_text().replace(
                "var siegeCamera = false;", "var siegeCamera = true;")
            if label == "client-b" and args.rotate_client_b:
                camera = camera.replace("var demoRotation = 0;", "var demoRotation = 1;")
            if label == "client-b" and args.cycle_rotations:
                camera = camera.replace("var cycleRotations = false;", "var cycleRotations = true;")
            (plugin_dir / "demo-camera.js").write_text(camera)
            if label == "client-a":
                (plugin_dir / "frontier-command-probe.js").write_text(
                    (ROOT / "scripts/frontier-command-probe.js").read_text())
            command = [str(ROOT / "build/openrct2/openrct2"), "join", "127.0.0.1",
                       "--port=11753", f"--rct2-data-path={RCT2_DATA}",
                       f"--openrct2-data-path={OPENRCT2_DATA}", f"--user-data-path={OUT / label}"]
            for attempt in range(3):
                process, output = start(label, command, client_env)
                try:
                    wait_for(label, "[Passthrough RTS Bridge] Started", process, 60)
                    wait_for(label, "RIDE_SIEGE_CLIENT_BEFORE", process, 60)
                except RuntimeError:
                    transfer_failed = "Decompression error!" in (OUT / f"{label}.log").read_text(errors="replace")
                    process.terminate(); process.wait(timeout=3); output.close()
                    if not transfer_failed or attempt == 2: raise
                    (OUT / f"{label}.log").rename(OUT / f"{label}-transfer-failed-{attempt + 1}.log")
                else:
                    running.append((process, output)); clients[label] = process; break
        if recorder:
            recorder.start(); recording_started = True
        local_socket = str(OUT / "openbw-local.socket")
        for side, port in (("zerg", 39999), ("terran", 40000)):
            faction_env = env | {"BRIDGE_BWAPI_MENU": "MULTI_PLAYER", "BRIDGE_BWAPI_RACE": side.capitalize(),
                                 "BRIDGE_BWAPI_SLOT": "0" if side == "zerg" else "1",
                                 "BRIDGE_BWAPI_RUNTIME_DIR": str(OUT / "openbw" / side),
                                 "OPENBW_LAN_MODE": "LOCAL", "OPENBW_LOCAL_PATH": local_socket,
                                 "BRIDGE_PUBLISH_PORT": str(port)}
            running.append(start(side, [str(ROOT / "scripts/run-bwapi.sh")], faction_env))
        wait_for("zerg", "[frontier] spawned marines=4 zerglings=8", running[-2][0], 30)
        wait_for("server", "RTS Bridge connected to BWAPI publisher", server, 20)
        for label in clients: wait_for(label, "RTS Bridge apply tick=", clients[label], 20)
        shot("initial")
        wait_for("server", "RTS Bridge connected to Terran BWAPI controller", server, 10)
        # Exercise the actual viewport tool, including OpenRCT2's right mouse path.
        # Marine 1000's fixture foot position projects to (384, 336) on client A.
        mouse_env = env | {"DISPLAY": ":91"}
        subprocess.run(["xdotool", "mousemove", "--sync", "384", "336", "click", "1"],
                       env=mouse_env, check=True)
        wait_for("client-a", "RTS Bridge selected Marines=openbw:1000", clients["client-a"], 3)
        subprocess.run(["xdotool", "mousemove", "--sync", "250", "300", "click", "3"],
                       env=mouse_env, check=True)
        wait_for("client-a", "unit=openbw:1000 accepted=true reason=ok", clients["client-a"], 5)
        wait_for("client-a", "FRONTIER_COMMAND_MOVED", clients["client-a"], 15)
        wait_for("client-a", "accepted=true reason=ok", clients["client-a"], 15)
        wait_for("client-a", "FRONTIER_ATTACK_QUERY accepted=true", clients["client-a"], 10)
        wait_for("client-a", "command request=888", clients["client-a"], 10)
        wait_for("zerg", "kind=terran_marine", running[-2][0], 15)
        wait_for("zerg", "[battle] attack-frame", running[-2][0], 20)
        shot("firing")
        wait_for("zerg", "[battle] destroyed", running[-2][0], 20)
        shot("death")
        wait_for("zerg", "[frontier] target-damage", running[-2][0], 35)
        shot("damage")
        wait_for("server", "RIDE_SIEGE_DEMOLITION_SUCCEEDED", server, 40)
        for label in clients: wait_for(label, "RIDE_SIEGE_CLIENT_AFTER", clients[label], 20)
        time.sleep(2)
        shot("final")
        zerg_log = (OUT / "zerg.log").read_text(errors="replace")
        terran_log = (OUT / "terran.log").read_text(errors="replace")
        server_log = (OUT / "server.log").read_text(errors="replace")
        if not re.search(r"\[battle\] attack-frame .*kind=terran_marine", zerg_log):
            raise RuntimeError("OpenBW produced no Marine attack frame")
        if not re.search(r"\[battle\] damage .*kind=zerg_zergling .*from=(\d+) to=(\d+)", zerg_log):
            raise RuntimeError("OpenBW produced no Zergling health loss")
        if "[battle] destroyed" not in zerg_log or "[frontier] target-destroyed" not in zerg_log:
            raise RuntimeError("OpenBW produced no unit death or carousel destruction")
        if server_log.count("RIDE_SIEGE_DEMOLITION_SUCCEEDED") != 1:
            raise RuntimeError("carousel was not demolished exactly once")
        digest = re.compile(r"\[frontier\] state-digest frame=(\d+) hash=([0-9a-f]+) units=(\d+)")
        zerg_digests = {int(f): (h, int(n)) for f, h, n in digest.findall(zerg_log)}
        terran_digests = {int(f): (h, int(n)) for f, h, n in digest.findall(terran_log)}
        common_frames = sorted(set(zerg_digests) & set(terran_digests))
        if len(common_frames) < 5 or any(zerg_digests[f] != terran_digests[f] for f in common_frames):
            raise RuntimeError("OpenBW faction endpoints disagreed on combat state")
        states = {name: parse_combat_applied((OUT / f"{name}.log").read_text(errors="replace"))
                  for name in ("server", "client-a", "client-b")}
        common = set.intersection(*(set(value) for value in states.values()))
        if len(common) < 10 or any(len({states[name][key] for name in states}) != 1 for key in common):
            raise RuntimeError("OpenRCT2 clients disagreed on authoritative combat state")
        initial = [key for key in common if len(states["server"][key]) == 12]
        deaths = [key for key in common if any(unit[4] == "death" for unit in states["server"][key])]
        if not initial or not deaths:
            raise RuntimeError("12 initial actors or native death animation was not observed on both clients")
        client_a_log = (OUT / "client-a.log").read_text(errors="replace")
        if "FRONTIER_COMMAND_QUERY accepted=true" not in client_a_log or "FRONTIER_COMMAND_MOVED" not in client_a_log:
            raise RuntimeError("OpenRCT2 client command was not executed in OpenBW")
        if "FRONTIER_ATTACK_QUERY accepted=true" not in client_a_log \
           or not re.search(r"command request=888 unit=openbw:[0-9]+ accepted=true reason=ok", client_a_log):
            raise RuntimeError("Terran BWAPI did not accept the player attack order")
        if "RTS Bridge selected Marines=openbw:1000" not in client_a_log \
           or "unit=openbw:1000 accepted=true reason=ok" not in client_a_log:
            raise RuntimeError("map selection or right-click Marine command failed")
        if not any(abs(unit[1] - 576) + abs(unit[2] - 392) >= 12
                   for key in common for unit in states["server"][key] if unit[0] == "openbw:1000"):
            raise RuntimeError("map-selected Marine did not move in OpenBW on both clients")
        report = {"status": "passed", "scenario": "frontier-defense", "live_openrct2": True,
                  "initial_units": 12, "marine_attack_frames": len(re.findall(r"\[battle\] attack-frame .*kind=terran_marine", zerg_log)),
                  "combat_deaths": zerg_log.count("[battle] destroyed"),
                  "carousel_damage_events": zerg_log.count("[frontier] target-damage"),
                  "carousel_demolitions": 1, "openbw_agreed_frames": len(common_frames),
                  "openrct2_common_snapshots": len(common), "native_death_snapshots": len(deaths),
                  "marine_command": "accepted and moved", "attack_command": "accepted by Terran BWAPI",
                  "map_command": "selected, accepted and moved",
                  "clients": list(clients)}
        (OUT / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)
        status = "passed"
        return 0
    except BaseException as error:
        error_text = str(error)
        (OUT / "verification.json").write_text(json.dumps({"status": "failed", "error": error_text}, indent=2) + "\n")
        raise
    finally:
        recorder_error = None
        try:
            if recording_started: recorder.stop(test_success=status == "passed", test_error=error_text)
        except BaseException as error:
            recorder_error = error
            status = "failed"
            error_text = (error_text + "; " if error_text else "") + f"recording: {error}"
            (OUT / "verification.json").write_text(json.dumps({"status": "failed", "error": error_text}, indent=2) + "\n")
        finally:
            for process, _ in reversed(running):
                if process.poll() is None: process.terminate()
            for process, output in reversed(running):
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
                output.close()
            artifact_run.finalize(status, error_text)
        if recorder_error is not None: raise recorder_error


def capture_park_assault(args: argparse.Namespace, video_config: VideoConfig) -> int:
    """Capture one 20-unit OpenBW assault on two real multiplayer clients."""
    global OUT
    for script in ("create-park-assault.py", "create-park-assault-map.py",
                   "export-park-assault-navigation.py"):
        subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT,
                       check=True, stdout=subprocess.DEVNULL)
    data = ROOT / "run-data/park-assault"
    park = data / "save/frontier-outpost.park"
    config = json.loads((data / "fixture.json").read_text())
    default_out = ROOT / "run-data/visual-demo"
    chosen_output = OUT if "DEMO_OUTPUT_DIR" in os.environ or OUT != default_out else None
    artifact_run = ArtifactRun("live-capture", "Frontier Outpost: 20 Zerglings, three rides",
                               chosen_output, config=vars(args) | {"park": str(park),
                                                                    "simulation": "one OpenBW game",
                                                                    "demolition": "three OpenRCT2 native actions"})
    OUT = artifact_run.output
    OUT.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/prepare-park-assault-plugin.py"),
                    "--output", str(data / "rts-bridge-configured.js")], cwd=ROOT,
                   check=True, stdout=subprocess.DEVNULL)
    env = os.environ.copy() | {"RCT2_DATA_DIR": str(RCT2_DATA),
                               "STARCRAFT_DATA_DIR": str(SC_DATA), "SDL_AUDIODRIVER": "dummy",
                               "LIBGL_ALWAYS_SOFTWARE": "1", "BRIDGE_SCENARIO": "park_assault",
                               "BRIDGE_FRAME_MS": "42", "BRIDGE_SERVER_DATA_DIR": str(OUT / "server-data"),
                               "BRIDGE_BWAPI_RUNTIME_DIR": str(OUT / "openbw")}
    scenario_config = json.loads((data / "scenario-config.json").read_text()) if (data / "scenario-config.json").is_file() else {}
    scenario_config.update({"park": str(park), "map": str(data / "map/park-assault.scm"),
                            "zerglings": 20, "proxy": "Terran_Barracks",
                            "navigation_grid": str(data / "navigation.grid"),
                            "bw_to_park_offset": config["transform"]})
    (OUT / "scenario-config.json").write_text(json.dumps(scenario_config, indent=2) + "\n")
    running = []
    recorder = VideoRecorder(video_config, OUT)
    recording_started = False
    status = "failed"
    error_text = None

    def shot(stage: str) -> None:
        for label, display in (("client-a", ":91"), ("client-b", ":92")):
            name = f"{label}-{stage}.png"
            subprocess.run(["scrot", "-z", "-o", str(OUT / name)], check=True,
                           env=env | {"DISPLAY": display})
            recorder.event("screenshot", client=label, filename=name, stage=stage)

    def client_state(label: str, kind: str) -> dict[str, dict]:
        log = (OUT / f"{label}.log").read_text(errors="replace")
        marker = "PARK_ASSAULT_CLIENT_" + kind + " "
        records = {}
        for line in log.splitlines():
            if marker in line:
                value, _ = json.JSONDecoder().raw_decode(line.split(marker, 1)[1])
                records[value["id"]] = value
        return records

    try:
        for label, display in (("display-a", ":91"), ("display-b", ":92")):
            running.append(start(label, ["Xvfb", display, "-screen", "0", "1280x800x24", "-nolisten", "tcp"], env))
        time.sleep(1)
        running.append(start("server", [str(ROOT / "scripts/run-openrct2-host.sh"), str(park)], env))
        server = running[-1][0]
        wait_for("server", "PARK_ASSAULT_READY", server, 40)
        clients = {}
        for label, display in (("client-a", ":91"), ("client-b", ":92")):
            client_env = env | {"DISPLAY": display}
            plugin_dir = OUT / label / "plugin"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            camera = (ROOT / "scripts/park-assault-camera.js").read_text()
            if label == "client-b":
                camera = camera.replace("var closeup = false;", "var closeup = true;")
            (plugin_dir / "park-assault-camera.js").write_text(camera)
            command = [str(ROOT / "build/openrct2/openrct2"), "join", "127.0.0.1",
                       "--port=11753", f"--rct2-data-path={RCT2_DATA}",
                       f"--openrct2-data-path={OPENRCT2_DATA}", f"--user-data-path={OUT / label}"]
            for attempt in range(3):
                process, output = start(label, command, client_env)
                try:
                    wait_for(label, "[Passthrough RTS Bridge] Started", process, 60)
                    wait_for(label, "PARK_ASSAULT_CAMERA role=", process, 60)
                    wait_for(label, "PARK_ASSAULT_CLIENT_BEFORE", process, 60)
                except RuntimeError:
                    transfer_failed = "Decompression error!" in (OUT / f"{label}.log").read_text(errors="replace")
                    process.terminate(); process.wait(timeout=3); output.close()
                    if not transfer_failed or attempt == 2:
                        raise
                    (OUT / f"{label}.log").rename(OUT / f"{label}-transfer-failed-{attempt + 1}.log")
                else:
                    running.append((process, output))
                    clients[label] = process
                    break
        for label in clients:
            if set(client_state(label, "BEFORE")) != {"carousel-1", "shop-1", "ride-2"}:
                raise RuntimeError(f"{label} did not confirm all three intact rides")
        recorder.start()
        recording_started = True
        recorder.event("intact_park_overview")
        shot("overview")
        time.sleep(2)
        bw_start_time = time.monotonic()
        running.append(start("bwapi", [str(ROOT / "scripts/run-bwapi.sh")], env))
        publisher = running[-1][0]
        wait_for("bwapi", "[park-assault] initialized zerglings=20", publisher, 30)
        wait_for("server", "RTS Bridge connected to BWAPI publisher", server, 20)
        for label in clients:
            wait_for(label, "RTS Bridge apply tick=", clients[label], 20)
        wait_for("bwapi", "[park-assault] move-order", publisher, 15)
        shot("approach")
        recorder.event("twenty_zerglings_approach")
        for target_id, stage in (("carousel-1", "carousel"), ("shop-1", "shop"),
                                 ("ride-2", "ferris")):
            wait_for("bwapi", f"[park-assault] target-damage id={target_id}", publisher, 45)
            shot(stage + "-attack")
            wait_for("server", f"PARK_ASSAULT_DEMOLITION_SUCCEEDED id={target_id}", server, 50)
            for label, client in clients.items():
                wait_for(label, f'PARK_ASSAULT_CLIENT_AFTER {{"id":"{target_id}"', client, 25)
            shot(stage + "-destroyed")
            recorder.event("native_demolition", target_id=target_id)
        combat_end_time = time.monotonic()
        time.sleep(2)
        shot("final")
        bw_log = (OUT / "bwapi.log").read_text(errors="replace")
        server_log = (OUT / "server.log").read_text(errors="replace")
        report = analyze_park_assault(bw_log, server_log, OUT)
        draw_diagnostics(OUT)
        for name in ("navigation-grid.json", "planned-paths.json"):
            (OUT / name).write_bytes((data / name).read_bytes())
        states = {name: parse_combat_applied((OUT / f"{name}.log").read_text(errors="replace"))
                  for name in ("server", "client-a", "client-b")}
        sequence_gaps = {}
        for name, value in states.items():
            sequences = sorted(seq for _session, seq in value)
            sequence_gaps[name] = sum(current - previous - 1 for previous, current
                                      in zip(sequences, sequences[1:]))
        last_destroy_frame = max((int(frame) for frame in re.findall(
            r"\[park-assault\] target-destroyed id=[a-z0-9-]+ proxy=\d+ frame=(\d+)", bw_log)), default=0)
        frame_rate_lower_bound = round(last_destroy_frame / max(0.001, combat_end_time - bw_start_time), 2)
        common = set.intersection(*(set(value) for value in states.values()))
        disagreements = [key for key in common if len({states[name][key] for name in states}) != 1]
        full = [key for key in common if len(states["server"][key]) == 20]
        if len(common) < 20 or disagreements or len(full) < 5:
            report["errors"].append("the two graphical clients did not agree on 20 native actors")
        if any(sequence_gaps.values()):
            report["errors"].append("one or more OpenRCT2 peers skipped bridge snapshot sequences")
        client_results = {}
        expected_ids = {target["id"]: target["ride_id"] for target in config["targets"]}
        for label in clients:
            before, after = client_state(label, "BEFORE"), client_state(label, "AFTER")
            if set(before) != set(expected_ids) or set(after) != set(expected_ids):
                report["errors"].append(f"{label} did not observe all three ride removals")
                continue
            for target_id, ride_id in expected_ids.items():
                if before[target_id]["ride_id"] != ride_id or after[target_id]["ride_id"] != ride_id \
                    or before[target_id]["tracks"] < 1 or after[target_id]["tracks"] != 0 \
                    or before[target_id]["scenery"] != after[target_id]["scenery"]:
                    report["errors"].append(f"{label} target or surviving scenery changed unexpectedly: {target_id}")
            client_results[label] = {"before": before, "after": after,
                                     "native_snapshots": len(states[label])}
            log = (OUT / f"{label}.log").read_text(errors="replace")
            if "desync" in log.lower() or "mismatch" in log.lower():
                report["errors"].append(f"{label} logged a multiplayer synchronization error")
        report.update({"live_openrct2": True, "graphical_clients": client_results,
                       "common_snapshots": len(common), "twenty_actor_snapshots": len(full),
                       "snapshot_disagreements": len(disagreements),
                       "snapshot_sequence_gaps": sequence_gaps,
                       "openbw_frame_rate_fps_lower_bound": frame_rate_lower_bound})
        report["status"] = "failed" if report["errors"] else "passed"
        (OUT / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        if report["status"] != "passed":
            raise RuntimeError("live park assault verification failed: " + "; ".join(report["errors"]))
        print(json.dumps(report, indent=2), flush=True)
        status = "passed"
        return 0
    except BaseException as error:
        error_text = str(error)
        if not (OUT / "verification.json").is_file():
            (OUT / "verification.json").write_text(json.dumps({"status": "failed", "scenario": "park-assault",
                                                              "error": error_text}, indent=2) + "\n")
        raise
    finally:
        recorder_error = None
        try:
            if recording_started:
                recorder.stop(test_success=status == "passed", test_error=error_text)
        except BaseException as error:
            recorder_error = error
            status = "failed"
            error_text = (error_text + "; " if error_text else "") + f"recording: {error}"
            (OUT / "verification.json").write_text(json.dumps({"status": "failed", "scenario": "park-assault",
                                                              "error": error_text}, indent=2) + "\n")
        finally:
            for process, _ in reversed(running):
                if process.poll() is None:
                    process.terminate()
            for process, output in reversed(running):
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
                output.close()
            artifact_run.finalize(status, error_text)
        if recorder_error is not None:
            raise recorder_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=65, help="live observation after both clients join")
    parser.add_argument("--rotate-client-b", action="store_true", help="give client B an independent camera rotation")
    parser.add_argument("--cycle-rotations", action="store_true", help="cycle client B through all four rotations")
    parser.add_argument("--verify-zergling", action="store_true", help="check actual screenshot pixels for local Zergling art")
    parser.add_argument("--verify-fallback", action="store_true", help="check CC0 scout pixels in the single-unit demo")
    parser.add_argument("--demo-units", type=int, choices=(1, 8), default=1)
    parser.add_argument("--scenario", choices=("patrol", "ride-siege", "frontier-defense", "park-assault"), default="patrol")
    parser.add_argument("--verify-destruction", action="store_true")
    parser.add_argument("--verify-combat", action="store_true")
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
    if args.verify_destruction and args.scenario not in ("ride-siege", "park-assault"):
        parser.error("--verify-destruction requires --scenario ride-siege or park-assault")
    if args.verify_combat and args.scenario != "frontier-defense":
        parser.error("--verify-combat requires --scenario frontier-defense")
    if args.scenario == "park-assault" and not args.record_video:
        parser.error("--scenario park-assault requires --record-video")
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
    if args.scenario == "ride-siege":
        return capture_ride_siege(args, video_config)
    if args.scenario == "frontier-defense":
        return capture_frontier_defense(args, video_config)
    if args.scenario == "park-assault":
        return capture_park_assault(args, video_config)
    global OUT
    default_out = ROOT / "run-data/visual-demo"
    chosen_output = OUT if "DEMO_OUTPUT_DIR" in os.environ or OUT != default_out else None
    artifact_run = ArtifactRun("live-capture", "Live OpenRCT2 graphical capture",
                               chosen_output, config=vars(args))
    OUT = artifact_run.output
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
    final_status = "failed"
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
        final_status = "passed"
        return 0
    except BaseException as error:
        test_error = f"{type(error).__name__}: {error}"
        final_status = "interrupted" if isinstance(error, KeyboardInterrupt) or "interrupted by SIGTERM" in str(error) else "failed"
        (OUT / "verification.json").write_text(json.dumps({"status": "failed", "error": test_error}, indent=2) + "\n")
        raise
    finally:
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        # Finalize MP4 atoms while both X displays still exist, including on test failure.
        prior_exception = sys.exc_info()[1]
        recorder_error = None
        try:
            if recording_started:
                recorder.stop(test_success=test_error is None, test_error=test_error)
        except BaseException as error:
            recorder_error = error
            final_status = "failed"
            test_error = (test_error + "; " if test_error else "") + f"recording: {error}"
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
            artifact_run.finalize(final_status, test_error)
        if recorder_error is not None and prior_exception is None:
            raise recorder_error


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
