"""Monitor alert manager for GUI — uses NaggerPopup-style notifications."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from core.plugin import Alert


SEVERITY_SOUNDS = {
    "critical": "fart3.mp3",
    "warning": "fart1.mp3",
    "info": "fart5.mp3",
}


def _find_sound_dir() -> Path | None:
    candidates = [
        Path.home() / "claude-nagger" / "sounds" / "farts",
        Path(__file__).parent.parent / "sounds",
        Path.home() / "bin" / "farts",
    ]
    for d in candidates:
        if d.is_dir():
            return d
    return None


class MonitorAlertManager:
    """Deduplicates alerts, shows desktop notifications, plays fart sounds."""

    def __init__(self, cooldown: int = 300):
        self._fired: dict[str, float] = {}
        self._cooldown = cooldown
        self._sound_dir = _find_sound_dir()

    def _key(self, alert: Alert) -> str:
        return f"{alert.source}:{alert.title}"

    def should_fire(self, alert: Alert) -> bool:
        key = self._key(alert)
        last = self._fired.get(key)
        if last is None:
            return True
        return (time.time() - last) > self._cooldown

    def process(self, alert: Alert) -> bool:
        if not self.should_fire(alert):
            return False
        self._fired[self._key(alert)] = time.time()
        self._notify(alert)
        self._play_sound(alert)
        return True

    def _notify(self, alert: Alert) -> None:
        urgency = {"critical": "critical", "warning": "normal", "info": "low"}.get(alert.severity, "normal")
        try:
            subprocess.Popen(
                ["notify-send", "-u", urgency,
                 f"💨 [{alert.source}] {alert.title}", alert.message],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    def _play_sound(self, alert: Alert) -> None:
        if not self._sound_dir:
            return
        sound_file = alert.sound or SEVERITY_SOUNDS.get(alert.severity)
        if not sound_file:
            return
        sound_path = self._sound_dir / sound_file
        if not sound_path.exists():
            return
        try:
            subprocess.Popen(["paplay", str(sound_path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            try:
                subprocess.Popen(["aplay", str(sound_path)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                pass
