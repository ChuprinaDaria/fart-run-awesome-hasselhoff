# Haiku UX Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Haiku into all pages as human-language explainer, add auto-project detection, activity timeline with context, copy-all support — everything explained "for dummies".

**Architecture:** Extend existing `haiku_client.py` with `batch_explain()`, create `project_detector.py` for auto-project, add `activity_log` + `app_state` SQLite tables, add `CopyableSection` widget. Each page gets Haiku integration with static fallback.

**Tech Stack:** Python 3.11, PyQt5, SQLite, Anthropic SDK (optional), existing Rust health crate

---

### Task 1: Extend HaikuClient with batch_explain and config support

**Files:**
- Modify: `core/haiku_client.py`
- Modify: `core/config.py:9-46` (DEFAULTS dict)
- Create: `tests/test_haiku_batch.py`

- [ ] **Step 1: Write failing tests for batch_explain and config fallback**

```python
# tests/test_haiku_batch.py
"""Tests for HaikuClient batch_explain and config support."""

from core.haiku_client import HaikuClient


def test_batch_explain_no_key_returns_empty():
    client = HaikuClient(api_key=None)
    result = client.batch_explain(
        items=["unused import os", "file too long"],
        context="python project",
        language="en",
    )
    assert result == {}


def test_batch_explain_returns_dict():
    """Structure test — actual API not called."""
    client = HaikuClient(api_key=None)
    result = client.batch_explain([], "ctx", "en")
    assert isinstance(result, dict)


def test_config_fallback():
    """HaikuClient reads api_key from config dict."""
    client = HaikuClient(api_key=None, config={"haiku": {"api_key": "sk-ant-test"}})
    assert client.is_available() is True


def test_config_fallback_empty():
    client = HaikuClient(api_key=None, config={"haiku": {"api_key": ""}})
    assert client.is_available() is False


def test_rate_limit_default_30s():
    client = HaikuClient(api_key=None)
    assert client._min_interval == 30
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_haiku_batch.py -v`
Expected: FAIL — `batch_explain` doesn't exist, `config` param doesn't exist

- [ ] **Step 3: Add `[haiku]` to config DEFAULTS**

In `core/config.py`, add to `DEFAULTS` dict after the `"snapshots"` block:

```python
    "haiku": {
        "api_key": "",
    },
```

- [ ] **Step 4: Implement batch_explain and config support in HaikuClient**

Replace the full `core/haiku_client.py`:

```python
"""Claude Haiku client for personalized tips and explanations.

Optional — requires anthropic SDK and API key.
~$0.001 per call, rate limited to max 1 call per 30 seconds.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time

log = logging.getLogger(__name__)

_DEFAULT_MIN_INTERVAL = 30  # seconds between API calls


class HaikuClient:
    def __init__(self, api_key: str | None = None, config: dict | None = None):
        self._api_key = (
            api_key
            or os.environ.get("ANTHROPIC_API_KEY")
            or (config or {}).get("haiku", {}).get("api_key", "")
            or None
        )
        if self._api_key == "":
            self._api_key = None
        self._cache: dict[str, str] = {}
        self._last_call: float = 0
        self._client = None
        self._min_interval = _DEFAULT_MIN_INTERVAL

    def is_available(self) -> bool:
        return self._api_key is not None

    def _get_client(self):
        if self._client is None and self._api_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                log.warning("anthropic SDK not installed — Haiku features disabled")
                self._api_key = None
        return self._client

    def ask(self, prompt: str, max_tokens: int = 200) -> str | None:
        """Ask Haiku a question. Returns cached response if available."""
        cache_key = hashlib.md5(prompt.encode()).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not self.is_available():
            return None

        now = time.time()
        if now - self._last_call < self._min_interval:
            return None

        client = self._get_client()
        if not client:
            return None

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            result = response.content[0].text
            self._cache[cache_key] = result
            self._last_call = now
            return result
        except Exception as e:
            log.error("Haiku API error: %s", e)
            return None

    def batch_explain(
        self,
        items: list[str],
        context: str,
        language: str,
    ) -> dict[str, str]:
        """Explain multiple items in one API call.

        Returns dict mapping item text -> explanation.
        Empty dict if unavailable or no items.
        """
        if not items or not self.is_available():
            return {}

        lang_name = "Ukrainian" if language == "ua" else "English"
        numbered = "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))

        prompt = (
            f"You are explaining code issues to someone who doesn't know programming. "
            f"No jargon. Simple words. Respond in {lang_name}.\n\n"
            f"Context: {context}\n\n"
            f"For each issue below, explain: what it is, why it's bad, what to do. "
            f"1-2 sentences per issue. Format: number. explanation\n\n"
            f"{numbered}"
        )

        max_tokens = min(100 * len(items), 2000)
        response = self.ask(prompt, max_tokens=max_tokens)
        if not response:
            return {}

        # Parse numbered response back to dict
        result: dict[str, str] = {}
        lines = response.strip().split("\n")
        current_num = -1
        current_text = []

        for line in lines:
            match = re.match(r"^(\d+)\.\s*(.+)", line.strip())
            if match:
                if current_num >= 0 and current_num < len(items):
                    result[items[current_num]] = " ".join(current_text)
                current_num = int(match.group(1)) - 1
                current_text = [match.group(2)]
            elif current_num >= 0:
                current_text.append(line.strip())

        if current_num >= 0 and current_num < len(items):
            result[items[current_num]] = " ".join(current_text)

        return result

    def summarize(self, text: str, language: str, max_tokens: int = 300) -> str | None:
        """General-purpose summary in human language."""
        lang_name = "Ukrainian" if language == "ua" else "English"
        prompt = (
            f"Explain this in simple terms for someone without technical experience. "
            f"No jargon. Respond in {lang_name}.\n\n{text}"
        )
        return self.ask(prompt, max_tokens=max_tokens)

    def get_tip(self, stats_summary: str) -> str | None:
        """Get personalized tip based on usage stats."""
        prompt = (
            f"You are a Claude Code usage advisor. Based on these stats, give ONE specific, "
            f"actionable tip to save tokens or improve efficiency. Max 2 sentences.\n\n"
            f"Stats: {stats_summary}"
        )
        return self.ask(prompt)

    def recommend_model(self, task_description: str) -> str | None:
        """Recommend model based on task."""
        prompt = (
            f"You are a Claude model advisor. For this task, recommend Opus, Sonnet, or Haiku. "
            f"ONE sentence with estimated token savings.\n\n"
            f"Task: {task_description[:200]}"
        )
        return self.ask(prompt, max_tokens=100)

    def explain_finding(self, finding_description: str, project_context: str = "") -> str | None:
        """Explain a security finding in context."""
        prompt = (
            f"Explain this security finding in simple terms for a developer. "
            f"What is the risk? How to fix it? 3 sentences max.\n\n"
            f"Finding: {finding_description}\n"
            f"Project context: {project_context or 'general dev environment'}"
        )
        return self.ask(prompt, max_tokens=150)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_haiku_batch.py -v`
Expected: all 5 PASS

- [ ] **Step 6: Commit**

```bash
git add core/haiku_client.py core/config.py tests/test_haiku_batch.py
git commit -m "feat: HaikuClient batch_explain, config fallback, 30s rate limit"
```

---

### Task 2: Project Detector — auto-detect project from Claude sessions

