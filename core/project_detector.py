"""Auto-detect projects from ~/.claude/projects/ directory."""
from __future__ import annotations
import logging
from pathlib import Path
from core.history import HistoryDB

log = logging.getLogger(__name__)
_LAST_PROJECT_KEY = "last_project_dir"


def detect_projects(claude_dir: str) -> list[dict]:
    """Scan claude_dir/projects/ for project directories.
    Returns list of {path, mtime, name} sorted by most recent first.
    Claude stores projects as encoded paths: -home-user-project
    """
    projects_dir = Path(claude_dir) / "projects"
    if not projects_dir.is_dir():
        return []
    results = []
    for entry in projects_dir.iterdir():
        if not entry.is_dir():
            continue
        # Decode: -home-user-project → /home/user/project
        decoded = "/" + entry.name[1:].replace("-", "/") if entry.name.startswith("-") else entry.name
        try:
            mtime = max(
                (f.stat().st_mtime for f in entry.rglob("*") if f.is_file()),
                default=entry.stat().st_mtime,
            )
        except OSError:
            mtime = 0
        real_path = Path(decoded)
        if real_path.is_dir():
            results.append({"path": decoded, "mtime": mtime, "name": real_path.name})
        else:
            results.append({"path": decoded, "mtime": mtime, "name": entry.name})
    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results


def get_last_project(db: HistoryDB) -> str | None:
    return db.get_state(_LAST_PROJECT_KEY)


def save_last_project(db: HistoryDB, path: str) -> None:
    db.set_state(_LAST_PROJECT_KEY, path)
