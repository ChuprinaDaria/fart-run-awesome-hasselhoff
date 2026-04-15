# Claude Status Monitor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show Claude API status + version in a permanent statusbar and Overview block so vibe coders don't panic when Anthropic goes down.

**Architecture:** `StatusChecker` pings `status.anthropic.com/api/v2/status.json` every 5 min (+ instantly on Haiku error). Results stored in SQLite `api_status_log`. `ClaudeStatusBar` widget at bottom of main window. Overview page gets a Claude Status block with 24h history and version timeline.

**Tech Stack:** Python 3.11+, PyQt5, urllib.request (stdlib), sqlite3 (stdlib), existing HistoryDB/HaikuClient/changelog_watcher

---

### Task 1: StatusResult dataclass + StatusChecker core logic

**Files:**
- Create: `core/status_checker.py`
- Test: `tests/test_status_checker.py`

- [ ] **Step 1: Write failing tests for StatusChecker**

```python
# tests/test_status_checker.py
"""Tests for Anthropic API status checker."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from unittest.mock import patch, MagicMock

import pytest

from core.history import HistoryDB
from core.status_checker import StatusChecker, StatusResult


@pytest.fixture
def db():
    d = HistoryDB(":memory:")
    d.init()
    return d


def _mock_urlopen(indicator: str, description: str):
    """Create a mock urlopen that returns a status.json response."""
    body = json.dumps({
        "status": {"indicator": indicator, "description": description}
    }).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestStatusChecker:
    def test_parse_status_ok(self, db):
        checker = StatusChecker(db)
        mock_resp = _mock_urlopen("none", "All Systems Operational")
        with patch("core.status_checker.urlopen", return_value=mock_resp):
            with patch("core.status_checker.get_claude_version", return_value="1.0.20"):
                result = checker.check_now()
        assert result.api_indicator == "none"
        assert result.api_description == "All Systems Operational"
        assert result.claude_version == "1.0.20"

    def test_parse_status_degraded(self, db):
        checker = StatusChecker(db)
        mock_resp = _mock_urlopen("minor", "Increased API Latency")
        with patch("core.status_checker.urlopen", return_value=mock_resp):
            with patch("core.status_checker.get_claude_version", return_value="1.0.20"):
                result = checker.check_now()
        assert result.api_indicator == "minor"

    def test_parse_status_down(self, db):
        checker = StatusChecker(db)
        mock_resp = _mock_urlopen("major", "Major outage")
        with patch("core.status_checker.urlopen", return_value=mock_resp):
            with patch("core.status_checker.get_claude_version", return_value=None):
                result = checker.check_now()
        assert result.api_indicator == "major"
        assert result.claude_version is None

    def test_timeout_returns_unknown(self, db):
        checker = StatusChecker(db)
        with patch("core.status_checker.urlopen", side_effect=OSError("timeout")):
            with patch("core.status_checker.get_claude_version", return_value="1.0.20"):
                result = checker.check_now()
        assert result.api_indicator == "unknown"
        assert result.api_description == "Could not reach status page"

    def test_bad_json_returns_unknown(self, db):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        checker = StatusChecker(db)
        with patch("core.status_checker.urlopen", return_value=mock_resp):
            with patch("core.status_checker.get_claude_version", return_value="1.0.20"):
                result = checker.check_now()
        assert result.api_indicator == "unknown"

    def test_unexpected_indicator(self, db):
        checker = StatusChecker(db)
        mock_resp = _mock_urlopen("maintenance", "Scheduled maintenance")
        with patch("core.status_checker.urlopen", return_value=mock_resp):
            with patch("core.status_checker.get_claude_version", return_value="1.0.20"):
                result = checker.check_now()
        assert result.api_indicator == "unknown"

    def test_save_and_load(self, db):
        checker = StatusChecker(db)
        mock_resp = _mock_urlopen("none", "All Systems Operational")
        with patch("core.status_checker.urlopen", return_value=mock_resp):
            with patch("core.status_checker.get_claude_version", return_value="1.0.20"):
                checker.check_now()
        last = checker.get_last_status()
        assert last is not None
        assert last.api_indicator == "none"

    def test_version_check_throttle(self, db):
        checker = StatusChecker(db)
        mock_resp = _mock_urlopen("none", "OK")
        with patch("core.status_checker.urlopen", return_value=mock_resp):
            with patch("core.status_checker.get_claude_version", return_value="1.0.20") as mock_ver:
                checker.check_now()
                checker.check_now()
                # Second call should reuse cached version
                assert mock_ver.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_status_checker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.status_checker'`

