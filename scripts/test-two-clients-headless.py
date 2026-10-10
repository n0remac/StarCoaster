#!/usr/bin/env python3
"""Exercise real BWAPI snapshots through one OpenRCT2 host and two headless clients."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent.parent
PARK = ROOT / "upstream/openrct2/test/tests/testdata/parks/EverythingPark.park"
OPENRCT2_DATA = ROOT / "build/openrct2-stage/usr/local/share/openrct2"
OUTPUT = ROOT / "run-data/headless-multiplayer"
APPLIED = re.compile(r"RTS Bridge apply tick=(\d+) seq=(\d+) id=(\S+) x=(\d+) y=(\d+)")


def start(name: str, command: list[str], env: dict[str, str]) -> tuple[subprocess.Popen, object]:
    output = (OUTPUT / f"{name}.log").open("w")
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
    return process, output


def await_log(path: Path, fragment: str, process: subprocess.Popen, seconds: float = 15) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists() and fragment in path.read_text(errors="replace"):
            return
        if process.poll() is not None:
            raise RuntimeError(f"process exited before '{fragment}' appeared; see {path}")
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for '{fragment}'; see {path}")


def read_states(path: Path) -> dict[int, tuple[int, str, int, int]]:
    result = {}
    for line in path.read_text(errors="replace").splitlines():
        match = APPLIED.search(line)
        if match:
            tick, seq, unit, x, y = match.groups()
            result[int(seq)] = (int(tick), unit, int(x), int(y))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=65)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    if not os.environ.get("STARCRAFT_DATA_DIR"):
        parser.error("set STARCRAFT_DATA_DIR to the directory containing your own MPQs")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("RCT2_DATA_DIR", "/usr/share/openrct2")
    paths = {name: OUTPUT / f"{name}.log" for name in ("bwapi", "server", "client-a", "client-b")}
    processes = []
    outputs = []
    try:
        bwapi, output = start("bwapi", [str(ROOT / "scripts/run-bwapi.sh")], env)
        processes.append(bwapi)
        outputs.append(output)
        await_log(paths["bwapi"], "registered unit id=", bwapi)

        server, output = start("server", [str(ROOT / "scripts/run-openrct2-host.sh"), str(PARK)], env)
        processes.append(server)
        outputs.append(output)
        await_log(paths["server"], "RTS Bridge connected to BWAPI publisher", server)

        for name in ("client-a", "client-b"):
            command = [
                str(ROOT / "build/openrct2/openrct2-cli"), "join", "127.0.0.1", "--headless",
                "--port=11753", f"--openrct2-data-path={OPENRCT2_DATA}",
                f"--rct2-data-path={env['RCT2_DATA_DIR']}",
                f"--user-data-path={OUTPUT / name}",
            ]
            process, output = start(name, command, env)
            processes.append(process)
            outputs.append(output)
            await_log(paths[name], "[Passthrough RTS Bridge] Started", process)

        print(f"All processes started; observing synchronized actions for {args.seconds:g} seconds", flush=True)
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            for process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f"process {process.pid} exited during observation")
            time.sleep(min(0.5, max(0.01, deadline - time.monotonic())))
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return_code = 1
    else:
        return_code = 0
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(processes):
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for output in outputs:
            output.close()

    if return_code:
        print(f"Logs: {OUTPUT}")
        return return_code

    states = [read_states(paths[name]) for name in ("server", "client-a", "client-b")]
    common = set(states[0]).intersection(states[1], states[2])
    mismatches = [seq for seq in common if len({item[seq] for item in states}) != 1]
    for name, values in zip(("server", "client-a", "client-b"), states):
        print(f"{name}: {len(values)} applied snapshots")
    print(f"Common snapshots: {len(common)}; tick/identity/coordinate mismatches: {len(mismatches)}")
    print(f"Logs: {OUTPUT}")
    if len(common) < 10 or mismatches:
        print("FAIL: synchronized action evidence is insufficient", file=sys.stderr)
        return 1
    print("PASS: real BWAPI movement matched on server and both headless clients")
    return 0


if __name__ == "__main__":
    sys.exit(main())
