# Background Test Runner Plugin — Design

**Date:** 2026-04-16
**Supersedes:** Task 17 section in `2026-04-16-health-scanner-reliability-design.md`
**Status:** Ready for implementation planning

This is the focused design for Task 17 from the health-scanner reliability
spec. The original section was a sketch; this document is the contract.

---

## Goal

Add a background test runner so unit tests become part of the Health page
output. Manual trigger first; save-point and watch triggers are opt-in.
Single concurrent run per project, coalesced re-trigger. Persist history
in `HistoryDB`. Surface results as status / sparkline / failure tail in
`HealthPage`.

## Non-goals

- Replace CI.
- Implement a custom test runner — we shell out to `pytest` / `cargo test`
  / `npm test`.
- Coverage reporting.
- Windows-specific output handling (Linux/macOS only for v1).
- Cross-file SAST, security scanning, accessibility checks — those are
  separate future features (`vibe_scanner` track), not test runner.

---

## Decisions made during brainstorming

These are pinned. Implementation must not silently revert them.

1. **Plugin abstraction:** A real `TestRunnerPlugin(Plugin)` is created.
   To make this meaningful, a minimal `PluginRegistry` is also added in
   `core/plugin_loader.py` so `migrate()` / `collect()` / `get_alerts()`
   actually run for every plugin (revives a contract that has been dead
   since the Textual era). Out of scope for this task: changing the
   `Plugin(ABC)` contract itself.

2. **Default triggers:** `manual` only. `trigger_on_save_point` and
   `watch` are opt-in via `config.toml`.

3. **UI placement:** New "Tests" section inside `gui/pages/health/page.py`,
   not a separate sidebar tab.

4. **Frameworks v1:** `pytest`, `cargo test`, `npm test` (with structured
   parsing for Jest and Vitest, exit-code-only fallback for everything
   else). Go is out of scope for v1.

5. **Async/sync bridge:** `PluginRegistry` uses `asyncio.run()` per cycle,
   not a long-lived event loop. Test runner is event-triggered, not
   timer-driven, so per-call cost is irrelevant.

6. **Output parsing:** Text-only for pytest and cargo (regex against the
   summary line; both formats are stable across years). Jest and Vitest
   use their built-in `--json` reporters appended to the auto-detected
   command (`npm test -- --json` / `--reporter=json`); no extra packages.
   `pytest-json-report` integration is intentionally not in v1 — adding
   it later is a one-file change in the pytest parser if the regex ever
   proves brittle.

7. **`test_runs` storage:** Lives only in `HistoryDB` (sync sqlite3, made
   thread-safe in Task 18). `TestRunnerPlugin.migrate()` is a no-op stub
   with a comment pointing to `HistoryDB`. We accept the contract
   asymmetry rather than duplicate the table across two DB files.

8. **Coalescing:** Single in-flight run per project. A second trigger
   while running sets a `_needs_rerun` flag; when the current run
   finishes, exactly one re-run fires. Never queue more than one pending.

---

## File layout

```
core/
  health/
    test_runner.py             # NEW — sync subprocess orchestration
    test_detector.py           # NEW — framework detection
    test_parsers/              # NEW
      __init__.py
      pytest.py
      cargo.py
      jest.py
      vitest.py
      generic.py
  plugin_loader.py             # NEW — minimal PluginRegistry
  history.py                   # MODIFY — add test_runs table + accessors

plugins/
  test_runner/                 # NEW
    __init__.py
    plugin.py                  # TestRunnerPlugin(Plugin)
    collector.py               # re-export detect_framework() for parity

gui/
  pages/
    health/
      page.py                  # MODIFY — "Tests" section
      test_runner_thread.py    # NEW — QThread wrapper
  pages/
    settings.py                # MODIFY — Tests group (toggles + override)

tests/
  fixtures/
    test_runner_pytest/        # NEW — minimal repo with 1 pass + 1 fail (used by test_test_runner.py)
    parser_outputs/            # NEW — captured stdout for parser unit tests
  test_test_runner.py          # NEW
  test_test_parsers.py         # NEW
  test_test_detector.py        # NEW
  test_plugin_loader.py        # NEW
  test_test_runner_coalescing.py  # NEW

config.toml                    # add [tests] section
```

---

## Components

