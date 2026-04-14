# claude-monitor GUI Refactor & Unification

**Date:** 2026-04-14
**Approach:** GUI rewrite, keep core/plugins intact, remove TUI

## Summary

Rewrite the GUI layer from scratch with Win95 Explorer-style sidebar layout. Unify V1 (Claude token tracking) and V2 (dev environment monitoring) into a single SQLite-backed GUI app. Remove Textual TUI, PostgreSQL dependency, and legacy V1 scripts.

## Architecture

### What stays (no changes)
- `core/plugin.py` — plugin base class
- `core/sqlite_db.py` — async SQLite wrapper
- `plugins/` — all 3 plugins (docker_monitor, port_map, security_scan) and their collectors

### What changes
- `core/config.py` — fix relative path, add `[paths]` and `[sounds]` sections
- `core/alerts.py` — local `sounds/` directory, warn if empty instead of silent fail

### What's new
- `core/autodiscovery.py` — finds Claude logs, Docker socket, projects automatically
- `gui/app.py` — main window with Explorer sidebar
- `gui/sidebar.py` — Win95 sidebar widget with counters
- `gui/pages/overview.py` — budget, tokens, nag messages
- `gui/pages/docker.py` — container list + Fart Off/Start/Restart/Logs/Remove actions
- `gui/pages/ports.py` — listening ports, conflicts, project mapping
- `gui/pages/security.py` — findings table + detail panel with human explanations
- `gui/pages/usage.py` — token usage (from claude_nagger)
- `gui/pages/analytics.py` — model comparison, project breakdown

### What's deleted
- `core/app.py` — Textual TUI
- `gui/docker_tab.py`, `gui/ports_tab.py`, `gui/security_tab.py` — old tab widgets
- `db.py` — PostgreSQL connector
- `hook.py` — post-session hook
- `importer.py` — PostgreSQL backfill
- `dashboard.py` — Matrix TUI
- `claude-wrapper.sh` — bash wrapper
- `sounds` symlink — replaced by real directory

## File Structure

```
claude-monitor/
├── sounds/
│   ├── farts/              ← alert sounds (mp3)
│   └── hasselhoff/         ← victory sounds + images
├── core/
│   ├── config.py           ← TOML config, absolute path resolution
│   ├── alerts.py           ← sounds from local sounds/, log.warning if empty
│   ├── autodiscovery.py    ← NEW: SystemState dataclass, auto-find everything
│   ├── plugin.py           ← unchanged
│   └── sqlite_db.py        ← unchanged
├── plugins/                ← unchanged
├── gui/
│   ├── app.py              ← NEW: MonitorApp main window + tray
│   ├── sidebar.py          ← NEW: Win95 sidebar with counters
│   ├── pages/
│   │   ├── overview.py     ← budget, tokens, nag, hasselhoff
│   │   ├── docker.py       ← containers + actions (fart off, start, restart, logs, remove)
│   │   ├── ports.py        ← ports, conflicts
│   │   ├── security.py     ← findings + detail panel
│   │   ├── usage.py        ← token usage
│   │   └── analytics.py    ← model comparison
│   └── monitor_alerts.py   ← refactored, no duplication with core/alerts.py
├── config.toml
└── pyproject.toml          ← remove textual, keep PyQt5
```

## Autodiscovery (`core/autodiscovery.py`)

```python
@dataclass
class ProjectInfo:
    path: Path
    name: str
    has_docker_compose: bool
    has_package_json: bool

@dataclass
class SystemState:
    claude_dir: Path | None
    docker_available: bool
    docker_error: str | None  # "not installed" / "socket not found" / "permission denied"
    projects: list[ProjectInfo]
```

### Detection logic

**Claude logs:**
- Check `~/.claude/projects/` exists and has `.jsonl` files
- If not found: show dialog offering file picker, save choice to `config.toml [paths].claude_dir`

**Docker:**
- Check `/var/run/docker.sock` exists
- Try `docker.from_env()` — catch specific exceptions:
  - `FileNotFoundError` → "Docker not installed"
  - `PermissionError` → "Add user to docker group: `sudo usermod -aG docker $USER`"
  - `DockerException` → show actual error message
- If not found: show dialog, user can skip or set socket path

**Projects:**
- Scan `~/` depth 2 for `.git/`, `docker-compose.yml`, `package.json`
- Cache results for 5 minutes
- If nothing found: show dialog for manual path

All manual overrides saved to `config.toml [paths]` section.

## GUI Layout

```
+-- fart.run & awesome Hasselhoff ----------- _ [] X -+
| File   View   Tools   Help                          |
+----------+------------------------------------------+
|          |                                          |
| Overview |   [active page content]                  |
| Docker(7)|                                          |
| Ports(12)|                                          |
| Security!|                                          |
| Usage    |                                          |
| Analytics|                                          |
| -------- |                                          |
| Settings |                                          |
|          |                                          |
+----------+------------------------------------------+
| Ready | Docker: 7 running | Alerts: 3       14:23  |
+----------------------------------------------------|
```

