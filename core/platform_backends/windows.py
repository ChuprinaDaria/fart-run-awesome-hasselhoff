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
        ps_script = (
            '[Windows.UI.Notifications.ToastNotificationManager, '
            'Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; '
            '$template = [Windows.UI.Notifications.ToastNotification]::new('
            '[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent('
            '[Windows.UI.Notifications.ToastTemplateType]::ToastText02)); '
            '$textNodes = $template.GetElementsByTagName("text"); '
            f'$textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) > $null; '
            f'$textNodes.Item(1).AppendChild($template.CreateTextNode("{message}")) > $null; '
            '[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('
            '"claude-monitor").Show($template)'
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
            os.startfile(url)  # type: ignore[attr-defined]
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
        sshd_config = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "ssh" / "sshd_config"
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
                ["net", "localgroup", "Administrators"],
                capture_output=True, text=True, timeout=10,
            )
            username = os.environ.get("USERNAME", "")
            is_admin = username.lower() in result.stdout.lower()
            return {"nopasswd_all": is_admin}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {"nopasswd_all": False}

    def elevate_command(self, cmd: list[str]) -> list[str]:
        args_str = " ".join(cmd[1:]) if len(cmd) > 1 else ""
        return [
            "powershell", "-Command",
            f"Start-Process -Verb RunAs -FilePath '{cmd[0]}' -ArgumentList '{args_str}'",
        ]
