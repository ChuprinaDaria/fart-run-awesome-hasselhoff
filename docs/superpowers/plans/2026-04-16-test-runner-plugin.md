# Background Test Runner Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a background test runner that shells out to pytest / cargo test / npm test, persists results in `HistoryDB`, and surfaces a Tests section in the Health page with manual / save-point / watch triggers (manual on by default, others opt-in).

**Architecture:** Sync `TestRunner` core (subprocess + ring buffer + timeout) wrapped by a Qt `QThread` for the GUI, with a real `TestRunnerPlugin(Plugin)` exposed via a new minimal `PluginRegistry` that bridges the existing async `Plugin(ABC)` contract through one-shot `asyncio.run()` calls. Single in-flight run per project, coalesced re-trigger via `_needs_rerun` on `HealthPage`.

**Tech Stack:** Python 3.11+, PyQt5, sqlite3 (via `core.history.HistoryDB`), `subprocess` (stdlib), optional `watchdog`. No new third-party deps required for v1.

**Spec:** `docs/superpowers/specs/2026-04-16-test-runner-plugin-design.md`

---

## File Structure

**New files:**
- `core/health/test_runner.py` — `TestRun` dataclass, `Parser` Protocol, `ParseResult` dataclass, `TestRunner` class
- `core/health/test_detector.py` — `detect_framework()`
- `core/health/test_parsers/__init__.py` — `for_framework(name)` registry
- `core/health/test_parsers/pytest.py` — pytest text parser
- `core/health/test_parsers/cargo.py` — cargo text parser
- `core/health/test_parsers/jest.py` — Jest JSON parser
- `core/health/test_parsers/vitest.py` — Vitest JSON parser
- `core/health/test_parsers/generic.py` — exit-code-only fallback
- `core/plugin_loader.py` — `PluginRegistry`
- `plugins/test_runner/__init__.py` — empty
- `plugins/test_runner/plugin.py` — `TestRunnerPlugin(Plugin)`
- `plugins/test_runner/collector.py` — re-export `detect_framework` for parity
- `gui/pages/health/test_runner_thread.py` — `TestRunnerThread(QThread)`
- `tests/fixtures/test_runner_pytest/` — minimal repo (1 pass + 1 fail)
- `tests/fixtures/parser_outputs/` — captured stdout for parser tests
- `tests/test_history_test_runs.py`, `tests/test_test_runner.py`, `tests/test_test_parsers.py`, `tests/test_test_detector.py`, `tests/test_test_runner_thread.py`, `tests/test_plugin_loader.py`, `tests/test_test_runner_coalescing.py`, `tests/test_test_runner_plugin.py`

**Modified files:**
- `core/history.py` — add `_migrate_test_runs()` + `save_test_run()` + `get_test_runs()` + `get_last_test_run()`
- `gui/pages/health/page.py` — `_build_tests_section()`, slots, coalescing
- `gui/pages/settings.py` — Tests group
- `gui/app/main.py` — wire `PluginRegistry` + save-point signal
- `config.toml` — `[tests]` section + `[plugins] test_runner = true`

---

## Task 1: `HistoryDB.test_runs` schema + accessors

**Files:**
- Modify: `core/history.py` (add migration in `init()`, add 3 methods)
- Create: `tests/test_history_test_runs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_history_test_runs.py
"""Tests for test_runs table in HistoryDB."""
from core.history import HistoryDB


def _sample_run(project_dir="/tmp/proj", started=1000.0, **overrides):
    base = dict(
        project_dir=project_dir,
        framework="pytest",
        command=["pytest", "-x"],
        started_at=started,
        finished_at=started + 5.0,
        duration_s=5.0,
        exit_code=0,
        timed_out=False,
        passed=10, failed=0, errors=0, skipped=1,
        output_tail="10 passed in 5s",
    )
    base.update(overrides)
    return base


def test_save_and_get_last_test_run():
    db = HistoryDB(":memory:")
    db.init()
    row_id = db.save_test_run(_sample_run())
    assert row_id > 0
    last = db.get_last_test_run("/tmp/proj")
    assert last["framework"] == "pytest"
    assert last["passed"] == 10
    assert last["command"] == ["pytest", "-x"]
    db.close()


def test_get_test_runs_returns_newest_first():
    db = HistoryDB(":memory:")
    db.init()
    db.save_test_run(_sample_run(started=1000.0))
    db.save_test_run(_sample_run(started=2000.0, exit_code=1, failed=2, passed=8))
    runs = db.get_test_runs("/tmp/proj")
    assert len(runs) == 2
    assert runs[0]["started_at"] == 2000.0
    assert runs[0]["failed"] == 2
    db.close()


def test_get_test_runs_filters_by_project():
    db = HistoryDB(":memory:")
    db.init()
    db.save_test_run(_sample_run(project_dir="/a"))
    db.save_test_run(_sample_run(project_dir="/b"))
    assert len(db.get_test_runs("/a")) == 1
    assert len(db.get_test_runs("/b")) == 1
    db.close()


def test_save_test_run_prunes_to_history_limit():
    db = HistoryDB(":memory:")
    db.init()
    for i in range(105):
        db.save_test_run(_sample_run(started=float(i)))
    runs = db.get_test_runs("/tmp/proj", limit=200)
    assert len(runs) == 100  # default history_limit
    # oldest 5 pruned: started_at 0..4 gone
    assert min(r["started_at"] for r in runs) == 5.0
    db.close()


def test_get_last_test_run_none_when_empty():
    db = HistoryDB(":memory:")
    db.init()
    assert db.get_last_test_run("/nope") is None
    db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_history_test_runs.py -v`
Expected: FAIL with `AttributeError: 'HistoryDB' object has no attribute 'save_test_run'`

- [ ] **Step 3: Add migration in `core/history.py::init()`**

Add this block right before the final `self.commit()` inside `init()` (around line 126):

```python
self.execute("""
    CREATE TABLE IF NOT EXISTS test_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_dir TEXT NOT NULL,
        framework TEXT NOT NULL,
        command TEXT NOT NULL,
        started_at REAL NOT NULL,
        finished_at REAL,
        duration_s REAL,
        exit_code INTEGER,
        timed_out INTEGER NOT NULL DEFAULT 0,
        passed INTEGER, failed INTEGER, errors INTEGER, skipped INTEGER,
        output_tail TEXT
    )
""")
self.execute("""
    CREATE INDEX IF NOT EXISTS idx_test_runs_project_started
        ON test_runs (project_dir, started_at DESC)
""")
```

- [ ] **Step 4: Add accessor methods to `HistoryDB`**

Append after the existing `get_state` / `set_state` block (around line 195):

```python
# --- Test runs ---

def save_test_run(self, run: dict, history_limit: int = 100) -> int:
    """Insert a TestRun-shaped dict, prune to history_limit per project."""
    import json
    self._ensure_conn()
    cursor = self.execute("""
        INSERT INTO test_runs
        (project_dir, framework, command, started_at, finished_at,
         duration_s, exit_code, timed_out, passed, failed, errors,
         skipped, output_tail)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run["project_dir"], run["framework"], json.dumps(run["command"]),
        run["started_at"], run.get("finished_at"), run.get("duration_s"),
        run.get("exit_code"), 1 if run.get("timed_out") else 0,
        run.get("passed"), run.get("failed"), run.get("errors"),
        run.get("skipped"), run.get("output_tail", ""),
    ))
    new_id = cursor.lastrowid
    # Prune older rows beyond history_limit for this project
    self.execute("""
        DELETE FROM test_runs WHERE project_dir = ?
          AND id NOT IN (
            SELECT id FROM test_runs WHERE project_dir = ?
            ORDER BY started_at DESC LIMIT ?
          )
    """, (run["project_dir"], run["project_dir"], history_limit))
    self.commit()
    return new_id

def _row_to_test_run(self, row) -> dict:
    import json
    return {
        "id": row[0], "project_dir": row[1], "framework": row[2],
        "command": json.loads(row[3]), "started_at": row[4],
        "finished_at": row[5], "duration_s": row[6], "exit_code": row[7],
        "timed_out": bool(row[8]), "passed": row[9], "failed": row[10],
        "errors": row[11], "skipped": row[12], "output_tail": row[13],
    }

def get_test_runs(self, project_dir: str, limit: int = 50) -> list[dict]:
    self._ensure_conn()
    rows = self.execute("""
        SELECT id, project_dir, framework, command, started_at, finished_at,
               duration_s, exit_code, timed_out, passed, failed, errors,
               skipped, output_tail
        FROM test_runs WHERE project_dir = ?
        ORDER BY started_at DESC LIMIT ?
    """, (project_dir, limit)).fetchall()
    return [self._row_to_test_run(r) for r in rows]

def get_last_test_run(self, project_dir: str) -> dict | None:
    runs = self.get_test_runs(project_dir, limit=1)
    return runs[0] if runs else None
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_history_test_runs.py -v`
Expected: 5 PASS

- [ ] **Step 6: Run full test suite to confirm no regressions**

Run: `pytest tests/ -x --tb=short -q`
Expected: All previously-green tests still pass.

- [ ] **Step 7: Commit**

```bash
git add core/history.py tests/test_history_test_runs.py
git commit -m "feat(history): add test_runs table + accessors for Task 17"
```

---

## Task 2: `TestRun` dataclass + parser contract

**Files:**
- Create: `core/health/test_runner.py` (skeleton — only types for now)
- Create: `tests/test_test_runner.py` (smoke import test)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_test_runner.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.health.test_runner'`

- [ ] **Step 3: Create the module**

```python
# core/health/test_runner.py
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
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_test_runner.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add core/health/test_runner.py tests/test_test_runner.py
git commit -m "feat(test_runner): add TestRun + ParseResult + Parser Protocol"
```

