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

    def close(self) -> None:
        if self._conn:
            self._conn.close()
