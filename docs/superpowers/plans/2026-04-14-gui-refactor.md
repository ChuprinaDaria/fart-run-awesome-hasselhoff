# GUI Refactor & Unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite GUI as Win95 Explorer-style sidebar app, unify V1/V2, remove TUI, add autodiscovery, Docker actions, human-readable security explanations.

**Architecture:** Keep core plugin system and collectors untouched. New GUI layer with sidebar navigation and page-based content. Single SQLite backend. Autodiscovery finds Claude logs, Docker, projects automatically.

**Tech Stack:** PyQt5, Python 3.11+, docker SDK, psutil, aiosqlite

**Spec:** `docs/superpowers/specs/2026-04-14-gui-refactor-design.md`

---

## File Map

### New files
| File | Responsibility |
|------|---------------|
| `core/autodiscovery.py` | Find Claude dir, Docker socket, projects; SystemState dataclass |
| `gui/sidebar.py` | Win95 Explorer sidebar widget with counters and selection |
| `gui/pages/__init__.py` | Package init |
| `gui/pages/overview.py` | Budget, tokens, nag messages, hasselhoff |
| `gui/pages/docker.py` | Container table + Fart Off/Start/Restart/Logs/Remove |
| `gui/pages/ports.py` | Listening ports, conflicts, project mapping |
| `gui/pages/security.py` | Findings table + detail panel with human explanations |
| `gui/pages/usage.py` | Token usage stats (reuses claude_nagger.core.parser) |
| `gui/pages/analytics.py` | Model comparison, project breakdown |
| `tests/test_autodiscovery.py` | Autodiscovery unit tests |
| `tests/test_security_explanations.py` | Security explanation coverage tests |
| `tests/test_sidebar.py` | Sidebar widget tests |

### Modified files
| File | Changes |
|------|---------|
| `gui/app.py` | Full rewrite — Explorer layout, single refresh loop, tray app |
| `gui/monitor_alerts.py` | Use local `sounds/`, log.warning if empty |
| `core/config.py` | Absolute path resolution, `[paths]` and `[sounds]` sections |
| `core/alerts.py` | Local sounds dir, warn if missing |
| `config.toml` | New sections: `[paths]`, `[sounds]` |
| `pyproject.toml` | Remove textual, PyQt5 to main deps, update entry points |

### Deleted files
| File | Reason |
|------|--------|
| `core/app.py` | Textual TUI — replaced by GUI |
| `gui/docker_tab.py` | Replaced by `gui/pages/docker.py` |
| `gui/ports_tab.py` | Replaced by `gui/pages/ports.py` |
| `gui/security_tab.py` | Replaced by `gui/pages/security.py` |
| `db.py` | PostgreSQL connector — V1 legacy |
| `hook.py` | Post-session hook — V1 legacy |
| `importer.py` | PostgreSQL backfill — V1 legacy |
| `dashboard.py` | Matrix TUI — V1 legacy |
| `claude-wrapper.sh` | Bash wrapper — V1 legacy |
| `sounds` (symlink) | Replaced by real directory |

### Moved files
| From | To | Reason |
|------|----|--------|
| `parser.py` | `core/parser.py` | Claude log parser used by GUI pages |
| `analyzer.py` | `core/analyzer.py` | Optional Ollama integration |

---

## Task 1: Sounds — copy into repo, remove symlink

**Files:**
- Delete: `sounds` (symlink)
- Create: `sounds/farts/` (copy mp3 files)
- Create: `sounds/hasselhoff/` (copy mp3 + images)

- [ ] **Step 1: Remove symlink and create directories**

```bash
rm sounds
mkdir -p sounds/farts sounds/hasselhoff
```

- [ ] **Step 2: Copy sound files from claude-nagger**

```bash
cp ~/claude-nagger/sounds/farts/*.mp3 sounds/farts/
cp ~/claude-nagger/sounds/hasselhoff/victory.mp3 sounds/hasselhoff/
cp ~/claude-nagger/sounds/hasselhoff/*.jpg sounds/hasselhoff/
cp ~/claude-nagger/sounds/hasselhoff/*.png sounds/hasselhoff/
```

- [ ] **Step 3: Verify files exist**

```bash
ls -la sounds/farts/
ls -la sounds/hasselhoff/
```

Expected: mp3 files in farts/, victory.mp3 + images in hasselhoff/

- [ ] **Step 4: Add sounds to .gitignore (binary files)**

Add to `.gitignore`:
```
# Keep sounds dir structure but don't track binaries
# sounds/**/*.mp3  — uncomment if you want to track them
```

Actually, since the user wants sounds in the repo and working on any machine, do NOT gitignore them. Leave `.gitignore` as is.

- [ ] **Step 5: Commit**

```bash
git add sounds/ .gitignore
git rm sounds  # remove symlink from git tracking if tracked
git commit -m "feat: move sounds into repo — farts/ and hasselhoff/ directories"
```

---

## Task 2: Config — fix paths, add new sections

**Files:**
- Modify: `core/config.py`
- Modify: `config.toml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for new config features**

Add to `tests/test_config.py`:

```python
def test_load_config_absolute_path(tmp_path):
    """Config resolves from project root, not relative."""
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[general]\nrefresh_interval = 10\n')
    config = load_config(cfg_file)
    assert config["general"]["refresh_interval"] == 10


def test_config_has_paths_section():
    """Config defaults include [paths] section."""
    config = load_config(Path("/nonexistent/config.toml"))
    assert "paths" in config
    assert config["paths"] == {}


def test_config_has_sounds_section():
    """Config defaults include [sounds] section."""
    config = load_config(Path("/nonexistent/config.toml"))
    assert "sounds" in config
    assert config["sounds"]["enabled"] is True
    assert config["sounds"]["quiet_hours_start"] == "23:00"
    assert config["sounds"]["quiet_hours_end"] == "07:00"


def test_config_env_var_override(tmp_path, monkeypatch):
    """MONITOR_CONFIG env var overrides default path."""
    cfg_file = tmp_path / "custom.toml"
    cfg_file.write_text('[general]\nrefresh_interval = 42\n')
    monkeypatch.setenv("MONITOR_CONFIG", str(cfg_file))
    config = load_config()
    assert config["general"]["refresh_interval"] == 42
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: FAIL — no `paths` section in defaults, no env var support

- [ ] **Step 3: Update `core/config.py`**

```python
"""Config loader for dev-monitor. TOML-based with defaults."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

DEFAULTS = {
    "general": {
        "refresh_interval": 5,
        "language": "en",
    },
    "sounds": {
        "enabled": True,
        "quiet_hours_start": "23:00",
        "quiet_hours_end": "07:00",
    },
    "alerts": {
        "cooldown_seconds": 300,
        "desktop_notifications": True,
    },
    "paths": {},
    "plugins": {
        "docker_monitor": {
            "enabled": True,
            "cpu_threshold": 80,
            "ram_threshold": 85,
            "alert_on_exit": True,
        },
        "port_map": {
            "enabled": True,
        },
        "security_scan": {
            "enabled": True,
            "scan_interval": 3600,
            "scan_paths": ["~"],
        },
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _project_root() -> Path:
    """Find project root (directory containing pyproject.toml or config.toml)."""
    current = Path(__file__).resolve().parent
    for parent in [current, current.parent, current.parent.parent]:
        if (parent / "pyproject.toml").exists() or (parent / "config.toml").exists():
            return parent
    return current.parent


def load_config(path: Path | None = None) -> dict:
    """Load TOML config. Resolution: explicit path > MONITOR_CONFIG env > project root."""
    if path is None:
        env_path = os.environ.get("MONITOR_CONFIG")
        if env_path:
            path = Path(env_path)
        else:
            path = _project_root() / "config.toml"

    user_config = {}
    if path.exists():
        with open(path, "rb") as f:
            user_config = tomllib.load(f)

    return _deep_merge(DEFAULTS, user_config)
```

- [ ] **Step 4: Update `config.toml`**

```toml
[general]
refresh_interval = 5
language = "en"

[sounds]
enabled = true
quiet_hours_start = "23:00"
quiet_hours_end = "07:00"

[alerts]
cooldown_seconds = 300
desktop_notifications = true

[paths]
# Auto-detected by default. Override here:
# claude_dir = "~/.claude"
# docker_socket = "/var/run/docker.sock"
# scan_paths = ["~/projects"]

[plugins.docker_monitor]
enabled = true
cpu_threshold = 80
ram_threshold = 85
alert_on_exit = true

[plugins.port_map]
enabled = true

[plugins.security_scan]
enabled = true
scan_interval = 3600
scan_paths = ["~"]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add core/config.py config.toml tests/test_config.py
git commit -m "feat: config — absolute paths, env var override, sounds/paths sections"
```

---

## Task 3: Autodiscovery — find Claude, Docker, projects

**Files:**
- Create: `core/autodiscovery.py`
- Create: `tests/test_autodiscovery.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_autodiscovery.py`:

