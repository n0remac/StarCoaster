#!/usr/bin/env python3
"""Check that local upstream checkouts match dependencies.lock.json."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = json.loads((ROOT / "dependencies.lock.json").read_text())


def main() -> int:
    failed = False
    for name, entry in LOCK.items():
        checkout = ROOT / "upstream" / name
        if not (checkout / ".git").exists():
            print(f"MISSING {name}: {checkout}")
            failed = True
            continue
        sha = subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
        ).strip()
        if sha != entry["commit"]:
            print(f"MISMATCH {name}: expected {entry['commit']}, found {sha}")
            failed = True
        else:
            print(f"OK {name}: {sha}")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
