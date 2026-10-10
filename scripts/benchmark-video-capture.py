#!/usr/bin/env python3
"""Run the 65-second graphical regression at selected recording rates on this Pi."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent.parent
TICKS = re.compile(r"RTS Bridge apply tick=(\d+)")


def process_sample(pid: int):
    try:
        stat = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
        name = (Path("/proc") / str(pid) / "comm").read_text().strip()
        children_text = (Path("/proc") / str(pid) / "task" / str(pid) / "children").read_text()
    except (FileNotFoundError, ProcessLookupError):
        return None
    ticks = int(stat[11]) + int(stat[12])
    rss_kib = int(stat[21]) * os.sysconf("SC_PAGE_SIZE") // 1024
    return name, ticks, rss_kib, [int(item) for item in children_text.split()]


def sample_tree(pid: int):
    samples = {}
    todo = [pid]
    while todo:
        child = todo.pop()
        value = process_sample(child)
        if value:
            samples[child] = value[:3]
            todo.extend(value[3])
    return samples


def benchmark(mode: str, park: Path, seconds: int, prefix: str) -> dict:
    output = ROOT / "run-data" / f"{prefix}-{mode}"
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DEMO_PARK"] = str(park)
    env["DEMO_OUTPUT_DIR"] = str(output)
    command = [sys.executable, str(ROOT / "scripts/capture-live-demo.py"), "--seconds", str(seconds),
               "--cycle-rotations", "--verify-zergling", "--publisher-restart", "--sample-animation"]
    if mode != "off":
        command += ["--record-video", "--video-fps", mode]
    highest_ticks = {}
    peak_rss = 0
    peak_ffmpeg_rss = 0
    started = time.monotonic()
    with (output / "benchmark-console.log").open("w") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        while process.poll() is None:
            current = sample_tree(process.pid)
            peak_rss = max(peak_rss, sum(value[2] for value in current.values()))
            for pid, (name, ticks, rss) in current.items():
                if name == "ffmpeg":
                    highest_ticks[pid] = max(highest_ticks.get(pid, 0), ticks)
                    peak_ffmpeg_rss = max(peak_ffmpeg_rss, rss)
            time.sleep(0.25)
        code = process.wait()
    elapsed = time.monotonic() - started
    client_stats = {}
    for client in ("client-a", "client-b"):
        path = output / f"{client}.log"
        content = path.read_text(errors="replace") if path.exists() else ""
        ticks = [int(tick) for tick in TICKS.findall(content)]
        client_stats[client] = {"applied_snapshots": len(ticks), "first_tick": min(ticks) if ticks else None,
                                "last_tick": max(ticks) if ticks else None,
                                "desync_warning": "mismatch" in content.lower()}
    metadata_path = output / "video-metadata.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else None
    clock_ticks = os.sysconf("SC_CLK_TCK")
    record_seconds = metadata["recording_duration_seconds"] if metadata else None
    return {"mode": mode, "exit_code": code, "wall_seconds": round(elapsed, 3),
            "ffmpeg_cpu_seconds": round(sum(highest_ticks.values()) / clock_ticks, 3),
            "ffmpeg_cpu_percent_of_one_core": round(100 * sum(highest_ticks.values()) / clock_ticks / record_seconds, 1)
            if record_seconds else None,
            "peak_tree_rss_kib": peak_rss, "peak_ffmpeg_rss_kib": peak_ffmpeg_rss,
            "clients": client_stats, "video": metadata["outputs"] if metadata else None,
            "output_directory": str(output)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modes", nargs="+", choices=("off", "5", "10", "15"),
                        default=("off", "5", "10", "15"))
    parser.add_argument("--seconds", type=int, default=65)
    parser.add_argument("--prefix", default="video-benchmark")
    parser.add_argument("--park", type=Path,
                        default=ROOT / "run-data/park-generator/save/bridge-render-test.park")
    args = parser.parse_args()
    if args.seconds < 35:
        parser.error("--seconds must be at least 35 for publisher restart benchmarking")
    park = args.park.resolve()
    results = []
    for mode in args.modes:
        print(f"Running {mode} FPS graphical regression", flush=True)
        result = benchmark(mode, park, args.seconds, args.prefix)
        results.append(result)
        summary = ROOT / "run-data" / f"{args.prefix}-summary.json"
        summary.write_text(json.dumps(results, indent=2) + "\n")
        print(f"{mode} FPS: exit={result['exit_code']} wall={result['wall_seconds']}s ",
              f"FFmpeg CPU={result['ffmpeg_cpu_percent_of_one_core']}%", flush=True)
    return 0 if all(result["exit_code"] == 0 for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