- [ ] **Step 3: Implement StatusChecker**

```python
# core/status_checker.py
"""Anthropic API status checker.

Pings status.anthropic.com every N minutes. Stores results in SQLite.
Provides StatusResult for statusbar and Overview page.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError

from core.changelog_watcher import get_claude_version
from core.history import HistoryDB

log = logging.getLogger(__name__)

STATUS_URL = "https://status.anthropic.com/api/v2/status.json"
_VALID_INDICATORS = {"none", "minor", "major", "critical"}
_HTTP_TIMEOUT = 5


@dataclass
class StatusResult:
    timestamp: str
    api_indicator: str        # "none", "minor", "major", "critical", "unknown"
    api_description: str
    claude_version: str | None
    response_time_ms: int


def _ensure_status_table(db: HistoryDB) -> None:
    db._ensure_conn()
    db._conn.execute("""
        CREATE TABLE IF NOT EXISTS api_status_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            indicator TEXT NOT NULL,
            description TEXT NOT NULL,
            claude_version TEXT DEFAULT '',
            response_time_ms INTEGER DEFAULT 0
        )
    """)
    db._conn.commit()


class StatusChecker:
    def __init__(self, db: HistoryDB):
        self._db = db
        _ensure_status_table(db)
        self._last_version: str | None = None
        self._last_version_check: float = 0
        self._version_interval = 300  # check claude version max once per 5 min

    def check_now(self) -> StatusResult:
        """Fetch current API status + Claude version. Save to DB."""
        ts = datetime.now().isoformat(timespec="seconds")

        # Fetch API status
        indicator = "unknown"
        description = "Could not reach status page"
        response_ms = 0

        try:
            start = time.monotonic()
            req = Request(STATUS_URL, headers={"User-Agent": "fartrun-monitor/1.0"})
            with urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                body = resp.read()
            response_ms = int((time.monotonic() - start) * 1000)

            data = json.loads(body)
            raw_indicator = data.get("status", {}).get("indicator", "")
            raw_description = data.get("status", {}).get("description", "")

            if raw_indicator in _VALID_INDICATORS:
                indicator = raw_indicator
                description = raw_description
            else:
                log.warning("Unexpected status indicator: %s", raw_indicator)
        except (URLError, OSError) as e:
            log.warning("Status page unreachable: %s", e)
        except (json.JSONDecodeError, KeyError) as e:
            log.warning("Status page bad response: %s", e)

        # Claude version (throttled)
        now = time.monotonic()
        if now - self._last_version_check >= self._version_interval:
            self._last_version = get_claude_version()
            self._last_version_check = now

        result = StatusResult(
            timestamp=ts,
            api_indicator=indicator,
            api_description=description,
            claude_version=self._last_version,
            response_time_ms=response_ms,
        )

        # Save to DB
        try:
            self._db._ensure_conn()
            self._db._conn.execute(
                "INSERT INTO api_status_log (timestamp, indicator, description, claude_version, response_time_ms) VALUES (?, ?, ?, ?, ?)",
                (ts, indicator, description, self._last_version or "", response_ms),
            )
            # Prune old records (keep 7 days)
            cutoff = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
            self._db._conn.execute(
                "DELETE FROM api_status_log WHERE timestamp < ?", (cutoff,)
            )
            self._db._conn.commit()
        except Exception as e:
            log.warning("Status DB write failed: %s", e)

        return result

    def get_last_status(self) -> StatusResult | None:
        """Get most recent status from DB."""
        try:
            self._db._ensure_conn()
            row = self._db._conn.execute(
                "SELECT timestamp, indicator, description, claude_version, response_time_ms "
                "FROM api_status_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return StatusResult(
                timestamp=row[0],
                api_indicator=row[1],
                api_description=row[2],
                claude_version=row[3] or None,
                response_time_ms=row[4],
            )
        except Exception:
            return None

    def get_status_history(self, hours: int = 24) -> list[StatusResult]:
        """Get status transitions in the last N hours."""
        try:
            cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
            self._db._ensure_conn()
            rows = self._db._conn.execute(
                "SELECT timestamp, indicator, description, claude_version, response_time_ms "
                "FROM api_status_log WHERE timestamp >= ? ORDER BY id DESC",
                (cutoff,),
            ).fetchall()

            # Filter to transitions only
            results = []
            prev_indicator = None
            for row in reversed(rows):  # oldest first for transition detection
                if row[1] != prev_indicator:
                    results.append(StatusResult(
                        timestamp=row[0],
                        api_indicator=row[1],
                        api_description=row[2],
                        claude_version=row[3] or None,
                        response_time_ms=row[4],
                    ))
                    prev_indicator = row[1]
            results.reverse()  # newest first for display
            return results
        except Exception:
            return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_status_checker.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add core/status_checker.py tests/test_status_checker.py
git commit -m "feat: StatusChecker — ping status.anthropic.com, parse indicator, SQLite log"
```

