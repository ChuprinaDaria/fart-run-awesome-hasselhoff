#!/usr/bin/env bash
# Claude Monitor wrapper.
# Use instead of 'claude' command.
# Add to ~/.bashrc: alias claude="~/claude-monitor/claude-wrapper.sh"

MONITOR_DIR="$(dirname "$0")"

# показуємо рекомендацію моделі якщо є аргументи (задача відома заздалегідь)
if [ $# -gt 0 ]; then
    python3 "$MONITOR_DIR/analyzer.py" --recommend "$*" 2>/dev/null
fi

# запускаємо claude з усіма аргументами
claude "$@"

# після завершення — питаємо про результат і зберігаємо ембединг
python3 "$MONITOR_DIR/hook.py"
