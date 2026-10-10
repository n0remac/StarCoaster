#!/usr/bin/env python3
"""Capture two real OpenRCT2 clients while the BWAPI Zergling is running."""

import os
import argparse
from pathlib import Path
import re
import re
import subprocess
import sys
import time


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
        if phrase in path.read_text(errors="replace"):
            return
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited; see {path}")
        time.sleep(0.2)
    raise RuntimeError(f"{name} did not report {phrase!r}; see {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=65, help="live observation after both clients join")
    parser.add_argument("--rotate-client-b", action="store_true", help="give client B an independent camera rotation")
    args = parser.parse_args()
    if args.seconds < 8:
        parser.error("--seconds must be at least 8")
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
    try:
        for label, display in (("display-a", ":91"), ("display-b", ":92")):
            running.append(start(label, ["Xvfb", display, "-screen", "0", "1280x800x24", "-nolisten", "tcp"], env))
        time.sleep(1)
        running.append(start("bwapi", [str(ROOT / "scripts/run-bwapi.sh")], env))
        wait_for("bwapi", "registered unit id=", running[-1][0])
        running.append(start("server", [str(ROOT / "scripts/run-openrct2-host.sh"), str(PARK)], env))
        wait_for("server", "RTS Bridge connected to BWAPI publisher", running[-1][0])
        for label, display in (("client-a", ":91"), ("client-b", ":92")):
            client_env = env | {"DISPLAY": display}
            plugin_dir = OUT / label / "plugin"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            camera = (ROOT / "scripts/demo-camera.js").read_text()
            if args.rotate_client_b and label == "client-b":
                camera = camera.replace("var demoRotation = 0;", "var demoRotation = 1;")
            (plugin_dir / "demo-camera.js").write_text(camera)
            command = [
                str(ROOT / "build/openrct2/openrct2"), "join", "127.0.0.1",
                "--port=11753", f"--rct2-data-path={RCT2_DATA}",
                f"--openrct2-data-path={OPENRCT2_DATA}",
                f"--user-data-path={OUT / label}",
            ]
            running.append(start(label, command, client_env))
            wait_for(label, "[Passthrough RTS Bridge] Started", running[-1][0], 60)
            wait_for(label, "RTS Bridge apply", running[-1][0], 60)
        print("Both graphical clients receiving live BWAPI snapshots", flush=True)
        start_time = time.monotonic()
        for shot_at, suffix in ((2, "early"), (5, "later"), (args.seconds, "final")):
            time.sleep(max(0, start_time + shot_at - time.monotonic()))
            for label, display in (("client-a", ":91"), ("client-b", ":92")):
                subprocess.run(["scrot", "-z", "-o", str(OUT / f"{label}-{suffix}.png")],
                               check=True, env=env | {"DISPLAY": display})
                print(f"Captured {OUT / f'{label}-{suffix}.png'}", flush=True)
        logs = [(OUT / f"client-{letter}.log").read_text(errors="replace") for letter in ("a", "b")]
        for letter, log in zip(("a", "b"), logs):
            count = log.count("RTS Bridge apply tick=")
            print(f"client-{letter}: {count} applied snapshots; desync={('mismatch' in log.lower())}", flush=True)
            if count < 10 or "mismatch" in log.lower():
                raise RuntimeError(f"client-{letter} failed the visual multiplayer check")
        state_pattern = re.compile(r"RTS Bridge apply tick=(\d+) seq=(\d+) id=(\S+) x=(\d+) y=(\d+)")
        all_logs = [(OUT / f"{name}.log").read_text(errors="replace") for name in ("server", "client-a", "client-b")]
        states = [
            {int(seq): (int(tick), unit_id, int(x), int(y))
             for tick, seq, unit_id, x, y in state_pattern.findall(log)}
            for log in all_logs
        ]
        common = set(states[0]).intersection(states[1], states[2])
        mismatches = [seq for seq in common if len({state[seq] for state in states}) != 1]
        print(f"common snapshots={len(common)}; tick/identity/coordinate mismatches={len(mismatches)}", flush=True)
        if len(common) < 10 or mismatches:
            raise RuntimeError("server and graphical clients disagree on applied snapshots")
        return 0
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