### `core/health/test_runner.py`

```python
@dataclass(frozen=True)
class TestRun:
    project_dir: str
    framework: str             # "pytest" | "cargo" | "jest" | "vitest" | "generic"
    command: list[str]
    started_at: float          # unix ts
    finished_at: float | None
    duration_s: float
    exit_code: int | None      # None = killed by timeout
    timed_out: bool
    passed: int | None         # None when parser couldn't extract
    failed: int | None
    errors: int | None
    skipped: int | None
    output_tail: str           # last 200 lines, joined

class TestRunner:
    def __init__(self, parser: Parser, timeout_s: int = 600):
        self._parser = parser
        self._timeout = timeout_s

    def run(self, project_dir: Path, cmd: list[str]) -> TestRun:
        """Blocking. Spawns subprocess, streams stdout into a 200-line ring
        buffer, kills on timeout, hands buffer to parser. Sync, no Qt."""
```

Implementation notes:
- `subprocess.Popen(cmd, cwd=project_dir, stdout=PIPE, stderr=STDOUT,
  text=True, bufsize=1)`.
- Read loop: `select()` on stdout with 100ms timeout, append lines to
  `collections.deque(maxlen=200)`.
- Wall-clock check vs `start + timeout` after every read tick. On
  exceed: `proc.kill()`, `proc.wait(timeout=2)`, log warning if zombie.
- Parser is invoked once at the end on the joined ring buffer. Wrapped
  in `try/except Exception`; failure yields `ParseResult(None, None,
  None, None)` — we still record the run, lose only counters.

### `core/health/test_parsers/`

Each module exports `parse(output: str, exit_code: int) -> ParseResult`:

```python
@dataclass
class ParseResult:
    passed: int | None
    failed: int | None
    errors: int | None
    skipped: int | None
```

- **pytest.py** — regex against the summary line `=+\s*(?:(\d+) failed,?\s*)?(?:(\d+) passed,?\s*)?(?:(\d+) skipped,?\s*)?(?:(\d+) errors?,?\s*)?`. Text-only for v1 (see decision 6).
- **cargo.py** — sum across all `test result: ok. N passed; M failed; K ignored` lines.
- **jest.py** / **vitest.py** — find the JSON block in stdout
  (`numPassedTests`, `numFailedTests`, `numPendingTests`).
- **generic.py** — returns all `None`. UI shows pass/fail by exit code only.

### `core/health/test_detector.py`

```python
def detect_framework(project_dir: Path) -> tuple[str, list[str]]:
    """Returns (framework_name, default_cmd_argv).
    Priority: pyproject.toml > Cargo.toml > package.json > heuristic."""
```

- `pyproject.toml` with `[tool.pytest.ini_options]` OR pytest in
  `[project.optional-dependencies]` OR `[project] dependencies` OR `tests/`
  with `conftest.py` → `("pytest", ["pytest", "-x", "--tb=short"])`.
- `Cargo.toml` → `("cargo", ["cargo", "test", "--all-features"])`.
- `package.json` with `scripts.test` containing `jest` →
  `("jest", ["npm", "test", "--", "--json"])`.
- `package.json` with `scripts.test` containing `vitest` →
  `("vitest", ["npm", "test", "--", "--reporter=json"])`.
- `package.json` with any other `scripts.test` → `("generic", ["npm", "test"])`.
- Nothing detected → `("generic", [])`.

Override is read by the caller (`HealthPage`) from `config.toml`'s
`[tests] command`. The detector itself does not read config.

### `plugins/test_runner/plugin.py`

```python
class TestRunnerPlugin(Plugin):
    name = "Tests"
    icon = "🧪"

    def __init__(self, config: dict):
        self._config = config.get("plugins", {}).get("test_runner", {})

    async def migrate(self, db):
        """No-op. test_runs table is owned by HistoryDB (sync sqlite3)."""

    async def collect(self, db):
        """No-op. Runs are event-triggered (button / save-point / watch)."""

    async def get_alerts(self, db) -> list[Alert]:
        # Bridges to sync HistoryDB via asyncio.to_thread.
        # Returns one warning-level Alert if last run failed or timed out.
        ...

    def render(self):
        # PyQt5 GUI doesn't use this. Placeholder fulfils the contract.
        from PyQt5.QtWidgets import QWidget
        return QWidget()
```

