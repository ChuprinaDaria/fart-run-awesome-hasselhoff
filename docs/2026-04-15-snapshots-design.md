# Activity Log Phase 2: Environment Snapshots — Design

> "Your AI has amnesia. You don't."

## Goal

Кнопка "Take Snapshot" зберігає поточний стан середовища (git, docker, ports, configs) в SQLite. Порівняння двох snapshots показує що змінилось. Auto-snapshot при старті + configurable timer.

## What's Stored

```python
@dataclass
class EnvironmentSnapshot:
    id: int                        # auto-increment
    timestamp: str                 # ISO datetime
    label: str                     # "App start", "Before AI session", user text
    project_dir: str               # which directory this snapshot is for

    # Git state
    git_branch: str
    git_last_commit: str           # hash + message
    git_tracked_files_count: int
    git_dirty_files: list[str]     # uncommitted changes

    # Docker state
    containers: list[dict]         # [{name, image, status, ports}]

    # Ports
    listening_ports: list[dict]    # [{port, pid, process}]

    # Config checksums
    config_checksums: dict[str, str]  # {path: sha256}
```

Config files tracked: `docker-compose*.yml`, `.env`, `.env.*`, `Dockerfile*`, `requirements*.txt`, `package.json`, `pyproject.toml`, `Makefile`, `tsconfig*.json`.

## SQLite Schema

New table in existing `history.db` (via HistoryDB pattern):

```sql
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    label TEXT NOT NULL,
    project_dir TEXT NOT NULL,
    git_branch TEXT DEFAULT '',
    git_last_commit TEXT DEFAULT '',
    git_tracked_count INTEGER DEFAULT 0,
    git_dirty_files TEXT DEFAULT '[]',       -- JSON array
    containers TEXT DEFAULT '[]',            -- JSON array of dicts
    listening_ports TEXT DEFAULT '[]',       -- JSON array of dicts
    config_checksums TEXT DEFAULT '{}'       -- JSON dict
)
```

## Core Module: `snapshot_manager.py`

```
create_snapshot(project_dir, label, docker_data, port_data) → EnvironmentSnapshot
load_snapshots(project_dir, limit=50) → list[EnvironmentSnapshot]
compare_snapshots(old, new) → SnapshotDiff
delete_snapshot(id)
prune_old(project_dir, max_count=50)
```

**SnapshotDiff:**
```python
@dataclass
class SnapshotDiff:
    # Git
    branch_changed: bool
    old_branch: str
    new_branch: str
    new_commits: int              # diff in commit count
    files_added: list[str]        # dirty files that appeared
    files_removed: list[str]      # dirty files that disappeared

    # Docker
    containers_added: list[str]
    containers_removed: list[str]
    containers_status_changed: list[tuple[str, str, str]]  # (name, old_status, new_status)

    # Ports
    ports_opened: list[int]
    ports_closed: list[int]

    # Configs
    configs_changed: list[str]    # paths where checksum differs
    configs_added: list[str]
    configs_removed: list[str]

    # Summary
    total_changes: int
```

## Auto-Snapshot

- **At app start:** `create_snapshot(dir, "App start", ...)` called from `app.py` after first data collection
- **Timer:** QTimer, interval from config `[snapshots] auto_interval_minutes = 30`. Label: "Auto ({time})"
- **Max snapshots:** 50 per project_dir. `prune_old()` called after each create.
- **Config:** `config.toml` gets new section:
  ```toml
  [snapshots]
  auto_interval_minutes = 30
  max_snapshots = 50
  enabled = true
  ```

## GUI Page

Separate page "Snapshots" in sidebar, after Activity Log.

```
┌──────────────────────────────────────────────┐
│ 📸 Snapshots                                  │
├──────────────────────────────────────────────┤
│ Project: /home/user/app    [Select Dir...]   │
│                                               │
│ [📸 Take Snapshot]  [🔍 Compare Selected]     │
│                                               │
│ ☐ #5  14:30  "After adding Redis"     [🗑]   │
│ ☐ #4  11:00  "Before AI session"      [🗑]   │
│ ☐ #3  09:15  "Auto (09:15)"           [🗑]   │
│ ☐ #2  Yesterday  "App start"          [🗑]   │
│ ☐ #1  Yesterday  "Working baseline"   [🗑]   │
│                                               │
│ ─── Compare #4 → #5 ─────────────────────── │
│                                               │
│ 📁 Git: branch same, +2 dirty files          │
│ 🐳 Docker: +1 container (redis)              │
│ 🔌 Ports: +2 (6379, 5555)                    │
│ ⚙️ Configs: docker-compose.yml CHANGED        │
│                                               │
│ Total: 6 changes                              │
└──────────────────────────────────────────────┘
```

- Select 2 checkboxes → "Compare Selected" becomes active
- Label editable via double-click (or input dialog on create)
- Delete button per snapshot
- Compare result shown below the list

## Alerts

Via existing AlertManager:
- Config file changed between snapshots → warning alert
- Container disappeared → warning alert
- Branch changed → info alert

Alerts fire only on auto-snapshots (not manual — user already knows).

## Integration

- `gui/app.py`: register page + start auto-snapshot timer
- `core/config.py`: add `[snapshots]` section defaults
- Activity Log page: optional "Take Snapshot" button shortcut
- Sidebar: counter showing snapshot count

## i18n

~15 new strings EN + UA: page title, buttons, comparison labels, alert messages, Hasselhoff variants.

## Scope Exclusions

- No snapshot export/import
- No visual diff viewer (text summary only)
- No git stash/restore from snapshot
- No snapshot sharing between machines

## Cross-Platform

- Git: subprocess (same as activity_tracker)
- Docker: docker SDK (existing)
- Ports: psutil (existing)
- Config checksums: hashlib.sha256 (stdlib)
- SQLite: sqlite3 (stdlib)
- All pathlib-based