---

### Task 2: History pruning + transition tests

**Files:**
- Modify: `tests/test_status_checker.py`

- [ ] **Step 1: Add pruning and transition tests**

Append to `tests/test_status_checker.py`:

```python
    def test_history_pruning(self, db):
        """Records older than 7 days are deleted."""
        checker = StatusChecker(db)
        _ensure_status_table(db)
        # Insert old record
        old_ts = (datetime.now() - timedelta(days=8)).isoformat(timespec="seconds")
        db._conn.execute(
            "INSERT INTO api_status_log (timestamp, indicator, description) VALUES (?, ?, ?)",
            (old_ts, "none", "OK"),
        )
        db._conn.commit()

        # check_now should prune the old record
        mock_resp = _mock_urlopen("none", "OK")
        with patch("core.status_checker.urlopen", return_value=mock_resp):
            with patch("core.status_checker.get_claude_version", return_value="1.0.20"):
                checker.check_now()

        rows = db._conn.execute("SELECT COUNT(*) FROM api_status_log").fetchone()
        assert rows[0] == 1  # only the new record

    def test_status_transitions(self, db):
        """get_status_history returns only state changes, not every check."""
        checker = StatusChecker(db)
        _ensure_status_table(db)
        now = datetime.now()
        # Insert: OK, OK, Degraded, Degraded, OK
        for i, (ind, desc) in enumerate([
            ("none", "OK"), ("none", "OK"), ("minor", "Slow"),
            ("minor", "Slow"), ("none", "OK"),
        ]):
            ts = (now - timedelta(minutes=25 - i * 5)).isoformat(timespec="seconds")
            db._conn.execute(
                "INSERT INTO api_status_log (timestamp, indicator, description) VALUES (?, ?, ?)",
                (ts, ind, desc),
            )
        db._conn.commit()

        history = checker.get_status_history(hours=1)
        # Should be 3 transitions: OK -> Degraded -> OK
        assert len(history) == 3
        assert history[0].api_indicator == "none"  # newest: OK
        assert history[1].api_indicator == "minor"  # middle: Degraded
        assert history[2].api_indicator == "none"  # oldest: OK
```

Add import at top of test file:

```python
from datetime import datetime, timedelta
from core.status_checker import _ensure_status_table
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_status_checker.py -v`
Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_status_checker.py
git commit -m "test: add pruning + transition history tests for StatusChecker"
```

---

### Task 3: HaikuClient on_api_error callback

**Files:**
- Modify: `core/haiku_client.py`
- Test: `tests/test_haiku_client.py`

- [ ] **Step 1: Write failing test for on_api_error callback**

Add to `tests/test_haiku_client.py`:

```python
def test_on_api_error_callback():
    """HaikuClient calls on_api_error when API call fails."""
    errors = []
    client = HaikuClient(api_key="sk-test", on_api_error=lambda e: errors.append(e))
    # Force an error by mocking the SDK
    with patch.object(client, "_get_client") as mock:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("Connection refused")
        mock.return_value = mock_client
        result = client.ask("test prompt")
    assert result is None
    assert len(errors) == 1
    assert "Connection refused" in errors[0]


