"""Check projected Zergling body pixels in the graphical assault captures."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re

import numpy as np
from PIL import Image, ImageDraw


def project(x: int, y: int, center: tuple[int, int], rotation: int = 1) -> tuple[int, int]:
    def rotate(px: int, py: int) -> tuple[int, int]:
        return ((px, py), (py, -px), (-px, -py), (-py, px))[rotation]
    rx, ry = rotate(x, y)
    cx, cy = rotate(*center)
    return 640 + 2 * ((ry - rx) - (cy - cx)), 400 + (rx + ry) - (cx + cy)


def body_pixels(rgb: np.ndarray, px: int, py: int) -> int:
    # The health bar is above this region. Paths, grass, and wall textures do
    # not have the local Zergling palette's blue-dominant body colours.
    left, right = max(0, px - 22), min(rgb.shape[1], px + 23)
    top, bottom = max(40, py - 22), min(rgb.shape[0] - 40, py + 23)
    if right <= left or bottom <= top:
        return 0
    red, green, blue = np.moveaxis(rgb[top:bottom, left:right].astype(np.int16), -1, 0)
    return int(((red >= 60) & (blue >= red + 35) & (blue >= green + 25)).sum())


def verify(output: Path, fixture: dict) -> dict:
    observed = json.loads((output / "observed-paths.json").read_text())
    events = json.loads((output / "capture-events.json").read_text())
    bw_log = (output / "bwapi.log").read_text(errors="replace")
    assignment = dict(re.findall(r"\[park-assault\] route id=(\d+) target=([a-z0-9-]+)", bw_log))
    deaths = {target: int(frame) for target, frame in re.findall(
        r"\[park-assault\] target-destroyed id=([a-z0-9-]+) proxy=\d+ frame=(\d+)", bw_log)}
    targets = {target["id"]: target for target in fixture["targets"]}
    data = Path(__file__).resolve().parent.parent / "run-data/park-assault/navigation-elements.json"
    paths = {(element["x"], element["y"]) for element in json.loads(data.read_text())["elements"]
        if element["type"] == "footpath"}
    checks = []
    failures = []
    focus = {"path": (1264, 624), "shop-attack": (1264, 624),
             "carousel-attack": (640, 640), "ferris-attack": (1360, 1280)}
    for event in events:
        stage = event["stage"]
        if event["client"] != "client-b" or stage not in focus:
            continue
        rgb = np.asarray(Image.open(output / event["filename"]).convert("RGB"))
        annotation = Image.fromarray(rgb.copy())
        draw = ImageDraw.Draw(annotation)
        samples = []
        for unit_id, history in observed.items():
            sample = min(history, key=lambda row: abs(row["frame"] - event["bw_frame"]))
            if abs(sample["frame"] - event["bw_frame"]) > 12:
                continue
            px, py = project(sample["park_x"], sample["park_y"], focus[stage])
            if px < 25 or px >= rgb.shape[1] - 25 or py < 65 or py >= rgb.shape[0] - 65:
                continue
            count = body_pixels(rgb, px, py)
            on_path = (sample["park_x"] // 32, sample["park_y"] // 32) in paths
            target_id = assignment.get(unit_id)
            if target_id is None:
                continue
            target = targets[target_id]
            distance = min(math.hypot(max(tile["x"] * 32 - sample["park_x"], 0,
                                          sample["park_x"] - (tile["x"] + 1) * 32),
                                      max(tile["y"] * 32 - sample["park_y"], 0,
                                          sample["park_y"] - (tile["y"] + 1) * 32))
                           for tile in target["footprint_tiles"])
            visible = count >= 10
            draw.rectangle((px - 22, py - 22, px + 22, py + 22),
                           outline=(0, 255, 0) if visible else (255, 64, 64), width=2)
            samples.append({"unit_id": unit_id, "target": target_id, "path": on_path,
                            "ride_distance": round(distance, 1), "projected": [px, py],
                            "body_pixels": count, "visible": visible})
        annotation.save(output / f"visual-samples-{stage}.png")
        if stage == "path":
            passed = any(row["visible"] for row in samples)
        else:
            target_id = stage.removesuffix("-attack")
            target_id = {"shop": "shop-1", "carousel": "carousel-1", "ferris": "ride-2"}[target_id]
            passed = (event["bw_frame"] < deaths[target_id] and
                      any(row["target"] == target_id and row["ride_distance"] <= 128
                          and row["visible"] for row in samples))
        if not passed:
            failures.append(f"{stage}: no visible Zergling at the required path or ride position")
        checks.append({"stage": stage, "capture_frame": event["bw_frame"],
                       "passed": passed, "samples": samples})
    if len(checks) != len(focus):
        failures.append("missing required graphical capture stages")
    if not any(sample["path"] and sample["visible"]
               for check in checks for sample in check["samples"]):
        failures.append("no visible Zergling was verified on a footpath")
    report = {"status": "failed" if failures else "passed", "checks": checks, "errors": failures}
    (output / "visual-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
