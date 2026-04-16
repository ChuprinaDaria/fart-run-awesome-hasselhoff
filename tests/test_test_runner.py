"""Tests for core.health.test_runner."""
from core.health.test_runner import TestRun, ParseResult, Parser


def test_test_run_dataclass_fields():
    run = TestRun(
        project_dir="/tmp", framework="pytest", command=["pytest"],
        started_at=1.0, finished_at=2.0, duration_s=1.0,
        exit_code=0, timed_out=False,
        passed=1, failed=0, errors=0, skipped=0,
        output_tail="ok",
    )
    assert run.framework == "pytest"
    assert run.passed == 1


def test_parse_result_optional_counters():
    r = ParseResult(passed=None, failed=None, errors=None, skipped=None)
    assert r.passed is None
