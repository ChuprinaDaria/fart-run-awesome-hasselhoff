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
        urgency = _URGENCY_MAP.get(alert.severity, "info")
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

        # Try severity-specific sound first
        severity = alert.severity
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

    def _find_sound_dir(self, mode: str) -> Path | None:
        root = _project_root()
        mode_dir = root / "sounds" / mode
        if mode_dir.is_dir():
            return mode_dir
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
