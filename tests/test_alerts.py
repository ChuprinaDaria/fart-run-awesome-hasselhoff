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
    assert manager.should_fire(a2) is False


def test_different_alerts_not_deduplicated(manager):
    a1 = Alert(source="docker", severity="critical", title="down", message="msg")
    a2 = Alert(source="docker", severity="warning", title="cpu high", message="msg")
    manager.mark_fired(a1)
    assert manager.should_fire(a2) is True


def test_quiet_hours(manager):
    with patch("core.alerts.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 4, 14, 2, 0, 0)
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        assert manager.is_quiet_hours() is True

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