def test_on_api_error_not_called_on_success():
    """on_api_error is NOT called when API succeeds."""
    errors = []
    client = HaikuClient(api_key="sk-test", on_api_error=lambda e: errors.append(e))
    with patch.object(client, "_get_client") as mock:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="hello")]
        mock_client.messages.create.return_value = mock_resp
        mock.return_value = mock_client
        result = client.ask("test prompt")
    assert result == "hello"
    assert len(errors) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_haiku_client.py::test_on_api_error_callback -v`
Expected: FAIL (TypeError — `on_api_error` not accepted)

- [ ] **Step 3: Add on_api_error to HaikuClient**

Modify `core/haiku_client.py`:

Change `__init__` signature:
```python
def __init__(self, api_key: str | None = None, config: dict | None = None, on_api_error=None):
```

Add after `self._client = None`:
```python
        self._on_api_error = on_api_error
```

Change the except block in `ask()` method (line 71-73) from:
```python
        except Exception as e:
            log.error("Haiku API error: %s", e)
            return None
```
to:
```python
        except Exception as e:
            log.error("Haiku API error: %s", e)
            if self._on_api_error:
                self._on_api_error(str(e))
            return None
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_haiku_client.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add core/haiku_client.py tests/test_haiku_client.py
git commit -m "feat: HaikuClient on_api_error callback for status monitor integration"
```

---

### Task 4: i18n strings + config

**Files:**
- Modify: `i18n/en.py`
- Modify: `i18n/ua.py`
- Modify: `config.toml`

- [ ] **Step 1: Add English strings**

Add to `i18n/en.py` STRINGS dict:

```python
    # === Claude Status Monitor ===
    "status_ok": "API: OK",
    "status_degraded": "API: Degraded",
    "status_down": "API: Down",
    "status_unknown": "API: Unknown",
    "status_claude_not_found": "Claude: not found",
    "status_checked_ago": "Checked {ago}",
    "status_check_now": "Check Now",
    "status_dont_panic": "If AI features aren't working right now, it's not your code. Anthropic is having issues. Wait it out.",
    "status_haiku_unavailable": "Haiku unavailable -- check API key in Settings",
    "status_all_day_ok": "All day: OK",
    "status_last_24h": "Last 24h",
    "status_version_history": "Version History",
    "status_claude_status": "Claude Code",
    "status_version": "Version: {version}",
    "status_show_changelog": "Show Full Changelog",
```

- [ ] **Step 2: Add Ukrainian strings**

Add to `i18n/ua.py` STRINGS dict:

```python
    # === Claude Status Monitor ===
    "status_ok": "API: OK",
    "status_degraded": "API: Деградація",
    "status_down": "API: Не працює",
    "status_unknown": "API: Невідомо",
    "status_claude_not_found": "Claude: не знайдено",
    "status_checked_ago": "Перевірено {ago}",
    "status_check_now": "Перевірити",
    "status_dont_panic": "Якщо AI фічі не працюють — це не твій код. В Anthropic проблеми. Зачекай.",
    "status_haiku_unavailable": "Haiku недоступний — перевір API ключ в Settings",
    "status_all_day_ok": "Весь день: OK",
    "status_last_24h": "Останні 24г",
    "status_version_history": "Історія версій",
    "status_claude_status": "Claude Code",
    "status_version": "Версія: {version}",
    "status_show_changelog": "Повний changelog",
```

- [ ] **Step 3: Add config section**

Add to `config.toml` after `[safety_net]` section:

```toml

[status]
check_interval_minutes = 5
enabled = true
```

- [ ] **Step 4: Commit**

```bash
git add i18n/en.py i18n/ua.py config.toml
git commit -m "feat: i18n strings + config for Claude Status Monitor"
```

---

### Task 5: ClaudeStatusBar widget

**Files:**
- Create: `gui/statusbar.py`

- [ ] **Step 1: Implement ClaudeStatusBar**

```python
# gui/statusbar.py
"""Permanent statusbar showing Claude version + API status.

Sits at the bottom of the main window, visible from every page.
Click navigates to Overview page.
"""

from __future__ import annotations

import random
from datetime import datetime

from PyQt5.QtWidgets import QStatusBar, QLabel
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QMouseEvent

