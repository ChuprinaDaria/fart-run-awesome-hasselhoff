"""
Database setup and operations for Claude Monitor.
PostgreSQL + pgvector.
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor


DB_NAME = "claude_monitor"


def get_conn():
    return psycopg2.connect(dbname=DB_NAME)


def init_db():
    """Create tables if not exist."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE EXTENSION IF NOT EXISTS vector;

        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            session_id TEXT UNIQUE NOT NULL,
            project TEXT,
            timestamp TIMESTAMPTZ,
            model TEXT,
            input_tokens INT DEFAULT 0,
            output_tokens INT DEFAULT 0,
            cache_read_tokens INT DEFAULT 0,
            cache_creation_tokens INT DEFAULT 0,
            total_tokens INT DEFAULT 0,
            duration_ms INT,
            assistant_turns INT DEFAULT 0,
            first_user_message TEXT,
            skills_used TEXT[],
            outcome TEXT,
            embedding vector(1024)
        );

        CREATE INDEX IF NOT EXISTS sessions_timestamp_idx ON sessions(timestamp);
        CREATE INDEX IF NOT EXISTS sessions_model_idx ON sessions(model);
        CREATE INDEX IF NOT EXISTS sessions_project_idx ON sessions(project);
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("DB initialized.")


def save_session(session: dict, embedding: list | None = None):
    """Insert or update a session."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO sessions (
            session_id, project, timestamp, model,
            input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
            total_tokens, duration_ms, assistant_turns,
            first_user_message, skills_used, outcome, embedding
        ) VALUES (
            %(session_id)s, %(project)s, %(timestamp)s, %(model)s,
            %(input_tokens)s, %(output_tokens)s, %(cache_read_tokens)s, %(cache_creation_tokens)s,
            %(total_tokens)s, %(duration_ms)s, %(assistant_turns)s,
            %(first_user_message)s, %(skills_used)s, %(outcome)s, %(embedding)s
        )
        ON CONFLICT (session_id) DO UPDATE SET
            outcome = EXCLUDED.outcome,
            embedding = COALESCE(EXCLUDED.embedding, sessions.embedding)
    """, {**session, "embedding": embedding})

    conn.commit()
    cur.close()
    conn.close()


def get_stats() -> dict:
    """Basic usage stats."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT
            COUNT(*) as total_sessions,
            SUM(total_tokens) as total_tokens,
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            AVG(total_tokens) as avg_tokens_per_session,
            COUNT(*) FILTER (WHERE model LIKE '%opus%') as opus_sessions,
            COUNT(*) FILTER (WHERE model LIKE '%sonnet%') as sonnet_sessions,
            COUNT(*) FILTER (WHERE model LIKE '%haiku%') as haiku_sessions
        FROM sessions
    """)
    stats = dict(cur.fetchone())

    cur.execute("""
        SELECT
            COUNT(*) as total_sessions,
            SUM(total_tokens) as total_tokens
        FROM sessions
        WHERE timestamp > NOW() - INTERVAL '24 hours'
    """)
    today = dict(cur.fetchone())
    stats["today_sessions"] = today["total_sessions"]
    stats["today_tokens"] = today["total_tokens"] or 0

    cur.close()
    conn.close()
    return stats


def find_similar(embedding: list, limit: int = 5) -> list:
    """Find sessions with similar task embeddings."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT
            session_id, project, timestamp, model,
            total_tokens, first_user_message, outcome,
            1 - (embedding <=> %s::vector) as similarity
        FROM sessions
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, (embedding, embedding, limit))

    results = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return results


if __name__ == "__main__":
    init_db()
    stats = get_stats()
    print("Stats:", json.dumps(stats, indent=2, default=str))