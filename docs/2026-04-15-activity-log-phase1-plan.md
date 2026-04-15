# Phase 1: Activity Log — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Activity Log page that shows git/docker/port changes in human language with directory picker, cross-platform (Linux/Mac/Windows).

**Architecture:** Three core modules (file_explainer, activity_tracker, models) feed data into a new GUI page. Git via subprocess, Docker/ports via existing SDK/psutil. Directory selected manually via file dialog.

**Tech Stack:** PyQt5, subprocess (git), docker SDK (existing), psutil (existing), shutil.which, pathlib

---

## File Structure

```
core/
  file_explainer.py       # pattern → human explanation mapping
  activity_tracker.py     # collect git diff, docker diff, port diff
  models.py               # + new dataclasses (FileChange, ActivityEntry, etc.)

gui/pages/
  activity.py             # Activity Log GUI page

i18n/
  en.py                   # + activity log strings
  ua.py                   # + activity log strings

tests/
  test_file_explainer.py  # file_explainer tests
  test_activity_tracker.py # activity_tracker tests
```

Modified:
- `gui/app.py` — register Activity Log page + sidebar item
- `core/models.py` — add new dataclasses
- `i18n/en.py` — add ~30 strings
- `i18n/ua.py` — add ~30 strings

---

### Task 1: Data Models

**Files:**
- Modify: `core/models.py`
- Test: `tests/test_activity_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_activity_models.py
"""Tests for Activity Log data models."""

from core.models import FileChange, DockerChange, PortChange, ActivityEntry


def test_file_change_creation():
    fc = FileChange(
        path="docker-compose.yml",
        status="modified",
        additions=15,
        deletions=2,
        explanation="Docker config — which services run",
    )
    assert fc.path == "docker-compose.yml"
    assert fc.status == "modified"
    assert fc.additions == 15
    assert fc.deletions == 2
    assert fc.explanation == "Docker config — which services run"


def test_file_change_defaults():
    fc = FileChange(path="README.md", status="added")
    assert fc.additions == 0
    assert fc.deletions == 0
    assert fc.explanation == ""


def test_docker_change_creation():
    dc = DockerChange(
        name="redis",
        image="redis:7-alpine",
        status="new",
        ports=["6379"],
        explanation="In-memory cache/queue",
    )
    assert dc.name == "redis"
    assert dc.status == "new"


def test_port_change_creation():
    pc = PortChange(port=6379, process="redis", status="new", explanation="Redis cache")
    assert pc.port == 6379
    assert pc.status == "new"


def test_activity_entry_creation():
    entry = ActivityEntry(
        timestamp="2026-04-15T14:35:00",
        files=[FileChange("a.py", "added")],
        docker_changes=[],
        port_changes=[],
        commits=["abc1234 feat: add worker"],
        project_dir="/home/user/project",
    )
    assert len(entry.files) == 1
    assert entry.project_dir == "/home/user/project"
    assert entry.commits == ["abc1234 feat: add worker"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_activity_models.py -v`
Expected: FAIL with ImportError (FileChange not defined)

- [ ] **Step 3: Write minimal implementation**

Add to `core/models.py` at the end:

```python
@dataclass
class FileChange:
    path: str
    status: str  # "added", "modified", "deleted", "renamed"
    additions: int = 0
    deletions: int = 0
    explanation: str = ""


@dataclass
class DockerChange:
    name: str
    image: str
    status: str  # "new", "removed", "restarted", "crashed"
    ports: list[str] = field(default_factory=list)
    explanation: str = ""


@dataclass
class PortChange:
    port: int
    process: str
    status: str  # "new", "closed"
    explanation: str = ""


@dataclass
class ActivityEntry:
    timestamp: str
    files: list[FileChange] = field(default_factory=list)
    docker_changes: list[DockerChange] = field(default_factory=list)
    port_changes: list[PortChange] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)
    project_dir: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_activity_models.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add core/models.py tests/test_activity_models.py
git commit -m "feat: add Activity Log data models (FileChange, DockerChange, PortChange, ActivityEntry)"
```

---

### Task 2: File Explainer

