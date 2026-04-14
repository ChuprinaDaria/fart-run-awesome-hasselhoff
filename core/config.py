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
