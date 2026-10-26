"""FIGlet font engine.

Parses FIGfont (.flf) files and renders text with the layout behaviour of
the reference C implementation (figlet.c 2.2.2): full-width, kerning and
controlled/universal smushing, including the six horizontal smushing rules.

Fonts are discovered from, in order: $ASCIIART_FONTPATH, the user directory
(~/.asciiart/fonts), an installed pyfiglet package, a system figlet
installation (queried via ``figlet -I2``), common system paths, and finally
the curated set bundled with this package. Existing installations always
win over the bundled pack.
"""
from __future__ import annotations

import difflib
import glob
import importlib.util
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

SM_EQUAL = 1
SM_LOWLINE = 2
SM_HIERARCHY = 4
SM_PAIR = 8
SM_BIGX = 16
SM_HARDBLANK = 32
SM_KERN = 64
SM_SMUSH = 128

HORIZONTAL_MASK = (
    SM_EQUAL | SM_LOWLINE | SM_HIERARCHY | SM_PAIR | SM_BIGX | SM_HARDBLANK
    | SM_KERN | SM_SMUSH
)

GERMAN_CODEPOINTS = (196, 214, 220, 228, 246, 252, 223)

_HEADER_RE = re.compile(
    r"^flf2a(?P<hardblank>.)\s+(?P<height>\d+)\s+(?P<baseline>\d+)\s+(?P<maxlen>\d+)\s+"
    r"(?P<old>-?\d+)\s+(?P<comments>\d+)(?:\s+(?P<direction>-?\d+)\s+(?P<full>\d+)"
    r"(?:\s+(?P<codetag>\d+))?)?\s*$"
)
_CONTROL_RE = re.compile(r"(?:\\[1-6])+$")
_CODETAG_RE = re.compile(r"^-?0x[0-9a-fA-F]+\s+(\d+)\s*$")


class FontError(Exception):
    """Raised when a font cannot be found or parsed."""


@dataclass(frozen=True)
class FontRef:
    name: str
    path: Path
    source: str

    @property
    def height(self) -> int:
        try:
            with open(self.path, "r", encoding="utf-8", errors="replace") as fh:
                match = _HEADER_RE.match(fh.readline().rstrip("\r\n"))
            if match:
                return int(match.group("height"))
        except OSError:
            pass
        return 0