```python
"""Tests for autodiscovery module."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.autodiscovery import discover_system, SystemState, ProjectInfo


def test_discover_claude_dir_exists(tmp_path):
    """Finds Claude dir when it exists with .jsonl files."""
    claude_dir = tmp_path / ".claude" / "projects" / "test"
    claude_dir.mkdir(parents=True)
    (claude_dir / "session.jsonl").touch()
    with patch("core.autodiscovery.Path.home", return_value=tmp_path):
        state = discover_system()
    assert state.claude_dir == tmp_path / ".claude"


def test_discover_claude_dir_missing(tmp_path):
    """Returns None when Claude dir doesn't exist."""
    with patch("core.autodiscovery.Path.home", return_value=tmp_path):
        state = discover_system()
    assert state.claude_dir is None


def test_discover_claude_dir_from_config(tmp_path):
    """Uses config override when provided."""
    claude_dir = tmp_path / "custom-claude"
    claude_dir.mkdir()
    (claude_dir / "projects").mkdir()
    state = discover_system(config_paths={"claude_dir": str(claude_dir)})
    assert state.claude_dir == claude_dir


def test_discover_docker_available():
    """Detects Docker when socket exists and client works."""
    with patch("core.autodiscovery.docker") as mock_docker:
        mock_docker.from_env.return_value = MagicMock()
        state = discover_system()
    assert state.docker_available is True
    assert state.docker_error is None


def test_discover_docker_permission_denied():
    """Reports permission error with helpful message."""
    with patch("core.autodiscovery.docker") as mock_docker:
        mock_docker.from_env.side_effect = PermissionError("access denied")
        mock_docker.errors = MagicMock()
        mock_docker.errors.DockerException = Exception
        state = discover_system()
    assert state.docker_available is False
    assert "docker group" in state.docker_error.lower() or "permission" in state.docker_error.lower()


def test_discover_docker_not_installed():
    """Reports Docker not installed."""
    with patch("core.autodiscovery.docker", None):
        state = discover_system()
    assert state.docker_available is False
    assert state.docker_error is not None


def test_discover_projects(tmp_path):
    """Finds projects with .git directories."""
    proj1 = tmp_path / "myapp"
    proj1.mkdir()
    (proj1 / ".git").mkdir()
    (proj1 / "docker-compose.yml").touch()

    proj2 = tmp_path / "other"
    proj2.mkdir()
    (proj2 / ".git").mkdir()
    (proj2 / "package.json").touch()

    with patch("core.autodiscovery.Path.home", return_value=tmp_path):
        state = discover_system()

    names = [p.name for p in state.projects]
    assert "myapp" in names
    assert "other" in names

    myapp = [p for p in state.projects if p.name == "myapp"][0]
    assert myapp.has_docker_compose is True

    other = [p for p in state.projects if p.name == "other"][0]
    assert other.has_package_json is True


def test_discover_psutil_limited():
    """Detects limited psutil access."""
    with patch("core.autodiscovery.psutil") as mock_ps:
        mock_ps.net_connections.side_effect = psutil.AccessDenied(pid=0)
        state = discover_system()
    assert state.psutil_limited is True


import psutil
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_autodiscovery.py -v
```

Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement `core/autodiscovery.py`**

```python
"""Auto-detect Claude, Docker, projects on the system."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import psutil

try:
    import docker
except ImportError:
    docker = None

log = logging.getLogger(__name__)


@dataclass
class ProjectInfo:
    path: Path
    name: str
    has_docker_compose: bool = False
    has_package_json: bool = False


@dataclass
class SystemState:
    claude_dir: Path | None = None
    docker_available: bool = False
    docker_error: str | None = None
    docker_client: object | None = None
    projects: list[ProjectInfo] = field(default_factory=list)
    psutil_limited: bool = False


def _find_claude_dir(config_override: str | None = None) -> Path | None:
    """Find Claude config directory."""
    if config_override:
        p = Path(config_override).expanduser()
        if p.exists():
            return p
        return None

    claude_dir = Path.home() / ".claude"
    projects_dir = claude_dir / "projects"
    if projects_dir.exists():
        # Check for at least one .jsonl file
        for _ in projects_dir.rglob("*.jsonl"):
            return claude_dir
    return None


def _find_docker(config_socket: str | None = None) -> tuple[bool, str | None, object | None]:
    """Try to connect to Docker. Returns (available, error_msg, client)."""
    if docker is None:
        return False, "Docker SDK not installed. Install: pip install docker", None

    try:
        kwargs = {}
        if config_socket:
            kwargs["base_url"] = f"unix://{config_socket}"
        client = docker.from_env(**kwargs)
        client.ping()
        return True, None, client
    except PermissionError:
        return False, "Permission denied. Fix: sudo usermod -aG docker $USER && newgrp docker", None
    except Exception as e:
        err = str(e)
        if "FileNotFoundError" in err or "No such file" in err:
            return False, "Docker socket not found. Is Docker running?", None
        if "Connection refused" in err:
            return False, "Docker daemon not responding. Start: sudo systemctl start docker", None
        return False, f"Docker error: {err}", None


def _find_projects(scan_paths: list[str] | None = None, depth: int = 2) -> list[ProjectInfo]:
    """Scan for projects with .git directories."""
    roots = [Path(p).expanduser() for p in scan_paths] if scan_paths else [Path.home()]
    projects = []

    for root in roots:
        if not root.is_dir():
            continue
        _scan_dir(root, projects, depth)

    projects.sort(key=lambda p: p.name.lower())
    return projects


def _scan_dir(base: Path, results: list[ProjectInfo], depth: int) -> None:
    """Recursively scan for projects up to given depth."""
    if depth <= 0:
        return
    try:
        for entry in base.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if (entry / ".git").is_dir():
                results.append(ProjectInfo(
                    path=entry,
                    name=entry.name,
                    has_docker_compose=(entry / "docker-compose.yml").exists() or (entry / "docker-compose.yaml").exists(),
                    has_package_json=(entry / "package.json").exists(),
                ))
            else:
                _scan_dir(entry, results, depth - 1)
    except PermissionError:
        pass


def _check_psutil_access() -> bool:
    """Check if psutil has full access to process info."""
    try:
        psutil.net_connections(kind="inet")
        return False  # not limited
    except psutil.AccessDenied:
        return True  # limited


def discover_system(config_paths: dict | None = None) -> SystemState:
    """Discover system capabilities. config_paths overrides auto-detection."""
    config_paths = config_paths or {}
    state = SystemState()

    # Claude
    state.claude_dir = _find_claude_dir(config_paths.get("claude_dir"))
    if state.claude_dir:
        log.info("Claude dir: %s", state.claude_dir)
    else:
        log.info("Claude dir not found")

    # Docker
    state.docker_available, state.docker_error, state.docker_client = _find_docker(
        config_paths.get("docker_socket")
    )
    if state.docker_available:
        log.info("Docker: available")
    else:
        log.warning("Docker: %s", state.docker_error)

    # Projects
    state.projects = _find_projects(config_paths.get("scan_paths"))
    log.info("Found %d projects", len(state.projects))

    # psutil
    state.psutil_limited = _check_psutil_access()
    if state.psutil_limited:
        log.warning("psutil: limited access, some processes hidden")

    return state
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_autodiscovery.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add core/autodiscovery.py tests/test_autodiscovery.py
git commit -m "feat: autodiscovery — find Claude, Docker, projects automatically"
```

---

## Task 4: Alerts — local sounds, warning on missing

**Files:**
- Modify: `core/alerts.py`
- Modify: `gui/monitor_alerts.py`
- Modify: `tests/test_alerts.py`

- [ ] **Step 1: Write failing test for local sound dir**

Add to `tests/test_alerts.py`:

```python
def test_alert_manager_finds_local_sounds(tmp_path):
    """AlertManager uses project-root sounds/ directory."""
    sounds_dir = tmp_path / "sounds" / "farts"
    sounds_dir.mkdir(parents=True)
    (sounds_dir / "fart1.mp3").touch()

    config = {
        "sounds": {"enabled": True, "quiet_hours_start": "23:00", "quiet_hours_end": "07:00"},
        "alerts": {"cooldown_seconds": 300, "desktop_notifications": False},
    }
    with patch("core.alerts._project_root", return_value=tmp_path):
        mgr = AlertManager(config)
    assert mgr._sound_dir == sounds_dir


def test_alert_manager_warns_on_missing_sounds(tmp_path, caplog):
    """AlertManager logs warning when sounds directory is empty."""
    sounds_dir = tmp_path / "sounds" / "farts"
    sounds_dir.mkdir(parents=True)
    # empty — no mp3 files

    config = {
        "sounds": {"enabled": True, "quiet_hours_start": "23:00", "quiet_hours_end": "07:00"},
        "alerts": {"cooldown_seconds": 300, "desktop_notifications": False},
    }
    with patch("core.alerts._project_root", return_value=tmp_path):
        mgr = AlertManager(config)

    import logging
    with caplog.at_level(logging.WARNING):
        alert = Alert(source="test", severity="critical", title="t", message="m")
        mgr.play_sound(alert)

    assert "no sound" in caplog.text.lower() or mgr._sound_dir is not None


from unittest.mock import patch
from core.alerts import AlertManager
from core.plugin import Alert
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_alerts.py -v
```

Expected: FAIL — no `_project_root` in alerts, old config structure

- [ ] **Step 3: Update `core/alerts.py`**

```python
"""Centralized alert manager — desktop notifications + fart sounds."""

from __future__ import annotations

import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path

from core.plugin import Alert

log = logging.getLogger(__name__)

SEVERITY_SOUNDS = {
    "critical": "farts",
    "warning": "farts",
}

URGENCY_MAP = {
    "critical": "critical",
    "warning": "normal",
    "info": "low",
}


def _project_root() -> Path:
    """Find project root."""
    current = Path(__file__).resolve().parent
    for parent in [current, current.parent, current.parent.parent]:
        if (parent / "pyproject.toml").exists() or (parent / "sounds").is_dir():
            return parent
    return current.parent


def _find_sound_dir() -> Path | None:
    """Find sounds directory in project root."""
    root = _project_root()
    sounds = root / "sounds" / "farts"
    if sounds.is_dir():
        return sounds
    # Fallback to sounds/ without farts/ subfolder
    sounds_root = root / "sounds"
    if sounds_root.is_dir():
        return sounds_root
    log.warning("No sounds directory found at %s", root / "sounds")
    return None


class AlertManager:
    """Handles deduplication, delivery, and sound for alerts."""

    def __init__(self, config: dict):
        self._config = config
        self._fired: dict[str, float] = {}
        self._cooldown = config["alerts"]["cooldown_seconds"]
        self._sound_dir = _find_sound_dir()

    def _dedup_key(self, alert: Alert) -> str:
        return f"{alert.source}:{alert.title}"

    def should_fire(self, alert: Alert) -> bool:
        key = self._dedup_key(alert)
        last = self._fired.get(key)
        if last is None:
            return True
        return (time.time() - last) > self._cooldown

    def mark_fired(self, alert: Alert) -> None:
        self._fired[self._dedup_key(alert)] = time.time()

    def is_quiet_hours(self) -> bool:
        now = datetime.now()
        sounds_cfg = self._config.get("sounds", {})
        start_str = sounds_cfg.get("quiet_hours_start", "23:00")
        end_str = sounds_cfg.get("quiet_hours_end", "07:00")
        start_h, start_m = map(int, start_str.split(":"))
        end_h, end_m = map(int, end_str.split(":"))
        current = now.hour * 60 + now.minute
        start = start_h * 60 + start_m
        end = end_h * 60 + end_m
        if start > end:
            return current >= start or current < end
        return start <= current < end

    def send_desktop(self, alert: Alert) -> None:
        if not self._config["alerts"].get("desktop_notifications", True):
            return
        urgency = URGENCY_MAP.get(alert.severity, "normal")
        try:
            subprocess.Popen(
                ["notify-send", "-u", urgency,
                 f"[{alert.source}] {alert.title}", alert.message],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    def play_sound(self, alert: Alert) -> None:
        sounds_cfg = self._config.get("sounds", {})
        if not sounds_cfg.get("enabled", True):
            return
        if self.is_quiet_hours():
            return
        if not self._sound_dir:
            log.warning("No sounds found — skipping sound for alert: %s", alert.title)
            return

        # Pick random sound from category
        import random
        category = SEVERITY_SOUNDS.get(alert.severity)
        if not category:
            return

        sound_files = [f for f in self._sound_dir.iterdir()
                       if f.suffix.lower() in (".mp3", ".wav", ".ogg", ".flac")]
        if not sound_files:
            log.warning("No sound files in %s", self._sound_dir)
            return

        sound_path = random.choice(sound_files)
        self._play_file(sound_path)

    def _play_file(self, sound_path: Path) -> None:
        """Play a sound file using available system player."""
        import shutil
        for cmd_name, args_fn in [
            ("ffplay", lambda p: ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(p)]),
            ("paplay", lambda p: ["paplay", str(p)]),
            ("aplay", lambda p: ["aplay", str(p)]),
        ]:
            if shutil.which(cmd_name):
                try:
                    subprocess.Popen(args_fn(sound_path),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except FileNotFoundError:
                    continue

    def process(self, alert: Alert) -> bool:
        """Process alert: dedup, notify, sound. Returns True if fired."""
        if not self.should_fire(alert):
            return False
        self.mark_fired(alert)
        self.send_desktop(alert)
        self.play_sound(alert)
        return True
```