---

## Task 3: pytest output parser

**Files:**
- Create: `core/health/test_parsers/__init__.py` (empty)
- Create: `core/health/test_parsers/pytest.py`
- Create: `tests/fixtures/parser_outputs/pytest_passed.txt`
- Create: `tests/fixtures/parser_outputs/pytest_failed.txt`
- Create: `tests/fixtures/parser_outputs/pytest_errors.txt`
- Create: `tests/fixtures/parser_outputs/pytest_skipped.txt`
- Create: `tests/test_test_parsers.py`

- [ ] **Step 1: Capture canonical pytest fixtures**

Create `tests/fixtures/parser_outputs/pytest_passed.txt`:
```
============================= test session starts ==============================
collected 3 items

tests/test_a.py ...                                                      [100%]

============================== 3 passed in 0.05s ===============================
```

Create `tests/fixtures/parser_outputs/pytest_failed.txt`:
```
============================= test session starts ==============================
collected 4 items

tests/test_a.py ..F.                                                     [100%]

=================================== FAILURES ===================================
______________________________ test_something __________________________________
    assert 1 == 2
E   assert 1 == 2

=========================== 1 failed, 3 passed in 0.07s ========================
```

Create `tests/fixtures/parser_outputs/pytest_errors.txt`:
```
============================= test session starts ==============================
collected 2 items / 1 error

==================================== ERRORS ====================================
___________________ ERROR collecting tests/test_broken.py ______________________
ImportError: cannot import name 'foo'

=========================== 1 passed, 1 error in 0.04s =========================
```

Create `tests/fixtures/parser_outputs/pytest_skipped.txt`:
```
============================= test session starts ==============================
collected 5 items

tests/test_a.py ..ss.                                                    [100%]

======================== 3 passed, 2 skipped in 0.06s ==========================
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_test_parsers.py
"""Per-framework parser tests."""
from pathlib import Path

from core.health.test_parsers import pytest as pytest_parser

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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_test_parsers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.health.test_parsers'`

- [ ] **Step 4: Create the parser package + module**

Create `core/health/test_parsers/__init__.py`:
```python
"""Per-framework output parsers for the background test runner."""
```

Create `core/health/test_parsers/pytest.py`:
```python
"""Pytest text-output parser.

Parses the standard summary line at the bottom of pytest output.
Format is stable across pytest 6+: '=== N passed, M failed, K skipped, E errors in 1.23s ==='.
"""
from __future__ import annotations

import re

from core.health.test_runner import ParseResult

# Match individual counters anywhere on the summary line.
_COUNTER_RE = re.compile(
    r"(\d+)\s+(passed|failed|skipped|error|errors)\b"
)
# The summary line begins and ends with at least one '=' run.
_SUMMARY_LINE_RE = re.compile(r"^=+\s*(.*?)\s*=+$", re.MULTILINE)


def parse(output: str, exit_code: int) -> ParseResult:
    passed = failed = errors = skipped = 0
    summary_lines = _SUMMARY_LINE_RE.findall(output)
    # Pick the last summary line that contains at least one counter word.
    for line in reversed(summary_lines):
        if any(kw in line for kw in ("passed", "failed", "skipped", "error")):
            for count, kind in _COUNTER_RE.findall(line):
                n = int(count)
                if kind == "passed":
                    passed = n
                elif kind == "failed":
                    failed = n
                elif kind == "skipped":
                    skipped = n
                elif kind in ("error", "errors"):
                    errors = n
            break
    return ParseResult(passed=passed, failed=failed, errors=errors, skipped=skipped)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_test_parsers.py -v`
Expected: 5 PASS

- [ ] **Step 6: Commit**

```bash
git add core/health/test_parsers/__init__.py core/health/test_parsers/pytest.py tests/fixtures/parser_outputs/ tests/test_test_parsers.py
git commit -m "feat(test_parsers): add pytest text-output parser"
```

---

## Task 4: cargo output parser

**Files:**
- Create: `core/health/test_parsers/cargo.py`
- Create: `tests/fixtures/parser_outputs/cargo_ok.txt`
- Create: `tests/fixtures/parser_outputs/cargo_failed.txt`
- Modify: `tests/test_test_parsers.py`

- [ ] **Step 1: Capture cargo fixtures**

Create `tests/fixtures/parser_outputs/cargo_ok.txt`:
```
   Compiling health v0.1.0
    Finished test [unoptimized + debuginfo] target(s) in 1.23s
     Running unittests src/lib.rs

running 5 tests
test foo::test_a ... ok
test foo::test_b ... ok
test foo::test_c ... ok
test bar::test_d ... ok
test bar::test_e ... ok

test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s
```

Create `tests/fixtures/parser_outputs/cargo_failed.txt`:
```
running 4 tests
test a ... ok
test b ... FAILED
test c ... ok
test d ... ignored

failures:
    b

test result: FAILED. 2 passed; 1 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.02s
```

- [ ] **Step 2: Add failing tests**

Append to `tests/test_test_parsers.py`:
```python
from core.health.test_parsers import cargo as cargo_parser


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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_test_parsers.py -v -k cargo`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Create cargo parser**

Create `core/health/test_parsers/cargo.py`:
```python
"""Cargo test output parser.

Sums counters across all 'test result: ...' lines (one per test binary).
"""
from __future__ import annotations

import re

from core.health.test_runner import ParseResult

_RESULT_RE = re.compile(
    r"test result:\s+\S+\.\s+(\d+)\s+passed;\s+(\d+)\s+failed;\s+(\d+)\s+ignored",
    re.MULTILINE,
)


def parse(output: str, exit_code: int) -> ParseResult:
    passed = failed = skipped = 0
    matches = _RESULT_RE.findall(output)
    for p, f, ign in matches:
        passed += int(p)
        failed += int(f)
        skipped += int(ign)
    return ParseResult(passed=passed, failed=failed, errors=0, skipped=skipped)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_test_parsers.py -v`
Expected: 7 PASS (5 pytest + 2 cargo).

- [ ] **Step 6: Commit**

```bash
git add core/health/test_parsers/cargo.py tests/fixtures/parser_outputs/cargo_ok.txt tests/fixtures/parser_outputs/cargo_failed.txt tests/test_test_parsers.py
git commit -m "feat(test_parsers): add cargo test output parser"
```

---

## Task 5: Jest JSON parser

**Files:**
- Create: `core/health/test_parsers/jest.py`
- Create: `tests/fixtures/parser_outputs/jest_passed.json`
- Create: `tests/fixtures/parser_outputs/jest_failed.json`
- Modify: `tests/test_test_parsers.py`

- [ ] **Step 1: Capture jest fixtures**

Create `tests/fixtures/parser_outputs/jest_passed.json`:
```json
{
  "numTotalTests": 12,
  "numPassedTests": 12,
  "numFailedTests": 0,
  "numPendingTests": 0,
  "success": true
}
```

Create `tests/fixtures/parser_outputs/jest_failed.json`:
```json
{
  "numTotalTests": 12,
  "numPassedTests": 9,
  "numFailedTests": 3,
  "numPendingTests": 1,
  "success": false
}
```

- [ ] **Step 2: Add failing tests**

Append to `tests/test_test_parsers.py`:
```python
from core.health.test_parsers import jest as jest_parser


def test_jest_parser_passed():
    r = jest_parser.parse(_load("jest_passed.json"), exit_code=0)
    assert r.passed == 12
    assert r.failed == 0


def test_jest_parser_failed():
    r = jest_parser.parse(_load("jest_failed.json"), exit_code=1)
    assert r.passed == 9
    assert r.failed == 3
    assert r.skipped == 1


def test_jest_parser_garbage_returns_none():
    """When no JSON object found, parser returns all None (we don't know counters)."""
    r = jest_parser.parse("npm WARN something\nrandom text\n", exit_code=1)
    assert r.passed is None
    assert r.failed is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_test_parsers.py -v -k jest`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Create jest parser**

Create `core/health/test_parsers/jest.py`:
```python
"""Jest --json output parser.

Jest writes a JSON object to stdout when invoked with --json. npm wrappers
prepend stuff like 'npm info ...', so we scan for the first '{' and try
to json-decode from there to the matching closing brace.
"""
from __future__ import annotations

import json

from core.health.test_runner import ParseResult


def _extract_json(output: str) -> dict | None:
    start = output.find("{")
    if start < 0:
        return None
    # Walk forward until balanced; tolerate string contents.
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(output)):
        ch = output[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(output[start:i+1])
                except json.JSONDecodeError:
                    return None
    return None


def parse(output: str, exit_code: int) -> ParseResult:
    obj = _extract_json(output)
    if obj is None:
        return ParseResult(passed=None, failed=None, errors=None, skipped=None)
    return ParseResult(
        passed=obj.get("numPassedTests"),
        failed=obj.get("numFailedTests"),
        errors=0,
        skipped=obj.get("numPendingTests"),
    )
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_test_parsers.py -v`
Expected: 10 PASS (5 + 2 + 3).

- [ ] **Step 6: Commit**

```bash
git add core/health/test_parsers/jest.py tests/fixtures/parser_outputs/jest_passed.json tests/fixtures/parser_outputs/jest_failed.json tests/test_test_parsers.py
git commit -m "feat(test_parsers): add Jest JSON output parser"
```

---

## Task 6: Vitest JSON parser

**Files:**
- Create: `core/health/test_parsers/vitest.py`
- Create: `tests/fixtures/parser_outputs/vitest_passed.json`
- Create: `tests/fixtures/parser_outputs/vitest_failed.json`
- Modify: `tests/test_test_parsers.py`

- [ ] **Step 1: Capture vitest fixtures**

Vitest's `--reporter=json` shape (subset relevant to us):

