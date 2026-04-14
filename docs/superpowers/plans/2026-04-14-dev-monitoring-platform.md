# Dev Monitoring Platform — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend claude-monitor with a plugin-based TUI for monitoring Docker containers, ports/services, and security vulnerabilities — with fart-powered alerts.

**Architecture:** Plugin-based Textual TUI app. Core provides plugin registry, SQLite DB, alert system (notify-send + sounds), TOML config. Each feature is an independent plugin with its own tab, collector, and alert rules. Existing claude-monitor code (PostgreSQL dashboard) stays untouched — new system is a separate entry point.

**Tech Stack:** Python 3.11+, Textual, Docker SDK, psutil, pip-audit, aiosqlite, tomllib, SQLite

---

### Task 1: Project scaffolding and pyproject.toml

**Files:**
- Create: `core/__init__.py`
- Create: `core/plugin.py`
- Create: `plugins/__init__.py`
- Create: `pyproject.toml` (modify if exists, but currently there is none)
- Create: `config.toml`
- Create: `tests/__init__.py`
- Create: `tests/test_plugin.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "claude-monitor"
version = "2.0.0"
description = "Dev environment monitoring platform with plugin architecture"
requires-python = ">=3.11"
dependencies = [
    "textual>=0.40",
    "docker>=7.0",
    "psutil>=5.9",
    "aiosqlite>=0.19",
]

[project.optional-dependencies]
security = ["pip-audit>=2.6"]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]

[project.scripts]
dev-monitor = "core.app:main"
```

- [ ] **Step 2: Create config.toml with defaults**

```toml
[general]
refresh_interval = 5
sound_enabled = true
sound_dir = ""  # auto-detect from claude-nagger if empty

[alerts]
cooldown_seconds = 300
desktop_notifications = true
sound_enabled = true
quiet_hours_start = "23:00"
quiet_hours_end = "07:00"

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

- [ ] **Step 3: Create core/plugin.py — abstract base class**

```python
"""Plugin base class for dev-monitor."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite
    from textual.widget import Widget


@dataclass
class Alert:
    source: str
    severity: str  # "critical", "warning", "info"
    title: str
    message: str
    sound: str | None = None


class Plugin(abc.ABC):
    """Every plugin implements this interface."""

    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    @property
    @abc.abstractmethod
    def icon(self) -> str: ...

    @abc.abstractmethod
    async def migrate(self, db: aiosqlite.Connection) -> None:
        """Create plugin-specific tables."""

    @abc.abstractmethod
    async def collect(self, db: aiosqlite.Connection) -> None:
        """Gather metrics. Called every refresh_interval."""

    @abc.abstractmethod
    def render(self) -> Widget:
        """Return Textual widget for plugin tab."""

    @abc.abstractmethod
    async def get_alerts(self, db: aiosqlite.Connection) -> list[Alert]:
        """Check thresholds and return alerts."""
```

- [ ] **Step 4: Create core/__init__.py and plugins/__init__.py**

```python
# core/__init__.py — empty
```

```python
# plugins/__init__.py — empty
```

- [ ] **Step 5: Write failing test for Plugin ABC**

```python
# tests/test_plugin.py
"""Tests for plugin base class."""

import pytest
from core.plugin import Plugin, Alert


def test_alert_creation():
    alert = Alert(
        source="test",
        severity="critical",
        title="Test Alert",
        message="Something broke",
        sound="fart1.mp3",
    )
    assert alert.source == "test"
    assert alert.severity == "critical"
    assert alert.sound == "fart1.mp3"


def test_plugin_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Plugin()


def test_plugin_subclass_must_implement_all():
    class IncompletePlugin(Plugin):
        name = "incomplete"
        icon = "?"

    with pytest.raises(TypeError):
        IncompletePlugin()
```

- [ ] **Step 6: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_plugin.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml config.toml core/ plugins/__init__.py tests/
git commit -m "feat: project scaffolding with plugin ABC and config"
```

---

### Task 2: Config loader (core/config.py)

**Files:**
- Create: `core/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_config.py
"""Tests for config loader."""

import pytest
from pathlib import Path
from core.config import load_config


def test_load_default_config(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("""
[general]
refresh_interval = 10
sound_enabled = false

[alerts]
cooldown_seconds = 60
desktop_notifications = true
sound_enabled = false
quiet_hours_start = "22:00"
quiet_hours_end = "08:00"

[plugins.docker_monitor]
enabled = true
cpu_threshold = 90
ram_threshold = 90
alert_on_exit = false
""")
    cfg = load_config(cfg_file)
    assert cfg["general"]["refresh_interval"] == 10
    assert cfg["general"]["sound_enabled"] is False
    assert cfg["plugins"]["docker_monitor"]["cpu_threshold"] == 90


def test_load_config_missing_file():
    cfg = load_config(Path("/nonexistent/config.toml"))
    # returns defaults
    assert cfg["general"]["refresh_interval"] == 5
    assert cfg["alerts"]["cooldown_seconds"] == 300


def test_plugin_enabled_check(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("""
[plugins.docker_monitor]
enabled = false

[plugins.port_map]
enabled = true
""")
    cfg = load_config(cfg_file)
    assert cfg["plugins"]["docker_monitor"]["enabled"] is False
    assert cfg["plugins"]["port_map"]["enabled"] is True
```

- [ ] **Step 2: Run test — verify it fails**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_config.py -v`
Expected: FAIL (ImportError — module not found)

- [ ] **Step 3: Implement core/config.py**

```python
"""Config loader for dev-monitor. TOML-based with defaults."""

from __future__ import annotations

import tomllib
from pathlib import Path

DEFAULTS = {
    "general": {
        "refresh_interval": 5,
        "sound_enabled": True,
        "sound_dir": "",
    },
    "alerts": {
        "cooldown_seconds": 300,
        "desktop_notifications": True,
        "sound_enabled": True,
        "quiet_hours_start": "23:00",
        "quiet_hours_end": "07:00",
    },
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


def load_config(path: Path | None = None) -> dict:
    """Load TOML config, falling back to defaults for missing keys."""
    if path is None:
        path = Path(__file__).parent.parent / "config.toml"

    user_config = {}
    if path.exists():
        with open(path, "rb") as f:
            user_config = tomllib.load(f)

    return _deep_merge(DEFAULTS, user_config)
```

- [ ] **Step 4: Run tests — verify pass**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_config.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add core/config.py tests/test_config.py
git commit -m "feat: TOML config loader with defaults and deep merge"
```

---

### Task 3: SQLite database manager (core/db.py)

**Files:**
- Create: `core/sqlite_db.py` (named differently to not clash with existing `db.py` for PostgreSQL)
- Create: `tests/test_sqlite_db.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_sqlite_db.py
"""Tests for SQLite database manager."""

import pytest
import asyncio
from core.sqlite_db import Database


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_monitor.db"
    return Database(db_path)


@pytest.mark.asyncio
async def test_connect_and_close(db):
    await db.connect()
    assert db._conn is not None
    await db.close()


@pytest.mark.asyncio
async def test_run_migration(db):
    await db.connect()

    async def migrate(conn):
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS test_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)

    await db.run_migration(migrate)

    async with db.connection() as conn:
        cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'")
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "test_table"

    await db.close()


@pytest.mark.asyncio
async def test_connection_context_manager(db):
    await db.connect()

    async def migrate(conn):
        await conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, val TEXT)")

    await db.run_migration(migrate)

    async with db.connection() as conn:
        await conn.execute("INSERT INTO items (val) VALUES (?)", ("hello",))
        await conn.commit()

    async with db.connection() as conn:
        cursor = await conn.execute("SELECT val FROM items")
        row = await cursor.fetchone()
        assert row[0] == "hello"

    await db.close()
```

- [ ] **Step 2: Run test — verify fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_sqlite_db.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement core/sqlite_db.py**

```python
"""SQLite database manager for dev-monitor plugins."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Callable, Awaitable

import aiosqlite


