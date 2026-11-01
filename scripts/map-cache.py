#!/usr/bin/env python3
"""Build, inspect, or reuse one validated existing-park preparation package."""

import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

from load_timing import LoadTiming
from scenario_package import ROOT
from single_map_cache import SingleMapCache


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "status", "reuse"))
    parser.add_argument("source", type=Path, help="installed scenario or existing save file")
    parser.add_argument("--cache-root", type=Path, default=ROOT / "run-data/map-cache")
    parser.add_argument("--session-dir", type=Path, help="fresh run-data directory for reuse")
    parser.add_argument("--rebuild", action="store_true", help="deliberately replace this key's package")
    args = parser.parse_args()
    if args.rebuild and args.action != "build":
        parser.error("--rebuild applies only to build")
    if args.action == "reuse" and args.session_dir is None:
        parser.error("reuse requires --session-dir")
    cache = SingleMapCache(args.cache_root)
    temporary = cache.root / "tmp"
    temporary.mkdir(exist_ok=True)
    os.environ["TMPDIR"] = str(temporary)
    tempfile.tempdir = str(temporary)
    timing = LoadTiming(args.source.name, cache.root / "timings.jsonl", "cache_" + args.action)
    try:
        if args.action == "status":
            state = cache.status(args.source, timing)
            result = {key: state[key] for key in ("status", "key", "package")}
            if "reason" in state:
                result["reason"] = state["reason"]
            outcome = state["status"]
        elif args.action == "build":
            manifest, reused = cache.build(args.source, rebuild=args.rebuild, timing=timing)
            result = {"status": "ready", "key": manifest["key"],
                      "package": str(cache.package_path(manifest["key"])), "reused": reused}
            outcome = "reused" if reused else "prepared"
        else:
            timing.generation = uuid.uuid4().hex
            plan = cache.materialize(args.source, args.session_dir, timing)
            result = {"status": "materialized", "key": timing.cache_key,
                      "session": str(Path(args.session_dir).resolve()), "plan": plan}
            outcome = "materialized"
        timing.finish(outcome)
        print(json.dumps(result, indent=2))
        return 0 if outcome not in ("invalid", "missing") else 1
    except Exception as error:
        timing.finish("failed", error)
        print(f"map-cache: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
