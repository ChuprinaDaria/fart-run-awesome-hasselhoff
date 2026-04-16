"""Per-framework parser tests."""
from pathlib import Path

from core.health.test_parsers import pytest as pytest_parser
from core.health.test_parsers import cargo as cargo_parser

FIXTURES = Path(__file__).parent / "fixtures" / "parser_outputs"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_pytest_parser_passed():
    r = pytest_parser.parse(_load("pytest_passed.txt"), exit_code=0)
    assert r.passed == 3
    assert r.failed == 0
    assert r.errors == 0
    assert r.skipped == 0


def test_pytest_parser_failed():
    r = pytest_parser.parse(_load("pytest_failed.txt"), exit_code=1)
    assert r.passed == 3
    assert r.failed == 1
    assert r.errors == 0


def test_pytest_parser_errors():
    r = pytest_parser.parse(_load("pytest_errors.txt"), exit_code=2)
    assert r.passed == 1
    assert r.errors == 1
    assert r.failed == 0


def test_pytest_parser_skipped():
    r = pytest_parser.parse(_load("pytest_skipped.txt"), exit_code=0)
    assert r.passed == 3
    assert r.skipped == 2


def test_pytest_parser_unparseable_returns_zeros():
    """When summary line is missing, return all zeros (not None) — the run
    happened, we just couldn't extract counters from this output shape."""
    r = pytest_parser.parse("garbage output\nno summary line here\n", exit_code=0)
    assert r.passed == 0 and r.failed == 0 and r.errors == 0 and r.skipped == 0


def test_cargo_parser_ok():
    r = cargo_parser.parse(_load("cargo_ok.txt"), exit_code=0)
    assert r.passed == 5
    assert r.failed == 0
    assert r.skipped == 0


def test_cargo_parser_failed():
    r = cargo_parser.parse(_load("cargo_failed.txt"), exit_code=101)
    assert r.passed == 2
    assert r.failed == 1
    assert r.skipped == 1  # cargo "ignored" maps to skipped
