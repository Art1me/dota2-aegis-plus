#!/usr/bin/env bash
# ==============================================================================
# AegisPlus Pro - Открытый облачный хостинг для телефона (HTTPS-туннель)
# Не требует регистрации. Работает через мобильный интернет 4G/5G и любой Wi-Fi.
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

export PYTHONPATH="$DIR:$PYTHONPATH"

echo "===================================================================="
echo "🛡️   AegisPlus Pro: Запуск открытого хостинга для телефона"
echo "===================================================================="

# 1. Проверяем работу сервера
if ! curl -s http://127.0.0.1:3000/api/status >/dev/null 2>&1; then
    echo "⚙️  Сервер AegisPlus не запущен. Запускаю в фоне..."
    nohup python3 "$DIR/backend/gsi_server.py" >/tmp/aegis_companion.log 2>&1 &
    
    # Ждем подтверждения старта
    for i in {1..10}; do
        if curl -s http://127.0.0.1:3000/api/status >/dev/null 2>&1; then
            echo "✅ Сервер AegisPlus успешно запущен и отвечает на 127.0.0.1:3000!"
            break
        fi
        sleep 0.5
    done
fi

if ! curl -s http://127.0.0.1:3000/api/status >/dev/null 2>&1; then
    echo "❌ Ошибка: Сервер не смог запуститься. Лог ошибки:"
    cat /tmp/aegis_companion.log | tail -n 15
    exit 1
fi

echo "🚀 Подключение к бесплатному защищенному HTTPS-шлюзу..."
echo "👉 Через несколько секунд появится ссылка вида: https://xxxx.lhr.life"
echo "👉 Откройте эту ссылку на телефоне в любой сети (даже через мобильный 4G/LTE)!"
echo "===================================================================="
echo ""

# Запуск SSH туннеля через localhost.run на IPv4 127.0.0.1:3000
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R 80:127.0.0.1:3000 nokey@localhost.run

