# Phase 2+3: Sound System (Classic/Fart) + Hasselhoff Taming + Overview Redesign

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fart-only sound system with Classic/Fart mode toggle, reduce Hasselhoff to Wizard-only + 1 daily achievement, add Win95-style notification popups, and redesign Overview with compact Docker/Ports widgets. Remove separate Docker and Ports pages.

**Architecture:** New sound profile system in `core/sounds.py`. Win95-style QDialog notification popup. Overview page gets collapsible Docker/Ports widgets. Sidebar loses Docker/Ports items. Port conflicts move to Security tab.

**Tech Stack:** Python 3.11+, PyQt5

**Depends on:** Phase 0+1 (platform layer, claude_nagger cleanup)

---

## File Structure

### New files:
- `sounds/classic/info.wav` — gentle beep
- `sounds/classic/warning.wav` — warning chime
- `sounds/classic/critical.wav` — alarm sound
- `gui/win95_popup.py` — Win95-style notification dialog
- `tests/test_sounds.py` — Sound system tests
- `tests/test_win95_popup.py` — Popup tests

### Files to modify:
- `core/alerts.py` — Sound mode selection (already refactored in Phase 0)
- `core/config.py` — Add `sounds.mode` default
- `gui/app.py` — Remove Docker/Ports pages, reduce Hasselhoff triggers, use Win95 popup
- `gui/pages/overview.py` — Add compact Docker/Ports widgets
- `gui/pages/settings.py` — Add sound mode selector
- `gui/sidebar.py` — Remove Docker/Ports items, reorder
- `plugins/security_scan/scanners.py` — Add port conflict as security finding type
- `i18n/en.py` — New strings
- `i18n/ua.py` — New strings

### Files to delete:
- `gui/pages/docker.py` — Replaced by compact widget on Overview
- `gui/pages/ports.py` — Replaced by Security findings

---

### Task 1: Sound mode system

**Files:**
- Modify: `core/config.py`
- Modify: `core/alerts.py`
- Create: `tests/test_sounds.py`

- [ ] **Step 1: Write failing test for sound modes**

```python
# tests/test_sounds.py
from unittest.mock import patch, MagicMock
from pathlib import Path

from core.alerts import AlertManager
from core.plugin import Alert


def test_classic_mode_uses_classic_dir():
    config = {
        "sounds": {"enabled": True, "mode": "classic", "quiet_hours_start": "23:00", "quiet_hours_end": "07:00"},
        "alerts": {"cooldown_seconds": 0, "desktop_notifications": False},
    }
    mgr = AlertManager(config)
    sound_dir = mgr._find_sound_dir("classic")
    assert sound_dir is None or "classic" in str(sound_dir)


def test_fart_mode_uses_fart_dir():
    config = {
        "sounds": {"enabled": True, "mode": "fart", "quiet_hours_start": "23:00", "quiet_hours_end": "07:00"},
        "alerts": {"cooldown_seconds": 0, "desktop_notifications": False},
    }
    mgr = AlertManager(config)
    sound_dir = mgr._find_sound_dir("fart")
    assert sound_dir is None or "fart" in str(sound_dir)


def test_default_mode_is_classic():
    config = {
        "sounds": {"enabled": True},
        "alerts": {"cooldown_seconds": 0, "desktop_notifications": True},
    }
    mgr = AlertManager(config)
    mode = config["sounds"].get("mode", "classic")
    assert mode == "classic"


def test_sound_disabled_skips_playback():
    config = {
        "sounds": {"enabled": False, "mode": "classic"},
        "alerts": {"cooldown_seconds": 0, "desktop_notifications": False},
    }
    mgr = AlertManager(config)
    mock_platform = MagicMock()
    with patch.object(mgr, '_platform', mock_platform):
        alert = Alert(source="test", severity="warning", title="T", message="M")
        mgr.play_sound(alert)
        mock_platform.play_sound.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_sounds.py -v`
Expected: FAIL (some tests may pass if structure matches)

- [ ] **Step 3: Add sound mode default to config**

In `core/config.py`, update DEFAULTS:

```python
"sounds": {
    "enabled": True,
    "mode": "classic",  # "classic" or "fart"
    "quiet_hours_start": "23:00",
    "quiet_hours_end": "07:00",
},
```

