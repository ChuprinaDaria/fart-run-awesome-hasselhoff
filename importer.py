"""
Import all parsed sessions into PostgreSQL.
Run once to backfill, then periodically for new sessions.
"""

from parser import parse_all_sessions
from db import save_session, get_stats


def import_all():
    print("Parsing sessions...")
    sessions = parse_all_sessions()
    print(f"Found {len(sessions)} sessions. Importing...")

    ok = 0
    skip = 0
    for s in sessions:
        try:
            save_session(s)
            ok += 1
        except Exception as e:
            print(f"  skip {s['session_id'][:8]}: {e}")
            skip += 1

    print(f"Done: {ok} imported, {skip} skipped.")
    print()

    stats = get_stats()
    print(f"Total sessions: {stats['total_sessions']}")
    print(f"Total tokens:   {stats['total_tokens']:,}")
    print(f"Opus sessions:  {stats['opus_sessions']}")
    print(f"Sonnet sessions:{stats['sonnet_sessions']}")
    print(f"Today tokens:   {stats['today_tokens']:,}")


if __name__ == "__main__":
    import_all()