# Environment Snapshots — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save/compare environment snapshots (git, docker, ports, configs) in SQLite with auto-snapshot at start + configurable timer.

**Architecture:** `snapshot_manager.py` handles CRUD + comparison logic using SQLite (same DB as HistoryDB). Collects data via existing `activity_tracker` + `hashlib` for config checksums. GUI page with list, compare view, and Take Snapshot button. Auto-snapshot via QTimer in app.py.

**Tech Stack:** Python (sqlite3, hashlib, pathlib), PyQt5, existing activity_tracker/docker/psutil

---

## File Structure

### New files

```
core/snapshot_manager.py        # CRUD, compare, auto-prune
gui/pages/snapshots.py          # GUI page
tests/test_snapshot_manager.py   # Tests
```

### Modified files

```
core/models.py                  # EnvironmentSnapshot + SnapshotDiff dataclasses
core/config.py                  # Add [snapshots] defaults
core/history.py                 # Add snapshots table migration
gui/app.py                      # Register page, auto-snapshot, timer
i18n/en.py                      # ~15 new strings
i18n/ua.py                      # ~15 new strings
```

---

### Task 1: Data models + SQLite schema

**Files:**
- Modify: `core/models.py`
- Modify: `core/history.py`
- Test: `tests/test_snapshot_manager.py`

- [ ] **Step 1: Add dataclasses to models.py**

Append to `core/models.py`:

```python
@dataclass
class EnvironmentSnapshot:
    id: int = 0
    timestamp: str = ""
    label: str = ""
    project_dir: str = ""
    git_branch: str = ""
    git_last_commit: str = ""
    git_tracked_count: int = 0
    git_dirty_files: list[str] = field(default_factory=list)
    containers: list[dict] = field(default_factory=list)
    listening_ports: list[dict] = field(default_factory=list)
    config_checksums: dict[str, str] = field(default_factory=dict)


@dataclass
class SnapshotDiff:
    branch_changed: bool = False
    old_branch: str = ""
    new_branch: str = ""
    dirty_added: list[str] = field(default_factory=list)
    dirty_removed: list[str] = field(default_factory=list)
    containers_added: list[str] = field(default_factory=list)
    containers_removed: list[str] = field(default_factory=list)
    containers_status_changed: list[tuple] = field(default_factory=list)
    ports_opened: list[int] = field(default_factory=list)
    ports_closed: list[int] = field(default_factory=list)
    configs_changed: list[str] = field(default_factory=list)
    configs_added: list[str] = field(default_factory=list)
    configs_removed: list[str] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return (
            int(self.branch_changed)
            + len(self.dirty_added) + len(self.dirty_removed)
            + len(self.containers_added) + len(self.containers_removed)
            + len(self.containers_status_changed)
            + len(self.ports_opened) + len(self.ports_closed)
            + len(self.configs_changed) + len(self.configs_added) + len(self.configs_removed)
        )
```

- [ ] **Step 2: Add snapshots table to history.py**

In `HistoryDB.init()`, after the `daily_stats` CREATE TABLE, add:

```python
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                label TEXT NOT NULL,
                project_dir TEXT NOT NULL,
                git_branch TEXT DEFAULT '',
                git_last_commit TEXT DEFAULT '',
                git_tracked_count INTEGER DEFAULT 0,
                git_dirty_files TEXT DEFAULT '[]',
                containers TEXT DEFAULT '[]',
                listening_ports TEXT DEFAULT '[]',
                config_checksums TEXT DEFAULT '{}'
            )
        """)
```

- [ ] **Step 3: Write test**

```python
# tests/test_snapshot_manager.py
"""Tests for snapshot manager."""

from core.models import EnvironmentSnapshot, SnapshotDiff


def test_snapshot_creation():
    s = EnvironmentSnapshot(
        id=1,
        timestamp="2026-04-15T14:30:00",
        label="Before AI session",
        project_dir="/tmp/test",
        git_branch="main",
        git_last_commit="abc1234 feat: init",
        git_tracked_count=42,
        git_dirty_files=["app.py"],
        containers=[{"name": "web", "image": "py", "status": "running"}],
        listening_ports=[{"port": 8000, "process": "python"}],
        config_checksums={".env": "abc123"},
    )
    assert s.label == "Before AI session"
    assert len(s.containers) == 1


def test_snapshot_diff_total():
    diff = SnapshotDiff(
        branch_changed=True,
        old_branch="main",
        new_branch="feature",
        containers_added=["redis"],
        ports_opened=[6379, 5555],
        configs_changed=[".env"],
    )
    assert diff.total_changes == 5  # 1 branch + 1 container + 2 ports + 1 config
```

