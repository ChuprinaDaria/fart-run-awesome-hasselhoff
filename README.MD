# Claude Code Usage Monitor

A lightweight local tool that tracks your Claude Code CLI sessions, token usage, and helps you use the right model for the right task.

```
╔══════════════════════════════════════════════════════════════╗
║              CLAUDE CODE USAGE MONITOR                       ║
║  2026-03-02 09:45:00                                         ║
╠══════════════════════════════════════════════════════════════╣
║  ▸ OVERALL                                                   ║
║  Total sessions : 52                                         ║
║  Total tokens   : 1.6M                                       ║
║  Avg per session: 30.4K                                      ║
║  ─────────────────────────────────────────────────────────   ║
║  ▸ TODAY                                                     ║
║  Sessions: 3   Tokens: 45.2K                                 ║
║  ─────────────────────────────────────────────────────────   ║
║  ▸ MODELS                                                    ║
║  OPUS   [████████████████░░░░░░░░░░] 37                      ║
║  SONNET [██████░░░░░░░░░░░░░░░░░░░░] 14                      ║
╚══════════════════════════════════════════════════════════════╝
```

## What it does

- Parses all Claude Code JSONL session logs from `~/.claude/projects/`
- Stores session data in local PostgreSQL with pgvector
- After each session asks you: *"Was the task solved? How?"*
- Shows a Matrix-style terminal dashboard with token usage, model distribution, recent sessions
- Ollama integration (coming): recommends Opus vs Sonnet based on past similar tasks

## Platform support

| Platform | Status |
|----------|--------|
| Linux    | ✅ Full support |
| macOS    | 🔜 Planned (separate branch, kqueue) |
| Windows  | use Linux |

## Requirements

- Linux
- Python 3.12+
- PostgreSQL 16+
- `postgresql-16-pgvector`
- `psycopg2-binary`

## Installation

```bash
# 1. Clone
git clone https://github.com/ChuprinaDaria/claude-code-usage-monitor
cd claude-code-usage-monitor

# 2. Install dependencies
sudo apt install postgresql postgresql-contrib postgresql-16-pgvector
pip install psycopg2-binary --break-system-packages

# 3. Setup PostgreSQL
sudo -u postgres createuser --superuser $USER
sudo -u postgres createdb claude_monitor
psql -d claude_monitor -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 4. Import existing sessions
python3 importer.py

# 5. Add alias to ~/.bashrc
echo 'alias claude="~/claude-code-usage-monitor/claude-wrapper.sh"' >> ~/.bashrc
source ~/.bashrc
```

## Usage

```bash
# Run dashboard
python3 dashboard.py

# Import new sessions manually
python3 importer.py

# The wrapper runs automatically when you use 'claude' command
claude  # asks for outcome after session ends
```

## How outcome tracking works

After each Claude Code session ends, you'll see:

```
──────────────────────────────────────────────────
  Claude Monitor — session outcome
──────────────────────────────────────────────────
  Task solved? How? (Enter to skip)
  Examples: 'yes, bug fixed'
            'partially, deploy still pending'
            'no, misunderstood the task'
──────────────────────────────────────────────────
  > 
```

This data is stored locally and will be used by the Ollama analyzer to learn which model works best for which types of tasks.

> **Note:** For meaningful outcome tracking, please fill this in after each session. The AI recommendation feature depends on this data.

## Project structure

```
claude-code-usage-monitor/
  parser.py          # reads ~/.claude/projects/**/*.jsonl
  db.py              # PostgreSQL schema and operations
  importer.py        # backfill all existing sessions
  dashboard.py       # Matrix-style terminal dashboard
  hook.py            # post-session outcome prompt
  claude-wrapper.sh  # wrapper script for 'claude' alias
  README.md
```

## Roadmap

- [ ] Ollama integration — local LLM analyzes task + history, recommends model
- [ ] Real-time inotify daemon (C) — watches logs as sessions happen
- [ ] macOS support (kqueue branch)
- [ ] Token budget alerts

## License

MIT