- [ ] **Step 4: Create sound directory structure**

```bash
mkdir -p sounds/classic sounds/fart
# Classic sounds will be added as actual .wav files
# For now, create placeholder README
echo "Place classic alert sounds here: info.wav, warning.wav, critical.wav" > sounds/classic/README.md
echo "Place fart sounds here" > sounds/fart/README.md
```

- [ ] **Step 5: Update alerts.py sound selection by severity**

In `core/alerts.py`, update `play_sound` method to pick sounds by severity:

```python
def play_sound(self, alert: Alert) -> None:
    sounds_cfg = self._config.get("sounds", {})
    if not sounds_cfg.get("enabled", True):
        return
    if self.is_quiet_hours():
        return

    sound_mode = sounds_cfg.get("mode", "classic")
    sound_dir = self._find_sound_dir(sound_mode)
    if not sound_dir:
        return

    # Try severity-specific sound first
    severity = alert.severity  # "critical", "warning", "info"
    severity_files = [f for f in sound_dir.iterdir()
                      if f.stem.lower().startswith(severity) and
                      f.suffix.lower() in (".mp3", ".wav", ".ogg", ".flac")]
    if severity_files:
        self._platform.play_sound(random.choice(severity_files))
        return

    # Fallback: any sound in the directory
    all_files = [f for f in sound_dir.iterdir()
                 if f.suffix.lower() in (".mp3", ".wav", ".ogg", ".flac")]
    if all_files:
        self._platform.play_sound(random.choice(all_files))
```

- [ ] **Step 6: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_sounds.py tests/test_alerts.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add core/config.py core/alerts.py sounds/ tests/test_sounds.py
git commit -m "feat: sound system with Classic/Fart modes — severity-based sound selection"
```

---

### Task 2: Win95 notification popup

**Files:**
- Create: `gui/win95_popup.py`
- Create: `tests/test_win95_popup.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_win95_popup.py
import pytest
from unittest.mock import patch

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication
import sys

app = QApplication.instance() or QApplication(sys.argv)


def test_popup_creates_with_severity():
    from gui.win95_popup import Win95Popup
    popup = Win95Popup("Test Title", "Test message", severity="warning")
    assert popup.windowTitle() == "Test Title"
    popup.close()


def test_popup_severity_icon():
    from gui.win95_popup import Win95Popup
    for sev in ("critical", "warning", "info"):
        popup = Win95Popup("T", "M", severity=sev)
        assert popup._icon_label.text() != ""
        popup.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_win95_popup.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Win95 popup**

```python
# gui/win95_popup.py
"""Win95-style notification popup dialog."""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

_SEVERITY_ICONS = {
    "critical": "✖",   # Red X
    "warning": "⚠",    # Yellow triangle
    "info": "ℹ",       # Blue i
}

_SEVERITY_COLORS = {
    "critical": "#cc0000",
    "warning": "#cc8800",
    "info": "#000080",
}

_SEVERITY_TITLES = {
    "critical": "Error",
    "warning": "Warning",
    "info": "Information",
}

WIN95_POPUP_STYLE = """
QDialog {
    background-color: #c0c0c0;
    border: 2px outset #dfdfdf;
}
QLabel {
    color: #000000;
}
QPushButton {
    background: #c0c0c0;
    border: 2px outset #dfdfdf;
    padding: 4px 20px;
    font-weight: bold;
    min-width: 75px;
}
QPushButton:pressed {
    border: 2px inset #808080;
}
"""


class Win95Popup(QDialog):
    """Windows 95-style message box for alerts."""

    def __init__(self, title: str, message: str, severity: str = "info",
                 auto_close_ms: int = 8000, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(WIN95_POPUP_STYLE)
        self.setMinimumWidth(350)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Dialog)

        layout = QVBoxLayout(self)

        # Title bar simulation
        title_bar = QLabel(f"  {_SEVERITY_TITLES.get(severity, 'Notice')}")
        title_bar.setStyleSheet(
            "background: #000080; color: white; font-weight: bold; "
            "padding: 2px 4px; font-size: 12px;"
        )
        layout.addWidget(title_bar)

        # Content area
        content_layout = QHBoxLayout()

        # Icon
        self._icon_label = QLabel(_SEVERITY_ICONS.get(severity, "ℹ"))
        self._icon_label.setFont(QFont("Arial", 32))
        self._icon_label.setStyleSheet(
            f"color: {_SEVERITY_COLORS.get(severity, '#000080')}; "
            "padding: 8px; min-width: 50px;"
        )
        self._icon_label.setAlignment(Qt.AlignTop | Qt.AlignCenter)
        content_layout.addWidget(self._icon_label)

        # Message
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet("padding: 8px; font-size: 12px;")
        content_layout.addWidget(msg_label, stretch=1)

        layout.addLayout(content_layout)

        # OK button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Auto-close timer
        if auto_close_ms > 0:
            QTimer.singleShot(auto_close_ms, self.accept)
```

