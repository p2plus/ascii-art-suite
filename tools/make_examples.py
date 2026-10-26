#!/usr/bin/env python3
"""Regenerate the example images used by the README and the demo GIF.

Run from the repository root:  python3 tools/make_examples.py
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "examples"

WIDTH, HEIGHT = 880, 560


def night_valley() -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT))
    px = img.load()
    rng = random.Random(42)
    top, horizon = (11, 16, 38), (58, 84, 128)
    y_horizon = int(HEIGHT * 0.62)
    for y in range(HEIGHT):
        t = min(y / y_horizon, 1.0)
        r = int(top[0] + (horizon[0] - top[0]) * t)
        g = int(top[1] + (horizon[1] - top[1]) * t)
        b = int(top[2] + (horizon[2] - top[2]) * t)
        for x in range(WIDTH):
            px[x, y] = (r, g, b)
    # stars, brighter towards the top
    for _ in range(260):
        x, y = rng.randrange(WIDTH), rng.randrange(y_horizon - 20)
        v = rng.randrange(120, 255)
        if rng.random() < 0.12:
            px[x, y] = (v, v, min(255, v + 20))
        else:
            px[x, y] = (v, v, v)
    draw = ImageDraw.Draw(img)
    # moon with terminator shading
    mx, my, mr = int(WIDTH * 0.72), int(HEIGHT * 0.2), 34
    for i, radius in enumerate(range(mr, 0, -1)):
        shade = 235 - int(90 * (radius / mr))
        draw.ellipse((mx - radius, my - radius, mx + radius, my + radius),
                     fill=(shade, shade, min(255, shade + 12)))
    for cx, cy, cr in ((mx - 10, my - 6, 6), (mx + 8, my + 10, 4), (mx + 2, my - 14, 3)):
        draw.ellipse((cx - cr, cy - cr, cx + cr, cy + cr), fill=(150, 150, 162))
    # mountain layers, far to near
    layers = (
        (0.55, (40, 52, 84)),
        (0.68, (26, 34, 60)),
        (0.82, (14, 19, 38)),
    )
    for depth, color in layers:
        points = [(0, HEIGHT), (0, int(HEIGHT * depth))]
        x = 0
        while x < WIDTH:
            x += rng.randrange(60, 140)
            points.append((min(x, WIDTH),
                           int(HEIGHT * depth) + rng.randrange(-70, 60)))
        points.append((WIDTH, int(HEIGHT * depth)))
        points.append((WIDTH, HEIGHT))
        draw.polygon(points, fill=color)
    # foreground lake with moon reflection
    draw.rectangle((0, int(HEIGHT * 0.9), WIDTH, HEIGHT), fill=(9, 13, 28))
    for i in range(9):
        w = rng.randrange(30, 130)
        x = mx - w // 2 + rng.randrange(-20, 20)
        y = int(HEIGHT * 0.9) + 6 + i * 5
        shade = 120 - i * 11
        draw.line((x, y, x + w, y), fill=(shade, shade, min(255, shade + 25)))
    return img


def bold_digits() -> Image.Image:
    """A big, stroked '42' for the braille renderer (bold shapes love dots)."""
    img = Image.new("L", (560, 250), 0)
    font = _load_font(190)
    draw = ImageDraw.Draw(img)
    draw.text((50, 22), "42", font=font, fill=255, stroke_width=12, stroke_fill=255)
    box = img.getbbox()
    if box:
        pad = 12
        box = (max(0, box[0] - pad), max(0, box[1] - pad),
               min(560, box[2] + pad), min(250, box[3] + pad))
        img = img.crop(box)
    return img


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = (
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    night_valley().save(OUT / "valley.png", optimize=True)
    bold_digits().save(OUT / "digits.png", optimize=True)
    for path in sorted(OUT.glob("*.png")):
        print(f"{path.name}: {path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