`collector.py` re-exports `detect_framework` for symmetry with
`docker_monitor`/`port_map`.

### `core/plugin_loader.py`

```python
class PluginRegistry:
    _IMPORTS = {
        "test_runner": "plugins.test_runner.plugin.TestRunnerPlugin",
        # docker_monitor, port_map, security_scan can be added here later.
    }

    def __init__(self, config: dict, db_path: Path):
        self._config = config
        self._db_path = db_path
        self._plugins: list[Plugin] = self._load_enabled()

    def start(self):
        """Run migrate() for all plugins. Called once at GUI startup."""
        asyncio.run(self._migrate_all())

    def collect_all(self) -> list[Alert]:
        """Run collect() + get_alerts() for all. Called from a QThread on a timer."""
        return asyncio.run(self._collect_and_alert())
```

- `_load_enabled` reads `config["plugins"][name] is True` for each known
  key, dynamically imports the class, instantiates with `config`.
- A plugin raising in `get_alerts()` does not propagate — log warning,
  return `[]` for that plugin, continue with others.
- For v1 only `test_runner` is wired. Migrating `docker_monitor` /
  `port_map` / `security_scan` to the registry is a follow-up; their
  current direct-import path (`gui/app/threads.py`) keeps working.

### `gui/pages/health/test_runner_thread.py`

```python
class TestRunnerThread(QThread):
    finished_run = pyqtSignal(object)   # emits TestRun
    progress = pyqtSignal(str)          # status: "running 12s", "killing"

    def __init__(self, runner: TestRunner, project_dir: Path, cmd: list[str]):
        ...

    def run(self):
        result = self._runner.run(self._project_dir, self._cmd)
        self.finished_run.emit(result)
```

### `core/history.py` — additions

```python
def save_test_run(self, run: TestRun) -> int: ...
def get_test_runs(self, project_dir: str, limit: int = 50) -> list[TestRun]: ...
def get_last_test_run(self, project_dir: str) -> TestRun | None: ...
```

Migration `_migrate_test_runs()` follows the existing `_migrate_*` pattern
in `history.py`. Schema:

```sql
CREATE TABLE IF NOT EXISTS test_runs (
    id INTEGER PRIMARY KEY,
    project_dir TEXT NOT NULL,
    framework TEXT NOT NULL,
    command TEXT NOT NULL,           -- JSON-encoded argv list
    started_at REAL NOT NULL,
    finished_at REAL,
    duration_s REAL,
    exit_code INTEGER,
    timed_out INTEGER NOT NULL DEFAULT 0,
    passed INTEGER, failed INTEGER, errors INTEGER, skipped INTEGER,
    output_tail TEXT
);
CREATE INDEX IF NOT EXISTS idx_test_runs_project_started
    ON test_runs (project_dir, started_at DESC);
```

`save_test_run` after insert prunes:
```sql
DELETE FROM test_runs WHERE project_dir = ?
  AND id NOT IN (
    SELECT id FROM test_runs WHERE project_dir = ?
    ORDER BY started_at DESC LIMIT ?
  );
```
`?, ?, ?` = `project_dir, project_dir, history_limit` (default 100).

### `gui/pages/health/page.py` — Tests section

A new `_build_tests_section()` adds a `QGroupBox("Tests")` between the
existing health findings and the page footer. Children:

- `QLabel` status (large font, color-coded by state).
- Sparkline widget showing last 10 runs' duration, color-coded by result
  (green pass, red fail, orange timeout). Reuses Qt-native painting; no
  new dep.
- `QPushButton "Run tests"` (disabled while a thread is active).
- Kebab menu (`QToolButton`) with single item "Show history" → opens
  `QDialog` with `QTableView` over `get_test_runs(project_dir, 100)`.
- Collapsible failure tail: copyable widget (`make_copy_all_button`
  pattern) shown only when last run failed or timed out.

State machine:

| State | Status text | Run button |
|---|---|---|
| no runs | `No tests run yet` | enabled |
| running | `running 12s…` | disabled |
| running + queued | `running 12s… (queued: re-run)` | disabled |
| passed | `passed in 1m 13s ✅` | enabled |
| failed | `failed: 3 of 124 ❌` (or `failed (counts unknown) ❌` if generic) | enabled |
| timed_out | `timed out after 10m ⏱` | enabled |
| error | `command not found` etc. | enabled |