from i18n import get_string as _t

# Indicator -> (i18n key, background color)
_STATUS_STYLES = {
    "none":     ("status_ok",       ""),
    "minor":    ("status_degraded", "background: #ffff00;"),
    "major":    ("status_down",     "background: #ff4444; color: white;"),
    "critical": ("status_down",     "background: #ff4444; color: white;"),
    "unknown":  ("status_unknown",  ""),
}

HOFF_OK = [
    "The Hoff is watching. All clear.",
    "All systems nominal. Hasselhoff approves.",
]
HOFF_DOWN = [
    "Even the Hoff can't fix this one. Wait.",
    "Don't hassle the API. It's down.",
]
HOFF_VERSION = [
    "The Hoff upgraded. New powers unlocked.",
]


class ClaudeStatusBar(QStatusBar):
    """Permanent statusbar with Claude version + API status."""

    clicked = pyqtSignal()  # emitted on click -> navigate to Overview

    def __init__(self, parent=None):
        super().__init__(parent)
        self._version_label = QLabel("Claude: --")
        self._status_label = QLabel(_t("status_unknown"))
        self._time_label = QLabel("")

        for lbl in (self._version_label, self._status_label, self._time_label):
            lbl.setStyleSheet("padding: 0 8px;")

        self.addPermanentWidget(self._version_label)
        self.addPermanentWidget(self._status_label)
        self.addPermanentWidget(self._time_label)

        self._last_indicator = "unknown"

    def update_status(self, indicator: str, version: str | None, timestamp: str) -> None:
        """Update all statusbar fields from a StatusResult."""
        # Version
        if version:
            self._version_label.setText(f"Claude {version}")
        else:
            self._version_label.setText(_t("status_claude_not_found"))

        # API status
        key, bg_style = _STATUS_STYLES.get(indicator, _STATUS_STYLES["unknown"])
        self._status_label.setText(_t(key))
        if bg_style:
            self._status_label.setStyleSheet(f"padding: 0 8px; font-weight: bold; {bg_style}")
        else:
            self._status_label.setStyleSheet("padding: 0 8px;")

        # Time ago
        try:
            checked = datetime.fromisoformat(timestamp)
            delta = datetime.now() - checked
            minutes = int(delta.total_seconds() / 60)
            if minutes < 1:
                ago = "just now"
            elif minutes < 60:
                ago = f"{minutes} min ago"
            else:
                ago = f"{minutes // 60}h ago"
            self._time_label.setText(_t("status_checked_ago").format(ago=ago))
        except (ValueError, TypeError):
            self._time_label.setText("")

        # Hasselhoff (10% chance)
        if random.random() < 0.10:
            if indicator == "none":
                self.showMessage(random.choice(HOFF_OK), 5000)
            elif indicator in ("major", "critical"):
                self.showMessage(random.choice(HOFF_DOWN), 5000)

        self._last_indicator = indicator

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Click anywhere on statusbar -> navigate to Overview."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
```

- [ ] **Step 2: Commit**

```bash
git add gui/statusbar.py
git commit -m "feat: ClaudeStatusBar widget — version + API status + Hasselhoff"
```

---

### Task 6: Overview page — Claude Status block

**Files:**
- Modify: `gui/pages/overview.py`

- [ ] **Step 1: Read current overview.py fully**

Read the complete file to understand the layout structure before modifying.

- [ ] **Step 2: Add Claude Status block**

Add imports at top of `gui/pages/overview.py`:

```python
from core.changelog_watcher import CHANGELOG_URL
```

Add after `layout.addWidget(self.budget_label)` and before `self.budget_bar = QProgressBar()` — a new Claude Status group:

```python
        # Claude Status block
        self.claude_group = QGroupBox(_t("status_claude_status"))
        cl = QVBoxLayout()

        # Current status row
        status_row = QHBoxLayout()
        self.lbl_claude_version = QLabel("Version: --")
        self.lbl_claude_version.setStyleSheet("font-weight: bold;")
        status_row.addWidget(self.lbl_claude_version)

        self.lbl_api_status = QLabel(_t("status_unknown"))
        status_row.addWidget(self.lbl_api_status)

        self.lbl_last_check = QLabel("")
        status_row.addWidget(self.lbl_last_check)

        self.btn_check_now = QPushButton(_t("status_check_now"))
        self.btn_check_now.setFixedWidth(100)
        status_row.addWidget(self.btn_check_now)
        status_row.addStretch()
        cl.addLayout(status_row)

        # Don't panic message (hidden by default)
        self.lbl_dont_panic = QLabel(_t("status_dont_panic"))
        self.lbl_dont_panic.setWordWrap(True)
        self.lbl_dont_panic.setStyleSheet(
            "color: #800000; padding: 4px; background: #ffffcc; border: 1px solid #808080;"
        )
        self.lbl_dont_panic.setVisible(False)
        cl.addWidget(self.lbl_dont_panic)

        # Status history (24h)
        self.lbl_history_title = QLabel(_t("status_last_24h"))
        self.lbl_history_title.setStyleSheet("font-weight: bold; margin-top: 8px;")
        cl.addWidget(self.lbl_history_title)

        self.lbl_status_history = QLabel(_t("status_all_day_ok"))
        self.lbl_status_history.setStyleSheet(
            "padding: 4px; background: white; border: 2px inset #808080; font-size: 11px;"
        )
        cl.addWidget(self.lbl_status_history)

        # Version history
        self.lbl_version_title = QLabel(_t("status_version_history"))
        self.lbl_version_title.setStyleSheet("font-weight: bold; margin-top: 8px;")
        cl.addWidget(self.lbl_version_title)

        self.lbl_version_history = QLabel("--")
        self.lbl_version_history.setStyleSheet(
            "padding: 4px; background: white; border: 2px inset #808080; font-size: 11px;"
        )
        cl.addWidget(self.lbl_version_history)

        # Changelog button
        from PyQt5.QtWidgets import QDesktopServices
        from PyQt5.QtCore import QUrl
        self.btn_changelog = QPushButton(_t("status_show_changelog"))
        self.btn_changelog.clicked.connect(
            lambda: __import__("PyQt5.QtGui", fromlist=["QDesktopServices"]).QDesktopServices.openUrl(
                QUrl(CHANGELOG_URL)
            )
        )
        cl.addWidget(self.btn_changelog)

        self.claude_group.setLayout(cl)
        layout.addWidget(self.claude_group)
