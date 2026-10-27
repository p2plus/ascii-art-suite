import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from asciiart import __version__, cli

try:
    import PIL  # noqa: F401
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestTextCommand(unittest.TestCase):
    def test_basic_render(self):
        code, out, err = run_cli("text", "Hi", "-f", "mini", "-w", "40")
        self.assertEqual(code, 0, err)
        self.assertIn("_", out)
        self.assertNotIn("$", out)

    def test_random_font_is_deterministic_with_seed(self):
        first = run_cli("text", "ok", "--random", "--seed", "3")
        second = run_cli("text", "ok", "--random", "--seed", "3")
        self.assertEqual(first[1], second[1])

    def test_unknown_font_fails_cleanly(self):
        code, out, err = run_cli("text", "Hi", "-f", "definitely-not-a-font")
        self.assertEqual(code, 1)
        self.assertIn("asciiart: error:", err)
        self.assertIn("standard", err)  # suggestion included

    def test_stdin_input(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out):
            with mock.patch.object(sys, "stdin", io.StringIO("piped\n")):
                code = cli.main(["text", "-", "-f", "mini", "-w", "40"])
        self.assertEqual(code, 0)
        self.assertIn("_", out.getvalue())

    def test_out_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "banner.txt"
            code, out, err = run_cli("text", "ok", "-f", "mini", "-o", str(path))
            self.assertEqual(code, 0, err)
            self.assertEqual(out, "")
            self.assertTrue(path.read_text().strip())

    def test_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn(__version__, out.getvalue())


class TestFontsCommand(unittest.TestCase):
    def test_lists_bundled_fonts(self):
        code, out, err = run_cli("fonts")
        self.assertEqual(code, 0, err)
        self.assertIn("standard", out.lower())
        self.assertIn("bundled", out)

    def test_verbose_shows_paths(self):
        code, out, err = run_cli("fonts", "-v")
        self.assertEqual(code, 0, err)
        self.assertIn("fonts/", out)


@unittest.skipUnless(HAS_PIL, "Pillow not installed")
class TestImageCommand(unittest.TestCase):
    def setUp(self):
        import io as _io

        from PIL import Image

        buffer = _io.BytesIO()
        gradient = Image.new("L", (60, 30))
        gradient.putdata([int(255 * x / 59) for _ in range(30) for x in range(60)])
        gradient.convert("RGB").save(buffer, "PNG")
        self.png_bytes = buffer.getvalue()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "grad.png"
        self.path.write_bytes(self.png_bytes)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ascii_output(self):
        code, out, err = run_cli("image", str(self.path), "-w", "40")
        self.assertEqual(code, 0, err)
        lines = out.strip("\n").splitlines()
        self.assertEqual(len(lines), 10)  # 40 cols * (30/60) * 0.5 aspect
        self.assertGreaterEqual(len(lines[0]), 20)

    def test_braille_output(self):
        code, out, err = run_cli("image", str(self.path), "-w", "20", "--format", "braille")
        self.assertEqual(code, 0, err)
        self.assertTrue(all(ord(ch) >= 0x2800 for ch in out if ch not in "\n"))
        # -w counts terminal columns, and every braille cell is one column
        lines = out.strip("\n").splitlines()
        self.assertTrue(all(len(line) == 20 for line in lines))

    def test_blocks_color_suppressed_when_piped(self):
        code, out, err = run_cli(
            "image", str(self.path), "-w", "20", "--format", "blocks"
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn("\x1b[", out)  # auto color -> none when not a tty

    def test_blocks_color_forced(self):
        code, out, err = run_cli(
            "image", str(self.path), "-w", "20", "--format", "blocks",
            "--color", "24bit",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("\x1b[38;2;", out)

    def test_no_color_env_wins(self):
        env = dict(os.environ, NO_COLOR="1")
        with mock.patch.dict(os.environ, env, clear=True):
            code, out, err = run_cli(
                "image", str(self.path), "-w", "20", "--format", "blocks",
                "--color", "24bit",
            )
        self.assertEqual(code, 0, err)
        self.assertNotIn("\x1b[", out)

    def test_stdin_bytes(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out):
            with mock.patch.object(sys, "stdin",
                                   mock.Mock(buffer=io.BytesIO(self.png_bytes))):
                code = cli.main(["image", "-", "-w", "10"])
        self.assertEqual(code, 0)
        self.assertTrue(out.getvalue().strip())

    def test_missing_file(self):
        code, out, err = run_cli("image", "/nonexistent/img.png")
        self.assertEqual(code, 1)
        self.assertIn("asciiart: error:", err)

    def test_bad_charset(self):
        code, out, err = run_cli("image", str(self.path), "--charset", "   ")
        self.assertEqual(code, 1)
        self.assertIn("asciiart: error:", err)


class TestDemoCommand(unittest.TestCase):
    def test_demo_runs(self):
        code, out, err = run_cli("demo", "--seed", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("fonts discovered", out)

    def test_demo_seed_is_deterministic(self):
        first = run_cli("demo", "--seed", "3")
        second = run_cli("demo", "--seed", "3")
        self.assertEqual(first[1], second[1])
        self.assertNotEqual(run_cli("demo", "--seed", "3")[1],
                            run_cli("demo", "--seed", "4")[1])


if __name__ == "__main__":
    unittest.main()
