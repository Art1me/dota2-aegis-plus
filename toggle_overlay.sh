#!/usr/bin/env bash
# AegisPlus Controller (Launcher & Steam Overlay Toggle)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ACTION="${1:-toggle}"

case "$ACTION" in
    quit|stop|exit|kill)
        curl -s -f -m 0.5 -X POST "http://127.0.0.1:3000/api/quit" >/dev/null 2>&1 || true
        sleep 0.2
        pkill -9 -f "overlay_window\.py" 2>/dev/null || true
        fuser -k 3000/tcp 2>/dev/null || true
        echo "AegisPlus полностью остановлен."
        exit 0
        ;;
    show|open)
        ENDPOINT="open"
        ;;
    close|hide)
        ENDPOINT="close"
        ;;
    *)
        ENDPOINT="toggle"
        ;;
esac

# 1. Try sending instant IPC command to running local server
if curl -s -f -m 0.5 -X POST "http://127.0.0.1:3000/api/overlay/$ENDPOINT" >/dev/null 2>&1; then
    exit 0
fi

# 2. Server is not running -> launch start.sh via setsid
setsid "$DIR/start.sh" >/tmp/aegisplus.log 2>&1 &
