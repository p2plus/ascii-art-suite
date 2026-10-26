"""Image loading and tone preparation on top of Pillow (optional dependency).

The text engine has no dependencies; converting images requires Pillow.
"""
from __future__ import annotations

import io
import os

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


def adjust_tone(
    gray: "Image.Image",
    brightness: float = 1.0,
    contrast: float = 1.0,
    gamma: float = 1.0,
    invert: bool = False,
    auto_levels: bool = False,
) -> "Image.Image":
    """Apply tone controls to an L-mode image, in a sensible order."""
    out = gray
    if auto_levels:
        out = ImageOps.autocontrast(out, cutoff=2)
    if brightness != 1.0:
        lut = [min(255, max(0, round(v * brightness))) for v in range(256)]
        out = out.point(lut)
    if contrast != 1.0:
        lut = [min(255, max(0, round((v - 128) * contrast + 128))) for v in range(256)]
        out = out.point(lut)
    if gamma != 1.0:
        # Exponent > 1 darkens midtones, matching e.g. ImageMagick -gamma.
        lut = [round(255 * ((v / 255) ** gamma)) for v in range(256)]
        out = out.point(lut)
    if invert:
        out = ImageOps.invert(out)
    return out


def pixel_grid_gray(img: "Image.Image") -> list[list[int]]:
    data = list(img.getdata())
    return [data[y * img.width : (y + 1) * img.width] for y in range(img.height)]


def pixel_grid_rgb(img: "Image.Image") -> list[list[tuple[int, int, int]]]:
    data = list(img.getdata())
    return [data[y * img.width : (y + 1) * img.width] for y in range(img.height)]
