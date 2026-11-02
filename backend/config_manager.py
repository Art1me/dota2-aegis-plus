import os
import re
import subprocess
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

    @classmethod
    def setup_hyprland_config(cls) -> bool:
        """
        Ensures Hyprland has keybinds for Super+O pointing to the current toggle_overlay.sh.
        Does NOT inject layerrule (noanim/noblur) which causes syntax errors in Hyprland.
        """
        hypr_conf = Path.home() / ".config" / "hypr" / "hyprland.conf"
        if not hypr_conf.exists():
            return False

        toggle_script = (Path(__file__).parent.parent / "toggle_overlay.sh").resolve()
        block_header = "# --- AegisPlus Overlay ---"
        clean_block = (
            f"\n{block_header}\n"
            f"windowrulev2 = float, title:^(AegisPlus)$\n"
            f"windowrulev2 = pin, title:^(AegisPlus)$\n"
            f"windowrulev2 = noborder, title:^(AegisPlus)$\n"
            f"windowrulev2 = noshadow, title:^(AegisPlus)$\n"
            f"windowrulev2 = size 100% 100%, title:^(AegisPlus)$\n"
            f"windowrulev2 = move 0 0, title:^(AegisPlus)$\n"
            f"bind = SUPER, O, exec, {toggle_script}\n"
            f"bind = SUPER SHIFT, O, exec, {toggle_script} quit\n"
        )

        try:
            content = hypr_conf.read_text(encoding="utf-8", errors="ignore")
            # First remove any stale noanim/noblur lines
            cleaned_lines = [line for line in content.splitlines() if "noanim" not in line and "noblur" not in line]
            content = "\n".join(cleaned_lines)

            # Check if block exists
            if block_header in content:
                pattern = re.compile(
                    r"# --- AegisPlus Overlay ---.*?(?=\n\S|\n# [^\-]|\Z)",
                    re.DOTALL
                )
                updated_content = pattern.sub(clean_block.strip(), content)
                if updated_content.strip() != content.strip():
                    hypr_conf.write_text(updated_content.strip() + "\n", encoding="utf-8")
                    subprocess.run(["hyprctl", "reload"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                with open(hypr_conf, "w", encoding="utf-8") as f:
                    f.write(content.strip() + clean_block)
                subprocess.run(["hyprctl", "reload"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"[AegisPlus Config] Ошибка настройки Hyprland: {e}")
            return False

    @classmethod
    def check_steam_launch_options(cls) -> Tuple[bool, str]:
        """
        Checks localconfig.vdf files in Steam userdata directories to see if
        '-gamestateintegration' is present for Dota 2 (App ID 570).
        """
        found_any = False
        has_gsi_flag = False

        for root in cls.get_all_steam_libraries():
            # Check root/userdata and root/../userdata
            candidates = [root / "userdata", root.parent / "userdata"]
            for userdata_dir in candidates:
                if userdata_dir.exists() and userdata_dir.is_dir():
                    for user_folder in userdata_dir.glob("*"):
                        localconfig = user_folder / "config" / "localconfig.vdf"
                        if localconfig.exists():
                            found_any = True
                            try:
                                text = localconfig.read_text(encoding="utf-8", errors="ignore")
                                if "-gamestateintegration" in text:
                                    has_gsi_flag = True
                                    break
                            except Exception as e:
                                print(f"[AegisPlus Config] Ошибка чтения {localconfig}: {e}")
                if has_gsi_flag:
                    break
            if has_gsi_flag:
                break

        if has_gsi_flag:
            return True, "Параметр '-gamestateintegration' обнаружен в Steam localconfig.vdf"
        elif found_any:
            msg = (
                "\n⚠️  [AegisPlus GSI Warning] ⚠️\n"
                "В параметрах запуска Dota 2 не найден флаг '-gamestateintegration'!\n"
                "Рекомендуется добавить '-gamestateintegration' в свойства игры в Steam:\n"
                "Steam -> Библиотека -> ПКМ по Dota 2 -> Свойства -> Общие -> Параметры запуска:\n"
                "  -gamestateintegration\n"
            )
            return False, msg
        return True, "Steam userdata не найден, проверка пропущена."


if __name__ == "__main__":
    success, msg = ConfigManager.install_gsi_config()
    print(msg)
    gsi_ok, gsi_msg = ConfigManager.check_steam_launch_options()
    if not gsi_ok:
        print(gsi_msg)
    else:
        print(f"[AegisPlus GSI] {gsi_msg}")
    ConfigManager.setup_hyprland_config()
