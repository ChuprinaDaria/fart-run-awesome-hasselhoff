"""SQLite persistence for usage trends and history."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.platform import get_platform


class HistoryDB:
    def __init__(self, db_path: str | None = None):
        if db_path and db_path != ":memory:":
            self._path = db_path
        elif db_path == ":memory:":
            self._path = ":memory:"
        else:
            data_dir = get_platform().data_dir()
            data_dir.mkdir(parents=True, exist_ok=True)
            self._path = str(data_dir / "history.db")
        self._conn: sqlite3.Connection | None = None

    def _ensure_conn(self) -> None:
        if self._conn is None:
            self.init()

    def init(self) -> None:
        self._conn = sqlite3.connect(self._path, timeout=10)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                tokens INTEGER,
                cost REAL,
                cache_efficiency REAL,
                sessions INTEGER,
                security_score INTEGER
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                label TEXT NOT NULL,
                project_dir TEXT NOT NULL,
                git_branch TEXT DEFAULT '',
                git_last_commit TEXT DEFAULT '',
                git_tracked_count INTEGER DEFAULT 0,
                git_dirty_files TEXT DEFAULT '[]',
                containers TEXT DEFAULT '[]',
                listening_ports TEXT DEFAULT '[]',
                config_checksums TEXT DEFAULT '{}'
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_dir TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                entry_json TEXT NOT NULL,
                haiku_summary TEXT DEFAULT '',
                haiku_context TEXT DEFAULT ''
            )
        """)
        # Safety Net tables
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS save_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                label TEXT NOT NULL,
                project_dir TEXT NOT NULL,
                branch TEXT NOT NULL,
                commit_hash TEXT NOT NULL,
                tag_name TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                lines_total INTEGER DEFAULT 0,
                hint_level INTEGER DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS rollback_backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                project_dir TEXT NOT NULL,
                save_point_id INTEGER NOT NULL,
                backup_branch TEXT NOT NULL,
                backup_commit TEXT NOT NULL,
                files_changed INTEGER DEFAULT 0,
                picked_files TEXT DEFAULT '[]',
                FOREIGN KEY (save_point_id) REFERENCES save_points(id)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS git_education (
                project_dir TEXT PRIMARY KEY,
                saves_count INTEGER DEFAULT 0,
                rollbacks_count INTEGER DEFAULT 0,
                picks_count INTEGER DEFAULT 0,
                gitignore_created INTEGER DEFAULT 0,
                git_initialized INTEGER DEFAULT 0
            )
        """)
        self._conn.commit()

        try:
            self._conn.execute("SELECT haiku_label FROM snapshots LIMIT 1")
        except sqlite3.OperationalError:
            self._conn.execute("ALTER TABLE snapshots ADD COLUMN haiku_label TEXT DEFAULT ''")
            self._conn.commit()

    def get_state(self, key: str) -> str | None:
        self._ensure_conn()
        cursor = self._conn.execute(
            "SELECT value FROM app_state WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str) -> None:
        self._ensure_conn()
        self._conn.execute(
            "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    def save_daily_stats(self, date: str, tokens: int, cost: float,
                         cache_efficiency: float, sessions: int,
                         security_score: int) -> None:
        self._ensure_conn()
        self._conn.execute("""
            INSERT OR REPLACE INTO daily_stats
            (date, tokens, cost, cache_efficiency, sessions, security_score)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (date, tokens, cost, cache_efficiency, sessions, security_score))
        self._conn.commit()

    def get_daily_stats(self, days: int = 30) -> list[dict]:
        self._ensure_conn()
        cursor = self._conn.execute("""
            SELECT date, tokens, cost, cache_efficiency, sessions, security_score
            FROM daily_stats
            ORDER BY date DESC
            LIMIT ?
        """, (days,))
        return [
            {"date": r[0], "tokens": r[1], "cost": r[2],
             "cache_efficiency": r[3], "sessions": r[4], "security_score": r[5]}
            for r in cursor.fetchall()
        ]

    def save_activity(self, project_dir: str, timestamp: str,
                      entry_json: str, haiku_summary: str = "",
                      haiku_context: str = "") -> int:
        self._ensure_conn()
        cursor = self._conn.execute(
            """INSERT INTO activity_log
               (project_dir, timestamp, entry_json, haiku_summary, haiku_context)
               VALUES (?, ?, ?, ?, ?)""",
            (project_dir, timestamp, entry_json, haiku_summary, haiku_context),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_activity_log(self, project_dir: str, limit: int = 20) -> list[dict]:
        self._ensure_conn()
        cursor = self._conn.execute(
            """SELECT id, timestamp, entry_json, haiku_summary, haiku_context
               FROM activity_log WHERE project_dir = ?
               ORDER BY id DESC LIMIT ?""",
            (project_dir, limit),
        )
        return [
            {"id": r[0], "timestamp": r[1], "entry_json": r[2],
             "haiku_summary": r[3], "haiku_context": r[4]}
            for r in cursor.fetchall()
        ]

    # --- Safety Net: Save Points ---

    def add_save_point(self, timestamp: str, label: str, project_dir: str,
                       branch: str, commit_hash: str, tag_name: str,
                       file_count: int = 0, lines_total: int = 0,
                       hint_level: int = 0) -> int:
        self._ensure_conn()
        cursor = self._conn.execute(
            """INSERT INTO save_points
               (timestamp, label, project_dir, branch, commit_hash, tag_name,
                file_count, lines_total, hint_level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, label, project_dir, branch, commit_hash, tag_name,
             file_count, lines_total, hint_level),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_save_points(self, project_dir: str, limit: int = 20) -> list[dict]:
        self._ensure_conn()
        cursor = self._conn.execute(
            """SELECT id, timestamp, label, branch, commit_hash, tag_name,
                      file_count, lines_total, hint_level
               FROM save_points WHERE project_dir = ?
               ORDER BY id DESC LIMIT ?""",
            (project_dir, limit),
        )
        return [
            {"id": r[0], "timestamp": r[1], "label": r[2], "branch": r[3],
             "commit_hash": r[4], "tag_name": r[5], "file_count": r[6],
             "lines_total": r[7], "hint_level": r[8]}
            for r in cursor.fetchall()
        ]

    def get_save_point(self, save_point_id: int) -> dict | None:
        self._ensure_conn()
        cursor = self._conn.execute(
            """SELECT id, timestamp, label, project_dir, branch, commit_hash,
                      tag_name, file_count, lines_total, hint_level
               FROM save_points WHERE id = ?""",
            (save_point_id,),
        )
        r = cursor.fetchone()
        if not r:
            return None
        return {"id": r[0], "timestamp": r[1], "label": r[2], "project_dir": r[3],
                "branch": r[4], "commit_hash": r[5], "tag_name": r[6],
                "file_count": r[7], "lines_total": r[8], "hint_level": r[9]}

    def delete_save_point(self, save_point_id: int) -> None:
        self._ensure_conn()
        self._conn.execute("DELETE FROM save_points WHERE id = ?", (save_point_id,))
        self._conn.commit()

    def count_save_points(self, project_dir: str) -> int:
        self._ensure_conn()
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM save_points WHERE project_dir = ?",
            (project_dir,),
        )
        return cursor.fetchone()[0]

    # --- Safety Net: Rollback Backups ---

    def add_rollback_backup(self, timestamp: str, project_dir: str,
                            save_point_id: int, backup_branch: str,
                            backup_commit: str, files_changed: int = 0) -> int:
        self._ensure_conn()
        cursor = self._conn.execute(
            """INSERT INTO rollback_backups
               (timestamp, project_dir, save_point_id, backup_branch,
                backup_commit, files_changed)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (timestamp, project_dir, save_point_id, backup_branch,
             backup_commit, files_changed),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_rollback_backups(self, project_dir: str) -> list[dict]:
        self._ensure_conn()
        cursor = self._conn.execute(
            """SELECT rb.id, rb.timestamp, rb.save_point_id, rb.backup_branch,
                      rb.backup_commit, rb.files_changed, rb.picked_files,
                      sp.label as sp_label
               FROM rollback_backups rb
               LEFT JOIN save_points sp ON rb.save_point_id = sp.id
               WHERE rb.project_dir = ?
               ORDER BY rb.id DESC""",
            (project_dir,),
        )
        return [
            {"id": r[0], "timestamp": r[1], "save_point_id": r[2],
             "backup_branch": r[3], "backup_commit": r[4],
             "files_changed": r[5], "picked_files": r[6],
             "sp_label": r[7] or ""}
            for r in cursor.fetchall()
        ]

    def update_picked_files(self, backup_id: int, picked_json: str) -> None:
        self._ensure_conn()
        self._conn.execute(
            "UPDATE rollback_backups SET picked_files = ? WHERE id = ?",
            (picked_json, backup_id),
        )
        self._conn.commit()

    # --- Safety Net: Git Education ---

    def get_git_education(self, project_dir: str) -> dict:
        self._ensure_conn()
        cursor = self._conn.execute(
            "SELECT saves_count, rollbacks_count, picks_count, gitignore_created, git_initialized "
            "FROM git_education WHERE project_dir = ?",
            (project_dir,),
        )
        r = cursor.fetchone()
        if not r:
            return {"saves_count": 0, "rollbacks_count": 0, "picks_count": 0,
                    "gitignore_created": 0, "git_initialized": 0}
        return {"saves_count": r[0], "rollbacks_count": r[1], "picks_count": r[2],
                "gitignore_created": r[3], "git_initialized": r[4]}

    def bump_git_education(self, project_dir: str, field: str) -> None:
        self._ensure_conn()
        self._conn.execute(
            "INSERT OR IGNORE INTO git_education (project_dir) VALUES (?)",
            (project_dir,),
        )
        if field in ("saves_count", "rollbacks_count", "picks_count"):
            self._conn.execute(
                f"UPDATE git_education SET {field} = {field} + 1 WHERE project_dir = ?",
                (project_dir,),
            )
        elif field in ("gitignore_created", "git_initialized"):
            self._conn.execute(
                f"UPDATE git_education SET {field} = 1 WHERE project_dir = ?",
                (project_dir,),
            )
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