Coalescing state lives on `HealthPage`:
- `self._test_thread: TestRunnerThread | None`
- `self._needs_rerun: bool`

Triggers all funnel through `_on_run_tests()`:
1. `_on_run_tests()` (button click).
2. `_on_save_point_created(project_dir)` (slot wired in `MainWindow`,
   gated by `config["tests"]["trigger_on_save_point"]`).
3. `_on_watch_event()` (slot bound to a `QTimer.singleShot(2000, ...)`
   debouncer, gated by `config["tests"]["watch"]`).

### `gui/pages/settings.py` — Tests group

New `QGroupBox("Tests")`:
- Checkbox "Run tests after each save-point".
- Checkbox "Watch files and re-run automatically" (disabled with tooltip
  `pip install watchdog` if `watchdog` is not importable).
- Line edit "Override command" (placeholder shows the auto-detected
  default).
- Number input "Timeout (seconds)" (default 600).

Settings changes write back to `config.toml` through the existing config
write helper.

---

## Data flow

### Manual run

```
Run button click
  → HealthPage._on_run_tests()
    → if thread running: _needs_rerun = True; return
    → framework, default_cmd = detect_framework(project_dir)
    → cmd = config["tests"]["command"].split() or default_cmd
    → parser = parsers.for_framework(framework)
    → runner = TestRunner(parser, timeout_s=cfg)
    → thread = TestRunnerThread(runner, project_dir, cmd)
    → thread.finished_run.connect(_on_test_finished)
    → thread.start()
    → status → "running 0s"; QTimer ticks the elapsed counter
TestRunner.run() (in worker thread)
  → Popen + select loop + ring buffer + timeout watch
  → returns TestRun
TestRunnerThread emits finished_run(TestRun)
  → HealthPage._on_test_finished(run)
    → HistoryDB.save_test_run(run)
    → update status / sparkline / tail
    → if _needs_rerun: clear flag, call _on_run_tests() again
    → _test_thread = None
```

### Save-point trigger (opt-in)

`MainWindow` already wires save-point creation events. Add a new slot
chain: `MainWindow.save_point_created` → `HealthPage._on_save_point_created`,
which checks the config flag and forwards to `_on_run_tests()`.

### Watch trigger (opt-in, requires `watchdog`)

On `HealthPage.set_project_dir()`, if `config["tests"]["watch"]` is true
and `watchdog` is importable, start an `Observer` over `watch_paths`
excluding `watch_exclude`. Each `on_modified` callback emits a
`pyqtSignal(str)` (Qt-safe, since watchdog runs in its own thread). The
slot resets a `QTimer.singleShot(debounce_ms, _on_run_tests)`. Each new
event resets the timer — that's the debounce.

### Coalescing example

```
t=0:    manual click       → thread starts
t=100:  save-point trigger → _needs_rerun = True (return)
t=200:  watch event         → _needs_rerun already True (no-op)
t=4500: thread finishes
        → save run; clear flag; _on_run_tests() again (one re-run)
```

Invariant: at most one in-flight run, at most one pending re-run.

### Plugin alerts

`MainWindow` already runs a periodic background `QThread` that polls
collectors. Extend it to also call `PluginRegistry.collect_all()`. The
returned `Alert` list is fed into the existing alert sink (status bar,
sound, etc.). `TestRunnerPlugin.get_alerts()` reads the last run via
`asyncio.to_thread(history_db.get_last_test_run, project_dir)`; emits a
`warning` Alert when it failed or timed out.

---

## Error handling

| Failure | Detection | Response |
|---|---|---|
| binary not found | `FileNotFoundError` from `Popen` | `TestRun(exit_code=-1, output_tail="command not found: …")`, save, UI error state with copyable hint |
| permission denied | `PermissionError` | same shape, different message |
| subprocess crash | `proc.returncode < 0` | `TestRun(exit_code=signal_num)`, status `crashed (SIG…)` |
| timeout | wall-clock check | `proc.kill()`, `proc.wait(2)`, `TestRun(timed_out=True)`. Zombie → log warning, still record |
| parser exception | wrapped at call site | log, fall back to `ParseResult(None,…)`, run still saved |
| no framework detected | `detect_framework` returns `("generic", [])` | UI: "No test framework detected" + link to docs; Run button disabled until override is set |
| empty override command | validated in `_on_run_tests` | tooltip "configure [tests] command in config.toml"; no run starts |
| `HistoryDB` write fails | exception in `save_test_run` | log, status-bar warning; do not crash |
| `watchdog` missing while watch=true | `ImportError` at startup | settings checkbox disabled, log warning, behave as watch=false |
| project dir deleted mid-run | subprocess raises | handled as generic crash |

