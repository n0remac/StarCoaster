#!/usr/bin/env python3
"""Force-generate a packaged scenario's park, fixture, and navigation data."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scenario_package import ensure_park, resolve


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario_id", nargs="?", default="frontier-outpost")
    args = parser.parse_args()
    try:
        plan = resolve(args.scenario_id)
        ensure_park(plan, force=True)
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        parser.error(str(exc))
    print(f"{plan['scenario_id']}: park={plan['park']} fixture={plan['fixture']} navigation={plan['navigation']}")


if __name__ == "__main__":
    main()
