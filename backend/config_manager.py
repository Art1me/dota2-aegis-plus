import os
from pathlib import Path

GSI_CONFIG_CONTENT = """"Dota 2 AegisPlus Integration"
{
    "uri"           "http://127.0.0.1:3000/gsi"
    "timeout"       "5.0"
    "buffer"        "0.1"
    "throttle"      "0.1"
    "heartbeat"     "30.0"
    "data"
    {
        "buildings"     "1"
        "provider"      "1"
        "map"           "1"
        "player"        "1"
        "hero"          "1"
        "abilities"     "1"
        "items"         "1"
        "draft"         "1"
        "wearables"     "1"
    }
}
"""

CANDIDATE_PATHS = [
    Path.home() / ".local/share/Steam/steamapps/common/dota 2 beta/game/dota/cfg",
    Path.home() / ".steam/steam/steamapps/common/dota 2 beta/game/dota/cfg",
    Path.home() / ".steam/root/steamapps/common/dota 2 beta/game/dota/cfg",
    Path.home() / "Library/Application Support/Steam/steamapps/common/dota 2 beta/game/dota/cfg",
    Path("C:/Program Files (x86)/Steam/steamapps/common/dota 2 beta/game/dota/cfg")
]

class ConfigManager:
    @staticmethod
    def find_dota_cfg_dir() -> Path | None:
        for candidate in CANDIDATE_PATHS:
            if candidate.exists() and candidate.is_dir():
                return candidate
        return None

    @classmethod
    def install_gsi_config(cls) -> tuple[bool, str]:
        cfg_dir = cls.find_dota_cfg_dir()
        if not cfg_dir:
            return False, "Папка cfg Dota 2 не найдена. Убедитесь, что игра установлена."

        target_file = cfg_dir / "gamestate_integration_aegis_plus.cfg"
        try:
            target_file.write_text(GSI_CONFIG_CONTENT, encoding="utf-8")
            return True, f"Конфигурация GSI успешно установлена в {target_file}"
        except Exception as e:
            return False, f"Ошибка при записи файла конфигурации: {e}"

    @classmethod
    def is_gsi_installed(cls) -> bool:
        cfg_dir = cls.find_dota_cfg_dir()
        if not cfg_dir:
            return False
        return (cfg_dir / "gamestate_integration_aegis_plus.cfg").exists()

if __name__ == "__main__":
    success, msg = ConfigManager.install_gsi_config()
    print(msg)
