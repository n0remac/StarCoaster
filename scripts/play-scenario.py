#!/usr/bin/env python3
"""Resolve a scenario package and reuse the existing world session launcher."""

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scenario_package import ROOT, build_native_map, ensure_park, resolve, session_environment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario_id")
    parser.add_argument("--plan", action="store_true", help="print resolved package without starting engines")
    args = parser.parse_args()
    try:
        plan = resolve(args.scenario_id)
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    if args.plan:
        print(json.dumps(plan, indent=2))
        return
    ensure_park(plan)
    build_native_map(plan)
    env = session_environment(plan)
    os.execvpe(str(ROOT / "scripts/run-world-session.sh"),
               [str(ROOT / "scripts/run-world-session.sh"), plan["park"]], env)


if __name__ == "__main__":
    main()
