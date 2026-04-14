"""Centralized alert manager — desktop notifications + fart sounds."""

from __future__ import annotations

import logging
import random
import shutil
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
    current = Path(__file__).resolve().parent
    for parent in [current, current.parent, current.parent.parent]:
        if (parent / "pyproject.toml").exists() or (parent / "sounds").is_dir():
            return parent
    return current.parent


def _find_sound_dir() -> Path | None:
    root = _project_root()
    sounds = root / "sounds" / "farts"
    if sounds.is_dir():
        return sounds
    sounds_root = root / "sounds"
    if sounds_root.is_dir():
        return sounds_root
    log.warning("No sounds directory found at %s", root / "sounds")
    return None


class AlertManager:
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
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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
        if not self.should_fire(alert):
            return False
        self.mark_fired(alert)
        self.send_desktop(alert)
        self.play_sound(alert)
        return True
