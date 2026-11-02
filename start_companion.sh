#!/usr/bin/env bash
# ==============================================================================
# AegisPlus Pro - Mobile Companion & Steam HUD Launcher
# Безопасный запуск: НЕ модифицирует системные конфиги Hyprland.
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

export PYTHONPATH="$DIR:$PYTHONPATH"

# 1. Проверка и автоматическая установка GSI конфига в Steam
python3 -c "
from backend.config_manager import ConfigManager
ok, msg = ConfigManager.install_gsi_config()
print(f'[Steam GSI] {msg}')
gsi_ok, gsi_msg = ConfigManager.check_steam_launch_options()
if not gsi_ok:
    print(gsi_msg)
"

# 2. Инструкция по закреплению HUD в игре через оверлей Steam
echo ""
echo "===================================================================="
echo "🎮 ИНСТРУКЦИЯ ДЛЯ ОВЕРЛЕЯ В ИГРЕ (Steam In-Game HUD):"
echo "  1. В Dota 2 нажмите Shift + Tab (оверлей Steam)."
echo "  2. Откройте встроенный браузер Steam."
echo "  3. Перейдите по ссылке: http://127.0.0.1:3000/?mode=hud"
echo "  4. Нажмите иконку 'Закрепить в игре' (Pin to Game) и настройте прозрачность."
echo ""
echo "📱 ДЛЯ ПОДКЛЮЧЕНИЯ С ТЕЛЕФОНА:"
echo "  • В домашнем Wi-Fi: отсканируйте QR-код ниже."
echo "  • Через мобильный 4G/LTE или открытый интернет: запустите в соседнем терминале:"
echo "      ./start_public_tunnel.sh"
echo "===================================================================="
echo ""


# 3. Запуск сервера ядра (доступен локально и по Wi-Fi)
exec python3 "$DIR/backend/gsi_server.py"
