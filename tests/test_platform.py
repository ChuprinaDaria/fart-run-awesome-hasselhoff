"""Tests for cross-platform abstraction layer."""

from unittest.mock import patch
from pathlib import Path

from core.platform import detect_platform, PlatformType, reset_platform


class TestPlatformDetection:
    def test_detect_linux(self):
        with patch("core.platform.sys.platform", "linux"):
            assert detect_platform() == PlatformType.LINUX

    def test_detect_macos(self):
        with patch("core.platform.sys.platform", "darwin"):
            assert detect_platform() == PlatformType.MACOS

    def test_detect_windows(self):
        with patch("core.platform.sys.platform", "win32"):
            assert detect_platform() == PlatformType.WINDOWS

    def test_detect_freebsd_falls_to_linux(self):
        with patch("core.platform.sys.platform", "freebsd"):
            assert detect_platform() == PlatformType.LINUX