- [ ] **Step 4: Run test**

Run: `python -m pytest tests/test_snapshot_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/models.py core/history.py tests/test_snapshot_manager.py
git commit -m "feat: add EnvironmentSnapshot/SnapshotDiff models + snapshots table"
```

---

### Task 2: Snapshot manager (CRUD + compare)

**Files:**
- Create: `core/snapshot_manager.py`
- Modify: `tests/test_snapshot_manager.py`

- [ ] **Step 1: Create snapshot_manager.py**

```python
# core/snapshot_manager.py
"""Create, load, compare, and prune environment snapshots."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from core.history import HistoryDB
from core.models import EnvironmentSnapshot, SnapshotDiff

log = logging.getLogger(__name__)

# Config files to track checksums for
CONFIG_PATTERNS = [
    "docker-compose*.yml", "docker-compose*.yaml",
    ".env", ".env.*",
    "Dockerfile*",
    "requirements*.txt",
    "package.json", "pyproject.toml",
    "Makefile", "tsconfig*.json",
]


def _file_sha256(path: Path) -> str:
    """Compute SHA256 of a file."""
    h = hashlib.sha256()
    try:
        h.update(path.read_bytes())
    except OSError:
        return ""
    return h.hexdigest()


def _collect_config_checksums(project_dir: str) -> dict[str, str]:
    """Collect SHA256 checksums for config files."""
    root = Path(project_dir)
    checksums: dict[str, str] = {}
    seen: set[str] = set()
    for pattern in CONFIG_PATTERNS:
        for match_path in root.glob(pattern):
            rel = str(match_path.relative_to(root))
            if rel not in seen:
                seen.add(rel)
                digest = _file_sha256(match_path)
                if digest:
                    checksums[rel] = digest
    return checksums


def _collect_git_state(project_dir: str) -> tuple[str, str, int, list[str]]:
    """Collect git branch, last commit, tracked count, dirty files."""
    git = shutil.which("git")
    if not git:
        return "", "", 0, []

    def run_git(*args: str) -> str | None:
        try:
            result = subprocess.run(
                [git, *args],
                cwd=project_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, OSError):
            return None

    branch = run_git("rev-parse", "--abbrev-ref", "HEAD") or ""
    last_commit = run_git("log", "--oneline", "-1") or ""

    tracked_output = run_git("ls-files")
    tracked_count = len(tracked_output.splitlines()) if tracked_output else 0

    dirty_output = run_git("status", "--porcelain")
    dirty_files = []
    if dirty_output:
        for line in dirty_output.splitlines():
            if line.strip():
                # Format: "XY filename"
                dirty_files.append(line[3:].strip())

    return branch, last_commit, tracked_count, dirty_files


def create_snapshot(
    project_dir: str,
    label: str,
    db: HistoryDB,
    docker_data: list[dict] | None = None,
    port_data: list[dict] | None = None,
) -> EnvironmentSnapshot:
    """Create and save a new snapshot."""
    branch, last_commit, tracked_count, dirty_files = _collect_git_state(project_dir)
    checksums = _collect_config_checksums(project_dir)

    snapshot = EnvironmentSnapshot(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        label=label,
        project_dir=project_dir,
        git_branch=branch,
        git_last_commit=last_commit,
        git_tracked_count=tracked_count,
        git_dirty_files=dirty_files,
        containers=docker_data or [],
        listening_ports=port_data or [],
        config_checksums=checksums,
    )

    db._ensure_conn()
    cursor = db._conn.execute(
        """
        INSERT INTO snapshots
        (timestamp, label, project_dir, git_branch, git_last_commit,
         git_tracked_count, git_dirty_files, containers, listening_ports, config_checksums)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot.timestamp,
            snapshot.label,
            snapshot.project_dir,
            snapshot.git_branch,
            snapshot.git_last_commit,
            snapshot.git_tracked_count,
            json.dumps(snapshot.git_dirty_files),
            json.dumps(snapshot.containers),
            json.dumps(snapshot.listening_ports),
            json.dumps(snapshot.config_checksums),
        ),
    )
    db._conn.commit()
    snapshot.id = cursor.lastrowid

    # Auto-prune
    prune_old(db, project_dir)

    return snapshot


def load_snapshots(db: HistoryDB, project_dir: str, limit: int = 50) -> list[EnvironmentSnapshot]:
    """Load snapshots for a project directory, newest first."""
    db._ensure_conn()
    cursor = db._conn.execute(
        """
        SELECT id, timestamp, label, project_dir, git_branch, git_last_commit,
               git_tracked_count, git_dirty_files, containers, listening_ports, config_checksums
        FROM snapshots
        WHERE project_dir = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (project_dir, limit),
    )
    snapshots = []
    for row in cursor.fetchall():
        snapshots.append(EnvironmentSnapshot(
            id=row[0],
            timestamp=row[1],
            label=row[2],
            project_dir=row[3],
            git_branch=row[4],
            git_last_commit=row[5],
            git_tracked_count=row[6],
            git_dirty_files=json.loads(row[7]),
            containers=json.loads(row[8]),
            listening_ports=json.loads(row[9]),
            config_checksums=json.loads(row[10]),
        ))
    return snapshots


def delete_snapshot(db: HistoryDB, snapshot_id: int) -> None:
    """Delete a snapshot by ID."""
    db._ensure_conn()
    db._conn.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
    db._conn.commit()


def prune_old(db: HistoryDB, project_dir: str, max_count: int = 50) -> None:
    """Keep only max_count newest snapshots per project."""
    db._ensure_conn()
    db._conn.execute(
        """
        DELETE FROM snapshots
        WHERE project_dir = ? AND id NOT IN (
            SELECT id FROM snapshots
            WHERE project_dir = ?
            ORDER BY id DESC
            LIMIT ?
        )
        """,
        (project_dir, project_dir, max_count),
    )
    db._conn.commit()


def compare_snapshots(old: EnvironmentSnapshot, new: EnvironmentSnapshot) -> SnapshotDiff:
    """Compare two snapshots, return diff."""
    diff = SnapshotDiff()

    # Git branch
    if old.git_branch != new.git_branch:
        diff.branch_changed = True
        diff.old_branch = old.git_branch
        diff.new_branch = new.git_branch

    # Dirty files
    old_dirty = set(old.git_dirty_files)
    new_dirty = set(new.git_dirty_files)
    diff.dirty_added = sorted(new_dirty - old_dirty)
    diff.dirty_removed = sorted(old_dirty - new_dirty)

    # Docker containers
    old_containers = {c.get("name", ""): c for c in old.containers}
    new_containers = {c.get("name", ""): c for c in new.containers}
    diff.containers_added = sorted(set(new_containers) - set(old_containers))
    diff.containers_removed = sorted(set(old_containers) - set(new_containers))
    for name in set(old_containers) & set(new_containers):
        old_status = old_containers[name].get("status", "")
        new_status = new_containers[name].get("status", "")
        if old_status != new_status:
            diff.containers_status_changed.append((name, old_status, new_status))

    # Ports
    old_ports = {p.get("port", 0) for p in old.listening_ports}
    new_ports = {p.get("port", 0) for p in new.listening_ports}
    diff.ports_opened = sorted(new_ports - old_ports)
    diff.ports_closed = sorted(old_ports - new_ports)

    # Config checksums
    old_cfgs = old.config_checksums
    new_cfgs = new.config_checksums
    diff.configs_added = sorted(set(new_cfgs) - set(old_cfgs))
    diff.configs_removed = sorted(set(old_cfgs) - set(new_cfgs))
    diff.configs_changed = sorted(
        k for k in set(old_cfgs) & set(new_cfgs) if old_cfgs[k] != new_cfgs[k]
    )

    return diff
```