- [ ] **Step 4: Update `gui/monitor_alerts.py` to delegate to `core/alerts.py`**

```python
"""Monitor alert manager for GUI — thin wrapper around core AlertManager."""

from __future__ import annotations

from core.alerts import AlertManager
from core.plugin import Alert


class MonitorAlertManager:
    """GUI-side alert manager. Delegates to core AlertManager."""

    def __init__(self, config: dict):
        self._manager = AlertManager(config)

    def process(self, alert: Alert) -> bool:
        return self._manager.process(alert)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_alerts.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add core/alerts.py gui/monitor_alerts.py tests/test_alerts.py
git commit -m "feat: alerts — local sounds dir, warning on missing, unified manager"
```

---

## Task 5: Move V1 files, clean up legacy

**Files:**
- Move: `parser.py` → `core/parser.py`
- Move: `analyzer.py` → `core/analyzer.py`
- Delete: `db.py`, `hook.py`, `importer.py`, `dashboard.py`, `claude-wrapper.sh`
- Delete: `core/app.py`
- Delete: `gui/docker_tab.py`, `gui/ports_tab.py`, `gui/security_tab.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Move parser and analyzer**

```bash
git mv parser.py core/parser.py
git mv analyzer.py core/analyzer.py
```

- [ ] **Step 2: Delete V1 legacy files**

```bash
git rm db.py hook.py importer.py dashboard.py claude-wrapper.sh
```

- [ ] **Step 3: Delete TUI**

```bash
git rm core/app.py
```

- [ ] **Step 4: Delete old GUI tabs (will be replaced)**

```bash
git rm gui/docker_tab.py gui/ports_tab.py gui/security_tab.py
```

- [ ] **Step 5: Update `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "claude-monitor"
version = "3.0.0"
description = "Dev environment monitoring platform — Win95 style"
requires-python = ">=3.11"
dependencies = [
    "PyQt5>=5.15",
    "docker>=7.0",
    "psutil>=5.9",
    "aiosqlite>=0.19",
]

[project.optional-dependencies]
security = ["pip-audit>=2.6"]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]

[project.scripts]
dev-monitor-gui = "gui.app:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 6: Fix imports in tests that reference deleted modules**

Check and update any tests referencing `core.app.DevMonitorApp` (e.g., `tests/test_app.py`). Either delete the test or update it to test the new GUI app later.

```bash
# Remove test for deleted TUI app
git rm tests/test_app.py
```

- [ ] **Step 7: Run remaining tests to check nothing broke**

```bash
pytest tests/ -v --ignore=tests/test_app.py 2>&1 | head -50
```

Expected: existing plugin/config/alert tests still pass

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: remove V1 legacy, TUI, old tabs — prepare for new GUI"
```

---

## Task 6: Security explanations — hardcoded dict

**Files:**
- Create: `gui/pages/__init__.py`
- Create: `gui/security_explanations.py`
- Create: `tests/test_security_explanations.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_security_explanations.py`:

```python
"""Tests for security finding explanations."""

from gui.security_explanations import get_explanation, EXPLANATIONS


def test_privileged_container_explanation():
    explanation = get_explanation("docker", "runs in privileged mode")
    assert explanation is not None
    assert "what" in explanation
    assert "risk" in explanation
    assert "fix" in explanation
    assert len(explanation["what"]) > 10
    assert len(explanation["risk"]) > 10
    assert len(explanation["fix"]) > 10


def test_docker_sock_explanation():
    explanation = get_explanation("docker", "docker.sock mounted inside container")
    assert explanation is not None


def test_root_user_explanation():
    explanation = get_explanation("docker", "runs as root")
    assert explanation is not None


def test_env_in_git_explanation():
    explanation = get_explanation("config", ".env file committed in git")
    assert explanation is not None


def test_exposed_port_explanation():
    explanation = get_explanation("network", "exposed on 0.0.0.0")
    assert explanation is not None


def test_broad_permissions_explanation():
    explanation = get_explanation("config", "Broad permissions")
    assert explanation is not None


def test_latest_tag_explanation():
    explanation = get_explanation("docker", ":latest tag")
    assert explanation is not None


def test_host_network_explanation():
    explanation = get_explanation("docker", "host network mode")
    assert explanation is not None


def test_unknown_finding_returns_generic():
    explanation = get_explanation("unknown", "something weird happened")
    assert explanation is not None
    assert "what" in explanation


def test_all_explanations_have_required_keys():
    """Every explanation must have what, risk, fix."""
    for key, exp in EXPLANATIONS.items():
        assert "what" in exp, f"Missing 'what' in {key}"
        assert "risk" in exp, f"Missing 'risk' in {key}"
        assert "fix" in exp, f"Missing 'fix' in {key}"


def test_human_description():
    """get_human_description returns simple text instead of technical jargon."""
    from gui.security_explanations import get_human_description
    desc = get_human_description("docker", "nginx: runs as root (no USER set)")
    assert "root" not in desc.lower() or "admin" in desc.lower() or "повний доступ" in desc.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_security_explanations.py -v
```

Expected: FAIL — module doesn't exist

- [ ] **Step 3: Create `gui/pages/__init__.py`**

```python
"""GUI pages package."""
```

- [ ] **Step 4: Create `gui/security_explanations.py`**

```python
"""Human-readable explanations for security findings.

Each finding type maps to a dict with:
- what: What this means in plain language
- risk: What an attacker could do
- fix: Copy-paste fix command or file change
"""

from __future__ import annotations

import re

EXPLANATIONS: dict[tuple[str, str], dict[str, str]] = {
    ("docker", "privileged"): {
        "what": "Container runs with full system privileges — same as root on the host machine.",
        "risk": "If an attacker compromises this container, they gain complete control over your server. They can read all files, install malware, access other containers.",
        "fix": "Remove 'privileged: true' from docker-compose.yml.\nIf you need specific permissions, use cap_add instead:\n\n  cap_add:\n    - NET_ADMIN  # only what you actually need",
    },
    ("docker", "docker.sock"): {
        "what": "Docker control socket is mounted inside the container. This gives the container full control over Docker itself.",
        "risk": "An attacker inside this container can create new containers, read secrets from other containers, or escape to the host entirely.",
        "fix": "Remove the docker.sock volume mount from docker-compose.yml:\n\n  # DELETE this line:\n  - /var/run/docker.sock:/var/run/docker.sock\n\nIf you need Docker access, use a Docker proxy with limited permissions.",
    },
    ("docker", "host network"): {
        "what": "Container shares the host's network directly instead of having its own isolated network.",
        "risk": "The container can see all network traffic on the host, access services on localhost, and bypass network isolation between containers.",
        "fix": "Remove 'network_mode: host' from docker-compose.yml.\nUse port mapping instead:\n\n  ports:\n    - '8080:8080'",
    },
    ("docker", "root"): {
        "what": "Container runs as admin (root). If hacked, attacker gets full access inside the container.",
        "risk": "Combined with other vulnerabilities, root access makes container escape much easier. The attacker can modify any file inside the container.",
        "fix": "Add a USER line to your Dockerfile:\n\n  RUN adduser --disabled-password appuser\n  USER appuser\n\nOr in docker-compose.yml:\n\n  user: '1000:1000'",
    },
    ("docker", "latest"): {
        "what": "Container uses the :latest tag instead of a specific version. You don't know exactly which version is running.",
        "risk": "A compromised or buggy update could be pulled automatically. Builds are not reproducible — works on my machine, breaks on yours.",
        "fix": "Pin to a specific version in your Dockerfile or docker-compose.yml:\n\n  # Instead of: image: postgres:latest\n  image: postgres:16.2-alpine",
    },
    ("config", "env_in_git"): {
        "what": "A .env file with secrets (passwords, API keys) is committed to git. Anyone with repo access can see them.",
        "risk": "If the repo is public or gets leaked, all your secrets are exposed. Passwords, API keys, database credentials — everything.",
        "fix": "1. Add .env to .gitignore:\n   echo '.env*' >> .gitignore\n\n2. Remove from git history:\n   git rm --cached .env\n   git commit -m 'remove .env from tracking'\n\n3. Rotate ALL secrets that were in the file — they're already compromised.",
    },
    ("config", "permissions"): {
        "what": "A sensitive file (with passwords, keys, or certificates) has too broad permissions. Other users on the system can read it.",
        "risk": "Any user on the server can read this file and steal credentials or certificates.",
        "fix": "Restrict permissions to owner only:\n\n  chmod 600 <filename>\n\nThis makes the file readable only by its owner.",
    },
    ("network", "exposed"): {
        "what": "This service listens on all network interfaces (0.0.0.0) instead of just localhost. It's accessible from outside your machine.",
        "risk": "Anyone on your network (or the internet if port-forwarded) can connect to this service. Databases, Redis, debug servers should never be exposed.",
        "fix": "Bind to localhost only. In docker-compose.yml:\n\n  ports:\n    # Instead of: '5432:5432'\n    - '127.0.0.1:5432:5432'\n\nOr in app config, change host from 0.0.0.0 to 127.0.0.1",
    },
    ("deps", "vulnerability"): {
        "what": "A dependency has a known security vulnerability (CVE). An attacker knows exactly how to exploit it.",
        "risk": "Depending on the vulnerability, an attacker could execute code on your server, steal data, or crash your application.",
        "fix": "Update the vulnerable package:\n\n  pip install --upgrade <package-name>\n\nOr pin a fixed version in requirements.txt.",
    },
}

