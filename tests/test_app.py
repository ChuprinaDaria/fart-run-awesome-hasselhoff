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
