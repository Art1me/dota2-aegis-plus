#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chmod +x "$SCRIPT_DIR/start.sh" "$SCRIPT_DIR/toggle_overlay.sh" 2>/dev/null || true

ACTION="${1:-toggle}"

case "$ACTION" in
    quit|stop|exit|kill)
        curl -s --max-time 0.3 -X POST "http://127.0.0.1:3000/api/shutdown" >/dev/null 2>&1 || true
        pkill -TERM -f "overlay_window\.py" 2>/dev/null || true
        exit 0
        ;;
    close|hide)
        curl -s --max-time 0.3 -X POST "http://127.0.0.1:3000/api/close_menu" >/dev/null 2>&1 || true
        exit 0
        ;;
    show|open)
        if curl -s --max-time 0.3 -X POST "http://127.0.0.1:3000/api/overlay/open" >/dev/null 2>&1; then
            exit 0
        fi
        setsid -f "$SCRIPT_DIR/start.sh" >/tmp/aegis_plus.log 2>&1
        exit 0
        ;;
    toggle|*)
        if curl -s --max-time 0.3 -X POST "http://127.0.0.1:3000/api/toggle_menu" >/dev/null 2>&1; then
            exit 0
        fi

        # If server is not responding, check if process exists and send signal
        if pgrep -f "overlay_window\.py" >/dev/null 2>&1; then
            pkill -USR1 -f "overlay_window\.py" 2>/dev/null || true
            exit 0
        fi

        # Otherwise start the overlay in background
        setsid -f "$SCRIPT_DIR/start.sh" >/tmp/aegis_plus.log 2>&1
        exit 0
        ;;
esac
