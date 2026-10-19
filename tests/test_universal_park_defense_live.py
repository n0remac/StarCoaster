#!/usr/bin/env python3
"""Live native verification of defense mode on an existing saved park."""
import json
import os
import hashlib
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("UNIVERSAL_DEFENSE_SOURCE",
                             ROOT / "run-data/frontier-playable/save/frontier-outpost-playable.park")).resolve()
ANCHOR = [int(value) for value in os.environ.get("UNIVERSAL_DEFENSE_ANCHOR", "44,56").split(",")]
if len(ANCHOR) != 2:
    raise SystemExit("UNIVERSAL_DEFENSE_ANCHOR must contain x,y")
BUILD = "--build" in sys.argv
MANUAL = "--manual" in sys.argv or BUILD
MIXED = "--wasm" in sys.argv
if MANUAL and MIXED:
    raise SystemExit("choose --manual or --wasm")
RUN = ROOT / "run-data/universal-park-defense-live" / ("construction" if BUILD else "manual" if MANUAL else "mixed" if MIXED else "automatic")
TEST_SOURCE = RUN / f"source-{int(time.time())}-{os.getpid()}.park"
SCENARIO_ID = "park-defense-" + hashlib.sha256(str(TEST_SOURCE).encode()).hexdigest()[:16]
JOURNAL = ROOT / "run-data/scenarios" / SCENARIO_ID / "spawn-queue.json.scenario.json"


def wait_for(predicate, seconds, description, processes):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        for process in processes:
            if process.poll() is not None:
                raise RuntimeError(f"{description}: process exited {process.returncode}")
        time.sleep(.25)
    raise TimeoutError(description)


def runtime():
    if not JOURNAL.is_file():
        return {}
    try:
        return json.loads(JOURNAL.read_text())
    except json.JSONDecodeError:
        return {}


