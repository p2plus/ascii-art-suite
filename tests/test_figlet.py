import unittest

from asciiart.figlet import (
    SM_KERN,
    SM_SMUSH,
    FigFont,
    FontError,
    list_fonts,
    load_font,
)

BUNDLED = sorted(list_fonts())


class TestHeaderParsing(unittest.TestCase):
    def setUp(self):
        self.font = load_font("standard")

    def test_header_fields(self):
        self.assertEqual(self.font.height, 6)
        self.assertEqual(self.font.baseline, 5)
        self.assertEqual(self.font.hardblank, "$")

    def test_smushmode_from_full_layout(self):
        # Standard.flf: full layout 24463 -> horizontal bits 143
        # (smushing with rules 1-4)
        self.assertEqual(self.font.smushmode, 143)

    def test_glyph_inventory(self):
        for code in range(32, 127):
            self.assertIn(code, self.font.glyphs)
        for code in (196, 214, 220, 228, 246, 223):
            self.assertIn(code, self.font.glyphs)

    def test_malformed_header(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.flf"
            bad.write_text("not a font\n")
            with self.assertRaises(FontError):
                FigFont(bad)


class TestRendering(unittest.TestCase):
    def test_known_output(self):
        # Lines are right-trimmed; blank trailing glyph rows are dropped.
        out = load_font("standard").render("Hello")
        self.assertEqual(
            out,
            "\n".join([
                " _   _      _ _",
                "| | | | ___| | | ___",
                "| |_| |/ _ \\ | |/ _ \\",
                "|  _  |  __/ | | (_) |",
                "|_| |_|\\___|_|_|\\___/",
            ]),
        )

    def test_line_count_within_height(self):
        for name in ("standard", "mini", "slant", "doom"):
            font = load_font(name)
            out = font.render("Xy")
            self.assertGreaterEqual(len(out.splitlines()), 1, name)
            self.assertLessEqual(len(out.splitlines()), font.height, name)

    def test_hardblank_never_leaks(self):
        for name in ("standard", "shadow", "epic", "graffiti"):
            font = load_font(name)
            out = font.render("Hard Blank Test")
            self.assertNotIn(font.hardblank, out)

    def test_layout_order_full_kern_smush(self):
        font = load_font("standard")
        full = font.render("HHHH", width=400, smushmode=0)
        kern = font.render("HHHH", width=400, smushmode=SM_KERN)
        smush = font.render("HHHH", width=400, smushmode=SM_KERN | SM_SMUSH | 15)
        widths = [len(lines.splitlines()[0]) for lines in (full, kern, smush)]
        self.assertGreaterEqual(widths[0], widths[1])
        self.assertGreaterEqual(widths[1], widths[2])
        self.assertGreater(widths[0], widths[2])

    def test_word_wrap_keeps_width_and_wraps(self):
        font = load_font("standard")
        out = font.render("alpha bravo charlie delta echo foxtrot", width=30)
        self.assertLessEqual(max(len(line) for line in out.splitlines()), 30)
        # wrapped into multiple figures separated by one blank line
        figures = out.split("\n\n")
        self.assertGreaterEqual(len(figures), 2)

    def test_explicit_newline(self):
        out = load_font("mini").render("ab\ncd", width=80)
        figures = out.split("\n\n")
        self.assertEqual(len(figures), 2)
        self.assertTrue(all(figure.strip() for figure in figures))

    def test_justify(self):
        font = load_font("mini")
        widths = []
        for justify in ("left", "center", "right"):
            out = font.render("hi", width=60, justify=justify)
            widths.append(max(len(line) for line in out.splitlines()))
        self.assertLess(widths[0], widths[1])
        self.assertLess(widths[1], widths[2])

    def test_unmapped_characters_are_dropped(self):
        out = load_font("standard").render("\x01")
        self.assertEqual(out, "")

    def test_rtl_renders(self):
        out = load_font("standard").render("abc", direction="rtl", width=120)
        self.assertTrue(out)

    def test_invalid_justify(self):
        with self.assertRaises(ValueError):
            load_font("standard").render("x", justify="diagonal")


class TestAllBundledFonts(unittest.TestCase):
    def test_every_font_renders_sample_text(self):
        failures = []
        for name in BUNDLED:
            try:
                font = load_font(name)
                out = font.render("Ascii 0123 Umlaut", width=70)
                self.assertTrue(out)
                self.assertLessEqual(
                    max(len(line) for line in out.splitlines()), 70, name
                )
                self.assertNotIn(font.hardblank, out, name)
            except Exception as exc:  # noqa: BLE001 - collect all failures
                failures.append(f"{name}: {exc!r}")
        self.assertEqual(failures, [])


class TestDiscovery(unittest.TestCase):
    def test_bundled_fonts_present(self):
        names = set(list_fonts())
        for expected in ("standard", "slant", "big", "mini", "doom", "starwars"):
            self.assertIn(expected, names)

    def test_bundled_source_label(self):
        refs = list_fonts()
        self.assertEqual(refs["standard"].source, "bundled")

    def test_case_insensitive_lookup(self):
        self.assertEqual(load_font("STANDARD").name, "Standard")

    def test_unknown_font_suggests_alternatives(self):
        with self.assertRaises(FontError) as ctx:
            load_font("standrd")
        self.assertIn("standard", str(ctx.exception))

    def test_load_by_path(self):
        from pathlib import Path

        path = Path(list_fonts()["mini"].path)
        font = load_font(str(path))
        self.assertEqual(font.name, "Mini")


if __name__ == "__main__":
    unittest.main()
