#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

export PYTHONPATH="$DIR:$PYTHONPATH"
python3 "$DIR/backend/config_manager.py"

echo "=========================================================="
echo "🛡️  AegisPlus GSI Server (Web & Steam Overlay Mode)"
echo "=========================================================="
echo "👉 Сервер слушает: http://127.0.0.1:3000"
echo "👉 Откройте эту ссылку в браузере или в оверлее Steam (Shift+Tab)"
echo "=========================================================="

exec python3 "$DIR/backend/gsi_server.py"
