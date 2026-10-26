"""The ``asciiart demo`` tour: fonts, ramps and renderers on one screen."""
from __future__ import annotations

import sys
from typing import IO

from .charsets import CHARSETS
from .cli import _pick_random
from .figlet import list_fonts, load_font

TOUR_FONTS = ("mini", "slant", "doom")
WILDCARD_POOL = ("starwars", "avatar", "epic", "shadow", "graffiti", "larry3d",
                 "colossal", "banner", "lean", "chunky")


def print_demo(out: IO[str] | None = None, seed: int = 7, width: int = 80) -> None:
    out = out or sys.stdout
    bundled = [ref for ref in list_fonts().values() if ref.source == "bundled"]
    total = len(list_fonts())

    def show(text: str, font: str) -> None:
        art = load_font(font).render(text, width=width)
        out.write(art + "\n\n")

    show("asciiart", "standard")
    out.write(f"{total} fonts discovered ({len(bundled)} bundled) - zero dependencies\n\n")

    out.write("text -> figlet, a few of the classics:\n\n")
    for font in TOUR_FONTS:
        try:
            show("Ascii Art", font)
        except Exception:  # noqa: BLE001 - demo must never die mid-tour
            continue

    out.write("text -> figlet, seeded wildcard pick:\n\n")
    pool = [name for name in WILDCARD_POOL if name in list_fonts()]
    if pool:
        show("Ascii Art", _pick_random(pool, seed))

    out.write("image -> ascii, the character ramps:\n\n")
    for name, ramp in CHARSETS.items():
        bar = "".join(
            ramp[min(v * len(ramp) // 256, len(ramp) - 1)] for v in range(0, 256, 2)
        )
        out.write(f"{name:>9}: {bar * 2}\n")
    out.write("\n")

    if _pillow_available():
        _demo_image(out, width)


def _pillow_available() -> bool:
    try:
        from . import imaging

        return imaging.PIL_AVAILABLE
    except Exception:  # pragma: no cover
        return False


def _demo_image(out: io.TextIOBase, width: int) -> None:
    from . import imaging, render

    out.write("image -> half-blocks (double vertical resolution):\n\n")
    img = _synthetic_scene()
    grid = imaging.to_grid(img, width - 10, 1.0)
    pixels = imaging.pixel_grid_gray(grid)
    out.write("\n".join(render.to_blocks_mono(pixels)) + "\n\n")

    out.write("image -> braille (2x4 dots per cell):\n\n")
    grid = imaging.to_grid(img.convert("L"), width - 10, 1.0)
    pixels = imaging.pixel_grid_gray(grid)
    out.write("\n".join(render.to_braille(pixels, threshold=0.45)) + "\n\n")


def _synthetic_scene():
    """A deterministic gradient-with-shapes scene, so the demo needs no assets."""
    from PIL import Image, ImageDraw

    w, h = 240, 120
    img = Image.new("L", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            base = 30 + int(120 * (y / h))
            glow = max(0, 140 - int(((x - 170) ** 2 + (y - 30) ** 2) ** 0.5) * 2)
            px[x, y] = min(255, base + glow)
    draw = ImageDraw.Draw(img)
    draw.polygon([(0, h), (w // 3, h // 2.4), (w // 1.6, h), ], fill=12)
    draw.polygon([(w // 2.6, h), (w // 1.9, h // 1.9), (w, int(h * 0.82)), (w, h)],
                 fill=0)
    draw.ellipse((158, 18, 182, 42), fill=235)
    return img