**Files:**
- Create: `core/project_detector.py`
- Modify: `core/history.py:27-54` (add `app_state` table to `init()`)
- Create: `tests/test_project_detector.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_project_detector.py
"""Tests for project detector."""

import tempfile
import os
from pathlib import Path
from core.project_detector import detect_projects, get_last_project, save_last_project
from core.history import HistoryDB


def test_detect_projects_no_claude_dir():
    projects = detect_projects("/nonexistent/path")
    assert projects == []


def test_detect_projects_from_claude_dir(tmp_path):
    # Create fake .claude/projects structure
    proj_dir = tmp_path / ".claude" / "projects"
    proj_dir.mkdir(parents=True)
    # Claude encodes paths: -home-user-myproject
    fake_proj = proj_dir / "-home-user-myproject"
    fake_proj.mkdir()
    (fake_proj / "session.jsonl").write_text("{}")

    projects = detect_projects(str(tmp_path / ".claude"))
    assert len(projects) >= 1
    assert projects[0]["path"] == "/home/user/myproject"


def test_save_and_get_last_project():
    db = HistoryDB(db_path=":memory:")
    db.init()
    assert get_last_project(db) is None
    save_last_project(db, "/home/user/proj")
    assert get_last_project(db) == "/home/user/proj"
    save_last_project(db, "/home/user/proj2")
    assert get_last_project(db) == "/home/user/proj2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_project_detector.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Add `app_state` table to HistoryDB.init()**

In `core/history.py`, add after the `snapshots` CREATE TABLE in `init()` method (after line 53):

```python
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
```

- [ ] **Step 4: Add helper methods to HistoryDB for app_state**

In `core/history.py`, add before the `close()` method:

```python
    def get_state(self, key: str) -> str | None:
        self._ensure_conn()
        cursor = self._conn.execute(
            "SELECT value FROM app_state WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str) -> None:
        self._ensure_conn()
        self._conn.execute(
            "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()
```

- [ ] **Step 5: Implement project_detector.py**

```python
# core/project_detector.py
"""Auto-detect projects from ~/.claude/projects/ directory."""

from __future__ import annotations

import logging
from pathlib import Path

from core.history import HistoryDB

log = logging.getLogger(__name__)

_LAST_PROJECT_KEY = "last_project_dir"


def detect_projects(claude_dir: str) -> list[dict]:
    """Scan claude_dir/projects/ for project directories.

    Returns list of {path, mtime} sorted by most recent first.
    Claude stores projects as encoded paths: -home-user-project
    """
    projects_dir = Path(claude_dir) / "projects"
    if not projects_dir.is_dir():
        return []

    results = []
    for entry in projects_dir.iterdir():
        if not entry.is_dir():
            continue
        # Decode: -home-user-project → /home/user/project
        decoded = entry.name.replace("-", "/", 1) if entry.name.startswith("-") else entry.name
        # Handle remaining dashes that are path separators
        # Claude uses the full path with - as separator
        decoded = "/" + entry.name[1:].replace("-", "/") if entry.name.startswith("-") else entry.name

        # Get most recent modification time from contents
        try:
            mtime = max(
                (f.stat().st_mtime for f in entry.rglob("*") if f.is_file()),
                default=entry.stat().st_mtime,
            )
        except OSError:
            mtime = 0

        # Check if decoded path actually exists on disk
        real_path = Path(decoded)
        if real_path.is_dir():
            results.append({"path": decoded, "mtime": mtime, "name": real_path.name})
        else:
            # Path might not exist anymore, still show it
            results.append({"path": decoded, "mtime": mtime, "name": entry.name})

    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results


def get_last_project(db: HistoryDB) -> str | None:
    """Get last used project directory from app_state."""
    return db.get_state(_LAST_PROJECT_KEY)


def save_last_project(db: HistoryDB, path: str) -> None:
    """Save last used project directory to app_state."""
    db.set_state(_LAST_PROJECT_KEY, path)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_project_detector.py -v`
Expected: all 3 PASS

- [ ] **Step 7: Commit**

```bash
git add core/project_detector.py core/history.py tests/test_project_detector.py
git commit -m "feat: project detector — auto-detect from ~/.claude/projects/"
```

---

### Task 3: Project Selector widget — shared dropdown across tabs

**Files:**
- Create: `gui/widgets/project_selector.py`
- Modify: `gui/app.py:127-151` (add project selector to header area)
- Modify: `gui/app.py:192-197` (connect project selector signals)

- [ ] **Step 1: Create project selector widget**

```python
# gui/widgets/project_selector.py
"""Shared project selector — dropdown + Browse button."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QComboBox, QPushButton, QFileDialog, QLabel,
)
from PyQt5.QtCore import pyqtSignal

from i18n import get_string as _t
from core.project_detector import detect_projects, get_last_project, save_last_project
from core.history import HistoryDB


class ProjectSelector(QWidget):
    """Shared project directory selector with auto-detection."""

    project_changed = pyqtSignal(str)  # emits project path

    def __init__(self, db: HistoryDB, claude_dir: str | None = None, parent=None):
        super().__init__(parent)
        self._db = db
        self._claude_dir = claude_dir
        self._current_path: str | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        lbl = QLabel(_t("project_label"))
        lbl.setStyleSheet("font-weight: bold; color: #000080;")
        layout.addWidget(lbl)

        self._combo = QComboBox()
        self._combo.setMinimumWidth(300)
        self._combo.setStyleSheet(
            "QComboBox { background: white; border: 2px inset #808080; padding: 2px; }"
        )
        self._combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self._combo)

        btn_browse = QPushButton(_t("project_browse"))
        btn_browse.setStyleSheet(
            "QPushButton { padding: 3px 10px; border: 2px outset #dfdfdf; }"
        )
        btn_browse.clicked.connect(self._on_browse)
        layout.addWidget(btn_browse)

        layout.addStretch()

        self._populate()

    def _populate(self) -> None:
        """Fill combo with detected projects + last used."""
        self._combo.blockSignals(True)
        self._combo.clear()

        projects = []
        if self._claude_dir:
            projects = detect_projects(self._claude_dir)

        last = get_last_project(self._db)

        # Add projects to combo
        seen = set()
        if last and last not in seen:
            self._combo.addItem(f"{Path(last).name}  ({last})", last)
            seen.add(last)

        for proj in projects:
            if proj["path"] not in seen:
                self._combo.addItem(f"{proj['name']}  ({proj['path']})", proj["path"])
                seen.add(proj["path"])

        if self._combo.count() == 0:
            self._combo.addItem(_t("project_none"), "")

        self._combo.blockSignals(False)

        # Auto-select last project
        if last:
            self._set_project(last, emit=True)
        elif self._combo.count() > 0 and self._combo.itemData(0):
            self._set_project(self._combo.itemData(0), emit=True)

    def _on_combo_changed(self, index: int) -> None:
        path = self._combo.itemData(index)
        if path:
            self._set_project(path, emit=True)

    def _on_browse(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(
            self, _t("project_browse"), str(Path.home()),
        )
        if dir_path:
            # Add to combo if not already present
            found = False
            for i in range(self._combo.count()):
                if self._combo.itemData(i) == dir_path:
                    self._combo.setCurrentIndex(i)
                    found = True
                    break
            if not found:
                name = Path(dir_path).name
                self._combo.addItem(f"{name}  ({dir_path})", dir_path)
                self._combo.setCurrentIndex(self._combo.count() - 1)

    def _set_project(self, path: str, emit: bool = False) -> None:
        if path == self._current_path:
            return
        self._current_path = path
        save_last_project(self._db, path)
        if emit:
            self.project_changed.emit(path)

    def current_project(self) -> str | None:
        return self._current_path
```

- [ ] **Step 2: Wire ProjectSelector into app.py**

In `gui/app.py`, add import at top (after line 40):

```python
from gui.widgets.project_selector import ProjectSelector
```

In `MonitorApp.__init__`, after `main_layout.addWidget(self.sidebar)` (line 151), add the project selector above the stack:

```python
        # Right side: project selector on top + content stack below
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Shared project selector
        self._project_db = None
        try:
            from core.history import HistoryDB
            self._project_db = HistoryDB()
            self._project_db.init()
        except Exception:
            pass

        claude_dir = str(system_state.claude_dir) if system_state.claude_dir else None
        self.project_selector = ProjectSelector(
            db=self._project_db or HistoryDB(db_path=":memory:"),
            claude_dir=claude_dir,
        )
        self.project_selector.project_changed.connect(self._on_project_changed)
        right_layout.addWidget(self.project_selector)

        right_layout.addWidget(self.stack)
        main_layout.addWidget(right_panel)
```

Remove the old `main_layout.addWidget(self.stack)` line (line 186).

Add the `_on_project_changed` method:

```python
    def _on_project_changed(self, path: str) -> None:
        """Sync project directory to Activity, Health, Snapshots."""
        self.page_activity.set_project_dir(path)
        self.page_snapshots.set_project_dir(path)
        self.page_health._project_dir = path
        self.page_health._dir_label.setText(
            path if len(path) <= 50 else "..." + path[-47:]
        )
        self.page_health._dir_label.setStyleSheet("color: #000000;")
        self.page_health._btn_scan.setEnabled(True)
```

- [ ] **Step 3: Add i18n strings**

Add to both `i18n/en.py` and `i18n/ua.py` STRINGS dicts:

EN:
```python
    "project_label": "Project:",
    "project_browse": "Browse...",
    "project_none": "No project selected",
```

UA:
```python
    "project_label": "Проект:",
    "project_browse": "Огляд...",
    "project_none": "Проект не обрано",
```

- [ ] **Step 4: Test manually — launch app, verify project auto-selects**

Run: `cd /home/dchuprina/claude-monitor && python -m gui.app`
Expected: project selector visible at top, auto-selects last used project

- [ ] **Step 5: Commit**

```bash
git add gui/widgets/project_selector.py gui/app.py i18n/en.py i18n/ua.py
git commit -m "feat: shared project selector — auto-detect from Claude sessions"
```

---

### Task 4: CopyableSection widget + copy buttons

**Files:**
- Modify: `gui/copyable_table.py`
- Create: `tests/test_copyable_section.py`

- [ ] **Step 1: Write test**

```python
# tests/test_copyable_section.py
"""Tests for CopyableSection text extraction."""

from gui.copyable_widgets import extract_text_from_labels


def test_extract_text_from_labels():
    texts = ["Line 1", "Line 2", "Line 3"]
    result = extract_text_from_labels(texts)
    assert result == "Line 1\nLine 2\nLine 3"


def test_extract_empty():
    assert extract_text_from_labels([]) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_copyable_section.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Create copyable_widgets.py with CopyableSection and copy button factory**

```python
# gui/copyable_widgets.py
"""Copy-to-clipboard widgets for all pages."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QPushButton, QApplication, QLabel, QWidget,
)
from PyQt5.QtCore import Qt

from i18n import get_string as _t


def extract_text_from_labels(texts: list[str]) -> str:
    """Join text lines for clipboard."""
    return "\n".join(texts)


def _collect_label_texts(widget: QWidget) -> list[str]:
    """Recursively collect text from all QLabels inside a widget."""
    texts = []
    for child in widget.findChildren(QLabel):
        text = child.text().strip()
        if text:
            texts.append(text)
    return texts


class CopyableSection(QGroupBox):
    """QGroupBox with built-in 'Copy' button."""

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.setStyleSheet(
            "QGroupBox { border: 2px groove #808080; margin-top: 12px; "
            "padding-top: 16px; font-weight: bold; background: white; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; "
            "padding: 0 4px; }"
        )
        self._inner_layout = QVBoxLayout(self)
        self._inner_layout.setSpacing(2)

    def layout(self):
        return self._inner_layout

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
            self.copy_to_clipboard()
        else:
            super().keyPressEvent(event)

    def copy_to_clipboard(self) -> None:
        texts = _collect_label_texts(self)
        if texts:
            QApplication.clipboard().setText("\n".join(texts))


def make_copy_all_button(get_text_fn) -> QPushButton:
    """Create a 'Copy all' button that calls get_text_fn() on click."""
    btn = QPushButton(_t("copy_all"))
    btn.setStyleSheet(
        "QPushButton { padding: 3px 12px; border: 2px outset #dfdfdf; font-size: 11px; }"
        "QPushButton:pressed { border: 2px inset #808080; }"
    )
    btn.setFixedHeight(24)

    def _on_click():
        text = get_text_fn()
        if text:
            QApplication.clipboard().setText(text)

    btn.clicked.connect(_on_click)
    return btn
```

- [ ] **Step 4: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_copyable_section.py -v`
Expected: PASS

- [ ] **Step 5: Add i18n strings for copy**

EN:
```python
    "copy_all": "Copy all",
    "copy_done": "Copied!",
```

UA:
```python
    "copy_all": "Копіювати все",
    "copy_done": "Скопійовано!",
```

- [ ] **Step 6: Commit**

```bash
git add gui/copyable_widgets.py tests/test_copyable_section.py i18n/en.py i18n/ua.py
git commit -m "feat: CopyableSection widget + copy-all button factory"
```

---

### Task 5: Settings — HaikuHoff section

**Files:**
- Modify: `gui/pages/settings.py:11-28` (add HaikuHoff group before language group)

- [ ] **Step 1: Add HaikuHoff group to settings.py**

In `gui/pages/settings.py`, after `layout = QVBoxLayout(self)` (line 17), add BEFORE the language group:

```python
        # --- HaikuHoff ---
        haiku_group = QGroupBox("HaikuHoff")
        hg = QFormLayout()

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("sk-ant-...")
        current_key = config.get("haiku", {}).get("api_key", "")
        self.api_key_input.setText(current_key)
        hg.addRow("HaikuHoff Key:", self.api_key_input)

        haiku_hint = QLabel(_t("haiku_hint"))
        haiku_hint.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
        haiku_hint.setWordWrap(True)
        hg.addRow(haiku_hint)

        test_row = QHBoxLayout()
        self.btn_test_haiku = QPushButton(_t("haiku_test"))
        self.btn_test_haiku.setFixedWidth(80)
        self.btn_test_haiku.clicked.connect(self._test_haiku)
        test_row.addWidget(self.btn_test_haiku)

        self.haiku_status = QLabel("")
        self.haiku_status.setStyleSheet("font-style: italic; padding-left: 8px;")
        test_row.addWidget(self.haiku_status)
        test_row.addStretch()
        hg.addRow(test_row)

        haiku_group.setLayout(hg)
        layout.addWidget(haiku_group)
```

Add `QLineEdit, QHBoxLayout` to PyQt5 imports at top.

Add `_test_haiku` method and update `_apply` to save api_key:

```python
    def _test_haiku(self):
        key = self.api_key_input.text().strip()
        if not key:
            self.haiku_status.setText(_t("haiku_no_key"))
            self.haiku_status.setStyleSheet("color: #cc0000; font-style: italic; padding-left: 8px;")
            return

        self.haiku_status.setText(_t("haiku_testing"))
        self.haiku_status.setStyleSheet("color: #808080; font-style: italic; padding-left: 8px;")

        from core.haiku_client import HaikuClient
        client = HaikuClient(api_key=key)
        client._min_interval = 0  # skip rate limit for test
        result = client.ask("Say OK", max_tokens=5)
        if result:
            self.haiku_status.setText(_t("haiku_connected"))
            self.haiku_status.setStyleSheet("color: #006600; font-style: italic; padding-left: 8px;")
        else:
            self.haiku_status.setText(_t("haiku_failed"))
            self.haiku_status.setStyleSheet("color: #cc0000; font-style: italic; padding-left: 8px;")
```

In `_apply`, add before writing config:

```python
        self._config.setdefault("haiku", {})
        self._config["haiku"]["api_key"] = self.api_key_input.text().strip()
```

- [ ] **Step 2: Add i18n strings**

EN:
```python
    "haiku_hint": "Claude API key — Haiku will explain everything in human language",
    "haiku_test": "Test",
    "haiku_no_key": "No key entered",
    "haiku_testing": "Testing...",
    "haiku_connected": "Connected!",
    "haiku_failed": "Connection failed",
```

UA:
```python
    "haiku_hint": "Ключ від Claude API — Haiku буде пояснювати все людською мовою",
    "haiku_test": "Тест",
    "haiku_no_key": "Ключ не введено",
    "haiku_testing": "Перевіряю...",
    "haiku_connected": "Підключено!",
    "haiku_failed": "Помилка підключення",
```

- [ ] **Step 3: Test manually — launch app, go to Settings, enter test key**

Run: `cd /home/dchuprina/claude-monitor && python -m gui.app`
Expected: HaikuHoff section visible with password field and Test button

- [ ] **Step 4: Commit**

```bash
git add gui/pages/settings.py i18n/en.py i18n/ua.py
git commit -m "feat: Settings — HaikuHoff section with API key + test connection"
```

---

### Task 6: Activity Log — timeline with "where you stopped" and history

**Files:**
- Modify: `core/history.py` (add `activity_log` table)
- Modify: `gui/pages/activity.py` (rewrite to 3-block layout with timeline)
- Modify: `core/activity_tracker.py` (add serialize/deserialize for SQLite)

- [ ] **Step 1: Add activity_log table to HistoryDB.init()**

In `core/history.py`, add after the `app_state` CREATE TABLE:

```python
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_dir TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                entry_json TEXT NOT NULL,
                haiku_summary TEXT DEFAULT '',
                haiku_context TEXT DEFAULT ''
            )
        """)
```

Add methods to HistoryDB:

```python
    def save_activity(self, project_dir: str, timestamp: str,
                      entry_json: str, haiku_summary: str = "",
                      haiku_context: str = "") -> int:
        self._ensure_conn()
        cursor = self._conn.execute(
            """INSERT INTO activity_log
               (project_dir, timestamp, entry_json, haiku_summary, haiku_context)
               VALUES (?, ?, ?, ?, ?)""",
            (project_dir, timestamp, entry_json, haiku_summary, haiku_context),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_activity_log(self, project_dir: str, limit: int = 20) -> list[dict]:
        self._ensure_conn()
        cursor = self._conn.execute(
            """SELECT id, timestamp, entry_json, haiku_summary, haiku_context
               FROM activity_log
               WHERE project_dir = ?
               ORDER BY id DESC LIMIT ?""",
            (project_dir, limit),
        )
        return [
            {"id": r[0], "timestamp": r[1], "entry_json": r[2],
             "haiku_summary": r[3], "haiku_context": r[4]}
            for r in cursor.fetchall()
        ]

    def get_latest_activity(self, project_dir: str) -> dict | None:
        self._ensure_conn()
        cursor = self._conn.execute(
            """SELECT id, timestamp, entry_json, haiku_summary, haiku_context
               FROM activity_log
               WHERE project_dir = ?
               ORDER BY id DESC LIMIT 1""",
            (project_dir,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {"id": row[0], "timestamp": row[1], "entry_json": row[2],
                "haiku_summary": row[3], "haiku_context": row[4]}
```

- [ ] **Step 2: Add serialization to ActivityEntry**

In `core/activity_tracker.py`, add at the bottom:

```python
def serialize_activity(entry: ActivityEntry) -> str:
    """Serialize ActivityEntry to JSON string for SQLite storage."""
    import json
    data = {
        "timestamp": entry.timestamp,
        "project_dir": entry.project_dir,
        "files": [
            {"path": f.path, "status": f.status, "additions": f.additions,
             "deletions": f.deletions, "explanation": f.explanation}
            for f in entry.files
        ],
        "docker_changes": [
            {"name": d.name, "image": d.image, "status": d.status,
             "ports": d.ports, "explanation": d.explanation}
            for d in entry.docker_changes
        ],
        "port_changes": [
            {"port": p.port, "process": p.process, "status": p.status,
             "explanation": p.explanation}
            for p in entry.port_changes
        ],
        "commits": entry.commits,
    }
    return json.dumps(data, ensure_ascii=False)


def deserialize_activity(json_str: str) -> ActivityEntry:
    """Deserialize ActivityEntry from JSON string."""
    import json
    data = json.loads(json_str)
    return ActivityEntry(
        timestamp=data["timestamp"],
        project_dir=data.get("project_dir", ""),
        files=[FileChange(**f) for f in data.get("files", [])],
        docker_changes=[DockerChange(**d) for d in data.get("docker_changes", [])],
        port_changes=[PortChange(**p) for p in data.get("port_changes", [])],
        commits=data.get("commits", []),
    )
```

- [ ] **Step 3: Rewrite activity.py with 3-block layout**

Replace `gui/pages/activity.py` entirely:

```python
"""Activity Log page — timeline with 'where you stopped' and Haiku explanations."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QScrollArea, QFrame, QApplication,
)
from PyQt5.QtCore import pyqtSignal, Qt, QThread
from PyQt5.QtGui import QFont

from i18n import get_string as _t, get_language
from core.activity_tracker import ActivityTracker, serialize_activity, deserialize_activity
from core.models import ActivityEntry, FileChange, DockerChange, PortChange
from gui.copyable_widgets import make_copy_all_button


class HaikuContextThread(QThread):
    """Get Haiku 'where you stopped' summary in background."""
    done = pyqtSignal(str, str)  # context_text, summary_text

    def __init__(self, commits: list[str], files: list[FileChange],
                 config: dict, parent=None):
        super().__init__(parent)
        self._commits = commits
        self._files = files
        self._config = config

    def run(self):
        context = ""
        summary = ""
        try:
            from core.haiku_client import HaikuClient
            lang = get_language()
            lang_name = "Ukrainian" if lang == "ua" else "English"
            haiku = HaikuClient(config=self._config)
            if not haiku.is_available():
                self.done.emit("", "")
                return

            # "Where you stopped" context
            if self._commits:
                commits_text = "\n".join(self._commits[:5])
                files_text = "\n".join(
                    f"{f.status}: {f.path} — {f.explanation}" for f in self._files[:10]
                )
                prompt = (
                    f"Here are the last commits and changed files in a project. "
                    f"Explain in 2-3 sentences what the user was working on and where they stopped. "
                    f"Simple words, no jargon. Respond in {lang_name}.\n\n"
                    f"Commits:\n{commits_text}\n\nChanged files:\n{files_text}"
                )
                context = haiku.ask(prompt, max_tokens=200) or ""

            # Activity summary
            if self._files:
                changes = "\n".join(
                    f"{f.status}: {f.path} (+{f.additions}/-{f.deletions}) — {f.explanation}"
                    for f in self._files[:15]
                )
                prompt = (
                    f"Here are the changes in a project. "
                    f"Explain briefly what happened, for each group of changes — 1-2 sentences. "
                    f"Simple words, no jargon. Respond in {lang_name}.\n\n{changes}"
                )
                summary = haiku.ask(prompt, max_tokens=300) or ""
        except Exception:
            pass
        self.done.emit(context, summary)


class ActivityPage(QWidget):
    """Activity Log — what changed, where you stopped, what's unfinished."""

    refresh_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._project_dir: str | None = None
        self._tracker: ActivityTracker | None = None
        self._config: dict = {}
        self._haiku_thread: HaikuContextThread | None = None
        self._all_texts: list[str] = []
        self._build_ui()

    def set_config(self, config: dict) -> None:
        self._config = config

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header row: title + refresh + copy
        header = QHBoxLayout()
        title = QLabel(_t("activity_header"))
        title.setFont(QFont("MS Sans Serif", 14, QFont.Bold))
        title.setStyleSheet("color: #000080;")
        header.addWidget(title)
        header.addStretch()

        self._btn_refresh = QPushButton(_t("activity_btn_refresh"))
        self._btn_refresh.clicked.connect(self._on_refresh)
        header.addWidget(self._btn_refresh)

        header.addWidget(make_copy_all_button(self._get_all_text))

        layout.addLayout(header)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 2px inset #808080; background: white; }")

        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._content_widget)

        layout.addWidget(scroll)

        self._show_placeholder(_t("activity_select_dir"))

    def _get_all_text(self) -> str:
        return "\n".join(self._all_texts)

    def _show_placeholder(self, text: str) -> None:
        self._clear_content()
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #808080; font-size: 14px; padding: 40px;")
        self._content_layout.addWidget(lbl)

    def _clear_content(self) -> None:
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._all_texts.clear()

    def set_project_dir(self, path: str) -> None:
        self._project_dir = path
        self._tracker = ActivityTracker(path)
        self._on_refresh()

    def _on_refresh(self) -> None:
        if not self._tracker or not self._project_dir:
            self._show_placeholder(_t("activity_select_dir"))
            return
        if not shutil.which("git"):
            self._show_placeholder(_t("activity_git_not_found"))
            return
        self.refresh_requested.emit()

    def update_data(
        self,
        entry: ActivityEntry | None = None,
        docker_data: list[dict] | None = None,
        port_data: list[dict] | None = None,
    ) -> None:
        if not self._tracker:
            return

        if entry is None:
            entry = self._tracker.collect_activity(
                docker_containers=docker_data,
                ports=port_data,
            )

        self._render_activity(entry)

        # Save to history
        try:
            from core.history import HistoryDB
            db = HistoryDB()
            db.init()
            db.save_activity(
                project_dir=entry.project_dir or self._project_dir or "",
                timestamp=entry.timestamp,
                entry_json=serialize_activity(entry),
            )
            db.close()
        except Exception:
            pass

        # Request Haiku context in background
        if entry.commits or entry.files:
            self._haiku_thread = HaikuContextThread(
                commits=entry.commits,
                files=entry.files,
                config=self._config,
            )
            self._haiku_thread.done.connect(self._on_haiku_done)
            self._haiku_thread.start()

    def _on_haiku_done(self, context: str, summary: str) -> None:
        """Insert Haiku context block at top of content."""
        if not context and not summary:
            return

        # Insert at the beginning
        if context:
            block = self._make_context_block(context)
            self._content_layout.insertWidget(0, block)
            self._all_texts.insert(0, f"[{_t('activity_where_stopped')}] {context}")

        if summary:
            # Find the files group and add summary under its title
            # Just add a summary label after the context block
            lbl = QLabel(f"  {summary}")
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                "color: #333; font-style: italic; font-size: 11px; "
                "padding: 4px 8px; background: #f0f0ff; "
                "border-left: 3px solid #000080;"
            )
            insert_pos = 1 if context else 0
            self._content_layout.insertWidget(insert_pos, lbl)

    def _make_context_block(self, text: str) -> QFrame:
        """Create highlighted 'where you stopped' block."""
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #fffff0; border: 2px solid #cc9900; "
            "padding: 8px; margin-bottom: 4px; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)

        header = QLabel(f"  {_t('activity_where_stopped')}")
        header.setFont(QFont("MS Sans Serif", 11, QFont.Bold))
        header.setStyleSheet("color: #806600; border: none;")
        layout.addWidget(header)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setStyleSheet("color: #333; font-size: 12px; border: none; padding-top: 4px;")
        layout.addWidget(body)

        return frame

    def _render_activity(self, entry: ActivityEntry) -> None:
        self._clear_content()
        has_content = False

        # Format timestamp
        try:
            dt = datetime.fromisoformat(entry.timestamp)
            now = datetime.now()
            if dt.date() == now.date():
                time_label = f"{_t('activity_today')}, {dt.strftime('%H:%M')}"
            else:
                time_label = dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            time_label = entry.timestamp

        # Timestamp header
        ts_lbl = QLabel(f"  {time_label}")
        ts_lbl.setStyleSheet(
            "color: #808080; font-size: 11px; font-weight: bold; padding: 4px;"
        )
        self._content_layout.addWidget(ts_lbl)
        self._all_texts.append(f"--- {time_label} ---")

        # Git files
        if entry.files:
            has_content = True
            group = self._make_group(
                f"{_t('activity_files_header')} ({len(entry.files)})"
            )
            group_layout = group.layout()
            for fc in entry.files:
                row = self._make_file_row(fc)
                group_layout.addWidget(row)
                self._all_texts.append(
                    f"  {fc.status}: {fc.path} (+{fc.additions}/-{fc.deletions}) — {fc.explanation}"
                )
            self._content_layout.addWidget(group)

        # Docker changes
        if entry.docker_changes:
            has_content = True
            group = self._make_group(_t("activity_docker_header"))
            group_layout = group.layout()
            for dc in entry.docker_changes:
                row = self._make_docker_row(dc)
                group_layout.addWidget(row)
                self._all_texts.append(f"  Docker: {dc.status} {dc.name} ({dc.image})")
            self._content_layout.addWidget(group)

        # Port changes
        if entry.port_changes:
            has_content = True
            group = self._make_group(_t("activity_ports_header"))
            group_layout = group.layout()
            for pc in entry.port_changes:
                row = self._make_port_row(pc)
                group_layout.addWidget(row)
                self._all_texts.append(f"  Port: {pc.status} :{pc.port} ({pc.process})")
            self._content_layout.addWidget(group)

        # Recent commits
        if entry.commits:
            has_content = True
            group = self._make_group(_t("activity_commits_header"))
            group_layout = group.layout()
            for commit in entry.commits:
                lbl = QLabel(f"  {commit}")
                lbl.setStyleSheet("font-family: monospace; color: #333;")
                group_layout.addWidget(lbl)
                self._all_texts.append(f"  {commit}")
            self._content_layout.addWidget(group)

        if not has_content:
            if self._tracker and not self._tracker.is_git_repo():
                self._show_placeholder(_t("activity_no_git"))
            else:
                self._show_placeholder(_t("activity_no_changes"))

        self._content_layout.addStretch()

    def _make_group(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        group.setStyleSheet(
            "QGroupBox { border: 2px groove #808080; margin-top: 12px; "
            "padding-top: 16px; font-weight: bold; background: white; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; "
            "padding: 0 4px; }"
        )
        layout = QVBoxLayout(group)
        layout.setSpacing(2)
        return group

    def _make_file_row(self, fc: FileChange) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(1)

        top = QHBoxLayout()
        status_map = {
            "added": ("+", "#006600", _t("activity_file_added")),
            "modified": ("~", "#000080", _t("activity_file_modified")),
            "deleted": ("-", "#cc0000", _t("activity_file_deleted")),
            "renamed": ("R", "#806600", _t("activity_file_renamed")),
        }
        icon, color, label = status_map.get(fc.status, ("?", "#808080", fc.status))

        status_lbl = QLabel(icon)
        status_lbl.setFixedWidth(16)
        status_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-family: monospace;")
        top.addWidget(status_lbl)

        path_lbl = QLabel(fc.path)
        path_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        top.addWidget(path_lbl)

        if fc.status in ("added", "deleted"):
            tag = QLabel(f"({label})")
            tag.setStyleSheet(f"color: {color}; font-weight: bold;")
            top.addWidget(tag)

        top.addStretch()

        if fc.additions or fc.deletions:
            stats_parts = []
            if fc.additions:
                stats_parts.append(f"+{fc.additions}")
            if fc.deletions:
                stats_parts.append(f"-{fc.deletions}")
            stats_lbl = QLabel(" ".join(stats_parts))
            stats_lbl.setStyleSheet("color: #808080; font-family: monospace;")
            top.addWidget(stats_lbl)

        layout.addLayout(top)

        if fc.explanation:
            is_env = ".env" in fc.path.lower()
            expl_color = "#cc6600" if is_env else "#666666"
            prefix = "\u26a0\ufe0f " if is_env else "  "
            expl_text = _t("activity_env_warning") if is_env else fc.explanation
            expl_lbl = QLabel(f"{prefix}{expl_text}")
            expl_lbl.setStyleSheet(f"color: {expl_color}; font-size: 11px;")
            layout.addWidget(expl_lbl)

        return frame

    def _make_docker_row(self, dc: DockerChange) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)

        status_styles = {
            "new": ("+", "#006600"), "removed": ("-", "#cc0000"),
            "crashed": ("\u25cf", "#cc0000"), "restarted": ("\u25cf", "#cc6600"),
        }
        icon, color = status_styles.get(dc.status, ("?", "#808080"))

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(20)
        icon_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(icon_lbl)

        name_lbl = QLabel(dc.name)
        name_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(name_lbl)

        if dc.image:
            img_lbl = QLabel(f"({dc.image})")
            img_lbl.setStyleSheet("color: #808080;")
            layout.addWidget(img_lbl)

        layout.addStretch()

        status_text = {
            "new": _t("activity_docker_new"), "removed": _t("activity_docker_removed"),
            "crashed": _t("activity_docker_crashed"), "restarted": _t("activity_docker_restarted"),
        }.get(dc.status, dc.status)

        status_tag = QLabel(status_text)
        status_tag.setStyleSheet(
            f"color: {color}; font-weight: bold; border: 1px solid #808080; padding: 1px 4px;"
        )
        layout.addWidget(status_tag)

        return frame

    def _make_port_row(self, pc: PortChange) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)

        is_new = pc.status == "new"
        color = "#006600" if is_new else "#cc0000"
        icon = "+" if is_new else "-"

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(16)
        icon_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-family: monospace;")
        layout.addWidget(icon_lbl)

        port_lbl = QLabel(f":{pc.port}")
        port_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-family: monospace;")
        layout.addWidget(port_lbl)

        if pc.process:
            proc_lbl = QLabel(f"({pc.process})")
            proc_lbl.setStyleSheet("color: #808080;")
            layout.addWidget(proc_lbl)

        layout.addStretch()

        tag_text = _t("activity_port_new") if is_new else _t("activity_port_closed")
        tag = QLabel(tag_text)
        tag.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(tag)

        return frame
```

- [ ] **Step 4: Add i18n strings**

EN:
```python
    "activity_where_stopped": "Where you left off",
    "activity_today": "Today",
    "activity_unfinished": "Unfinished",
    "activity_unfinished_hint": "Run Health scan to see unfinished work",
```

UA:
```python
    "activity_where_stopped": "Де ти зупинився",
    "activity_today": "Сьогодні",
    "activity_unfinished": "Незакінчене",
    "activity_unfinished_hint": "Запусти Health scan щоб побачити незакінчене",
```

- [ ] **Step 5: Wire config to ActivityPage in app.py**

In `gui/app.py`, after creating `self.page_activity = ActivityPage()` (line 165), add:

```python
        self.page_activity.set_config(config)
```

- [ ] **Step 6: Test manually — launch, select project, verify timeline + Haiku context**

Run: `cd /home/dchuprina/claude-monitor && python -m gui.app`
Expected: Activity tab shows timeline with timestamps. If API key set — "where you stopped" block appears.

- [ ] **Step 7: Commit**

```bash
git add core/history.py core/activity_tracker.py gui/pages/activity.py gui/app.py i18n/en.py i18n/ua.py
git commit -m "feat: Activity Log — timeline, 'where you stopped', Haiku context, copy-all"
```

---

### Task 7: Health page — Haiku explains findings "for dummies"

**Files:**
- Modify: `gui/pages/health_page.py` (add Haiku integration + copy)

- [ ] **Step 1: Add HaikuHealthThread and integrate into health_page.py**

In `gui/pages/health_page.py`, add after existing imports:

```python
from i18n import get_language
from gui.copyable_widgets import make_copy_all_button
```

Add a new thread class after `HealthScanThread`:

```python
class HaikuHealthThread(QThread):
    """Get Haiku explanations for top findings in background."""
    done = pyqtSignal(dict, str)  # explanations dict, summary text

    def __init__(self, findings: list, config: dict, parent=None):
        super().__init__(parent)
        self._findings = findings
        self._config = config

    def run(self):
        explanations = {}
        summary = ""
        try:
            from core.haiku_client import HaikuClient
            haiku = HaikuClient(config=self._config)
            if not haiku.is_available():
                self.done.emit({}, "")
                return

            lang = get_language()

            # Batch explain top 10
            top = self._findings[:10]
            items = [f"{f.title}: {f.message}" for f in top]
            explanations = haiku.batch_explain(
                items=items,
                context="code health check results",
                language=lang,
            )

            # Summary
            severity_counts = {}
            for f in self._findings:
                severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1
            stats = ", ".join(f"{k}: {v}" for k, v in severity_counts.items())
            lang_name = "Ukrainian" if lang == "ua" else "English"
            summary_prompt = (
                f"Project health scan found: {stats}. Total {len(self._findings)} issues. "
                f"Give an overall assessment in 2-3 sentences. Simple words, no jargon. "
                f"Respond in {lang_name}."
            )
            summary = haiku.ask(summary_prompt, max_tokens=200) or ""
        except Exception:
            pass
        self.done.emit(explanations, summary)
```

- [ ] **Step 2: Add config, copy button, and Haiku wiring to HealthPage**

Add `set_config` method and modify `__init__`:

```python
    def __init__(self):
        super().__init__()
        self._project_dir: str | None = None
        self._scan_thread: HealthScanThread | None = None
        self._haiku_thread: HaikuHealthThread | None = None
        self._config: dict = {}
        self._all_texts: list[str] = []
        self._last_report: HealthReport | None = None
        self._build_ui()

    def set_config(self, config: dict) -> None:
        self._config = config
```

Add copy button to header in `_build_ui`, after the scan button:

```python
        header.addWidget(make_copy_all_button(lambda: "\n".join(self._all_texts)))
```

Modify `_on_scan_done` to trigger Haiku:

```python
    def _on_scan_done(self, report: HealthReport) -> None:
        self._btn_scan.setEnabled(True)
        self._btn_scan.setText(_t("health_btn_scan"))
        self._last_report = report
        self._render_report(report)

        # Trigger Haiku explanations
        if report.findings:
            self._haiku_thread = HaikuHealthThread(
                findings=report.findings, config=self._config,
            )
            self._haiku_thread.done.connect(self._on_haiku_done)
            self._haiku_thread.start()
```

Add `_on_haiku_done`:

```python
    def _on_haiku_done(self, explanations: dict, summary: str) -> None:
        """Insert Haiku explanations into rendered findings."""
        if summary:
            # Add summary at top
            lbl = QLabel(f"  {summary}")
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                "color: #333; font-style: italic; font-size: 12px; "
                "padding: 8px; background: #f0f0ff; "
                "border: 2px solid #000080; margin: 4px;"
            )
            self._content_layout.insertWidget(0, lbl)
            self._all_texts.insert(0, f"[Summary] {summary}")

        if explanations:
            # Find QFrames with finding rows and add explanation labels
            for i in range(self._content_layout.count()):
                item = self._content_layout.itemAt(i)
                if not item or not item.widget():
                    continue
                widget = item.widget()
                if isinstance(widget, QGroupBox):
                    group_layout = widget.layout()
                    if not group_layout:
                        continue
                    for j in range(group_layout.count()):
                        sub_item = group_layout.itemAt(j)
                        if not sub_item or not sub_item.widget():
                            continue
                        frame = sub_item.widget()
                        if not isinstance(frame, QFrame):
                            continue
                        # Check if any label text matches an explanation key
                        for child_label in frame.findChildren(QLabel):
                            text = child_label.text().strip()
                            for key, expl in explanations.items():
                                if key.split(": ", 1)[-1][:30] in text:
                                    haiku_lbl = QLabel(f"    {expl}")
                                    haiku_lbl.setWordWrap(True)
                                    haiku_lbl.setStyleSheet(
                                        "color: #4040a0; font-style: italic; "
                                        "font-size: 11px; padding: 2px 8px;"
                                    )
                                    frame.layout().addWidget(haiku_lbl)
                                    self._all_texts.append(f"  [Haiku] {expl}")
                                    break
```

In `_make_finding_row`, add to `self._all_texts`:

After creating `msg_lbl`, add:

```python
        self._all_texts.append(f"[{finding.severity}] {finding.title}: {finding.message}")
```

- [ ] **Step 3: Wire config in app.py**

After `self.page_health = HealthPage()`:

```python
        self.page_health.set_config(config)
```

- [ ] **Step 4: Test manually**

Run: `cd /home/dchuprina/claude-monitor && python -m gui.app`
Expected: Health scan shows findings. With API key — Haiku explanations appear under top findings in italic purple. Summary at top.

- [ ] **Step 5: Commit**

```bash
git add gui/pages/health_page.py gui/app.py
git commit -m "feat: Health — Haiku explains findings in human language + copy-all"
```

---

### Task 8: Snapshots — "game saves" with Haiku explanations

**Files:**
- Modify: `core/history.py` (add `haiku_label` column to snapshots)
- Modify: `core/snapshot_manager.py` (accept and store haiku_label)
- Modify: `gui/pages/snapshots.py` (Haiku integration + hint + copy)

- [ ] **Step 1: Add haiku_label column migration**

In `core/history.py`, add after all CREATE TABLE statements in `init()`:

```python
        # Migration: add haiku_label to snapshots if missing
        try:
            self._conn.execute("SELECT haiku_label FROM snapshots LIMIT 1")
        except sqlite3.OperationalError:
            self._conn.execute(
                "ALTER TABLE snapshots ADD COLUMN haiku_label TEXT DEFAULT ''"
            )
            self._conn.commit()
```

- [ ] **Step 2: Update snapshot_manager.py to store/load haiku_label**

In `core/snapshot_manager.py`, modify `create_snapshot` to accept `haiku_label`:

```python
def create_snapshot(
    project_dir: str,
    label: str,
    db: HistoryDB,
    docker_data: list[dict] | None = None,
    port_data: list[dict] | None = None,
    haiku_label: str = "",
) -> EnvironmentSnapshot:
```

Update the INSERT to include `haiku_label`:

```python
    cursor = db._conn.execute(
        """
        INSERT INTO snapshots
        (timestamp, label, project_dir, git_branch, git_last_commit,
         git_tracked_count, git_dirty_files, containers, listening_ports,
         config_checksums, haiku_label)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot.timestamp, snapshot.label, snapshot.project_dir,
            snapshot.git_branch, snapshot.git_last_commit, snapshot.git_tracked_count,
            json.dumps(snapshot.git_dirty_files), json.dumps(snapshot.containers),
            json.dumps(snapshot.listening_ports), json.dumps(snapshot.config_checksums),
            haiku_label,
        ),
    )
```

In `EnvironmentSnapshot` dataclass (`core/models.py`), add field:

```python
    haiku_label: str = ""
```

Update `load_snapshots` to read `haiku_label`:

```python
    cursor = db._conn.execute(
        """
        SELECT id, timestamp, label, project_dir, git_branch, git_last_commit,
               git_tracked_count, git_dirty_files, containers, listening_ports,
               config_checksums, COALESCE(haiku_label, '')
        FROM snapshots
        WHERE project_dir = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (project_dir, limit),
    )
    return [
        EnvironmentSnapshot(
            id=row[0], timestamp=row[1], label=row[2], project_dir=row[3],
            git_branch=row[4], git_last_commit=row[5], git_tracked_count=row[6],
            git_dirty_files=json.loads(row[7]), containers=json.loads(row[8]),
            listening_ports=json.loads(row[9]), config_checksums=json.loads(row[10]),
            haiku_label=row[11],
        )
        for row in cursor.fetchall()
    ]
```

- [ ] **Step 3: Update snapshots.py with hint, Haiku labels, comparison explanation, copy**

Add to imports in `gui/pages/snapshots.py`:

```python
from PyQt5.QtCore import QThread
from i18n import get_language
from gui.copyable_widgets import make_copy_all_button
```

Add hint in `_build_ui`, after the actions layout, before the scroll area:

```python
        # Hint for vibe coders
        hint = QLabel(_t("snap_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "color: #666; font-style: italic; font-size: 11px; "
            "padding: 4px 8px; background: #f8f8ff; border: 1px solid #d0d0d0;"
        )
        layout.addWidget(hint)
```

In `_make_snapshot_row`, show `haiku_label` if available instead of technical info:

```python
        if snap.haiku_label:
            info_lbl = QLabel(snap.haiku_label)
            info_lbl.setStyleSheet("color: #4040a0; font-style: italic; font-size: 11px;")
            layout.addWidget(info_lbl)
        else:
            # Fallback to technical info
            info_parts = []
            if snap.git_branch:
                info_parts.append(snap.git_branch)
            if snap.containers:
                info_parts.append(f"{len(snap.containers)} containers")
            if snap.listening_ports:
                info_parts.append(f"{len(snap.listening_ports)} ports")
            if info_parts:
                info_lbl = QLabel(" | ".join(info_parts))
                info_lbl.setStyleSheet("color: #808080; font-size: 11px;")
                layout.addWidget(info_lbl)
```

Add Haiku thread for comparison explanation:

```python
class HaikuSnapshotThread(QThread):
    done = pyqtSignal(str)

    def __init__(self, diff_text: str, config: dict, parent=None):
        super().__init__(parent)
        self._diff_text = diff_text
        self._config = config

    def run(self):
        try:
            from core.haiku_client import HaikuClient
            haiku = HaikuClient(config=self._config)
            if not haiku.is_available():
                self.done.emit("")
                return
            lang = get_language()
            lang_name = "Ukrainian" if lang == "ua" else "English"
            prompt = (
                f"Here is the difference between two project snapshots. "
                f"Explain in simple words what changed and what it might mean. "
                f"3-5 sentences. No jargon. Respond in {lang_name}.\n\n{self._diff_text}"
            )
            result = haiku.ask(prompt, max_tokens=300) or ""
            self.done.emit(result)
        except Exception:
            self.done.emit("")
```

In `_render_compare`, after building the comparison group, trigger Haiku:

```python
        # Trigger Haiku explanation
        diff_text = f"Branch: {diff.old_branch} -> {diff.new_branch}\n" if diff.branch_changed else ""
        diff_text += f"New dirty files: {diff.dirty_added}\n" if diff.dirty_added else ""
        diff_text += f"Containers added: {diff.containers_added}\n" if diff.containers_added else ""
        diff_text += f"Ports opened: {diff.ports_opened}\n" if diff.ports_opened else ""
        diff_text += f"Configs changed: {diff.configs_changed}\n" if diff.configs_changed else ""

        if diff_text.strip():
            self._haiku_snap_thread = HaikuSnapshotThread(diff_text, self._config)
            self._haiku_snap_thread.done.connect(
                lambda text: self._insert_haiku_compare(group, text)
            )
            self._haiku_snap_thread.start()
```

Add `_insert_haiku_compare`:

```python
    def _insert_haiku_compare(self, group: QGroupBox, text: str) -> None:
        if not text:
            return
        lbl = QLabel(f"  {text}")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            "color: #333; font-style: italic; font-size: 12px; "
            "padding: 8px; background: #f0f0ff; border-left: 3px solid #000080;"
        )
        group.layout().insertWidget(0, lbl)
```

Add `set_config` method and `_config` field, add copy button.

- [ ] **Step 4: Add i18n strings**

EN:
```python
    "snap_hint": "Snapshots = game saves. Take one before AI starts changing things. Then compare what was and what became.",
```

UA:
```python
    "snap_hint": "Знімки = збереження в грі. Зроби знімок перед тим як AI почне щось міняти. Потім порівняй що було і що стало.",
```

- [ ] **Step 5: Wire config in app.py**

After `self.page_snapshots = SnapshotsPage()`:

```python
        self.page_snapshots.set_config(config)
```

- [ ] **Step 6: Test manually**

Run: `cd /home/dchuprina/claude-monitor && python -m gui.app`
Expected: Snapshots page shows hint. With API key — Haiku explanation appears when comparing.

- [ ] **Step 7: Commit**

```bash
git add core/models.py core/history.py core/snapshot_manager.py gui/pages/snapshots.py gui/app.py i18n/en.py i18n/ua.py
git commit -m "feat: Snapshots — game save hint, Haiku labels + comparison explanation"
```

---

### Task 9: Changelog popup — Haiku explains what's new

**Files:**
- Modify: `gui/changelog_popup.py`

- [ ] **Step 1: Add Haiku explanation to changelog popup**

Replace `gui/changelog_popup.py`:

```python
"""Changelog popup — shown when Claude Code version changes."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from i18n import get_string as _t, get_language


class HaikuChangelogThread(QThread):
    done = pyqtSignal(str)

    def __init__(self, old_version: str, new_version: str, config: dict, parent=None):
        super().__init__(parent)
        self._old = old_version
        self._new = new_version
        self._config = config

    def run(self):
        try:
            from core.haiku_client import HaikuClient
            haiku = HaikuClient(config=self._config)
            if not haiku.is_available():
                self.done.emit("")
                return
            lang = get_language()
            lang_name = "Ukrainian" if lang == "ua" else "English"
            prompt = (
                f"Claude Code updated from version {self._old} to {self._new}. "
                f"Briefly explain what might be new and whether anything could break "
                f"in existing projects. 3-5 sentences, simple words. "
                f"Respond in {lang_name}."
            )
            result = haiku.ask(prompt, max_tokens=300) or ""
            self.done.emit(result)
        except Exception:
            self.done.emit("")


class ChangelogPopup(QDialog):
    """Win95-style popup for Claude Code updates with Haiku explanation."""

    def __init__(
        self,
        old_version: str,
        new_version: str,
        changelog_url: str,
        config: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._changelog_url = changelog_url
        self._dismissed = False
        self._config = config or {}

        self.setWindowTitle(_t("changelog_title"))
        self.setMinimumSize(420, 220)
        self.setStyleSheet("QDialog { background: #c0c0c0; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        # Title
        title = QLabel(_t("changelog_title"))
        title.setFont(QFont("MS Sans Serif", 14, QFont.Bold))
        title.setStyleSheet("color: #000080;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(8)

        # Version change
        version_lbl = QLabel(f"{old_version}  \u2192  {new_version}")
        version_lbl.setFont(QFont("MS Sans Serif", 16, QFont.Bold))
        version_lbl.setAlignment(Qt.AlignCenter)
        version_lbl.setStyleSheet("color: #000000;")
        layout.addWidget(version_lbl)

        layout.addSpacing(8)

        # Haiku explanation placeholder
        self._haiku_label = QLabel(_t("changelog_message"))
        self._haiku_label.setWordWrap(True)
        self._haiku_label.setAlignment(Qt.AlignLeft)
        self._haiku_label.setStyleSheet(
            "color: #333; font-size: 12px; padding: 8px; "
            "background: #f8f8ff; border: 1px solid #d0d0d0;"
        )
        layout.addWidget(self._haiku_label)

        layout.addSpacing(12)

        # Buttons
        buttons = QHBoxLayout()

        btn_got_it = QPushButton(_t("changelog_got_it"))
        btn_got_it.setStyleSheet(
            "QPushButton { background: #000080; color: white; padding: 6px 20px; "
            "border: 2px outset #4040c0; font-weight: bold; }"
            "QPushButton:pressed { border: 2px inset #000080; }"
        )
        btn_got_it.clicked.connect(self._on_got_it)
        buttons.addWidget(btn_got_it)

        btn_changelog = QPushButton(_t("changelog_show_full"))
        btn_changelog.setStyleSheet(
            "QPushButton { padding: 6px 20px; border: 2px outset #dfdfdf; }"
            "QPushButton:pressed { border: 2px inset #808080; }"
        )
        btn_changelog.clicked.connect(self._on_show_changelog)
        buttons.addWidget(btn_changelog)

        layout.addLayout(buttons)

        # Start Haiku thread
        self._haiku_thread = HaikuChangelogThread(
            old_version, new_version, self._config,
        )
        self._haiku_thread.done.connect(self._on_haiku_done)
        self._haiku_thread.start()

    def _on_haiku_done(self, text: str) -> None:
        if text:
            self._haiku_label.setText(text)
            self.setMinimumSize(420, 300)
            self.adjustSize()

    def _on_got_it(self) -> None:
        self._dismissed = True
        self.accept()

    def _on_show_changelog(self) -> None:
        from core.platform import get_platform
        get_platform().open_url(self._changelog_url)

    @property
    def was_dismissed(self) -> bool:
        return self._dismissed
```

- [ ] **Step 2: Pass config to ChangelogPopup in app.py**

In `gui/app.py`, in `_check_claude_update` method, change the popup creation:

```python
                popup = ChangelogPopup(
                    old_version=update_info["old_version"],
                    new_version=update_info["new_version"],
                    changelog_url=update_info["changelog_url"],
                    config=self._config,
                    parent=self,
                )
```

- [ ] **Step 3: Test manually**

Can't easily test version change, but verify popup renders without crash.

- [ ] **Step 4: Commit**

```bash
git add gui/changelog_popup.py gui/app.py
git commit -m "feat: Changelog popup — Haiku explains what's new in Claude Code updates"
```

---

### Task 10: Final wiring — pass config everywhere + remove old directory pickers

**Files:**
- Modify: `gui/app.py` (cleanup: remove per-page dir pickers, ensure config flows)
- Modify: `gui/pages/activity.py` (hide dir picker if project_selector exists)
- Modify: `gui/pages/health_page.py` (hide dir picker if project_selector exists)
- Modify: `gui/pages/snapshots.py` (hide dir picker if project_selector exists)

- [ ] **Step 1: Hide per-page directory pickers**

In `gui/pages/activity.py`, `gui/pages/health_page.py`, `gui/pages/snapshots.py` — each page keeps its dir picker as fallback but hides it when called from app with project selector.

Add method to each page:

```python
    def hide_dir_picker(self) -> None:
        """Hide per-page dir picker when shared project selector is active."""
        if hasattr(self, '_btn_select'):
            self._btn_select.hide()
        if hasattr(self, '_dir_label'):
            self._dir_label.hide()
```

In `gui/app.py`, after creating pages and project selector, call:

```python
        self.page_activity.hide_dir_picker()
        self.page_health.hide_dir_picker()
        self.page_snapshots.hide_dir_picker()
```

- [ ] **Step 2: Ensure _on_settings_changed propagates config to pages**

In `gui/app.py`, in `_on_settings_changed`:

```python
    def _on_settings_changed(self, new_config: dict):
        self._config = new_config
        self._alert_manager = AlertManager(new_config)
        set_language(new_config.get("general", {}).get("language", "en"))
        # Propagate config to pages that use Haiku
        self.page_activity.set_config(new_config)
        self.page_health.set_config(new_config)
        if hasattr(self.page_snapshots, 'set_config'):
            self.page_snapshots.set_config(new_config)
        self.statusBar().showMessage("Settings applied", 3000)
```

- [ ] **Step 3: Full manual test**

Run: `cd /home/dchuprina/claude-monitor && python -m gui.app`

Test checklist:
1. Project auto-selects on startup
2. Activity tab shows timeline immediately (no empty page)
3. Settings has HaikuHoff section
4. Health scan runs, findings display
5. Snapshots show hint text
6. Copy All buttons work on Activity, Health
7. If API key set: Haiku explanations appear
8. Language switch updates Haiku prompts

- [ ] **Step 4: Commit**

```bash
git add gui/app.py gui/pages/activity.py gui/pages/health_page.py gui/pages/snapshots.py
git commit -m "feat: final wiring — shared project selector, config propagation, hide per-page pickers"
```

---

### Task 11: Run all existing tests to verify nothing is broken

- [ ] **Step 1: Run full test suite**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v --tb=short 2>&1 | head -80`
Expected: all existing tests PASS, new tests PASS

- [ ] **Step 2: Fix any failures**

If any test fails, fix it. Common issues:
- `HaikuClient` signature changed — update `tests/test_haiku_client.py` to pass `config=None`
- `EnvironmentSnapshot` has new `haiku_label` field — existing tests should be fine (has default)

- [ ] **Step 3: Commit fixes if any**

```bash
git add -u
git commit -m "fix: update tests for Haiku UX overhaul changes"
```
