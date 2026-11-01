#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "=========================================================="
echo "🛡️  AegisPlus - Профессиональный Dota 2 Overlay Assistant"
echo "=========================================================="

# Check and install GSI config
export PYTHONPATH="$DIR:$PYTHONPATH"
python3 "$DIR/backend/config_manager.py"

echo "🚀 Запуск AegisPlus..."
echo "👉 Оверлей: прозрачное окно поверх экрана"
echo "👉 Веб-панель: доступна по адресу http://127.0.0.1:3000 (также работает в Shift+Tab внутри игры)"
echo "----------------------------------------------------------"

exec python3 "$DIR/overlay_window.py"
