#!/usr/bin/env python3
"""Save a normal no-objective park from the existing Frontier layout for live defense checks."""
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "run-data/frontier-playable/save/frontier-outpost-playable.park"
OUTPUT = ROOT / "run-data/universal-park-defense-live/fixture"
NAME = "ordinary-frontier-park"


def main():
    if not SOURCE.is_file():
        raise RuntimeError(f"missing source park: {SOURCE}")
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    (OUTPUT / "plugin").mkdir(parents=True, exist_ok=True)
    (OUTPUT / "config.ini").write_text("[network]\nadvertise = false\n")
    (OUTPUT / "plugin/prepare.js").write_text(
        'registerPlugin({name:"Ordinary Park Fixture",version:"1.0",authors:["StarCoaster"],'
        'type:"local",licence:"MIT",targetApiVersion:124,minApiVersion:124,main:function(){'
        'var done=false;context.subscribe("interval.tick",function(){if(done)return;done=true;'
        'scenario.objective.type="none";scenario.status="inProgress";'
        'context.saveGame({filename:"' + NAME + '"});'
        'console.log("ORDINARY_PARK_SAVED objective="+scenario.objective.type'
        '+" status="+scenario.status+" map="+map.size.x+"x"+map.size.y);});}});')
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    command = [str(ROOT / "build/openrct2/openrct2-cli"), "host", str(SOURCE),
               "--headless", "--address=127.0.0.1", f"--port={port}",
               f"--rct2-data-path={os.environ.get('RCT2_DATA_DIR', '/home/pi/games/rct2')}",
               f"--openrct2-data-path={ROOT / 'build/openrct2-stage/usr/local/share/openrct2'}",
               f"--user-data-path={OUTPUT}"]
    saved = OUTPUT / "save" / (NAME + ".park")
    saved.unlink(missing_ok=True)
    log = OUTPUT / "prepare.log"
    with log.open("w") as stream:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if "ORDINARY_PARK_SAVED objective=none status=inProgress map=64x64" in log.read_text(errors="replace") \
                        and saved.is_file() and saved.stat().st_size > 0:
                    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != source_hash:
                        raise AssertionError("source park changed")
                    print(saved)
                    return
                if process.poll() is not None:
                    raise RuntimeError(f"OpenRCT2 exited before saving; see {log}")
                time.sleep(.25)
            raise TimeoutError(f"park save timed out; see {log}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
