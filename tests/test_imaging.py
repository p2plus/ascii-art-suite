import unittest

from asciiart import imaging

try:
    import PIL  # noqa: F401
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def gradient(width=100, height=50):
    from PIL import Image

    img = Image.new("L", (width, height))
    img.putdata([int(255 * x / (width - 1)) for _ in range(height) for x in range(width)])
    return img


def gray_sums(img):
    return sum(img.tobytes())


@unittest.skipUnless(HAS_PIL, "Pillow not installed")
class TestGrid(unittest.TestCase):
    def test_grid_dimensions(self):
        grid = imaging.to_grid(gradient(), 40, 0.5)
        self.assertEqual(grid.size, (40, 10))

    def test_custom_rows(self):
        grid = imaging.to_grid(gradient(), 40, rows=7)
        self.assertEqual(grid.size, (40, 7))

    def test_aspect_scales_rows(self):
        grid = imaging.to_grid(gradient(100, 100), 20, 0.5)
        self.assertEqual(grid.size, (20, 10))

    def test_rejects_bad_width(self):
        with self.assertRaises(ValueError):
            imaging.to_grid(gradient(), 0)


@unittest.skipUnless(HAS_PIL, "Pillow not installed")
class TestTone(unittest.TestCase):
    def test_gamma_darkens(self):
        base = gradient(256, 1)
        dark = imaging.adjust_tone(base, gamma=2.0)
        self.assertLess(gray_sums(dark), gray_sums(base))

    def test_brightness_clamps(self):
        bright = imaging.adjust_tone(gradient(256, 1), brightness=5.0)
        self.assertEqual(max(bright.tobytes()), 255)

    def test_invert(self):
        base = gradient(256, 1)
        inv = imaging.adjust_tone(base, invert=True)
        self.assertEqual(gray_sums(inv), sum(255 - v for v in base.tobytes()))

    def test_auto_levels_stretches(self):
        from PIL import Image

        low_contrast = Image.new("L", (10, 10))
        low_contrast.putdata([100 + (x + y) % 51 for y in range(10) for x in range(10)])
        stretched = imaging.adjust_tone(low_contrast, auto_levels=True)
        self.assertIn(0, stretched.tobytes())
        self.assertIn(255, stretched.tobytes())

    def test_rgb_tone_preserves_channels(self):
        from PIL import Image

        img = Image.new("RGB", (4, 1), (200, 40, 30))
        out = imaging.adjust_tone(img, gamma=1.5)
        self.assertEqual(out.mode, "RGB")
        r, g, b = out.getpixel((0, 0))
        self.assertNotEqual((r, g, b), (r, r, r), "RGB must not collapse to gray")
        self.assertGreater(g, b, "channel order must survive tone correction")

    def test_rgb_auto_levels_per_band(self):
        from PIL import Image

        # red band low-contrast near 200, green band near 60
        img = Image.new("RGB", (8, 1))
        img.putdata([(200 + (x % 3), 60 + (x % 3), 128) for x in range(8)])
        out = imaging.adjust_tone(img, auto_levels=True)
        pixels = [out.getpixel((x, 0)) for x in range(8)]
        self.assertTrue(any(p[0] == 255 for p in pixels), "red band must stretch")
        self.assertTrue(any(p[1] == 0 for p in pixels), "green band must stretch")


@unittest.skipUnless(HAS_PIL, "Pillow not installed")
class TestPixelGrid(unittest.TestCase):
    def test_gray_grid_matches_pixel_access(self):
        from PIL import Image

        img = gradient(7, 5)
        grid = imaging.pixel_grid_gray(img)
        self.assertEqual(len(grid), 5)
        self.assertEqual(len(grid[0]), 7)
        self.assertEqual(grid[2][3], img.getpixel((3, 2)))

    def test_rgb_grid_matches_pixel_access(self):
        from PIL import Image

        img = Image.new("RGB", (5, 3))
        img.putdata([(10, 20, 30), (40, 50, 60), (70, 80, 90)] * 5)
        grid = imaging.pixel_grid_rgb(img)
        self.assertEqual(grid[1][2], img.getpixel((2, 1)))


@unittest.skipUnless(HAS_PIL, "Pillow not installed")
class TestLoad(unittest.TestCase):
    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            imaging.load_image("/nonexistent/nope.png")

    def test_load_bytes(self):
        import io

        from PIL import Image

        buffer = io.BytesIO()
        gradient(20, 10).convert("RGB").save(buffer, "PNG")
        img = imaging.load_image(buffer.getvalue())
        self.assertEqual(img.size, (20, 10))

    def test_alpha_composites_on_background(self):
        import io

        from PIL import Image

        def load_with(alpha):
            rgba = Image.new("RGBA", (4, 4), (255, 0, 0, alpha))
            buffer = io.BytesIO()
            rgba.save(buffer, "PNG")
            return imaging.load_image(buffer.getvalue(), background="#ffffff")

        self.assertEqual(load_with(0).getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(load_with(255).getpixel((0, 0)), (255, 0, 0))
        # half-transparent lands between the two extremes
        mid = load_with(128).getpixel((0, 0))
        self.assertGreaterEqual(mid[1], 100)
        self.assertLessEqual(mid[1], 155)

    def test_bad_background(self):
        with self.assertRaises(ValueError):
            imaging._parse_hex("#12345")


class TestParseHex(unittest.TestCase):
    def test_short_and_long_forms(self):
        self.assertEqual(imaging._parse_hex("#fff"), (255, 255, 255))
        self.assertEqual(imaging._parse_hex("00ff00"), (0, 255, 0))


if __name__ == "__main__":
    unittest.main()
