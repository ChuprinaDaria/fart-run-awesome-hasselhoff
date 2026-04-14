#!/usr/bin/env python3
"""
Claude Monitor Analyzer.
Embeds session tasks via mxbai-embed-large,
finds similar past sessions,
recommends model via qwen2.5:3b.
"""

import json
import requests
from db import get_conn, find_similar, save_session


OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
LLM_MODEL = "qwen2.5:3b"


def embed(text: str) -> list[float] | None:
    """Get embedding for text via Ollama."""
    if not text or not text.strip():
        return None
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": text},
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        # api/embed returns {"embeddings": [[...]]}
        embeddings = data.get("embeddings") or data.get("embedding")
        if isinstance(embeddings, list) and embeddings:
            if isinstance(embeddings[0], list):
                return embeddings[0]
            return embeddings
    except Exception as e:
        print(f"  Embed error: {e}")
    return None


def recommend(task: str, similar: list) -> str | None:
    """Ask Qwen to recommend model based on task and similar sessions."""
    if not similar:
        return None

    examples = ""
    for s in similar[:3]:
        model = s.get("model", "?")
        tokens = s.get("total_tokens", 0)
        outcome = s.get("outcome") or "no outcome"
        prev_task = (s.get("first_user_message") or "")[:100]
        examples += f"- Task: {prev_task}\n  Model: {model}, Tokens: {tokens}, Result: {outcome}\n"

    prompt = f"""You are a Claude Code assistant. Based on similar past sessions, recommend which Claude model to use.

Current task: {task[:200]}

Similar past sessions:
{examples}

Rules:
- Opus: complex architecture, design decisions, hard bugs
- Sonnet: routine tasks, refactoring, small fixes, explanations

Reply in ONE short sentence. Example: "Use Sonnet — similar tasks worked well with 30K tokens."
"""

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": LLM_MODEL, "prompt": prompt, "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except Exception as e:
        print(f"  LLM error: {e}")
    return None


def embed_batch(texts: list[str]) -> list[list[float]] | None:
    """Embed multiple texts in one API call."""
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": texts},
            timeout=300,
        )
        r.raise_for_status()
        embeddings = r.json().get("embeddings")
        if isinstance(embeddings, list) and len(embeddings) == len(texts):
            return embeddings
    except Exception as e:
        print(f"  Batch embed error: {e}")
    return None


def embed_all_sessions():
    """Backfill embeddings for all sessions that don't have one."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT session_id, first_user_message
        FROM sessions
        WHERE embedding IS NULL AND first_user_message IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        print("Нічого ембедити.")
        return

    print(f"Embedding {len(rows)} sessions (chunks of 10)...")
    CHUNK = 10
    ok = 0
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        ids = [r[0] for r in chunk]
        texts = [r[1] for r in chunk]
        print(f"  Chunk {i//CHUNK + 1}: {len(texts)} texts...")
        embeddings = embed_batch(texts)
        if not embeddings:
            print(f"  Chunk failed, skipping.")
            continue
        conn = get_conn()
        cur = conn.cursor()
        for session_id, emb in zip(ids, embeddings):
            cur.execute(
                "UPDATE sessions SET embedding = %s WHERE session_id = %s",
                (emb, session_id)
            )
            ok += 1
        conn.commit()
        cur.close()
        conn.close()
        print(f"  ✓ {ok} total done")

    print(f"Done: {ok}/{len(rows)} embedded.")


def analyze_task(task: str) -> str | None:
    """
    Main entry point: embed task, find similar, get recommendation.
    Returns recommendation string or None.
    """
    emb = embed(task)
    if not emb:
        return None

    similar = find_similar(emb, limit=5)
    if not similar:
        return None

    return recommend(task, similar)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--recommend":
        task = " ".join(sys.argv[2:])
        rec = analyze_task(task)
        if rec:
            print(f"\n  Рекомендація моделі: {rec}\n")
    else:
        # backfill embeddings
        embed_all_sessions()

        # test recommendation
        test_task = "fix the bug in the authentication middleware"
        print(f"\nTest task: {test_task}")
        rec = analyze_task(test_task)
        print(f"Recommendation: {rec}")