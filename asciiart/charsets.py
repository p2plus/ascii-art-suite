"""Named character ramps for brightness-to-character mapping.

Ramps are ordered from darkest (background) to brightest. Any non-empty
string is accepted as a custom ramp via the CLI.
"""
from __future__ import annotations

CHARSETS: dict[str, str] = {
    "standard": " .:-=+*#%@",
    "detailed": " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$",
    "blocks": " ░▒▓█",
    "contrast": " .:*#@",
    "minimal": " .:#",
}


def resolve(name: str) -> str:
    """Return a ramp by name, or treat the argument itself as a ramp."""
    if not name:
        raise ValueError("charset must not be empty")
    if name in CHARSETS:
        return CHARSETS[name]
    if name.strip():
        return name
    raise ValueError(f"unknown charset {name!r}; known: {', '.join(CHARSETS)}")
