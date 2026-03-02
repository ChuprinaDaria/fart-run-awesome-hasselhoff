#!/usr/bin/env bash
# Claude Monitor wrapper.
# Use instead of 'claude' command.
# Add to ~/.bashrc: alias claude="~/claude-monitor/claude-wrapper.sh"

MONITOR_DIR="$(dirname "$0")"

# запускаємо claude з усіма аргументами
claude "$@"

# після завершення — питаємо про результат
python3 "$MONITOR_DIR/hook.py"