- [ ] **Step 2: Add CRUD + compare tests**

Append to `tests/test_snapshot_manager.py`:

```python
from core.history import HistoryDB
from core.snapshot_manager import (
    create_snapshot, load_snapshots, delete_snapshot,
    compare_snapshots, prune_old, _collect_config_checksums,
)


def test_create_and_load(tmp_path):
    db = HistoryDB(":memory:")
    db.init()

    s = create_snapshot(
        project_dir=str(tmp_path),
        label="test snapshot",
        db=db,
        docker_data=[{"name": "web", "status": "running"}],
        port_data=[{"port": 8000, "process": "python"}],
    )
    assert s.id > 0
    assert s.label == "test snapshot"

    loaded = load_snapshots(db, str(tmp_path))
    assert len(loaded) == 1
    assert loaded[0].id == s.id
    assert loaded[0].containers == [{"name": "web", "status": "running"}]
    db.close()


def test_delete_snapshot():
    db = HistoryDB(":memory:")
    db.init()

    s = create_snapshot("/tmp/test", "to delete", db)
    assert len(load_snapshots(db, "/tmp/test")) == 1

    delete_snapshot(db, s.id)
    assert len(load_snapshots(db, "/tmp/test")) == 0
    db.close()


def test_prune_old():
    db = HistoryDB(":memory:")
    db.init()

    for i in range(10):
        create_snapshot("/tmp/test", f"snap {i}", db)

    prune_old(db, "/tmp/test", max_count=3)
    remaining = load_snapshots(db, "/tmp/test")
    assert len(remaining) == 3
    # Newest should survive
    assert remaining[0].label == "snap 9"
    db.close()


def test_compare_snapshots():
    old = EnvironmentSnapshot(
        git_branch="main",
        git_dirty_files=["app.py"],
        containers=[{"name": "web", "status": "running"}],
        listening_ports=[{"port": 8000}],
        config_checksums={".env": "aaa", "Makefile": "bbb"},
    )
    new = EnvironmentSnapshot(
        git_branch="feature",
        git_dirty_files=["app.py", "utils.py"],
        containers=[
            {"name": "web", "status": "running"},
            {"name": "redis", "status": "running"},
        ],
        listening_ports=[{"port": 8000}, {"port": 6379}],
        config_checksums={".env": "ccc", "docker-compose.yml": "ddd"},
    )
    diff = compare_snapshots(old, new)
    assert diff.branch_changed is True
    assert diff.old_branch == "main"
    assert diff.new_branch == "feature"
    assert diff.dirty_added == ["utils.py"]
    assert diff.containers_added == ["redis"]
    assert diff.ports_opened == [6379]
    assert diff.configs_changed == [".env"]
    assert diff.configs_added == ["docker-compose.yml"]
    assert diff.configs_removed == ["Makefile"]
    assert diff.total_changes == 7


def test_config_checksums(tmp_path):
    (tmp_path / ".env").write_text("KEY=val\n")
    (tmp_path / "requirements.txt").write_text("flask\n")
    checksums = _collect_config_checksums(str(tmp_path))
    assert ".env" in checksums
    assert "requirements.txt" in checksums
    assert len(checksums[".env"]) == 64  # sha256 hex
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_snapshot_manager.py -v`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add core/snapshot_manager.py tests/test_snapshot_manager.py
git commit -m "feat: add snapshot_manager — CRUD, compare, prune, config checksums"
```

---

### Task 3: Config defaults + i18n

**Files:**
- Modify: `core/config.py`
- Modify: `i18n/en.py`
- Modify: `i18n/ua.py`

- [ ] **Step 1: Add snapshot config defaults**

In `core/config.py`, in the `DEFAULTS` dict, after `"plugins"` section, add:

```python
    "snapshots": {
        "enabled": True,
        "auto_interval_minutes": 30,
        "max_snapshots": 50,
    },
