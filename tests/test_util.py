"""Tests for the summary helpers."""
import pytest

from coop_schweiz.util import clean_name, format_summary, parse_summary


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        ("Brot", ("Brot", 1)),
        ("2x Milch", ("Milch", 2)),
        ("2 x Milch", ("Milch", 2)),
        ("3× Eier", ("Eier", 3)),
        ("2X Butter", ("Butter", 2)),
        ("  2x   Milch  ", ("Milch", 2)),
        ("3xl Shirt", ("3xl Shirt", 1)),
        ("2xAA Batterien", ("2xAA Batterien", 1)),
        ("0x Milch", ("0x Milch", 1)),
        ("1234x Milch", ("1234x Milch", 1)),
        ("", ("", 1)),
        (None, ("", 1)),
    ],
)
def test_parse_summary(summary, expected):
    assert parse_summary(summary) == expected


def test_format_and_parse_round_trip():
    assert format_summary("Milch", 1) == "Milch"
    assert format_summary("Milch", 2) == "2× Milch"
    assert parse_summary(format_summary("Milch", 2)) == ("Milch", 2)


def test_long_name_keeps_its_quantity():
    assert parse_summary("2× " + "x" * 200) == ("x" * 200, 2)


def test_clean_name():
    assert clean_name(" a\n b\t c ") == "a b c"
    assert len(clean_name("x" * 500)) == 200