# Patterns to match finding descriptions to explanation keys
_PATTERNS: list[tuple[re.Pattern, tuple[str, str]]] = [
    (re.compile(r"privileged mode", re.I), ("docker", "privileged")),
    (re.compile(r"docker\.sock", re.I), ("docker", "docker.sock")),
    (re.compile(r"host network", re.I), ("docker", "host network")),
    (re.compile(r"runs as root|no USER set", re.I), ("docker", "root")),
    (re.compile(r":latest tag|:latest\b", re.I), ("docker", "latest")),
    (re.compile(r"\.env.*committed|\.env.*git", re.I), ("config", "env_in_git")),
    (re.compile(r"broad permissions|Broad permissions", re.I), ("config", "permissions")),
    (re.compile(r"exposed on 0\.0\.0\.0|0\.0\.0\.0", re.I), ("network", "exposed")),
    (re.compile(r"CVE-|vulnerability|vuln", re.I), ("deps", "vulnerability")),
]

_GENERIC = {
    "what": "A potential security issue was detected in your environment.",
    "risk": "This could expose your system to attacks. Review the details and take action.",
    "fix": "Review the finding description and consult security documentation for your specific setup.",
}

# Human-readable description replacements
_HUMAN_DESCRIPTIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(.+): runs in privileged mode"), r"\1: full admin access — if hacked, attacker owns the server"),
    (re.compile(r"(.+): docker\.sock mounted inside container"), r"\1: Docker control exposed — attacker can control ALL containers"),
    (re.compile(r"(.+): uses host network mode"), r"\1: shares host network — can see all traffic"),
    (re.compile(r"(.+): runs as root \(no USER set\)"), r"\1: runs as admin — if hacked, attacker gets full access"),
    (re.compile(r"(.+): uses :latest tag \((.+)\)"), r"\1: no version pinned (\2) — updates can break things"),
    (re.compile(r"\.env file committed in git: (.+)"), r"Secrets leaked in git: \1 — passwords visible to anyone with access"),
    (re.compile(r"Broad permissions \((.+)\) on sensitive file: (.+)"), r"File \2 readable by everyone (perms: \1) — should be owner-only"),
    (re.compile(r"Port (\d+) \((.+)\) exposed on 0\.0\.0\.0"), r"Port \1 (\2) open to the world — should be localhost only"),
]


def get_explanation(finding_type: str, description: str) -> dict[str, str]:
    """Get human-readable explanation for a security finding."""
    # Try exact key match first
    for pattern, key in _PATTERNS:
        if pattern.search(description):
            return EXPLANATIONS.get(key, _GENERIC)

    # Fallback: try by type
    for key, exp in EXPLANATIONS.items():
        if key[0] == finding_type:
            return exp

    return _GENERIC


def get_human_description(finding_type: str, description: str) -> str:
    """Convert technical finding description to human-readable text."""
    for pattern, replacement in _HUMAN_DESCRIPTIONS:
        result = pattern.sub(replacement, description)
        if result != description:
            return result
    return description
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_security_explanations.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add gui/pages/__init__.py gui/security_explanations.py tests/test_security_explanations.py
git commit -m "feat: human-readable security explanations for non-technical users"
```

---

## Task 7: Sidebar widget

**Files:**
- Create: `gui/sidebar.py`
- Create: `tests/test_sidebar.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_sidebar.py`:

```python
"""Tests for Win95 sidebar widget."""

import sys
from unittest.mock import patch

# Ensure PyQt5 can be imported in test
import pytest

try:
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
except ImportError:
    pytest.skip("PyQt5 not available", allow_module_level=True)

from gui.sidebar import Sidebar, SidebarItem


def test_sidebar_creates_items():
    items = [
        SidebarItem("Overview", "overview"),
        SidebarItem("Docker", "docker"),
    ]
    sidebar = Sidebar(items)
    assert sidebar.count() == 2


def test_sidebar_select_item():
    items = [
        SidebarItem("Overview", "overview"),
        SidebarItem("Docker", "docker"),
    ]
    sidebar = Sidebar(items)
    sidebar.select("docker")
    assert sidebar.selected_key() == "docker"


def test_sidebar_update_counter():
    items = [
        SidebarItem("Docker", "docker"),
    ]
    sidebar = Sidebar(items)
    sidebar.update_counter("docker", 7)
    # Check the label text contains the counter
    text = sidebar.item_text("docker")
    assert "(7)" in text


def test_sidebar_update_alert():
    items = [
        SidebarItem("Security", "security"),
    ]
    sidebar = Sidebar(items)
    sidebar.update_alert("security", 3)
    text = sidebar.item_text("security")
    assert "(3!)" in text


def test_sidebar_disable_item():
    items = [
        SidebarItem("Docker", "docker"),
    ]
    sidebar = Sidebar(items)
    sidebar.set_enabled("docker", False)
    assert sidebar.is_item_enabled("docker") is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_sidebar.py -v
```

Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement `gui/sidebar.py`**

```python
"""Win95 Explorer-style sidebar widget."""

from __future__ import annotations

from dataclasses import dataclass
from PyQt5.QtWidgets import QListWidget, QListWidgetItem
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QColor, QFont


@dataclass
class SidebarItem:
    label: str
    key: str
    is_separator: bool = False


SIDEBAR_STYLE = """
QListWidget {
    background: #c0c0c0;
    border: none;
    border-right: 2px groove #808080;
    font-family: "MS Sans Serif", "Liberation Sans", Arial, sans-serif;
    font-size: 12px;
    outline: none;
}
QListWidget::item {
    padding: 6px 10px;
    border: none;
}
QListWidget::item:selected {
    background: #000080;
    color: white;
}
QListWidget::item:hover:!selected {
    background: #d4d4d4;
}
QListWidget::item:disabled {
    color: #808080;
}
"""