```

- [ ] **Step 2: Add English i18n strings**

Add to `i18n/en.py` before closing `}`:

```python
    # Snapshots
    "side_snapshots": "Snapshots",
    "snap_header": "Snapshots",
    "snap_no_dir": "No project directory selected",
    "snap_select_dir": "Select project directory",
    "snap_btn_select": "Select Directory...",
    "snap_btn_take": "Take Snapshot",
    "snap_btn_compare": "Compare Selected",
    "snap_btn_delete": "Delete",
    "snap_label_prompt": "Snapshot label (optional):",
    "snap_no_snapshots": "No snapshots yet. Click 'Take Snapshot' to save current state.",
    "snap_compare_title": "Compare #{} → #{}",
    "snap_git_section": "Git",
    "snap_docker_section": "Docker",
    "snap_ports_section": "Ports",
    "snap_configs_section": "Configs",
    "snap_branch_changed": "Branch: {} → {}",
    "snap_no_changes": "No changes between these snapshots",
    "snap_total_changes": "Total: {} changes",
    "snap_auto_label": "Auto",
    "snap_start_label": "App start",

    # Hasselhoff — Snapshots
    "hoff_snap_header": "Hoff's Polaroid",
    "hoff_snap_no_changes": "Same beach, same Hoff. Nothing changed.",
