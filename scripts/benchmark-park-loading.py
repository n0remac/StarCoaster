#!/usr/bin/env python3
"""Measure stock and saved park loading without touching a managed game service."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

from load_timing import LoadTiming
from park_session_supervisor import ParkSessionSupervisor
from scenario_package import ROOT


def free_ports(count):
    probes = [socket.socket() for _ in range(count)]
    try:
        for probe in probes:
            probe.bind(("127.0.0.1", 0))
        return [probe.getsockname()[1] for probe in probes]
    finally:
        for probe in probes:
            probe.close()


def version(command):
    try:
        return subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=10, check=False).stdout.strip()[:200]
    except (OSError, subprocess.TimeoutExpired) as error:
        return str(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", action="append", required=True, help="installed RCT2 scenario filename")
    parser.add_argument("--save", type=Path, required=True, help="existing OpenRCT2 save or park")
    parser.add_argument("--samples", type=int, default=2)
    parser.add_argument("--output", type=Path, default=ROOT / "run-data/map-loading-baseline")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "run-data").resolve()):
        parser.error("output must be under run-data")
    if args.samples < 2:
        parser.error("at least two samples are needed for first and repeated selection")
    if args.save.suffix.lower() not in (".park", ".sc6", ".sc4", ".sv6", ".sv4"):
        parser.error("save must use a supported OpenRCT2 format")
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / "tmp"
    temporary.mkdir(exist_ok=True)
    os.environ["TMPDIR"] = str(temporary)
    tempfile.tempdir = str(temporary)
    library = output / "library"
    library.mkdir(exist_ok=True)
    saved_name = "Baseline Save" + args.save.suffix.lower()
    shutil.copy2(args.save.resolve(strict=True), library / saved_name)
    supervisor = ParkSessionSupervisor(library, output / "runtime", start_browser=False)
    names = args.stock + [saved_name]
    available = supervisor.catalog()
    for name in names:
        if name not in available:
            parser.error("map is not installed: " + name)
    metadata = {"schema_version": 1, "source_commit": version(["git", "rev-parse", "HEAD"]),
                "openbw_revision": version(["git", "-C", "upstream/openbw", "rev-parse", "HEAD"]),
                "openrct2_version": version([str(ROOT / "build/openrct2/openrct2-cli"), "--version"]),
                "sample_count_per_map": args.samples, "maps": names, "samples": []}
    for name in names:
        for index in range(args.samples):
            ports = free_ports(4)
            keys = ("OPENRCT2_PORT", "STARCOASTER_BRIDGE_PORT", "BRIDGE_OPENBW_PORT", "BRIDGE_CONTROLLER_PORT")
            prior = {key: os.environ.get(key) for key in keys}
            os.environ.update({key: str(port) for key, port in zip(keys, ports)})
            timing = LoadTiming(name, supervisor.runtime / "load-timings.jsonl", "baseline")
            process = None
            outcome, failure = "ready", None
            try:
                generation, plan = supervisor.prepare(name, timing)
                timing.generation = generation
                with timing.stage("session_startup"):
                    process, log_path = supervisor.launch(generation, plan)
                    supervisor.await_ready(process, log_path)
            except Exception as error:
                outcome, failure = "failed", error
            finally:
                timing.finish(outcome, failure)
                supervisor.stop(process)
                for key, value in prior.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            record = json.loads((supervisor.runtime / "load-timings.jsonl").read_text().splitlines()[-1])
            metadata["samples"].append({"map": name, "sample": index + 1, "generation": record["generation"],
                                        "source_sha256": record["source_sha256"], "outcome": outcome,
                                        "total_ms": record["total_ms"],
                                        "stages": {key: value["elapsed_ms"] for key, value in record["stages"].items()},
                                        "error": str(failure)[:240] if failure else None})
            print(f"{name} sample {index + 1}/{args.samples}: {outcome} {record['total_ms']} ms", flush=True)
    metadata["record_file"] = str(supervisor.runtime / "load-timings.jsonl")
    (output / "summary.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(output / "summary.json", flush=True)
    return 1 if any(sample["outcome"] != "ready" for sample in metadata["samples"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
