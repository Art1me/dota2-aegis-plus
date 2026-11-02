#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

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

# Clean up any lingering processes on port 3000 and old instances
pkill -f "overlay_window\.py" 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
sleep 0.2

# Preload libgtk4-layer-shell.so before libwayland-client loads
if [ -f "/usr/lib64/libgtk4-layer-shell.so" ]; then
    export LD_PRELOAD="/usr/lib64/libgtk4-layer-shell.so"
elif [ -f "/usr/lib/libgtk4-layer-shell.so" ]; then
    export LD_PRELOAD="/usr/lib/libgtk4-layer-shell.so"
fi

export WEBKIT_DISABLE_DMABUF_RENDERER=1
export WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1
export PYTHONUNBUFFERED=1
export PYTHONPATH="$DIR:$PYTHONPATH"

# Run config manager (GSI cfg, Hyprland rules check, Steam check)
python3 "$DIR/backend/config_manager.py"

echo "🚀 Запуск AegisPlus..."
echo "👉 Оверлей: прозрачное окно поверх экрана (Wayland Layer Shell)"
echo "👉 Веб-панель: доступна по адресу http://127.0.0.1:3000"
echo "----------------------------------------------------------"

exec python3 "$DIR/overlay_window.py"
