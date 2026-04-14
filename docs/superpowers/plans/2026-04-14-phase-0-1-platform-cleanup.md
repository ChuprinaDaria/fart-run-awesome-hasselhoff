# Phase 0+1: Cross-Platform Abstraction Layer + Dead Code Cleanup

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a cross-platform abstraction layer (Linux/macOS/Windows) for all OS-specific operations, and clean up dead code from v1.0/v2.0 that pollutes the codebase.

**Architecture:** New `core/platform.py` module detects OS and provides unified API for notifications, sounds, paths, firewall checks, etc. Each platform backend lives in `core/platform_backends/`. Dead code removal consolidates `claude_nagger/` into `core/` and `gui/pages/`, deletes unused modules.

**Tech Stack:** Python 3.11+, PyQt5, psutil, subprocess, platform stdlib

---

## File Structure

### New files:
- `core/platform.py` — Platform detection + unified API facade
- `core/platform_backends/__init__.py` — Package init
- `core/platform_backends/linux.py` — Linux implementations
- `core/platform_backends/macos.py` — macOS implementations
- `core/platform_backends/windows.py` — Windows implementations
- `tests/test_platform.py` — Platform abstraction tests

### Files to modify:
- `core/alerts.py` — Replace hardcoded `notify-send`/`ffplay` with platform API
- `core/autodiscovery.py` — Replace hardcoded paths with platform API
- `core/config.py` — Use platform paths for config location
- `plugins/security_scan/scanners.py` — Replace Linux-only system scanners with platform dispatch
- `gui/pages/settings.py` — Use platform paths for config save, replace `toml` with `tomli_w`/`tomllib`

### Files to delete:
- `core/analyzer.py` — Dead code (imports nonexistent `db` module, uses PostgreSQL)
- `claude_nagger/cli/app.py` — Unused CLI entry point
- `claude_nagger/cli/tui.py` — Unused TUI dashboard
- `claude_nagger/gui/app.py` — Unused standalone GUI (replaced by gui/app.py)
- `claude_nagger/gui/popup.py` — Unused popup notifications
- `claude_nagger/core/sounds.py` — Replaced by new sound system in Phase 2

### Files to relocate:
- `claude_nagger/core/calculator.py` → `core/calculator.py`
- `claude_nagger/core/models.py` → `core/models.py`
- `claude_nagger/core/analyzer.py` → `core/usage_analyzer.py`
- `claude_nagger/core/tips.py` → `core/tips.py`
- `claude_nagger/core/parser.py` → `core/token_parser.py`
- `claude_nagger/nagger/messages.py` → `core/nagger/messages.py`
- `claude_nagger/nagger/hasselhoff.py` → `core/nagger/hasselhoff.py`
- `claude_nagger/i18n/__init__.py` → `i18n/__init__.py`
- `claude_nagger/i18n/en.py` → `i18n/en.py`
- `claude_nagger/i18n/ua.py` → `i18n/ua.py`
- `claude_nagger/gui/usage.py` → integrate into `gui/pages/usage.py`
- `claude_nagger/gui/discover.py` → integrate into `gui/pages/discover.py`

---

### Task 1: Create platform detection module

**Files:**
- Create: `core/platform.py`
- Create: `core/platform_backends/__init__.py`
- Create: `tests/test_platform.py`

- [ ] **Step 1: Write the failing test for platform detection**

```python
# tests/test_platform.py
import sys
from unittest.mock import patch

from core.platform import detect_platform, PlatformType


def test_detect_linux():
    with patch("sys.platform", "linux"):
        assert detect_platform() == PlatformType.LINUX


def test_detect_macos():
    with patch("sys.platform", "darwin"):
        assert detect_platform() == PlatformType.MACOS


def test_detect_windows():
    with patch("sys.platform", "win32"):
        assert detect_platform() == PlatformType.WINDOWS


def test_config_dir_linux():
    from core.platform import get_platform
    with patch("sys.platform", "linux"):
        p = get_platform()
        config_dir = p.config_dir()
        assert ".config/claude-monitor" in str(config_dir) or ".claude-monitor" in str(config_dir)


def test_cache_dir_linux():
    from core.platform import get_platform
    with patch("sys.platform", "linux"):
        p = get_platform()
        cache_dir = p.cache_dir()
        assert ".cache/claude-monitor" in str(cache_dir) or "claude-monitor" in str(cache_dir)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_platform.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'core.platform'"

- [ ] **Step 3: Write platform detection and base API**

```python
# core/platform.py
"""Cross-platform abstraction layer for OS-specific operations."""

from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path
from typing import Protocol


class PlatformType(Enum):
    LINUX = "linux"
    MACOS = "macos"
    WINDOWS = "windows"


def detect_platform() -> PlatformType:
    if sys.platform == "darwin":
        return PlatformType.MACOS
    if sys.platform == "win32":
        return PlatformType.WINDOWS
    return PlatformType.LINUX


class PlatformBackend(Protocol):
    """Interface every platform backend must implement."""

    def config_dir(self) -> Path: ...
    def cache_dir(self) -> Path: ...
    def data_dir(self) -> Path: ...
    def notify(self, title: str, message: str, urgency: str = "normal") -> None: ...
    def play_sound(self, path: Path) -> None: ...
    def open_url(self, url: str) -> None: ...
    def open_file(self, path: Path) -> None: ...
    def check_firewall(self) -> dict: ...
    def check_system_updates(self) -> list[str]: ...
    def check_ssh_config(self) -> dict: ...
    def check_sudoers(self) -> dict: ...
    def elevate_command(self, cmd: list[str]) -> list[str]: ...


