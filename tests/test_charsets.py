import unittest

from asciiart.charsets import CHARSETS, resolve


class TestCharsets(unittest.TestCase):
    def test_named_ramps_exist(self):
        for name in ("standard", "detailed", "blocks", "contrast", "minimal"):
            self.assertIn(name, CHARSETS)
            self.assertGreaterEqual(len(CHARSETS[name]), 3)

    def test_ramps_are_ascending(self):
        # darkest first: space must be the first character of every ramp
        for name, ramp in CHARSETS.items():
            self.assertEqual(ramp[0], " ", f"{name} should start with a blank")

    def test_resolve_by_name(self):
        self.assertEqual(resolve("standard"), CHARSETS["standard"])

    def test_resolve_custom_ramp(self):
        self.assertEqual(resolve(".oO@"), ".oO@")

    def test_resolve_rejects_empty(self):
        with self.assertRaises(ValueError):
            resolve("")
        with self.assertRaises(ValueError):
            resolve("   ")


if __name__ == "__main__":
    unittest.main()