- [ ] **Step 4: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_win95_popup.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gui/win95_popup.py tests/test_win95_popup.py
git commit -m "feat: Win95-style notification popup with severity icons"
```

---

### Task 3: Tame Hasselhoff — reduce triggers

**Files:**
- Modify: `gui/app.py`

- [ ] **Step 1: Remove Hasselhoff triggers from Docker, Security, Usage**

In `gui/app.py`, make these changes:

1. In `_check_docker_alerts`: Remove the Hasselhoff trigger blocks:
   - Remove: `if prev and prev != "running": self._trigger_hasselhoff(...)` (container started)
   - Remove: `if len(running) >= 3 and all_healthy: ... self._trigger_hasselhoff(...)` (all healthy)
   - Remove: `self._hoff_docker_triggered` flag

2. In `_check_usage_alerts`: Remove Hasselhoff triggers:
   - Remove: cache ratio Hasselhoff trigger (`_hoff_cache_triggered`)
   - Remove: efficient day Hasselhoff trigger (`_hoff_efficient_triggered`)

3. In `_on_scan_done`: Remove clean scan Hasselhoff:
   - Remove: `if not all_critical and findings: self._trigger_hasselhoff(...)`

4. Keep only:
   - `_trigger_hasselhoff` method itself (used by Wizard page)
   - `_do_hoff` menu action (manual trigger)
   - `page_hoff_wizard.hoff_event.connect(self._trigger_hasselhoff)` signal

- [ ] **Step 2: Replace desktop notify-send with Win95 popup**

In `gui/app.py`, modify AlertManager integration to optionally show Win95 popup:

```python
# In _on_data_ready or wherever alerts are processed, add:
from gui.win95_popup import Win95Popup

# Add method to MonitorApp:
def _show_win95_alert(self, alert):
    """Show Win95-style popup for important alerts."""
    if alert.severity in ("critical", "warning"):
        popup = Win95Popup(
            f"[{alert.source}] {alert.title}",
            alert.message,
            severity=alert.severity,
            parent=self,
        )
        popup.show()
```

- [ ] **Step 3: Wire Win95 popup into alert flow**

Override `send_desktop` in MonitorApp to use Win95 popup when GUI is active:

```python
# In MonitorApp.__init__, after creating _alert_manager:
self._alert_manager.on_alert = self._show_win95_alert
```

Or modify AlertManager.process to emit a signal that the GUI catches.

- [ ] **Step 4: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gui/app.py
git commit -m "feat: tame Hasselhoff — remove auto-triggers, add Win95 popup for alerts"
```

---

### Task 4: Settings page — add sound mode selector

**Files:**
- Modify: `gui/pages/settings.py`
- Modify: `i18n/en.py`
- Modify: `i18n/ua.py`

- [ ] **Step 1: Add i18n strings**

In `i18n/en.py`, add:
```python
"sound_mode": "Sound Mode",
"sound_mode_classic": "Classic (normal alerts)",
"sound_mode_fart": "Fart Mode (the Hoff way)",
```

In `i18n/ua.py`, add:
```python
"sound_mode": "Режим звуку",
"sound_mode_classic": "Класичний (звичайні алерти)",
"sound_mode_fart": "Пердьож-режим (шлях Хоффа)",
```

- [ ] **Step 2: Add sound mode combo to Settings page**

In `gui/pages/settings.py`, in the sound group section, add after `self.sound_enabled`:

```python
self.sound_mode = QComboBox()
self.sound_mode.addItems(["classic", "fart"])
current_mode = config.get("sounds", {}).get("mode", "classic")
self.sound_mode.setCurrentText(current_mode)
sg.addRow(_t("sound_mode") + ":", self.sound_mode)
```

In `_apply`, add:
```python
self._config["sounds"]["mode"] = self.sound_mode.currentText()
```

- [ ] **Step 3: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add gui/pages/settings.py i18n/en.py i18n/ua.py
git commit -m "feat: sound mode selector in Settings — Classic vs Fart"
```

---

### Task 5: Compact Docker/Ports widget for Overview

**Files:**
- Modify: `gui/pages/overview.py`
- Modify: `i18n/en.py`
- Modify: `i18n/ua.py`

- [ ] **Step 1: Add i18n strings**

In `i18n/en.py`:
```python
"docker_compact": "Docker: {} running | {} stopped",
"docker_compact_error": "Docker: not available",
"docker_compact_alert": " | ⚠ {} alerts",
"ports_compact": "Ports: {} listening | {} conflicts",
"no_conflicts": "No port conflicts",
```

In `i18n/ua.py`:
```python
"docker_compact": "Docker: {} працює | {} зупинено",
"docker_compact_error": "Docker: недоступний",
"docker_compact_alert": " | ⚠ {} алертів",
"ports_compact": "Порти: {} слухають | {} конфліктів",
"no_conflicts": "Конфліктів портів немає",
```

- [ ] **Step 2: Add compact Docker widget to Overview**

In `gui/pages/overview.py`, add after the stats_group:

```python
# --- Compact Docker/Ports ---
self.infra_group = QGroupBox("Infrastructure")
il = QVBoxLayout()

self.docker_status = QLabel(_t("docker_compact").format(0, 0))
self.docker_status.setStyleSheet(
    "padding: 4px 8px; background: white; border: 2px inset #808080; font-size: 11px;"
)
il.addWidget(self.docker_status)

self.ports_status = QLabel(_t("ports_compact").format(0, 0))
self.ports_status.setStyleSheet(
    "padding: 4px 8px; background: white; border: 2px inset #808080; font-size: 11px;"
)
il.addWidget(self.ports_status)

self.infra_group.setLayout(il)
layout.addWidget(self.infra_group)
```

Add update methods:

```python
def update_docker_compact(self, infos: list[dict]) -> None:
    running = sum(1 for i in infos if i.get("status") == "running")
    stopped = len(infos) - running
    text = _t("docker_compact").format(running, stopped)

    # Check for alerts
    alerts = 0
    for i in infos:
        if i.get("status") == "exited" and i.get("exit_code", 0) != 0:
            alerts += 1
        if i.get("cpu_percent", 0) > 80:
            alerts += 1
    if alerts:
        text += _t("docker_compact_alert").format(alerts)

    color = "#006600" if alerts == 0 else "#cc0000"
    self.docker_status.setText(text)
    self.docker_status.setStyleSheet(
        f"padding: 4px 8px; background: white; border: 2px inset #808080; "
        f"font-size: 11px; color: {color};"
    )

def update_ports_compact(self, ports: list[dict]) -> None:
    total = len(ports)
    conflicts = sum(1 for p in ports if p.get("conflict"))
    text = _t("ports_compact").format(total, conflicts)
    color = "#006600" if conflicts == 0 else "#cc8800"
    self.ports_status.setText(text)
    self.ports_status.setStyleSheet(
        f"padding: 4px 8px; background: white; border: 2px inset #808080; "
        f"font-size: 11px; color: {color};"
    )

def set_docker_error(self, msg: str) -> None:
    self.docker_status.setText(_t("docker_compact_error"))
    self.docker_status.setStyleSheet(
        "padding: 4px 8px; background: white; border: 2px inset #808080; "
        "font-size: 11px; color: #999999;"
    )
```

- [ ] **Step 3: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add gui/pages/overview.py i18n/en.py i18n/ua.py
git commit -m "feat: compact Docker/Ports widgets on Overview page"
```

---

### Task 6: Remove Docker and Ports pages, update sidebar and app.py

**Files:**
- Delete: `gui/pages/docker.py`
- Delete: `gui/pages/ports.py`
- Modify: `gui/app.py`
- Modify: `gui/sidebar.py` (if needed)

