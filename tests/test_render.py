import unittest

from asciiart.render import (
    BRAILLE_OFFSET,
    quantize_256,
    to_ascii,
    to_blocks_color,
    to_blocks_mono,
    to_braille,
)

WHITE = [[255] * 4] * 4
BLACK = [[0] * 4] * 4


class TestAscii(unittest.TestCase):
    def test_black_is_first_ramp_char(self):
        self.assertEqual(to_ascii([[0]], " .:#"), [" "])

    def test_white_is_last_ramp_char(self):
        self.assertEqual(to_ascii([[255]], " .:#"), ["#"])

    def test_invert_flips_ends(self):
        self.assertEqual(to_ascii([[0]], " .:#", invert=True), ["#"])

    def test_uniform_row(self):
        out = to_ascii([[10, 200]] * 3, " .:#")
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0][0], " ")

    def test_clamps_out_of_range(self):
        # 300 is out of the 0..255 range but must not IndexError
        self.assertEqual(to_ascii([[300]], "@@"), ["@"])


class TestBlocksMono(unittest.TestCase):
    def test_all_white_is_solid(self):
        # 4 pixel rows -> 2 terminal rows
        self.assertEqual(to_blocks_mono(WHITE), ["████", "████"])

    def test_all_black_is_blank(self):
        self.assertEqual(to_blocks_mono(BLACK), ["    ", "    "])

    def test_upper_half(self):
        grid = [[255, 0, 255, 0], [0, 0, 0, 0]]
        self.assertEqual(to_blocks_mono(grid), ["▀ ▀ "])

    def test_lower_half(self):
        grid = [[0, 0, 0, 0], [255, 0, 255, 0]]
        self.assertEqual(to_blocks_mono(grid), ["▄ ▄ "])

    def test_odd_height_padded(self):
        grid = [[255, 255]]
        self.assertEqual(to_blocks_mono(grid), ["▀▀"])


class TestBlocksColor(unittest.TestCase):
    def test_truecolor_escapes(self):
        rgb = [[(1, 2, 3), (4, 5, 6)], [(7, 8, 9), (10, 11, 12)]]
        line = to_blocks_color(rgb)[0]
        self.assertIn("\x1b[38;2;1;2;3m", line)
        self.assertIn("\x1b[48;2;7;8;9m", line)
        self.assertIn("▀", line)
        self.assertTrue(line.endswith("\x1b[0m"))

    def test_8bit_escapes(self):
        rgb = [[(0, 0, 0)], [(255, 255, 255)]]
        line = to_blocks_color(rgb, depth="8bit")[0]
        self.assertIn("\x1b[38;5;16m", line)
        self.assertIn("\x1b[48;5;231m", line)


class TestBraille(unittest.TestCase):
    def test_all_black_is_blank_cells(self):
        lines = to_braille([[0] * 8] * 8)
        self.assertEqual(lines, [chr(BRAILLE_OFFSET) * 4] * 2)

    def test_all_white_is_full_cells(self):
        lines = to_braille([[255] * 8] * 8)
        self.assertEqual(lines, [chr(BRAILLE_OFFSET + 0xFF) * 4] * 2)

    def test_single_dot_bit(self):
        grid = [[0] * 8 for _ in range(8)]
        grid[0][0] = 255  # exactly one lit pixel, top-left
        lines = to_braille(grid)
        self.assertEqual(lines[0][0], chr(BRAILLE_OFFSET + 0x01))

    def test_invert(self):
        black = to_braille([[0] * 4] * 4)
        white_inverted = to_braille([[255] * 4] * 4, invert=True)
        self.assertEqual(black, white_inverted)

    def test_dither_smears_error(self):
        # a lone bright pixel must influence its neighbours under dithering
        grid = [[140] * 8 for _ in range(8)]
        plain = to_braille([row[:] for row in grid], threshold=0.5)
        dithered = to_braille([row[:] for row in grid], threshold=0.5, dither=True)
        self.assertNotEqual(plain, dithered)

    def test_threshold_bounds(self):
        with self.assertRaises(ValueError):
            to_braille([[0]], threshold=0.0)


class TestQuantize(unittest.TestCase):
    def test_exact_primaries(self):
        self.assertEqual(quantize_256(0, 0, 0), 16)
        self.assertEqual(quantize_256(255, 255, 255), 231)
        self.assertEqual(quantize_256(255, 0, 0), 196)

    def test_ansi_first_sixteen_are_skipped(self):
        code = quantize_256(128, 0, 0)
        self.assertGreaterEqual(code, 16)

    def test_grays_land_in_gray_ramp(self):
        code = quantize_256(128, 128, 128)
        self.assertGreaterEqual(code, 232)
        self.assertLessEqual(code, 255)


if __name__ == "__main__":
    unittest.main()
