"""Safety Net — Save / Rollback / Pick for vibe coders.

Git-based code snapshots with teaching moments.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.history import HistoryDB
from core.file_explainer import explain_file

log = logging.getLogger(__name__)

# Files/dirs to skip when listing pickable files
_SKIP_PATTERNS = {
    "node_modules", "__pycache__", ".git", ".env", ".venv",
    "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
    "dist", "build", ".next", ".nuxt",
}


@dataclass
class SavePointResult:
    id: int
    commit_hash: str
    tag_name: str
    file_count: int
    lines_total: int
    warnings_fixed: list[str] = field(default_factory=list)


@dataclass
class RollbackPreview:
    files_affected: int
    current_branch: str
    target_commit: str
    target_label: str


@dataclass
class RollbackResult:
    backup_branch: str
    backup_commit: str
    files_restored: int


@dataclass
class PickableFile:
    path: str
    status: str          # "added", "modified", "deleted"
    additions: int
    deletions: int
    explanation: str


@dataclass
class PickResult:
    files_applied: list[str]
    commit_hash: str


class SafetyNet:
    def __init__(self, project_dir: str, db: HistoryDB, config: dict | None = None):
        self._dir = project_dir
        self._db = db
        self._config = config or {}
        self._sn_config = self._config.get("safety_net", {})

    # --- helpers ---

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                ["git"] + list(args),
                cwd=self._dir,
                capture_output=True,
                text=True,
                check=check,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            log.warning("git %s timed out after 30s", args)
            if check:
                raise
            return subprocess.CompletedProcess(
                args=["git"] + list(args),
                returncode=-1,
                stdout="",
                stderr="timeout",
            )

    def _git_ok(self, *args: str) -> str:
        """Run git command, return stdout. Empty string on failure."""
        r = self._git(*args, check=False)
        return r.stdout.strip() if r.returncode == 0 else ""

    def _has_git(self) -> bool:
        return shutil.which("git") is not None

    def _is_repo(self) -> bool:
        return (Path(self._dir) / ".git").is_dir()

    def _current_branch(self) -> str:
        return self._git_ok("rev-parse", "--abbrev-ref", "HEAD") or "main"

    def _current_commit(self) -> str:
        return self._git_ok("rev-parse", "--short", "HEAD")

    def _has_changes(self) -> bool:
        r = self._git("status", "--porcelain", check=False)
        return bool(r.stdout.strip())

    def _count_tracked_files(self) -> int:
        r = self._git("ls-files", check=False)
        if r.returncode != 0:
            return 0
        return len([l for l in r.stdout.splitlines() if l.strip()])

    def _count_lines(self) -> int:
        """Count total lines in tracked source files."""
        r = self._git("ls-files", check=False)
        if r.returncode != 0:
            return 0
        total = 0
        for rel_path in r.stdout.splitlines():
            if not rel_path.strip():
                continue
            full = Path(self._dir) / rel_path
            if not full.is_file():
                continue
            # skip binary-looking files
            try:
                with open(full, encoding="utf-8", errors="ignore") as f:
                    total += sum(1 for _ in f)
            except (OSError, UnicodeDecodeError):
                pass
        return total

    def _next_tag(self) -> str:
        """Find next available savepoint-N tag."""
        r = self._git("tag", "-l", "savepoint-*", check=False)
        existing = set()
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("savepoint-"):
                try:
                    existing.add(int(line.split("-", 1)[1]))
                except ValueError:
                    pass
        n = 1
        while n in existing:
            n += 1
        return f"savepoint-{n}"

    def _next_backup_branch(self, base: str) -> str:
        """Find available backup branch name."""
        r = self._git("branch", "--list", f"{base}*", check=False)
        if not r.stdout.strip():
            return base
        suffix = 2
        while True:
            candidate = f"{base}-{suffix}"
            if candidate not in r.stdout:
                return candidate
            suffix += 1

    # --- Save ---

    def can_save(self) -> tuple[bool, str]:
        if not self._has_git():
            return False, "git_not_installed"
        if not self._is_repo():
            return False, "no_git_repo"
        if not self._has_changes():
            return False, "no_changes"
        return True, ""

    def pre_save_warnings(self) -> list[dict]:
        warnings = []
        gitignore = Path(self._dir) / ".gitignore"

        # .env tracked by git?
        env_file = Path(self._dir) / ".env"
        if env_file.exists():
            r = self._git("ls-files", ".env", check=False)
            if r.stdout.strip():
                warnings.append({
                    "type": "env_tracked",
                    "message": "safety_warn_env",
                    "fix": "add_gitignore",
                    "pattern": ".env",
                })

        # node_modules without .gitignore?
        nm = Path(self._dir) / "node_modules"
        if nm.is_dir():
            has_ignore = False
            if gitignore.exists():
                content = gitignore.read_text(errors="ignore")
                has_ignore = "node_modules" in content
            if not has_ignore:
                warnings.append({
                    "type": "node_modules",
                    "message": "safety_warn_node_modules",
                    "fix": "add_gitignore",
                    "pattern": "node_modules/",
                })

        return warnings

    def create_save_point(self, label: str) -> SavePointResult:
        if not self._is_repo():
            raise RuntimeError("Not a git repository")

        # git add + commit
        self._git("add", ".")
        tag_name = self._next_tag()
        commit_msg = f"Save Point: {label}"

        r = self._git("commit", "-m", commit_msg, check=False)
        if r.returncode != 0:
            if "please tell me who you are" in r.stderr.lower() or \
               "author identity unknown" in r.stderr.lower():
                raise RuntimeError("git_config_missing")
            if "nothing to commit" in r.stdout.lower() or "nothing to commit" in r.stderr.lower():
                raise RuntimeError("no_changes")
            raise RuntimeError(f"git commit failed: {r.stderr}")

        commit_hash = self._current_commit()
        self._git("tag", tag_name)

        file_count = self._count_tracked_files()
        lines_total = self._count_lines()

        # Save to DB
        sp_id = self._db.add_save_point(
            timestamp=datetime.now().isoformat(),
            label=label,
            project_dir=self._dir,
            branch=self._current_branch(),
            commit_hash=commit_hash,
            tag_name=tag_name,
            file_count=file_count,
            lines_total=lines_total,
        )

        # Enforce max save points
        max_sp = self._sn_config.get("max_save_points", 20)
        self._cleanup_old_save_points(max_sp)

        self._db.bump_git_education(self._dir, "saves_count")

        return SavePointResult(
            id=sp_id,
            commit_hash=commit_hash,
            tag_name=tag_name,
            file_count=file_count,
            lines_total=lines_total,
        )

    def _cleanup_old_save_points(self, max_count: int) -> None:
        points = self._db.get_save_points(self._dir, limit=max_count + 50)
        if len(points) <= max_count:
            return
        to_remove = points[max_count:]
        for sp in to_remove:
            # Remove git tag
            self._git("tag", "-d", sp["tag_name"], check=False)
            self._db.delete_save_point(sp["id"])

    def get_save_points(self, limit: int = 20) -> list[dict]:
        return self._db.get_save_points(self._dir, limit)

    # --- Rollback ---

    def can_rollback(self, save_point_id: int) -> tuple[bool, str]:
        sp = self._db.get_save_point(save_point_id)
        if not sp:
            return False, "save_point_not_found"

        # Check if merge in progress
        merge_head = Path(self._dir) / ".git" / "MERGE_HEAD"
        if merge_head.exists():
            return False, "merge_in_progress"

        # Check if we're already at this commit
        current = self._current_commit()
        if current == sp["commit_hash"]:
            if not self._has_changes():
                return False, "already_at_save_point"

        return True, ""

    def rollback_preview(self, save_point_id: int) -> RollbackPreview | None:
        sp = self._db.get_save_point(save_point_id)
        if not sp:
            return None

        # Count files that differ
        r = self._git("diff", "--name-only", sp["commit_hash"], check=False)
        files_in_diff = len([l for l in r.stdout.splitlines() if l.strip()])

        # Also count uncommitted changes
        r2 = self._git("status", "--porcelain", check=False)
        uncommitted = len([l for l in r2.stdout.splitlines() if l.strip()])

        return RollbackPreview(
            files_affected=max(files_in_diff, uncommitted),
            current_branch=self._current_branch(),
            target_commit=sp["commit_hash"],
            target_label=sp["label"],
        )

    def rollback(self, save_point_id: int) -> RollbackResult:
        sp = self._db.get_save_point(save_point_id)
        if not sp:
            raise RuntimeError("save_point_not_found")

        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d-%H-%M")
        backup_base = f"backup/{timestamp}"
        backup_branch = self._next_backup_branch(backup_base)

        # Commit current changes if any
        if self._has_changes():
            self._git("add", ".")
            self._git("commit", "-m",
                       f"backup before rollback to {sp['tag_name']}",
                       check=False)

        backup_commit = self._current_commit()

        # Count changed files for metadata
        r = self._git("diff", "--name-only", sp["commit_hash"], check=False)
        files_changed = len([l for l in r.stdout.splitlines() if l.strip()])

        # Create backup branch at current position
        self._git("branch", backup_branch)

        # Reset to save point
        self._git("reset", "--hard", sp["tag_name"])

        files_restored = self._count_tracked_files()

        # Save to DB
        self._db.add_rollback_backup(
            timestamp=now.isoformat(),
            project_dir=self._dir,
            save_point_id=save_point_id,
            backup_branch=backup_branch,
            backup_commit=backup_commit,
            files_changed=files_changed,
        )

        self._db.bump_git_education(self._dir, "rollbacks_count")

        return RollbackResult(
            backup_branch=backup_branch,
            backup_commit=backup_commit,
            files_restored=files_restored,
        )

    def get_changes_since(self, save_point_id: int) -> list:
        """Files changed since a save point (including untracked).

        Returns list of FileChange (path/additions/deletions/status) for the
        Smart Rollback dialog to feed to feature_grouper.
        """
        from core.feature_grouper import FileChange

        sp = self._db.get_save_point(save_point_id)
        if not sp:
            return []

        def _is_junk(path: str) -> bool:
            return any(path.startswith(p + "/") or path == p
                       for p in _SKIP_PATTERNS)

        changes: dict[str, FileChange] = {}

        # Tracked changes: diff working tree against save-point commit
        r = self._git("diff", "--numstat", sp["commit_hash"], check=False)
        r_status = self._git("diff", "--name-status", sp["commit_hash"],
                             check=False)
        status_map: dict[str, str] = {}
        for line in r_status.stdout.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                code, path = parts
                status_map[path] = {"A": "added", "D": "deleted"}.get(
                    code.strip()[:1], "modified"
                )

        if r.returncode == 0:
            for line in r.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                adds_str, dels_str, path = parts[0], parts[1], parts[2]
                if _is_junk(path):
                    continue
                adds = int(adds_str) if adds_str.isdigit() else 0
                dels = int(dels_str) if dels_str.isdigit() else 0
                changes[path] = FileChange(
                    path=path, additions=adds, deletions=dels,
                    status=status_map.get(path, "modified"),
                )

        # Untracked files — count their line count as "additions"
        r_untracked = self._git("ls-files", "--others", "--exclude-standard",
                                check=False)
        if r_untracked.returncode == 0:
            for path in r_untracked.stdout.splitlines():
                path = path.strip()
                if not path or _is_junk(path) or path in changes:
                    continue
                try:
                    lines = (Path(self._dir) / path).read_text(
                        errors="ignore"
                    ).count("\n") + 1
                except Exception:
                    lines = 0
                changes[path] = FileChange(
                    path=path, additions=lines, deletions=0, status="added",
                )

        return list(changes.values())

    def rollback_with_picks(self, save_point_id: int,
                            keep_paths: list[str]) -> RollbackResult:
        """Rollback to save point BUT re-apply selected paths from the backup.

        Flow:
        1. Normal rollback() — commits current work, branches as backup,
           hard-resets to save point.
        2. For each keep_path, checkout that file from the backup commit
           back into the working tree.
        3. Commit the kept files as a single "selective rollback" commit
           so the history is clean and you can Pick more later if needed.
        """
        result = self.rollback(save_point_id)
        if not keep_paths:
            return result

        applied: list[str] = []
        for path in keep_paths:
            r = self._git("checkout", result.backup_commit, "--", path,
                          check=False)
            if r.returncode == 0:
                applied.append(path)

        if applied:
            self._git("add", *applied, check=False)
            commit_msg = (
                f"selective rollback: keep {len(applied)} file(s) "
                f"from save_point_{save_point_id}"
            )
            self._git("commit", "-m", commit_msg, check=False)

        return result

    # --- Pick ---

    def list_pickable_files(self, backup_id: int) -> list[PickableFile]:
        backups = self._db.get_rollback_backups(self._dir)
        backup = None
        for b in backups:
            if b["id"] == backup_id:
                backup = b
                break
        if not backup:
            return []

        sp = self._db.get_save_point(backup["save_point_id"])
        if not sp:
            return []

        # git diff between save point and backup branch
        r = self._git(
            "diff", "--numstat", f"{sp['tag_name']}..{backup['backup_branch']}",
            check=False,
        )
        if r.returncode != 0:
            return []

        files = []
        for line in r.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            adds_str, dels_str, path = parts[0], parts[1], parts[2]

            # Skip junk
            skip = False
            for pattern in _SKIP_PATTERNS:
                if path.startswith(pattern + "/") or path == pattern:
                    skip = True
                    break
            if skip:
                continue

            adds = int(adds_str) if adds_str != "-" else 0
            dels = int(dels_str) if dels_str != "-" else 0

            # Determine status
            r2 = self._git(
                "diff", "--name-status", f"{sp['tag_name']}..{backup['backup_branch']}",
                "--", path, check=False,
            )
            status = "modified"
            if r2.stdout.strip():
                code = r2.stdout.strip().split("\t")[0]
                if code.startswith("A"):
                    status = "added"
                elif code.startswith("D"):
                    status = "deleted"

            files.append(PickableFile(
                path=path,
                status=status,
                additions=adds,
                deletions=dels,
                explanation=explain_file(path),
            ))

        return files

    def pick_files(self, backup_id: int, paths: list[str]) -> PickResult:
        backups = self._db.get_rollback_backups(self._dir)
        backup = None
        for b in backups:
            if b["id"] == backup_id:
                backup = b
                break
        if not backup:
            raise RuntimeError("backup_not_found")

        applied = []
        for path in paths:
            r = self._git(
                "checkout", backup["backup_branch"], "--", path,
                check=False,
            )
            if r.returncode == 0:
                applied.append(path)
            else:
                log.warning("Could not pick %s: %s", path, r.stderr.strip())

        if not applied:
            raise RuntimeError("no_files_picked")

        self._git("add", *applied)
        file_list = ", ".join(applied[:5])
        if len(applied) > 5:
            file_list += f" (+{len(applied) - 5} more)"
        self._git("commit", "-m",
                   f"picked from {backup['backup_branch']}: {file_list}")

        commit_hash = self._current_commit()

        # Update DB
        picked = json.loads(backup.get("picked_files", "[]"))
        picked.extend(applied)
        self._db.update_picked_files(backup_id, json.dumps(picked))

        self._db.bump_git_education(self._dir, "picks_count")

        return PickResult(files_applied=applied, commit_hash=commit_hash)

    # --- Git Init ---

    def ensure_git(self) -> bool:
        if not self._has_git():
            return False
        if self._is_repo():
            return True
        r = self._git("init", check=False)
        if r.returncode == 0:
            self._db.bump_git_education(self._dir, "git_initialized")
            return True
        return False

    def fix_gitignore(self, patterns: list[str]) -> None:
        gitignore = Path(self._dir) / ".gitignore"
        existing = ""
        if gitignore.exists():
            existing = gitignore.read_text(errors="ignore")

        lines = existing.splitlines()
        added = []
        for pattern in patterns:
            if pattern not in existing:
                lines.append(pattern)
                added.append(pattern)

        if added:
            gitignore.write_text("\n".join(lines) + "\n")
            self._db.bump_git_education(self._dir, "gitignore_created")

    def set_git_user(self, name: str, email: str) -> None:
        self._git("config", "user.name", name)
        self._git("config", "user.email", email)