```

Add public methods to OverviewPage class:

```python
    def update_claude_status(self, result, history: list, version_history: list) -> None:
        """Update Claude Status block from StatusResult + histories."""
        # Version
        if result.claude_version:
            self.lbl_claude_version.setText(
                _t("status_version").format(version=result.claude_version)
            )
        else:
            self.lbl_claude_version.setText(_t("status_claude_not_found"))

        # API status with color
        indicator = result.api_indicator
        status_text = f"{_t(_STATUS_MAP.get(indicator, 'status_unknown'))} -- {result.api_description}"
        self.lbl_api_status.setText(status_text)

        if indicator in ("major", "critical"):
            self.lbl_api_status.setStyleSheet("color: red; font-weight: bold;")
            self.lbl_dont_panic.setVisible(True)
            self.claude_group.setStyleSheet(
                "QGroupBox { border: 2px groove #ff4444; }"
            )
        elif indicator == "minor":
            self.lbl_api_status.setStyleSheet("color: #808000; font-weight: bold;")
            self.lbl_dont_panic.setVisible(True)
            self.claude_group.setStyleSheet(
                "QGroupBox { border: 2px groove #ffff00; }"
            )
        else:
            self.lbl_api_status.setStyleSheet("")
            self.lbl_dont_panic.setVisible(False)
            self.claude_group.setStyleSheet("")

        # Last check time
        try:
            checked = datetime.fromisoformat(result.timestamp)
            delta = datetime.now() - checked
            minutes = int(delta.total_seconds() / 60)
            ago = "just now" if minutes < 1 else f"{minutes} min ago"
            self.lbl_last_check.setText(_t("status_checked_ago").format(ago=ago))
        except (ValueError, TypeError):
            pass

        # Status history
        if not history:
            self.lbl_status_history.setText(_t("status_all_day_ok"))
        else:
            lines = []
            for h in history[:10]:
                ts = h.timestamp[11:16] if len(h.timestamp) > 16 else h.timestamp
                label = _STATUS_MAP.get(h.api_indicator, "Unknown")
                desc = f" -- {h.api_description}" if h.api_description else ""
                lines.append(f"{ts}  {label}{desc}")
            self.lbl_status_history.setText("\n".join(lines))

        # Version history
        if version_history:
            lines = []
            for v in version_history[:5]:
                lines.append(f"{v[0]}  detected {v[1]}")
            self.lbl_version_history.setText("\n".join(lines))
