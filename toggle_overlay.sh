#!/usr/bin/env bash
# AegisPlus Toggle Controller (Steam Overlay style toggle)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

PID=$(pgrep -f "python3.*overlay_window.py" | head -n 1)

if [ -n "$PID" ]; then
    kill -SIGUSR1 "$PID"
else
    nohup "$DIR/start.sh" >/tmp/aegisplus.log 2>&1 &
fi
