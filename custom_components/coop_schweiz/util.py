"""Helpers without Home Assistant dependency."""
from __future__ import annotations

import re

MAX_NAME_LENGTH = 200
MAX_QUANTITY = 999

# "2x Milk" / "2 × Milk": up to three digits, an x, then whitespace.
# The whitespace is required so that "3xl shirt" stays a plain name.
_QUANTITY = re.compile(r"^(\d{1,3})\s*[x×]\s+(\S.*)$", re.IGNORECASE)


def clean_name(name: str | None) -> str:
    """Collapse whitespace and control characters, limit the length."""
    return " ".join((name or "").split())[:MAX_NAME_LENGTH].strip()


def clamp_quantity(quantity: int) -> int:
    """Keep a quantity inside 1..MAX_QUANTITY."""
    return max(1, min(int(quantity), MAX_QUANTITY))


def parse_summary(summary: str | None) -> tuple[str, int]:
    """Split a to-do summary into (name, quantity).

    "2x Milk" -> ("Milk", 2), "Bread" -> ("Bread", 1).
    """
    text = " ".join((summary or "").split())
    match = _QUANTITY.match(text)
    if match and int(match.group(1)) >= 1:
        return clean_name(match.group(2)), clamp_quantity(int(match.group(1)))
    return clean_name(text), 1


def format_summary(name: str, quantity: int) -> str:
    """Build the to-do summary shown in Home Assistant."""
    return f"{quantity}× {name}" if quantity > 1 else name