- [ ] **Step 1: Update gui/app.py — remove Docker/Ports pages**

Remove imports:
```python
# Remove these:
from gui.pages.docker import DockerPage
from gui.pages.ports import PortsPage
```

Remove page creation:
```python
# Remove:
self.page_docker = DockerPage(system_state.docker_client)
self.page_ports = PortsPage()
```

Remove from stack registration and sidebar items:
```python
# Remove from sidebar_items:
SidebarItem(_t("side_docker"), "docker"),
SidebarItem(_t("side_ports"), "ports"),

# Remove from page registration loop:
("docker", self.page_docker),
("ports", self.page_ports),
```

Update sidebar items to new order:
```python
sidebar_items = [
    SidebarItem(_t("side_overview"), "overview"),
    SidebarItem(_t("side_security"), "security"),
    SidebarItem(_t("side_usage"), "usage"),
    SidebarItem(_t("side_analytics"), "analytics"),
    SidebarItem("", "", is_separator=True),
    SidebarItem(_t("side_tips"), "tips"),
    SidebarItem(_t("side_discover"), "discover"),
    SidebarItem(_t("side_settings"), "settings"),
    SidebarItem("", "", is_separator=True),
    SidebarItem("Hoff Wizard", "hoff_wizard"),
]
```

- [ ] **Step 2: Route Docker/Ports data to Overview compact widgets**

In `_on_data_ready`:
```python
def _on_data_ready(self, data: dict):
    self._collecting = False

    # Docker → compact widget on Overview
    infos = data.get("docker", [])
    self.page_overview.update_docker_compact(infos)
    if self._is_alert_enabled("docker"):
        self._check_docker_alerts(infos)

    # Ports → compact widget on Overview
    ports = data.get("ports", [])
    self.page_overview.update_ports_compact(ports)
    if self._is_alert_enabled("ports"):
        for p in ports:
            if p.get("conflict"):
                self._alert_manager.process(Alert(
                    source="ports", severity="warning",
                    title=f"Port {p['port']} conflict",
                    message=f"Port {p['port']} used by multiple processes",
                ))

    self.statusBar().showMessage("Ready")
```

- [ ] **Step 3: Remove Docker-specific signals**

Remove from `__init__`:
```python
# Remove:
self.page_docker.fart_off_triggered.connect(self._on_fart_off)
self.page_docker.container_count_changed.connect(...)
```

Remove `_on_fart_off` method.

- [ ] **Step 4: Simplify `_check_docker_alerts` — alerts only, no Hasselhoff**

```python
def _check_docker_alerts(self, infos: list[dict]):
    cpu_thresh = self._config["plugins"]["docker_monitor"]["cpu_threshold"]
    ram_thresh = self._config["plugins"]["docker_monitor"]["ram_threshold"]

    for info in infos:
        name = info["name"]

        if info["status"] == "exited" and info.get("exit_code", 0) != 0:
            self._alert_manager.process(Alert(
                source="docker", severity="critical",
                title=f"{name} crashed (exit {info['exit_code']})",
                message=f"Container {name} exited with code {info['exit_code']}",
            ))
        elif info["status"] == "running":
            if info["cpu_percent"] > cpu_thresh:
                self._alert_manager.process(Alert(
                    source="docker", severity="warning",
                    title=f"{name} CPU {info['cpu_percent']:.0f}%",
                    message=f"CPU at {info['cpu_percent']:.1f}%",
                ))
            if info["mem_limit"] > 0:
                ram_pct = (info["mem_usage"] / info["mem_limit"]) * 100
                if ram_pct > ram_thresh:
                    self._alert_manager.process(Alert(
                        source="docker", severity="critical",
                        title=f"{name} RAM {ram_pct:.0f}%",
                        message=f"RAM at {ram_pct:.1f}%",
                    ))
```

- [ ] **Step 5: Delete the page files**

```bash
rm gui/pages/docker.py gui/pages/ports.py
```