class Database:
    """Async SQLite wrapper with migration support."""

    def __init__(self, path: Path | str):
        self._path = Path(path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def run_migration(self, migrate_fn: Callable[[aiosqlite.Connection], Awaitable[None]]) -> None:
        if not self._conn:
            raise RuntimeError("Database not connected")
        await migrate_fn(self._conn)
        await self._conn.commit()

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        if not self._conn:
            raise RuntimeError("Database not connected")
        yield self._conn
```

- [ ] **Step 4: Run tests — verify pass**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_sqlite_db.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add core/sqlite_db.py tests/test_sqlite_db.py
git commit -m "feat: async SQLite database manager with migrations"
```

---

### Task 4: Alert system (core/alerts.py)

**Files:**
- Create: `core/alerts.py`
- Create: `tests/test_alerts.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_alerts.py
"""Tests for alert system."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from core.alerts import AlertManager
from core.plugin import Alert


@pytest.fixture
def manager(tmp_path):
    config = {
        "alerts": {
            "cooldown_seconds": 5,
            "desktop_notifications": True,
            "sound_enabled": True,
            "quiet_hours_start": "23:00",
            "quiet_hours_end": "07:00",
        },
        "general": {
            "sound_dir": "",
        },
    }
    return AlertManager(config)


def test_deduplication(manager):
    alert = Alert(source="docker", severity="critical", title="down", message="container crashed")
    assert manager.should_fire(alert) is True
    manager.mark_fired(alert)
    assert manager.should_fire(alert) is False


def test_dedup_key(manager):
    a1 = Alert(source="docker", severity="critical", title="down", message="msg1")
    a2 = Alert(source="docker", severity="critical", title="down", message="msg2 different")
    manager.mark_fired(a1)
    # same source+title = deduplicated
    assert manager.should_fire(a2) is False


def test_different_alerts_not_deduplicated(manager):
    a1 = Alert(source="docker", severity="critical", title="down", message="msg")
    a2 = Alert(source="docker", severity="warning", title="cpu high", message="msg")
    manager.mark_fired(a1)
    assert manager.should_fire(a2) is True


def test_quiet_hours(manager):
    # 2am is within quiet hours (23:00 - 07:00)
    with patch("core.alerts.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 4, 14, 2, 0, 0)
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        assert manager.is_quiet_hours() is True

    # 12pm is NOT within quiet hours
    with patch("core.alerts.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 4, 14, 12, 0, 0)
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        assert manager.is_quiet_hours() is False


@patch("core.alerts.subprocess")
def test_send_desktop_notification(mock_subprocess, manager):
    alert = Alert(source="docker", severity="critical", title="Container down", message="nginx crashed")
    manager.send_desktop(alert)
    mock_subprocess.Popen.assert_called_once()
    args = mock_subprocess.Popen.call_args[0][0]
    assert args[0] == "notify-send"
    assert "Container down" in args


@patch("core.alerts.subprocess")
def test_no_sound_in_quiet_hours(mock_subprocess, manager):
    with patch.object(manager, "is_quiet_hours", return_value=True):
        alert = Alert(source="docker", severity="critical", title="down", message="msg", sound="fart1.mp3")
        manager.play_sound(alert)
        mock_subprocess.Popen.assert_not_called()
```

- [ ] **Step 2: Run test — verify fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_alerts.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement core/alerts.py**

```python
"""Centralized alert manager — notify-send + fart sounds."""

from __future__ import annotations

import subprocess
import time
from datetime import datetime
from pathlib import Path

from core.plugin import Alert

# Sound severity mapping
SEVERITY_SOUNDS = {
    "critical": "fart3.mp3",   # гучний пердіж
    "warning": "fart1.mp3",    # тихий пердіж
    "info": "fart5.mp3",       # короткий пук
}

URGENCY_MAP = {
    "critical": "critical",
    "warning": "normal",
    "info": "low",
}


def _find_sound_dir() -> Path | None:
    """Auto-detect sound directory from claude-nagger."""
    candidates = [
        Path.home() / "claude-nagger" / "sounds" / "farts",
        Path.home() / "bin" / "farts",
    ]
    for d in candidates:
        if d.is_dir():
            return d
    return None


class AlertManager:
    """Handles deduplication, delivery, and sound for alerts."""

    def __init__(self, config: dict):
        self._config = config
        self._fired: dict[str, float] = {}  # dedup_key -> timestamp
        self._cooldown = config["alerts"]["cooldown_seconds"]

        sound_dir = config["general"].get("sound_dir", "")
        self._sound_dir = Path(sound_dir) if sound_dir else _find_sound_dir()

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
        start_str = self._config["alerts"]["quiet_hours_start"]
        end_str = self._config["alerts"]["quiet_hours_end"]
        start_h, start_m = map(int, start_str.split(":"))
        end_h, end_m = map(int, end_str.split(":"))
        current = now.hour * 60 + now.minute
        start = start_h * 60 + start_m
        end = end_h * 60 + end_m
        if start > end:  # wraps midnight (e.g. 23:00 - 07:00)
            return current >= start or current < end
        return start <= current < end

    def send_desktop(self, alert: Alert) -> None:
        if not self._config["alerts"]["desktop_notifications"]:
            return
        urgency = URGENCY_MAP.get(alert.severity, "normal")
        try:
            subprocess.Popen(
                ["notify-send", "-u", urgency, f"[{alert.source}] {alert.title}", alert.message],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    def play_sound(self, alert: Alert) -> None:
        if not self._config["alerts"]["sound_enabled"]:
            return
        if self.is_quiet_hours():
            return
        if not self._sound_dir:
            return
        sound_file = alert.sound or SEVERITY_SOUNDS.get(alert.severity)
        if not sound_file:
            return
        sound_path = self._sound_dir / sound_file
        if not sound_path.exists():
            return
        try:
            subprocess.Popen(
                ["paplay", str(sound_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            try:
                subprocess.Popen(
                    ["aplay", str(sound_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                pass

    def process(self, alert: Alert) -> bool:
        """Process an alert: dedup check, send notifications. Returns True if fired."""
        if not self.should_fire(alert):
            return False
        self.mark_fired(alert)
        self.send_desktop(alert)
        self.play_sound(alert)
        return True
```

- [ ] **Step 4: Run tests — verify pass**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_alerts.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add core/alerts.py tests/test_alerts.py
git commit -m "feat: alert manager with notify-send, fart sounds, and deduplication"
```

---

### Task 5: Textual App shell with plugin registry (core/app.py)

**Files:**
- Create: `core/app.py`
- Create: `tests/test_app.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_app.py
"""Tests for main app plugin registration."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from core.app import DevMonitorApp


def test_app_creates():
    app = DevMonitorApp(config_path=None, db_path=":memory:")
    assert app is not None


def test_register_plugin():
    app = DevMonitorApp(config_path=None, db_path=":memory:")
    mock_plugin = MagicMock()
    mock_plugin.name = "test"
    mock_plugin.icon = "T"
    app.register_plugin(mock_plugin)
    assert "test" in app.plugins
```

- [ ] **Step 2: Run test — verify fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_app.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement core/app.py**

```python
"""Main Textual application with plugin registry."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, TabbedContent, TabPane, Static

from core.config import load_config
from core.sqlite_db import Database
from core.alerts import AlertManager
from core.plugin import Plugin


class DevMonitorApp(App):
    """Dev environment monitoring dashboard."""

    CSS = """
    Screen {
        background: $surface;
    }
    TabbedContent {
        height: 1fr;
    }
    .status-bar {
        dock: bottom;
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self, config_path: Path | str | None = None, db_path: Path | str = "monitor.db"):
        super().__init__()
        if config_path:
            self._config = load_config(Path(config_path))
        else:
            self._config = load_config()
        self._db = Database(db_path)
        self._alert_manager = AlertManager(self._config)
        self.plugins: dict[str, Plugin] = {}
        self._refresh_interval = self._config["general"]["refresh_interval"]

    def register_plugin(self, plugin: Plugin) -> None:
        self.plugins[plugin.name] = plugin

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent():
            for plugin in self.plugins.values():
                with TabPane(f"{plugin.icon} {plugin.name}", id=f"tab-{plugin.name}"):
                    yield plugin.render()
        yield Static("dev-monitor | q: quit | r: refresh", classes="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        await self._db.connect()
        for plugin in self.plugins.values():
            await self._db.run_migration(plugin.migrate)
        self.set_interval(self._refresh_interval, self._collect_all)

    async def _collect_all(self) -> None:
        for plugin in self.plugins.values():
            try:
                async with self._db.connection() as conn:
                    await plugin.collect(conn)
                    alerts = await plugin.get_alerts(conn)
                    for alert in alerts:
                        self._alert_manager.process(alert)
            except Exception as e:
                self.notify(f"Plugin {plugin.name} error: {e}", severity="error")

    async def action_refresh(self) -> None:
        await self._collect_all()
        self.notify("Refreshed", severity="information")

    async def on_unmount(self) -> None:
        await self._db.close()


def main():
    """Entry point. Discovers and registers enabled plugins, then runs."""
    from plugins.docker_monitor.plugin import DockerMonitorPlugin
    from plugins.port_map.plugin import PortMapPlugin
    from plugins.security_scan.plugin import SecurityScanPlugin

    app = DevMonitorApp()
    config = app._config

    plugin_map = {
        "docker_monitor": DockerMonitorPlugin,
        "port_map": PortMapPlugin,
        "security_scan": SecurityScanPlugin,
    }

    for name, cls in plugin_map.items():
        plugin_cfg = config["plugins"].get(name, {})
        if plugin_cfg.get("enabled", True):
            app.register_plugin(cls(config))

    app.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — verify pass**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_app.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app.py tests/test_app.py
git commit -m "feat: Textual app shell with plugin registry and refresh loop"
```

---

### Task 6: Docker Monitor Plugin — collector

**Files:**
- Create: `plugins/docker_monitor/__init__.py`
- Create: `plugins/docker_monitor/plugin.py`
- Create: `plugins/docker_monitor/collector.py`
- Create: `tests/test_docker_collector.py`

- [ ] **Step 1: Write failing test for collector**

```python
# tests/test_docker_collector.py
"""Tests for Docker metrics collector."""

import pytest
from unittest.mock import MagicMock, patch
from plugins.docker_monitor.collector import collect_containers


def _mock_container(name, status, cpu_percent=5.0, mem_usage=100_000_000, mem_limit=500_000_000, ports=None, health="healthy", restart_count=0, exit_code=0):
    """Create a mock Docker container."""
    container = MagicMock()
    container.name = name
    container.status = status
    container.image.tags = ["postgres:16"]
    container.attrs = {
        "State": {
            "Health": {"Status": health} if health else {},
            "ExitCode": exit_code,
        },
        "RestartCount": restart_count,
        "Created": "2026-04-14T10:00:00Z",
        "HostConfig": {
            "Privileged": False,
            "Binds": [],
            "NetworkMode": "bridge",
        },
        "Config": {"User": "postgres"},
    }
    container.ports = ports or {"5432/tcp": [{"HostPort": "5432"}]}

    if status == "running":
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 500_000_000},
                "system_cpu_usage": 10_000_000_000,
                "online_cpus": 4,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 400_000_000},
                "system_cpu_usage": 9_000_000_000,
            },
            "memory_stats": {
                "usage": mem_usage,
                "limit": mem_limit,
            },
            "networks": {
                "eth0": {"rx_bytes": 1024, "tx_bytes": 2048}
            },
        }
        container.stats.return_value = stats
    else:
        container.stats.side_effect = Exception("not running")

    return container


def test_collect_running_container():
    container = _mock_container("postgres", "running")
    result = collect_containers([container])
    assert len(result) == 1
    info = result[0]
    assert info["name"] == "postgres"
    assert info["status"] == "running"
    assert "cpu_percent" in info
    assert "mem_usage" in info
    assert info["mem_usage"] == 100_000_000


def test_collect_stopped_container():
    container = _mock_container("nginx", "exited", exit_code=137)
    result = collect_containers([container])
    assert len(result) == 1
    assert result[0]["status"] == "exited"
    assert result[0]["cpu_percent"] == 0.0


def test_collect_ports():
    container = _mock_container("web", "running", ports={"8080/tcp": [{"HostPort": "8080"}], "443/tcp": [{"HostPort": "443"}]})
    result = collect_containers([container])
    assert len(result[0]["ports"]) == 2
```

- [ ] **Step 2: Run test — verify fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_docker_collector.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement collector**

```python
# plugins/docker_monitor/__init__.py — empty
```

```python
# plugins/docker_monitor/collector.py
"""Docker container metrics collector."""

from __future__ import annotations


def _calc_cpu_percent(stats: dict) -> float:
    """Calculate CPU usage percentage from Docker stats."""
    cpu = stats.get("cpu_stats", {})
    precpu = stats.get("precpu_stats", {})
    cpu_delta = cpu.get("cpu_usage", {}).get("total_usage", 0) - precpu.get("cpu_usage", {}).get("total_usage", 0)
    sys_delta = cpu.get("system_cpu_usage", 0) - precpu.get("system_cpu_usage", 0)
    online_cpus = cpu.get("online_cpus", 1)
    if sys_delta > 0 and cpu_delta >= 0:
        return round((cpu_delta / sys_delta) * online_cpus * 100, 1)
    return 0.0


def _parse_ports(ports_dict: dict) -> list[dict]:
    """Parse Docker port bindings to a list of {container_port, host_port, protocol}."""
    result = []
    if not ports_dict:
        return result
    for container_port_proto, bindings in ports_dict.items():
        if not bindings:
            continue
        parts = container_port_proto.split("/")
        container_port = parts[0]
        protocol = parts[1] if len(parts) > 1 else "tcp"
        for binding in bindings:
            result.append({
                "container_port": container_port,
                "host_port": binding.get("HostPort", ""),
                "protocol": protocol,
            })
    return result


def collect_containers(containers: list) -> list[dict]:
    """Collect metrics from a list of Docker container objects."""
    results = []
    for c in containers:
        state = c.attrs.get("State", {})
        health_obj = state.get("Health", {})
        health = health_obj.get("Status") if health_obj else None

        info = {
            "name": c.name,
            "status": c.status,
            "image": c.image.tags[0] if c.image.tags else "unknown",
            "created": c.attrs.get("Created", ""),
            "health": health,
            "exit_code": state.get("ExitCode", 0),
            "restart_count": c.attrs.get("RestartCount", 0),
            "ports": _parse_ports(c.ports),
            "cpu_percent": 0.0,
            "mem_usage": 0,
            "mem_limit": 0,
            "net_rx": 0,
            "net_tx": 0,
            # security-relevant fields
            "privileged": c.attrs.get("HostConfig", {}).get("Privileged", False),
            "binds": c.attrs.get("HostConfig", {}).get("Binds") or [],
            "network_mode": c.attrs.get("HostConfig", {}).get("NetworkMode", ""),
            "user": c.attrs.get("Config", {}).get("User", ""),
        }

        if c.status == "running":
            try:
                stats = c.stats(stream=False)
                info["cpu_percent"] = _calc_cpu_percent(stats)
                mem = stats.get("memory_stats", {})
                info["mem_usage"] = mem.get("usage", 0)
                info["mem_limit"] = mem.get("limit", 0)
                networks = stats.get("networks", {})
                for iface_stats in networks.values():
                    info["net_rx"] += iface_stats.get("rx_bytes", 0)
                    info["net_tx"] += iface_stats.get("tx_bytes", 0)
            except Exception:
                pass

        results.append(info)
    return results
```

- [ ] **Step 4: Run tests — verify pass**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_docker_collector.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add plugins/docker_monitor/ tests/test_docker_collector.py
git commit -m "feat: Docker container metrics collector"
```

---

### Task 7: Docker Monitor Plugin — TUI widget and plugin class

**Files:**
- Create: `plugins/docker_monitor/widget.py`
- Modify: `plugins/docker_monitor/plugin.py`
- Create: `tests/test_docker_plugin.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_docker_plugin.py
"""Tests for Docker Monitor plugin."""

import pytest
import aiosqlite
from plugins.docker_monitor.plugin import DockerMonitorPlugin
from core.config import DEFAULTS


@pytest.fixture
def plugin():
    return DockerMonitorPlugin(DEFAULTS)


@pytest.mark.asyncio
async def test_migrate_creates_tables(plugin, tmp_path):
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(db_path) as conn:
        await plugin.migrate(conn)
        await conn.commit()

        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        assert "docker_containers" in tables
        assert "docker_metrics" in tables
        assert "docker_events" in tables


@pytest.mark.asyncio
async def test_get_alerts_cpu_threshold(plugin, tmp_path):
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(db_path) as conn:
        await plugin.migrate(conn)
        await conn.commit()

        # Insert a container with high CPU
        await conn.execute(
            "INSERT INTO docker_containers (container_id, name, status, cpu_percent, mem_usage, mem_limit, image) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("abc123", "worker", "running", 95.0, 500_000_000, 1_000_000_000, "app:latest"),
        )
        await conn.commit()

        alerts = await plugin.get_alerts(conn)
        cpu_alerts = [a for a in alerts if "CPU" in a.title]
        assert len(cpu_alerts) == 1
        assert cpu_alerts[0].severity == "warning"


@pytest.mark.asyncio
async def test_get_alerts_container_exited(plugin, tmp_path):
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(db_path) as conn:
        await plugin.migrate(conn)
        await conn.commit()

        await conn.execute(
            "INSERT INTO docker_containers (container_id, name, status, cpu_percent, mem_usage, mem_limit, image, exit_code) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("def456", "nginx", "exited", 0, 0, 0, "nginx:latest", 137),
        )
        await conn.commit()

        alerts = await plugin.get_alerts(conn)
        exit_alerts = [a for a in alerts if "exited" in a.title.lower() or "crashed" in a.title.lower()]
        assert len(exit_alerts) >= 1
        assert exit_alerts[0].severity == "critical"
```

- [ ] **Step 2: Run test — verify fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_docker_plugin.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement widget**

```python
# plugins/docker_monitor/widget.py
"""Docker Monitor TUI widget."""

from __future__ import annotations

from textual.widgets import DataTable, Static
from textual.containers import Vertical


def fmt_bytes(n: int) -> str:
    if n >= 1_073_741_824:
        return f"{n / 1_073_741_824:.1f}GB"
    if n >= 1_048_576:
        return f"{n / 1_048_576:.0f}MB"
    if n >= 1024:
        return f"{n / 1024:.0f}KB"
    return f"{n}B"


class DockerTable(DataTable):
    """Table showing Docker container status."""

    def on_mount(self) -> None:
        self.add_columns("", "NAME", "STATUS", "CPU%", "RAM", "PORTS", "HEALTH")
        self.cursor_type = "row"

    def update_data(self, containers: list[dict]) -> None:
        self.clear()
        for c in containers:
            status = c.get("status", "unknown")
            if status == "running":
                icon = "[green]●[/]"
            elif status == "exited":
                icon = "[dim]○[/]"
            else:
                icon = "[yellow]◉[/]"

            cpu = c.get("cpu_percent", 0)
            cpu_str = f"{cpu:.1f}%" if status == "running" else "—"
            if cpu > 80:
                cpu_str = f"[red]{cpu_str}[/]"
            elif cpu > 50:
                cpu_str = f"[yellow]{cpu_str}[/]"

            mem = fmt_bytes(c.get("mem_usage", 0)) if status == "running" else "—"

            ports_list = c.get("ports", [])
            ports_str = ", ".join(f"{p['host_port']}→{p['container_port']}" for p in ports_list[:3])
            if len(ports_list) > 3:
                ports_str += f" +{len(ports_list) - 3}"

            health = c.get("health") or "—"

            self.add_row(icon, c.get("name", "?"), status, cpu_str, mem, ports_str, health)


class EventsLog(Static):
    """Recent Docker events display."""

    def update_events(self, events: list[dict]) -> None:
        lines = []
        for e in events[-10:]:
            ts = e.get("timestamp", "")[:5] if e.get("timestamp") else ""
            lines.append(f"{ts}  {e.get('message', '')}")
        self.update("\n".join(lines) if lines else "No recent events")


class DockerMonitorWidget(Vertical):
    """Combined Docker monitoring widget."""

    def compose(self):
        yield DockerTable(id="docker-table")
        yield Static("─── Events ───", classes="section-header")
        yield EventsLog(id="docker-events")
```

- [ ] **Step 4: Implement plugin class**

```python
# plugins/docker_monitor/plugin.py
"""Docker Monitor plugin — tracks containers, CPU, RAM, ports, health."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import docker

from core.plugin import Plugin, Alert
from plugins.docker_monitor.collector import collect_containers
from plugins.docker_monitor.widget import DockerMonitorWidget

if TYPE_CHECKING:
    import aiosqlite
    from textual.widget import Widget


class DockerMonitorPlugin(Plugin):

    name = "Docker"
    icon = "🐳"

    def __init__(self, config: dict):
        self._config = config.get("plugins", {}).get("docker_monitor", {})
        self._cpu_threshold = self._config.get("cpu_threshold", 80)
        self._ram_threshold = self._config.get("ram_threshold", 85)
        self._alert_on_exit = self._config.get("alert_on_exit", True)
        self._widget: DockerMonitorWidget | None = None
        try:
            self._client = docker.from_env()
        except docker.errors.DockerException:
            self._client = None

    async def migrate(self, db: aiosqlite.Connection) -> None:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS docker_containers (
                container_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                image TEXT,
                status TEXT,
                cpu_percent REAL DEFAULT 0,
                mem_usage INTEGER DEFAULT 0,
                mem_limit INTEGER DEFAULT 0,
                health TEXT,
                exit_code INTEGER DEFAULT 0,
                restart_count INTEGER DEFAULT 0,
                ports TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS docker_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                container_id TEXT NOT NULL,
                cpu_percent REAL,
                mem_usage INTEGER,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (container_id) REFERENCES docker_containers(container_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS docker_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                container_name TEXT,
                event_type TEXT,
                message TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

    async def collect(self, db: aiosqlite.Connection) -> None:
        if not self._client:
            return

        containers = self._client.containers.list(all=True)
        infos = collect_containers(containers)
        now = datetime.now(timezone.utc).isoformat()

        for info in infos:
            c_id = info["name"]  # use name as stable ID
            await db.execute("""
                INSERT INTO docker_containers
                    (container_id, name, image, status, cpu_percent, mem_usage, mem_limit, health, exit_code, restart_count, ports, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(container_id) DO UPDATE SET
                    status=excluded.status, cpu_percent=excluded.cpu_percent,
                    mem_usage=excluded.mem_usage, mem_limit=excluded.mem_limit,
                    health=excluded.health, exit_code=excluded.exit_code,
                    restart_count=excluded.restart_count, ports=excluded.ports,
                    updated_at=excluded.updated_at
            """, (
                c_id, info["name"], info["image"], info["status"],
                info["cpu_percent"], info["mem_usage"], info["mem_limit"],
                info["health"], info["exit_code"], info["restart_count"],
                str(info["ports"]), now,
            ))

            if info["status"] == "running":
                await db.execute(
                    "INSERT INTO docker_metrics (container_id, cpu_percent, mem_usage, timestamp) VALUES (?, ?, ?, ?)",
                    (c_id, info["cpu_percent"], info["mem_usage"], now),
                )

        await db.commit()

        # Cleanup old metrics (keep 24h)
        await db.execute("DELETE FROM docker_metrics WHERE timestamp < datetime('now', '-1 day')")
        await db.commit()

        # Update widget
        if self._widget:
            table = self._widget.query_one("#docker-table", None)
            if table:
                table.update_data(infos)

    def render(self) -> Widget:
        self._widget = DockerMonitorWidget()
        return self._widget

    async def get_alerts(self, db: aiosqlite.Connection) -> list[Alert]:
        alerts = []
        cursor = await db.execute("SELECT * FROM docker_containers")
        rows = await cursor.fetchall()
        columns = [d[0] for d in cursor.description]

        for row in rows:
            c = dict(zip(columns, row))

            # Container crashed/exited
            if c["status"] == "exited" and self._alert_on_exit:
                alerts.append(Alert(
                    source="docker",
                    severity="critical",
                    title=f"{c['name']} crashed (exit {c['exit_code']})",
                    message=f"Container {c['name']} exited with code {c['exit_code']}",
                    sound="fart3.mp3",
                ))

            if c["status"] != "running":
                continue

            # CPU threshold
            if c["cpu_percent"] > self._cpu_threshold:
                alerts.append(Alert(
                    source="docker",
                    severity="warning",
                    title=f"{c['name']} CPU {c['cpu_percent']:.0f}%",
                    message=f"Container {c['name']} CPU usage at {c['cpu_percent']:.1f}% (threshold: {self._cpu_threshold}%)",
                    sound="fart1.mp3",
                ))

            # RAM threshold
            if c["mem_limit"] > 0:
                ram_pct = (c["mem_usage"] / c["mem_limit"]) * 100
                if ram_pct > self._ram_threshold:
                    alerts.append(Alert(
                        source="docker",
                        severity="critical",
                        title=f"{c['name']} RAM {ram_pct:.0f}%",
                        message=f"Container {c['name']} RAM at {ram_pct:.1f}% (threshold: {self._ram_threshold}%)",
                        sound="fart3.mp3",
                    ))

            # Unhealthy
            if c["health"] == "unhealthy":
                alerts.append(Alert(
                    source="docker",
                    severity="warning",
                    title=f"{c['name']} unhealthy",
                    message=f"Container {c['name']} health check is failing",
                    sound="fart1.mp3",
                ))

            # Restart loop (3+ restarts)
            if c["restart_count"] >= 3:
                alerts.append(Alert(
                    source="docker",
                    severity="critical",
                    title=f"{c['name']} restart loop ({c['restart_count']}x)",
                    message=f"Container {c['name']} has restarted {c['restart_count']} times",
                    sound="fart3.mp3",
                ))

        return alerts
```

- [ ] **Step 5: Run tests — verify pass**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_docker_plugin.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add plugins/docker_monitor/ tests/test_docker_plugin.py
git commit -m "feat: Docker Monitor plugin with TUI widget and alerts"
```

---

### Task 8: Port/Service Map Plugin

**Files:**
- Create: `plugins/port_map/__init__.py`
- Create: `plugins/port_map/plugin.py`
- Create: `plugins/port_map/collector.py`
- Create: `plugins/port_map/widget.py`
- Create: `tests/test_port_map.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_port_map.py
"""Tests for Port/Service Map plugin."""

import pytest
from unittest.mock import patch, MagicMock
from collections import namedtuple
from plugins.port_map.collector import collect_ports


# Mock psutil connection
SConn = namedtuple("SConn", ["fd", "family", "type", "laddr", "raddr", "status", "pid"])
SAddr = namedtuple("SAddr", ["ip", "port"])


def _mock_process(pid, name, cwd="/home/user/project"):
    proc = MagicMock()
    proc.pid = pid
    proc.info = {"pid": pid, "name": name}
    proc.name.return_value = name
    proc.cwd.return_value = cwd
    proc.cmdline.return_value = [name]
    return proc


@patch("plugins.port_map.collector.psutil")
def test_collect_listening_ports(mock_psutil):
    mock_psutil.net_connections.return_value = [
        SConn(fd=3, family=2, type=1, laddr=SAddr("0.0.0.0", 5432), raddr=(), status="LISTEN", pid=100),
        SConn(fd=4, family=2, type=1, laddr=SAddr("127.0.0.1", 3000), raddr=(), status="LISTEN", pid=200),
    ]

    proc_100 = _mock_process(100, "postgres")
    proc_200 = _mock_process(200, "node", "/home/user/cafe")

    mock_psutil.Process.side_effect = lambda pid: {100: proc_100, 200: proc_200}[pid]

    result = collect_ports()
    assert len(result) == 2
    assert result[0]["port"] == 5432
    assert result[0]["process"] == "postgres"
    assert result[1]["port"] == 3000


@patch("plugins.port_map.collector.psutil")
def test_detect_port_conflict(mock_psutil):
    mock_psutil.net_connections.return_value = [
        SConn(fd=3, family=2, type=1, laddr=SAddr("0.0.0.0", 3000), raddr=(), status="LISTEN", pid=100),
        SConn(fd=4, family=2, type=1, laddr=SAddr("0.0.0.0", 3000), raddr=(), status="LISTEN", pid=200),
    ]
    proc_100 = _mock_process(100, "node", "/home/user/cafe")
    proc_200 = _mock_process(200, "node", "/home/user/nexelin")
    mock_psutil.Process.side_effect = lambda pid: {100: proc_100, 200: proc_200}[pid]

    result = collect_ports()
    conflicts = [p for p in result if p.get("conflict")]
    assert len(conflicts) >= 1


@patch("plugins.port_map.collector.psutil")
def test_project_detection_from_cwd(mock_psutil):
    mock_psutil.net_connections.return_value = [
        SConn(fd=3, family=2, type=1, laddr=SAddr("0.0.0.0", 8000), raddr=(), status="LISTEN", pid=100),
    ]
    proc = _mock_process(100, "uvicorn", "/home/dchuprina/sloth-all")
    mock_psutil.Process.side_effect = lambda pid: proc

    result = collect_ports()
    assert result[0]["project"] == "sloth-all"
```

- [ ] **Step 2: Run test — verify fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_port_map.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement collector**

```python
# plugins/port_map/__init__.py — empty
```

```python
# plugins/port_map/collector.py
"""Port and service collector using psutil."""

from __future__ import annotations

import psutil
from pathlib import Path


def _detect_project(cwd: str) -> str:
    """Extract project name from process working directory."""
    path = Path(cwd)
    home = Path.home()
    if str(path).startswith(str(home)):
        parts = path.relative_to(home).parts
        if parts:
            return parts[0]
    return path.name


def collect_ports() -> list[dict]:
    """Collect all listening ports with process info."""
    connections = psutil.net_connections(kind="inet")
    listening = [c for c in connections if c.status == "LISTEN" and c.pid]

    # Group by port to detect conflicts
    port_pids: dict[int, list] = {}
    for conn in listening:
        port = conn.laddr.port
        port_pids.setdefault(port, []).append(conn)

    results = []
    seen = set()

    for conn in listening:
        port = conn.laddr.port
        pid = conn.pid
        key = (port, pid)
        if key in seen:
            continue
        seen.add(key)

        ip = conn.laddr.ip
        protocol = "TCP" if conn.type == 1 else "UDP"

        process_name = ""
        project = ""
        cwd = ""
        try:
            proc = psutil.Process(pid)
            process_name = proc.name()
            cwd = proc.cwd()
            project = _detect_project(cwd)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        has_conflict = len(port_pids.get(port, [])) > 1

        results.append({
            "port": port,
            "ip": ip,
            "protocol": protocol,
            "pid": pid,
            "process": process_name,
            "project": project,
            "cwd": cwd,
            "conflict": has_conflict,
            "exposed": ip == "0.0.0.0",
        })

    results.sort(key=lambda x: x["port"])
    return results
```

- [ ] **Step 4: Run tests — verify pass**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_port_map.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Implement widget**

```python
# plugins/port_map/widget.py
"""Port Map TUI widget."""

from __future__ import annotations

from textual.widgets import DataTable, Static
from textual.containers import Vertical


class PortTable(DataTable):
    """Table showing listening ports and services."""

    def on_mount(self) -> None:
        self.add_columns("PORT", "PROTO", "PROCESS", "CONTAINER", "PROJECT", "STATUS")
        self.cursor_type = "row"

    def update_data(self, ports: list[dict], docker_ports: dict[int, str] | None = None) -> None:
        docker_ports = docker_ports or {}
        self.clear()
        for p in ports:
            port = str(p["port"])
            container = docker_ports.get(p["port"], "—")

            if p["conflict"]:
                status = "[red]CONFLICT[/]"
                port = f"[red]⚠ {port}[/]"
            else:
                status = "[green]● UP[/]"

            self.add_row(
                port,
                p["protocol"],
                p["process"],
                container,
                p.get("project", ""),
                status,
            )


class PortSummary(Static):
    """Summary statistics for ports."""

    def update_summary(self, ports: list[dict]) -> None:
        total = len(ports)
        conflicts = sum(1 for p in ports if p["conflict"])
        exposed = sum(1 for p in ports if p.get("exposed"))
        self.update(f"{total} ports listening | {conflicts} conflicts | {exposed} exposed (0.0.0.0)")


class PortMapWidget(Vertical):
    """Combined port map widget."""

    def compose(self):
        yield PortTable(id="port-table")
        yield Static("─── Summary ───", classes="section-header")
        yield PortSummary(id="port-summary")
```

- [ ] **Step 6: Implement plugin class**

```python
# plugins/port_map/plugin.py
"""Port/Service Map plugin — tracks listening ports, conflicts, services."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from core.plugin import Plugin, Alert
from plugins.port_map.collector import collect_ports
from plugins.port_map.widget import PortMapWidget

if TYPE_CHECKING:
    import aiosqlite
    from textual.widget import Widget


class PortMapPlugin(Plugin):

    name = "Ports"
    icon = "🔌"

    def __init__(self, config: dict):
        self._config = config.get("plugins", {}).get("port_map", {})
        self._widget: PortMapWidget | None = None

    async def migrate(self, db: aiosqlite.Connection) -> None:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS port_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                port INTEGER NOT NULL,
                ip TEXT,
                protocol TEXT DEFAULT 'TCP',
                pid INTEGER,
                process TEXT,
                project TEXT,
                container_name TEXT,
                conflict INTEGER DEFAULT 0,
                exposed INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(port, pid)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS port_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                port INTEGER NOT NULL,
                process TEXT,
                event TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

    async def collect(self, db: aiosqlite.Connection) -> None:
        ports = collect_ports()
        now = datetime.now(timezone.utc).isoformat()

        # Get previous state for diff
        cursor = await db.execute("SELECT port, pid, process FROM port_services")
        old_ports = {(row[0], row[1]): row[2] for row in await cursor.fetchall()}

        # Clear and re-insert (snapshot approach)
        await db.execute("DELETE FROM port_services")
        for p in ports:
            await db.execute("""
                INSERT INTO port_services (port, ip, protocol, pid, process, project, conflict, exposed, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (p["port"], p["ip"], p["protocol"], p["pid"], p["process"],
                  p.get("project", ""), int(p["conflict"]), int(p.get("exposed", False)), now))

        # Log events for new/disappeared ports
        new_keys = {(p["port"], p["pid"]) for p in ports}
        old_keys = set(old_ports.keys())

        for key in new_keys - old_keys:
            port, pid = key
            proc = next((p["process"] for p in ports if p["port"] == port and p["pid"] == pid), "?")
            await db.execute(
                "INSERT INTO port_history (port, process, event, timestamp) VALUES (?, ?, 'up', ?)",
                (port, proc, now),
            )

        for key in old_keys - new_keys:
            port, pid = key
            proc = old_ports.get(key, "?")
            await db.execute(
                "INSERT INTO port_history (port, process, event, timestamp) VALUES (?, ?, 'down', ?)",
                (port, proc, now),
            )

        await db.commit()

        # Update widget
        if self._widget:
            table = self._widget.query_one("#port-table", None)
            if table:
                table.update_data(ports)
            summary = self._widget.query_one("#port-summary", None)
            if summary:
                summary.update_summary(ports)

    def render(self) -> Widget:
        self._widget = PortMapWidget()
        return self._widget

    async def get_alerts(self, db: aiosqlite.Connection) -> list[Alert]:
        alerts = []
        cursor = await db.execute("SELECT port, process, project, conflict, exposed FROM port_services WHERE conflict = 1")
        for row in await cursor.fetchall():
            port, process, project, _, _ = row
            alerts.append(Alert(
                source="ports",
                severity="warning",
                title=f"Port {port} conflict",
                message=f"Port {port} used by multiple processes ({process}, project: {project})",
                sound="fart1.mp3",
            ))
        return alerts
```

- [ ] **Step 7: Commit**

```bash
git add plugins/port_map/ tests/test_port_map.py
git commit -m "feat: Port/Service Map plugin with conflict detection"
```

---

### Task 9: Security Scan Plugin — scanners

**Files:**
- Create: `plugins/security_scan/__init__.py`
- Create: `plugins/security_scan/scanners.py`
- Create: `tests/test_security_scanners.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_security_scanners.py
"""Tests for security scanners."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from plugins.security_scan.scanners import (
    scan_docker_security,
    scan_env_in_git,
    scan_file_permissions,
    scan_exposed_ports,
    Finding,
)


def test_finding_creation():
    f = Finding(
        type="docker",
        severity="critical",
        description="Container runs as root",
        source="postgres",
    )
    assert f.severity == "critical"
    assert f.source == "postgres"


def test_docker_privileged_detection():
    container_info = {
        "name": "risky",
        "privileged": True,
        "binds": [],
        "network_mode": "bridge",
        "user": "",
        "image": "app:latest",
    }
    findings = scan_docker_security([container_info])
    privs = [f for f in findings if "privileged" in f.description.lower()]
    assert len(privs) == 1
    assert privs[0].severity == "critical"


def test_docker_socket_mounted():
    container_info = {
        "name": "dind",
        "privileged": False,
        "binds": ["/var/run/docker.sock:/var/run/docker.sock"],
        "network_mode": "bridge",
        "user": "",
        "image": "app:latest",
    }
    findings = scan_docker_security([container_info])
    socket_findings = [f for f in findings if "docker.sock" in f.description.lower()]
    assert len(socket_findings) == 1


def test_docker_root_user():
    container_info = {
        "name": "rootapp",
        "privileged": False,
        "binds": [],
        "network_mode": "bridge",
        "user": "",
        "image": "app:latest",
    }
    findings = scan_docker_security([container_info])
    root_findings = [f for f in findings if "root" in f.description.lower()]
    assert len(root_findings) == 1
    assert root_findings[0].severity == "high"


def test_docker_latest_tag():
    container_info = {
        "name": "unstable",
        "privileged": False,
        "binds": [],
        "network_mode": "bridge",
        "user": "app",
        "image": "redis:latest",
    }
    findings = scan_docker_security([container_info])
    latest_findings = [f for f in findings if ":latest" in f.description]
    assert len(latest_findings) == 1
    assert latest_findings[0].severity == "medium"


def test_env_in_git(tmp_path):
    # Create a fake git repo with .env tracked
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=password123")

    with patch("plugins.security_scan.scanners.subprocess") as mock_sub:
        mock_sub.run.return_value = MagicMock(
            returncode=0,
            stdout=".env\nconfig/.env.prod\n",
        )
        findings = scan_env_in_git([tmp_path])
        assert len(findings) >= 1
        assert findings[0].severity == "critical"


def test_exposed_ports():
    ports = [
        {"port": 5432, "ip": "0.0.0.0", "process": "postgres", "project": ""},
        {"port": 3000, "ip": "127.0.0.1", "process": "node", "project": "cafe"},
    ]
    findings = scan_exposed_ports(ports)
    assert len(findings) == 1
    assert "0.0.0.0" in findings[0].description
```

- [ ] **Step 2: Run test — verify fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_security_scanners.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement scanners**

```python
# plugins/security_scan/__init__.py — empty
```

```python
# plugins/security_scan/scanners.py
"""Security scanners for dev environment."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Finding:
    type: str        # "docker", "config", "deps", "network"
    severity: str    # "critical", "high", "medium", "low"
    description: str
    source: str      # container name, file path, package name


def scan_docker_security(container_infos: list[dict]) -> list[Finding]:
    """Scan Docker containers for security issues."""
    findings = []
    for c in container_infos:
        name = c["name"]

        if c.get("privileged"):
            findings.append(Finding("docker", "critical", f"{name}: runs in privileged mode", name))

        for bind in c.get("binds") or []:
            if "docker.sock" in bind:
                findings.append(Finding("docker", "critical", f"{name}: docker.sock mounted inside container", name))

        if c.get("network_mode") == "host":
            findings.append(Finding("docker", "high", f"{name}: uses host network mode", name))

        if not c.get("user"):
            findings.append(Finding("docker", "high", f"{name}: runs as root (no USER set)", name))

        image = c.get("image", "")
        if image.endswith(":latest") or ":" not in image:
            findings.append(Finding("docker", "medium", f"{name}: uses :latest tag ({image})", name))

    return findings


def scan_env_in_git(scan_paths: list[Path]) -> list[Finding]:
    """Check for .env files tracked in git repos."""
    findings = []
    for path in scan_paths:
        if not (path / ".git").exists():
            continue
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "ls-files"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                continue
            for tracked_file in result.stdout.strip().split("\n"):
                tracked_file = tracked_file.strip()
                if not tracked_file:
                    continue
                name = Path(tracked_file).name
                if name.startswith(".env"):
                    findings.append(Finding(
                        "config", "critical",
                        f".env file committed in git: {tracked_file}",
                        str(path / tracked_file),
                    ))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return findings


def scan_file_permissions(scan_paths: list[Path]) -> list[Finding]:
    """Check for files with overly broad permissions."""
    findings = []
    sensitive_patterns = [".env", "credentials", "secret", ".pem", ".key"]
    for path in scan_paths:
        if not path.is_dir():
            continue
        for pattern in sensitive_patterns:
            for f in path.rglob(f"*{pattern}*"):
                if not f.is_file():
                    continue
                try:
                    mode = f.stat().st_mode & 0o777
                    if mode & 0o077:  # readable/writable by group/others
                        findings.append(Finding(
                            "config", "high",
                            f"Broad permissions ({oct(mode)}) on sensitive file: {f}",
                            str(f),
                        ))
                except OSError:
                    continue
    return findings


def scan_exposed_ports(ports: list[dict]) -> list[Finding]:
    """Check for services listening on 0.0.0.0."""
    findings = []
    for p in ports:
        if p["ip"] == "0.0.0.0":
            findings.append(Finding(
                "network", "high",
                f"Port {p['port']} ({p['process']}) exposed on 0.0.0.0 instead of 127.0.0.1",
                f"port:{p['port']}",
            ))
    return findings


def scan_pip_audit(scan_paths: list[Path]) -> list[Finding]:
    """Run pip-audit on requirements files."""
    findings = []
    for path in scan_paths:
        for req_file in path.rglob("requirements*.txt"):
            try:
                result = subprocess.run(
                    ["pip-audit", "-r", str(req_file), "--format", "json", "--progress-spinner", "off"],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    continue
                import json
                try:
                    data = json.loads(result.stdout)
                    for vuln in data.get("dependencies", []):
                        for v in vuln.get("vulns", []):
                            severity = "critical" if "critical" in v.get("fix_versions", [""])[0].lower() else "high"
                            findings.append(Finding(
                                "deps", severity,
                                f"{vuln['name']}=={vuln['version']}: {v.get('id', 'CVE-?')} — {v.get('description', '')[:100]}",
                                str(req_file),
                            ))
                except (json.JSONDecodeError, KeyError):
                    pass
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
    return findings


def scan_npm_audit(scan_paths: list[Path]) -> list[Finding]:
    """Run npm audit on package.json projects."""
    findings = []
    for path in scan_paths:
        for pkg_file in path.rglob("package.json"):
            pkg_dir = pkg_file.parent
            if not (pkg_dir / "node_modules").exists():
                continue
            try:
                result = subprocess.run(
                    ["npm", "audit", "--json"],
                    capture_output=True, text=True, timeout=60, cwd=str(pkg_dir),
                )
                import json
                try:
                    data = json.loads(result.stdout)
                    vulns = data.get("vulnerabilities", {})
                    for name, info in vulns.items():
                        sev = info.get("severity", "moderate")
                        severity_map = {"critical": "critical", "high": "high", "moderate": "medium", "low": "low"}
                        findings.append(Finding(
                            "deps", severity_map.get(sev, "medium"),
                            f"npm: {name} — {sev} severity",
                            str(pkg_dir),
                        ))
                except (json.JSONDecodeError, KeyError):
                    pass
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
    return findings
```

- [ ] **Step 4: Run tests — verify pass**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_security_scanners.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add plugins/security_scan/ tests/test_security_scanners.py
git commit -m "feat: security scanners — Docker, .env, permissions, ports, deps"
```

---

### Task 10: Security Scan Plugin — plugin class and widget

**Files:**
- Create: `plugins/security_scan/plugin.py`
- Create: `plugins/security_scan/widget.py`
- Create: `tests/test_security_plugin.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_security_plugin.py
"""Tests for Security Scan plugin."""

import pytest
import aiosqlite
from plugins.security_scan.plugin import SecurityScanPlugin
from core.config import DEFAULTS


@pytest.fixture
def plugin():
    return SecurityScanPlugin(DEFAULTS)


@pytest.mark.asyncio
async def test_migrate_creates_tables(plugin, tmp_path):
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(db_path) as conn:
        await plugin.migrate(conn)
        await conn.commit()

        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        assert "security_findings" in tables
        assert "security_scans" in tables


@pytest.mark.asyncio
async def test_store_and_retrieve_findings(plugin, tmp_path):
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(db_path) as conn:
        await plugin.migrate(conn)
        await conn.commit()

        await conn.execute(
            "INSERT INTO security_findings (type, severity, description, source) VALUES (?, ?, ?, ?)",
            ("docker", "critical", "Container runs privileged", "postgres"),
        )
        await conn.commit()

        alerts = await plugin.get_alerts(conn)
        assert len(alerts) == 1
        assert alerts[0].severity == "critical"


@pytest.mark.asyncio
async def test_findings_severity_counts(plugin, tmp_path):
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(db_path) as conn:
        await plugin.migrate(conn)
        await conn.commit()

        for sev in ["critical", "critical", "high", "medium", "low", "low", "low"]:
            await conn.execute(
                "INSERT INTO security_findings (type, severity, description, source) VALUES (?, ?, ?, ?)",
                ("test", sev, f"Test {sev} finding", "test"),
            )
        await conn.commit()

        cursor = await conn.execute(
            "SELECT severity, COUNT(*) FROM security_findings GROUP BY severity"
        )
        counts = dict(await cursor.fetchall())
        assert counts["critical"] == 2
        assert counts["high"] == 1
        assert counts["low"] == 3
```

- [ ] **Step 2: Run test — verify fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_security_plugin.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement widget**

```python
# plugins/security_scan/widget.py
"""Security Scan TUI widget."""

from __future__ import annotations

from textual.widgets import DataTable, Static
from textual.containers import Vertical


SEVERITY_ICONS = {
    "critical": "[red bold]CRIT[/]",
    "high": "[#ff8c00]HIGH[/]",
    "medium": "[yellow]MED[/]",
    "low": "[dim]LOW[/]",
}


class FindingsTable(DataTable):
    """Table showing security findings."""

    def on_mount(self) -> None:
        self.add_columns("SEV", "TYPE", "DESCRIPTION", "SOURCE")
        self.cursor_type = "row"

    def update_data(self, findings: list[dict]) -> None:
        self.clear()
        # Sort: critical first
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        findings.sort(key=lambda f: order.get(f.get("severity", "low"), 4))

        for f in findings:
            sev = SEVERITY_ICONS.get(f["severity"], f["severity"])
            desc = f["description"][:80]
            source = f.get("source", "")[:30]
            self.add_row(sev, f.get("type", ""), desc, source)


class SecuritySummary(Static):
    """Summary bar with severity counts."""

    def update_counts(self, findings: list[dict]) -> None:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in findings:
            sev = f.get("severity", "low")
            counts[sev] = counts.get(sev, 0) + 1
        self.update(
            f"[red bold]CRITICAL ({counts['critical']})[/]  "
            f"[#ff8c00]HIGH ({counts['high']})[/]  "
            f"[yellow]MEDIUM ({counts['medium']})[/]  "
            f"[dim]LOW ({counts['low']})[/]"
        )


class SecurityWidget(Vertical):
    """Combined security scan widget."""

    def compose(self):
        yield SecuritySummary(id="security-summary")
        yield FindingsTable(id="security-table")
```

- [ ] **Step 4: Implement plugin class**

```python
# plugins/security_scan/plugin.py
"""Security Scan plugin — Docker, configs, deps, network."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from core.plugin import Plugin, Alert
from plugins.security_scan.scanners import (
    scan_docker_security,
    scan_env_in_git,
    scan_file_permissions,
    scan_exposed_ports,
    scan_pip_audit,
    scan_npm_audit,
    Finding,
)
from plugins.security_scan.widget import SecurityWidget

if TYPE_CHECKING:
    import aiosqlite
    from textual.widget import Widget


class SecurityScanPlugin(Plugin):

    name = "Security"
    icon = "🛡"

    def __init__(self, config: dict):
        self._config = config.get("plugins", {}).get("security_scan", {})
        self._scan_interval = self._config.get("scan_interval", 3600)
        raw_paths = self._config.get("scan_paths", ["~"])
        self._scan_paths = [Path(p).expanduser() for p in raw_paths]
        self._last_scan: float = 0
        self._widget: SecurityWidget | None = None

    async def migrate(self, db: aiosqlite.Connection) -> None:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS security_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                severity TEXT NOT NULL,
                description TEXT NOT NULL,
                source TEXT,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                resolved_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS security_scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                duration_seconds REAL,
                findings_count INTEGER
            )
        """)

    async def collect(self, db: aiosqlite.Connection) -> None:
        now = time.time()
        if (now - self._last_scan) < self._scan_interval and self._last_scan > 0:
            return  # skip — not time for scan yet

        start = time.time()
        all_findings: list[Finding] = []

        # Docker security (reuse data from docker_monitor if available)
        try:
            import docker
            client = docker.from_env()
            containers = client.containers.list(all=True)
            from plugins.docker_monitor.collector import collect_containers
            infos = collect_containers(containers)
            all_findings.extend(scan_docker_security(infos))
        except Exception:
            pass

        # .env in git
        all_findings.extend(scan_env_in_git(self._scan_paths))

        # File permissions
        all_findings.extend(scan_file_permissions(self._scan_paths))

        # Exposed ports
        try:
            from plugins.port_map.collector import collect_ports
            ports = collect_ports()
            all_findings.extend(scan_exposed_ports(ports))
        except Exception:
            pass

        # Dependency audits (slower — run anyway on scan interval)
        all_findings.extend(scan_pip_audit(self._scan_paths))
        all_findings.extend(scan_npm_audit(self._scan_paths))

        duration = time.time() - start
        self._last_scan = now

        # Mark old findings as resolved
        await db.execute("UPDATE security_findings SET resolved_at = CURRENT_TIMESTAMP WHERE resolved_at IS NULL")

        # Insert new findings
        for f in all_findings:
            await db.execute(
                "INSERT INTO security_findings (type, severity, description, source) VALUES (?, ?, ?, ?)",
                (f.type, f.severity, f.description, f.source),
            )

        # Log scan
        await db.execute(
            "INSERT INTO security_scans (duration_seconds, findings_count) VALUES (?, ?)",
            (round(duration, 1), len(all_findings)),
        )
        await db.commit()

        # Update widget
        if self._widget:
            findings_dicts = [{"type": f.type, "severity": f.severity, "description": f.description, "source": f.source} for f in all_findings]
            table = self._widget.query_one("#security-table", None)
            if table:
                table.update_data(findings_dicts)
            summary = self._widget.query_one("#security-summary", None)
            if summary:
                summary.update_counts(findings_dicts)

    def render(self) -> Widget:
        self._widget = SecurityWidget()
        return self._widget

    async def get_alerts(self, db: aiosqlite.Connection) -> list[Alert]:
        alerts = []
        cursor = await db.execute(
            "SELECT type, severity, description, source FROM security_findings WHERE resolved_at IS NULL"
        )
        for row in await cursor.fetchall():
            type_, severity, desc, source = row
            if severity in ("critical", "high"):
                sound = "fart3.mp3" if severity == "critical" else "fart1.mp3"
                alerts.append(Alert(
                    source="security",
                    severity=severity,
                    title=f"[{type_}] {desc[:50]}",
                    message=desc,
                    sound=sound,
                ))
        return alerts
```

- [ ] **Step 5: Run tests — verify pass**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_security_plugin.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add plugins/security_scan/ tests/test_security_plugin.py
git commit -m "feat: Security Scan plugin with findings, alerts, and TUI widget"
```

---

### Task 11: Integration test — full app startup

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
"""Integration test — app creates, registers plugins, runs migrations."""

import pytest
import aiosqlite
from pathlib import Path
from core.config import load_config, DEFAULTS
from core.sqlite_db import Database
from core.alerts import AlertManager
from plugins.docker_monitor.plugin import DockerMonitorPlugin
from plugins.port_map.plugin import PortMapPlugin
from plugins.security_scan.plugin import SecurityScanPlugin


@pytest.mark.asyncio
async def test_all_plugins_migrate(tmp_path):
    """All three MVP plugins create their tables without conflicts."""
    db = Database(tmp_path / "test.db")
    await db.connect()

    plugins = [
        DockerMonitorPlugin(DEFAULTS),
        PortMapPlugin(DEFAULTS),
        SecurityScanPlugin(DEFAULTS),
    ]

    for plugin in plugins:
        await db.run_migration(plugin.migrate)

    async with db.connection() as conn:
        cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in await cursor.fetchall()]

    await db.close()

    expected = [
        "docker_containers", "docker_events", "docker_metrics",
        "port_history", "port_services",
        "security_findings", "security_scans",
    ]
    for t in expected:
        assert t in tables, f"Missing table: {t}"


def test_all_plugins_render():
    """All plugins return a valid Textual widget."""
    plugins = [
        DockerMonitorPlugin(DEFAULTS),
        PortMapPlugin(DEFAULTS),
        SecurityScanPlugin(DEFAULTS),
    ]
    for plugin in plugins:
        widget = plugin.render()
        assert widget is not None


def test_alert_manager_processes_plugin_alerts():
    """Alert manager correctly processes alerts from plugins."""
    from core.plugin import Alert
    manager = AlertManager(DEFAULTS)

    alert = Alert(source="docker", severity="critical", title="test crash", message="container died")
    assert manager.process(alert) is True
    # dedup prevents second fire
    assert manager.process(alert) is False
```

- [ ] **Step 2: Run all tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: integration tests for plugin system, migrations, and alerts"
```

---

### Task 12: Entry point, sounds, and final polish

**Files:**
- Create: `sounds/` symlink or copy
- Modify: `core/app.py` (add startup animation)
- Create: `tests/conftest.py`

- [ ] **Step 1: Create tests/conftest.py for shared fixtures**

```python
# tests/conftest.py
"""Shared test fixtures."""

import pytest
from pathlib import Path


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test_monitor.db"
```

- [ ] **Step 2: Symlink sounds from claude-nagger**

```bash
cd /home/dchuprina/claude-monitor
ln -sf /home/dchuprina/claude-nagger/sounds/farts sounds
```

- [ ] **Step 3: Run full test suite**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 4: Test app launch (manual smoke test)**

Run: `cd /home/dchuprina/claude-monitor && python -m core.app`
Expected: TUI launches with tabs for Docker, Ports, Security. Press `q` to quit.

- [ ] **Step 5: Commit**

```bash
git add sounds tests/conftest.py
git commit -m "feat: final MVP — sounds, test fixtures, entry point ready"
```

---

### Task 13: README update

**Files:**
- Modify: `README.MD`

- [ ] **Step 1: Add dev-monitor section to README**

Add after existing content in `README.MD`:

```markdown

---

## Dev Monitor (v2.0)

Plugin-based TUI dashboard for monitoring your local dev environment.

### Features (MVP)

- **Docker Monitor** — container status, CPU/RAM, health checks, restart detection
- **Port/Service Map** — listening ports, conflict detection, project auto-discovery
- **Security Scan** — Docker security, .env in git, dependency CVEs, exposed ports
- **Alerts** — desktop notifications + fart sounds by severity

### Quick Start

```bash
# Install dependencies
pip install textual docker psutil aiosqlite

# Optional: security scanning
pip install pip-audit

# Run
python -m core.app
# or
dev-monitor  # if installed via pip
```

### Keybindings

| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Force refresh all plugins |
| `Tab` | Switch between plugin tabs |

### Configuration

Edit `config.toml` to customize thresholds, enable/disable plugins, set quiet hours.
```

- [ ] **Step 2: Commit**

```bash
git add README.MD
git commit -m "docs: add dev-monitor v2.0 section to README"
```