_cached_platform: PlatformBackend | None = None


def get_platform() -> PlatformBackend:
    global _cached_platform
    if _cached_platform is not None:
        return _cached_platform

    pt = detect_platform()
    if pt == PlatformType.LINUX:
        from core.platform_backends.linux import LinuxBackend
        _cached_platform = LinuxBackend()
    elif pt == PlatformType.MACOS:
        from core.platform_backends.macos import MacOSBackend
        _cached_platform = MacOSBackend()
    else:
        from core.platform_backends.windows import WindowsBackend
        _cached_platform = WindowsBackend()
    return _cached_platform


def reset_platform() -> None:
    """Reset cached platform — for testing only."""
    global _cached_platform
    _cached_platform = None
```

```python
# core/platform_backends/__init__.py
"""Platform-specific backends."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_platform.py -v`
Expected: PASS (at least detection tests; backend tests may fail until backends exist)

- [ ] **Step 5: Commit**

```bash
git add core/platform.py core/platform_backends/__init__.py tests/test_platform.py
git commit -m "feat: add platform detection module with PlatformBackend protocol"
```

---

### Task 2: Linux backend

**Files:**
- Create: `core/platform_backends/linux.py`
- Modify: `tests/test_platform.py`

- [ ] **Step 1: Write failing tests for Linux backend**

```python
# append to tests/test_platform.py
from unittest.mock import patch, MagicMock
from core.platform_backends.linux import LinuxBackend


class TestLinuxBackend:
    def setup_method(self):
        self.backend = LinuxBackend()

    def test_config_dir(self):
        d = self.backend.config_dir()
        assert d == Path.home() / ".config" / "claude-monitor"

    def test_cache_dir(self):
        d = self.backend.cache_dir()
        assert d == Path.home() / ".cache" / "claude-monitor"

    def test_data_dir(self):
        d = self.backend.data_dir()
        assert d == Path.home() / ".local" / "share" / "claude-monitor"

    @patch("shutil.which", return_value="/usr/bin/notify-send")
    @patch("subprocess.Popen")
    def test_notify(self, mock_popen, mock_which):
        self.backend.notify("Test", "Message", "critical")
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert "notify-send" in args
        assert "-u" in args
        assert "critical" in args

    @patch("shutil.which", side_effect=lambda x: "/usr/bin/pw-play" if x == "pw-play" else None)
    @patch("subprocess.Popen")
    def test_play_sound_pipewire(self, mock_popen, mock_which):
        self.backend.play_sound(Path("/tmp/test.wav"))
        args = mock_popen.call_args[0][0]
        assert "pw-play" in args[0]

    @patch("shutil.which", side_effect=lambda x: "/usr/bin/paplay" if x == "paplay" else None)
    @patch("subprocess.Popen")
    def test_play_sound_pulseaudio(self, mock_popen, mock_which):
        self.backend.play_sound(Path("/tmp/test.wav"))
        args = mock_popen.call_args[0][0]
        assert "paplay" in args[0]

    @patch("subprocess.Popen")
    def test_open_url(self, mock_popen):
        self.backend.open_url("https://example.com")
        args = mock_popen.call_args[0][0]
        assert "xdg-open" in args

    def test_elevate_command(self):
        cmd = self.backend.elevate_command(["ufw", "enable"])
        assert cmd[0] in ("pkexec", "sudo")
        assert "ufw" in cmd
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_platform.py::TestLinuxBackend -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement Linux backend**

```python
# core/platform_backends/linux.py
"""Linux platform backend."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

_URGENCY_MAP = {"critical": "critical", "warning": "normal", "info": "low"}

_SOUND_PLAYERS = [
    ("pw-play", lambda p: ["pw-play", str(p)]),
    ("paplay", lambda p: ["paplay", str(p)]),
    ("ffplay", lambda p: ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(p)]),
    ("aplay", lambda p: ["aplay", str(p)]),
]


