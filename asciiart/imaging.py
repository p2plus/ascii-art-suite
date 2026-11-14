"""Image loading and tone preparation on top of Pillow (optional dependency).

The text engine has no dependencies; converting images requires Pillow.
"""
from __future__ import annotations

import io
import os
from typing import Callable

try:
    from PIL import Image, ImageOps
    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without Pillow
    Image = None
    ImageOps = None
    PIL_AVAILABLE = False


def require_pillow() -> None:
    if not PIL_AVAILABLE:
        raise RuntimeError(
            "image conversion requires Pillow; install it with: pip install pillow"
        )


def load_image(source: str | bytes, background: str = "#000000") -> "Image.Image":
    """Load a path or raw bytes and composite alpha onto *background*."""
    require_pillow()
    if isinstance(source, bytes):
        img = Image.open(io.BytesIO(source))
    elif source == "-":
        img = Image.open(io.BytesIO(sys_stdin_bytes()))
    else:
        if not os.path.isfile(source):
            raise FileNotFoundError(f"no such file: {source}")
        img = Image.open(source)
    img.load()
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        base = Image.new("RGBA", rgba.size, _parse_hex(background))
        base.alpha_composite(rgba)
        img = base
    return img.convert("RGB")


def sys_stdin_bytes() -> bytes:
    import sys

    data = sys.stdin.buffer.read()
    if not data:
        raise ValueError("no image data on stdin")
    return data


def _parse_hex(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        raise ValueError(f"invalid color: {color!r} (expected #rrggbb)")
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError as exc:
        raise ValueError(f"invalid color: {color!r} (expected #rrggbb)") from exc


def to_grid(
    img: "Image.Image",
    cols: int,
    aspect: float = 0.5,
    rows: int | None = None,
) -> "Image.Image":
    """Resize to a character grid; *aspect* compensates tall terminal cells."""
    if cols < 1:
        raise ValueError("width must be at least 1 column")
    w, h = img.size
    if rows is None:
        rows = max(1, round(cols * h / w * aspect)) if w else 1
    return img.resize((cols, rows), Image.Resampling.LANCZOS)  # type: ignore[attr-defined]


def _lut_for(img: "Image.Image", make: "Callable[[int], int]") -> list[int]:
    """256-entry LUT, repeated per band so multiband point() accepts it."""
    lut = [make(v) for v in range(256)]
    return lut * len(img.getbands()) if len(img.getbands()) > 1 else lut


def adjust_tone(
    gray: "Image.Image",
    brightness: float = 1.0,
    contrast: float = 1.0,
    gamma: float = 1.0,
    invert: bool = False,
    auto_levels: bool = False,
) -> "Image.Image":
    """Apply tone controls to an image (L or RGB), in a sensible order.

    Point LUTs apply equally to every band, so RGB survives intact; only
    auto-levels needs band separation (per-channel histogram stretch).
    """
    out = gray
    if auto_levels:
        if out.mode == "RGB":
            out = Image.merge("RGB", [ImageOps.autocontrast(band, cutoff=2)
                                      for band in out.split()])
        else:
            out = ImageOps.autocontrast(out, cutoff=2)
    if brightness != 1.0:
        out = out.point(_lut_for(out, lambda v: min(255, max(0, round(v * brightness)))))
    if contrast != 1.0:
        out = out.point(_lut_for(out, lambda v: min(255, max(0, round((v - 128) * contrast + 128)))))
    if gamma != 1.0:
        # Exponent > 1 darkens midtones, matching e.g. ImageMagick -gamma.
        out = out.point(_lut_for(out, lambda v: round(255 * ((v / 255) ** gamma))))
    if invert:
        out = ImageOps.invert(out)
    return out


def pixel_grid_gray(img: "Image.Image") -> list[list[int]]:
    if img.mode != "L":
        img = img.convert("L")
    raw = img.tobytes()
    w = img.width
    return [list(raw[y * w : (y + 1) * w]) for y in range(img.height)]


def pixel_grid_rgb(img: "Image.Image") -> list[list[tuple[int, int, int]]]:
    if img.mode != "RGB":
        img = img.convert("RGB")
    raw = img.tobytes()
    w = img.width
    return [
        [tuple(raw[(y * w + x) * 3 : (y * w + x) * 3 + 3]) for x in range(w)]
        for y in range(img.height)
    ]
