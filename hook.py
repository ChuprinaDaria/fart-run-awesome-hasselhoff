#!/usr/bin/env python3
"""
Claude Monitor Hook.
Run after Claude Code session ends.
Asks user for outcome and saves to DB.

Usage: add to ~/.bashrc or use as wrapper script.
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone


def get_latest_session_id() -> str | None:
    """Find the most recently modified JSONL session file."""
    projects_dir = Path.home() / ".claude" / "projects"
    latest_file = None
    latest_mtime = 0

    for f in projects_dir.glob("**/*.jsonl"):
        if "subagents" in str(f):
            continue
        mtime = f.stat().st_mtime
        if mtime > latest_mtime:
            latest_mtime = mtime
            latest_file = f

    if not latest_file:
        return None

    # витягуємо session_id з файлу
    with open(latest_file, errors="ignore") as fp:
        for line in fp:
            try:
                d = json.loads(line)
                sid = d.get("sessionId")
                if sid:
                    return sid
            except Exception:
                continue
    return None


def ask_outcome() -> str | None:
    """Ask user about the session outcome."""
    print("\n" + "─" * 50)
    print("  Claude Monitor — оцінка сесії")
    print("─" * 50)
    print("  Задача вирішена? Як? (Enter = пропустити)")
    print("  Приклади: 'так, баг пофіксено'")
    print("            'частково, залишився деплой'")
    print("            'ні, неправильно зрозумів задачу'")
    print("─" * 50)

    try:
        outcome = input("  > ").strip()
        return outcome if outcome else None
    except (KeyboardInterrupt, EOFError):
        return None


def save_outcome(session_id: str, outcome: str):
    """Update outcome in DB."""
    try:
        import psycopg2
        conn = psycopg2.connect(dbname="claude_monitor")
        cur = conn.cursor()
        cur.execute(
            "UPDATE sessions SET outcome = %s WHERE session_id = %s",
            (outcome, session_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        print(f"  ✓ Збережено\n")
    except Exception as e:
        print(f"  DB error: {e}\n")


def embed_session(session_id: str):
    """Embed current session silently."""
    try:
        import psycopg2
        from analyzer import embed
        conn = psycopg2.connect(dbname="claude_monitor")
        cur = conn.cursor()
        cur.execute(
            "SELECT first_user_message FROM sessions WHERE session_id = %s AND embedding IS NULL",
            (session_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0]:
            emb = embed(row[0])
            if emb:
                conn = psycopg2.connect(dbname="claude_monitor")
                cur = conn.cursor()
                cur.execute(
                    "UPDATE sessions SET embedding = %s WHERE session_id = %s",
                    (emb, session_id)
                )
                conn.commit()
                cur.close()
                conn.close()
                print("  ✓ Ембединг збережено\n")
    except Exception:
        pass


def run():
    session_id = get_latest_session_id()
    if not session_id:
        return

    outcome = ask_outcome()
    if outcome:
        save_outcome(session_id, outcome)
    else:
        print("  Пропущено\n")

    embed_session(session_id)


if __name__ == "__main__":
    run()