class LinuxBackend:
    def config_dir(self) -> Path:
        return Path.home() / ".config" / "claude-monitor"

    def cache_dir(self) -> Path:
        return Path.home() / ".cache" / "claude-monitor"

    def data_dir(self) -> Path:
        return Path.home() / ".local" / "share" / "claude-monitor"

    def notify(self, title: str, message: str, urgency: str = "normal") -> None:
        u = _URGENCY_MAP.get(urgency, "normal")
        if not shutil.which("notify-send"):
            log.warning("notify-send not found")
            return
        try:
            subprocess.Popen(
                ["notify-send", "-u", u, title, message],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    def play_sound(self, path: Path) -> None:
        for cmd_name, args_fn in _SOUND_PLAYERS:
            if shutil.which(cmd_name):
                try:
                    subprocess.Popen(
                        args_fn(path),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    return
                except FileNotFoundError:
                    continue
        log.warning("No sound player found (tried pw-play, paplay, ffplay, aplay)")

    def open_url(self, url: str) -> None:
        try:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            log.warning("xdg-open not found")

    def open_file(self, path: Path) -> None:
        self.open_url(str(path))

    def check_firewall(self) -> dict:
        """Return {"active": bool, "tool": str, "details": str}."""
        # Try ufw first
        try:
            result = subprocess.run(
                ["ufw", "status"], capture_output=True, text=True, timeout=10,
            )
            if "inactive" in result.stdout.lower():
                return {"active": False, "tool": "ufw", "details": "ufw is inactive"}
            if result.returncode == 0:
                return {"active": True, "tool": "ufw", "details": result.stdout.strip()}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Try nftables
        try:
            result = subprocess.run(
                ["nft", "list", "ruleset"], capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return {"active": True, "tool": "nftables", "details": "nftables rules found"}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Try iptables
        try:
            result = subprocess.run(
                ["iptables", "-L", "-n"], capture_output=True, text=True, timeout=10,
            )
            lines = [l for l in result.stdout.strip().split("\n")
                     if l.strip() and not l.startswith("Chain") and not l.startswith("target")]
            if lines:
                return {"active": True, "tool": "iptables", "details": f"{len(lines)} rules"}
            return {"active": False, "tool": "iptables", "details": "no rules configured"}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return {"active": False, "tool": "none", "details": "no firewall found"}

    def check_system_updates(self) -> list[str]:
        """Return list of available security update descriptions."""
        updates = []
        # Try apt (Debian/Ubuntu)
        try:
            result = subprocess.run(
                ["apt", "list", "--upgradable"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                lines = [l for l in result.stdout.strip().split("\n")
                         if l and not l.startswith("Listing")]
                security = [l for l in lines if "security" in l.lower()]
                if security:
                    updates.append(f"{len(security)} security updates (apt)")
                elif len(lines) > 10:
                    updates.append(f"{len(lines)} package updates (apt)")
            return updates
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Try dnf (Fedora/RHEL)
        try:
            result = subprocess.run(
                ["dnf", "check-update", "--security", "-q"],
                capture_output=True, text=True, timeout=30,
            )
            lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
            if lines:
                updates.append(f"{len(lines)} security updates (dnf)")
            return updates
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Try pacman (Arch)
        try:
            result = subprocess.run(
                ["pacman", "-Qu"], capture_output=True, text=True, timeout=30,
            )
            lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
            if lines:
                updates.append(f"{len(lines)} package updates (pacman)")
            return updates
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return updates

    def check_ssh_config(self) -> dict:
        """Return {"exists": bool, "issues": list[str]}."""
        sshd_config = Path("/etc/ssh/sshd_config")
        if not sshd_config.exists():
            return {"exists": False, "issues": []}

        try:
            content = sshd_config.read_text()
        except PermissionError:
            return {"exists": True, "issues": ["cannot read — permission denied"]}

        config = {}
        for line in content.lower().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                config[parts[0]] = parts[1]

        issues = []
        if config.get("permitrootlogin") not in ("no", "prohibit-password"):
            issues.append("root login allowed")
        if config.get("passwordauthentication") == "yes":
            issues.append("password auth enabled")
        if config.get("permitemptypasswords") == "yes":
            issues.append("empty passwords allowed")
        if config.get("port", "22") == "22":
            issues.append("default port 22")

        return {"exists": True, "issues": issues}

    def check_sudoers(self) -> dict:
        """Return {"nopasswd_all": bool}."""
        try:
            result = subprocess.run(
                ["sudo", "-l", "-n"],
                capture_output=True, text=True, timeout=10,
            )
            has_nopasswd = "NOPASSWD" in result.stdout and "ALL" in result.stdout
            return {"nopasswd_all": has_nopasswd}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {"nopasswd_all": False}

    def elevate_command(self, cmd: list[str]) -> list[str]:
        if shutil.which("pkexec"):
            return ["pkexec"] + cmd
        return ["sudo"] + cmd
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_platform.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/platform.py core/platform_backends/ tests/test_platform.py
git commit -m "feat: add Linux platform backend — notifications, sounds, firewall, updates"
```

---

### Task 3: macOS backend

**Files:**
- Create: `core/platform_backends/macos.py`
- Modify: `tests/test_platform.py`

- [ ] **Step 1: Write failing tests for macOS backend**

```python
# append to tests/test_platform.py
from core.platform_backends.macos import MacOSBackend


class TestMacOSBackend:
    def setup_method(self):
        self.backend = MacOSBackend()

    def test_config_dir(self):
        d = self.backend.config_dir()
        assert "Library/Application Support/claude-monitor" in str(d)

    def test_cache_dir(self):
        d = self.backend.cache_dir()
        assert "Library/Caches/claude-monitor" in str(d)

    @patch("subprocess.Popen")
    def test_notify(self, mock_popen):
        self.backend.notify("Test", "Hello", "normal")
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert "osascript" in args

    @patch("subprocess.Popen")
    def test_play_sound(self, mock_popen):
        self.backend.play_sound(Path("/tmp/test.wav"))
        args = mock_popen.call_args[0][0]
        assert "afplay" in args

    @patch("subprocess.Popen")
    def test_open_url(self, mock_popen):
        self.backend.open_url("https://example.com")
        args = mock_popen.call_args[0][0]
        assert "open" in args

    def test_elevate_command(self):
        cmd = self.backend.elevate_command(["pfctl", "-e"])
        assert "osascript" in cmd[0] or "sudo" in cmd[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_platform.py::TestMacOSBackend -v`
Expected: FAIL

- [ ] **Step 3: Implement macOS backend**

```python
# core/platform_backends/macos.py
"""macOS platform backend."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


class MacOSBackend:
    def config_dir(self) -> Path:
        return Path.home() / "Library" / "Application Support" / "claude-monitor"

    def cache_dir(self) -> Path:
        return Path.home() / "Library" / "Caches" / "claude-monitor"

    def data_dir(self) -> Path:
        return Path.home() / "Library" / "Application Support" / "claude-monitor"

    def notify(self, title: str, message: str, urgency: str = "normal") -> None:
        script = f'display notification "{message}" with title "{title}"'
        try:
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            log.warning("osascript not found")

    def play_sound(self, path: Path) -> None:
        try:
            subprocess.Popen(
                ["afplay", str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            log.warning("afplay not found")

    def open_url(self, url: str) -> None:
        try:
            subprocess.Popen(
                ["open", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            log.warning("open not found")

    def open_file(self, path: Path) -> None:
        self.open_url(str(path))

    def check_firewall(self) -> dict:
        try:
            # Application firewall
            result = subprocess.run(
                ["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"],
                capture_output=True, text=True, timeout=10,
            )
            if "enabled" in result.stdout.lower():
                return {"active": True, "tool": "socketfilterfw", "details": result.stdout.strip()}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # pf firewall
        try:
            result = subprocess.run(
                ["pfctl", "-s", "info"], capture_output=True, text=True, timeout=10,
            )
            if "enabled" in result.stderr.lower() or "enabled" in result.stdout.lower():
                return {"active": True, "tool": "pf", "details": "pf is enabled"}
            return {"active": False, "tool": "pf", "details": "pf is disabled"}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return {"active": False, "tool": "none", "details": "no firewall detected"}

    def check_system_updates(self) -> list[str]:
        try:
            result = subprocess.run(
                ["softwareupdate", "-l"],
                capture_output=True, text=True, timeout=60,
            )
            lines = [l.strip() for l in result.stdout.split("\n")
                     if l.strip() and "Security" in l]
            if lines:
                return [f"{len(lines)} security updates (softwareupdate)"]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return []

    def check_ssh_config(self) -> dict:
        # macOS uses same path as Linux
        sshd_config = Path("/etc/ssh/sshd_config")
        if not sshd_config.exists():
            return {"exists": False, "issues": []}

        try:
            content = sshd_config.read_text()
        except PermissionError:
            return {"exists": True, "issues": ["cannot read — permission denied"]}

        config = {}
        for line in content.lower().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                config[parts[0]] = parts[1]

        issues = []
        if config.get("permitrootlogin") not in ("no", "prohibit-password"):
            issues.append("root login allowed")
        if config.get("passwordauthentication") == "yes":
            issues.append("password auth enabled")
        return {"exists": True, "issues": issues}

    def check_sudoers(self) -> dict:
        try:
            result = subprocess.run(
                ["sudo", "-l", "-n"],
                capture_output=True, text=True, timeout=10,
            )
            has_nopasswd = "NOPASSWD" in result.stdout and "ALL" in result.stdout
            return {"nopasswd_all": has_nopasswd}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {"nopasswd_all": False}

    def elevate_command(self, cmd: list[str]) -> list[str]:
        # Use osascript for GUI elevation prompt
        cmd_str = " ".join(cmd)
        return [
            "osascript", "-e",
            f'do shell script "{cmd_str}" with administrator privileges',
        ]
```

- [ ] **Step 4: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_platform.py::TestMacOSBackend -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/platform_backends/macos.py tests/test_platform.py
git commit -m "feat: add macOS platform backend — afplay, osascript, pf firewall"
```

---

### Task 4: Windows backend

**Files:**
- Create: `core/platform_backends/windows.py`
- Modify: `tests/test_platform.py`

- [ ] **Step 1: Write failing tests for Windows backend**

```python
# append to tests/test_platform.py
import os
from core.platform_backends.windows import WindowsBackend


class TestWindowsBackend:
    def setup_method(self):
        self.backend = WindowsBackend()

    def test_config_dir(self):
        d = self.backend.config_dir()
        assert "claude-monitor" in str(d)

    def test_cache_dir(self):
        d = self.backend.cache_dir()
        assert "claude-monitor" in str(d)

    @patch("subprocess.Popen")
    def test_notify_powershell(self, mock_popen):
        self.backend.notify("Test", "Hello")
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert "powershell" in args[0].lower() or "pwsh" in args[0].lower()

    @patch("subprocess.Popen")
    def test_open_url(self, mock_popen):
        self.backend.open_url("https://example.com")
        mock_popen.assert_called_once()

    def test_elevate_command(self):
        cmd = self.backend.elevate_command(["netsh", "advfirewall", "show"])
        assert "powershell" in cmd[0].lower() or "runas" in str(cmd).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_platform.py::TestWindowsBackend -v`
Expected: FAIL

- [ ] **Step 3: Implement Windows backend**

```python
# core/platform_backends/windows.py
"""Windows platform backend."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def _appdata() -> Path:
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))


def _localappdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))


class WindowsBackend:
    def config_dir(self) -> Path:
        return _appdata() / "claude-monitor"

    def cache_dir(self) -> Path:
        return _localappdata() / "claude-monitor" / "cache"

    def data_dir(self) -> Path:
        return _localappdata() / "claude-monitor" / "data"

    def notify(self, title: str, message: str, urgency: str = "normal") -> None:
        # PowerShell toast notification
        ps_script = (
            f'[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, '
            f'ContentType = WindowsRuntime] > $null; '
            f'$template = [Windows.UI.Notifications.ToastNotification]::new('
            f'[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent('
            f'[Windows.UI.Notifications.ToastTemplateType]::ToastText02)); '
            f'$textNodes = $template.GetElementsByTagName("text"); '
            f'$textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) > $null; '
            f'$textNodes.Item(1).AppendChild($template.CreateTextNode("{message}")) > $null; '
            f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('
            f'"claude-monitor").Show($template)'
        )
        try:
            subprocess.Popen(
                ["powershell", "-WindowStyle", "Hidden", "-Command", ps_script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError:
            log.warning("powershell not found")

    def play_sound(self, path: Path) -> None:
        # Use PowerShell to play sound (works without external deps)
        ps_cmd = f'(New-Object Media.SoundPlayer "{path}").PlaySync()'
        try:
            subprocess.Popen(
                ["powershell", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError:
            log.warning("powershell not found for sound playback")

    def open_url(self, url: str) -> None:
        try:
            os.startfile(url)  # type: ignore[attr-defined]  # Windows only
        except AttributeError:
            subprocess.Popen(["cmd", "/c", "start", "", url])

    def open_file(self, path: Path) -> None:
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except AttributeError:
            subprocess.Popen(["cmd", "/c", "start", "", str(path)])

    def check_firewall(self) -> dict:
        try:
            result = subprocess.run(
                ["netsh", "advfirewall", "show", "allprofiles", "state"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                active = "ON" in result.stdout.upper()
                return {"active": active, "tool": "advfirewall",
                        "details": result.stdout.strip()[:200]}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return {"active": False, "tool": "none", "details": "cannot check firewall"}

    def check_system_updates(self) -> list[str]:
        # winget upgrade
        try:
            result = subprocess.run(
                ["winget", "upgrade", "--include-unknown"],
                capture_output=True, text=True, timeout=30,
            )
            lines = [l for l in result.stdout.strip().split("\n")
                     if l.strip() and not l.startswith("-") and not l.startswith("Name")]
            if len(lines) > 2:
                return [f"{len(lines)} package updates (winget)"]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return []

    def check_ssh_config(self) -> dict:
        sshd_config = Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "ssh" / "sshd_config"
        if not sshd_config.exists():
            return {"exists": False, "issues": []}

        try:
            content = sshd_config.read_text()
        except PermissionError:
            return {"exists": True, "issues": ["cannot read — permission denied"]}

        config = {}
        for line in content.lower().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                config[parts[0]] = parts[1]

        issues = []
        if config.get("permitrootlogin") not in ("no", "prohibit-password"):
            issues.append("root login allowed")
        if config.get("passwordauthentication") == "yes":
            issues.append("password auth enabled")
        return {"exists": True, "issues": issues}

    def check_sudoers(self) -> dict:
        # Check if user is in Administrators group
        try:
            result = subprocess.run(
                ["net", "localgroup", "Administrators"],
                capture_output=True, text=True, timeout=10,
            )
            username = os.environ.get("USERNAME", "")
            is_admin = username.lower() in result.stdout.lower()
            return {"nopasswd_all": is_admin}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {"nopasswd_all": False}

    def elevate_command(self, cmd: list[str]) -> list[str]:
        cmd_str = " ".join(cmd)
        return [
            "powershell", "-Command",
            f"Start-Process -Verb RunAs -FilePath '{cmd[0]}' -ArgumentList '{' '.join(cmd[1:])}'",
        ]
```

- [ ] **Step 4: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_platform.py::TestWindowsBackend -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/platform_backends/windows.py tests/test_platform.py
git commit -m "feat: add Windows platform backend — toast notifications, advfirewall, winget"
```

---

### Task 5: Wire platform into alerts.py

**Files:**
- Modify: `core/alerts.py`

- [ ] **Step 1: Write failing test for cross-platform alerts**

```python
# append to tests/test_alerts.py
from unittest.mock import patch, MagicMock

def test_alert_manager_uses_platform_notify():
    """AlertManager should delegate to platform backend, not hardcode notify-send."""
    from core.alerts import AlertManager
    from core.plugin import Alert

    config = {
        "sounds": {"enabled": False},
        "alerts": {"cooldown_seconds": 0, "desktop_notifications": True},
    }
    mgr = AlertManager(config)
    alert = Alert(source="test", severity="warning", title="Test", message="msg")

    mock_backend = MagicMock()
    with patch("core.alerts.get_platform", return_value=mock_backend):
        mgr.send_desktop(alert)
        mock_backend.notify.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_alerts.py::test_alert_manager_uses_platform_notify -v`
Expected: FAIL

- [ ] **Step 3: Rewrite alerts.py to use platform backend**

Replace `core/alerts.py` content:

```python
"""Centralized alert manager — cross-platform notifications + sounds."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from pathlib import Path

from core.platform import get_platform
from core.plugin import Alert

log = logging.getLogger(__name__)

_URGENCY_MAP = {
    "critical": "critical",
    "warning": "warning",
    "info": "info",
}


def _project_root() -> Path:
    current = Path(__file__).resolve().parent
    for parent in [current, current.parent, current.parent.parent]:
        if (parent / "pyproject.toml").exists() or (parent / "sounds").is_dir():
            return parent
    return current.parent


class AlertManager:
    def __init__(self, config: dict):
        self._config = config
        self._fired: dict[str, float] = {}
        self._cooldown = config["alerts"]["cooldown_seconds"]
        self._platform = get_platform()

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
        urgency = _URGENCY_MAP.get(alert.severity, "normal")
        self._platform.notify(
            f"[{alert.source}] {alert.title}",
            alert.message,
            urgency,
        )

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

        sound_files = [f for f in sound_dir.iterdir()
                       if f.suffix.lower() in (".mp3", ".wav", ".ogg", ".flac")]
        if not sound_files:
            log.warning("No sound files in %s", sound_dir)
            return

        sound_path = random.choice(sound_files)
        self._platform.play_sound(sound_path)

    def _find_sound_dir(self, mode: str) -> Path | None:
        root = _project_root()
        # Try mode-specific directory first
        mode_dir = root / "sounds" / mode
        if mode_dir.is_dir():
            return mode_dir
        # Fallback to generic sounds
        sounds_dir = root / "sounds"
        if sounds_dir.is_dir():
            return sounds_dir
        return None

    def play_file(self, path: Path) -> None:
        """Play a specific sound file."""
        self._platform.play_sound(path)

    def process(self, alert: Alert) -> bool:
        if not self.should_fire(alert):
            return False
        self.mark_fired(alert)
        self.send_desktop(alert)
        self.play_sound(alert)
        return True
```

- [ ] **Step 4: Run full alert tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_alerts.py -v`
Expected: PASS (may need to fix existing tests that mock notify-send directly)

- [ ] **Step 5: Fix any existing test breakages**

Update `tests/test_alerts.py` to mock `core.alerts.get_platform` instead of `subprocess.Popen` / `notify-send`.

- [ ] **Step 6: Commit**

```bash
git add core/alerts.py tests/test_alerts.py
git commit -m "refactor: alerts use platform backend instead of hardcoded Linux commands"
```

---

### Task 6: Wire platform into security scanners

**Files:**
- Modify: `plugins/security_scan/scanners.py`

- [ ] **Step 1: Write failing test for platform-aware scanners**

```python
# append to tests/test_security_scanners.py
from unittest.mock import patch, MagicMock

def test_scan_firewall_uses_platform():
    """scan_firewall should delegate to platform backend."""
    mock_backend = MagicMock()
    mock_backend.check_firewall.return_value = {
        "active": False, "tool": "ufw", "details": "ufw is inactive"
    }
    with patch("plugins.security_scan.scanners.get_platform", return_value=mock_backend):
        from plugins.security_scan.scanners import scan_firewall
        findings = scan_firewall()
        mock_backend.check_firewall.assert_called_once()
        assert any("inactive" in f.description.lower() or "unprotected" in f.description.lower()
                    for f in findings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_security_scanners.py::test_scan_firewall_uses_platform -v`
Expected: FAIL

- [ ] **Step 3: Rewrite system-level scanners to use platform backend**

Replace `scan_firewall`, `scan_ssh_config`, `scan_system_updates`, `scan_sudoers` in `plugins/security_scan/scanners.py`:

```python
# At the top of the file, add:
from core.platform import get_platform

# Replace scan_firewall:
def scan_firewall() -> list[Finding]:
    """Check if firewall is active — cross-platform."""
    platform = get_platform()
    result = platform.check_firewall()
    findings = []
    if not result["active"]:
        details = result["details"]
        tool = result["tool"]
        if tool == "none":
            findings.append(Finding(
                "system", "high",
                "No firewall detected — system is open to network attacks",
                "firewall",
            ))
        else:
            findings.append(Finding(
                "system", "high",
                f"Firewall ({tool}) is inactive — {details}",
                tool,
            ))
    return findings


# Replace scan_ssh_config:
def scan_ssh_config() -> list[Finding]:
    """Check SSH server configuration — cross-platform."""
    platform = get_platform()
    result = platform.check_ssh_config()
    findings = []
    if not result["exists"]:
        return findings
    for issue in result["issues"]:
        severity = "critical" if "empty passwords" in issue else (
            "high" if "root login" in issue else "medium"
        )
        findings.append(Finding("system", severity, f"SSH: {issue}", "sshd_config"))
    return findings


# Replace scan_system_updates:
def scan_system_updates() -> list[Finding]:
    """Check for available security updates — cross-platform."""
    platform = get_platform()
    updates = platform.check_system_updates()
    findings = []
    for desc in updates:
        severity = "high" if "security" in desc.lower() else "medium"
        findings.append(Finding(
            "system", severity,
            f"{desc} — update your system",
            "updates",
        ))
    return findings


# Replace scan_sudoers:
def scan_sudoers() -> list[Finding]:
    """Check for risky admin configurations — cross-platform."""
    platform = get_platform()
    result = platform.check_sudoers()
    findings = []
    if result["nopasswd_all"]:
        findings.append(Finding(
            "system", "medium",
            "Current user has passwordless admin access for ALL commands",
            "sudoers",
        ))
    return findings
```

- [ ] **Step 4: Run security scanner tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_security_scanners.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/security_scan/scanners.py tests/test_security_scanners.py
git commit -m "refactor: security scanners use platform backend — cross-platform firewall, SSH, updates"
```

---

### Task 7: Wire platform into autodiscovery and config

**Files:**
- Modify: `core/autodiscovery.py`
- Modify: `core/config.py`

- [ ] **Step 1: Update config.py to use platform paths**

In `core/config.py`, add platform-aware config path resolution:

```python
# Add at top:
from core.platform import get_platform

# Modify load_config:
def load_config(path: Path | None = None) -> dict:
    """Load TOML config. Resolution: explicit path > MONITOR_CONFIG env > platform config dir > project root."""
    if path is None:
        env_path = os.environ.get("MONITOR_CONFIG")
        if env_path:
            path = Path(env_path)
        else:
            # Try platform config dir first
            platform_config = get_platform().config_dir() / "config.toml"
            if platform_config.exists():
                path = platform_config
            else:
                path = _project_root() / "config.toml"

    user_config = {}
    if path.exists():
        with open(path, "rb") as f:
            user_config = tomllib.load(f)

    return _deep_merge(DEFAULTS, user_config)
```

- [ ] **Step 2: Update autodiscovery.py Docker socket for Windows**

In `core/autodiscovery.py`, modify `_find_docker`:

```python
# Add at top:
import sys

# Modify _find_docker:
def _find_docker(config_socket: str | None = None) -> tuple[bool, str | None, object | None]:
    if docker is None:
        return False, "Docker SDK not installed. Install: pip install docker", None
    try:
        kwargs = {}
        if config_socket:
            kwargs["base_url"] = config_socket
        elif sys.platform == "win32":
            kwargs["base_url"] = "npipe:////./pipe/docker_engine"
        client = docker.from_env(**kwargs)
        client.ping()
        return True, None, client
    except PermissionError:
        if sys.platform == "win32":
            return False, "Permission denied. Run as Administrator or add user to docker-users group", None
        return False, "Permission denied. Fix: sudo usermod -aG docker $USER && newgrp docker", None
    except Exception as e:
        err = str(e)
        if "FileNotFoundError" in err or "No such file" in err:
            return False, "Docker socket not found. Is Docker running?", None
        if "Connection refused" in err:
            return False, "Docker daemon not responding. Start Docker Desktop or docker service", None
        return False, f"Docker error: {err}", None
```

- [ ] **Step 3: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_config.py tests/test_autodiscovery.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add core/config.py core/autodiscovery.py
git commit -m "refactor: config and autodiscovery use platform paths, Windows Docker support"
```

---

### Task 8: Delete dead code

**Files:**
- Delete: `core/analyzer.py`
- Delete: `claude_nagger/cli/app.py`
- Delete: `claude_nagger/cli/tui.py`
- Delete: `claude_nagger/gui/app.py`
- Delete: `claude_nagger/gui/popup.py`
- Delete: `claude_nagger/core/sounds.py` (if exists)

- [ ] **Step 1: Verify nothing imports these files**

Run: `cd /home/dchuprina/claude-monitor && grep -r "from claude_nagger.cli" --include="*.py" .`
Run: `cd /home/dchuprina/claude-monitor && grep -r "from claude_nagger.gui.app" --include="*.py" .`
Run: `cd /home/dchuprina/claude-monitor && grep -r "from claude_nagger.gui.popup" --include="*.py" .`
Run: `cd /home/dchuprina/claude-monitor && grep -r "from core.analyzer" --include="*.py" .`
Run: `cd /home/dchuprina/claude-monitor && grep -r "import analyzer" --include="*.py" .`

Expected: No results, or only self-imports. If anything imports these, fix the import first.

- [ ] **Step 2: Delete the files**

```bash
rm -f core/analyzer.py
rm -f claude_nagger/cli/app.py claude_nagger/cli/tui.py
rm -f claude_nagger/gui/app.py claude_nagger/gui/popup.py
rm -f claude_nagger/core/sounds.py
```

- [ ] **Step 3: Run full test suite to verify nothing breaks**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove dead code — analyzer.py, CLI/TUI, standalone GUI, popup"
```

---

### Task 9: Relocate claude_nagger core modules to core/

**Files:**
- Move: `claude_nagger/core/calculator.py` → `core/calculator.py`
- Move: `claude_nagger/core/models.py` → `core/models.py`
- Move: `claude_nagger/core/analyzer.py` → `core/usage_analyzer.py`
- Move: `claude_nagger/core/tips.py` → `core/tips.py`
- Move: `claude_nagger/core/parser.py` → `core/token_parser.py`

- [ ] **Step 1: Copy files to new locations**

```bash
cp claude_nagger/core/calculator.py core/calculator.py
cp claude_nagger/core/models.py core/models.py
cp claude_nagger/core/analyzer.py core/usage_analyzer.py
cp claude_nagger/core/tips.py core/tips.py
cp claude_nagger/core/parser.py core/token_parser.py
```

- [ ] **Step 2: Fix imports in moved files**

In each moved file, replace:
- `from .models import` → `from core.models import`
- `from .analyzer import` → `from core.usage_analyzer import`
- `from .calculator import` → `from core.calculator import`

In `core/tips.py`:
```python
# Old:
from .models import TokenStats, CostBreakdown, Tip
from .analyzer import Analyzer
# New:
from core.models import TokenStats, CostBreakdown, Tip
from core.usage_analyzer import Analyzer
```

In `core/calculator.py`:
```python
# Old:
from .models import TokenStats, ModelUsage, CostBreakdown
# New:
from core.models import TokenStats, ModelUsage, CostBreakdown
```

- [ ] **Step 3: Update all imports across the codebase**

In `gui/app.py`, replace:
```python
# Old:
from claude_nagger.core.parser import TokenParser
from claude_nagger.core.calculator import CostCalculator
from claude_nagger.core.analyzer import Analyzer
from claude_nagger.nagger.messages import get_nag_message, get_nag_level
# New:
from core.token_parser import TokenParser
from core.calculator import CostCalculator
from core.usage_analyzer import Analyzer
from core.nagger.messages import get_nag_message, get_nag_level
```

In `gui/pages/overview.py`, `gui/pages/analytics.py`, `gui/pages/tips.py`, `gui/pages/usage.py`:
Replace `from claude_nagger.` imports with `from core.` imports.

- [ ] **Step 4: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: move claude_nagger/core/ modules to core/ — calculator, models, parser, tips"
```

---

### Task 10: Relocate i18n and nagger modules

**Files:**
- Move: `claude_nagger/i18n/` → `i18n/`
- Move: `claude_nagger/nagger/` → `core/nagger/`

- [ ] **Step 1: Copy files**

```bash
mkdir -p i18n core/nagger
cp claude_nagger/i18n/__init__.py i18n/__init__.py
cp claude_nagger/i18n/en.py i18n/en.py
cp claude_nagger/i18n/ua.py i18n/ua.py
cp claude_nagger/nagger/__init__.py core/nagger/__init__.py
cp claude_nagger/nagger/messages.py core/nagger/messages.py
cp claude_nagger/nagger/hasselhoff.py core/nagger/hasselhoff.py
```

- [ ] **Step 2: Fix imports in moved files**

In `i18n/__init__.py`:
```python
# Adjust relative imports if they reference claude_nagger
```

In `core/nagger/messages.py`:
```python
# Old:
from claude_nagger.i18n import get_language
# New:
from i18n import get_language
```

In `core/nagger/hasselhoff.py`:
```python
# Old:
from claude_nagger.i18n import get_language
# New:
from i18n import get_language
```

- [ ] **Step 3: Update all imports across the codebase**

Find and replace globally:
- `from claude_nagger.i18n import` → `from i18n import`
- `from claude_nagger.nagger.` → `from core.nagger.`

Files to update:
- `gui/app.py`
- `gui/pages/overview.py`
- `gui/pages/settings.py`
- `gui/pages/hasselhoff_wizard.py`
- `gui/pages/tips.py`
- `gui/pages/usage.py`
- `core/tips.py`

- [ ] **Step 4: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: move i18n/ and nagger/ out of claude_nagger — flatten module structure"
```

---

### Task 11: Integrate discover.py into gui/pages/ and remove claude_nagger package

**Files:**
- Move: `claude_nagger/gui/discover.py` → `gui/pages/discover.py`
- Move: `claude_nagger/gui/usage.py` → integrate into `gui/pages/usage.py`
- Delete: entire `claude_nagger/` directory

- [ ] **Step 1: Copy discover.py**

```bash
cp claude_nagger/gui/discover.py gui/pages/discover.py
```

- [ ] **Step 2: Fix imports in gui/pages/discover.py**

```python
# Old:
from claude_nagger.i18n import get_language
# New:
from i18n import get_language
```

- [ ] **Step 3: Update gui/pages/usage.py to be self-contained**

Read `claude_nagger/gui/usage.py`, copy its content directly into `gui/pages/usage.py` replacing the delegation pattern. Fix imports to use `core.` instead of `claude_nagger.core.`.

- [ ] **Step 4: Update gui/app.py imports**

```python
# Old:
from claude_nagger.gui.discover import DiscoverTab
# New:
from gui.pages.discover import DiscoverTab
```

- [ ] **Step 5: Delete claude_nagger/ entirely**

```bash
rm -rf claude_nagger/
```

- [ ] **Step 6: Run full test suite**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 7: Update any test imports that reference claude_nagger**

Check and fix:
```bash
grep -r "claude_nagger" tests/ --include="*.py"
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: remove claude_nagger package — all modules integrated into core/ and gui/"
```

---

### Task 12: Update settings.py to save config cross-platform

**Files:**
- Modify: `gui/pages/settings.py`

- [ ] **Step 1: Fix settings save to use platform config path**

Replace the `_apply` method in `gui/pages/settings.py`:

```python
def _apply(self):
    """Save settings to config.toml — cross-platform."""
    import tomllib
    from core.platform import get_platform

    self._config["general"]["language"] = self.lang_combo.currentText()
    self._config["sounds"]["enabled"] = self.sound_enabled.isChecked()
    self._config["alerts"]["desktop_notifications"] = self.notif_enabled.isChecked()
    self._config["alerts"]["cooldown_seconds"] = self.cooldown_spin.value()

    self._config.setdefault("alert_filters", {})
    self._config["alert_filters"]["docker"] = self.alert_docker.isChecked()
    self._config["alert_filters"]["security"] = self.alert_security.isChecked()
    self._config["alert_filters"]["ports"] = self.alert_ports.isChecked()
    self._config["alert_filters"]["usage"] = self.alert_usage.isChecked()

    # Write config — try platform dir first, fallback to project root
    platform = get_platform()
    config_dir = platform.config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"

    try:
        # Use tomli_w if available, else manual TOML write
        try:
            import tomli_w
            with open(config_path, "wb") as f:
                tomli_w.dump(self._config, f)
        except ImportError:
            import toml
            with open(config_path, "w") as f:
                toml.dump(self._config, f)

        self.status_label.setText(_t("saved_ok"))
        self.status_label.setStyleSheet("color: #006600; font-style: italic; padding: 4px;")
        self.settings_changed.emit(self._config)
    except Exception as e:
        self.status_label.setText(_t("save_error").format(e))
        self.status_label.setStyleSheet("color: #cc0000; font-style: italic; padding: 4px;")
```

- [ ] **Step 2: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add gui/pages/settings.py
git commit -m "refactor: settings save uses platform config dir — cross-platform"
```

---

### Task 13: Final validation

- [ ] **Step 1: Run full test suite**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Verify no more claude_nagger references**

Run: `cd /home/dchuprina/claude-monitor && grep -r "claude_nagger" --include="*.py" . | grep -v __pycache__`
Expected: No results

- [ ] **Step 3: Verify core/analyzer.py is gone**

Run: `ls core/analyzer.py 2>&1`
Expected: "No such file or directory"

- [ ] **Step 4: Verify platform imports work**

Run: `cd /home/dchuprina/claude-monitor && python -c "from core.platform import get_platform; p = get_platform(); print(f'Platform: {type(p).__name__}, config: {p.config_dir()}')"`
Expected: "Platform: LinuxBackend, config: /home/dchuprina/.config/claude-monitor"

- [ ] **Step 5: Commit any final fixes**

```bash
git add -A
git commit -m "chore: Phase 0+1 complete — cross-platform layer + dead code cleanup"
```
