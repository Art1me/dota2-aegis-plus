#!/usr/bin/env bash
# AegisPlus Controller (Launcher & Steam Overlay Toggle)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ACTION="${1:-toggle}"

case "$ACTION" in
    quit|stop|exit|kill)
        curl -s -f -m 0.5 -X POST "http://127.0.0.1:3000/api/shutdown" >/dev/null 2>&1 || true
        sleep 0.2
        pkill -TERM -f "overlay_window\.py" 2>/dev/null || true
        fuser -k 3000/tcp 2>/dev/null || true
        echo "AegisPlus полностью остановлен."
        exit 0
        ;;
    close|hide)
        curl -s -f -m 0.5 -X POST "http://127.0.0.1:3000/api/close_menu" >/dev/null 2>&1 || true
        exit 0
        ;;
    show|open)
        if pgrep -f "overlay_window\.py" >/dev/null 2>&1; then
            curl -s -f -m 0.5 -X POST "http://127.0.0.1:3000/api/overlay/open" >/dev/null 2>&1 || true
            exit 0
        fi
        setsid "$DIR/start.sh" >/tmp/aegisplus.log 2>&1 &
        exit 0
        ;;
    toggle|*)
        if pgrep -f "overlay_window\.py" >/dev/null 2>&1; then
            pkill -USR1 -f "overlay_window\.py"
            exit 0
        fi
        setsid "$DIR/start.sh" >/tmp/aegisplus.log 2>&1 &
        exit 0
        ;;
esac