**Files:**
- Create: `core/file_explainer.py`
- Test: `tests/test_file_explainer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_file_explainer.py
"""Tests for file_explainer — pattern → human explanation mapping."""

from core.file_explainer import explain_file


def test_docker_compose():
    assert "Docker" in explain_file("docker-compose.yml")


def test_dockerfile():
    assert "Docker" in explain_file("Dockerfile")
    assert "Docker" in explain_file("backend/Dockerfile")


def test_requirements():
    assert "Python" in explain_file("requirements.txt")
    assert "dependenc" in explain_file("requirements.txt").lower()


def test_package_json():
    assert "Node" in explain_file("package.json") or "JS" in explain_file("package.json")


def test_env_file():
    result = explain_file(".env")
    assert "variable" in result.lower() or "secret" in result.lower() or "config" in result.lower()


def test_migration():
    result = explain_file("apps/users/migrations/0002_add_email.py")
    assert "migration" in result.lower() or "database" in result.lower()


def test_python_file():
    result = explain_file("src/worker.py")
    assert result  # not empty, generic explanation


def test_unknown_file():
    result = explain_file("something.xyz")
    assert result  # still returns something, not empty


def test_gitignore():
    result = explain_file(".gitignore")
    assert "git" in result.lower() or "ignore" in result.lower()


def test_makefile():
    result = explain_file("Makefile")
    assert result


def test_github_actions():
    result = explain_file(".github/workflows/ci.yml")
    assert "CI" in result or "pipeline" in result.lower() or "action" in result.lower()


def test_alembic_migration():
    result = explain_file("alembic/versions/abc123_add_users.py")
    assert "migration" in result.lower() or "database" in result.lower()


def test_pyproject_toml():
    result = explain_file("pyproject.toml")
    assert "Python" in result or "project" in result.lower()


def test_lock_files():
    result = explain_file("package-lock.json")
    assert "lock" in result.lower() or "dependenc" in result.lower()
    result2 = explain_file("poetry.lock")
    assert "lock" in result2.lower() or "dependenc" in result2.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_file_explainer.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write implementation**

```python
# core/file_explainer.py
"""Map file paths to human-readable explanations.

Uses pattern matching on file names, extensions, and directory paths.
No AI calls — pure heuristic mapping.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath


# (compiled_regex, explanation) — first match wins
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Docker
    (re.compile(r"(^|/)docker-compose[^/]*\.ya?ml$", re.I), "Docker config — which services run"),
    (re.compile(r"(^|/)Dockerfile(\.[^/]*)?$", re.I), "Docker image — how container is built"),
    (re.compile(r"(^|/)\.dockerignore$", re.I), "Docker ignore — files excluded from build"),

    # CI/CD
    (re.compile(r"\.github/workflows/.*\.ya?ml$", re.I), "GitHub Actions CI/CD pipeline"),
    (re.compile(r"\.gitlab-ci\.ya?ml$", re.I), "GitLab CI/CD pipeline"),
    (re.compile(r"(^|/)Jenkinsfile$", re.I), "Jenkins CI/CD pipeline"),

    # Python
    (re.compile(r"(^|/)requirements.*\.txt$", re.I), "Python dependencies — what gets installed"),
    (re.compile(r"(^|/)pyproject\.toml$", re.I), "Python project config — dependencies & tools"),
    (re.compile(r"(^|/)setup\.(py|cfg)$", re.I), "Python package config"),
    (re.compile(r"(^|/)Pipfile(\.lock)?$", re.I), "Python dependencies (Pipenv)"),
    (re.compile(r"(^|/)poetry\.lock$", re.I), "Python dependency lock — exact versions pinned"),
    (re.compile(r"/migrations/.*\.py$", re.I), "DB migration — changes database structure"),
    (re.compile(r"alembic/versions/.*\.py$", re.I), "DB migration (Alembic) — changes database structure"),

    # JS/Node
    (re.compile(r"(^|/)package\.json$", re.I), "Node.js/JS project config — dependencies & scripts"),
    (re.compile(r"(^|/)package-lock\.json$", re.I), "JS dependency lock — exact versions pinned"),
    (re.compile(r"(^|/)yarn\.lock$", re.I), "JS dependency lock (Yarn) — exact versions pinned"),
    (re.compile(r"(^|/)pnpm-lock\.yaml$", re.I), "JS dependency lock (pnpm) — exact versions pinned"),
    (re.compile(r"(^|/)tsconfig.*\.json$", re.I), "TypeScript config"),
    (re.compile(r"(^|/)webpack\.config\.", re.I), "Webpack bundler config"),
    (re.compile(r"(^|/)vite\.config\.", re.I), "Vite bundler config"),

    # Environment & secrets
    (re.compile(r"(^|/)\.env(\.[^/]*)?$", re.I), "Environment variables — secrets, keys, settings"),
    (re.compile(r"(^|/)\.env\.example$", re.I), "Env template — example config (no real secrets)"),

    # Git
    (re.compile(r"(^|/)\.gitignore$", re.I), "Git ignore — files excluded from version control"),
    (re.compile(r"(^|/)\.gitattributes$", re.I), "Git attributes — line endings, diff settings"),

    # Build & automation
    (re.compile(r"(^|/)Makefile$", re.I), "Makefile — build/automation commands"),
    (re.compile(r"(^|/)Procfile$", re.I), "Procfile — how app runs in production"),

    # Config
    (re.compile(r"(^|/)nginx.*\.conf$", re.I), "Nginx web server config"),
    (re.compile(r"(^|/)\.eslintrc", re.I), "ESLint config — JS code style rules"),
    (re.compile(r"(^|/)\.prettierrc", re.I), "Prettier config — code formatting rules"),
    (re.compile(r"(^|/)CLAUDE\.md$", re.I), "Claude Code instructions — AI assistant config"),

    # Terraform / IaC
    (re.compile(r"\.tf$", re.I), "Terraform — infrastructure as code"),
    (re.compile(r"(^|/)terraform\.tfvars", re.I), "Terraform variables"),

    # Kubernetes
    (re.compile(r"(^|/)k8s/.*\.ya?ml$", re.I), "Kubernetes config"),
    (re.compile(r"(^|/)helm/.*\.ya?ml$", re.I), "Helm chart — Kubernetes package config"),
]

# Extension-based fallback (less specific)
_EXT_MAP: dict[str, str] = {
    ".py": "Python source code",
    ".js": "JavaScript source code",
    ".ts": "TypeScript source code",
    ".jsx": "React component (JSX)",
    ".tsx": "React component (TypeScript)",
    ".vue": "Vue.js component",
    ".svelte": "Svelte component",
    ".html": "HTML page",
    ".css": "Stylesheet",
    ".scss": "SASS stylesheet",
    ".sql": "SQL query/script",
    ".sh": "Shell script",
    ".bash": "Bash script",
    ".ps1": "PowerShell script",
    ".bat": "Windows batch script",
    ".cmd": "Windows command script",
    ".md": "Documentation (Markdown)",
    ".rst": "Documentation (reStructuredText)",
    ".json": "JSON data/config",
    ".yaml": "YAML config",
    ".yml": "YAML config",
    ".toml": "TOML config",
    ".ini": "INI config",
    ".cfg": "Config file",
    ".xml": "XML data/config",
    ".go": "Go source code",
    ".rs": "Rust source code",
    ".java": "Java source code",
    ".kt": "Kotlin source code",
    ".rb": "Ruby source code",
    ".php": "PHP source code",
    ".c": "C source code",
    ".cpp": "C++ source code",
    ".h": "C/C++ header file",
    ".cs": "C# source code",
    ".swift": "Swift source code",
    ".r": "R script",
    ".dart": "Dart source code",
    ".lua": "Lua script",
    ".ex": "Elixir source code",
    ".erl": "Erlang source code",
}


def explain_file(path: str) -> str:
    """Return human-readable explanation for a file path.

    Checks specific patterns first, then falls back to extension mapping.
    Always returns a non-empty string.
    """
    # Normalise separators (Windows backslashes → forward slashes)
    normalised = path.replace("\\", "/")

    # Try specific patterns first
    for pattern, explanation in _PATTERNS:
        if pattern.search(normalised):
            return explanation

    # Extension fallback
    suffix = PurePosixPath(normalised).suffix.lower()
    if suffix in _EXT_MAP:
        return _EXT_MAP[suffix]

    # Last resort
    return "Project file"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_file_explainer.py -v`
Expected: PASS (all 14 tests)

- [ ] **Step 5: Commit**

```bash
git add core/file_explainer.py tests/test_file_explainer.py
git commit -m "feat: add file_explainer — pattern-based human explanations for files"
```

---

### Task 3: Activity Tracker (git)

**Files:**
- Create: `core/activity_tracker.py`
- Test: `tests/test_activity_tracker.py`

- [ ] **Step 1: Write the failing test for git detection**

```python
# tests/test_activity_tracker.py
"""Tests for activity_tracker — git/docker/port change detection."""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

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
    # Init repo + initial commit
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
    # Should still return the staged new file
    assert any(c.path == "new.py" for c in changes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_activity_tracker.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write implementation**

```python
# core/activity_tracker.py
"""Collect environment changes — git, docker, ports.

