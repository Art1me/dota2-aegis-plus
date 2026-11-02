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

# Clean up lingering processes on port 3000 and old instances
pkill -f "overlay_window\.py" 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
sleep 0.2

# Explicit Wayland environment setup
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [ -z "$WAYLAND_DISPLAY" ]; then
    DETECTED_WL=$(find "$XDG_RUNTIME_DIR" -maxdepth 1 -name "wayland-[0-9]*" -type s 2>/dev/null | head -n 1)
    if [ -n "$DETECTED_WL" ]; then
        export WAYLAND_DISPLAY="$(basename "$DETECTED_WL")"
    else
        export WAYLAND_DISPLAY="wayland-1"
    fi
fi
export GDK_BACKEND=wayland
export GSK_RENDERER=gl

# Preload libgtk4-layer-shell.so before libwayland-client loads
if [ -f "/usr/lib64/libgtk4-layer-shell.so" ]; then
    export LD_PRELOAD="/usr/lib64/libgtk4-layer-shell.so"
elif [ -f "/usr/lib/libgtk4-layer-shell.so" ]; then
    export LD_PRELOAD="/usr/lib/libgtk4-layer-shell.so"
fi

export WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1
export PYTHONUNBUFFERED=1
export PYTHONPATH="$DIR:$PYTHONPATH"

# Run config manager (GSI cfg, Hyprland binds, Steam check)
python3 "$DIR/backend/config_manager.py"

echo "🚀 Запуск AegisPlus..."
echo "👉 Оверлей: Wayland ($WAYLAND_DISPLAY, GDK_BACKEND=$GDK_BACKEND, GSK_RENDERER=$GSK_RENDERER)"
echo "👉 Веб-панель: доступна по адресу http://127.0.0.1:3000"
echo "----------------------------------------------------------"

exec python3 "$DIR/overlay_window.py"
