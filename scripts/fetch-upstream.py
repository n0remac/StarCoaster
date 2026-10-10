#!/usr/bin/env python3
"""Fetch the three pinned upstream repositories into this project directory."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = json.loads((ROOT / "dependencies.lock.json").read_text())


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def main() -> int:
    (ROOT / "upstream").mkdir(exist_ok=True)
    for name, entry in LOCK.items():
        checkout = ROOT / "upstream" / name
        if not (checkout / ".git").exists():
            command = ["git", "clone", "--depth", "1", "--filter=blob:none"]
            if entry.get("branch"):
                command += ["--branch", entry["branch"]]
            command += [entry["repository"], str(checkout)]
            subprocess.run(command, check=True)
        origin = git("-C", str(checkout), "remote", "get-url", "origin")
        if origin != entry["repository"]:
            print(f"Wrong origin for {name}: {origin}", file=sys.stderr)
            return 1
        current = git("-C", str(checkout), "rev-parse", "HEAD")
        if current != entry["commit"]:
            if git("-C", str(checkout), "status", "--porcelain"):
                print(f"Refusing to change modified checkout: {checkout}", file=sys.stderr)
                return 1
            subprocess.run(
                ["git", "-C", str(checkout), "fetch", "--depth", "1", "origin", entry["commit"]],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(checkout), "checkout", "--detach", entry["commit"]],
                check=True,
            )
        print(f"{name}: {entry['commit']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
