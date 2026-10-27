"""Command line interface: ``asciiart <image|text|fonts|demo>``."""
from __future__ import annotations

import argparse
import io
import os
import shutil
import sys
import time
from pathlib import Path

from . import __version__
from .charsets import CHARSETS, resolve as resolve_charset
from .figlet import FontError, list_fonts, load_font

PROGRAM = "asciiart"

EXAMPLES = """\
examples:
  asciiart text "hello world" -f slant
  asciiart text RIDICULOUS --random
  echo "banner from stdin" | asciiart text - -f mini
  asciiart image photo.jpg -w 100
  asciiart image photo.jpg --format blocks --color 24bit
  asciiart image diagram.png --format braille --threshold 0.4
  asciiart fonts -v
"""


def _auto_width() -> int:
    if sys.stdout.isatty():
        size = shutil.get_terminal_size(fallback=(80, 24))
        if size.columns > 0:
            return size.columns
    return 80


def _color_depth(requested: str) -> str | None:
    """Resolve --color to '24bit'/'8bit'/None, honouring auto and NO_COLOR."""
    if os.environ.get("NO_COLOR"):
        return None
    if requested == "auto":
        return "24bit" if sys.stdout.isatty() else None
    return None if requested == "none" else requested


def _pick_random(names: list[str], seed: int | None) -> str:
    """Deterministic xorshift pick; seeded with the clock when no seed is given."""
    state = (seed if seed is not None else time.time_ns()) & 0xFFFFFFFF or 1
    for _ in range(4):
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
    return names[state % len(names)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Convert images to ASCII art and text to FIGlet banners.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"{PROGRAM} {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    image = sub.add_parser("image", help="convert an image to terminal art")
    image.add_argument("input", help="image file, or - to read from stdin")
    image.add_argument("-w", "--width", type=int, default=None,
                       help="output columns (default: terminal width or 80)")
    image.add_argument("--format", choices=("ascii", "blocks", "braille"),
                       default="ascii", help="output renderer (default: ascii)")
    image.add_argument("-c", "--charset", default="standard",
                       help=f"named ramp or custom characters for --format ascii "
                            f"(one of: {', '.join(CHARSETS)})")
    image.add_argument("--aspect", type=float, default=None, metavar="F",
                       help="pixel rows per column; corrects for terminal cell "
                            "shape. Default depends on --format: 0.5 for ascii, "
                            "1.0 for blocks and braille")
    image.add_argument("--color", choices=("auto", "none", "24bit", "8bit"),
                       default="auto", help="ANSI color depth (default: auto)")
    image.add_argument("-i", "--invert", action="store_true",
                       help="flip light and dark")
    image.add_argument("--brightness", type=float, default=1.0, metavar="F",
                       help="brightness multiplier (default: 1.0)")
    image.add_argument("--contrast", type=float, default=1.0, metavar="F",
                       help="contrast multiplier (default: 1.0)")
    image.add_argument("--gamma", type=float, default=1.0, metavar="F",
                       help="gamma correction (default: 1.0)")
    image.add_argument("--auto-levels", action="store_true",
                       help="stretch the histogram before converting")
    image.add_argument("--threshold", type=float, default=0.5, metavar="F",
                       help="braille dot threshold in 0..1 (default: 0.5)")
    image.add_argument("--dither", action="store_true",
                       help="Floyd-Steinberg dithering for braille output")
    image.add_argument("--bg", default="#000000", metavar="COLOR",
                       help="background for transparent images (default: #000000)")
    image.add_argument("-o", "--out", default=None, metavar="FILE",
                       help="write to FILE instead of stdout")
    image.set_defaults(func=cmd_image)

    text = sub.add_parser("text", help="render text in FIGlet fonts")
    text.add_argument("input", nargs="?", default=None,
                      help="text to render, or - for stdin (default: -)")
    text.add_argument("-f", "--font", default="standard",
                      help="font name or path to an .flf file (default: standard)")
    text.add_argument("--random", action="store_true",
                      help="pick a random font (see also --seed)")
    text.add_argument("--seed", type=int, default=None, metavar="N",
                      help="seed for --random")
    text.add_argument("-w", "--width", type=int, default=None,
                      help="wrap width in columns (default: terminal width or 80)")
    text.add_argument("-j", "--justify", choices=("left", "center", "right"),
                      default="left", help="alignment within the wrap width")
    text.add_argument("--direction", choices=("auto", "ltr", "rtl"), default="auto",
                      help="override the font's print direction")
    text.add_argument("-o", "--out", default=None, metavar="FILE",
                      help="write to FILE instead of stdout")
    text.set_defaults(func=cmd_text)

    fonts = sub.add_parser("fonts", help="list available fonts and their sources")
    fonts.add_argument("-v", "--verbose", action="store_true",
                       help="also show font file paths")
    fonts.set_defaults(func=cmd_fonts)

    demo = sub.add_parser("demo", help="print a quick tour of the suite")
    demo.add_argument("--seed", type=int, default=7, metavar="N",
                      help="seed for random font picks")
    demo.set_defaults(func=cmd_demo)

    return parser


# ------------------------------------------------------------------ commands

def cmd_image(args: argparse.Namespace, out: io.TextIOBase) -> None:
    from . import imaging, render

    try:
        imaging.require_pillow()
        img = imaging.load_image(args.input, background=args.bg)
    except (RuntimeError, FileNotFoundError, ValueError, OSError) as exc:
        raise CliError(str(exc))
    cols = args.width if args.width else _auto_width()
    if cols < 1:
        raise CliError("width must be at least 1 column")
    if args.aspect is None:
        aspect = 0.5 if args.format == "ascii" else 1.0
    else:
        aspect = args.aspect
    try:
        if args.format == "braille":
            # two grid columns per braille character: -w is terminal columns
            grid = imaging.to_grid(img.convert("L"), cols * 2, aspect)
            grid = imaging.adjust_tone(
                grid, args.brightness, args.contrast, args.gamma,
                args.invert, args.auto_levels,
            )
            pixels = imaging.pixel_grid_gray(grid)
            lines = render.to_braille(
                pixels, threshold=args.threshold, invert=False, dither=args.dither
            )
        elif args.format == "blocks":
            depth = _color_depth(args.color)
            grid = imaging.to_grid(img, cols, aspect)
            grid = imaging.adjust_tone(
                grid.convert("L"), args.brightness, args.contrast, args.gamma,
                args.invert, args.auto_levels,
            )
            if depth:
                rgb = grid.convert("RGB")
                pixels = imaging.pixel_grid_rgb(rgb)
                lines = render.to_blocks_color(pixels, depth=depth)
            else:
                pixels = imaging.pixel_grid_gray(grid)
                lines = render.to_blocks_mono(pixels)
        else:
            ramp = resolve_charset(args.charset)
            grid = imaging.to_grid(img.convert("L"), cols, aspect)
            grid = imaging.adjust_tone(
                grid, args.brightness, args.contrast, args.gamma,
                args.invert, args.auto_levels,
            )
            pixels = imaging.pixel_grid_gray(grid)
            lines = render.to_ascii(pixels, ramp)
    except ValueError as exc:
        raise CliError(str(exc))
    out.write("\n".join(lines) + "\n")


def cmd_text(args: argparse.Namespace, out: io.TextIOBase) -> None:
    try:
        if args.random:
            names = sorted(list_fonts())
            if not names:
                raise CliError("no fonts found")
            args.font = _pick_random(names, args.seed)
        if args.input in (None, "-"):
            text = sys.stdin.read()
        else:
            text = args.input
        width = args.width if args.width else _auto_width()
        font = load_font(args.font)
        result = font.render(
            text.rstrip("\n"), width=width,
            justify=args.justify, direction=args.direction,
        )
    except FontError as exc:
        raise CliError(str(exc))
    out.write(result + "\n")


def cmd_fonts(args: argparse.Namespace, out: io.TextIOBase) -> None:
    fonts = list_fonts()
    if not fonts:
        raise CliError("no fonts found; set ASCIIART_FONTPATH or see asciiart fonts -h")
    name_w = max(len(ref.name) for ref in fonts.values())
    for ref in fonts.values():
        row = f"{ref.name:<{name_w}}  {ref.height:>2} rows  {ref.source:<8}"
        if args.verbose:
            row += f"  {ref.path}"
        out.write(row + "\n")


def cmd_demo(args: argparse.Namespace, out: io.TextIOBase) -> None:
    from .demo import print_demo

    print_demo(out=out, seed=args.seed)


# ------------------------------------------------------------------ plumbing

class CliError(Exception):
    """User-facing failure; message is printed to stderr."""


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    target = getattr(args, "out", None)
    if target:
        buffer = io.StringIO()
        code = _dispatch(args, buffer)
        if code:
            return code
        path = Path(target).expanduser()
        try:
            path.write_text(buffer.getvalue(), encoding="utf-8")
        except OSError as exc:
            print(f"{PROGRAM}: error: cannot write {target}: {exc}", file=sys.stderr)
            return 1
        return 0
    return _dispatch(args, sys.stdout)


def _dispatch(args: argparse.Namespace, out: io.TextIOBase) -> int:
    try:
        args.func(args, out)
    except CliError as exc:
        print(f"{PROGRAM}: error: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
