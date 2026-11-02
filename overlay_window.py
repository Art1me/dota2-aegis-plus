#!/usr/bin/env python3
import atexit
import json
import os
import signal
import sys
import threading
import time

PID_FILE = "/tmp/aegisplus.pid"

def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        print(f"[AegisPlus] Ошибка записи PID файла: {e}")

def remove_pid_file():
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception:
        pass

# Ensure libgtk4-layer-shell is preloaded on Wayland so Gtk4LayerShell symbols link properly
if os.environ.get("XDG_SESSION_TYPE") == "wayland" and "libgtk4-layer-shell" not in os.environ.get("LD_PRELOAD", ""):
    for candidate in [
        "/usr/lib64/libgtk4-layer-shell.so",
        "/usr/lib/libgtk4-layer-shell.so",
        "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so"
    ]:
        if os.path.exists(candidate):
            env = os.environ.copy()
            cur_preload = env.get("LD_PRELOAD", "")
            env["LD_PRELOAD"] = f"{candidate}:{cur_preload}" if cur_preload else candidate
            os.execve(sys.executable, [sys.executable] + sys.argv, env)
            break

# Disable WebKit bubblewrap sandbox & clear LD_PRELOAD so child processes (WebKitWebProcess)
# do not inherit LD_PRELOAD and crash in bubblewrap with libGLX_nvidia.so.0!
os.environ["WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"] = "1"
os.environ.pop("LD_PRELOAD", None)

import cairo
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('WebKit', '6.0')

try:
    gi.require_version('Gtk4LayerShell', '1.0')
    from gi.repository import Gtk4LayerShell
    HAS_LAYER_SHELL = True
except Exception:
    HAS_LAYER_SHELL = False

from gi.repository import Gdk, Gio, GLib, Gtk, WebKit

from backend.config_manager import ConfigManager
from backend.gsi_server import set_overlay_app, start_server, state

APP_ID = "com.aegisplus.dota2.overlay"
SERVER_URL = "http://127.0.0.1:3000"


class OverlayApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.hold()  # Keeps application alive across window states
        self.window = None
        self.webview = None
        self.interactive = True  # Starts in Menu mode, toggled by Super+O
        set_overlay_app(self)

    def do_activate(self):
        if not self.window:
            self.window = Gtk.ApplicationWindow(application=self)
            self.window.set_title("AegisPlus Dota 2 Overlay")

            # 1. Wayland Layer Shell support (Hyprland / Sway / wlroots)
            use_layer_shell = (os.environ.get("AEGIS_NO_LAYERSHELL") != "1") and HAS_LAYER_SHELL
            layer_shell_active = False
            if use_layer_shell:
                try:
                    if Gtk4LayerShell.is_supported():
                        # Initialize layer shell BEFORE window is shown / mapped
                        Gtk4LayerShell.init_for_window(self.window)
                        Gtk4LayerShell.set_namespace(self.window, "aegis-overlay")
                        Gtk4LayerShell.set_layer(self.window, Gtk4LayerShell.Layer.OVERLAY)
                        Gtk4LayerShell.set_exclusive_zone(self.window, -1)  # CRITICAL: -1
                        Gtk4LayerShell.set_keyboard_mode(self.window, Gtk4LayerShell.KeyboardMode.ON_DEMAND)
                        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.TOP, True)
                        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.BOTTOM, True)
                        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.LEFT, True)
                        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.RIGHT, True)

                        display = Gdk.Display.get_default()
                        if display:
                            monitors = display.get_monitors()
                            if monitors.get_n_items() > 0:
                                target_mon = monitors.get_item(monitors.get_n_items() - 1)
                                Gtk4LayerShell.set_monitor(self.window, target_mon)

                        layer_shell_active = True
                        print("[AegisPlus] Wayland Layer Shell (OVERLAY) успешно активирован")
                except Exception as e:
                    print(f"[AegisPlus] Layer Shell запущен с предупреждением: {e}")

            self.window.set_default_size(1920, 1080)
            self.window.set_opacity(1.0)
            if not layer_shell_active:
                self.window.set_decorated(False)
                self.window.set_title("AegisPlus")
                print("[AegisPlus] Запуск в режиме независимого прозрачного плавающего окна")

            # 2. Transparent background for GTK4 Window (preserving WebKit native render buffer)
            css_provider = Gtk.CssProvider()
            css_provider.load_from_data(b"""
            window.background {
                background-color: transparent;
            }
            """)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER
            )

            self.webview = WebKit.WebView()
            self.webview.set_hexpand(True)
            self.webview.set_vexpand(True)
            self.webview.set_size_request(1920, 1080)
            settings = self.webview.get_settings()
            settings.set_enable_write_console_messages_to_stdout(True)
            settings.set_enable_developer_extras(True)

            rgba = Gdk.RGBA()
            rgba.parse("rgba(0, 0, 0, 0)")
            self.webview.set_background_color(rgba)

            ucm = self.webview.get_user_content_manager()
            ucm.register_script_message_handler("overlay")
            ucm.connect("script-message-received::overlay", self.on_script_message)

            self.webview.load_uri(SERVER_URL)
            self.window.set_child(self.webview)

            # Ensure input region is configured after surface is mapped
            def on_map(widget):
                GLib.idle_add(lambda: self.set_interactive_mode(True))

            self.window.connect("map", on_map)

            # Register Unix signal handlers via GLib exclusively
            self.setup_glib_signals()

        self.window.set_visible(True)
        self.window.present()

    def set_interactive_mode(self, interactive: bool):
        """
        Switches between 2 UI modes:
        - interactive == False: HUD mode (0% input blocking, all clicks pass to Dota 2).
        - interactive == True:  Menu mode (full input enabled, modal/controls interactive).
        """
        self.interactive = interactive
        if not self.window:
            return

        surface = self.window.get_surface()
        if surface is None:
            return

        if not self.interactive:
            # HUD mode: empty input region -> clicks go straight into Dota 2
            empty_region = cairo.Region(cairo.RectangleInt(0, 0, 0, 0))
            surface.set_input_region(empty_region)

            if HAS_LAYER_SHELL and Gtk4LayerShell.is_supported():
                try:
                    Gtk4LayerShell.set_keyboard_mode(self.window, Gtk4LayerShell.KeyboardMode.NONE)
                except Exception:
                    pass

            print("[AegisPlus] Режим HUD: сквозной ввод в Dota 2 (клики проходят сквозь окно)")
        else:
            # Menu mode: full window input region -> user can click buttons & select options
            surface.set_input_region(None)

            if HAS_LAYER_SHELL and Gtk4LayerShell.is_supported():
                try:
                    Gtk4LayerShell.set_keyboard_mode(self.window, Gtk4LayerShell.KeyboardMode.ON_DEMAND)
                except Exception:
                    pass

            print("[AegisPlus] Режим Меню: оверлей интерактивен (управление панелью)")

        # Notify WebKit frontend to toggle CSS classes (.mode-hud vs .mode-menu)
        if self.webview:
            js = f"if (window.setUiMode) window.setUiMode({str(interactive).lower()});"
            try:
                self.webview.evaluate_javascript(js, -1, None, None, None, None, None)
            except TypeError:
                try:
                    self.webview.evaluate_javascript(js, -1)
                except Exception as e:
                    print(f"[AegisPlus] Ошибка JavaScript evaluation: {e}")
            except Exception as e:
                print(f"[AegisPlus] Ошибка JavaScript evaluation: {e}")

    def toggle_interactive_mode(self):
        """Toggles between Menu and HUD modes."""
        self.set_interactive_mode(not self.interactive)

    def setup_glib_signals(self):
        """Registers Unix signals using GLib.unix_signal_add instead of standard signal.signal."""
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.handle_sigint_term)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.handle_sigint_term)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.handle_sigusr1)

    def handle_sigusr1(self, *args):
        """Toggles interactive mode (Menu <-> HUD) on SIGUSR1 from Super+O."""
        print(f"[AegisPlus] SIGUSR1 получен: переключение режима Меню/HUD")
        self.toggle_interactive_mode()
        return GLib.SOURCE_CONTINUE

    def handle_sigint_term(self, *args):
        """Handles clean termination on SIGINT / SIGTERM."""
        print("[AegisPlus] Получен сигнал завершения...")
        self.quit_application()
        return GLib.SOURCE_REMOVE

    def on_script_message(self, ucm, js_result):
        """Receives messages from WebKit JavaScript."""
        try:
            val = js_result.to_json(0)
            data = json.loads(val)
            action = data.get("action")
            if action == "close_menu":
                self.set_interactive_mode(False)
            elif action == "open_menu":
                self.set_interactive_mode(True)
            elif action == "toggle_menu":
                self.set_interactive_mode(not self.interactive)
            elif action == "quit_app":
                print("[AegisPlus] Получен запрос на выход из интерфейса")
                self.quit_application()
        except Exception as e:
            print(f"[AegisPlus] Ошибка обработки WebKit сообщения: {e}")

    def quit_application(self):
        print("[AegisPlus] Завершение работы AegisPlus...")
        remove_pid_file()
        try:
            self.quit()
        except Exception:
            pass
        os._exit(0)


def main():
    write_pid_file()
    atexit.register(remove_pid_file)

    # 1. Install / verify GSI config for Dota 2 in all candidate locations
    success, msg = ConfigManager.install_gsi_config()
    print(f"[AegisPlus GSI] {msg}")
    gsi_ok, gsi_msg = ConfigManager.check_steam_launch_options()
    if not gsi_ok:
        print(gsi_msg)
    else:
        print(f"[AegisPlus GSI] {gsi_msg}")
    ConfigManager.setup_hyprland_config()

    # 2. Start Background HTTP + SSE Server
    server_thread = threading.Thread(target=start_server, args=(3000,), daemon=True)
    server_thread.start()

    time.sleep(0.3)

    # 3. Launch GTK4 Overlay Application
    app = OverlayApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