Cross-platform: Linux, macOS, Windows.
Git via subprocess (shell=False, UTF-8 forced).
Docker via existing docker SDK. Ports via psutil.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from core.file_explainer import explain_file
from core.models import (
    FileChange, DockerChange, PortChange, ActivityEntry,
)

log = logging.getLogger(__name__)


class ActivityTracker:
    """Track changes in a project directory."""

    def __init__(self, project_dir: str):
        self._dir = project_dir
        self._prev_containers: dict[str, dict] = {}
        self._prev_ports: set[int] = set()

    def _find_git(self) -> str | None:
        """Find git binary. Cross-platform via shutil.which."""
        return shutil.which("git")

    def _run_git(self, *args: str) -> str | None:
        """Run a git command in project dir. Returns stdout or None on error."""
        git = self._find_git()
        if not git:
            return None
        try:
            result = subprocess.run(
                [git, *args],
                cwd=self._dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if result.returncode != 0:
                return None
            return result.stdout
        except (subprocess.TimeoutExpired, OSError) as e:
            log.warning("git command failed: %s", e)
            return None

    def is_git_repo(self) -> bool:
        """Check if project_dir is inside a git repository."""
        output = self._run_git("rev-parse", "--is-inside-work-tree")
        return output is not None and output.strip() == "true"

    def get_git_changes(self) -> list[FileChange]:
        """Get file changes: staged + unstaged + untracked.

        Works with repos that have no commits yet (empty repos).
        """
        if not self.is_git_repo():
            return []

        changes: dict[str, FileChange] = {}

        # Check if there are any commits
        has_commits = self._run_git("rev-parse", "HEAD") is not None

        if has_commits:
            # Staged changes (diff against HEAD)
            self._parse_diff_output(
                self._run_git("diff", "--cached", "--name-status"),
                self._run_git("diff", "--cached", "--numstat"),
                changes,
            )

            # Unstaged changes (working tree vs index)
            self._parse_diff_output(
                self._run_git("diff", "--name-status"),
                self._run_git("diff", "--numstat"),
                changes,
            )
        else:
            # No commits yet — treat all staged files as added
            output = self._run_git("diff", "--cached", "--name-only", "--diff-filter=A")
            if output:
                for line in output.strip().splitlines():
                    path = line.strip()
                    if path:
                        changes[path] = FileChange(
                            path=path, status="added",
                            explanation=explain_file(path),
                        )

        # Untracked files
        untracked = self._run_git("ls-files", "--others", "--exclude-standard")
        if untracked:
            for line in untracked.strip().splitlines():
                path = line.strip()
                if path and path not in changes:
                    changes[path] = FileChange(
                        path=path, status="added",
                        explanation=explain_file(path),
                    )

        return list(changes.values())

    def _parse_diff_output(
        self,
        name_status: str | None,
        numstat: str | None,
        changes: dict[str, FileChange],
    ) -> None:
        """Parse git diff --name-status and --numstat output."""
        status_map = {"A": "added", "M": "modified", "D": "deleted"}
        statuses: dict[str, str] = {}

        if name_status:
            for line in name_status.strip().splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    code = parts[0][0]  # R100 → R
                    path = parts[-1]    # renamed: take new name
                    status = status_map.get(code, "modified")
                    if code == "R":
                        status = "renamed"
                    statuses[path] = status

        stats: dict[str, tuple[int, int]] = {}
        if numstat:
            for line in numstat.strip().splitlines():
                parts = line.split("\t")
                if len(parts) >= 3:
                    try:
                        add = int(parts[0]) if parts[0] != "-" else 0
                        rem = int(parts[1]) if parts[1] != "-" else 0
                        path = parts[2]
                        stats[path] = (add, rem)
                    except ValueError:
                        pass

        for path, status in statuses.items():
            add, rem = stats.get(path, (0, 0))
            if path in changes:
                # Merge: keep more severe status, sum stats
                existing = changes[path]
                existing.additions += add
                existing.deletions += rem
            else:
                changes[path] = FileChange(
                    path=path,
                    status=status,
                    additions=add,
                    deletions=rem,
                    explanation=explain_file(path),
                )

    def get_recent_commits(self, limit: int = 10) -> list[str]:
        """Get recent commit onelines."""
        output = self._run_git("log", f"--oneline", f"-{limit}")
        if not output:
            return []
        return [line.strip() for line in output.strip().splitlines() if line.strip()]

    def get_docker_changes(self, current_containers: list[dict]) -> list[DockerChange]:
        """Compare current containers against previous state.

        Args:
            current_containers: list of dicts from docker collector
                (keys: name, image, status, ports)
        """
        current_map = {c["name"]: c for c in current_containers}
        changes: list[DockerChange] = []

        # New containers
        for name, info in current_map.items():
            if name not in self._prev_containers:
                ports = []
                raw_ports = info.get("ports", "")
                if isinstance(raw_ports, str) and raw_ports:
                    ports = [p.strip() for p in raw_ports.split(",") if p.strip()]
                elif isinstance(raw_ports, list):
                    ports = [str(p) for p in raw_ports]
                changes.append(DockerChange(
                    name=name,
                    image=info.get("image", ""),
                    status="new",
                    ports=ports,
                    explanation=f"New container appeared",
                ))
            else:
                prev = self._prev_containers[name]
                if info.get("status") != prev.get("status"):
                    new_status = info.get("status", "unknown")
                    if new_status == "exited" and info.get("exit_code", 0) != 0:
                        change_status = "crashed"
                        explanation = f"Exited with code {info.get('exit_code', '?')}"
                    elif new_status == "running" and prev.get("status") == "exited":
                        change_status = "restarted"
                        explanation = "Restarted"
                    else:
                        change_status = new_status
                        explanation = f"Status: {prev.get('status')} → {new_status}"
                    changes.append(DockerChange(
                        name=name,
                        image=info.get("image", ""),
                        status=change_status,
                        explanation=explanation,
                    ))

        # Removed containers
        for name, info in self._prev_containers.items():
            if name not in current_map:
                changes.append(DockerChange(
                    name=name,
                    image=info.get("image", ""),
                    status="removed",
                    explanation="Container disappeared",
                ))

        self._prev_containers = dict(current_map)
        return changes

    def get_port_changes(self, current_ports: list[dict]) -> list[PortChange]:
        """Compare current listening ports against previous state.

        Args:
            current_ports: list of dicts from port collector
                (keys: port, process, proto)
        """
        current_set = {p["port"] for p in current_ports}
        current_map = {p["port"]: p for p in current_ports}
        changes: list[PortChange] = []

        # New ports
        for port_num in current_set - self._prev_ports:
            info = current_map[port_num]
            changes.append(PortChange(
                port=port_num,
                process=info.get("process", "unknown"),
                status="new",
                explanation=f"Now listening ({info.get('process', '?')})",
            ))

        # Closed ports
        for port_num in self._prev_ports - current_set:
            changes.append(PortChange(
                port=port_num,
                process="",
                status="closed",
                explanation="Stopped listening",
            ))

        self._prev_ports = set(current_set)
        return changes

    def collect_activity(
        self,
        docker_containers: list[dict] | None = None,
        ports: list[dict] | None = None,
    ) -> ActivityEntry:
        """Collect all changes into a single ActivityEntry."""
        files = self.get_git_changes()
        commits = self.get_recent_commits(limit=5)

        docker_changes = []
        if docker_containers is not None:
            docker_changes = self.get_docker_changes(docker_containers)

        port_changes = []
        if ports is not None:
            port_changes = self.get_port_changes(ports)

        return ActivityEntry(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            files=files,
            docker_changes=docker_changes,
            port_changes=port_changes,
            commits=commits,
            project_dir=self._dir,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_activity_tracker.py -v`
Expected: PASS (all 8 tests)

- [ ] **Step 5: Commit**

```bash
git add core/activity_tracker.py tests/test_activity_tracker.py
git commit -m "feat: add activity_tracker — git/docker/port change detection"
```

---

### Task 4: Activity Tracker (docker + ports)

**Files:**
- Modify: `tests/test_activity_tracker.py` (add tests)

- [ ] **Step 1: Write tests for docker and port change detection**

Add to `tests/test_activity_tracker.py`:

```python
def test_docker_changes_new_container():
    tracker = ActivityTracker("/tmp/fake")
    containers = [
        {"name": "web", "image": "python:3.11", "status": "running", "ports": "8000"},
    ]
    changes = tracker.get_docker_changes(containers)
    assert len(changes) == 1
    assert changes[0].name == "web"
    assert changes[0].status == "new"


def test_docker_changes_removed_container():
    tracker = ActivityTracker("/tmp/fake")
    # First call — establish baseline
    tracker.get_docker_changes([
        {"name": "web", "image": "python:3.11", "status": "running", "ports": "8000"},
    ])
    # Second call — container gone
    changes = tracker.get_docker_changes([])
    assert len(changes) == 1
    assert changes[0].name == "web"
    assert changes[0].status == "removed"


def test_docker_changes_crashed():
    tracker = ActivityTracker("/tmp/fake")
    tracker.get_docker_changes([
        {"name": "db", "image": "postgres:16", "status": "running", "ports": "5432"},
    ])
    changes = tracker.get_docker_changes([
        {"name": "db", "image": "postgres:16", "status": "exited", "exit_code": 1, "ports": ""},
    ])
    assert len(changes) == 1
    assert changes[0].status == "crashed"


def test_docker_no_changes():
    tracker = ActivityTracker("/tmp/fake")
    containers = [
        {"name": "web", "image": "python:3.11", "status": "running", "ports": "8000"},
    ]
    tracker.get_docker_changes(containers)
    changes = tracker.get_docker_changes(containers)
    assert len(changes) == 0


def test_port_changes_new():
    tracker = ActivityTracker("/tmp/fake")
    ports = [{"port": 8000, "process": "python", "proto": "tcp"}]
    changes = tracker.get_port_changes(ports)
    assert len(changes) == 1
    assert changes[0].port == 8000
    assert changes[0].status == "new"


def test_port_changes_closed():
    tracker = ActivityTracker("/tmp/fake")
    tracker.get_port_changes([{"port": 8000, "process": "python", "proto": "tcp"}])
    changes = tracker.get_port_changes([])
    assert len(changes) == 1
    assert changes[0].port == 8000
    assert changes[0].status == "closed"


def test_port_no_changes():
    tracker = ActivityTracker("/tmp/fake")
    ports = [{"port": 8000, "process": "python", "proto": "tcp"}]
    tracker.get_port_changes(ports)
    changes = tracker.get_port_changes(ports)
    assert len(changes) == 0


def test_collect_activity(tmp_path):
    """Integration: collect_activity returns an ActivityEntry."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path), capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path), capture_output=True,
    )
    (tmp_path / "app.py").write_text("x = 1")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)

    tracker = ActivityTracker(str(tmp_path))
    entry = tracker.collect_activity(
        docker_containers=[{"name": "web", "image": "py", "status": "running", "ports": ""}],
        ports=[{"port": 8000, "process": "python", "proto": "tcp"}],
    )
    assert entry.project_dir == str(tmp_path)
    assert len(entry.files) >= 1
    assert len(entry.docker_changes) == 1
    assert len(entry.port_changes) == 1
    assert entry.timestamp  # not empty
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_activity_tracker.py -v`
Expected: PASS (all 16 tests)

- [ ] **Step 3: Commit**

```bash
git add tests/test_activity_tracker.py
git commit -m "test: add docker/port change detection tests for activity_tracker"
```

---

### Task 5: i18n strings

**Files:**
- Modify: `i18n/en.py`
- Modify: `i18n/ua.py`

- [ ] **Step 1: Add English strings**

Add to `i18n/en.py` before the closing `}`:

```python
    # Activity Log
    "side_activity": "Activity Log",
    "activity_header": "Activity Log",
    "activity_no_dir": "No project directory selected",
    "activity_select_dir": "Select project directory to track changes",
    "activity_btn_select": "Select Directory...",
    "activity_btn_refresh": "Refresh",
    "activity_dir_label": "Project:",
    "activity_no_git": "Not a git repository",
    "activity_no_changes": "No changes detected",
    "activity_files_header": "Files Changed",
    "activity_docker_header": "Docker Changes",
    "activity_ports_header": "Ports",
    "activity_commits_header": "Recent Commits",
    "activity_file_added": "NEW",
    "activity_file_modified": "modified",
    "activity_file_deleted": "DELETED",
    "activity_file_renamed": "RENAMED",
    "activity_docker_new": "NEW container",
    "activity_docker_removed": "REMOVED",
    "activity_docker_crashed": "CRASHED",
    "activity_docker_restarted": "restarted",
    "activity_port_new": "NEW",
    "activity_port_closed": "CLOSED",
    "activity_env_warning": "Environment variables changed — check if secrets are OK",
    "activity_container_crash": "Container died — check logs",
    "activity_git_not_found": "Git not installed — file tracking unavailable",

    # Hasselhoff mode — Activity Log
    "hoff_activity_header": "The Hoff Sees All",
    "hoff_activity_no_changes": "Even the Hoff needs a break sometimes",
    "hoff_activity_crash": "Don't hassle the container... oh wait, it hassled itself",
```

- [ ] **Step 2: Add Ukrainian strings**

Add to `i18n/ua.py` before the closing `}`:

```python
    # Activity Log
    "side_activity": "Журнал змін",
    "activity_header": "Журнал змін",
    "activity_no_dir": "Директорію проєкту не обрано",
    "activity_select_dir": "Оберіть директорію проєкту для відстеження змін",
    "activity_btn_select": "Обрати директорію...",
    "activity_btn_refresh": "Оновити",
    "activity_dir_label": "Проєкт:",
    "activity_no_git": "Це не git-репозиторій",
    "activity_no_changes": "Змін не виявлено",
    "activity_files_header": "Змінені файли",
    "activity_docker_header": "Docker зміни",
    "activity_ports_header": "Порти",
    "activity_commits_header": "Останні коміти",
    "activity_file_added": "НОВИЙ",
    "activity_file_modified": "змінено",
    "activity_file_deleted": "ВИДАЛЕНО",
    "activity_file_renamed": "ПЕРЕЙМЕНОВАНО",
    "activity_docker_new": "НОВИЙ контейнер",
    "activity_docker_removed": "ВИДАЛЕНО",
    "activity_docker_crashed": "ВПАВ",
    "activity_docker_restarted": "перезапущено",
    "activity_port_new": "НОВИЙ",
    "activity_port_closed": "ЗАКРИТО",
    "activity_env_warning": "Змінні середовища змінились — перевірте секрети",
    "activity_container_crash": "Контейнер впав — перевірте логи",
    "activity_git_not_found": "Git не встановлено — відстеження файлів недоступне",

    # Hasselhoff mode — Activity Log
    "hoff_activity_header": "Хофф бачить все",
    "hoff_activity_no_changes": "Навіть Хофф іноді відпочиває",
    "hoff_activity_crash": "Не чіпай контейнер... а, він сам себе зламав",
```

- [ ] **Step 3: Commit**

```bash
git add i18n/en.py i18n/ua.py
git commit -m "feat: add Activity Log i18n strings (EN + UA)"
```

---

### Task 6: Activity Log GUI Page

**Files:**
- Create: `gui/pages/activity.py`

- [ ] **Step 1: Write the Activity Log page**

```python
# gui/pages/activity.py
"""Activity Log page — shows git/docker/port changes in human language."""

from __future__ import annotations

import shutil
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QScrollArea, QFileDialog, QFrame,
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont

from i18n import get_string as _t
from core.activity_tracker import ActivityTracker
from core.models import ActivityEntry, FileChange, DockerChange, PortChange


class ActivityPage(QWidget):
    """Activity Log — what changed in the project environment."""

    refresh_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._project_dir: str | None = None
        self._tracker: ActivityTracker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header row: title + dir picker + refresh
        header = QHBoxLayout()
        title = QLabel(_t("activity_header"))
        title.setFont(QFont("MS Sans Serif", 14, QFont.Bold))
        title.setStyleSheet("color: #000080;")
        header.addWidget(title)
        header.addStretch()

        self._dir_label = QLabel(_t("activity_no_dir"))
        self._dir_label.setStyleSheet("color: #808080;")
        header.addWidget(self._dir_label)

        self._btn_select = QPushButton(_t("activity_btn_select"))
        self._btn_select.clicked.connect(self._on_select_dir)
        header.addWidget(self._btn_select)

        self._btn_refresh = QPushButton(_t("activity_btn_refresh"))
        self._btn_refresh.clicked.connect(self._on_refresh)
        header.addWidget(self._btn_refresh)

        layout.addLayout(header)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 2px inset #808080; background: white; }")

        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._content_widget)

        layout.addWidget(scroll)

        # Initial state
        self._show_placeholder(_t("activity_select_dir"))

    def _show_placeholder(self, text: str) -> None:
        """Show a centered placeholder message."""
        self._clear_content()
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #808080; font-size: 14px; padding: 40px;")
        self._content_layout.addWidget(lbl)

    def _clear_content(self) -> None:
        """Remove all widgets from content area."""
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _on_select_dir(self) -> None:
        """Open directory picker."""
        dir_path = QFileDialog.getExistingDirectory(
            self, _t("activity_btn_select"), str(Path.home()),
        )
        if dir_path:
            self.set_project_dir(dir_path)

    def set_project_dir(self, path: str) -> None:
        """Set project directory and refresh."""
        self._project_dir = path
        self._tracker = ActivityTracker(path)

        # Truncate long paths for display
        display = path
        if len(display) > 50:
            display = "..." + display[-47:]
        self._dir_label.setText(f"{_t('activity_dir_label')} {display}")
        self._dir_label.setStyleSheet("color: #000000;")

        self._on_refresh()

    def _on_refresh(self) -> None:
        """Collect and display activity."""
        if not self._tracker or not self._project_dir:
            self._show_placeholder(_t("activity_select_dir"))
            return

        # Check git
        git_available = shutil.which("git") is not None
        if not git_available:
            self._show_placeholder(_t("activity_git_not_found"))
            return

        self.refresh_requested.emit()

    def update_data(
        self,
        entry: ActivityEntry | None = None,
        docker_data: list[dict] | None = None,
        port_data: list[dict] | None = None,
    ) -> None:
        """Update the page with fresh activity data.

        Called from app.py refresh cycle.
        If entry is None, collects data from tracker.
        """
        if not self._tracker:
            return

        if entry is None:
            entry = self._tracker.collect_activity(
                docker_containers=docker_data,
                ports=port_data,
            )

        self._render_activity(entry)

    def _render_activity(self, entry: ActivityEntry) -> None:
        """Render activity entry into the content area."""
        self._clear_content()

        has_content = False

        # Git files
        if entry.files:
            has_content = True
            group = self._make_group(
                f"{_t('activity_files_header')} ({len(entry.files)} files)"
            )
            group_layout = group.layout()
            for fc in entry.files:
                row = self._make_file_row(fc)
                group_layout.addWidget(row)
            self._content_layout.addWidget(group)

        # Docker changes
        if entry.docker_changes:
            has_content = True
            group = self._make_group(_t("activity_docker_header"))
            group_layout = group.layout()
            for dc in entry.docker_changes:
                row = self._make_docker_row(dc)
                group_layout.addWidget(row)
            self._content_layout.addWidget(group)

        # Port changes
        if entry.port_changes:
            has_content = True
            group = self._make_group(_t("activity_ports_header"))
            group_layout = group.layout()
            for pc in entry.port_changes:
                row = self._make_port_row(pc)
                group_layout.addWidget(row)
            self._content_layout.addWidget(group)

        # Recent commits
        if entry.commits:
            has_content = True
            group = self._make_group(_t("activity_commits_header"))
            group_layout = group.layout()
            for commit in entry.commits:
                lbl = QLabel(f"  {commit}")
                lbl.setStyleSheet("font-family: monospace; color: #333;")
                group_layout.addWidget(lbl)
            self._content_layout.addWidget(group)

        if not has_content:
            if not self._tracker.is_git_repo():
                self._show_placeholder(_t("activity_no_git"))
            else:
                self._show_placeholder(_t("activity_no_changes"))

        self._content_layout.addStretch()

    def _make_group(self, title: str) -> QGroupBox:
        """Create a Win95-style group box."""
        group = QGroupBox(title)
        group.setStyleSheet(
            "QGroupBox { border: 2px groove #808080; margin-top: 12px; "
            "padding-top: 16px; font-weight: bold; background: white; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; "
            "padding: 0 4px; }"
        )
        layout = QVBoxLayout(group)
        layout.setSpacing(2)
        return group

    def _make_file_row(self, fc: FileChange) -> QFrame:
        """Create a row for a file change."""
        frame = QFrame()
        frame.setStyleSheet("QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(1)

        # Line 1: status icon + path + stats
        top = QHBoxLayout()

        status_map = {
            "added": ("+", "#006600", _t("activity_file_added")),
            "modified": ("~", "#000080", _t("activity_file_modified")),
            "deleted": ("-", "#cc0000", _t("activity_file_deleted")),
            "renamed": ("R", "#806600", _t("activity_file_renamed")),
        }
        icon, color, label = status_map.get(fc.status, ("?", "#808080", fc.status))

        status_lbl = QLabel(f"{icon}")
        status_lbl.setFixedWidth(16)
        status_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-family: monospace;")
        top.addWidget(status_lbl)

        path_lbl = QLabel(fc.path)
        path_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        top.addWidget(path_lbl)

        if fc.status == "added":
            tag = QLabel(f"({label})")
            tag.setStyleSheet("color: #006600; font-weight: bold;")
            top.addWidget(tag)
        elif fc.status == "deleted":
            tag = QLabel(f"({label})")
            tag.setStyleSheet("color: #cc0000; font-weight: bold;")
            top.addWidget(tag)

        top.addStretch()

        if fc.additions or fc.deletions:
            stats_text = ""
            if fc.additions:
                stats_text += f"+{fc.additions}"
            if fc.deletions:
                if stats_text:
                    stats_text += " "
                stats_text += f"-{fc.deletions}"
            stats_lbl = QLabel(stats_text)
            stats_lbl.setStyleSheet("color: #808080; font-family: monospace;")
            top.addWidget(stats_lbl)

        layout.addLayout(top)

        # Line 2: explanation
        if fc.explanation:
            # Warn on .env changes
            is_env = ".env" in fc.path.lower()
            expl_color = "#cc6600" if is_env else "#666666"
            prefix = "\u26a0\ufe0f " if is_env else "  "
            expl_text = _t("activity_env_warning") if is_env else fc.explanation

            expl_lbl = QLabel(f"{prefix}{expl_text}")
            expl_lbl.setStyleSheet(f"color: {expl_color}; font-size: 11px;")
            layout.addWidget(expl_lbl)

        return frame

    def _make_docker_row(self, dc: DockerChange) -> QFrame:
        """Create a row for a docker change."""
        frame = QFrame()
        frame.setStyleSheet("QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)

        status_styles = {
            "new": ("+", "#006600"),
            "removed": ("-", "#cc0000"),
            "crashed": ("\U0001f534", "#cc0000"),
            "restarted": ("\u25cf", "#cc6600"),
        }
        icon, color = status_styles.get(dc.status, ("?", "#808080"))

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(20)
        icon_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(icon_lbl)

        name_lbl = QLabel(f"{dc.name}")
        name_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(name_lbl)

        if dc.image:
            img_lbl = QLabel(f"({dc.image})")
            img_lbl.setStyleSheet("color: #808080;")
            layout.addWidget(img_lbl)

        layout.addStretch()

        status_text = {
            "new": _t("activity_docker_new"),
            "removed": _t("activity_docker_removed"),
            "crashed": _t("activity_docker_crashed"),
            "restarted": _t("activity_docker_restarted"),
        }.get(dc.status, dc.status)

        status_tag = QLabel(status_text)
        status_tag.setStyleSheet(
            f"color: {color}; font-weight: bold; "
            "border: 1px solid #808080; padding: 1px 4px;"
        )
        layout.addWidget(status_tag)

        if dc.explanation:
            expl = QLabel(dc.explanation)
            expl.setStyleSheet("color: #666; font-size: 11px;")
            layout.addWidget(expl)

        return frame

    def _make_port_row(self, pc: PortChange) -> QFrame:
        """Create a row for a port change."""
        frame = QFrame()
        frame.setStyleSheet("QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)

        is_new = pc.status == "new"
        color = "#006600" if is_new else "#cc0000"
        icon = "+" if is_new else "-"

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(16)
        icon_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-family: monospace;")
        layout.addWidget(icon_lbl)

        port_lbl = QLabel(f":{pc.port}")
        port_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-family: monospace;")
        layout.addWidget(port_lbl)

        if pc.process:
            proc_lbl = QLabel(f"({pc.process})")
            proc_lbl.setStyleSheet("color: #808080;")
            layout.addWidget(proc_lbl)

        layout.addStretch()

        tag_text = _t("activity_port_new") if is_new else _t("activity_port_closed")
        tag = QLabel(tag_text)
        tag.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(tag)

        if pc.explanation:
            expl = QLabel(pc.explanation)
            expl.setStyleSheet("color: #666; font-size: 11px;")
            layout.addWidget(expl)

        return frame
```

- [ ] **Step 2: Commit**

```bash
git add gui/pages/activity.py
git commit -m "feat: add Activity Log GUI page with file/docker/port change display"
```

---

### Task 7: Wire into app.py (sidebar + refresh)

**Files:**
- Modify: `gui/app.py`

- [ ] **Step 1: Add import**

At top of `gui/app.py`, add after the discover import:

```python
from gui.pages.activity import ActivityPage
```

- [ ] **Step 2: Add sidebar item**

In the `sidebar_items` list, add after the overview item:

```python
SidebarItem(_t("side_activity"), "activity"),
```

So it becomes:
```python
sidebar_items = [
    SidebarItem(_t("side_overview"), "overview"),
    SidebarItem(_t("side_activity"), "activity"),
    SidebarItem(_t("side_security"), "security"),
    ...
```

- [ ] **Step 3: Create page instance and register**

After `self.page_discover = DiscoverTab()`, add:

```python
self.page_activity = ActivityPage()
```

In the `for key, page in [...]` list, add after overview:

```python
("activity", self.page_activity),
```

- [ ] **Step 4: Connect signals**

After the existing signal connections, add:

```python
self.page_activity.refresh_requested.connect(self._refresh_all)
```

- [ ] **Step 5: Feed activity data from refresh cycle**

In `_on_data_ready` method, after the ports section, add:

```python
# Activity Log — feed docker + port data
if hasattr(self, "page_activity"):
    self.page_activity.update_data(
        docker_data=infos,
        port_data=ports,
    )
```

- [ ] **Step 6: Verify the app launches**

Run: `python -m gui.app` (or however the app starts)
Expected: Activity Log appears in sidebar, clicking it shows the page with directory picker.

- [ ] **Step 7: Commit**

```bash
git add gui/app.py
git commit -m "feat: wire Activity Log page into sidebar and refresh cycle"
```

---

### Task 8: Manual Integration Test

- [ ] **Step 1: Run all tests**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: All existing tests still pass + all new tests pass.

- [ ] **Step 2: Manual smoke test**

1. Launch the app
2. Click "Activity Log" in sidebar
3. Click "Select Directory..." → pick a git repo
4. Verify files show with human explanations
5. Verify commits section shows recent commits
6. If Docker running — verify docker changes appear on second refresh
7. Verify port changes appear on second refresh

- [ ] **Step 3: Cross-platform notes check**

Verify in code:
- `shutil.which("git")` — works on Linux/Mac/Windows
- `subprocess.run` uses `shell=False` and `encoding="utf-8"` everywhere
- `pathlib.Path` used for all file system paths
- No hardcoded `/` separators in OS paths (only in git output parsing which always uses `/`)
- `QFileDialog.getExistingDirectory` — Qt handles platform dialogs natively

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: integration fixes for Activity Log"
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Data models | `core/models.py`, `tests/test_activity_models.py` |
| 2 | File explainer | `core/file_explainer.py`, `tests/test_file_explainer.py` |
| 3 | Activity tracker (git) | `core/activity_tracker.py`, `tests/test_activity_tracker.py` |
| 4 | Activity tracker (docker+ports) | `tests/test_activity_tracker.py` |
| 5 | i18n strings | `i18n/en.py`, `i18n/ua.py` |
| 6 | GUI page | `gui/pages/activity.py` |
| 7 | Wire into app | `gui/app.py` |
| 8 | Integration test | all |

**Cross-platform guarantees:**
- Git: `shutil.which("git")` + `encoding="utf-8"` + `shell=False`
- Docker: existing SDK (cross-platform)
- Ports: existing psutil (cross-platform)
- File dialogs: Qt native dialogs
- Paths: `pathlib` everywhere, `PurePosixPath` for git output
