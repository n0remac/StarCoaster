#!/usr/bin/env python3
"""Find exact local GRP gait frames near logged actor positions in squad PNGs."""

import argparse
import json
from pathlib import Path
import re

import numpy as np
from PIL import Image

from squad_verification import local_purple_counts, project, screen_direction


def match_actor(screen: np.ndarray, source: Path, manifest: dict, actor: tuple,
                rotation: int, center_z: int) -> dict:
    unit_id, x, y, facing, motion, z = actor
    if motion != "walk":
        return {"id": unit_id, "score": 0.0, "frame": None}
    direction = screen_direction(facing, rotation)
    px, py = project(x, y, rotation, z, center_z)
    best = (0.0, None, None)
    for pose in range(10):
        name = f"walk{pose}_{direction}.png"
        meta = manifest["frames"][name]
        image = Image.open(source / name).convert("RGBA")
        image = image.resize((image.width * 2, image.height * 2), Image.Resampling.NEAREST)
        pixels = np.asarray(image)
        opaque_y, opaque_x = np.nonzero(pixels[:, :, 3])
        sampled = np.linspace(0, len(opaque_x) - 1, min(24, len(opaque_x)), dtype=int)
        sx, sy = opaque_x[sampled], opaque_y[sampled]
        colours = pixels[sy, sx, :3]
        expected_x, expected_y = px + meta["x"] * 2, py + meta["y"] * 2
        origins_x = np.arange(max(0, expected_x - 100),
                              min(screen.shape[1] - pixels.shape[1], expected_x + 100) + 1)
        origins_y = np.arange(max(0, expected_y - 70),
                              min(screen.shape[0] - pixels.shape[0], expected_y + 70) + 1)
        if not len(origins_x) or not len(origins_y):
            continue
        scores = np.zeros((len(origins_y), len(origins_x)), dtype=np.uint8)
        for tx, ty, colour in zip(sx, sy, colours):
            region = screen[origins_y[:, None] + ty, origins_x[None, :] + tx, :]
            scores += np.all(region == colour, axis=2)
        finalists = np.argpartition(scores.ravel(), -min(4, scores.size))[-4:]
        for flat in finalists:
            row, col = np.unravel_index(flat, scores.shape)
            ox, oy = int(origins_x[col]), int(origins_y[row])
            confidence = float(np.mean(np.all(screen[oy + opaque_y, ox + opaque_x, :]
                                              == pixels[opaque_y, opaque_x, :3], axis=1)))
            if confidence > best[0]:
                best = (confidence, name, (ox, oy))
    return {"id": unit_id, "score": round(best[0], 3), "frame": best[1], "origin": best[2]}


def verify(directory: Path, source: Path, minimum_poses: int = 4) -> dict:
    manifest = json.loads((source / "manifest.json").read_text())
    states = json.loads((directory / "screenshot-states.json").read_text())
    results = []
    for filename, state in states.items():
        if not re.search(r"-t5\.[1-5](?:-rot[0-3])?\.png$", filename):
            continue
        path = directory / filename
        rotation_match = re.search(r"-rot([0-3])\.png$", filename)
        rotation = int(rotation_match.group(1)) if rotation_match else 0
        screen = np.asarray(Image.open(path).convert("RGB"))
        actors = state["actors"]
        counts = local_purple_counts(path, actors, rotation, state["center_z"])
        ranked = sorted((a for a in actors if a[4] == "walk"), key=lambda a: counts.get(a[0], 0), reverse=True)
        for actor in ranked[:4]:
            result = match_actor(screen, source, manifest, actor, rotation, state["center_z"])
            if result["score"] >= 0.8:
                results.append({"screenshot": filename, "rotation": rotation, **result})
                break
        else:
            results.append({"screenshot": filename, "rotation": rotation,
                            "id": None, "score": 0.0, "frame": None})
    poses = sorted({result["frame"].split("_", 1)[0] for result in results if result["frame"]})
    report = {"source_walk_poses": 10, "exactly_matched_poses": poses, "matches": results}
    (directory / "sprite-match.json").write_text(json.dumps(report, indent=2) + "\n")
    if len(poses) < minimum_poses:
        raise RuntimeError(f"Only {len(poses)} exact local gait poses were seen; need {minimum_poses}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--source", type=Path, default=Path("run-data/generated-assets/starcraft/zergling"))
    parser.add_argument("--minimum-poses", type=int, default=4)
    args = parser.parse_args()
    report = verify(args.directory, args.source, args.minimum_poses)
    print(f"Exact local gait poses: {report['exactly_matched_poses']}")