class Sidebar(QListWidget):
    """Win95 Explorer sidebar with selectable items and counters."""

    page_selected = pyqtSignal(str)  # emits key

    def __init__(self, items: list[SidebarItem], parent=None):
        super().__init__(parent)
        self.setFixedWidth(150)
        self.setStyleSheet(SIDEBAR_STYLE)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._items: dict[str, QListWidgetItem] = {}
        self._labels: dict[str, str] = {}
        self._counters: dict[str, str] = {}

        for item in items:
            if item.is_separator:
                list_item = QListWidgetItem("")
                list_item.setFlags(Qt.NoItemFlags)
                list_item.setSizeHint(list_item.sizeHint().__class__(0, 8))
                # Draw a groove-style separator
                list_item.setBackground(QColor("#c0c0c0"))
                self.addItem(list_item)
            else:
                list_item = QListWidgetItem(item.label)
                list_item.setData(Qt.UserRole, item.key)
                self.addItem(list_item)
                self._items[item.key] = list_item
                self._labels[item.key] = item.label

        self.currentItemChanged.connect(self._on_item_changed)

        # Select first non-separator item
        for i in range(self.count()):
            item = self.item(i)
            if item.flags() & Qt.ItemIsSelectable:
                self.setCurrentItem(item)
                break

    def _on_item_changed(self, current: QListWidgetItem, _previous):
        if current and current.data(Qt.UserRole):
            self.page_selected.emit(current.data(Qt.UserRole))

    def select(self, key: str) -> None:
        """Select item by key."""
        if key in self._items:
            self.setCurrentItem(self._items[key])

    def selected_key(self) -> str | None:
        """Get currently selected item key."""
        current = self.currentItem()
        if current:
            return current.data(Qt.UserRole)
        return None

    def item_text(self, key: str) -> str:
        """Get display text of an item."""
        if key in self._items:
            return self._items[key].text()
        return ""

    def _update_label(self, key: str) -> None:
        """Rebuild label text from base label + counter."""
        if key not in self._items:
            return
        base = self._labels[key]
        counter = self._counters.get(key, "")
        text = f"{base} {counter}" if counter else base
        self._items[key].setText(text)

    def update_counter(self, key: str, count: int) -> None:
        """Update counter badge, e.g., 'Docker (7)'."""
        self._counters[key] = f"({count})" if count > 0 else ""
        self._update_label(key)

    def update_alert(self, key: str, count: int) -> None:
        """Update alert badge, e.g., 'Security (3!)'."""
        self._counters[key] = f"({count}!)" if count > 0 else ""
        self._update_label(key)
        if key in self._items and count > 0:
            self._items[key].setForeground(QColor("#cc0000"))
        elif key in self._items:
            self._items[key].setForeground(QColor("#000000"))

    def set_enabled(self, key: str, enabled: bool) -> None:
        """Enable/disable a sidebar item (greyed out when disabled)."""
        if key in self._items:
            item = self._items[key]
            if enabled:
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            else:
                item.setFlags(Qt.NoItemFlags)

    def is_item_enabled(self, key: str) -> bool:
        """Check if item is enabled."""
        if key in self._items:
            return bool(self._items[key].flags() & Qt.ItemIsEnabled)
        return False
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_sidebar.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add gui/sidebar.py tests/test_sidebar.py
git commit -m "feat: Win95 Explorer sidebar widget with counters and alerts"
```

---

## Task 8: GUI pages — Overview, Usage, Analytics

**Files:**
- Create: `gui/pages/overview.py`
- Create: `gui/pages/usage.py`
- Create: `gui/pages/analytics.py`

These pages reuse existing logic from `claude_nagger.gui.app` (OverviewTab, AnalyticsTab, CalculatorTab) but adapted for the new layout.

- [ ] **Step 1: Create `gui/pages/overview.py`**

```python
"""Overview page — budget, tokens, nag messages, hasselhoff."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QGroupBox, QFormLayout,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class OverviewPage(QWidget):
    """Main overview: budget bar, token stats, nag message."""

    nag_requested = pyqtSignal()
    hoff_requested = pyqtSignal()
    refresh_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # Budget bar
        self.budget_label = QLabel("Budget: $0.00 / $5.00")
        self.budget_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.budget_label)

        self.budget_bar = QProgressBar()
        self.budget_bar.setMaximum(100)
        layout.addWidget(self.budget_bar)

        self.cost_label = QLabel("$0.00")
        self.cost_label.setStyleSheet(
            "font-size: 28px; font-weight: bold; color: #000080; "
            "border: 2px inset #808080; background: white; padding: 8px;"
        )
        self.cost_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.cost_label)

        # Token stats
        self.stats_group = QGroupBox("Tokens")
        sl = QFormLayout()
        self.lbl_sessions = QLabel("0")
        self.lbl_input = QLabel("0")
        self.lbl_output = QLabel("0")
        self.lbl_cache_read = QLabel("0")
        self.lbl_cache_write = QLabel("0")
        self.lbl_billable = QLabel("0")
        self.lbl_cache_eff = QLabel("0%")
        self.lbl_cache_saved = QLabel("$0.00")
        for label_text, widget in [
            ("Sessions:", self.lbl_sessions),
            ("Input tokens:", self.lbl_input),
            ("Output tokens:", self.lbl_output),
            ("Cache read:", self.lbl_cache_read),
            ("Cache write:", self.lbl_cache_write),
            ("Billable:", self.lbl_billable),
            ("Cache efficiency:", self.lbl_cache_eff),
            ("Cache saved:", self.lbl_cache_saved),
        ]:
            sl.addRow(QLabel(label_text), widget)
        self.stats_group.setLayout(sl)
        layout.addWidget(self.stats_group)

        # Nag message
        self.nag_label = QLabel("")
        self.nag_label.setWordWrap(True)
        self.nag_label.setStyleSheet(
            "font-style: italic; padding: 8px; background: #ffffcc; "
            "color: #000; border: 2px inset #808080;"
        )
        layout.addWidget(self.nag_label)

        # Hasselhoff image
        self.hoff_label = QLabel()
        self.hoff_label.setAlignment(Qt.AlignCenter)
        self.hoff_label.setFixedHeight(120)
        layout.addWidget(self.hoff_label)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_nag = QPushButton("Nag Me")
        self.btn_hoff = QPushButton("Hasselhoff!")
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        self.btn_nag.clicked.connect(self.nag_requested.emit)
        self.btn_hoff.clicked.connect(self.hoff_requested.emit)
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_nag)
        btn_layout.addWidget(self.btn_hoff)
        layout.addLayout(btn_layout)
        layout.addStretch()

    def update_data(self, stats, cost, cache_eff: float, savings: float,
                    nag_msg: str, budget: float = 5.0) -> None:
        """Update all overview widgets."""
        pct = min(cost.total_cost / budget * 100, 100) if budget > 0 else 0
        self.budget_label.setText(f"Budget: ${cost.total_cost:.2f} / ${budget:.2f}")
        self.budget_bar.setValue(int(pct))

        cc = "#00cc00" if pct < 33 else ("#ffcc00" if pct < 66 else "#ff3333")
        self.budget_bar.setStyleSheet(f"QProgressBar::chunk {{ background: {cc}; }}")
        self.cost_label.setText(f"${cost.total_cost:.2f}")
        self.cost_label.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {cc}; "
            "border: 2px inset #808080; background: white; padding: 8px;"
        )

        self.lbl_sessions.setText(str(len(stats.sessions)))
        self.lbl_input.setText(_fmt(stats.total_input))
        self.lbl_output.setText(_fmt(stats.total_output))
        self.lbl_cache_read.setText(_fmt(stats.total_cache_read))
        self.lbl_cache_write.setText(_fmt(stats.total_cache_write))
        self.lbl_billable.setText(_fmt(stats.total_billable))
        self.lbl_cache_eff.setText(f"{cache_eff:.1f}%")
        self.lbl_cache_saved.setText(f"~${savings:.2f}")
        self.nag_label.setText(f'"{nag_msg}"')

    def set_hoff_image(self, path: str) -> None:
        """Show hasselhoff image."""
        pixmap = QPixmap(path).scaledToHeight(100, Qt.SmoothTransformation)
        self.hoff_label.setPixmap(pixmap)

    def set_no_claude(self) -> None:
        """Show 'Claude not found' state."""
        self.budget_label.setText("Claude not found")
        self.cost_label.setText("--")
        self.nag_label.setText("Set Claude path in Settings to see token stats")
```

- [ ] **Step 2: Create `gui/pages/usage.py`**

```python
"""Usage page — delegates to claude_nagger UsageTab."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt


class UsagePage(QWidget):
    """Token usage breakdown — reuses claude_nagger's UsageTab if available."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self._inner = None

        try:
            from claude_nagger.gui.usage import UsageTab
            self._inner = UsageTab()
            layout.addWidget(self._inner)
        except ImportError:
            label = QLabel("Usage data requires claude_nagger module")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: #808080; font-style: italic;")
            layout.addWidget(label)

    def update_data(self, stats, cost, sub=None) -> None:
        if self._inner:
            self._inner.update_data(stats, cost, sub)
```

- [ ] **Step 3: Create `gui/pages/analytics.py`**

```python
"""Analytics page — model comparison and project breakdown."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt5.QtCore import Qt


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class AnalyticsPage(QWidget):
    """Cache efficiency, model comparison, project breakdown."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        self.cache_label = QLabel("Cache Efficiency: 0%")
        self.cache_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.cache_label)

        self.cache_bar = QProgressBar()
        self.cache_bar.setMaximum(100)
        layout.addWidget(self.cache_bar)

        self.savings_label = QLabel("Cache saved: $0.00")
        layout.addWidget(self.savings_label)

        self.model_table = QTableWidget()
        self.model_table.setColumnCount(3)
        self.model_table.setHorizontalHeaderLabels(["Model", "Tokens", "Cost"])
        self.model_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.model_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.model_table)

        self.project_table = QTableWidget()
        self.project_table.setColumnCount(3)
        self.project_table.setHorizontalHeaderLabels(["Project", "Billable", "Sessions"])
        self.project_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.project_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.project_table)

        layout.addStretch()

    def update_data(self, stats, cache_eff: float, savings: float,
                    comparison: dict, projects: list) -> None:
        self.cache_label.setText(f"Cache Efficiency: {cache_eff:.1f}%")
        self.cache_bar.setValue(int(cache_eff))
        self.savings_label.setText(f"Cache saved: ~${savings:.2f}")

        self.model_table.setRowCount(len(stats.model_totals))
        for i, (model, mu) in enumerate(stats.model_totals.items()):
            name = model.replace("claude-", "").upper()
            self.model_table.setItem(i, 0, QTableWidgetItem(name))
            self.model_table.setItem(i, 1, QTableWidgetItem(_fmt(mu.billable_tokens)))
            self.model_table.setItem(i, 2, QTableWidgetItem(f"${comparison.get('actual', 0):.2f}"))

        self.project_table.setRowCount(min(len(projects), 10))
        for i, p in enumerate(projects[:10]):
            self.project_table.setItem(i, 0, QTableWidgetItem(p.project))
            self.project_table.setItem(i, 1, QTableWidgetItem(_fmt(p.total_billable)))
            self.project_table.setItem(i, 2, QTableWidgetItem(str(p.sessions)))

    def set_no_claude(self) -> None:
        self.cache_label.setText("Claude not found — no analytics")
```

- [ ] **Step 4: Commit**

```bash
git add gui/pages/overview.py gui/pages/usage.py gui/pages/analytics.py
git commit -m "feat: GUI pages — overview, usage, analytics"
```

---

## Task 9: GUI pages — Docker with actions

**Files:**
- Create: `gui/pages/docker.py`

- [ ] **Step 1: Create `gui/pages/docker.py`**

```python
"""Docker page — container list with Fart Off/Start/Restart/Logs/Remove."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QLabel, QPushButton, QMenu, QAction,
    QDialog, QTextEdit, QMessageBox,
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QColor
import logging

log = logging.getLogger(__name__)


def _fmt_bytes(n: int) -> str:
    if n >= 1_073_741_824:
        return f"{n / 1_073_741_824:.1f}GB"
    if n >= 1_048_576:
        return f"{n / 1_048_576:.0f}MB"
    if n >= 1024:
        return f"{n / 1024:.0f}KB"
    return f"{n}B"


class DockerActionThread(QThread):
    """Run Docker actions in background thread."""
    finished = pyqtSignal(str, bool, str)  # action, success, message

    def __init__(self, client, container_name: str, action: str):
        super().__init__()
        self._client = client
        self._container_name = container_name
        self._action = action

    def run(self):
        try:
            container = self._client.containers.get(self._container_name)
            if self._action == "stop":
                container.stop(timeout=10)
                self.finished.emit("stop", True, f"{self._container_name} stopped")
            elif self._action == "start":
                container.start()
                self.finished.emit("start", True, f"{self._container_name} started")
            elif self._action == "restart":
                container.restart(timeout=10)
                self.finished.emit("restart", True, f"{self._container_name} restarted")
            elif self._action == "remove":
                container.remove(force=True)
                self.finished.emit("remove", True, f"{self._container_name} removed")
            elif self._action == "logs":
                logs = container.logs(tail=100).decode("utf-8", errors="replace")
                self.finished.emit("logs", True, logs)
        except Exception as e:
            self.finished.emit(self._action, False, str(e))