Create `tests/fixtures/parser_outputs/vitest_passed.json`:
```json
{
  "numTotalTests": 8,
  "numPassedTests": 8,
  "numFailedTests": 0,
  "numPendingTests": 0,
  "success": true
}
```

Create `tests/fixtures/parser_outputs/vitest_failed.json`:
```json
{
  "numTotalTests": 8,
  "numPassedTests": 5,
  "numFailedTests": 3,
  "numPendingTests": 0,
  "success": false
}
```

- [ ] **Step 2: Add failing tests**

Append to `tests/test_test_parsers.py`:
```python
from core.health.test_parsers import vitest as vitest_parser


def test_vitest_parser_passed():
    r = vitest_parser.parse(_load("vitest_passed.json"), exit_code=0)
    assert r.passed == 8
    assert r.failed == 0


def test_vitest_parser_failed():
    r = vitest_parser.parse(_load("vitest_failed.json"), exit_code=1)
    assert r.passed == 5
    assert r.failed == 3
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_test_parsers.py -v -k vitest`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Create vitest parser**

Vitest emits the same key shape as Jest in this subset, so we delegate:

```python
# core/health/test_parsers/vitest.py
"""Vitest --reporter=json output parser.

Vitest's JSON reporter matches Jest's shape for the counters we read.
We delegate to the Jest parser to avoid duplicating the JSON-extraction
walker; if the formats ever diverge, fork this module.
"""
from __future__ import annotations

from core.health.test_parsers import jest as _jest
from core.health.test_runner import ParseResult


def parse(output: str, exit_code: int) -> ParseResult:
    return _jest.parse(output, exit_code)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_test_parsers.py -v`
Expected: 12 PASS.

- [ ] **Step 6: Commit**

```bash
git add core/health/test_parsers/vitest.py tests/fixtures/parser_outputs/vitest_passed.json tests/fixtures/parser_outputs/vitest_failed.json tests/test_test_parsers.py
git commit -m "feat(test_parsers): add Vitest JSON output parser"
```

---

## Task 7: generic exit-code parser

**Files:**
- Create: `core/health/test_parsers/generic.py`
- Modify: `tests/test_test_parsers.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_test_parsers.py`:
```python
from core.health.test_parsers import generic as generic_parser


def test_generic_parser_returns_all_none():
    r = generic_parser.parse("any output at all", exit_code=0)
    assert r.passed is None
    assert r.failed is None
    assert r.errors is None
    assert r.skipped is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_parsers.py -v -k generic`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create generic parser**

```python
# core/health/test_parsers/generic.py
"""Fallback parser for unknown frameworks.

Returns all None so the GUI shows pass/fail by exit code only without
inventing counters.
"""
from __future__ import annotations

from core.health.test_runner import ParseResult


def parse(output: str, exit_code: int) -> ParseResult:
    return ParseResult(passed=None, failed=None, errors=None, skipped=None)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_test_parsers.py -v`
Expected: 13 PASS.

- [ ] **Step 5: Commit**

```bash
git add core/health/test_parsers/generic.py tests/test_test_parsers.py
git commit -m "feat(test_parsers): add generic exit-code-only parser"
```

---

## Task 8: parser registry `for_framework()`

**Files:**
- Modify: `core/health/test_parsers/__init__.py`
- Modify: `tests/test_test_parsers.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_test_parsers.py`:
```python
from core.health.test_parsers import for_framework


def test_for_framework_known():
    p = for_framework("pytest")
    r = p.parse(_load("pytest_passed.txt"), exit_code=0)
    assert r.passed == 3


def test_for_framework_unknown_returns_generic():
    p = for_framework("unknown-thing")
    r = p.parse("anything", exit_code=0)
    assert r.passed is None  # generic
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_parsers.py -v -k for_framework`
Expected: FAIL with `ImportError: cannot import name 'for_framework'`.

- [ ] **Step 3: Implement registry**

Replace `core/health/test_parsers/__init__.py`:
```python
"""Per-framework output parsers for the background test runner."""
from __future__ import annotations

from types import ModuleType

from core.health.test_parsers import (
    cargo, generic, jest, pytest, vitest,
)

_REGISTRY: dict[str, ModuleType] = {
    "pytest": pytest,
    "cargo": cargo,
    "jest": jest,
    "vitest": vitest,
    "generic": generic,
}


def for_framework(name: str) -> ModuleType:
    """Return the parser module for the given framework name.

    Unknown names fall back to the generic (exit-code-only) parser.
    The returned module exposes a `parse(output: str, exit_code: int) -> ParseResult`
    function.
    """
    return _REGISTRY.get(name, generic)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_test_parsers.py -v`
Expected: 15 PASS.

- [ ] **Step 5: Commit**

```bash
git add core/health/test_parsers/__init__.py tests/test_test_parsers.py
git commit -m "feat(test_parsers): add for_framework() registry helper"
```

---

## Task 9: framework detector

**Files:**
- Create: `core/health/test_detector.py`
- Create: `tests/test_test_detector.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_test_detector.py
"""Tests for project-type test framework detection."""
from pathlib import Path

import pytest

from core.health.test_detector import detect_framework


def _write(tmp_path: Path, name: str, content: str = "") -> None:
    (tmp_path / name).write_text(content)


def test_detects_pytest_from_pyproject(tmp_path):
    _write(tmp_path, "pyproject.toml", '[tool.pytest.ini_options]\nminversion="6.0"\n')
    name, cmd = detect_framework(tmp_path)
    assert name == "pytest"
    assert cmd[0] == "pytest"


def test_detects_cargo_from_cargo_toml(tmp_path):
    _write(tmp_path, "Cargo.toml", '[package]\nname = "x"\nversion = "0.1.0"\n')
    name, cmd = detect_framework(tmp_path)
    assert name == "cargo"
    assert cmd[:2] == ["cargo", "test"]


def test_detects_jest_from_package_json(tmp_path):
    _write(tmp_path, "package.json", '{"scripts": {"test": "jest"}}')
    name, cmd = detect_framework(tmp_path)
    assert name == "jest"
    # Append --json so parser has structured input.
    assert "--json" in " ".join(cmd)


def test_detects_vitest_from_package_json(tmp_path):
    _write(tmp_path, "package.json", '{"scripts": {"test": "vitest run"}}')
    name, cmd = detect_framework(tmp_path)
    assert name == "vitest"
    assert "--reporter=json" in " ".join(cmd)


def test_falls_back_to_generic_for_other_npm_test(tmp_path):
    _write(tmp_path, "package.json", '{"scripts": {"test": "mocha"}}')
    name, cmd = detect_framework(tmp_path)
    assert name == "generic"
    assert cmd == ["npm", "test"]


def test_pyproject_wins_over_cargo_when_both_present(tmp_path):
    _write(tmp_path, "pyproject.toml", '[tool.pytest.ini_options]\n')
    _write(tmp_path, "Cargo.toml", '[package]\nname="x"\n')
    name, _ = detect_framework(tmp_path)
    assert name == "pytest"


def test_empty_project_returns_generic_with_empty_cmd(tmp_path):
    name, cmd = detect_framework(tmp_path)
    assert name == "generic"
    assert cmd == []


def test_pytest_via_conftest_only(tmp_path):
    """Project with no pyproject but conftest.py + tests/ folder -> pytest."""
    (tmp_path / "tests").mkdir()
    _write(tmp_path / "tests", "conftest.py")
    name, _ = detect_framework(tmp_path)
    assert name == "pytest"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_detector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.health.test_detector'`.

- [ ] **Step 3: Create detector**

```python
# core/health/test_detector.py
"""Detects which test framework a project uses, returns a default command.

Priority: pyproject.toml > Cargo.toml > package.json > heuristic.
The caller is responsible for honoring an explicit override from config.toml.
"""
from __future__ import annotations

import json
from pathlib import Path


def _has_pytest_marker(project_dir: Path) -> bool:
    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(errors="ignore")
        if "[tool.pytest" in text or "pytest" in text:
            return True
    if (project_dir / "setup.cfg").exists():
        if "pytest" in (project_dir / "setup.cfg").read_text(errors="ignore"):
            return True
    if (project_dir / "tox.ini").exists():
        if "pytest" in (project_dir / "tox.ini").read_text(errors="ignore"):
            return True
    if (project_dir / "tests" / "conftest.py").exists():
        return True
    if (project_dir / "conftest.py").exists():
        return True
    return False


def _read_npm_test_script(project_dir: Path) -> str | None:
    pkg = project_dir / "package.json"
    if not pkg.exists():
        return None
    try:
        data = json.loads(pkg.read_text(errors="ignore"))
    except json.JSONDecodeError:
        return None
    scripts = data.get("scripts") or {}
    return scripts.get("test")


def detect_framework(project_dir: Path) -> tuple[str, list[str]]:
    """Return (framework_name, default argv).

    Empty argv means 'no framework detected — caller must show an error
    or ask user to set [tests] command override'.
    """
    project_dir = Path(project_dir)

    if _has_pytest_marker(project_dir):
        return ("pytest", ["pytest", "-x", "--tb=short"])

    if (project_dir / "Cargo.toml").exists():
        return ("cargo", ["cargo", "test", "--all-features"])

    npm_test = _read_npm_test_script(project_dir)
    if npm_test is not None:
        if "vitest" in npm_test:
            return ("vitest", ["npm", "test", "--", "--reporter=json"])
        if "jest" in npm_test:
            return ("jest", ["npm", "test", "--", "--json"])
        return ("generic", ["npm", "test"])

    return ("generic", [])
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_test_detector.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add core/health/test_detector.py tests/test_test_detector.py
git commit -m "feat(test_runner): add framework detector"
```

---

## Task 10: `TestRunner.run()` — happy path subprocess

