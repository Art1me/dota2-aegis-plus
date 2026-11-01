#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

# 1. If already running, just open overlay and exit immediately!
if curl -s -f -m 0.5 -X POST "http://127.0.0.1:3000/api/overlay/open" >/dev/null 2>&1; then
    echo "🛡️  AegisPlus уже запущен! Оверлей развернут на экране."
    exit 0
fi

echo "=========================================================="
echo "🛡️  AegisPlus - Профессиональный Dota 2 Overlay Assistant"
echo "=========================================================="

PID_FILE="/tmp/aegisplus.pid"
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ]; then
        kill -9 "$OLD_PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
fi

pkill -f "overlay_window\.py" 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
sleep 0.2

# Check and install GSI config
export PYTHONPATH="$DIR:$PYTHONPATH"
python3 "$DIR/backend/config_manager.py"

# Preload libgtk4-layer-shell for Wayland Layer Shell support
for lib in /usr/lib64/libgtk4-layer-shell.so /usr/lib/libgtk4-layer-shell.so /usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so; do
    if [ -f "$lib" ]; then
        export LD_PRELOAD="$lib${LD_PRELOAD:+:$LD_PRELOAD}"
        break
    fi
done

export PYTHONUNBUFFERED=1
export WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1

echo "🚀 Запуск AegisPlus..."
echo "👉 Оверлей: прозрачное окно поверх экрана"
echo "👉 Веб-панель: доступна по адресу http://127.0.0.1:3000 (также работает в Shift+Tab внутри игры)"
echo "----------------------------------------------------------"

exec python3 "$DIR/overlay_window.py"
