"""Projected screenshot checks for the controlled path, trees, and wall park."""

from __future__ import annotations

import json
from pathlib import Path
import re

import numpy as np
from PIL import Image

from park_assault_visual import body_pixels
from squad_verification import project


def verify(output: Path) -> dict:
    states = json.loads((output / "screenshot-states.json").read_text())
    samples = []
    for filename, state in sorted(states.items()):
        if len(state["actors"]) != 1:
            continue
        unit_id, x, y, facing, motion, z = state["actors"][0]
        rotation_tag = re.search(r"-rot([0-3])\.png$", filename)
        rotation = int(rotation_tag[1]) if rotation_tag else 0
        px, py = project(x, y, rotation, z, state["center_z"])
        rgb = np.asarray(Image.open(output / filename).convert("RGB"))
        candidates = ((body_pixels(rgb, px + dx, py + dy), dx, dy)
                      for dx in range(-64, 65, 8) for dy in range(-24, 25, 8))
        pixels, dx, dy = max(candidates)
        samples.append({"screenshot": filename, "unit": unit_id, "motion": motion,
                        "rotation": rotation, "position": {"x": x, "y": y},
                        "projected": [px, py], "sample_shift": [dx, dy],
                        "body_pixels": pixels, "on_path": 320 <= x <= 640 and abs(y - 480) <= 12})
    visible = [row for row in samples if row["on_path"] and row["body_pixels"] >= 20]
    rotations = {row["rotation"] for row in visible if row["screenshot"].startswith("client-b")}
    motions = {row["motion"] for row in visible}
    clear = [row for row in visible if row["position"]["x"] >= 500 and row["body_pixels"] >= 120]
    near_tree = [row for row in samples if row["on_path"]
                 and 400 <= row["position"]["x"] <= 480 and row["body_pixels"] < 110]
    near_wall = [row for row in visible if 512 <= row["position"]["x"] <= 560
                 and row["body_pixels"] >= 120]
    errors = []
    if rotations != {0, 1, 2, 3}:
        errors.append(f"visible path actor missing camera rotations {sorted({0, 1, 2, 3} - rotations)}")
    if not {"idle", "walk"}.issubset(motions):
        errors.append("standing and walking path actors were not both visible")
    if not clear or not near_tree:
        errors.append("clear and partly tree-occluded actor samples were not both captured")
    if not near_wall:
        errors.append("actor beside the wall was not visible")
    result = {"status": "failed" if errors else "passed", "samples": samples,
              "visible_rotations": sorted(rotations), "visible_motions": sorted(motions),
              "clear_samples": len(clear), "tree_occlusion_samples": len(near_tree),
              "wall_front_samples": len(near_wall), "errors": errors}
    (output / "visual-fixture-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
