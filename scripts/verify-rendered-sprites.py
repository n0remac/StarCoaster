#!/usr/bin/env python3
"""Match actual OpenRCT2 screenshot pixels to local sprite frames at zoom -1."""

import argparse
import json
from pathlib import Path
import re

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parent.parent


def purple(red: np.ndarray, green: np.ndarray, blue: np.ndarray) -> np.ndarray:
    return (red >= 60) & (blue >= red + 35) & (blue >= green + 25)


def templates(directory: Path) -> list[tuple[str, np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    result = []
    for path in sorted(directory.glob("*.png")):
        if not path.stem.startswith(("idle_", "walk0_", "walk1_")):
            continue
        image = Image.open(path).convert("RGBA")
        image = image.resize((image.width * 2, image.height * 2), Image.Resampling.NEAREST)
        array = np.asarray(image)
        opaque_y, opaque_x = np.nonzero(array[:, :, 3] > 0)
        colour = array[:, :, :3].astype(np.int16)
        candidates = purple(colour[:, :, 0], colour[:, :, 1], colour[:, :, 2]) & (array[:, :, 3] > 0)
        purple_y, purple_x = np.nonzero(candidates)
        if len(purple_x) == 0:
            raise ValueError(f"Sprite has no detectable body pixels: {path}")
        sample = np.linspace(0, len(purple_x) - 1, min(24, len(purple_x)), dtype=int)
        result.append((path.name, array[:, :, :3], opaque_x, opaque_y,
                       np.column_stack((purple_x[sample], purple_y[sample]))))
    if len(result) != 24:
        raise ValueError(f"Expected 24 local sprites in {directory}, got {len(result)}")
    return result


def match(path: Path, source: list) -> dict:
    image = np.asarray(Image.open(path).convert("RGB"))
    world = image[image.shape[0] // 8:image.shape[0] * 13 // 16,
                  image.shape[1] // 8:image.shape[1] * 7 // 8]
    marked = purple(world[:, :, 0].astype(np.int16), world[:, :, 1].astype(np.int16),
                    world[:, :, 2].astype(np.int16))
    ys, xs = np.nonzero(marked)
    if len(xs) < 20:
        return {"image": path.name, "frame": None, "score": 0.0}
    first_x = image.shape[1] // 8 + int(xs.min())
    first_y = image.shape[0] // 8 + int(ys.min())
    best = (0.0, None, None)
    for name, rgb, opaque_x, opaque_y, sample in source:
        sample_rgb = rgb[sample[:, 1], sample[:, 0], :]
        purple_pixels = purple(rgb[:, :, 0].astype(np.int16), rgb[:, :, 1].astype(np.int16),
                               rgb[:, :, 2].astype(np.int16))
        py, px = np.nonzero(purple_pixels)
        left = max(0, first_x - int(px.max()) - 16)
        right = min(image.shape[1] - rgb.shape[1], first_x - int(px.min()) + 16)
        top = max(0, first_y - int(py.max()) - 16)
        bottom = min(image.shape[0] - rgb.shape[0], first_y - int(py.min()) + 16)
        if right < left or bottom < top:
            continue
        origins_x = np.arange(left, right + 1)
        origins_y = np.arange(top, bottom + 1)
        score_grid = np.zeros((len(origins_y), len(origins_x)), dtype=np.uint8)
        for (sx, sy), colour in zip(sample, sample_rgb):
            region = image[origins_y[:, None] + sy, origins_x[None, :] + sx, :]
            score_grid += np.all(region == colour, axis=2)
        finalists = np.argpartition(score_grid.ravel(), -min(5, score_grid.size))[-5:]
        for flat in finalists:
            row, col = np.unravel_index(flat, score_grid.shape)
            x, y = int(origins_x[col]), int(origins_y[row])
            same = np.all(image[y + opaque_y, x + opaque_x, :] == rgb[opaque_y, opaque_x, :], axis=1)
            confidence = float(same.mean())
            if confidence > best[0]:
                best = (confidence, name, [x, y])
    return {"image": path.name, "frame": best[1], "score": round(best[0], 3), "origin": best[2]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--sprite-dir", type=Path, default=ROOT / "run-data/generated-assets/starcraft/zergling")
    parser.add_argument("--expect-motion", choices=["walk", "idle", "mixed"], default="mixed")
    parser.add_argument("--axis", choices=["east-west", "diagonal"])
    args = parser.parse_args()
    source = templates(args.sprite_dir)
    report = [match(path, source) for path in sorted(args.capture_dir.glob("client-*.png"))]
    confident = [item for item in report if item["score"] >= 0.8]
    for item in report:
        print(f"{item['image']}: {item['frame'] or 'occluded/absent'} score={item['score']:.3f}")
    for client in ("client-a", "client-b"):
        found = [item for item in confident if item["image"].startswith(client)]
        if len(found) < 2:
            raise RuntimeError(f"Too few exact sprite matches on {client}")
    if args.expect_motion == "walk":
        motions = {item["frame"].split("_", 1)[0] for item in confident}
        if not {"walk0", "walk1"}.issubset(motions):
            raise RuntimeError(f"Both walking poses were not observed: {motions}")
    elif args.expect_motion == "idle":
        if any(not item["frame"].startswith("idle_") for item in confident):
            raise RuntimeError("Walking artwork appeared in the idle probe")
    if args.axis:
        for item in confident:
            rotation = re.search(r"-rot([0-3])\.png$", item["image"])
            if not rotation:
                continue
            direction = item["frame"].split("_", 1)[1].removesuffix(".png")
            r = int(rotation.group(1))
            expected = ({"east", "west"} if r % 2 == 0 else {"north", "south"}) if args.axis == "east-west" else (
                {"southeast", "northwest"} if r % 2 == 0 else {"southwest", "northeast"})
            if direction not in expected:
                raise RuntimeError(f"Wrong direction at camera rotation {r}: {item['frame']}")
    (args.capture_dir / "visual-match.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Exact matches: {len(confident)}/{len(report)}")


if __name__ == "__main__":
    main()
