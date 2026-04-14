"""Centralized alert manager — notify-send + fart sounds."""

from __future__ import annotations

import subprocess
import time
from datetime import datetime
from pathlib import Path

from core.plugin import Alert

SEVERITY_SOUNDS = {
    "critical": "fart3.mp3",
    "warning": "fart1.mp3",
    "info": "fart5.mp3",
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
        self._fired: dict[str, float] = {}
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
        if start > end:
            return current >= start or current < end
        return start <= current < end

    def send_desktop(self, alert: Alert) -> None:
        if not self._config["alerts"]["desktop_notifications"]:
            return
        urgency = URGENCY_MAP.get(alert.severity, "normal")
        try:
            subprocess.Popen(
                ["notify-send", "-u", urgency, alert.title, alert.message],
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