```

Add at module level in overview.py:

```python
from datetime import datetime

_STATUS_MAP = {
    "none": "OK",
    "minor": "Degraded",
    "major": "Down",
    "critical": "Down",
    "unknown": "Unknown",
}
```

- [ ] **Step 3: Commit**

```bash
git add gui/pages/overview.py
git commit -m "feat: Claude Status block in Overview — version, API status, 24h history"
```

---

### Task 7: Wire everything in app.py

**Files:**
- Modify: `gui/app.py`

- [ ] **Step 1: Read current app.py fully to understand wiring points**

Read the complete file, especially `__init__`, timer setup, and `_check_claude_update`.

- [ ] **Step 2: Add StatusChecker + StatusBar + timer wiring**

Add imports at top of `gui/app.py`:

```python
from core.status_checker import StatusChecker
from gui.statusbar import ClaudeStatusBar
```

In `MonitorApp.__init__`, after `self._history_db` is created (find the line), add:

```python
        # Status checker
        status_config = config.get("status", {})
        self._status_checker = StatusChecker(self._history_db)
```

Replace `self.statusBar().showMessage(_t("ready"))` (line 213) with:

```python
        # Claude Status Bar
        self._claude_statusbar = ClaudeStatusBar(self)
        self.setStatusBar(self._claude_statusbar)
        self._claude_statusbar.clicked.connect(lambda: self._on_page_selected("overview"))
```

After the existing timer setup section, add status timer:

```python
        # Status check timer (every N minutes)
        interval_min = config.get("status", {}).get("check_interval_minutes", 5)
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._check_api_status)
        if config.get("status", {}).get("enabled", True):
            self._status_timer.start(interval_min * 60 * 1000)
```

Add the status check method:

```python
    def _check_api_status(self) -> None:
        """Check Anthropic API status in background."""
        class _StatusThread(QThread):
            done = pyqtSignal(object)
            def __init__(self, checker, parent=None):
                super().__init__(parent)
                self._checker = checker
            def run(self):
                result = self._checker.check_now()
                self.done.emit(result)

        thread = _StatusThread(self._status_checker, self)
        thread.done.connect(self._on_status_checked)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        self._status_thread = thread  # prevent GC

    def _on_status_checked(self, result) -> None:
        """Update statusbar + overview from status check result."""
        self._claude_statusbar.update_status(
            result.api_indicator, result.claude_version, result.timestamp
        )

        # Update Overview if it has the method
        if hasattr(self.page_overview, "update_claude_status"):
            history = self._status_checker.get_status_history(hours=24)
            # Version history from changelog_watcher
            from core.changelog_watcher import _ensure_version_table
            try:
                _ensure_version_table(self._history_db)
                rows = self._history_db._conn.execute(
                    "SELECT version, detected_at FROM claude_versions ORDER BY id DESC LIMIT 5"
                ).fetchall()
            except Exception:
                rows = []
            self.page_overview.update_claude_status(result, history, rows)

        # Connect overview Check Now button (once)
        if not hasattr(self, "_status_btn_connected"):
            if hasattr(self.page_overview, "btn_check_now"):
                self.page_overview.btn_check_now.clicked.connect(self._check_api_status)
                self._status_btn_connected = True
```

Modify HaikuClient creation (find where it's created in app.py or pages) to pass `on_api_error`:

```python
        # When creating HaikuClient instances, pass error callback
        self._on_haiku_api_error = lambda e: self._check_api_status()
```

In `_check_claude_update` method, add initial status check after the changelog check:

```python
        # Initial status check
        self._check_api_status()
