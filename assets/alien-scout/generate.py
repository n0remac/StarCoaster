#!/usr/bin/env python3
"""Draw the bridge's original four-direction, three-frame creature sprite set."""

from pathlib import Path
import re
from PIL import Image, ImageDraw


OUT = Path(__file__).resolve().parent / "sprites"
OUT.mkdir(parents=True, exist_ok=True)

INK = (20, 34, 48, 255)
BODY = (34, 150, 145, 255)
LIGHT = (88, 213, 182, 255)
SHADOW = (23, 96, 111, 255)
EYE = (245, 189, 78, 255)


def load_openrct2_palette() -> list[tuple[int, int, int]]:
    header = Path(__file__).resolve().parents[2] / "upstream/openrct2/src/openrct2/drawing/ImageImporter.h"
    source = header.read_text().split("constexpr OpenRCT2::Drawing::GamePalette StandardPalette", 1)[1]
    entries = re.findall(r"\{\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\}", source)
    if len(entries) < 256:
        raise RuntimeError("could not read OpenRCT2's 256-colour palette")
    # The C++ palette entries use BGRA order.
    return [(int(red), int(green), int(blue)) for blue, green, red, _ in entries[:256]]


PALETTE = load_openrct2_palette()


def snap_to_palette(image: Image.Image) -> Image.Image:
    pixels = image.load()
    cache: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha < 128:
                continue
            colour = (red, green, blue)
            if colour not in cache:
                cache[colour] = min(
                    PALETTE[10:246],
                    key=lambda p: (p[0] - red) ** 2 + (p[1] - green) ** 2 + (p[2] - blue) ** 2,
                )
            pixels[x, y] = (*cache[colour], alpha)
    return image


def draw_sprite(direction: str, stride: int) -> Image.Image:
    canvas = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Two foot positions give the walk a visible gait while sharing one body.
    near_foot = 2 if stride == 1 else -1 if stride == 2 else 0
    far_foot = -2 if stride == 1 else 1 if stride == 2 else 0
    draw.polygon([(9 + far_foot, 22), (13, 21), (13, 27), (8 + far_foot, 28)], fill=INK)
    draw.polygon([(18 + near_foot, 22), (22, 21), (24 + near_foot, 28), (18 + near_foot, 28)], fill=INK)
    draw.polygon([(11, 17), (20, 17), (23, 24), (9, 24)], fill=INK)
    draw.polygon([(12, 18), (19, 18), (21, 22), (11, 22)], fill=BODY)
    draw.line([(12, 19), (17, 18)], fill=LIGHT, width=2)

    if direction in ("east", "west"):
        draw.polygon([(10, 10), (19, 9), (24, 13), (23, 19), (14, 21), (9, 17)], fill=INK)
        draw.polygon([(11, 12), (19, 11), (22, 14), (21, 18), (14, 19), (11, 16)], fill=BODY)
        draw.polygon([(13, 12), (19, 11), (21, 13), (15, 14)], fill=LIGHT)
        draw.rectangle((19, 14, 20, 15), fill=EYE)
        draw.line([(12, 10), (10, 5), (8, 5)], fill=INK, width=2)
        draw.line([(17, 9), (17, 4), (19, 3)], fill=INK, width=2)
        draw.polygon([(9, 19), (6, 16), (5, 17), (8, 23)], fill=SHADOW)
        if direction == "west":
            canvas = canvas.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    elif direction == "south":
        draw.polygon([(9, 10), (22, 10), (25, 15), (21, 21), (11, 21), (7, 15)], fill=INK)
        draw.polygon([(10, 12), (21, 12), (23, 15), (20, 19), (12, 19), (9, 15)], fill=BODY)
        draw.polygon([(11, 12), (21, 12), (19, 14), (13, 14)], fill=LIGHT)
        draw.rectangle((12, 15, 13, 16), fill=EYE)
        draw.rectangle((19, 15, 20, 16), fill=EYE)
        draw.line([(11, 11), (9, 5), (7, 4)], fill=INK, width=2)
        draw.line([(21, 11), (23, 5), (25, 4)], fill=INK, width=2)
    else:  # north: back view without visible eyes
        draw.polygon([(9, 10), (22, 10), (25, 15), (21, 21), (11, 21), (7, 15)], fill=INK)
        draw.polygon([(10, 12), (21, 12), (23, 15), (20, 19), (12, 19), (9, 15)], fill=SHADOW)
        draw.polygon([(11, 12), (21, 12), (19, 17), (13, 17)], fill=BODY)
        draw.line([(11, 10), (9, 4), (7, 3)], fill=INK, width=2)
        draw.line([(21, 10), (23, 4), (25, 3)], fill=INK, width=2)

    return canvas


for state, stride in (("idle", 0), ("walk0", 1), ("walk1", 2)):
    for direction in ("east", "south", "west", "north"):
        snap_to_palette(draw_sprite(direction, stride)).save(OUT / f"{state}_{direction}.png")

print(f"Wrote 12 original sprites to {OUT}")
