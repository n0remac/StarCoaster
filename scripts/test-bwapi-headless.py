#!/usr/bin/env python3
"""Run the real BWAPI movement smoke test and retain its local logs."""

import argparse
import os
from pathlib import Path
import re
import socket
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=20)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    if not os.environ.get("STARCRAFT_DATA_DIR"):
        parser.error("set STARCRAFT_DATA_DIR to the directory containing your own MPQs")

    port = int(os.environ.get("BRIDGE_PUBLISH_PORT", "39999"))
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            print(f"FAIL: port {port} is already serving a publisher", file=sys.stderr)
            return 1

    output_dir = ROOT / "run-data" / "headless-test"
    output_dir.mkdir(parents=True, exist_ok=True)
    launcher_log = output_dir / "bwapi.log"
    receiver_log = output_dir / "receiver.log"

    with launcher_log.open("w") as output:
        launcher = subprocess.Popen(
            [str(ROOT / "scripts" / "run-bwapi.sh")],
            cwd=ROOT,
            env=os.environ.copy(),
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            receiver = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "receive-snapshots.py"),
                 "--port", str(port), "--seconds", str(args.seconds)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=args.seconds + 3,
                check=False,
            )
            receiver_log.write_text(receiver.stdout + receiver.stderr)
        except subprocess.TimeoutExpired:
            receiver_log.write_text("FAIL: receiver timed out\n")
            receiver = None
        finally:
            if launcher.poll() is None:
                launcher.terminate()
            try:
                launcher.wait(timeout=3)
            except subprocess.TimeoutExpired:
                launcher.kill()
                launcher.wait()

    launcher_text = launcher_log.read_text()
    receiver_text = receiver_log.read_text()
    registered = re.search(r"\[bridge\] registered unit id=(\d+)", launcher_text)
    moved = registered and f"[bridge] Unit::move id={registered.group(1)}" in launcher_text
    passed = receiver is not None and receiver.returncode == 0 and bool(moved)
    print(receiver_text.rstrip())
    print(f"Launcher log: {launcher_log}")
    print(f"Receiver log: {receiver_log}")
    if passed:
        print(f"PASS: BWAPI registered unit {registered.group(1)}, accepted move, and published changing positions")
        return 0
    print("FAIL: BWAPI movement gate did not pass; inspect the logs above", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