**Files:**
- Modify: `core/health/test_runner.py` (add `TestRunner` class)
- Create: `tests/fixtures/test_runner_pytest/pyproject.toml`
- Create: `tests/fixtures/test_runner_pytest/tests/test_dummy.py`
- Modify: `tests/test_test_runner.py`

- [ ] **Step 1: Build the fixture repo**

Create `tests/fixtures/test_runner_pytest/pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create `tests/fixtures/test_runner_pytest/tests/test_dummy.py`:
```python
def test_passes():
    assert 1 + 1 == 2

def test_fails():
    assert 1 == 2
```

- [ ] **Step 2: Add the failing happy-path test**

Append to `tests/test_test_runner.py`:
```python
from pathlib import Path

from core.health.test_runner import TestRunner
from core.health.test_parsers import for_framework

FIXTURE_PYTEST = Path(__file__).parent / "fixtures" / "test_runner_pytest"


def test_runner_executes_pytest_fixture():
    runner = TestRunner(parser=for_framework("pytest"), timeout_s=30)
    run = runner.run(FIXTURE_PYTEST, ["pytest", "--tb=no", "-q"])
    assert run.framework_set_by_caller is False or True  # placeholder; see Step 3
    # The fixture has 1 pass and 1 fail.
    assert run.passed == 1
    assert run.failed == 1
    assert run.exit_code == 1
    assert run.timed_out is False
    assert run.duration_s > 0
    assert "1 failed" in run.output_tail or "1 passed" in run.output_tail
```

(The `framework_set_by_caller` line is a noop assertion — the runner doesn't decide framework names; the caller does. We pass `framework=...` in Step 3 below; remove that line if present.)

Replace the `framework_set_by_caller` line with:
```python
    assert run.framework == "pytest"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_test_runner.py::test_runner_executes_pytest_fixture -v`
Expected: FAIL with `AttributeError: type object 'TestRunner' has no attribute 'run'` (or `TypeError`).

- [ ] **Step 4: Implement `TestRunner` happy path**

Append to `core/health/test_runner.py`:
```python
import select
import subprocess
import time
from collections import deque
from pathlib import Path


