import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

GSI_CONFIG_CONTENT = """"Dota 2 AegisPlus Integration"
{
    "uri"           "http://127.0.0.1:3000/"
    "timeout"       "5.0"
    "buffer"        "0.1"
    "throttle"      "0.1"
    "heartbeat"     "5.0"
    "data"
    {
        "provider"      "1"
        "map"           "1"
        "player"        "1"
        "hero"          "1"
        "abilities"     "1"
        "items"         "1"
        "buildings"     "1"
        "draft"         "1"
    }
}
"""

STANDARD_STEAM_ROOTS = [
    Path.home() / ".local/share/Steam",
    Path.home() / ".steam/steam",
    Path.home() / ".steam/root",
    Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    Path.home() / ".var/app/com.valvesoftware.Steam/.steam/steam",
]


class ConfigManager:
    @staticmethod
    def _parse_library_folders(vdf_path: Path) -> List[Path]:
        """Parses libraryfolders.vdf to find all Steam library paths."""
        libraries: List[Path] = []
        if not vdf_path.exists():
            return libraries

        try:
            content = vdf_path.read_text(encoding="utf-8", errors="ignore")
            matches = re.findall(r'"path"\s+"([^"]+)"', content, re.IGNORECASE)
            for m in matches:
                p = Path(m)
                if p.exists() and p.is_dir():
                    libraries.append(p)
        except Exception as e:
            print(f"[AegisPlus Config] Ошибка чтения {vdf_path}: {e}")

        return libraries

    @classmethod
    def get_all_steam_libraries(cls) -> List[Path]:
        """Discovers all Steam library folders across standard locations and mounted drives."""
        seen = set()
        libraries: List[Path] = []

        for root in STANDARD_STEAM_ROOTS:
            if root.exists() and root.is_dir():
                resolved = root.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    libraries.append(root)

                # Check libraryfolders.vdf in this Steam root
                vdf = root / "steamapps" / "libraryfolders.vdf"
                for extra_lib in cls._parse_library_folders(vdf):
                    resolved_extra = extra_lib.resolve()
                    if resolved_extra not in seen:
                        seen.add(resolved_extra)
                        libraries.append(extra_lib)

        return libraries

    @classmethod
    def find_dota_cfg_dirs(cls) -> List[Path]:
        """
        Locates the dota 2 cfg directories across all Steam libraries.
        Returns list of existing cfg directories.
        """
        cfg_dirs: List[Path] = []
        libraries = cls.get_all_steam_libraries()

        for lib in libraries:
            candidate = lib / "steamapps" / "common" / "dota 2 beta" / "game" / "dota" / "cfg"
            if candidate.exists() and candidate.is_dir():
                if candidate not in cfg_dirs:
                    cfg_dirs.append(candidate)

        return cfg_dirs

    @classmethod
    def install_gsi_config(cls) -> Tuple[bool, str]:
        """
        Installs the GSI configuration file into:
        1. dota 2 beta/game/dota/cfg/
        2. dota 2 beta/game/dota/cfg/gamestate_integration/
        Ensures both locations have gamestate_integration_aegis_plus.cfg.
        """
        cfg_dirs = cls.find_dota_cfg_dirs()
        if not cfg_dirs:
            return False, "Папка cfg Dota 2 не найдена. Убедитесь, что Dota 2 установлена."

        installed_paths = []
        for cfg_dir in cfg_dirs:
            # 1. Main cfg folder
            main_target = cfg_dir / "gamestate_integration_aegis_plus.cfg"
            try:
                main_target.write_text(GSI_CONFIG_CONTENT, encoding="utf-8")
                installed_paths.append(str(main_target))
            except Exception as e:
                print(f"[AegisPlus Config] Не удалось записать в {main_target}: {e}")

            # 2. Subfolder dota/cfg/gamestate_integration/
            gsi_subdir = cfg_dir / "gamestate_integration"
            try:
                os.makedirs(gsi_subdir, exist_ok=True)
                sub_target = gsi_subdir / "gamestate_integration_aegis_plus.cfg"
                sub_target.write_text(GSI_CONFIG_CONTENT, encoding="utf-8")
                installed_paths.append(str(sub_target))
            except Exception as e:
                print(f"[AegisPlus Config] Не удалось записать в {gsi_subdir}: {e}")

        if installed_paths:
            return True, f"Конфигурация GSI успешно установлена в:\n" + "\n".join(f"  • {p}" for p in installed_paths)
        return False, "Не удалось записать файл конфигурации GSI ни в одну папку."

    @classmethod
    def is_gsi_installed(cls) -> bool:
        cfg_dirs = cls.find_dota_cfg_dirs()
        for cfg_dir in cfg_dirs:
            if (cfg_dir / "gamestate_integration_aegis_plus.cfg").exists():
                return True
            if (cfg_dir / "gamestate_integration" / "gamestate_integration_aegis_plus.cfg").exists():
                return True
        return False


if __name__ == "__main__":
    success, msg = ConfigManager.install_gsi_config()
    print(msg)