```

- [ ] **Step 3: Add Ukrainian i18n strings**

Add to `i18n/ua.py` before closing `}`:

```python
    # Snapshots
    "side_snapshots": "Знімки",
    "snap_header": "Знімки середовища",
    "snap_no_dir": "Директорію проєкту не обрано",
    "snap_select_dir": "Оберіть директорію проєкту",
    "snap_btn_select": "Обрати директорію...",
    "snap_btn_take": "Зробити знімок",
    "snap_btn_compare": "Порівняти обрані",
    "snap_btn_delete": "Видалити",
    "snap_label_prompt": "Мітка знімка (необов'язково):",
    "snap_no_snapshots": "Знімків ще немає. Натисніть 'Зробити знімок' для збереження стану.",
    "snap_compare_title": "Порівняння #{} → #{}",
    "snap_git_section": "Git",
    "snap_docker_section": "Docker",
    "snap_ports_section": "Порти",
    "snap_configs_section": "Конфігурація",
    "snap_branch_changed": "Гілка: {} → {}",
    "snap_no_changes": "Між цими знімками нічого не змінилось",
    "snap_total_changes": "Всього: {} змін",
    "snap_auto_label": "Авто",
    "snap_start_label": "Старт додатку",

    # Hasselhoff — Snapshots
    "hoff_snap_header": "Полароїд Хоффа",
    "hoff_snap_no_changes": "Той самий пляж, той самий Хофф. Нічого не змінилось.",
