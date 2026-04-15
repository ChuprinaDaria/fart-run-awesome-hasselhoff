"""Tests for snapshot manager."""

from core.models import EnvironmentSnapshot, SnapshotDiff


def test_snapshot_creation():
    s = EnvironmentSnapshot(
        id=1,
        timestamp="2026-04-15T14:30:00",
        label="Before AI session",
        project_dir="/tmp/test",
        git_branch="main",
        git_last_commit="abc1234 feat: init",
        git_tracked_count=42,
        git_dirty_files=["app.py"],
        containers=[{"name": "web", "image": "py", "status": "running"}],
        listening_ports=[{"port": 8000, "process": "python"}],
        config_checksums={".env": "abc123"},
    )
    assert s.label == "Before AI session"
    assert len(s.containers) == 1


def test_snapshot_diff_total():
    diff = SnapshotDiff(
        branch_changed=True,
        old_branch="main",
        new_branch="feature",
        containers_added=["redis"],
        ports_opened=[6379, 5555],
        configs_changed=[".env"],
    )
    assert diff.total_changes == 5