### Sidebar (`gui/sidebar.py`)
- Win95 Explorer style: flat list, selected = blue background (#000080) + white text
- Counters in parentheses: `Docker (7)`, `Ports (12)`
- Alert indicator: `Security (3!)` in red when critical findings exist
- Sections not available (autodiscovery failed) shown greyed out; click opens "set path" dialog
- Separator line before Settings
- Width: fixed ~140px

### Single refresh loop
- One `QTimer` with interval from `config.toml [general].refresh_interval` (default 5s)
- Each tick: collect data from all enabled plugins, process alerts
- Security scan: separate `QTimer` from `config.toml [plugins.security_scan].scan_interval` (default 3600s)
- Security scan runs in `QThread` to avoid blocking GUI (pip-audit/npm audit are slow)

## Docker Page (`gui/pages/docker.py`)

### Container table
Columns: Status icon | Name | State | CPU% | RAM | Ports | Health

### Actions
- **Context menu** (right-click on container): Start / Restart / Logs / Remove
- **"Fart Off" button** next to each running container — stops container + plays random fart sound
- **Logs popup**: QDialog with last 100 lines, monospace font, auto-scroll, close button
- All Docker actions run in QThread to avoid blocking

### Error handling
- Docker not available: show banner with specific error from autodiscovery
- Individual container action fails: show error in status bar

## Security Page (`gui/pages/security.py`)

### Table
Columns: Severity | Type | Description (human-readable) | Source

Description column shows human-readable text instead of technical jargon:
- "runs as root (no USER set)" → "Container runs as admin — if hacked, attacker gets full access"
- "docker.sock mounted" → "Docker control exposed inside container — attacker can control all containers"
- "exposed on 0.0.0.0" → "Service accessible from any network — should be localhost only"

### Detail panel (bottom, shown on row click)

Three sections:
- **What is this** — 1-2 sentences for non-technical user
- **What's the risk** — concrete attack scenario
- **How to fix** — copy-paste command or file change

Explanations are hardcoded in a dict keyed by finding type + pattern matching on description. Not AI-generated.

Example:
```python
EXPLANATIONS = {
    ("docker", "privileged"): {
        "what": "Container runs with full system privileges, same as root on host.",
        "risk": "If attacker compromises the container, they own the entire server.",
        "fix": "Remove 'privileged: true' from docker-compose.yml. Use specific capabilities instead:\n"
               "  cap_add:\n    - NET_ADMIN  # only what you need",
    },
    ...
}
```

### Scan button
- "Scan Now" button triggers immediate scan
- Scan runs in QThread
- Progress shown in button text: "Scanning..."
- pip-audit and npm-audit timeouts remain (120s/60s) but don't block GUI

## Sounds

### Directory structure
```
sounds/
├── farts/           ← mp3 files for alerts and fart off
└── hasselhoff/      ← mp3 + images for hoff mode
```

Files copied from `~/claude-nagger/sounds/` into repo. Symlink removed.

### Sound logic (`core/alerts.py`)
- Sound dir: `<project_root>/sounds/` — always, no fallback chain
- If directory empty: `log.warning("No sounds in sounds/farts/")` + desktop notification without sound
- Severity mapping:
  - critical → random mp3 from `farts/`
  - warning → random mp3 from `farts/`
  - info → desktop notification only, no sound
- "Fart Off" action → random fart
- "Hoff Mode" → `hasselhoff/victory.mp3` + random image from `hasselhoff/`
- Quiet hours from config — no sounds during night

### Player
Reuse `SoundPlayer` from `claude_nagger` with updated paths. Supports ffplay/cvlc/aplay fallback.

## Config (`config.toml`)

```toml
[general]
refresh_interval = 5
language = "en"          # en / ua

[sounds]
enabled = true
quiet_hours_start = "23:00"
quiet_hours_end = "07:00"

[alerts]
cooldown_seconds = 300
desktop_notifications = true

[paths]
# Auto-detected by default. User overrides saved here by GUI:
# claude_dir = "~/.claude"
# docker_socket = "/var/run/docker.sock"
# scan_paths = ["~/projects"]

[plugins.docker_monitor]
enabled = true
cpu_threshold = 80
ram_threshold = 85

[plugins.port_map]
enabled = true

[plugins.security_scan]
enabled = true
scan_interval = 3600
```

`load_config()` resolves path as: explicit argument > `MONITOR_CONFIG` env var > `<project_root>/config.toml`. No more relative `../config.toml`.

## psutil Without Root

- At startup: test if `psutil.net_connections()` returns full process info
- If limited: show yellow banner in Ports page: "Some processes hidden. Run with sudo or add CAP_NET_ADMIN for full info."
- Ports without PID shown as `<unknown process>` instead of silently skipped
- Not a blocker — monitor works with partial data

## V1/V2 Unification

### Kept from V1
- `parser.py` → moves to `core/parser.py`, parses `~/.claude/projects/**/*.jsonl` directly
- `analyzer.py` → optional, works if Ollama is running locally

### Removed (V1 legacy)
- `db.py` (PostgreSQL + pgvector)
- `hook.py` (post-session prompt)
- `importer.py` (PostgreSQL backfill)
- `dashboard.py` (Matrix TUI)
- `claude-wrapper.sh` (bash wrapper)
- `psycopg2-binary` dependency

### Data flow
All data flows through SQLite only. Claude token data parsed from `.jsonl` on each refresh (no import step needed).

## Dependencies

### Keep
- PyQt5 >= 5.15
- docker >= 7.0
- psutil >= 5.9
- aiosqlite >= 0.19 (for plugin migrations)
- pytest, pytest-asyncio (dev)

### Remove
- textual (TUI framework)
- psycopg2-binary (PostgreSQL)

### Optional
- pip-audit (security scanning)
- ollama (model recommendations)