```

- [ ] **Step 4: Commit**

```bash
git add core/config.py i18n/en.py i18n/ua.py
git commit -m "feat: add snapshot config defaults + i18n strings (EN + UA)"
```

---

### Task 4: GUI Snapshots page

**Files:**
- Create: `gui/pages/snapshots.py`

- [ ] **Step 1: Create snapshots.py**

```python
# gui/pages/snapshots.py
"""Snapshots page — save and compare environment state."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QScrollArea, QFileDialog, QCheckBox,
    QInputDialog, QFrame, QMessageBox,
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont

from i18n import get_string as _t
from core.models import EnvironmentSnapshot, SnapshotDiff
from core.history import HistoryDB
from core.snapshot_manager import (
    create_snapshot, load_snapshots, delete_snapshot, compare_snapshots,
)


class SnapshotsPage(QWidget):
    """Snapshots — save and compare environment state."""

    snapshot_taken = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._project_dir: str | None = None
        self._db: HistoryDB | None = None
        self._snapshots: list[EnvironmentSnapshot] = []
        self._checkboxes: list[tuple[QCheckBox, int]] = []  # (checkbox, snapshot_id)
        self._build_ui()

    def _get_db(self) -> HistoryDB:
        if self._db is None:
            self._db = HistoryDB()
            self._db.init()
        return self._db

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header
        header = QHBoxLayout()
        title = QLabel(_t("snap_header"))
        title.setFont(QFont("MS Sans Serif", 14, QFont.Bold))
        title.setStyleSheet("color: #000080;")
        header.addWidget(title)
        header.addStretch()

        self._dir_label = QLabel(_t("snap_no_dir"))
        self._dir_label.setStyleSheet("color: #808080;")
        header.addWidget(self._dir_label)

        self._btn_select = QPushButton(_t("snap_btn_select"))
        self._btn_select.clicked.connect(self._on_select_dir)
        header.addWidget(self._btn_select)

        layout.addLayout(header)

        # Action buttons
        actions = QHBoxLayout()
        self._btn_take = QPushButton(_t("snap_btn_take"))
        self._btn_take.clicked.connect(self._on_take_snapshot)
        self._btn_take.setEnabled(False)
        self._btn_take.setStyleSheet(
            "QPushButton { background: #000080; color: white; padding: 6px 16px; "
            "border: 2px outset #4040c0; font-weight: bold; }"
            "QPushButton:pressed { border: 2px inset #000080; }"
            "QPushButton:disabled { background: #808080; color: #c0c0c0; }"
        )
        actions.addWidget(self._btn_take)

        self._btn_compare = QPushButton(_t("snap_btn_compare"))
        self._btn_compare.clicked.connect(self._on_compare)
        self._btn_compare.setEnabled(False)
        actions.addWidget(self._btn_compare)
        actions.addStretch()
        layout.addLayout(actions)

        # Scroll area for snapshot list + compare result
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 2px inset #808080; background: white; }")

        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._content_widget)

        layout.addWidget(scroll)

        self._show_placeholder(_t("snap_select_dir"))

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
        self._checkboxes.clear()

    def _on_select_dir(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(
            self, _t("snap_btn_select"), str(Path.home()),
        )
        if dir_path:
            self._project_dir = dir_path
            display = dir_path if len(dir_path) <= 50 else "..." + dir_path[-47:]
            self._dir_label.setText(display)
            self._dir_label.setStyleSheet("color: #000000;")
            self._btn_take.setEnabled(True)
            self._refresh_list()

    def set_project_dir(self, path: str) -> None:
        """Set project dir programmatically (from app.py)."""
        self._project_dir = path
        display = path if len(path) <= 50 else "..." + path[-47:]
        self._dir_label.setText(display)
        self._dir_label.setStyleSheet("color: #000000;")
        self._btn_take.setEnabled(True)
        self._refresh_list()

    def _on_take_snapshot(self) -> None:
        if not self._project_dir:
            return
        label, ok = QInputDialog.getText(
            self, _t("snap_btn_take"), _t("snap_label_prompt"),
        )
        if not ok:
            return
        if not label.strip():
            label = _t("snap_btn_take")

        create_snapshot(
            project_dir=self._project_dir,
            label=label.strip(),
            db=self._get_db(),
        )
        self.snapshot_taken.emit()
        self._refresh_list()

    def take_auto_snapshot(
        self,
        label: str,
        docker_data: list[dict] | None = None,
        port_data: list[dict] | None = None,
    ) -> None:
        """Take snapshot programmatically (auto-snapshot from app.py)."""
        if not self._project_dir:
            return
        create_snapshot(
            project_dir=self._project_dir,
            label=label,
            db=self._get_db(),
            docker_data=docker_data,
            port_data=port_data,
        )
        self._refresh_list()

    def _refresh_list(self) -> None:
        if not self._project_dir:
            return
        self._snapshots = load_snapshots(self._get_db(), self._project_dir)
        self._render_list()

    def _render_list(self) -> None:
        self._clear_content()

        if not self._snapshots:
            self._show_placeholder(_t("snap_no_snapshots"))
            return

        for snap in self._snapshots:
            row = self._make_snapshot_row(snap)
            self._content_layout.addWidget(row)

        self._content_layout.addStretch()

    def _make_snapshot_row(self, snap: EnvironmentSnapshot) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; background: white; }"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 4)

        cb = QCheckBox()
        cb.stateChanged.connect(self._on_checkbox_changed)
        layout.addWidget(cb)
        self._checkboxes.append((cb, snap.id))

        id_lbl = QLabel(f"#{snap.id}")
        id_lbl.setStyleSheet("color: #000080; font-weight: bold; font-family: monospace;")
        id_lbl.setFixedWidth(40)
        layout.addWidget(id_lbl)

        time_lbl = QLabel(snap.timestamp[:16].replace("T", " "))
        time_lbl.setStyleSheet("color: #333; font-family: monospace;")
        time_lbl.setFixedWidth(130)
        layout.addWidget(time_lbl)

        label_lbl = QLabel(f'"{snap.label}"')
        label_lbl.setStyleSheet("color: #333; font-style: italic;")
        layout.addWidget(label_lbl)

        layout.addStretch()

        # Brief info
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

        del_btn = QPushButton(_t("snap_btn_delete"))
        del_btn.setFixedWidth(60)
        del_btn.setStyleSheet("QPushButton { font-size: 10px; padding: 2px; }")
        del_btn.clicked.connect(lambda _, sid=snap.id: self._on_delete(sid))
        layout.addWidget(del_btn)

        return frame

    def _on_checkbox_changed(self) -> None:
        selected = [sid for cb, sid in self._checkboxes if cb.isChecked()]
        self._btn_compare.setEnabled(len(selected) == 2)

    def _on_compare(self) -> None:
        selected = [sid for cb, sid in self._checkboxes if cb.isChecked()]
        if len(selected) != 2:
            return

        snap_map = {s.id: s for s in self._snapshots}
        old_id, new_id = sorted(selected)
        old_snap = snap_map.get(old_id)
        new_snap = snap_map.get(new_id)
        if not old_snap or not new_snap:
            return

        diff = compare_snapshots(old_snap, new_snap)
        self._render_compare(old_id, new_id, diff)

    def _render_compare(self, old_id: int, new_id: int, diff: SnapshotDiff) -> None:
        # Remove old compare results (anything after the snapshot list)
        # Find and remove compare group if it exists
        for i in range(self._content_layout.count() - 1, -1, -1):
            item = self._content_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if hasattr(widget, "_is_compare_result"):
                    widget.deleteLater()
                    self._content_layout.removeItem(item)

        if diff.total_changes == 0:
            group = QGroupBox(_t("snap_compare_title").format(old_id, new_id))
            group._is_compare_result = True
            group.setStyleSheet(
                "QGroupBox { border: 2px groove #808080; margin-top: 12px; "
                "padding-top: 16px; font-weight: bold; background: white; }"
                "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
            )
            gl = QVBoxLayout(group)
            gl.addWidget(QLabel(f"  {_t('snap_no_changes')}"))
            self._content_layout.insertWidget(self._content_layout.count() - 1, group)
            return

        group = QGroupBox(_t("snap_compare_title").format(old_id, new_id))
        group._is_compare_result = True
        group.setStyleSheet(
            "QGroupBox { border: 2px groove #808080; margin-top: 12px; "
            "padding-top: 16px; font-weight: bold; background: white; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
        )
        gl = QVBoxLayout(group)

        # Git
        if diff.branch_changed or diff.dirty_added or diff.dirty_removed:
            gl.addWidget(self._section_label(
                f"\U0001f4c1 {_t('snap_git_section')}"
            ))
            if diff.branch_changed:
                gl.addWidget(self._detail_label(
                    _t("snap_branch_changed").format(diff.old_branch, diff.new_branch)
                ))
            for f in diff.dirty_added:
                gl.addWidget(self._detail_label(f"  + {f} (new dirty)"))
            for f in diff.dirty_removed:
                gl.addWidget(self._detail_label(f"  - {f} (cleaned)"))

        # Docker
        if diff.containers_added or diff.containers_removed or diff.containers_status_changed:
            gl.addWidget(self._section_label(
                f"\U0001f433 {_t('snap_docker_section')}"
            ))
            for c in diff.containers_added:
                gl.addWidget(self._detail_label(f"  + {c} (new container)", "#006600"))
            for c in diff.containers_removed:
                gl.addWidget(self._detail_label(f"  - {c} (removed)", "#cc0000"))
            for name, old_s, new_s in diff.containers_status_changed:
                gl.addWidget(self._detail_label(f"  ~ {name}: {old_s} \u2192 {new_s}", "#cc6600"))

        # Ports
        if diff.ports_opened or diff.ports_closed:
            gl.addWidget(self._section_label(
                f"\U0001f50c {_t('snap_ports_section')}"
            ))
            for p in diff.ports_opened:
                gl.addWidget(self._detail_label(f"  + :{p} (opened)", "#006600"))
            for p in diff.ports_closed:
                gl.addWidget(self._detail_label(f"  - :{p} (closed)", "#cc0000"))

        # Configs
        if diff.configs_changed or diff.configs_added or diff.configs_removed:
            gl.addWidget(self._section_label(
                f"\u2699\ufe0f {_t('snap_configs_section')}"
            ))
            for c in diff.configs_changed:
                gl.addWidget(self._detail_label(f"  ~ {c} CHANGED", "#cc6600"))
            for c in diff.configs_added:
                gl.addWidget(self._detail_label(f"  + {c} (new)", "#006600"))
            for c in diff.configs_removed:
                gl.addWidget(self._detail_label(f"  - {c} (removed)", "#cc0000"))

        # Summary
        summary = QLabel(f"  {_t('snap_total_changes').format(diff.total_changes)}")
        summary.setStyleSheet("font-weight: bold; padding-top: 8px;")
        gl.addWidget(summary)

        # Insert before the stretch
        self._content_layout.insertWidget(self._content_layout.count() - 1, group)

    def _on_delete(self, snapshot_id: int) -> None:
        reply = QMessageBox.question(
            self, _t("snap_btn_delete"),
            f"Delete snapshot #{snapshot_id}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            delete_snapshot(self._get_db(), snapshot_id)
            self._refresh_list()

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; color: #000080; padding-top: 4px;")
        return lbl

    @staticmethod
    def _detail_label(text: str, color: str = "#333") -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {color}; font-family: monospace; padding-left: 8px;")
        return lbl
```

- [ ] **Step 2: Commit**

```bash
git add gui/pages/snapshots.py
git commit -m "feat: add Snapshots GUI page with list, compare, delete"
```

---

### Task 5: Wire into app.py (sidebar + auto-snapshot + timer)

**Files:**
- Modify: `gui/app.py`

- [ ] **Step 1: Add import**

After `from gui.pages.health_page import HealthPage`:
```python
from gui.pages.snapshots import SnapshotsPage
```

- [ ] **Step 2: Add sidebar item**

After `SidebarItem(_t("side_activity"), "activity"),`:
```python
SidebarItem(_t("side_snapshots"), "snapshots"),
```

- [ ] **Step 3: Create page and register**

After `self.page_activity = ActivityPage()`:
```python
self.page_snapshots = SnapshotsPage()
```

In `for key, page in [...]`, after `("activity", self.page_activity),`:
```python
("snapshots", self.page_snapshots),
```

- [ ] **Step 4: Add auto-snapshot timer**

After the security timer setup block, add:

```python
        # Snapshot auto timer
        snap_config = config.get("snapshots", {})
        if snap_config.get("enabled", True):
            snap_interval = snap_config.get("auto_interval_minutes", 30) * 60 * 1000
            self._snapshot_timer = QTimer(self)
            self._snapshot_timer.timeout.connect(self._auto_snapshot)
            self._snapshot_timer.start(snap_interval)
```

- [ ] **Step 5: Add auto-snapshot method and startup snapshot**

After the `_do_hoff` method, add:

```python
    def _auto_snapshot(self):
        """Take auto-snapshot if snapshots page has a project dir."""
        from i18n import get_string as _t
        from datetime import datetime
        time_str = datetime.now().strftime("%H:%M")
        self.page_snapshots.take_auto_snapshot(
            label=f"{_t('snap_auto_label')} ({time_str})",
        )
```

In `_on_data_ready`, after the Activity Log block, add:

```python
        # Auto-snapshot on first data collection (app start)
        if not hasattr(self, "_start_snapshot_taken"):
            self._start_snapshot_taken = True
            self.page_snapshots.take_auto_snapshot(
                label=_t("snap_start_label"),
                docker_data=infos,
                port_data=ports,
            )
```

- [ ] **Step 6: Verify import**

Run: `python -c "from gui.app import MonitorApp; print('OK')"`

- [ ] **Step 7: Commit**

```bash
git add gui/app.py
git commit -m "feat: wire Snapshots page into sidebar + auto-snapshot timer"
```

---

### Task 6: Full integration test

- [ ] **Step 1: Run all tests**

Run:
```bash
python -m pytest tests/test_snapshot_manager.py tests/test_health_dead_code.py tests/test_health_models.py tests/test_health_project_map.py tests/test_activity_tracker.py tests/test_file_explainer.py tests/test_activity_models.py tests/test_history.py tests/test_config.py tests/test_platform.py -v
```
Expected: all pass (90+ tests)

- [ ] **Step 2: Commit plan**

```bash
git add docs/2026-04-15-snapshots-plan.md
git commit -m "docs: add Snapshots implementation plan"
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Models + SQLite schema | `core/models.py`, `core/history.py`, test |
| 2 | Snapshot manager (CRUD + compare) | `core/snapshot_manager.py`, test |
| 3 | Config defaults + i18n | `core/config.py`, `i18n/en.py`, `i18n/ua.py` |
| 4 | GUI page | `gui/pages/snapshots.py` |
| 5 | Wire into app + auto-snapshot + timer | `gui/app.py` |
| 6 | Integration test | all |