def main():
    if not SOURCE.is_file():
        raise RuntimeError(f"missing source park: {SOURCE}")
    original_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    RUN.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, TEST_SOURCE)
    if hashlib.sha256(TEST_SOURCE.read_bytes()).hexdigest() != original_hash:
        raise AssertionError("working source copy differs from original park")
    client = RUN / "client"
    (client / "plugin").mkdir(parents=True, exist_ok=True)
    if not MIXED:
        (client / "plugin/universal-defense-probe.js").write_text(
            ("var UNIVERSAL_DEFENSE_VERIFY_MANUAL = true;\n" if MANUAL else "")
            + ("var UNIVERSAL_DEFENSE_VERIFY_BUILD = true;\n" if BUILD else "")
            + "var UNIVERSAL_DEFENSE_ANCHOR = " + json.dumps(ANCHOR) + ";\n"
            + (ROOT / "tests/universal-defense-probe.js").read_text())
    # The host distributes the production bridge plugin through multiplayer.
    report = {"status": "failed", "mode": "construction" if BUILD else "manual" if MANUAL else "mixed" if MIXED else "automatic",
              "source": str(SOURCE), "checks": {}, "artifacts": {
        "session_log": str(RUN / "session.log"), "client_log": str(RUN / "client.log"),
        "journal": str(JOURNAL)}}
    processes = []
    streams = []
    try:
        stream = (RUN / "session.log").open("w")
        streams.append(stream)
        env = os.environ.copy() | {"BRIDGE_LAUNCH_CLIENT": "0"}
        if MIXED:
            env.update({"BRIDGE_SERVE_WASM": "1", "WASM_LISTEN_ADDRESS": "127.0.0.1:49123",
                        "WASM_DEPLOY_DIR": str(ROOT / "run-data/universal-defense-deploy")})
        session = subprocess.Popen([str(ROOT / "scripts/project.sh"), "play", "--park", str(TEST_SOURCE)],
            cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(session)
        wait_for(lambda: "WORLD_READY" in (RUN / "session.log").read_text(errors="replace"),
                 120, "native park readiness", processes)
        report["checks"]["existing_park_ready"] = "passed"
        imported = re.search(r"WORLD_READY entities=(\d+)",
                             (RUN / "session.log").read_text(errors="replace"))
        if not imported or int(imported.group(1)) < 1:
            raise AssertionError("original park entities were not imported")
        if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != original_hash:
            raise AssertionError("source park changed during launch")
        report["checks"]["park_features_and_source_preserved"] = "passed"
        first = runtime()
        if first.get("defense_enabled") or first.get("waves"):
            raise AssertionError("Zerg waves started before the player enabled defense")
        report["checks"]["disabled_default"] = "passed"
        browser_env = env | {"WASM_LIVE_URL": "http://127.0.0.1:49123/",
                             "WASM_LIVE_PROFILE": str(ROOT / "run-data/wasm-defense-profile-fixed"),
                             "WASM_LIVE_CAMERA": "1", "WASM_DEFENSE_PROBE": "1",
                             "WASM_DEFENSE_CONFIGURE": "1", "WASM_DEFENSE_ANCHOR": ",".join(map(str, ANCHOR)),
                             "WASM_LIVE_RECORD": "0", "WASM_LIVE_DURATION_MS": "20000",
                             "WASM_CAPTURE_INTERVAL_MS": "10000"}
        if MIXED:
            stream = (RUN / "browser-first.log").open("w")
            streams.append(stream)
            browser = subprocess.Popen(["node", "browser/live-test.mjs"], cwd=ROOT,
                env=browser_env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(browser)
        stream = (RUN / "client.log").open("w")
        streams.append(stream)
        rct2 = os.environ.get("RCT2_DATA_DIR", str(Path.home() / "games/rct2"))
        executable = ROOT / "build/openrct2/openrct2-cli"
        joined = None
        def join_native():
            process = subprocess.Popen([str(executable), "join", "127.0.0.1", "--headless", "--port=11753",
                f"--rct2-data-path={rct2}",
                f"--openrct2-data-path={ROOT / 'build/openrct2-stage/usr/local/share/openrct2'}",
                f"--user-data-path={client}"], cwd=ROOT, env=env,
                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(process)
            return process
        if not MIXED:
            joined = join_native()
        configured = wait_for(lambda: runtime() if runtime().get("defense_enabled") else None,
                              600 if MIXED else 90, "authorized defense enable", processes)
        if configured.get("spawn_anchor") != ANCHOR or len(configured.get("fixed_spawn_zone", {}).get("tiles", [])) < 4:
            raise AssertionError("fixed spawn point was not accepted")
        if configured["next_automatic_frame"] - configured["last_frame"] > 2880:
            raise AssertionError("preparation deadline exceeds 120 seconds")
        report["checks"]["authorized_fixed_spawn_and_countdown"] = "passed"
        report["anchor"] = configured["spawn_anchor"]
        if MIXED:
            joined = join_native()
        origin = "manual" if MANUAL else "periodic"
        wave = wait_for(lambda: next((wave for wave in runtime().get("waves") or []
                                     if wave.get("origin") == origin), None),
                        100 if BUILD else 60 if MANUAL else 180, f"first {origin} wave", processes)
        if wave["sequence"] != 1 or wave.get("spawn_zone") != "selected":
            raise AssertionError(f"{origin} wave sequence or zone differs")
        if not MANUAL and wave["triggered_frame"] < configured["next_automatic_frame"]:
            raise AssertionError("automatic wave started before preparation deadline")
        if len(wave.get("units") or []) != 8 or any(unit["unit_type"] != "zerg_zergling"
                                                   for unit in wave["units"]):
            raise AssertionError("first wave composition differs")
        report["checks"][f"{origin}_wave_timing_zone_and_composition"] = "passed"
        ready = wait_for(lambda: next((item for item in runtime().get("waves") or []
                                      if item.get("id") == wave["id"] and
                                      sum(unit.get("state") == "ready" for unit in item.get("units") or []) == 8), None),
                         60, "native Zerg spawn completion", processes)
        zone = set(map(tuple, ready["fixed_zone"]["tiles"]))
        if any((attempt["x"] // 32, attempt["y"] // 32) not in zone
               for unit in ready["units"] for attempt in unit.get("attempts") or []):
            raise AssertionError("wave attempted a spawn outside the selected zone")
        report["checks"]["eight_native_zerglings_in_fixed_zone"] = "passed"
        report["wave_ids"] = [wave["id"]]
        if BUILD:
            log = (RUN / "session.log").read_text(errors="replace")
            if "UNIVERSAL_DEFENSE_BUILD id=" not in (RUN / "client.log").read_text(errors="replace"):
                raise AssertionError("Barracks was not constructed")
            trained = re.search(r"\[world-control\] train command=.*accepted=1 queue=1 "
                                r"minerals=(\d+) supply=(\d+)/(\d+) frame=(\d+) "
                                r"unit_type=terran_marine gas=(\d+)", log)
            if not trained:
                raise AssertionError("OpenBW did not accept Marine training")
            if "WORLD_BUILDING_RECEIVED id=openrct2:large_scenery:" not in log:
                raise AssertionError("native Barracks state was not synchronized")
            report["checks"]["barracks_construction_and_native_marine_training"] = "passed"
            report["native_training"] = {"minerals_after": int(trained.group(1)),
                                         "supply_used": int(trained.group(2)),
                                         "supply_total": int(trained.group(3)),
                                         "frame": int(trained.group(4)),
                                         "gas_after": int(trained.group(5))}
        if MIXED:
            wait_for(lambda: browser.poll() is not None, 480, "browser gameplay capture", [session, joined])
            if browser.returncode != 0:
                raise RuntimeError("first browser gameplay capture failed")
            browser_artifacts = ROOT / "build/wasm-live-test"
            first_report = json.loads((browser_artifacts / "runtime.json").read_text())
            if first_report.get("outcome") != "passed" or not any(
                "WASM_CAMERA_READY" in item.get("text", "") and "zerg_zergling" in item.get("text", "")
                for item in first_report.get("records", [])):
                raise AssertionError("browser did not render a native Zergling")
            shutil.copy2(browser_artifacts / "runtime.json", RUN / "browser-first.json")
            report["checks"]["wasm_native_zergling_and_multiplayer"] = "passed"
            report["artifacts"]["browser_first"] = str(RUN / "browser-first.json")
            report["artifacts"]["recording"] = [str(path) for path in browser_artifacts.glob("*.webm")]
            stream = (RUN / "browser-reconnect.log").open("w")
            streams.append(stream)
            reconnect = subprocess.Popen(["node", "browser/live-test.mjs"], cwd=ROOT,
                env=browser_env | {"WASM_LIVE_RECORD": "0", "WASM_LIVE_DURATION_MS": "10000"},
                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(reconnect)
            wait_for(lambda: reconnect.poll() is not None, 480, "browser reconnect", [session, joined])
            if reconnect.returncode != 0:
                raise RuntimeError("browser reconnect failed")
            reconnect_report = json.loads((browser_artifacts / "runtime.json").read_text())
            if reconnect_report.get("outcome") != "passed":
                raise AssertionError("browser reconnect did not recover gameplay")
            if [item["id"] for item in runtime().get("waves") or []] != [wave["id"]]:
                raise AssertionError("browser reconnect duplicated a wave")
            shutil.copy2(browser_artifacts / "runtime.json", RUN / "browser-reconnect.json")
            report["checks"]["browser_reconnect_no_duplicate_wave"] = "passed"
            report["artifacts"]["browser_reconnect"] = str(RUN / "browser-reconnect.json")
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in reversed(processes):
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        for stream in streams:
            stream.close()
        (RUN / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
