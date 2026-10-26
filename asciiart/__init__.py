"""asciiart - images and text as terminal art.

Text rendering is dependency-free and speaks the FIGfont format natively:
it uses the fonts of an existing figlet or pyfiglet installation when one is
present and falls back to the curated set bundled with this package.
Image conversion is available whenever Pillow is installed.

Library quick start::

    from asciiart import render_text
    print(render_text("hello", font="slant"))

    from asciiart import image_to_ascii
    print(image_to_ascii("photo.jpg", width=80))
"""
from __future__ import annotations

__version__ = "1.0.0"

from .charsets import CHARSETS
from .figlet import FigFont, FontError, list_fonts, load_font, render_text
from .figlet import SM_EQUAL, SM_HIERARCHY, SM_KERN, SM_LOWLINE, SM_PAIR, SM_BIGX, SM_HARDBLANK, SM_SMUSH

__all__ = [
    "CHARSETS",
    "FigFont",
    "FontError",
    "SM_BIGX",
    "SM_EQUAL",
    "SM_HARDBLANK",
    "SM_HIERARCHY",
    "SM_KERN",
    "SM_LOWLINE",
    "SM_PAIR",
    "SM_SMUSH",
    "__version__",
    "image_to_ascii",
    "list_fonts",
    "load_font",
    "render_text",
]


def image_to_ascii(
    source,
    width: int = 80,
    charset: str = "standard",
    aspect: float = 0.5,
    invert: bool = False,
) -> str:
    """Render *source* (path or bytes) as ASCII art using *charset*."""
    from . import imaging, render
    from .charsets import resolve as resolve_charset

    ramp = resolve_charset(charset)
    img = imaging.load_image(source).convert("L")
    grid = imaging.to_grid(img, width, aspect)
    pixels = imaging.pixel_grid_gray(grid)
    return "\n".join(render.to_ascii(pixels, ramp, invert=invert))