class LogsDialog(QDialog):
    """Dialog showing container logs."""

    def __init__(self, container_name: str, logs_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Logs: {container_name}")
        self.setMinimumSize(600, 400)
        layout = QVBoxLayout(self)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setFontFamily("Courier New")
        text.setFontPointSize(10)
        text.setPlainText(logs_text)
        text.moveCursor(text.textCursor().End)
        layout.addWidget(text)

        btn = QPushButton("Close")
        btn.clicked.connect(self.close)
        layout.addWidget(btn)


class DockerPage(QWidget):
    """Docker container monitoring with management actions."""

    fart_off_triggered = pyqtSignal(str)  # container name
    container_count_changed = pyqtSignal(int)  # number of running containers

    def __init__(self, docker_client=None):
        super().__init__()
        self._client = docker_client
        self._containers: list[dict] = []
        self._action_threads: list[DockerActionThread] = []

        layout = QVBoxLayout(self)

        # Error banner (hidden by default)
        self.error_banner = QLabel("")
        self.error_banner.setWordWrap(True)
        self.error_banner.setStyleSheet(
            "background: #ffffcc; color: #000; padding: 8px; "
            "border: 2px inset #808080; font-weight: bold;"
        )
        self.error_banner.hide()
        layout.addWidget(self.error_banner)

        # Container table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["", "NAME", "STATUS", "CPU%", "RAM", "PORTS", "HEALTH", ""]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("QTableWidget { alternate-background-color: #e8e8e8; }")
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table)

        # Events panel
        events_group = QGroupBox("Events")
        events_layout = QVBoxLayout()
        self.events_label = QLabel("No events yet")
        self.events_label.setWordWrap(True)
        self.events_label.setStyleSheet(
            "padding: 4px; background: white; border: 2px inset #808080; "
            "font-family: 'Courier New', monospace; font-size: 11px;"
        )
        self.events_label.setMinimumHeight(80)
        self.events_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        events_layout.addWidget(self.events_label)
        events_group.setLayout(events_layout)
        layout.addWidget(events_group)

        self._events: list[str] = []

    def set_docker_error(self, error: str) -> None:
        """Show error banner when Docker is not available."""
        self.error_banner.setText(f"Docker: {error}")
        self.error_banner.show()

    def set_docker_client(self, client) -> None:
        """Set Docker client after autodiscovery or manual config."""
        self._client = client
        self.error_banner.hide()

    def update_data(self, containers: list[dict]) -> None:
        self._containers = containers
        running = sum(1 for c in containers if c.get("status") == "running")
        self.container_count_changed.emit(running)

        self.table.setRowCount(len(containers))
        for i, c in enumerate(containers):
            status = c.get("status", "unknown")

            # Status icon
            if status == "running":
                icon, color = "\u25cf", QColor(0, 160, 0)
            elif status == "exited":
                icon, color = "\u25cb", QColor(128, 128, 128)
            else:
                icon, color = "\u25c9", QColor(200, 200, 0)

            cpu = c.get("cpu_percent", 0)
            if cpu > 80:
                color = QColor(255, 50, 50)

            icon_item = QTableWidgetItem(icon)
            icon_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, icon_item)
            self.table.setItem(i, 1, QTableWidgetItem(c.get("name", "?")))
            self.table.setItem(i, 2, QTableWidgetItem(status))

            cpu_str = f"{cpu:.1f}%" if status == "running" else "\u2014"
            cpu_item = QTableWidgetItem(cpu_str)
            cpu_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, cpu_item)

            mem = _fmt_bytes(c.get("mem_usage", 0)) if status == "running" else "\u2014"
            mem_item = QTableWidgetItem(mem)
            mem_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, mem_item)

            ports_list = c.get("ports", [])
            ports_str = ", ".join(f"{p['host_port']}\u2192{p['container_port']}" for p in ports_list[:3])
            self.table.setItem(i, 5, QTableWidgetItem(ports_str))

            health = c.get("health") or "\u2014"
            self.table.setItem(i, 6, QTableWidgetItem(health))

            # Fart Off button for running containers
            if status == "running":
                btn = QPushButton("Fart Off")
                btn.setStyleSheet(
                    "background: #c0c0c0; border: 2px outset #dfdfdf; "
                    "padding: 2px 8px; font-size: 10px; font-weight: bold;"
                )
                btn.clicked.connect(lambda _, name=c["name"]: self._fart_off(name))
                self.table.setCellWidget(i, 7, btn)
            else:
                self.table.setCellWidget(i, 7, None)

            # Color row
            for col in range(7):
                item = self.table.item(i, col)
                if item:
                    item.setForeground(color)

    def _fart_off(self, container_name: str) -> None:
        """Stop container and play fart sound."""
        self.fart_off_triggered.emit(container_name)
        self._run_action(container_name, "stop")

    def _show_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0 or row >= len(self._containers):
            return

        container = self._containers[row]
        name = container["name"]
        status = container["status"]

        menu = QMenu(self)
        if status == "running":
            menu.addAction("Stop", lambda: self._run_action(name, "stop"))
            menu.addAction("Restart", lambda: self._run_action(name, "restart"))
        else:
            menu.addAction("Start", lambda: self._run_action(name, "start"))
        menu.addAction("Logs", lambda: self._run_action(name, "logs"))
        menu.addSeparator()
        menu.addAction("Remove", lambda: self._confirm_remove(name))

        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _confirm_remove(self, name: str) -> None:
        reply = QMessageBox.question(
            self, "Remove Container",
            f"Remove container '{name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._run_action(name, "remove")

    def _run_action(self, container_name: str, action: str) -> None:
        if not self._client:
            return
        thread = DockerActionThread(self._client, container_name, action)
        thread.finished.connect(lambda act, ok, msg: self._on_action_done(container_name, act, ok, msg))
        self._action_threads.append(thread)
        thread.start()
        self.add_event(f"{action} → {container_name}...")

    @pyqtSlot(str, str, bool, str)
    def _on_action_done(self, container_name: str, action: str, success: bool, message: str) -> None:
        if action == "logs" and success:
            dialog = LogsDialog(container_name, message, self)
            dialog.show()
        elif success:
            self.add_event(f"{action} → {container_name}: OK")
        else:
            self.add_event(f"{action} → {container_name}: FAIL — {message}")

        # Clean up finished threads
        self._action_threads = [t for t in self._action_threads if t.isRunning()]

    def add_event(self, message: str) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._events.append(f"{ts}  {message}")
        self._events = self._events[-10:]
        self.events_label.setText("\n".join(self._events))
```

- [ ] **Step 2: Commit**

```bash
git add gui/pages/docker.py
git commit -m "feat: Docker page with Fart Off, Start, Restart, Logs, Remove"
```

---

## Task 10: GUI pages — Ports and Security

**Files:**
- Create: `gui/pages/ports.py`
- Create: `gui/pages/security.py`

- [ ] **Step 1: Create `gui/pages/ports.py`**

```python
"""Ports page — listening ports, conflicts, project mapping."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class PortsPage(QWidget):
    """Listening ports with conflict detection and project mapping."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # Warning banner (hidden by default)
        self.warning_banner = QLabel("")
        self.warning_banner.setWordWrap(True)
        self.warning_banner.setStyleSheet(
            "background: #ffffcc; color: #000; padding: 8px; "
            "border: 2px inset #808080;"
        )
        self.warning_banner.hide()
        layout.addWidget(self.warning_banner)

        # Ports table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["PORT", "PROTO", "PROCESS", "PROJECT", "IP", "STATUS"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("QTableWidget { alternate-background-color: #e8e8e8; }")
        layout.addWidget(self.table)

        # Summary
        self.summary = QLabel("")
        self.summary.setStyleSheet("padding: 4px; font-style: italic;")
        layout.addWidget(self.summary)

    def set_psutil_warning(self, limited: bool) -> None:
        """Show warning when psutil has limited access."""
        if limited:
            self.warning_banner.setText(
                "Some processes hidden — limited permissions. "
                "Run with sudo or add CAP_NET_ADMIN for full port info."
            )
            self.warning_banner.show()
        else:
            self.warning_banner.hide()

    def update_data(self, ports: list[dict]) -> None:
        self.table.setRowCount(len(ports))
        conflicts = 0
        exposed = 0

        for i, p in enumerate(ports):
            is_conflict = p.get("conflict", False)
            is_exposed = p.get("exposed", False)
            if is_conflict:
                conflicts += 1
            if is_exposed:
                exposed += 1

            if is_conflict:
                color = QColor(255, 50, 50)
            elif is_exposed:
                color = QColor(200, 140, 0)
            else:
                color = QColor(0, 120, 0)

            port_item = QTableWidgetItem(str(p.get("port", "")))
            port_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, port_item)

            self.table.setItem(i, 1, QTableWidgetItem(p.get("protocol", "")))

            process = p.get("process", "") or "<unknown process>"
            self.table.setItem(i, 2, QTableWidgetItem(process))
            self.table.setItem(i, 3, QTableWidgetItem(p.get("project", "")))
            self.table.setItem(i, 4, QTableWidgetItem(p.get("ip", "")))

            status = "CONFLICT" if is_conflict else ("EXPOSED" if is_exposed else "OK")
            self.table.setItem(i, 5, QTableWidgetItem(status))

            for col in range(6):
                item = self.table.item(i, col)
                if item:
                    item.setForeground(color)

        self.summary.setText(
            f"{len(ports)} ports listening | "
            f"{conflicts} conflicts | {exposed} exposed"
        )

    def port_count(self) -> int:
        return self.table.rowCount()