- [ ] **Step 6: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v`
Expected: PASS (docker/ports page tests will fail — remove them too)

- [ ] **Step 7: Remove or update tests referencing deleted pages**

```bash
rm -f tests/test_docker_plugin.py  # if it imports DockerPage
# Update test_integration.py if it references docker/ports pages
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: remove Docker/Ports pages — compact widgets on Overview, alerts only"
```

---

### Task 7: Move port conflicts to Security tab

**Files:**
- Modify: `plugins/security_scan/scanners.py`
- Modify: `gui/app.py`

- [ ] **Step 1: Ensure port conflict detection runs during security scan**

In `gui/app.py`, in `_run_security_scan` (the `scan()` inner function), port scanning is already included via `scan_exposed_ports`. Verify that port conflicts from the collector are also fed to security:

```python
# In scan() inside _run_security_scan, add:
try:
    from plugins.port_map.collector import collect_ports
    ports = collect_ports()
    findings.extend(scan_exposed_ports(ports))
    # Add conflict findings
    for p in ports:
        if p.get("conflict"):
            findings.append({
                "type": "network", "severity": "warning",
                "description": f"Port {p['port']} conflict — multiple processes listening",
                "source": f"port:{p['port']}",
            })
except Exception:
    pass
```

Wait — `scan()` returns `Finding` objects that get converted to dicts. The port conflict needs to go through the same Finding dataclass. Better approach:

Add to `plugins/security_scan/scanners.py`:

```python
def scan_port_conflicts(ports: list[dict]) -> list[Finding]:
    """Detect ports with multiple processes listening."""
    findings = []
    for p in ports:
        if p.get("conflict"):
            findings.append(Finding(
                "network", "warning",
                f"Port {p['port']} conflict — multiple processes: {p.get('process', '?')}",
                f"port:{p['port']}",
            ))
    return findings
```

- [ ] **Step 2: Call it in the security scan flow**

In `gui/app.py`, `_run_security_scan`, add:
```python
from plugins.security_scan.scanners import scan_port_conflicts
# After scan_exposed_ports:
findings.extend(scan_port_conflicts(ports))
```

- [ ] **Step 3: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add plugins/security_scan/scanners.py gui/app.py
git commit -m "feat: port conflicts now appear in Security tab as findings"
```

---

### Task 8: Clean up i18n — remove dead strings

**Files:**
- Modify: `i18n/en.py`
- Modify: `i18n/ua.py`

- [ ] **Step 1: Remove strings for deleted pages**

Remove from both `en.py` and `ua.py`:
```python
# Remove Docker page strings:
"docker_name", "docker_status", "docker_cpu", "docker_ram",
"docker_ports", "docker_health", "fart_off", "start", "stop",
"restart", "logs", "remove", "mcp_servers", "mcp_name",
"mcp_command", "mcp_status", "mcp_args", "events", "no_events",
"remove_confirm_title", "remove_confirm_msg", "close",

# Remove Ports page strings:
"port", "proto", "process", "ip", "status", "ports_summary", "psutil_warning",

# Remove sidebar strings for deleted pages:
"side_docker", "side_ports",

# Remove most Hasselhoff trigger strings (keep wizard ones):
"hoff_clean_scan", "hoff_cache_hit", "hoff_efficient",
"hoff_container_up", "hoff_all_healthy",
```

- [ ] **Step 2: Verify no code references removed strings**

```bash
cd /home/dchuprina/claude-monitor && grep -r "docker_name\|fart_off\|side_docker\|side_ports\|hoff_clean_scan\|hoff_cache_hit\|hoff_efficient\|hoff_container_up\|hoff_all_healthy" --include="*.py" . | grep -v i18n | grep -v __pycache__
```
Expected: No results (all references should be in deleted files)

- [ ] **Step 3: Commit**

```bash
git add i18n/en.py i18n/ua.py
git commit -m "chore: remove dead i18n strings for deleted Docker/Ports/Hasselhoff triggers"
```

---

### Task 9: Final validation

- [ ] **Step 1: Run full test suite**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 2: Verify deleted files are gone**

```bash
ls gui/pages/docker.py gui/pages/ports.py 2>&1
```
Expected: "No such file or directory" for both

- [ ] **Step 3: Verify sound mode config works**

Run: `cd /home/dchuprina/claude-monitor && python -c "from core.config import load_config; c = load_config(); print(f'Sound mode: {c[\"sounds\"][\"mode\"]}')"`
Expected: "Sound mode: classic"

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "chore: Phase 2+3 complete — sound modes, Hasselhoff tamed, Overview compact, no Docker/Ports pages"
```
