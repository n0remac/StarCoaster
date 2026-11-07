#!/usr/bin/env python3
"""Select a stock park from browser New Game and use its native economy."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/home/pi/games/rct2/Scenarios/Bumbly Bazaar.SC6")


def ports(count):
    sockets = [socket.socket() for _ in range(count)]
    try:
        for item in sockets:
            item.bind(("127.0.0.1", 0))
        return [item.getsockname()[1] for item in sockets]
    finally:
        for item in sockets:
            item.close()


def stop(process):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--profile", type=Path,
                        help="reuse an earlier isolated E4 browser profile with provisioned assets")
    parser.add_argument("--wasm-port", type=int,
                        help="reuse the private origin of an earlier isolated E4 run")
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    if not runtime.is_relative_to((ROOT / "run-data").resolve()):
        parser.error("runtime must be under ignored run-data")
    profile = args.profile.resolve() if args.profile else runtime / "profile"
    if not profile.is_relative_to((ROOT / "run-data").resolve()):
        parser.error("profile must be under ignored run-data")
    for name in ("library", "artifacts", "xdg-config", "xdg-cache"):
        (runtime / name).mkdir(parents=True, exist_ok=True)
    local_bundle = (ROOT / "build/wasm-client").resolve()
    if not (local_bundle / "manifest.json").is_file():
        raise RuntimeError("built local economy WASM bundle is required")
    bundle_root = runtime / "local-bundle"
    bundle_root.mkdir(exist_ok=True)
    (bundle_root / "current").symlink_to(local_bundle, target_is_directory=True)
    # Chromium traps when its short-lived process sockets use the USB mount.
    # Licensed provisioned data, profile and captures stay on that mount.
    chromium_tmp = tempfile.TemporaryDirectory(prefix="economy-e4-chromium-", dir="/tmp")
    before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    native_ports = ports(4)
    if args.wasm_port:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", args.wasm_port))
        native_ports.append(args.wasm_port)
    else:
        native_ports.extend(ports(1))
    environment = os.environ.copy() | dict(zip(("OPENRCT2_PORT", "STARCOASTER_BRIDGE_PORT",
        "BRIDGE_OPENBW_PORT", "BRIDGE_CONTROLLER_PORT", "WASM_PORT"), map(str, native_ports)))
    environment.update({"RCT2_DATA_DIR": "/home/pi/games/rct2",
        "STARCRAFT_DATA_DIR": "/home/pi/games/starcraft",
        "BRIDGE_FRAME_MS": os.environ.get("BRIDGE_FRAME_MS", "15"),
        "BRIDGE_DISABLE_ASSAULT_AI": "1",
        "WASM_LISTEN_ADDRESS": f"127.0.0.1:{native_ports[4]}",
        "WASM_DEPLOY_DIR": str(bundle_root),
        "WASM_PRIVATE_RCT2": "1", "TMPDIR": chromium_tmp.name,
        "XDG_CONFIG_HOME": str(runtime / "xdg-config"),
        "XDG_CACHE_HOME": str(runtime / "xdg-cache"),
        "CHROME_CONFIG_HOME": str(runtime / "xdg-config/chromium")})
    browser_env = environment | {"WASM_NORMAL_HANDOFF": "1",
        "WASM_ECONOMY_E4_PROBE": "1", "WASM_LIVE_URL": f"http://127.0.0.1:{native_ports[4]}/",
        "WASM_LIVE_PROFILE": str(profile),
        "WASM_PERF_ARTIFACTS": str(runtime / "artifacts"),
        "WASM_LIVE_BOOT_TIMEOUT_MS": "600000",
        "WASM_LIVE_CAMERA_TIMEOUT_MS": os.environ.get("WASM_LIVE_CAMERA_TIMEOUT_MS", "180000"),
        "WASM_LIVE_DURATION_MS": os.environ.get("WASM_LIVE_DURATION_MS", "30000"),
        "WASM_LIVE_RECORD": "0",
        "WASM_LIVE_SCREENCAST": "0"}
    supervisor = browser = None
    with (runtime / "supervisor.log").open("w") as supervisor_log, \
            (runtime / "browser.log").open("w") as browser_log:
        try:
            supervisor = subprocess.Popen(["python3", "scripts/park_session_supervisor.py",
                "--parks", str(runtime / "library"), "--runtime", str(runtime / "supervisor")],
                cwd=ROOT, env=environment, stdout=supervisor_log,
                stderr=subprocess.STDOUT, start_new_session=True)
            # The first private launch inventories licensed RCT2 files before
            # opening the HTTP listener. Later launches reuse stat-qualified
            # digests; allow the initial USB scan to complete on a busy Pi.
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                if supervisor.poll() is not None:
                    raise RuntimeError("supervisor exited before browser server; see supervisor.log")
                try:
                    with urlopen(browser_env["WASM_LIVE_URL"], timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                time.sleep(.5)
            else:
                raise TimeoutError("private WASM server unavailable")
            print("PRIVATE_BROWSER_READY", browser_env["WASM_LIVE_URL"], flush=True)
            browser = subprocess.Popen(["node", "browser/live-test.mjs"], cwd=ROOT,
                env=browser_env, stdout=browser_log, stderr=subprocess.STDOUT,
                start_new_session=True)
            deadline = time.monotonic() + 900
            last_notice = 0
            while browser.poll() is None and time.monotonic() < deadline:
                if supervisor.poll() is not None:
                    raise RuntimeError("supervisor exited during browser handoff")
                elapsed = int(900 - (deadline - time.monotonic()))
                if elapsed // 30 > last_notice:
                    last_notice = elapsed // 30
                    print("BROWSER_ELAPSED", elapsed, flush=True)
                time.sleep(1)
            if browser.poll() is None:
                raise TimeoutError("browser normal handoff exceeded 900 seconds")
            if browser.returncode != 0:
                raise RuntimeError(f"browser probe exited {browser.returncode}; see browser.log")
            artifact = json.loads((runtime / "artifacts/runtime.json").read_text())
            if artifact["outcome"] != "passed" or not artifact["metrics"].get("handoffGeneration"):
                raise AssertionError("browser did not complete normal New Game handoff")
            generation = artifact["metrics"]["handoffGeneration"]
            session_log = runtime / "supervisor/sessions" / generation / "session.log"
            host = session_log.read_text(errors="replace")
            lines = (runtime / "browser.log").read_text(errors="replace")
            balances = [int(value) for value in re.findall(
                r"player resources owner=1 minerals=(\d+) gas=0", host)]
            checks = {
                "native_bootstrap": "finite economy bootstrap ready" in host,
                "paired_sites": len(re.findall(r"resource site=.* publisher=\d+ controller=\d+", host)) >= 7,
                "browser_train": "ECONOMY_E4_TRAINED workers=5" in lines,
                "browser_gather": "ECONOMY_E4_GATHERING worker=" in lines,
                "native_train_debit_and_delivery": 50 in balances and 0 in balances and
                    any(value > 0 for value in balances[balances.index(0) + 1:]),
                "native_gather_order": "verb=unit.gather accepted=1" in host,
                "source_unchanged": hashlib.sha256(SOURCE.read_bytes()).hexdigest() == before,
            }
            report = {"generation": generation, "checks": checks, "balances": balances,
                "source_sha256": before,
                "wasm_sha256": json.loads((local_bundle / "manifest.json").read_text())["artifacts"]["openrct2.wasm"],
                "session_log": str(session_log),
                "browser_log": str(runtime / "browser.log"),
                "browser_runtime": str(runtime / "artifacts/runtime.json")}
            (runtime / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2), flush=True)
            if not all(checks.values()):
                raise AssertionError("normal New Game economy criteria failed")
        finally:
            stop(browser)
            stop(supervisor)
            chromium_tmp.cleanup()


if __name__ == "__main__":
    main()
