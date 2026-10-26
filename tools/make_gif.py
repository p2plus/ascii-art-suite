#!/usr/bin/env python3
"""Regenerate demo/demo.gif: a scripted terminal session showing the suite.

Run from the repository root:  python3 tools/make_gif.py
Requires Pillow. All command output shown is produced by the real CLI code
paths, then replayed against a rendered terminal window.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from asciiart import cli  # noqa: E402

OUT_PATH = ROOT / "demo" / "demo.gif"

# window chrome
PAGE_BG = (9, 12, 16)
WIN_BG = (13, 17, 23)
TITLE_BG = (22, 27, 34)
BORDER = (48, 54, 61)
DOTS = ((61, 68, 77),) * 3
TEXT = (230, 237, 243)
DIM = (139, 148, 158)
PROMPT = (63, 185, 80)
CMD = (230, 237, 243)

WIDTH, HEIGHT = 880, 600
MARGIN_X, MARGIN_Y = 26, 52
TITLE_H = 40
FONT_SIZE = 15
LINE_H = 21

FONT_CANDIDATES = (
    "/System/Library/Fonts/SFNSMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
    "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
)

ANSI_RE = re.compile(r"\x1b\[([0-9;]*)m")


def load_font() -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(path, FONT_SIZE)
        except OSError:
            continue
        probes = "▀▄█⠀⢀⣿"
        if all(font.getmask(ch).getbbox() for ch in probes):
            return font
    raise SystemExit("no system monospace font with block/braille coverage found")


def capture(argv: list[str]) -> list[str]:
    """Run the real CLI and return its stdout lines (ANSI sequences kept)."""
    buffer = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(buffer):
        cli.main(argv)
    return buffer.getvalue().rstrip("\n").split("\n")


# ---------------------------------------------------------------- terminal ui

class Terminal:
    def __init__(self, font: ImageFont.FreeTypeFont):
        self.font = font
        self.advance = font.getlength("M")
        self.cols = int((WIDTH - 2 * MARGIN_X) / self.advance)
        self.rows = (HEIGHT - MARGIN_Y - TITLE_H - MARGIN_Y) // LINE_H + 1
        self.lines: list[list[tuple[str, tuple, tuple]]] = []

    def clear(self) -> None:
        self.lines = []

    def add_raw(self, text: str, fg: tuple = CMD, bg: tuple = WIN_BG) -> None:
        self.lines.append([(ch, fg, bg) for ch in text])

    def add_ansi(self, line: str) -> None:
        cells: list[tuple[str, tuple, tuple]] = []
        fg, bg = TEXT, WIN_BG
        pos = 0
        for match in ANSI_RE.finditer(line):
            for ch in line[pos : match.start()]:
                cells.append((ch, fg, bg))
            params = match.group(1).split(";")
            if params in (["0"], [""]):
                fg, bg = TEXT, WIN_BG
            elif params[0] == "38" and params[1] == "2":
                fg = tuple(int(p) for p in params[2:5])
            elif params[0] == "48" and params[1] == "2":
                bg = tuple(int(p) for p in params[2:5])
            pos = match.end()
        for ch in line[pos:]:
            cells.append((ch, fg, bg))
        self.lines.append(cells)

    def render(self, cursor: tuple[int, int] | None = None) -> Image.Image:
        img = Image.new("RGB", (WIDTH, HEIGHT), PAGE_BG)
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), fill=PAGE_BG)
        # window with a soft border
        draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), fill=WIN_BG, outline=BORDER, width=1)
        draw.rectangle((0, 0, WIDTH - 1, TITLE_H), fill=TITLE_BG)
        for i, color in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
            x = 18 + i * 24
            draw.ellipse((x, TITLE_H // 2 - 6, x + 12, TITLE_H // 2 + 6), fill=color)
        title = "zsh - 80x24"
        tw = draw.textlength(title, font=self.font)
        draw.text(((WIDTH - tw) / 2, (TITLE_H - FONT_SIZE) / 2 - 2), title,
                  font=self.font, fill=DIM)
        visible = self.lines[-(self.rows - 1):]
        y = TITLE_H + MARGIN_Y
        for line in visible:
            x = MARGIN_X
            for ch, fg, bg in line:
                cw = self.advance
                if ch == "▀":
                    draw.rectangle((x, y, x + cw, y + LINE_H // 2), fill=fg)
                    draw.rectangle((x, y + LINE_H // 2, x + cw, y + LINE_H), fill=bg)
                elif bg != WIN_BG:
                    draw.rectangle((x, y, x + cw, y + LINE_H), fill=bg)
                    if ch != "▀":
                        draw.text((x, y), ch, font=self.font, fill=fg)
                elif ch != " ":
                    draw.text((x, y), ch, font=self.font, fill=fg)
                x += cw
            y += LINE_H
        if cursor is not None:
            cx, cy = cursor
            px = MARGIN_X + cx * self.advance
            py = TITLE_H + MARGIN_Y + cy * LINE_H
            draw.rectangle((px, py, px + self.advance - 2, py + LINE_H), fill=TEXT)
        return img


# ------------------------------------------------------------------- scenes

def build_frames(term: Terminal) -> list[Image.Image]:
    frames: list[Image.Image] = []
    fps_pause = 26

    def hold(n: int):
        for i in range(n):
            frames.append(term.render(cursor=None if i % 14 >= 7 else last_cursor()))

    def last_cursor():
        row = min(len(term.lines), term.rows - 2)
        col = len(term.lines[-1]) if term.lines else 0
        return (min(col, term.cols - 2), row)

    def type_command(command: str):
        prompt = [("$", PROMPT, WIN_BG), (" ", WIN_BG, WIN_BG)]
        for i in range(len(command) + 1):
            line = prompt + [(c, CMD, WIN_BG) for c in command[:i]]
            if term.lines and term.lines[-1][:1] == prompt[:1]:
                term.lines[-1] = line
            else:
                term.lines.append(line)
            frames.append(term.render(cursor=(len(line), len(term.lines) - 1)))

    def show_output(lines: list[str], ansi: bool = False, per_frame: int = 3):
        for start in range(0, len(lines), per_frame):
            for line in lines[start : start + per_frame]:
                (term.add_ansi if ansi else term.add_raw)(line)
            frames.append(term.render())

    def run_scene(command: str, output: list[str], ansi: bool = False,
                  hold_frames: int = fps_pause, per_frame: int = 3):
        type_command(command)
        show_output(output, ansi=ansi, per_frame=per_frame)
        hold(hold_frames)
        term.clear()
        frames.append(term.render())

    run_scene(
        'asciiart text "asciiart" -f standard',
        capture(["text", "asciiart", "-f", "standard"]),
    )
    run_scene(
        'asciiart text "any figlet font" -f doom',
        capture(["text", "any figlet font", "-f", "doom"]),
    )
    run_scene(
        'asciiart image examples/valley.png -w 74 --auto-levels',
        capture(["image", "examples/valley.png", "-w", "74", "--auto-levels"]),
    )
    run_scene(
        'asciiart image examples/valley.png -w 74 --format blocks --color 24bit',
        capture(["image", "examples/valley.png", "-w", "74",
                 "--format", "blocks", "--color", "24bit"]),
        ansi=True,
    )
    run_scene(
        'asciiart image examples/digits.png -w 54 --format braille',
        capture(["image", "examples/digits.png", "-w", "54", "--format", "braille"]),
        hold_frames=34,
    )
    run_scene(
        'asciiart fonts',
        capture(["fonts"])[:12],
        hold_frames=30,
        per_frame=12,
    )
    # closing prompt
    term.lines.append([("$", PROMPT, WIN_BG), (" ", WIN_BG, WIN_BG)])
    for i in range(30):
        frames.append(term.render(cursor=None if i % 12 >= 6 else (2, len(term.lines) - 1)))
    return frames


def main() -> None:
    font = load_font()
    term = Terminal(font)
    frames = build_frames(term)
    OUT_PATH.parent.mkdir(exist_ok=True)
    pal_frames = [f.quantize(colors=256, method=Image.MEDIANCUT, dither=0) for f in frames]
    pal_frames[0].save(
        OUT_PATH,
        save_all=True,
        append_images=pal_frames[1:],
        duration=50,
        loop=0,
        optimize=True,
    )
    size = OUT_PATH.stat().st_size
    print(f"{OUT_PATH}: {len(frames)} frames, {size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