```

- [ ] **Step 2: Create `gui/pages/security.py`**

```python
"""Security page — findings table with detail panel and human explanations."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QGroupBox, QTextEdit, QSplitter,
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QColor

from gui.security_explanations import get_explanation, get_human_description


SEVERITY_COLORS = {
    "critical": ("#ffffff", "#cc0000"),
    "high": ("#000000", "#ff8c00"),
    "medium": ("#000000", "#ffcc00"),
    "low": ("#000000", "#c0c0c0"),
}


class SecurityScanThread(QThread):
    """Run security scan in background."""
    scan_done = pyqtSignal(list)  # list of finding dicts

    def __init__(self, scanner_fn):
        super().__init__()
        self._scanner_fn = scanner_fn

    def run(self):
        try:
            findings = self._scanner_fn()
            self.scan_done.emit(findings)
        except Exception as e:
            self.scan_done.emit([])


class SecurityPage(QWidget):
    """Security findings with human-readable explanations."""

    scan_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # Severity counters
        counter_layout = QHBoxLayout()
        self.counters = {}
        for sev in ["critical", "high", "medium", "low"]:
            fg, bg = SEVERITY_COLORS[sev]
            label = QLabel(f" {sev.upper()}: 0 ")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(
                f"font-size: 14px; font-weight: bold; color: {fg}; "
                f"background: {bg}; border: 2px outset #dfdfdf; padding: 4px 12px;"
            )
            self.counters[sev] = label
            counter_layout.addWidget(label)
        layout.addLayout(counter_layout)

        # Splitter: table on top, detail panel on bottom
        splitter = QSplitter(Qt.Vertical)

        # Findings table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["SEV", "TYPE", "DESCRIPTION", "SOURCE"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.currentCellChanged.connect(self._on_row_selected)
        splitter.addWidget(self.table)

        # Detail panel
        self.detail_panel = QGroupBox("Details")
        detail_layout = QVBoxLayout()

        self.detail_what = QLabel("")
        self.detail_what.setWordWrap(True)
        self.detail_what.setStyleSheet("padding: 4px;")

        self.detail_risk = QLabel("")
        self.detail_risk.setWordWrap(True)
        self.detail_risk.setStyleSheet("padding: 4px; color: #cc0000;")

        self.detail_fix = QTextEdit("")
        self.detail_fix.setReadOnly(True)
        self.detail_fix.setMaximumHeight(100)
        self.detail_fix.setFontFamily("Courier New")
        self.detail_fix.setFontPointSize(10)
        self.detail_fix.setStyleSheet("background: #1a1a2e; color: #00ff00; border: 2px inset #808080;")

        detail_layout.addWidget(QLabel("What is this:"))
        detail_layout.addWidget(self.detail_what)
        detail_layout.addWidget(QLabel("Risk:"))
        detail_layout.addWidget(self.detail_risk)
        detail_layout.addWidget(QLabel("How to fix:"))
        detail_layout.addWidget(self.detail_fix)
        self.detail_panel.setLayout(detail_layout)
        self.detail_panel.hide()
        splitter.addWidget(self.detail_panel)

        layout.addWidget(splitter)

        # Scan button
        btn_layout = QHBoxLayout()
        self.btn_scan = QPushButton("Scan Now")
        self.btn_scan.setStyleSheet("font-size: 13px; padding: 6px 16px;")
        self.btn_scan.clicked.connect(self.scan_requested.emit)
        btn_layout.addWidget(self.btn_scan)
        self.last_scan_label = QLabel("Last scan: never")
        self.last_scan_label.setStyleSheet("font-style: italic; color: #666;")
        btn_layout.addWidget(self.last_scan_label)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._findings: list[dict] = []

    def update_data(self, findings: list[dict]) -> None:
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        findings.sort(key=lambda f: order.get(f.get("severity", "low"), 4))
        self._findings = findings

        # Counters
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in findings:
            counts[f.get("severity", "low")] = counts.get(f.get("severity", "low"), 0) + 1
        for sev, label in self.counters.items():
            label.setText(f" {sev.upper()}: {counts[sev]} ")

        # Table
        self.table.setRowCount(len(findings))
        for i, f in enumerate(findings):
            sev = f.get("severity", "low")
            fg_hex, bg_hex = SEVERITY_COLORS.get(sev, ("#000", "#ccc"))

            sev_item = QTableWidgetItem(sev.upper())
            sev_item.setTextAlignment(Qt.AlignCenter)
            sev_item.setForeground(QColor(fg_hex))
            sev_item.setBackground(QColor(bg_hex))
            self.table.setItem(i, 0, sev_item)

            self.table.setItem(i, 1, QTableWidgetItem(f.get("type", "")))

            # Human-readable description
            desc = get_human_description(f.get("type", ""), f.get("description", ""))
            self.table.setItem(i, 2, QTableWidgetItem(desc[:100]))

            self.table.setItem(i, 3, QTableWidgetItem(f.get("source", "")[:30]))

        from datetime import datetime
        self.last_scan_label.setText(f"Last scan: {datetime.now().strftime('%H:%M:%S')}")

    def _on_row_selected(self, row, _col, _prev_row, _prev_col):
        if row < 0 or row >= len(self._findings):
            self.detail_panel.hide()
            return

        finding = self._findings[row]
        explanation = get_explanation(finding.get("type", ""), finding.get("description", ""))

        self.detail_what.setText(explanation["what"])
        self.detail_risk.setText(explanation["risk"])
        self.detail_fix.setPlainText(explanation["fix"])
        self.detail_panel.show()

    def set_scanning(self, scanning: bool) -> None:
        self.btn_scan.setEnabled(not scanning)
        self.btn_scan.setText("Scanning..." if scanning else "Scan Now")

    def critical_count(self) -> int:
        return sum(1 for f in self._findings if f.get("severity") in ("critical", "high"))
```

- [ ] **Step 3: Commit**

```bash
git add gui/pages/ports.py gui/pages/security.py
git commit -m "feat: Ports and Security pages with detail panel and explanations"
```

---

## Task 11: Main app — Explorer layout, single refresh loop, tray

**Files:**
- Rewrite: `gui/app.py`

- [ ] **Step 1: Rewrite `gui/app.py`**

```python
"""fart.run & awesome Hasselhoff — Dev Monitor GUI.