```

- [ ] **Step 3: Commit**

```bash
git add gui/app.py
git commit -m "feat: wire StatusChecker + ClaudeStatusBar + timer in app.py"
```

---

### Task 8: Integration test — full flow

**Files:**
- Modify: `tests/test_status_checker.py`

- [ ] **Step 1: Add integration-style test**

Append to `tests/test_status_checker.py`:

```python
class TestStatusCheckerIntegration:
    def test_full_cycle(self, db):
        """Full cycle: check -> save -> load -> history."""
        checker = StatusChecker(db)

        # First check: OK
        mock_ok = _mock_urlopen("none", "All Systems Operational")
        with patch("core.status_checker.urlopen", return_value=mock_ok):
            with patch("core.status_checker.get_claude_version", return_value="1.0.20"):
                r1 = checker.check_now()
        assert r1.api_indicator == "none"

        # Force version cache expiry for second check
        checker._last_version_check = 0

        # Second check: Degraded
        mock_deg = _mock_urlopen("minor", "Slow responses")
        with patch("core.status_checker.urlopen", return_value=mock_deg):
            with patch("core.status_checker.get_claude_version", return_value="1.0.21"):
                r2 = checker.check_now()
        assert r2.api_indicator == "minor"
        assert r2.claude_version == "1.0.21"

        # Load last
        last = checker.get_last_status()
        assert last.api_indicator == "minor"

        # History should show 2 transitions
        history = checker.get_status_history(hours=1)
        assert len(history) == 2

    def test_haiku_error_callback_pattern(self, db):
        """Simulates the on_api_error -> check_now flow."""
        checker = StatusChecker(db)
        checks = []

        def on_error(msg):
            mock_resp = _mock_urlopen("major", "API Down")
            with patch("core.status_checker.urlopen", return_value=mock_resp):
                with patch("core.status_checker.get_claude_version", return_value=None):
                    result = checker.check_now()
                    checks.append(result)

        # Simulate haiku error triggering a check
        on_error("Connection refused")
        assert len(checks) == 1
        assert checks[0].api_indicator == "major"
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/test_status_checker.py -v`
Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_status_checker.py
git commit -m "test: integration tests for StatusChecker full cycle + haiku error pattern"
```

---

### Task 9: Final wiring — HaikuClient error callback propagation

**Files:**
- Modify: `gui/app.py`
- Modify: `gui/pages/activity.py`
- Modify: `gui/pages/health_page.py`
- Modify: `gui/pages/snapshots.py`

- [ ] **Step 1: Find all HaikuClient instantiation points**

Search for `HaikuClient(` across the codebase. Each page creates its own HaikuClient in its thread. We need to propagate the callback.

- [ ] **Step 2: Add set_haiku_error_callback to pages**

In `gui/app.py`, after creating pages and `_on_haiku_api_error`, set the callback:

```python
        # Propagate haiku error callback to all pages that use Haiku
        for page in (self.page_activity, self.page_health, self.page_snapshots):
            if hasattr(page, "set_haiku_error_callback"):
                page.set_haiku_error_callback(self._on_haiku_api_error)
```

Each page that creates HaikuClient in a thread needs a `set_haiku_error_callback` method and must pass it through. The exact changes depend on how each page creates HaikuClient — read each file and add the callback propagation.

Pattern for each page:

```python
    def set_haiku_error_callback(self, callback):
        self._haiku_error_callback = callback
```

Then when creating HaikuClient in the thread:

```python
    client = HaikuClient(config=self._config, on_api_error=self._haiku_error_callback)
```

- [ ] **Step 3: Commit**

```bash
git add gui/app.py gui/pages/activity.py gui/pages/health_page.py gui/pages/snapshots.py
git commit -m "feat: propagate HaikuClient error callback to trigger status check"
```

---

### Task 10: Manual smoke test

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v --tb=short
```

Expected: all PASS

- [ ] **Step 2: Launch app and verify**

```bash
python -m gui.app
```

Verify:
1. Statusbar at bottom shows "Claude X.Y.Z | API: OK | Checked just now"
2. Click statusbar → navigates to Overview
3. Overview has Claude Status block with version + API status + history
4. "Check Now" button triggers immediate check
5. If no internet → statusbar shows "API: Unknown" (gray, not red)

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -u
git commit -m "fix: smoke test fixes for Claude Status Monitor"
```