class TestRunner:
    """Runs a test command in a subprocess, returns a `TestRun`.

    Sync. Knows nothing about Qt or DB. Call from a worker thread
    (e.g. `TestRunnerThread`) so it doesn't block the GUI.
    """

    _TAIL_LINES = 200
    _READ_INTERVAL_S = 0.1

    def __init__(self, parser: Parser, timeout_s: int = 600,
                 framework: str = "pytest"):
        self._parser = parser
        self._timeout = timeout_s
        self._framework = framework

    def run(self, project_dir: Path, cmd: list[str]) -> TestRun:
        started = time.time()
        deadline = time.monotonic() + self._timeout
        tail: deque[str] = deque(maxlen=self._TAIL_LINES)
        timed_out = False
        exit_code: int | None = None

        try:
            proc = subprocess.Popen(
                cmd, cwd=str(project_dir),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except FileNotFoundError as e:
            finished = time.time()
            return TestRun(
                project_dir=str(project_dir), framework=self._framework,
                command=list(cmd), started_at=started, finished_at=finished,
                duration_s=finished - started, exit_code=-1, timed_out=False,
                passed=None, failed=None, errors=None, skipped=None,
                output_tail=f"command not found: {e.filename or cmd[0]}",
            )
        except PermissionError as e:
            finished = time.time()
            return TestRun(
                project_dir=str(project_dir), framework=self._framework,
                command=list(cmd), started_at=started, finished_at=finished,
                duration_s=finished - started, exit_code=-1, timed_out=False,
                passed=None, failed=None, errors=None, skipped=None,
                output_tail=f"permission denied: {e.filename or cmd[0]}",
            )

        assert proc.stdout is not None
        while True:
            if time.monotonic() > deadline:
                proc.kill()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass  # zombie; record timeout anyway
                timed_out = True
                exit_code = None
                break
            ready, _, _ = select.select([proc.stdout], [], [], self._READ_INTERVAL_S)
            if ready:
                line = proc.stdout.readline()
                if line == "":  # EOF
                    proc.wait()
                    exit_code = proc.returncode
                    break
                tail.append(line.rstrip("\n"))
            elif proc.poll() is not None:
                # Drain remaining output.
                rest = proc.stdout.read() or ""
                for r in rest.splitlines():
                    tail.append(r)
                exit_code = proc.returncode
                break

        finished = time.time()
        output = "\n".join(tail)
        try:
            parsed = self._parser.parse(output, exit_code if exit_code is not None else -1)
        except Exception:
            parsed = ParseResult(passed=None, failed=None, errors=None, skipped=None)

        return TestRun(
            project_dir=str(project_dir), framework=self._framework,
            command=list(cmd), started_at=started, finished_at=finished,
            duration_s=finished - started,
            exit_code=exit_code, timed_out=timed_out,
            passed=parsed.passed, failed=parsed.failed,
            errors=parsed.errors, skipped=parsed.skipped,
            output_tail=output,
        )
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_test_runner.py::test_runner_executes_pytest_fixture -v`
Expected: PASS. (May take 2-5 s as it actually runs pytest in a subprocess.)

If pytest is not on PATH inside the test environment, switch the cmd to `[sys.executable, "-m", "pytest", ...]` in Step 2 and document that change.

- [ ] **Step 6: Run all parser/runner tests**

Run: `pytest tests/test_test_runner.py tests/test_test_parsers.py tests/test_test_detector.py -v`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add core/health/test_runner.py tests/fixtures/test_runner_pytest/ tests/test_test_runner.py
git commit -m "feat(test_runner): add TestRunner happy-path subprocess execution"
```

---

## Task 11: `TestRunner` timeout path

**Files:**
- Modify: `tests/test_test_runner.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_test_runner.py`:
```python
from core.health.test_parsers import for_framework as _for_framework


def test_runner_kills_on_timeout(tmp_path):
    runner = TestRunner(parser=_for_framework("generic"), timeout_s=1,
                        framework="generic")
    start = time.time()
    run = runner.run(tmp_path, ["sleep", "60"])
    elapsed = time.time() - start
    assert run.timed_out is True
    assert run.exit_code is None
    assert elapsed < 5  # killed within ~1s + 2s wait grace
```

(Add `import time` to the test file imports if not already there.)

- [ ] **Step 2: Run test**

Run: `pytest tests/test_test_runner.py::test_runner_kills_on_timeout -v`
Expected: PASS (the timeout logic is already in Task 10; this is verification it actually works under load).

If it FAILS because `sleep` isn't on Windows — the spec excludes Windows from v1, mark with `@pytest.mark.skipif(sys.platform == "win32", ...)`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_test_runner.py
git commit -m "test(test_runner): add timeout-kill verification"
```

---

## Task 12: `TestRunner` error paths (binary missing, big output, parser exception)

**Files:**
- Modify: `tests/test_test_runner.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_test_runner.py`:
```python
def test_runner_command_not_found(tmp_path):
    runner = TestRunner(parser=_for_framework("generic"), timeout_s=5,
                        framework="generic")
    run = runner.run(tmp_path, ["definitely-not-a-binary-12345"])
    assert run.exit_code == -1
    assert "not found" in run.output_tail.lower()


def test_runner_truncates_output_to_tail(tmp_path):
    """Subprocess prints 500 lines; we keep only the last 200."""
    runner = TestRunner(parser=_for_framework("generic"), timeout_s=10,
                        framework="generic")
    # Use python -c so it works cross-platform.
    import sys
    code = "for i in range(500): print(f'line-{i}')"
    run = runner.run(tmp_path, [sys.executable, "-c", code])
    assert run.exit_code == 0
    lines = run.output_tail.splitlines()
    assert len(lines) == 200
    assert lines[-1] == "line-499"
    assert lines[0] == "line-300"


def test_runner_swallows_parser_exceptions(tmp_path):
    """Parser raising must not crash the run."""
    class BadParser:
        def parse(self, output, exit_code):
            raise RuntimeError("boom")

    runner = TestRunner(parser=BadParser(), timeout_s=5, framework="generic")
    import sys
    run = runner.run(tmp_path, [sys.executable, "-c", "print('hi')"])
    assert run.exit_code == 0
    assert run.passed is None and run.failed is None
    assert "hi" in run.output_tail
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_test_runner.py -v`
Expected: All PASS — the implementation in Task 10 already handles these. If a test fails, fix the implementation in `core/health/test_runner.py` until it passes.

- [ ] **Step 3: Commit**

```bash
git add tests/test_test_runner.py
git commit -m "test(test_runner): cover command-not-found / output-truncation / parser-exception"
```

---

## Task 13: `TestRunnerPlugin`

**Files:**
- Create: `plugins/test_runner/__init__.py` (empty)
- Create: `plugins/test_runner/plugin.py`
- Create: `plugins/test_runner/collector.py`
- Create: `tests/test_test_runner_plugin.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_test_runner_plugin.py
"""Tests for TestRunnerPlugin."""
import asyncio
from unittest.mock import patch

import pytest

from core.history import HistoryDB
from plugins.test_runner.plugin import TestRunnerPlugin


@pytest.fixture
def db():
    db = HistoryDB(":memory:")
    db.init()
    yield db
    db.close()


def test_plugin_metadata():
    plugin = TestRunnerPlugin(config={})
    assert plugin.name == "Tests"
    assert plugin.icon == "🧪"


def test_plugin_migrate_is_noop():
    """test_runs is owned by HistoryDB; plugin.migrate must not raise and
    must not touch the aiosqlite DB it gets passed."""
    plugin = TestRunnerPlugin(config={})
    asyncio.run(plugin.migrate(db=None))  # passing None is fine for a no-op


def test_plugin_collect_is_noop():
    plugin = TestRunnerPlugin(config={})
    asyncio.run(plugin.collect(db=None))


def test_plugin_render_returns_qwidget():
    plugin = TestRunnerPlugin(config={})
    w = plugin.render()
    # Don't import QWidget at module top — keeps the test runnable in
    # contexts where Qt isn't installed; here we just check the type name.
    assert type(w).__name__ in ("QWidget", "QFrame")


def test_get_alerts_returns_warning_when_last_run_failed(db):
    db.save_test_run({
        "project_dir": "/tmp/proj", "framework": "pytest",
        "command": ["pytest"], "started_at": 1.0, "finished_at": 2.0,
        "duration_s": 1.0, "exit_code": 1, "timed_out": False,
        "passed": 5, "failed": 2, "errors": 0, "skipped": 0,
        "output_tail": "2 failed",
    })
    plugin = TestRunnerPlugin(config={
        "plugins": {"test_runner": {"project_dir": "/tmp/proj"}}
    })
    with patch.object(plugin, "_history_db", return_value=db):
        alerts = asyncio.run(plugin.get_alerts(db=None))
    assert len(alerts) == 1
    assert alerts[0].severity == "warning"
    assert "test" in alerts[0].title.lower()


def test_get_alerts_empty_when_last_run_passed(db):
    db.save_test_run({
        "project_dir": "/tmp/proj", "framework": "pytest",
        "command": ["pytest"], "started_at": 1.0, "finished_at": 2.0,
        "duration_s": 1.0, "exit_code": 0, "timed_out": False,
        "passed": 5, "failed": 0, "errors": 0, "skipped": 0,
        "output_tail": "all good",
    })
    plugin = TestRunnerPlugin(config={
        "plugins": {"test_runner": {"project_dir": "/tmp/proj"}}
    })
    with patch.object(plugin, "_history_db", return_value=db):
        alerts = asyncio.run(plugin.get_alerts(db=None))
    assert alerts == []


def test_get_alerts_empty_when_no_runs_yet(db):
    plugin = TestRunnerPlugin(config={
        "plugins": {"test_runner": {"project_dir": "/tmp/proj"}}
    })
    with patch.object(plugin, "_history_db", return_value=db):
        alerts = asyncio.run(plugin.get_alerts(db=None))
    assert alerts == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_runner_plugin.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'plugins.test_runner.plugin'`.

- [ ] **Step 3: Create plugin package + collector re-export**

Create `plugins/test_runner/__init__.py`:
```python
"""Background test runner plugin."""
```

Create `plugins/test_runner/collector.py`:
```python
"""Re-export framework detection for symmetry with docker_monitor/port_map."""
from core.health.test_detector import detect_framework

__all__ = ["detect_framework"]
```

- [ ] **Step 4: Implement the plugin**

Create `plugins/test_runner/plugin.py`:
```python
"""TestRunnerPlugin — fulfils the Plugin(ABC) contract.

Storage lives in HistoryDB (sync sqlite3, see Task 18 in the original
reliability spec for the threading work). The aiosqlite `db` argument
the contract passes is intentionally ignored — `migrate()` is a no-op
and `collect()` is too, because runs are event-triggered (button /
save-point / watch), not collected on a timer.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from core.history import HistoryDB
from core.plugin import Alert, Plugin

if TYPE_CHECKING:
    from textual.widget import Widget  # legacy contract type


class TestRunnerPlugin(Plugin):
    name = "Tests"
    icon = "🧪"

    def __init__(self, config: dict):
        self._config = config.get("plugins", {}).get("test_runner", {}) or {}
        self._project_dir: str | None = self._config.get("project_dir")

    async def migrate(self, db) -> None:  # noqa: ARG002
        """No-op. test_runs table is owned by HistoryDB."""

    async def collect(self, db) -> None:  # noqa: ARG002
        """No-op. Runs fire on user/save-point/watch triggers, not on a timer."""

    async def get_alerts(self, db) -> list[Alert]:  # noqa: ARG002
        if not self._project_dir:
            return []
        history = self._history_db()
        last = await asyncio.to_thread(history.get_last_test_run, self._project_dir)
        if last is None:
            return []
        if last["timed_out"] or (last.get("failed") or 0) > 0:
            failed = last.get("failed") or 0
            total = (last.get("passed") or 0) + failed + (last.get("errors") or 0)
            title = "Tests timed out" if last["timed_out"] else f"Tests failing ({failed}/{total})"
            return [Alert(
                source="tests", severity="warning",
                title=title,
                message=f"Last run finished with exit code {last['exit_code']}",
            )]
        return []

    def render(self):
        # PyQt5 GUI doesn't use this. Placeholder fulfils the Plugin contract.
        from PyQt5.QtWidgets import QWidget
        return QWidget()

    def _history_db(self) -> HistoryDB:
        # Indirection so tests can patch it.
        return HistoryDB()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_test_runner_plugin.py -v`
Expected: 7 PASS.

- [ ] **Step 6: Commit**

```bash
git add plugins/test_runner/__init__.py plugins/test_runner/plugin.py plugins/test_runner/collector.py tests/test_test_runner_plugin.py
git commit -m "feat(plugins): add TestRunnerPlugin with HistoryDB-backed alerts"
```

---

## Task 14: `PluginRegistry`

**Files:**
- Create: `core/plugin_loader.py`
- Create: `tests/test_plugin_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plugin_loader.py
"""Tests for PluginRegistry."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from core.plugin import Alert
from core.plugin_loader import PluginRegistry


def test_loads_only_enabled_plugins(tmp_path):
    config = {"plugins": {"test_runner": True}}
    reg = PluginRegistry(config=config, db_path=tmp_path / "x.db")
    assert len(reg._plugins) == 1
    assert type(reg._plugins[0]).__name__ == "TestRunnerPlugin"


def test_disabled_plugin_not_loaded(tmp_path):
    config = {"plugins": {"test_runner": False}}
    reg = PluginRegistry(config=config, db_path=tmp_path / "x.db")
    assert reg._plugins == []


def test_unknown_key_ignored(tmp_path):
    config = {"plugins": {"definitely_not_a_plugin": True}}
    reg = PluginRegistry(config=config, db_path=tmp_path / "x.db")
    assert reg._plugins == []


def test_start_calls_migrate_on_each_plugin(tmp_path):
    config = {"plugins": {"test_runner": True}}
    reg = PluginRegistry(config=config, db_path=tmp_path / "x.db")
    plugin = reg._plugins[0]
    plugin.migrate = AsyncMock()
    reg.start()
    plugin.migrate.assert_awaited_once()


def test_collect_all_aggregates_alerts(tmp_path):
    config = {"plugins": {"test_runner": True}}
    reg = PluginRegistry(config=config, db_path=tmp_path / "x.db")
    plugin = reg._plugins[0]
    plugin.collect = AsyncMock()
    plugin.get_alerts = AsyncMock(return_value=[
        Alert(source="tests", severity="warning", title="t", message="m"),
    ])
    alerts = reg.collect_all()
    assert len(alerts) == 1
    assert alerts[0].title == "t"


def test_failing_plugin_does_not_break_others(tmp_path, caplog):
    """A plugin that raises in get_alerts must not propagate; others run."""
    config = {"plugins": {"test_runner": True}}
    reg = PluginRegistry(config=config, db_path=tmp_path / "x.db")
    bad = reg._plugins[0]
    bad.collect = AsyncMock()
    bad.get_alerts = AsyncMock(side_effect=RuntimeError("boom"))
    alerts = reg.collect_all()
    assert alerts == []
    assert any("boom" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_plugin_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.plugin_loader'`.

- [ ] **Step 3: Implement the registry**

```python
# core/plugin_loader.py
"""Minimal plugin registry — bridges async Plugin(ABC) contract to sync callers.

For v1 only `test_runner` is wired here. Adding docker_monitor / port_map /
security_scan to `_IMPORTS` migrates them off the direct-import path in
gui/app/threads.py — that's a follow-up, not part of Task 17.
"""
from __future__ import annotations

import asyncio
import importlib
import logging
from pathlib import Path

from core.plugin import Alert, Plugin

log = logging.getLogger("fartrun.plugin_loader")

_IMPORTS: dict[str, str] = {
    "test_runner": "plugins.test_runner.plugin.TestRunnerPlugin",
}


class PluginRegistry:
    def __init__(self, config: dict, db_path: Path):
        self._config = config
        self._db_path = db_path
        self._plugins: list[Plugin] = self._load_enabled()

    def _load_enabled(self) -> list[Plugin]:
        enabled = self._config.get("plugins", {}) or {}
        out: list[Plugin] = []
        for key, dotted in _IMPORTS.items():
            if not enabled.get(key):
                continue
            module_path, _, cls_name = dotted.rpartition(".")
            try:
                module = importlib.import_module(module_path)
                cls = getattr(module, cls_name)
                out.append(cls(config=self._config))
            except Exception as e:
                log.warning("Failed to load plugin %s: %s", key, e)
        return out

    def start(self) -> None:
        """Run migrate() for every loaded plugin once at startup."""
        asyncio.run(self._migrate_all())

    async def _migrate_all(self) -> None:
        # Real db connection plumbing isn't needed for v1 plugins (test_runner
        # ignores the db arg). When wiring more plugins, open an aiosqlite
        # connection here and pass it in.
        for p in self._plugins:
            try:
                await p.migrate(db=None)
            except Exception as e:
                log.warning("Plugin %s migrate failed: %s", type(p).__name__, e)

    def collect_all(self) -> list[Alert]:
        """Run collect() then get_alerts() for every plugin. Returns aggregated alerts."""
        return asyncio.run(self._collect_and_alert())

    async def _collect_and_alert(self) -> list[Alert]:
        alerts: list[Alert] = []
        for p in self._plugins:
            try:
                await p.collect(db=None)
            except Exception as e:
                log.warning("Plugin %s collect failed: %s", type(p).__name__, e)
            try:
                got = await p.get_alerts(db=None)
                alerts.extend(got)
            except Exception as e:
                log.warning("Plugin %s get_alerts failed: %s", type(p).__name__, e)
        return alerts
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_plugin_loader.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add core/plugin_loader.py tests/test_plugin_loader.py
git commit -m "feat(plugin_loader): add minimal PluginRegistry async/sync bridge"
```

---

## Task 15: `TestRunnerThread` (Qt wrapper)

**Files:**
- Create: `gui/pages/health/test_runner_thread.py`
- Create: `tests/test_test_runner_thread.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_test_runner_thread.py
"""Tests for TestRunnerThread (Qt wrapper around TestRunner)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtCore import QCoreApplication, QEventLoop, QTimer

from core.health.test_runner import TestRun
from gui.pages.health.test_runner_thread import TestRunnerThread


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


def test_thread_emits_finished_run_signal(qapp, tmp_path):
    fake_run = TestRun(
        project_dir=str(tmp_path), framework="pytest", command=["x"],
        started_at=1.0, finished_at=2.0, duration_s=1.0,
        exit_code=0, timed_out=False,
        passed=1, failed=0, errors=0, skipped=0, output_tail="ok",
    )
    fake_runner = MagicMock()
    fake_runner.run.return_value = fake_run

    thread = TestRunnerThread(fake_runner, tmp_path, ["x"])
    received = []
    thread.finished_run.connect(lambda r: received.append(r))

    loop = QEventLoop()
    thread.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)  # safety
    thread.start()
    loop.exec_()

    assert len(received) == 1
    assert received[0].passed == 1
    fake_runner.run.assert_called_once_with(tmp_path, ["x"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_runner_thread.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.pages.health.test_runner_thread'`.

- [ ] **Step 3: Implement the thread**

```python
# gui/pages/health/test_runner_thread.py
"""QThread wrapper around the sync TestRunner.

Emits `finished_run(TestRun)` once when the subprocess finishes (or is
killed by timeout). Owns no state beyond the runner + invocation args.
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from core.health.test_runner import TestRun, TestRunner


class TestRunnerThread(QThread):
    finished_run = pyqtSignal(object)  # emits TestRun

    def __init__(self, runner: TestRunner, project_dir: Path,
                 cmd: list[str], parent=None):
        super().__init__(parent)
        self._runner = runner
        self._project_dir = project_dir
        self._cmd = cmd

    def run(self) -> None:
        result = self._runner.run(self._project_dir, self._cmd)
        self.finished_run.emit(result)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_test_runner_thread.py -v`
Expected: PASS.

If your CI doesn't have a display server, ensure `QT_QPA_PLATFORM=offscreen` is set when running Qt tests (already common in this repo's `conftest.py` if other Qt tests run there — verify by skimming `tests/conftest.py`).

- [ ] **Step 5: Commit**

```bash
git add gui/pages/health/test_runner_thread.py tests/test_test_runner_thread.py
git commit -m "feat(gui): add TestRunnerThread QThread wrapper"
```

---

## Task 16: `HealthPage` Tests section + manual run + coalescing

**Files:**
- Modify: `gui/pages/health/page.py` (add `_build_tests_section`, `_on_run_tests`, `_on_test_finished`, attrs)
- Create: `tests/test_test_runner_coalescing.py`
- Modify: `i18n/en.py` and `i18n/ua.py` (add new strings)

- [ ] **Step 1: Add i18n strings**

Append to `i18n/en.py` (alongside existing `health_*` keys):
```python
    "tests_section_title": "Tests",
    "tests_status_idle": "No tests run yet",
    "tests_status_running": "running {seconds}s…",
    "tests_status_running_queued": "running {seconds}s… (queued: re-run)",
    "tests_status_passed": "passed in {duration} ✅",
    "tests_status_failed_counts": "failed: {failed} of {total} ❌",
    "tests_status_failed_unknown": "failed (counts unknown) ❌",
    "tests_status_timed_out": "timed out after {duration} ⏱",
    "tests_status_error": "{message}",
    "tests_btn_run": "Run tests",
    "tests_btn_history": "Show history",
    "tests_no_framework": "No test framework detected. Set [tests] command in config.toml.",
```

Mirror the same keys in `i18n/ua.py` with Ukrainian translations.

- [ ] **Step 2: Write the failing coalescing test**

```python
# tests/test_test_runner_coalescing.py
"""Tests that two trigger calls during an in-flight run produce exactly
one TestRun row and one re-run, never queue more than one pending."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def test_coalescing_two_triggers_one_pending(qapp, tmp_path, monkeypatch):
    from gui.pages.health import page as page_mod
    from core.health.test_runner import TestRun

    page = page_mod.HealthPage()
    page._project_dir = str(tmp_path)
    page._config = {"tests": {"command": "", "timeout_s": 600, "history_limit": 100}}

    # Monkeypatch detect_framework so we don't read tmp_path's filesystem.
    monkeypatch.setattr(
        "gui.pages.health.page.detect_framework",
        lambda d: ("generic", ["true"]),
    )

    # Replace TestRunnerThread with a stub that doesn't actually start a thread.
    started_count = {"n": 0}
    pending_threads = []

    class StubThread:
        def __init__(self, runner, project_dir, cmd, parent=None):
            self._runner = runner
            self._project_dir = project_dir
            self._cmd = cmd
            self._slots = []
        def isRunning(self):
            return self in pending_threads
        def start(self):
            started_count["n"] += 1
            pending_threads.append(self)
        @property
        def finished_run(self):
            outer = self
            class _Sig:
                def connect(self_inner, slot):
                    outer._slots.append(slot)
            return _Sig()
        def fire_finished(self, run):
            pending_threads.remove(self)
            for slot in self._slots:
                slot(run)

    monkeypatch.setattr("gui.pages.health.page.TestRunnerThread", StubThread)
    # Patch HistoryDB.save_test_run to a no-op (we're not testing persistence).
    monkeypatch.setattr(
        "gui.pages.health.page.HistoryDB",
        lambda: MagicMock(save_test_run=lambda r: 1, get_last_test_run=lambda d: None,
                          get_test_runs=lambda d, limit=10: []),
    )

    page._on_run_tests()           # trigger #1 — starts run
    page._on_run_tests()           # trigger #2 — sets _needs_rerun
    page._on_run_tests()           # trigger #3 — _needs_rerun already True; no-op
    assert started_count["n"] == 1
    assert page._needs_rerun is True
    assert len(pending_threads) == 1

    # Simulate first thread finishing.
    fake_run = TestRun(
        project_dir=str(tmp_path), framework="generic", command=["true"],
        started_at=1.0, finished_at=2.0, duration_s=1.0,
        exit_code=0, timed_out=False,
        passed=None, failed=None, errors=None, skipped=None, output_tail="",
    )
    pending_threads[0].fire_finished(fake_run)

    # Coalesced re-run must have started.
    assert started_count["n"] == 2
    assert page._needs_rerun is False
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_test_runner_coalescing.py -v`
Expected: FAIL — likely `AttributeError: '_on_run_tests'` or similar, because we haven't built the section yet.

- [ ] **Step 4: Modify `HealthPage` — add attrs, section builder, slots**

Open `gui/pages/health/page.py`. Add imports near the top (after existing imports):
```python
from core.health.test_detector import detect_framework
from core.health.test_runner import TestRunner
from core.health.test_parsers import for_framework
from core.history import HistoryDB
from gui.pages.health.test_runner_thread import TestRunnerThread
from PyQt5.QtCore import QTimer
```

In `HealthPage.__init__`, after the existing attribute initialization, add:
```python
        # Test runner state
        self._test_thread: TestRunnerThread | None = None
        self._needs_rerun: bool = False
        self._test_status_label = None
        self._test_run_button = None
        self._test_elapsed_timer: QTimer | None = None
        self._test_run_started_monotonic: float | None = None
```

In `_build_ui`, after the existing health findings section is added but before the footer, call:
```python
        layout.addWidget(self._build_tests_section())
```

Then add new methods to `HealthPage`:
```python
    def _build_tests_section(self) -> QGroupBox:
        from PyQt5.QtWidgets import QGroupBox, QHBoxLayout, QVBoxLayout
        box = QGroupBox(_t("tests_section_title"))
        box.setStyleSheet(GROUP_STYLE)
        v = QVBoxLayout(box)

        row = QHBoxLayout()
        self._test_status_label = QLabel(_t("tests_status_idle"))
        self._test_status_label.setFont(FONT_UI)
        row.addWidget(self._test_status_label, stretch=1)

        self._test_run_button = QPushButton(_t("tests_btn_run"))
        self._test_run_button.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self._test_run_button.clicked.connect(self._on_run_tests)
        row.addWidget(self._test_run_button)

        v.addLayout(row)
        return box

    def _on_run_tests(self) -> None:
        if self._test_thread is not None and self._test_thread.isRunning():
            self._needs_rerun = True
            self._update_test_status_running()
            return
        if not self._project_dir:
            return
        framework, default_cmd = detect_framework(Path(self._project_dir))
        override = (self._config.get("tests", {}) or {}).get("command", "") or ""
        cmd = override.split() if override.strip() else default_cmd
        if not cmd:
            self._test_status_label.setText(_t("tests_no_framework"))
            return

        timeout = int((self._config.get("tests", {}) or {}).get("timeout_s", 600))
        runner = TestRunner(parser=for_framework(framework),
                            timeout_s=timeout, framework=framework)
        thread = TestRunnerThread(runner, Path(self._project_dir), cmd)
        thread.finished_run.connect(self._on_test_finished)
        self._test_thread = thread
        self._test_run_button.setEnabled(False)
        self._needs_rerun = False
        import time as _time
        self._test_run_started_monotonic = _time.monotonic()
        self._update_test_status_running()
        if self._test_elapsed_timer is None:
            self._test_elapsed_timer = QTimer(self)
            self._test_elapsed_timer.timeout.connect(self._update_test_status_running)
        self._test_elapsed_timer.start(1000)
        thread.start()

    def _update_test_status_running(self) -> None:
        if self._test_status_label is None or self._test_run_started_monotonic is None:
            return
        import time as _time
        elapsed = int(_time.monotonic() - self._test_run_started_monotonic)
        key = "tests_status_running_queued" if self._needs_rerun else "tests_status_running"
        self._test_status_label.setText(_t(key).format(seconds=elapsed))

    def _on_test_finished(self, run) -> None:
        if self._test_elapsed_timer is not None:
            self._test_elapsed_timer.stop()
        try:
            HistoryDB().save_test_run(self._test_run_to_dict(run))
        except Exception as e:
            log.warning("save_test_run failed: %s", e)

        self._test_thread = None
        self._test_run_started_monotonic = None
        self._test_run_button.setEnabled(True)
        self._render_test_status_for(run)

        if self._needs_rerun:
            self._needs_rerun = False
            self._on_run_tests()

    @staticmethod
    def _test_run_to_dict(run) -> dict:
        return {
            "project_dir": run.project_dir, "framework": run.framework,
            "command": run.command, "started_at": run.started_at,
            "finished_at": run.finished_at, "duration_s": run.duration_s,
            "exit_code": run.exit_code, "timed_out": run.timed_out,
            "passed": run.passed, "failed": run.failed,
            "errors": run.errors, "skipped": run.skipped,
            "output_tail": run.output_tail,
        }

    def _render_test_status_for(self, run) -> None:
        if self._test_status_label is None:
            return
        if run.timed_out:
            self._test_status_label.setText(
                _t("tests_status_timed_out").format(duration=_format_duration(run.duration_s))
            )
            return
        if run.exit_code in (0, None) and not run.timed_out and run.exit_code != -1:
            self._test_status_label.setText(
                _t("tests_status_passed").format(duration=_format_duration(run.duration_s))
            )
            return
        if run.exit_code == -1:
            self._test_status_label.setText(
                _t("tests_status_error").format(message=run.output_tail.splitlines()[0] if run.output_tail else "error")
            )
            return
        if run.passed is None:
            self._test_status_label.setText(_t("tests_status_failed_unknown"))
            return
        total = (run.passed or 0) + (run.failed or 0) + (run.errors or 0)
        self._test_status_label.setText(
            _t("tests_status_failed_counts").format(failed=run.failed or 0, total=total)
        )
```

At module bottom (or near other helpers) add:
```python
def _format_duration(seconds: float | None) -> str:
    if not seconds:
        return "0s"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60}s"
```

(Also add `from pathlib import Path` to imports if not already present.)

- [ ] **Step 5: Run the coalescing test**

Run: `pytest tests/test_test_runner_coalescing.py -v`
Expected: PASS.

- [ ] **Step 6: Run full suite to confirm no regressions**

Run: `pytest tests/ -x --tb=short -q`
Expected: All previously-green tests still pass + the new ones.

- [ ] **Step 7: Commit**

```bash
git add gui/pages/health/page.py tests/test_test_runner_coalescing.py i18n/en.py i18n/ua.py
git commit -m "feat(health): add Tests section with manual run and coalescing"
```

---

## Task 17: save-point trigger (opt-in)

**Files:**
- Modify: `gui/pages/health/page.py` (add `_on_save_point_created`)
- Modify: `gui/app/main.py` (wire signal from `SavePointsPage` to `HealthPage._on_save_point_created`)
- Modify: `tests/test_test_runner_coalescing.py` (add a save-point trigger test)

- [ ] **Step 1: Add failing test**

Append to `tests/test_test_runner_coalescing.py`:
```python
def test_save_point_trigger_runs_when_enabled(qapp, tmp_path, monkeypatch):
    from gui.pages.health import page as page_mod

    page = page_mod.HealthPage()
    page._project_dir = str(tmp_path)
    page._config = {"tests": {"trigger_on_save_point": True, "command": "", "timeout_s": 600}}
    started = {"n": 0}
    monkeypatch.setattr(page, "_on_run_tests", lambda: started.update(n=started["n"] + 1))
    page._on_save_point_created(str(tmp_path))
    assert started["n"] == 1


def test_save_point_trigger_silent_when_disabled(qapp, tmp_path, monkeypatch):
    from gui.pages.health import page as page_mod

    page = page_mod.HealthPage()
    page._project_dir = str(tmp_path)
    page._config = {"tests": {"trigger_on_save_point": False}}
    started = {"n": 0}
    monkeypatch.setattr(page, "_on_run_tests", lambda: started.update(n=started["n"] + 1))
    page._on_save_point_created(str(tmp_path))
    assert started["n"] == 0


def test_save_point_trigger_ignores_other_projects(qapp, tmp_path, monkeypatch):
    from gui.pages.health import page as page_mod

    page = page_mod.HealthPage()
    page._project_dir = str(tmp_path)
    page._config = {"tests": {"trigger_on_save_point": True}}
    started = {"n": 0}
    monkeypatch.setattr(page, "_on_run_tests", lambda: started.update(n=started["n"] + 1))
    page._on_save_point_created("/some/other/project")
    assert started["n"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_runner_coalescing.py -v -k save_point`
Expected: FAIL with `AttributeError: 'HealthPage' object has no attribute '_on_save_point_created'`.

- [ ] **Step 3: Implement the slot**

Append to `HealthPage` in `gui/pages/health/page.py`:
```python
    def _on_save_point_created(self, project_dir: str) -> None:
        if not (self._config.get("tests", {}) or {}).get("trigger_on_save_point"):
            return
        if project_dir != self._project_dir:
            return
        self._on_run_tests()
```

- [ ] **Step 4: Wire the signal in `MainWindow`**

In `gui/app/main.py`, find where `SavePointsPage` is instantiated. Add a signal connection (locate a `pyqtSignal(str)` named `save_point_created` on `SavePointsPage` if it exists; if it doesn't, add one and emit it from the existing save-point success path).

Then in `MainWindow.__init__` after both pages exist:
```python
self._save_points_page.save_point_created.connect(
    self._health_page._on_save_point_created
)
```

If `SavePointsPage` doesn't have such a signal yet, add it as the smallest viable change:
1. In `gui/pages/save_points_page.py`, declare `save_point_created = pyqtSignal(str)` on the class.
2. After a successful save, call `self.save_point_created.emit(self._project_dir)`.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_test_runner_coalescing.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add gui/pages/health/page.py gui/app/main.py gui/pages/save_points_page.py tests/test_test_runner_coalescing.py
git commit -m "feat(health): wire save-point trigger to test runner (opt-in)"
```

---

## Task 18: watch mode (opt-in, requires `watchdog`)

**Files:**
- Modify: `gui/pages/health/page.py` (add `_start_watch_observer`, `_stop_watch_observer`, debounce)
- Modify: `tests/test_test_runner_coalescing.py` (add a debounce test using mocked watchdog)

- [ ] **Step 1: Add failing test**

Append to `tests/test_test_runner_coalescing.py`:
```python
def test_watch_debounce_collapses_burst(qapp, tmp_path, monkeypatch):
    from gui.pages.health import page as page_mod

    page = page_mod.HealthPage()
    page._project_dir = str(tmp_path)
    page._config = {"tests": {"watch": True, "debounce_ms": 50}}
    started = {"n": 0}
    monkeypatch.setattr(page, "_on_run_tests", lambda: started.update(n=started["n"] + 1))

    # Fire 5 events back-to-back; only one run after debounce window.
    for _ in range(5):
        page._on_watch_event()

    from PyQt5.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(200, loop.quit)
    loop.exec_()

    assert started["n"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_runner_coalescing.py -v -k watch`
Expected: FAIL with `AttributeError: '_on_watch_event'`.

- [ ] **Step 3: Implement watch debounce + observer**

Append to `HealthPage`:
```python
    def _on_watch_event(self) -> None:
        if not (self._config.get("tests", {}) or {}).get("watch"):
            return
        debounce = int((self._config.get("tests", {}) or {}).get("debounce_ms", 2000))
        if not hasattr(self, "_watch_debounce_timer") or self._watch_debounce_timer is None:
            from PyQt5.QtCore import QTimer
            self._watch_debounce_timer = QTimer(self)
            self._watch_debounce_timer.setSingleShot(True)
            self._watch_debounce_timer.timeout.connect(self._on_run_tests)
        self._watch_debounce_timer.start(debounce)

    def _start_watch_observer(self) -> None:
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            log.info("watchdog not installed; watch mode disabled")
            return
        if not self._project_dir:
            return
        cfg = self._config.get("tests", {}) or {}
        watch_paths = cfg.get("watch_paths") or ["."]
        excludes = set(cfg.get("watch_exclude") or [])

        page = self
        class _Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.is_directory:
                    return
                p = event.src_path
                if any(part in excludes for part in Path(p).parts):
                    return
                # watchdog runs in its own thread; QTimer.singleShot is Qt-safe
                # but we want to use the same debounce path — emit via signal
                # would need a pyqtSignal; for simplicity bounce through QTimer.
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(0, page._on_watch_event)

        self._watch_observer = Observer()
        for wp in watch_paths:
            self._watch_observer.schedule(_Handler(), str(Path(self._project_dir) / wp), recursive=True)
        self._watch_observer.start()

    def _stop_watch_observer(self) -> None:
        obs = getattr(self, "_watch_observer", None)
        if obs is not None:
            obs.stop()
            obs.join(timeout=2)
            self._watch_observer = None
```

Wire `_start_watch_observer()` from `set_project_dir()` (find the existing method and append a call at the end). Wire `_stop_watch_observer()` in `closeEvent` if `HealthPage` has one, otherwise add:
```python
    def closeEvent(self, event):
        self._stop_watch_observer()
        super().closeEvent(event)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_test_runner_coalescing.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/pages/health/page.py tests/test_test_runner_coalescing.py
git commit -m "feat(health): add watch-mode debounce trigger (opt-in)"
```

---

## Task 19: Settings UI Tests group + config defaults

**Files:**
- Modify: `gui/pages/settings.py` (add Tests group)
- Modify: `config.toml` (add `[plugins] test_runner = true` and `[tests]`)
- Modify: `i18n/en.py`, `i18n/ua.py` (add settings strings)

- [ ] **Step 1: Add config defaults**

Append to `config.toml`:
```toml
[plugins]
test_runner = true

[tests]
command = ""
timeout_s = 600
trigger_on_save_point = false
watch = false
watch_paths = ["."]
watch_exclude = [".git", "node_modules", "target", "__pycache__", ".venv", "dist"]
debounce_ms = 2000
history_limit = 100
```

(If `[plugins]` already exists in config.toml in some other shape, merge — do not duplicate the section header.)

- [ ] **Step 2: Add i18n strings**

To `i18n/en.py`:
```python
    "settings_tests_group": "Tests",
    "settings_tests_save_point": "Run tests after each save-point",
    "settings_tests_watch": "Watch files and re-run automatically",
    "settings_tests_watch_disabled": "Install `watchdog` to enable: pip install watchdog",
    "settings_tests_command": "Override command",
    "settings_tests_command_placeholder": "auto-detected (pytest / cargo test / npm test)",
    "settings_tests_timeout": "Timeout (seconds)",
```

Mirror in `i18n/ua.py`.

- [ ] **Step 3: Add the Tests group to Settings page**

Open `gui/pages/settings.py`. Find an existing `QGroupBox` constructor and use it as a template. After the last group is added but before the save button, add:

```python
def _build_tests_group(self) -> QGroupBox:
    from PyQt5.QtWidgets import (
        QCheckBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
        QSpinBox, QVBoxLayout,
    )
    box = QGroupBox(_t("settings_tests_group"))
    v = QVBoxLayout(box)

    self._cb_tests_save_point = QCheckBox(_t("settings_tests_save_point"))
    self._cb_tests_save_point.setChecked(
        bool(self._config.get("tests", {}).get("trigger_on_save_point", False))
    )
    v.addWidget(self._cb_tests_save_point)

    self._cb_tests_watch = QCheckBox(_t("settings_tests_watch"))
    self._cb_tests_watch.setChecked(
        bool(self._config.get("tests", {}).get("watch", False))
    )
    try:
        import watchdog  # noqa: F401
    except ImportError:
        self._cb_tests_watch.setEnabled(False)
        self._cb_tests_watch.setToolTip(_t("settings_tests_watch_disabled"))
    v.addWidget(self._cb_tests_watch)

    cmd_row = QHBoxLayout()
    cmd_row.addWidget(QLabel(_t("settings_tests_command") + ":"))
    self._le_tests_cmd = QLineEdit(self._config.get("tests", {}).get("command", ""))
    self._le_tests_cmd.setPlaceholderText(_t("settings_tests_command_placeholder"))
    cmd_row.addWidget(self._le_tests_cmd)
    v.addLayout(cmd_row)

    timeout_row = QHBoxLayout()
    timeout_row.addWidget(QLabel(_t("settings_tests_timeout") + ":"))
    self._sb_tests_timeout = QSpinBox()
    self._sb_tests_timeout.setRange(10, 7200)
    self._sb_tests_timeout.setValue(int(self._config.get("tests", {}).get("timeout_s", 600)))
    timeout_row.addWidget(self._sb_tests_timeout)
    timeout_row.addStretch()
    v.addLayout(timeout_row)

    return box
```

Call `layout.addWidget(self._build_tests_group())` from `_build_ui()`.

In the existing save handler (find the method that writes config back to `config.toml`), add:
```python
self._config.setdefault("tests", {})
self._config["tests"]["trigger_on_save_point"] = self._cb_tests_save_point.isChecked()
self._config["tests"]["watch"] = self._cb_tests_watch.isChecked()
self._config["tests"]["command"] = self._le_tests_cmd.text()
self._config["tests"]["timeout_s"] = self._sb_tests_timeout.value()
```

- [ ] **Step 4: Smoke-launch the GUI to confirm the group renders**

Run:
```bash
source .venv/bin/activate
QT_QPA_PLATFORM=offscreen python -c "
from PyQt5.QtWidgets import QApplication
import sys
app = QApplication(sys.argv)
from gui.pages.settings import SettingsPage
p = SettingsPage()
p.set_config({'tests': {}})
print('OK')
"
```
Expected: prints `OK` with no exception.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -x --tb=short -q`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add gui/pages/settings.py config.toml i18n/en.py i18n/ua.py
git commit -m "feat(settings): add Tests group with save-point/watch/override/timeout"
```

---

## Task 20: wire `PluginRegistry` into `MainWindow` periodic loop

**Files:**
- Modify: `gui/app/main.py` (instantiate registry, call `start()` once, wire `collect_all()` into existing alert poll)

- [ ] **Step 1: Locate the existing periodic poll**

Open `gui/app/main.py`. Find where docker/port collectors are polled (the `gui/app/threads.py` loop or whichever timer triggers them). Note the cadence and the alert sink used.

- [ ] **Step 2: Add registry instantiation**

In `MainWindow.__init__`, after config is loaded:
```python
from core.plugin_loader import PluginRegistry
from core.platform import get_platform

self._plugin_registry = PluginRegistry(
    config=self._config,
    db_path=get_platform().data_dir() / "history.db",
)
self._plugin_registry.start()
```

When the user picks a project, set the project_dir on the test_runner plugin so `get_alerts` knows what to read:
```python
for p in self._plugin_registry._plugins:
    if type(p).__name__ == "TestRunnerPlugin":
        p._project_dir = self._current_project_dir
```
(Wrap in try/except since `_plugins` is private — acceptable for v1, follow-up task can add a public setter on the registry.)

- [ ] **Step 3: Hook into the periodic alert sink**

Find the existing `QThread` (likely `BackgroundCollectorThread` in `gui/app/threads.py`) that runs every `refresh_interval` seconds and pushes alerts to the status bar / sound. After the existing alert assembly, append:
```python
plugin_alerts = self._registry.collect_all()
all_alerts.extend(plugin_alerts)
```
You may need to pass the registry into the thread's constructor.

- [ ] **Step 4: Manual verification**

Run:
```bash
source .venv/bin/activate
QT_QPA_PLATFORM=offscreen timeout 5 python -m gui.app.main || true
```
Expected: process starts and exits cleanly after 5s with no Python tracebacks.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -x --tb=short -q`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add gui/app/main.py gui/app/threads.py
git commit -m "feat(app): wire PluginRegistry into MainWindow + periodic alert sink"
```

---

## Task 21: smoke test on this repo + docs

**Files:**
- (None — manual verification + documenting the smoke procedure in the spec.)

- [ ] **Step 1: Get baseline pytest count**

Run:
```bash
source .venv/bin/activate
pytest -q tests/ 2>&1 | tail -3
```
Note the total (let `N` be that number).

- [ ] **Step 2: Launch GUI**

Run:
```bash
source .venv/bin/activate
python -m gui.app.main &
GUI_PID=$!
sleep 3
```
- [ ] **Step 3: Manual UI walkthrough**

In the running GUI:
1. Open the project selector and pick `/home/dchuprina/claude-monitor`.
2. Switch to the Health page.
3. Confirm "Tests" group is visible with status "No tests run yet".
4. Click "Run tests".
5. Expected: status switches to "running 0s…" → "running 1s…" → … → final state shows "passed in <duration>" with the count matching `N` from Step 1, OR "failed: X of <N>" if there are real failures.
6. Open Settings → Tests group and confirm Run-on-save-point unchecked, Watch unchecked (or disabled if watchdog not installed).

- [ ] **Step 4: Concurrency smoke**

Click "Run tests" twice in rapid succession. Confirm the status briefly shows "running … (queued: re-run)" and a second run starts after the first finishes.

- [ ] **Step 5: Save-point smoke (optional, only if you enable the trigger)**

Enable "Run tests after each save-point" in Settings → save. Then create a new save-point in the Save Points page. Confirm the Tests section starts a run within ~1s.

- [ ] **Step 6: Stop the GUI**

```bash
kill $GUI_PID || true
```

- [ ] **Step 7: Commit acceptance note**

Append a short status line at the bottom of the spec doc (`docs/superpowers/specs/2026-04-16-test-runner-plugin-design.md`):

```markdown
---

## Acceptance log

- 2026-04-16: smoke run on `/home/dchuprina/claude-monitor` — passed: `<N>` tests in `<duration>`. Coalescing verified (one queued re-run from rapid double-click). Save-point trigger verified opt-in.
```

Commit:
```bash
git add docs/superpowers/specs/2026-04-16-test-runner-plugin-design.md
git commit -m "docs(spec): record Task 17 smoke-test acceptance"
```

---

## Self-review notes

After completing all tasks, run a final regression sweep:

```bash
source .venv/bin/activate
pytest tests/ --tb=short -q
```
Expected: every previously-green test still passes, plus all new tests added in Tasks 1–18.

If any task in this plan fails its tests and you can't fix it within the task's scope, stop. Open a follow-up task or escalate; do not skip steps to keep the green count up.