class FigFont:
    """A parsed FIGfont file."""

    def __init__(self, path: str | os.PathLike[str], name: str | None = None):
        self.path = Path(path)
        self.name = name or self.path.stem
        try:
            raw = self.path.read_bytes()
        except OSError as exc:
            raise FontError(f"cannot read font file {self.path}: {exc}") from exc
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        # Split on \n only, like figlet.c: NEL/LS/PS bytes inside latin-1
        # fonts are glyph data, not line breaks (str.splitlines would break).
        self._parse(text.replace("\r\n", "\n").split("\n"))

    # ------------------------------------------------------------------ parse

    def _parse(self, lines: list[str]) -> None:
        if not lines:
            raise FontError(f"{self.path}: empty font file")
        header = _HEADER_RE.match(lines[0].rstrip("\r"))
        if header is None:
            raise FontError(f"{self.path}: malformed FIGfont header: {lines[0]!r}")
        self.hardblank = header.group("hardblank")
        self.height = int(header.group("height"))
        self.baseline = int(header.group("baseline"))
        self.old_layout = int(header.group("old"))
        has_full = header.group("full") is not None
        self.print_direction = int(header.group("direction") or 0)
        self.full_layout = int(header.group("full") or 0)
        self.comments = lines[1 : 1 + int(header.group("comments"))]
        self._lines = lines[1 + int(header.group("comments")) :]
        self.glyphs: dict[int, tuple[str, ...]] = {}
        self._parse_required_glyphs()
        self._parse_extended_glyphs()
        self.smushmode = self._resolve_smushmode(has_full)
        missing = [cp for cp in range(32, 127) if cp not in self.glyphs]
        if missing:
            raise FontError(
                f"{self.path}: missing {len(missing)} required ASCII glyphs"
            )

    def _read_glyph(self) -> tuple[str, ...] | None:
        rows: list[str] = []
        for _ in range(self.height):
            if not self._lines:
                if rows:
                    rows.extend([""] * (self.height - len(rows)))
                    break
                return None
            line = self._lines.pop(0).rstrip("\r")
            endmark = line[-1] if line else "@"
            if len(line) >= 2 and line[-2] == endmark:
                line = line[:-2]
            elif line:
                line = line[:-1]
            line = _CONTROL_RE.sub("", line)
            rows.append(line)
        if not rows:
            return None
        width = max(len(row) for row in rows)
        return tuple(row.ljust(width) for row in rows)

    def _parse_required_glyphs(self) -> None:
        codes = list(range(32, 127)) + list(GERMAN_CODEPOINTS)
        for code in codes:
            glyph = self._read_glyph()
            if glyph is None:
                break
            self.glyphs[code] = glyph

    def _parse_extended_glyphs(self) -> None:
        while self._lines:
            line = self._lines.pop(0).strip()
            if not line:
                continue
            match = _CODETAG_RE.match(line)
            if match is None:
                continue
            code = int(line.split()[0], 16)
            for _ in range(int(match.group(1))):
                if self._lines:
                    self._lines.pop(0)
            glyph = self._read_glyph()
            if glyph is not None and code >= 0:
                self.glyphs[code] = glyph

    def _resolve_smushmode(self, has_full: bool) -> int:
        if has_full:
            return self.full_layout & HORIZONTAL_MASK
        if self.old_layout == 0:
            return SM_KERN
        if self.old_layout < 0:
            return 0
        # Pre-2.2 fonts carry rule bits only, activated by smushing
        # (figlet.c readfont()).
        return (self.old_layout & 31) | SM_SMUSH

    # ----------------------------------------------------------------- render

    def render(
        self,
        text: str,
        width: int = 80,
        justify: str = "left",
        direction: str = "auto",
        smushmode: int | None = None,
    ) -> str:
        """Render *text* into a multi-line string, wrapping at *width*."""
        if justify not in ("left", "center", "right"):
            raise ValueError(f"justify must be left, center or right, not {justify!r}")
        rtl = direction == "rtl" or (direction == "auto" and self.print_direction == 1)
        if rtl:
            text = text[::-1]
        mode = self.smushmode if smushmode is None else smushmode & HORIZONTAL_MASK

        finished: list[str] = []
        rows: list[str] = []
        prev_width = 0
        word_start: tuple[list[str], int] | None = None
        word_chars: list[str] = []

        def flush(rows_: list[str]) -> None:
            if not any(row.strip() for row in rows_):
                return
            lines = [row.replace(self.hardblank, " ").rstrip() for row in rows_]
            while lines and lines[-1] == "":
                lines.pop()
            for row in lines:
                pad = max(width - len(row), 0)
                if justify == "center":
                    row = " " * (pad // 2) + row
                elif justify == "right":
                    row = " " * pad + row
                finished.append(row)
            finished.append("")

        def try_add(rows_: list[str], ch: str, prev_w: int) -> tuple[list[str] | None, int]:
            glyph = self.glyphs.get(ord(ch))
            if glyph is None:
                return list(rows_) or ["" for _ in range(self.height)], prev_w
            rows_ = list(rows_) or ["" for _ in range(self.height)]
            cur_w = len(glyph[0])
            line_len = len(rows_[0])
            amount = self._smushamt(rows_, glyph, cur_w, prev_w, mode)
            if line_len + cur_w - amount > width:
                return None, prev_w
            new_rows: list[str] = []
            for i in range(self.height):
                row, grow = rows_[i], glyph[i]
                out = list(row)
                for k in range(amount):
                    column = line_len - amount + k
                    if column < 0:
                        column = 0
                    left = out[column] if column < len(out) else " "
                    merged = self._smushem(left, grow[k], prev_w, cur_w, mode)
                    if merged:
                        if column < len(out):
                            out[column] = merged
                        else:
                            out.append(merged)
                new_rows.append("".join(out) + grow[amount:])
            return new_rows, cur_w

        for ch in text:
            if ch == "\n":
                flush(rows)
                rows, prev_width = [], 0
                word_start, word_chars = None, []
                continue
            if ch.isspace():
                if rows and word_chars:
                    word_start = (list(rows), prev_width)
                added, prev_width = try_add(rows, " ", prev_width)
                if added is None:
                    flush(rows)
                    rows, prev_width = [], 0
                    added, prev_width = try_add(rows, " ", 0)
                rows = added or ["" for _ in range(self.height)]
                word_chars = []
                continue
            added, new_prev = try_add(rows, ch, prev_width)
            if added is None and word_start is not None:
                # Overflow: retry the current word on a fresh line instead of
                # breaking it mid-glyph.
                snapshot, snap_prev = word_start
                flush(snapshot)
                rows, prev_width = list(snapshot), snap_prev
                word_start = None
                for c in word_chars:
                    added, prev_width = try_add(rows, c, prev_width)
                    if added is None:
                        flush(rows)
                        rows, prev_width = [], 0
                        added, prev_width = try_add(rows, c, 0)
                    rows = added or ["" for _ in range(self.height)]
                added, new_prev = try_add(rows, ch, prev_width)
            if added is not None:
                rows = added
                prev_width = new_prev
                word_chars.append(ch)
                continue
            flush(rows)
            rows, prev_width = [], 0
            added, prev_width = try_add(rows, ch, 0)
            rows = added or ["" for _ in range(self.height)]

        flush(rows)
        while finished and finished[-1] == "":
            finished.pop()
        return "\n".join(finished)

    # ------------------------------------------------------- smushing internals

    def _smushamt(
        self,
        rows: list[str],
        glyph: tuple[str, ...],
        cur_width: int,
        prev_width: int,
        mode: int,
    ) -> int:
        """Maximum columns *glyph* may shift left, ported from figlet.c smushamt()."""
        if not mode & (SM_KERN | SM_SMUSH):
            return 0
        max_smush = cur_width
        for i in range(self.height):
            row, grow = rows[i], glyph[i]
            line_bd, ch1 = self._last_visible(row)
            char_bd, ch2 = self._first_visible(grow)
            amt = char_bd + len(row) - 1 - line_bd
            if not ch1 or ch1 == " ":
                amt += 1
            elif ch2 and self._smushem(ch1, ch2, prev_width, cur_width, mode):
                amt += 1
            if amt < max_smush:
                max_smush = amt
        return max_smush

    @staticmethod
    def _last_visible(row: str) -> tuple[int, str]:
        i = len(row) - 1
        while i > 0 and row[i] == " ":
            i -= 1
        return i, row[i] if row else " "

    @staticmethod
    def _first_visible(row: str) -> tuple[int, str]:
        i = 0
        while i < len(row) and row[i] == " ":
            i += 1
        return i, row[i] if i < len(row) else ""

    def _smushem(
        self, lch: str, rch: str, prev_width: int, cur_width: int, mode: int
    ) -> str | None:
        """Merge two overlapping sub-characters; None if they cannot merge.

        Ported from figlet.c smushem(), including the six controlled rules.
        """
        hb = self.hardblank
        if lch == " ":
            return rch
        if rch == " ":
            return lch
        if prev_width < 2 or cur_width < 2:
            return None
        if not mode & SM_SMUSH:
            return None  # kerning only
        if not mode & 63:
            # Universal overlapping: later character wins, hardblanks lose.
            if lch == hb:
                return rch
            if rch == hb:
                return lch
            return rch
        if mode & SM_HARDBLANK and lch == hb and rch == hb:
            return lch
        if lch == hb or rch == hb:
            return None
        if mode & SM_EQUAL and lch == rch:
            return lch
        if mode & SM_LOWLINE:
            klass = "|/\\[]{}()<>"
            if lch == "_" and rch in klass:
                return rch
            if rch == "_" and lch in klass:
                return lch
        if mode & SM_HIERARCHY:
            for lower, higher in (
                ("|", "/\\[]{}()<>"),
                ("/\\", "[]{}()<>"),
                ("[]", "{}()<>"),
                ("{}", "()<>"),
                ("()", "<>"),
            ):
                if lch in lower and rch in higher:
                    return rch
                if rch in lower and lch in higher:
                    return lch
        if mode & SM_PAIR:
            for left, right in ("[]", "{}", "()"):
                if (lch == left and rch == right) or (lch == right and rch == left):
                    return "|"
        if mode & SM_BIGX:
            if lch == "/" and rch == "\\":
                return "|"
            if lch == "\\" and rch == "/":
                return "Y"
            if lch == ">" and rch == "<":
                return "X"
        return None

    def describe_layout(self) -> str:
        mode = self.smushmode
        if not mode & (SM_KERN | SM_SMUSH):
            return "full-width"
        if mode & SM_SMUSH:
            rules = mode & 63
            if rules == 0:
                return "universal smushing"
            return f"smushing ({bin(rules).count('1')} rules)"
        return "kerning"


# ------------------------------------------------------------------ discovery

_BUNDLED_DIR = Path(__file__).with_name("fonts")

_SYSTEM_DIRS = (
    "/usr/share/figlet",
    "/usr/share/figlet/fonts",
    "/usr/local/share/figlet",
    "/usr/local/share/figlet/fonts",
    "/opt/homebrew/share/figlet",
    "/opt/homebrew/share/figlet/fonts",
    "/opt/local/share/figlet",
    "C:/figlet/fonts",
)


def _pyfiglet_dir() -> Path | None:
    spec = importlib.util.find_spec("pyfiglet")
    if spec is None or not spec.origin:
        return None
    candidate = Path(spec.origin).parent / "fonts"
    return candidate if candidate.is_dir() else None


def _figlet_binary_dir() -> Path | None:
    if shutil.which("figlet") is None:
        return None
    try:
        result = subprocess.run(
            ["figlet", "-I2"],
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = result.stdout.strip()
    if not out:
        return None
    candidate = Path(out.splitlines()[-1])
    return candidate if candidate.is_dir() else None


def font_search_paths() -> list[tuple[Path, str]]:
    """Font directories in priority order (highest priority first)."""
    entries: list[tuple[Path, str]] = []
    env = os.environ.get("ASCIIART_FONTPATH")
    if env:
        for part in env.split(os.pathsep):
            if part:
                entries.append((Path(part), "env"))
    user = Path.home() / ".asciiart" / "fonts"
    if user.is_dir():
        entries.append((user, "user"))
    for finder, source in ((_pyfiglet_dir, "pyfiglet"), (_figlet_binary_dir, "figlet")):
        found = finder()
        if found:
            entries.append((found, source))
    for directory in _SYSTEM_DIRS:
        if Path(directory).is_dir():
            entries.append((Path(directory), "system"))
    entries.append((_BUNDLED_DIR, "bundled"))
    return entries


def list_fonts() -> dict[str, FontRef]:
    """All discoverable fonts keyed by lowercase name; higher priority wins."""
    fonts: dict[str, FontRef] = {}
    for directory, source in font_search_paths():
        for path in sorted(glob.glob(str(directory / "*.flf"))):
            ref = FontRef(Path(path).stem, Path(path), source)
            fonts.setdefault(ref.name.lower(), ref)
    return dict(sorted(fonts.items()))


_font_cache: dict[str, FigFont] = {}


def load_font(name: str = "standard") -> FigFont:
    """Load a font by name (case-insensitive) or by path to an .flf file."""
    key = name.lower()
    if key in _font_cache:
        return _font_cache[key]
    candidate = Path(name)
    if candidate.suffix.lower() == ".flf" and candidate.is_file():
        font = FigFont(candidate)
        _font_cache[key] = font
        return font
    fonts = list_fonts()
    ref = fonts.get(key)
    if ref is None:
        close = difflib.get_close_matches(key, fonts.keys(), n=3, cutoff=0.5)
        hint = f"; did you mean: {', '.join(sorted(close))}?" if close else ""
        known = ", ".join(sorted(fonts)) or "none found"
        raise FontError(f"unknown font {name!r}{hint}\navailable fonts: {known}")
    font = FigFont(ref.path, ref.name)
    _font_cache[key] = font
    return font


def render_text(
    text: str,
    font: str = "standard",
    width: int = 80,
    justify: str = "left",
    direction: str = "auto",
) -> str:
    """Convenience wrapper: render *text* with the named font."""
    return load_font(font).render(text, width=width, justify=justify, direction=direction)
