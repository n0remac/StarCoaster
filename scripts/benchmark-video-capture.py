#!/usr/bin/env python3
"""Compare Frontier simulation progress without video and at 15/30 FPS."""

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


def benchmark(mode: str, seconds: int, prefix: str, layout: str, width: int,
              preset: str, crf: int, frame_ms: int, graphics: str,
              display_width: int, display_height: int) -> dict:
    output = ROOT / "run-data" / f"{prefix}-{mode}"
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["STARCOASTER_ARTIFACT_ROOT"] = str(output / "artifacts")
    command = [sys.executable, str(ROOT / "scripts/record-scenario.py"),
               "--duration", str(seconds), "--video-layout", layout,
               "--video-width", str(width), "--video-preset", preset,
               "--video-crf", str(crf), "--frame-ms", str(frame_ms),
               "--graphics", graphics, "--display-width", str(display_width),
               "--display-height", str(display_height)]
    command += ["--no-video"] if mode == "off" else ["--video-fps", mode]
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
    runs = list((output / "artifacts").glob("*/run.json"))
    artifact = max(runs, key=lambda path: path.stat().st_mtime).parent if runs else output
    client_stats = {}
    for client in ("client-a", "client-b"):
        path = artifact / f"{client}.log"
        content = path.read_text(errors="replace") if path.exists() else ""
        ticks = [int(tick) for tick in TICKS.findall(content)]
        client_stats[client] = {"applied_snapshots": len(ticks), "first_tick": min(ticks) if ticks else None,
                                "last_tick": max(ticks) if ticks else None,
                                "tick_span": max(ticks) - min(ticks) if len(ticks) > 1 else 0,
                                "desync_warning": "mismatch" in content.lower()}
    metadata_path = artifact / "video-metadata.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else None
    clock_ticks = os.sysconf("SC_CLK_TCK")
    record_seconds = metadata["recording_duration_seconds"] if metadata else None
    return {"mode": mode, "layout": layout, "exit_code": code, "wall_seconds": round(elapsed, 3),
            "ffmpeg_cpu_seconds": round(sum(highest_ticks.values()) / clock_ticks, 3),
            "ffmpeg_cpu_percent_of_one_core": round(100 * sum(highest_ticks.values()) / clock_ticks / record_seconds, 1)
            if record_seconds else None,
            "peak_tree_rss_kib": peak_rss, "peak_ffmpeg_rss_kib": peak_ffmpeg_rss,
            "clients": client_stats, "video": metadata["outputs"] if metadata else None,
            "artifact_directory": str(artifact), "output_directory": str(output)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modes", nargs="+", choices=("off", "15", "30"),
                        default=("off", "15", "30"))
    parser.add_argument("--seconds", type=int, default=45)
    parser.add_argument("--prefix", default="video-benchmark")
    parser.add_argument("--layout", choices=("single", "combined", "separate"), default="single")
    parser.add_argument("--video-width", type=int, default=960)
    parser.add_argument("--video-preset", default="ultrafast")
    parser.add_argument("--video-crf", type=int, default=30)
    parser.add_argument("--frame-ms", type=int, default=70)
    parser.add_argument("--graphics", choices=("software", "native"), default="software")
    parser.add_argument("--display-width", type=int, default=1280)
    parser.add_argument("--display-height", type=int, default=800)
    args = parser.parse_args()
    if args.seconds < 15:
        parser.error("--seconds must be at least 15")
    results = []
    for mode in args.modes:
        print(f"Running {mode} FPS graphical regression", flush=True)
        result = benchmark(mode, args.seconds, args.prefix, args.layout,
                           args.video_width, args.video_preset, args.video_crf, args.frame_ms,
                           args.graphics, args.display_width, args.display_height)
        results.append(result)
        summary = ROOT / "run-data" / f"{args.prefix}-summary.json"
        summary.write_text(json.dumps(results, indent=2) + "\n")
        print(f"{mode} FPS: exit={result['exit_code']} wall={result['wall_seconds']}s ",
              f"FFmpeg CPU={result['ffmpeg_cpu_percent_of_one_core']}%", flush=True)
    return 0 if all(result["exit_code"] == 0 for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
