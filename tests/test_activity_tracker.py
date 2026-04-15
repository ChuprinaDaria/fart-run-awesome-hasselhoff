"""Tests for activity_tracker — git/docker/port change detection."""

import subprocess
from unittest.mock import patch

from core.activity_tracker import ActivityTracker


def test_find_git_binary():
    """Git binary found via shutil.which."""
    tracker = ActivityTracker("/tmp/fake")
    with patch("shutil.which", return_value="/usr/bin/git"):
        assert tracker._find_git() == "/usr/bin/git"


def test_find_git_binary_missing():
    """Returns None when git not installed."""
    tracker = ActivityTracker("/tmp/fake")
    with patch("shutil.which", return_value=None):
        assert tracker._find_git() is None


def test_is_git_repo_true(tmp_path):
    """Detects a git repo correctly."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
    tracker = ActivityTracker(str(tmp_path))
    assert tracker.is_git_repo() is True


def test_is_git_repo_false(tmp_path):
    """Non-git directory returns False."""
    tracker = ActivityTracker(str(tmp_path))
    assert tracker.is_git_repo() is False


def test_git_file_changes(tmp_path):
    """Detects added/modified/deleted files."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path), capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path), capture_output=True,
    )

    # Create and commit a file
    (tmp_path / "hello.py").write_text("print('hello')")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(tmp_path), capture_output=True,
    )

    # Modify file + add new one
    (tmp_path / "hello.py").write_text("print('hello world')")
    (tmp_path / "docker-compose.yml").write_text("version: '3'")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)

    tracker = ActivityTracker(str(tmp_path))
    changes = tracker.get_git_changes()

    paths = [c.path for c in changes]
    assert "docker-compose.yml" in paths
    assert "hello.py" in paths

    # docker-compose.yml should have an explanation
    dc = next(c for c in changes if c.path == "docker-compose.yml")
    assert "Docker" in dc.explanation


def test_git_recent_commits(tmp_path):
    """Gets recent commit messages."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path), capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path), capture_output=True,
    )
    (tmp_path / "a.py").write_text("x = 1")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add a"],
        cwd=str(tmp_path), capture_output=True,
    )

    tracker = ActivityTracker(str(tmp_path))
    commits = tracker.get_recent_commits(limit=5)
    assert len(commits) == 1
    assert "feat: add a" in commits[0]


def test_git_changes_no_git(tmp_path):
    """Gracefully returns empty when not a git repo."""
    tracker = ActivityTracker(str(tmp_path))
    changes = tracker.get_git_changes()
    assert changes == []


def test_git_changes_no_commits(tmp_path):
    """Gracefully handles repo with no commits yet."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
    (tmp_path / "new.py").write_text("x = 1")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)

    tracker = ActivityTracker(str(tmp_path))
    changes = tracker.get_git_changes()
    assert any(c.path == "new.py" for c in changes)