Out of scope (intentional): ANSI escapes on Windows, concurrent edits to
`config.toml` mid-run, race on `_needs_rerun` (Qt signals are queued).

---

## Config

```toml
[plugins]
test_runner = true

[tests]
command = ""                       # empty = auto-detect
timeout_s = 600
trigger_on_save_point = false
watch = false
watch_paths = ["."]
watch_exclude = [".git", "node_modules", "target", "__pycache__", ".venv", "dist"]
debounce_ms = 2000
history_limit = 100
```

All keys optional; defaults live in code.

---

## Testing

### Unit — `tests/test_test_runner.py`

1. Pytest fixture repo (1 pass + 1 fail) → `passed=1, failed=1, exit_code=1`.
2. Timeout: `cmd=["sleep","60"]`, timeout=1 → `timed_out=True, exit_code=None, duration_s<3`.
3. `cmd=["definitely-not-a-binary-12345"]` → `exit_code=-1, "not found" in output_tail`.
4. Streaming: cmd prints 500 lines → `len(output_tail.splitlines()) == 200`, no crash.
5. Parser raising → run saved with all counters `None`.

### Unit — `tests/test_test_parsers.py`

Per-parser, fed canonical fixtures from `tests/fixtures/parser_outputs/`:
- pytest passed / failed / errors / json-report variants.
- cargo ok / failed.
- jest json / vitest json.
- generic returns all-None regardless of input.

### Unit — `tests/test_test_detector.py`

Tmp-dir fixtures for: pyproject only, Cargo only, package.json+jest,
package.json+vitest, package.json+mocha (→ generic), pyproject+Cargo
(→ pyproject wins), empty (→ generic, []).

### Unit — `tests/test_plugin_loader.py`

- Registry with `{plugins: {test_runner: true}}` loads exactly 1 plugin.
- `start()` calls `migrate()` for each (mock plugin counts calls).
- `collect_all()` aggregates alerts.
- A plugin raising in `get_alerts()` does not break the others; warning
  logged.

### Integration — `tests/test_test_runner_coalescing.py`

Mocked `TestRunner` (no real subprocess). Headless `HealthPage`. Two
calls to `_on_run_tests()` 50 ms apart → assert one active thread,
`_needs_rerun=True`. Finish first run → second starts; final
`_needs_rerun=False`.

### Smoke — manual, documented in spec

```bash
cd /home/dchuprina/claude-monitor
source .venv/bin/activate
python -m gui.app.main &
# In GUI: select project_dir = ./, Health page, click "Run tests".
# Expect ~5-15 s running, then "passed: <current total>" — green status,
# no failed/errors, sparkline gains one green bar. Number must equal
# `pytest -q | tail -1` run from CLI immediately after.
```

### Acceptance (mirrors original spec)

| Criterion | Result |
|---|---|
| Background test runner working, one worker per project, coalesced triggers | ⏳ — this task |
| All previously-passing pytest tests still pass | required |
| New tests added (≥ 5 files) all pass | required |
| Smoke run on this repo via GUI shows `passed: <CLI total>`, all green | required |

---

## Rollout

- Single feature branch `feat/test-runner-plugin`.
- Commits per logical chunk in this order:
  1. `core/history.py` migrations + accessors.
  2. `core/health/test_runner.py` + parsers + detector.
  3. `plugins/test_runner/` + `core/plugin_loader.py`.
  4. `gui/pages/health/page.py` Tests section + `test_runner_thread.py`.
  5. `gui/pages/settings.py` Tests group + `config.toml` defaults.
  6. Wire `PluginRegistry` into `MainWindow` periodic loop.
- Disable switch: `[plugins] test_runner = false` removes the plugin
  from the registry; the GUI section hides itself when the plugin is
  not registered.