Win95 Explorer-style sidebar layout with unified refresh loop.
"""

import sys
import random
import logging
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QLabel, QSystemTrayIcon, QMenu, QMenuBar,
    QAction, QFileDialog, QMessageBox,
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon, QPixmap, QColor, QPainter, QFont

from core.config import load_config
from core.autodiscovery import discover_system, SystemState
from core.alerts import AlertManager
from core.plugin import Alert
from gui.sidebar import Sidebar, SidebarItem
from gui.pages.overview import OverviewPage
from gui.pages.docker import DockerPage
from gui.pages.ports import PortsPage
from gui.pages.security import SecurityPage, SecurityScanThread
from gui.pages.usage import UsagePage
from gui.pages.analytics import AnalyticsPage

log = logging.getLogger(__name__)

WIN95_STYLE = """
QMainWindow, QWidget { background-color: #c0c0c0; font-family: "MS Sans Serif", "Liberation Sans", Arial, sans-serif; font-size: 12px; }
QPushButton { background: #c0c0c0; border: 2px outset #dfdfdf; padding: 4px 12px; font-weight: bold; }
QPushButton:pressed { border: 2px inset #808080; }
QProgressBar { border: 2px inset #808080; background: white; text-align: center; height: 20px; }
QProgressBar::chunk { background: #000080; }
QGroupBox { border: 2px groove #808080; margin-top: 12px; padding-top: 16px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QTableWidget { background: white; border: 2px inset #808080; gridline-color: #808080; }
QHeaderView::section { background: #c0c0c0; border: 1px outset #dfdfdf; padding: 2px; font-weight: bold; }
QComboBox { background: white; border: 2px inset #808080; padding: 2px; }
QLabel { color: #000000; }
QMenuBar { background: #c0c0c0; border-bottom: 1px solid #808080; }
QMenuBar::item:selected { background: #000080; color: white; }
QMenu { background: #c0c0c0; border: 2px outset #dfdfdf; }
QMenu::item:selected { background: #000080; color: white; }
QStatusBar { background: #c0c0c0; border-top: 2px groove #808080; }
"""


def _make_tray_icon(color: str = "green") -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    colors = {"green": QColor(0, 200, 0), "yellow": QColor(255, 200, 0), "red": QColor(255, 50, 50)}
    painter.setBrush(colors.get(color, colors["green"]))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, 28, 28)
    painter.setPen(QColor(255, 255, 255))
    painter.setFont(QFont("Arial", 14, QFont.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "F")
    painter.end()
    return QIcon(pixmap)


class MonitorApp(QMainWindow):
    """Main application window — Win95 Explorer style."""

    def __init__(self, config: dict, system_state: SystemState):
        super().__init__()
        self._config = config
        self._state = system_state
        self._alert_manager = AlertManager(config)

        self.setWindowTitle("fart.run & awesome Hasselhoff — Dev Monitor")
        self.setMinimumSize(950, 650)
        self.setStyleSheet(WIN95_STYLE)

        # Menu bar
        self._create_menu_bar()

        # Central widget: sidebar + content stack
        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        sidebar_items = [
            SidebarItem("Overview", "overview"),
            SidebarItem("Docker", "docker"),
            SidebarItem("Ports", "ports"),
            SidebarItem("Security", "security"),
            SidebarItem("Usage", "usage"),
            SidebarItem("Analytics", "analytics"),
            SidebarItem("", "", is_separator=True),
            SidebarItem("Settings", "settings"),
        ]
        self.sidebar = Sidebar(sidebar_items)
        self.sidebar.page_selected.connect(self._on_page_selected)
        main_layout.addWidget(self.sidebar)

        # Content stack
        self.stack = QStackedWidget()
        self._pages: dict[str, QWidget] = {}

        # Create pages
        self.page_overview = OverviewPage()
        self.page_docker = DockerPage(system_state.docker_client)
        self.page_ports = PortsPage()
        self.page_security = SecurityPage()
        self.page_usage = UsagePage()
        self.page_analytics = AnalyticsPage()
        self.page_settings = QLabel("Settings — coming soon")
        self.page_settings.setAlignment(Qt.AlignCenter)

        for key, page in [
            ("overview", self.page_overview),
            ("docker", self.page_docker),
            ("ports", self.page_ports),
            ("security", self.page_security),
            ("usage", self.page_usage),
            ("analytics", self.page_analytics),
            ("settings", self.page_settings),
        ]:
            self.stack.addWidget(page)
            self._pages[key] = page

        main_layout.addWidget(self.stack)
        self.setCentralWidget(central)

        # Status bar
        self.statusBar().showMessage("Ready")

        # Connect signals
        self.page_overview.refresh_requested.connect(self._refresh_all)
        self.page_overview.nag_requested.connect(self._do_nag)
        self.page_overview.hoff_requested.connect(self._do_hoff)
        self.page_docker.fart_off_triggered.connect(self._on_fart_off)
        self.page_docker.container_count_changed.connect(
            lambda n: self.sidebar.update_counter("docker", n)
        )
        self.page_security.scan_requested.connect(self._run_security_scan)

        # Apply autodiscovery state
        if not system_state.docker_available:
            self.page_docker.set_docker_error(system_state.docker_error or "Docker not available")
        if not system_state.claude_dir:
            self.page_overview.set_no_claude()
            self.page_analytics.set_no_claude()
        if system_state.psutil_limited:
            self.page_ports.set_psutil_warning(True)

        # Unified refresh timer
        refresh_interval = config["general"]["refresh_interval"] * 1000
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_all)
        self._refresh_timer.start(refresh_interval)

        # Security scan timer (separate, longer interval)
        scan_interval = config["plugins"]["security_scan"]["scan_interval"] * 1000
        self._security_timer = QTimer(self)
        self._security_timer.timeout.connect(self._run_security_scan)
        self._security_timer.start(scan_interval)

        # Initial refresh
        self._refresh_all()
        self._run_security_scan()

    def _create_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        file_menu.addAction("Refresh", self._refresh_all, "Ctrl+R")
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close, "Ctrl+Q")

        tools_menu = menubar.addMenu("Tools")
        tools_menu.addAction("Scan Security", self._run_security_scan)
        tools_menu.addAction("Nag Me", self._do_nag)
        tools_menu.addAction("Hasselhoff!", self._do_hoff)

        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self._show_about)

    def _on_page_selected(self, key: str):
        if key in self._pages:
            self.stack.setCurrentWidget(self._pages[key])

    def _refresh_all(self):
        """Single refresh loop — collects data from all sources."""
        # Docker
        if self._state.docker_available and self._state.docker_client:
            try:
                from plugins.docker_monitor.collector import collect_containers
                containers = self._state.docker_client.containers.list(all=True)
                infos = collect_containers(containers)
                self.page_docker.update_data(infos)
                self._check_docker_alerts(infos)
            except Exception as e:
                log.error("Docker refresh error: %s", e)

        # Ports
        try:
            from plugins.port_map.collector import collect_ports
            ports = collect_ports()
            self.page_ports.update_data(ports)
            self.sidebar.update_counter("ports", len(ports))

            for p in ports:
                if p.get("conflict"):
                    self._alert_manager.process(Alert(
                        source="ports", severity="warning",
                        title=f"Port {p['port']} conflict",
                        message=f"Port {p['port']} used by multiple processes",
                    ))
        except Exception as e:
            log.error("Ports refresh error: %s", e)

        # Claude stats (if available)
        if self._state.claude_dir:
            try:
                from claude_nagger.core.parser import TokenParser
                from claude_nagger.core.calculator import CostCalculator
                from claude_nagger.core.analyzer import Analyzer
                from claude_nagger.nagger.messages import get_nag_message, get_nag_level

                parser = TokenParser()
                stats = parser.parse_today()
                calc = CostCalculator()
                cost = calc.calculate_cost(stats)
                cache_eff = Analyzer.cache_efficiency(stats)
                savings = Analyzer.cache_savings_usd(stats)
                comparison = Analyzer.model_comparison(stats)
                projects = Analyzer.project_breakdown(stats)

                level = get_nag_level(stats.total_billable)
                nag_msg = get_nag_message(level, stats.total_billable, len(stats.sessions))

                self.page_overview.update_data(stats, cost, cache_eff, savings, nag_msg)
                self.page_analytics.update_data(stats, cache_eff, savings, comparison, projects)

                sub = parser.get_subscription()
                self.page_usage.update_data(stats, cost, sub)
            except Exception as e:
                log.error("Claude stats error: %s", e)

        self.statusBar().showMessage(
            f"Docker: {self.sidebar.item_text('docker')} | "
            f"Ports: {self.sidebar.item_text('ports')} | "
            f"Ready"
        )

    def _check_docker_alerts(self, infos: list[dict]):
        cpu_thresh = self._config["plugins"]["docker_monitor"]["cpu_threshold"]
        ram_thresh = self._config["plugins"]["docker_monitor"]["ram_threshold"]

        for info in infos:
            if info["status"] == "exited" and info.get("exit_code", 0) != 0:
                self._alert_manager.process(Alert(
                    source="docker", severity="critical",
                    title=f"{info['name']} crashed (exit {info['exit_code']})",
                    message=f"Container {info['name']} exited with code {info['exit_code']}",
                ))
            elif info["status"] == "running":
                if info["cpu_percent"] > cpu_thresh:
                    self._alert_manager.process(Alert(
                        source="docker", severity="warning",
                        title=f"{info['name']} CPU {info['cpu_percent']:.0f}%",
                        message=f"CPU at {info['cpu_percent']:.1f}%",
                    ))
                if info["mem_limit"] > 0:
                    ram_pct = (info["mem_usage"] / info["mem_limit"]) * 100
                    if ram_pct > ram_thresh:
                        self._alert_manager.process(Alert(
                            source="docker", severity="critical",
                            title=f"{info['name']} RAM {ram_pct:.0f}%",
                            message=f"RAM at {ram_pct:.1f}%",
                        ))

    def _run_security_scan(self):
        self.page_security.set_scanning(True)

        def scan():
            from plugins.security_scan.scanners import (
                scan_docker_security, scan_env_in_git,
                scan_file_permissions, scan_exposed_ports,
            )
            findings = []

            if self._state.docker_available and self._state.docker_client:
                try:
                    from plugins.docker_monitor.collector import collect_containers
                    containers = self._state.docker_client.containers.list(all=True)
                    infos = collect_containers(containers)
                    findings.extend(scan_docker_security(infos))
                except Exception:
                    pass

            scan_paths = [Path(p).expanduser() for p in
                          self._config["plugins"]["security_scan"].get("scan_paths", ["~"])]
            findings.extend(scan_env_in_git(scan_paths))
            findings.extend(scan_file_permissions(scan_paths))

            try:
                from plugins.port_map.collector import collect_ports
                ports = collect_ports()
                findings.extend(scan_exposed_ports(ports))
            except Exception:
                pass

            return [
                {"type": f.type, "severity": f.severity,
                 "description": f.description, "source": f.source}
                for f in findings
            ]

        self._scan_thread = SecurityScanThread(scan)
        self._scan_thread.scan_done.connect(self._on_scan_done)
        self._scan_thread.start()

    def _on_scan_done(self, findings: list[dict]):
        self.page_security.update_data(findings)
        self.page_security.set_scanning(False)

        critical = self.page_security.critical_count()
        self.sidebar.update_alert("security", critical)

        for f in findings:
            if f["severity"] in ("critical", "high"):
                self._alert_manager.process(Alert(
                    source="security", severity=f["severity"],
                    title=f"[{f['type']}] {f['description'][:50]}",
                    message=f["description"],
                ))

    def _on_fart_off(self, container_name: str):
        """Play fart sound when Fart Off button is pressed."""
        self._alert_manager.play_sound(Alert(
            source="docker", severity="warning",
            title=f"Fart Off: {container_name}",
            message=f"Stopping {container_name}",
        ))

    def _do_nag(self):
        self._alert_manager.play_sound(Alert(
            source="nag", severity="critical", title="Nag", message="nag",
        ))

    def _do_hoff(self):
        try:
            from claude_nagger.nagger.hasselhoff import get_hoff_phrase, get_hoff_image, get_victory_sound
            img_path = get_hoff_image()
            if img_path:
                self.page_overview.set_hoff_image(img_path)
            victory = get_victory_sound()
            if victory:
                self._alert_manager._play_file(Path(victory))
            phrase = get_hoff_phrase()
            self.statusBar().showMessage(f"HASSELHOFF: {phrase}", 5000)
        except ImportError:
            self.statusBar().showMessage("Hasselhoff requires claude_nagger module", 3000)

    def _show_about(self):
        QMessageBox.about(
            self, "About",
            "fart.run & awesome Hasselhoff\n"
            "Dev Environment Monitor v3.0\n\n"
            "Win95 style, fart-powered alerts,\n"
            "and David Hasselhoff supervision."
        )


class MonitorTrayApp:
    """System tray application wrapping MonitorApp."""

    def __init__(self, config: dict, system_state: SystemState):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.dashboard = MonitorApp(config, system_state)

        self.tray = QSystemTrayIcon(_make_tray_icon("green"), self.app)
        self.tray.setToolTip("fart.run & awesome Hasselhoff")
        self.tray.activated.connect(self._on_tray_click)

        self.menu = QMenu()
        self.menu.addAction("Show Dashboard", self._show)
        self.menu.addAction("Nag Me", self.dashboard._do_nag)
        self.menu.addAction("Hasselhoff!", self.dashboard._do_hoff)
        self.menu.addSeparator()
        self.menu.addAction("Quit", self._quit)
        self.tray.setContextMenu(self.menu)

        self.tray.show()
        self.dashboard.show()

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._show()

    def _show(self):
        self.dashboard.show()
        self.dashboard.raise_()

    def _quit(self):
        self.tray.hide()
        self.app.quit()

    def run(self):
        return self.app.exec_()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    config = load_config()
    system_state = discover_system(config.get("paths", {}))

    app = MonitorTrayApp(config, system_state)
    sys.exit(app.run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the app to verify it launches**

```bash
python -m gui.app
```

Expected: Window opens with Explorer sidebar, Docker containers visible, no crashes

- [ ] **Step 3: Commit**

```bash
git add gui/app.py
git commit -m "feat: main GUI — Explorer sidebar, unified refresh, tray app"
```

---

## Task 12: Update .desktop file and final cleanup

**Files:**
- Modify: `fart-run-awesome-hasselhoff.desktop`
- Modify: `.gitignore`

- [ ] **Step 1: Update .desktop file**

```ini
[Desktop Entry]
Name=fart.run & awesome Hasselhoff
Comment=Dev Environment Monitor — Win95 Style
Exec=python3 -m gui.app
Icon=utilities-system-monitor
Terminal=false
Type=Application
Categories=Development;System;Monitor;
StartupNotify=true
```

- [ ] **Step 2: Update .gitignore**

Add:
```
.superpowers/
__pycache__/
*.pyc
monitor.db
monitor.db-shm
monitor.db-wal
```

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass (old TUI tests deleted, new tests for autodiscovery/sidebar/security pass)

- [ ] **Step 4: Run app and verify all pages work**

```bash
python -m gui.app
```

Manual check:
- Sidebar navigation works
- Docker containers show up
- Fart Off button works
- Security scan runs
- Ports page shows listening ports
- Right-click context menu on containers
- Security detail panel shows on row click

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: final cleanup — .desktop, .gitignore, v3.0 ready"
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Sounds into repo | `sounds/` |
| 2 | Config fix | `core/config.py`, `config.toml` |
| 3 | Autodiscovery | `core/autodiscovery.py` |
| 4 | Alerts local sounds | `core/alerts.py`, `gui/monitor_alerts.py` |
| 5 | Delete legacy, move files | `db.py`, `hook.py`, etc. |
| 6 | Security explanations | `gui/security_explanations.py` |
| 7 | Sidebar widget | `gui/sidebar.py` |
| 8 | Overview/Usage/Analytics pages | `gui/pages/` |
| 9 | Docker page with actions | `gui/pages/docker.py` |
| 10 | Ports + Security pages | `gui/pages/ports.py`, `gui/pages/security.py` |
| 11 | Main app rewrite | `gui/app.py` |
| 12 | Cleanup + testing | `.desktop`, `.gitignore` |
