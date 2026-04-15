"""Git Survival checks — git status explainer, commit quality, branch awareness, gitignore health, cheat sheet."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from core.health.models import HealthFinding, HealthReport

log = logging.getLogger(__name__)


def _run_git(project_dir: str, *args: str) -> str | None:
    git = shutil.which("git")
    if not git:
        return None
    try:
        result = subprocess.run(
            [git, *args],
            cwd=project_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError):
        return None


def _is_git_repo(project_dir: str) -> bool:
    output = _run_git(project_dir, "rev-parse", "--is-inside-work-tree")
    return output is not None and output.strip() == "true"


def check_git_status(report: HealthReport, project_dir: str) -> None:
    """Check 5.1 — explain git status in human language."""
    if not _is_git_repo(project_dir):
        report.findings.append(HealthFinding(
            check_id="git.status",
            title="Not a git repository",
            severity="medium",
            message=(
                "This directory is not tracked by git. "
                "Run 'git init' to start version control. "
                "Without git, you can't undo mistakes."
            ),
        ))
        return

    output = _run_git(project_dir, "status", "--porcelain")
    if not output:
        report.findings.append(HealthFinding(
            check_id="git.status",
            title="Git: clean working tree",
            severity="info",
            message="Everything is committed. Clean slate.",
        ))
        return

    staged = []
    modified = []
    untracked = []

    for line in output.splitlines():
        if not line.strip():
            continue
        index_status = line[0] if len(line) > 0 else " "
        work_status = line[1] if len(line) > 1 else " "
        filename = line[3:].strip()

        if index_status in "AMDRC" and work_status == " ":
            staged.append(filename)
        elif work_status == "M":
            modified.append(filename)
        elif index_status == "?" and work_status == "?":
            untracked.append(filename)
        elif index_status in "AMDRC":
            staged.append(filename)
            if work_status != " ":
                modified.append(filename)

    parts = []
    if staged:
        parts.append(f"{len(staged)} staged (ready to commit)")
    if modified:
        parts.append(f"{len(modified)} modified (changed but not staged)")
    if untracked:
        parts.append(f"{len(untracked)} untracked (new files git doesn't know about)")

    report.findings.append(HealthFinding(
        check_id="git.status",
        title=f"Git status: {', '.join(parts)}",
        severity="info",
        message=(
            f"Working tree: {', '.join(parts)}. "
            + ("Staged files are ready for commit. " if staged else "")
            + ("Modified files need 'git add' before commit. " if modified else "")
            + ("Untracked files won't be saved until you 'git add' them." if untracked else "")
        ),
    ))


def check_commit_quality(report: HealthReport, project_dir: str) -> None:
    """Check 5.2 — check recent commits for size and message quality."""
    if not _is_git_repo(project_dir):
        return

    log_output = _run_git(
        project_dir, "log", "--oneline", "--shortstat", "-10"
    )
    if not log_output:
        return

    bad_messages = ["fix", "update", "wip", "test", "asdf", ".", "temp", "stuff", "changes"]
    big_commits = []
    bad_msg_commits = []

    lines = log_output.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Oneline: "abc1234 message"
        parts = line.split(" ", 1)
        if len(parts) < 2:
            i += 1
            continue

        commit_hash = parts[0]
        message = parts[1].strip().lower()

        # Check message quality
        if message in bad_messages or len(message) < 4:
            bad_msg_commits.append((commit_hash, parts[1].strip()))

        # Check next line for stats
        if i + 1 < len(lines):
            stat_line = lines[i + 1].strip()
            if "file" in stat_line and "changed" in stat_line:
                # Parse "N files changed, M insertions(+), K deletions(-)"
                try:
                    insertions = 0
                    deletions = 0
                    if "insertion" in stat_line:
                        ins_part = stat_line.split("insertion")[0].split(",")[-1].strip()
                        insertions = int(ins_part)
                    if "deletion" in stat_line:
                        del_part = stat_line.split("deletion")[0].split(",")[-1].strip()
                        deletions = int(del_part)
                    total = insertions + deletions
                    if total > 300:
                        big_commits.append((commit_hash, parts[1].strip(), total))
                except (ValueError, IndexError):
                    pass
                i += 2
                continue

        i += 1

    if big_commits:
        for commit_hash, msg, total in big_commits[:3]:
            report.findings.append(HealthFinding(
                check_id="git.commits",
                title=f"Big commit: {commit_hash} ({total} lines)",
                severity="low",
                message=(
                    f"Commit '{msg}' changed {total} lines. "
                    f"That's not a commit, that's a release. "
                    f"Small commits = easy rollback."
                ),
            ))

    if bad_msg_commits:
        for commit_hash, msg in bad_msg_commits[:3]:
            report.findings.append(HealthFinding(
                check_id="git.commits",
                title=f"Vague commit: '{msg}'",
                severity="low",
                message=(
                    f"Commit '{msg}' — what does this mean in 2 weeks? "
                    f"Good format: 'feat: add user login' or 'fix: crash on empty input'."
                ),
            ))


def check_branch_awareness(report: HealthReport, project_dir: str) -> None:
    """Check 5.3 — current branch, unmerged branches, direct main commits."""
    if not _is_git_repo(project_dir):
        return

    branch = _run_git(project_dir, "rev-parse", "--abbrev-ref", "HEAD") or "unknown"

    # Check if committing directly to main/master
    if branch in ("main", "master"):
        # Count recent commits on main
        log_output = _run_git(project_dir, "log", "--oneline", "-5")
        commit_count = len(log_output.splitlines()) if log_output else 0

        if commit_count > 0:
            report.findings.append(HealthFinding(
                check_id="git.branches",
                title=f"Working directly on {branch}",
                severity="low",
                message=(
                    f"You're on '{branch}' and committing directly. "
                    f"That's like editing the original document without a copy. "
                    f"Create a branch: git checkout -b my-feature"
                ),
            ))

    # Count unmerged branches
    branches_output = _run_git(project_dir, "branch", "--no-merged")
    if branches_output:
        unmerged = [b.strip().lstrip("* ") for b in branches_output.splitlines() if b.strip()]
        if unmerged:
            report.findings.append(HealthFinding(
                check_id="git.branches",
                title=f"{len(unmerged)} unmerged branches",
                severity="info",
                message=(
                    f"Branches not merged: {', '.join(unmerged[:5])}. "
                    + (f"(and {len(unmerged) - 5} more) " if len(unmerged) > 5 else "")
                    + "Merge or delete them to keep things clean."
                ),
            ))


def check_gitignore(report: HealthReport, project_dir: str) -> None:
    """Check 5.4 — .gitignore existence and completeness."""
    root = Path(project_dir)
    gitignore = root / ".gitignore"

    if not gitignore.exists():
        report.findings.append(HealthFinding(
            check_id="git.gitignore",
            title="No .gitignore file",
            severity="medium",
            message=(
                "No .gitignore — you might be committing junk files. "
                "Create one: https://gitignore.io or 'npx gitignore node' / 'npx gitignore python'."
            ),
        ))
        return

    try:
        content = gitignore.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    # Check for common missing patterns
    missing = []

    # Detect project type and check relevant patterns
    has_python = any(root.rglob("*.py"))
    has_node = (root / "package.json").exists()

    if has_python:
        checks = {
            "__pycache__": "__pycache__/",
            ".venv": ".venv/ or venv/",
            "*.pyc": "*.pyc",
        }
        for pattern, desc in checks.items():
            if pattern not in content:
                missing.append(desc)

    if has_node:
        if "node_modules" not in content:
            missing.append("node_modules/")
        if ".next" not in content and (root / ".next").exists():
            missing.append(".next/")

    # Universal
    if ".env" not in content and any(root.glob(".env*")):
        missing.append(".env (secrets!)")
    if ".DS_Store" not in content:
        missing.append(".DS_Store")

    if missing:
        report.findings.append(HealthFinding(
            check_id="git.gitignore",
            title=f".gitignore missing: {', '.join(missing[:3])}",
            severity="medium" if ".env" in str(missing) else "low",
            message=(
                f".gitignore is missing: {', '.join(missing)}. "
                f"Without these, you might commit secrets or 40,000 node_modules files."
            ),
        ))


def generate_cheat_sheet(report: HealthReport, project_dir: str) -> None:
    """Check 5.5 — context-sensitive git commands based on current state."""
    if not _is_git_repo(project_dir):
        report.findings.append(HealthFinding(
            check_id="git.cheatsheet",
            title="Git quick start",
            severity="info",
            message="git init → git add . → git commit -m 'first commit'. Three commands. Done.",
        ))
        return

    commands = []

    status = _run_git(project_dir, "status", "--porcelain")
    if status:
        has_untracked = any(l.startswith("??") for l in status.splitlines() if l.strip())
        has_modified = any(l[1] == "M" for l in status.splitlines() if len(l) > 1)
        has_staged = any(l[0] in "AMDRC" for l in status.splitlines() if l.strip())

        if has_untracked:
            commands.append("git add <file> — start tracking a new file")
        if has_modified:
            commands.append("git add <file> — stage your changes for commit")
        if has_staged:
            commands.append("git commit -m 'description' — save staged changes")
        if has_modified or has_untracked:
            commands.append("git stash — temporarily hide changes, work on something else")
    else:
        commands.append("git log --oneline -5 — see recent history")
        commands.append("git diff — see what changed since last commit")

    branch = _run_git(project_dir, "rev-parse", "--abbrev-ref", "HEAD") or ""
    if branch in ("main", "master"):
        commands.append(f"git checkout -b my-feature — create a branch before changing {branch}")

    if commands:
        cmd_text = " | ".join(commands[:4])
        report.findings.append(HealthFinding(
            check_id="git.cheatsheet",
            title="Git commands you need right now",
            severity="info",
            message=cmd_text,
        ))


def run_git_survival_checks(report: HealthReport, project_dir: str) -> None:
    """Run all git survival checks."""
    check_git_status(report, project_dir)
    check_commit_quality(report, project_dir)
    check_branch_awareness(report, project_dir)
    check_gitignore(report, project_dir)
    generate_cheat_sheet(report, project_dir)
