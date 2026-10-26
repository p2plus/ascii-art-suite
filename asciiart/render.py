"""Output renderers: plain ASCII ramps, ANSI half-blocks and Unicode braille.

All renderers consume grayscale (or RGB) pixel grids and return plain lines
of text. Color is emitted as ANSI escape sequences and only used where a
renderer supports it.
"""
from __future__ import annotations

from typing import Sequence

BRAILLE_OFFSET = 0x2800
_BRAILLE_BITS = (
    (0x01, 0x08),
    (0x02, 0x10),
    (0x04, 0x20),
    (0x40, 0x80),
)

# xterm 256-color palette: 16 primaries, 6x6x6 cube, 24 grayscale steps.
_CUBE = (0, 95, 135, 175, 215, 255)
_PALETTE: tuple[tuple[int, int, int], ...] | None = None


def _palette() -> tuple[tuple[int, int, int], ...]:
    global _PALETTE
    if _PALETTE is None:
        colors = [(0, 0, 0)] * 256
        for r in range(6):
            for g in range(6):
                for b in range(6):
                    colors[16 + 36 * r + 6 * g + b] = (_CUBE[r], _CUBE[g], _CUBE[b])
        for i in range(24):
            v = 8 + 10 * i
            colors[232 + i] = (v, v, v)
        _PALETTE = tuple(colors)
    return _PALETTE


def quantize_256(r: int, g: int, b: int) -> int:
    """Nearest xterm-256 color index for an RGB triple.

    Indices 0-15 are the terminal-configurable ANSI primaries and are
    deliberately skipped; the 6x6x6 cube (16-231) and the gray ramp
    (232-255) have defined colors.
    """
    palette = _palette()
    best, best_dist = 16, 1 << 30
    for index in range(16, 256):
        pr, pg, pb = palette[index]
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if d < best_dist:
            best, best_dist = index, d
    return best


def fg_24bit(r: int, g: int, b: int) -> str:
    return f"\x1b[38;2;{r};{g};{b}m"


def bg_24bit(r: int, g: int, b: int) -> str:
    return f"\x1b[48;2;{r};{g};{b}m"


def fg_8bit(code: int) -> str:
    return f"\x1b[38;5;{code}m"


def bg_8bit(code: int) -> str:
    return f"\x1b[48;5;{code}m"


RESET = "\x1b[0m"


# ---------------------------------------------------------------- ramps

def to_ascii(gray: Sequence[Sequence[int]], ramp: str, invert: bool = False) -> list[str]:
    """Map an 8-bit grayscale grid onto a character ramp."""
    chars = ramp[::-1] if invert else ramp
    span = len(chars)
    lines = []
    for row in gray:
        line = "".join(chars[min(value * span // 256, span - 1)] for value in row)
        lines.append(line)
    return lines


# ---------------------------------------------------------------- half blocks

def to_blocks_mono(gray: Sequence[Sequence[int]], invert: bool = False) -> list[str]:
    """Two pixel rows per terminal row using space/▀/▄/█."""
    lines = []
    for y in range(0, len(gray), 2):
        upper = gray[y]
        lower = gray[y + 1] if y + 1 < len(gray) else [0] * len(upper)
        chars = []
        for x in range(len(upper)):
            up = 255 - upper[x] if invert else upper[x]
            down = 255 - lower[x] if invert else lower[x]
            bit_up, bit_down = up >= 128, down >= 128
            if bit_up and bit_down:
                chars.append("█")
            elif bit_up:
                chars.append("▀")
            elif bit_down:
                chars.append("▄")
            else:
                chars.append(" ")
        lines.append("".join(chars))
    return lines


def to_blocks_color(
    rgb: Sequence[Sequence[Sequence[int]]],
    depth: str = "24bit",
    background: tuple[int, int, int] = (0, 0, 0),
) -> list[str]:
    """Truecolor/8-bit half-block rendering: fg = upper pixel, bg = lower."""
    lines = []
    for y in range(0, len(rgb), 2):
        upper = rgb[y]
        lower = rgb[y + 1] if y + 1 < len(rgb) else [background] * len(upper)
        parts = [RESET]
        for x in range(len(upper)):
            ur, ug, ub = upper[x]
            lr, lg, lb = lower[x]
            if depth == "8bit":
                parts.append(fg_8bit(quantize_256(ur, ug, ub)))
                parts.append(bg_8bit(quantize_256(lr, lg, lb)))
            else:
                parts.append(fg_24bit(ur, ug, ub))
                parts.append(bg_24bit(lr, lg, lb))
            parts.append("▀")
        parts.append(RESET)
        lines.append("".join(parts))
    return lines


# ---------------------------------------------------------------- braille

def to_braille(
    gray: Sequence[Sequence[int]],
    threshold: float = 0.5,
    invert: bool = False,
    dither: bool = False,
) -> list[str]:
    """2x4 dot cells; *threshold* in 0..1 of brightness."""
    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be strictly between 0 and 1")
    height = len(gray)
    width = max((len(row) for row in gray), default=0)
    if dither:
        buffer = [[float(v) for v in row] for row in gray]
    else:
        buffer = None
    lines = []
    for cy in range(0, height, 4):
        chars = []
        for cx in range(0, width, 2):
            code = 0
            for dy in range(4):
                for dx in range(2):
                    y, x = cy + dy, cx + dx
                    inside = y < height and x < len(gray[y])
                    if buffer is not None:
                        if not inside:
                            continue
                        value = buffer[y][x]
                        on = value >= threshold * 255
                        if invert:
                            on = not on
                        error = value - (255 if on else 0)
                        if on:
                            code |= _BRAILLE_BITS[dy][dx]
                        for ny, nx, w in (
                            (y, x + 1, 7 / 16),
                            (y + 1, x - 1, 3 / 16),
                            (y + 1, x, 5 / 16),
                            (y + 1, x + 1, 1 / 16),
                        ):
                            if ny < height and 0 <= nx < len(buffer[ny]):
                                buffer[ny][nx] += error * w
                    else:
                        if not inside:
                            continue
                        on = gray[y][x] >= threshold * 255
                        if invert:
                            on = not on
                        if on:
                            code |= _BRAILLE_BITS[dy][dx]
            chars.append(chr(BRAILLE_OFFSET + code))
        lines.append("".join(chars))
    return lines
