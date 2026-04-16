"""Sync subprocess orchestration for the background test runner.

Pure stdlib; knows nothing about Qt or the database.
Plugin / GUI layers wrap this.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TestRun:
    project_dir: str
    framework: str
    command: list[str]
    started_at: float
    finished_at: float | None
    duration_s: float
    exit_code: int | None
    timed_out: bool
    passed: int | None
    failed: int | None
    errors: int | None
    skipped: int | None
    output_tail: str


@dataclass
class ParseResult:
    passed: int | None
    failed: int | None
    errors: int | None
    skipped: int | None


class Parser(Protocol):
    def parse(self, output: str, exit_code: int) -> ParseResult: ...
