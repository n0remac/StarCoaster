"""Check that staged g2 offsets match the local source frame manifests."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def report(output: Path) -> dict:
    registered = {row["path"]: row for row in json.loads(
        (ROOT / "upstream/openrct2/resources/g2/sprites.json").read_text()) if "path" in row}
    result = {"units": {}, "mismatches": []}
    for unit in ("zergling", "marine"):
        manifest = json.loads((ROOT / f"run-data/generated-assets/starcraft/{unit}/manifest.json").read_text())
        frames = {}
        for name, frame in manifest["frames"].items():
            path = f"bridge/{'marine/' if unit == 'marine' else ''}{name}"
            entry = registered.get(path)
            if entry is None or (entry["x"], entry["y"]) != (frame["x"], frame["y"]):
                result["mismatches"].append(path)
            motion = "idle" if name.startswith("idle") else "walk" if name.startswith("walk") else \
                     "attack" if name.startswith("attack") else "death"
            frames.setdefault(motion, []).append(frame["y"] + frame["height"])
        result["units"][unit] = {motion: {"frames": len(feet), "bottom_offset_min": min(feet),
                                           "bottom_offset_max": max(feet)}
                                 for motion, feet in frames.items()}
    result["status"] = "passed" if not result["mismatches"] else "failed"
    (output / "sprite-anchor-report.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
