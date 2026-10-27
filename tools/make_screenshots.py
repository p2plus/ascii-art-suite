#!/usr/bin/env python3
"""Render the README screenshots (terminal-window PNGs) from real CLI output.

Run from the repository root:  python3 tools/make_screenshots.py
Shares the terminal renderer with tools/make_gif.py for a consistent look.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from make_gif import (  # noqa: E402
    ANSI_RE,
    MARGIN_X,
    MARGIN_Y,
    TITLE_H,
    Terminal,
    capture,
    load_font,
)

OUT = ROOT / "docs" / "screenshots"


def visible_len(line: str) -> int:
    return len(ANSI_RE.sub("", line))


def screenshot(path: Path, command: str, output_lines: list[str],
               font_size: int, line_h: int, bottom: int = 26) -> None:
    font = load_font(font_size)
    cols = max(visible_len(line) for line in output_lines)
    width = round(2 * MARGIN_X + cols * font.getlength("M")) + 16
    n_lines = 1 + len(output_lines)
    height = TITLE_H + MARGIN_Y + n_lines * line_h + bottom
    term = Terminal(font, width=width, height=height, title="asciiart", line_h=line_h)
    term.add_prompt(command)
    for line in output_lines:
        term.add_ansi(line)
    image = term.render()
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    print(f"{path.relative_to(ROOT)}: {path.stat().st_size // 1024} KB, "
          f"{image.size[0]}x{image.size[1]}, {cols} cols visible")


def main() -> None:
    screenshot(
        OUT / "valley-blocks-color.png",
        "asciiart image examples/valley.png -w 80 --format blocks --color 24bit",
        capture(["image", "examples/valley.png", "-w", "80",
                 "--format", "blocks", "--color", "24bit"]),
        font_size=13,
        line_h=18,
    )
    screenshot(
        OUT / "braille-42.png",
        "asciiart image examples/digits.png -w 48 --format braille --threshold 0.45",
        capture(["image", "examples/digits.png", "-w", "48",
                 "--format", "braille", "--threshold", "0.45"]),
        font_size=15,
        line_h=21,
    )


if __name__ == "__main__":
    main()
