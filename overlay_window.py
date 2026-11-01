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
from backend.gsi_server import start_server, state

APP_ID = "com.aegisplus.dota2.overlay"
SERVER_URL = "http://127.0.0.1:3000"

class OverlayApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.hold()  # Keeps application alive when overlay window is hidden
        self.window = None
        self.webview = None
        self.overlay_open = True
        self.is_locked = False

    def do_activate(self):
        if not self.window:
            self.window = Gtk.ApplicationWindow(application=self)
            self.window.set_title("AegisPlus Dota 2 Overlay")

            # Wayland Layer Shell support (Hyprland / Sway / wlroots)
            layer_shell_active = False
            if HAS_LAYER_SHELL:
                try:
                    if Gtk4LayerShell.is_supported():
                        # Initialize layer shell before modifying toplevel geometry
                        Gtk4LayerShell.init_for_window(self.window)
                        Gtk4LayerShell.set_namespace(self.window, "aegis-overlay")
                        Gtk4LayerShell.set_layer(self.window, Gtk4LayerShell.Layer.OVERLAY)
                        Gtk4LayerShell.set_keyboard_mode(self.window, Gtk4LayerShell.KeyboardMode.ON_DEMAND)
                        Gtk4LayerShell.set_exclusive_zone(self.window, -1)
                        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.TOP, True)
                        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.BOTTOM, True)
                        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.LEFT, True)
                        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.RIGHT, True)

                        layer_shell_active = True
                        print("[AegisPlus] Wayland Layer Shell (OVERLAY) успешно активирован")
                except Exception as e:
                    print(f"[AegisPlus] Layer Shell запущен с предупреждением: {e}")

            if not layer_shell_active:
                self.window.set_default_size(1920, 1080)
                self.window.set_decorated(False)
                print("[AegisPlus] Запуск в режиме независимого прозрачного окна")

            # Setup WebKit UserContentManager to receive click-through toggle from JS
            self.webview = WebKit.WebView()
            settings = self.webview.get_settings()
            settings.set_enable_write_console_messages_to_stdout(True)
            settings.set_enable_developer_extras(True)

            def on_load_changed(wv, event):
                print(f"[AegisPlus WebKit] Load event: {event.value_name}")
            self.webview.connect("load-changed", on_load_changed)

            ucm = self.webview.get_user_content_manager()
            ucm.register_script_message_handler("overlay")
            ucm.connect("script-message-received::overlay", self.on_script_message)
            
            # Transparent background for GTK4 Window and WebKit
            css_provider = Gtk.CssProvider()
            css_provider.load_from_data(b"""
            window, window.background, .background, webkitwebview {
                background: none;
                background-image: none;
                background-color: transparent;
            }
            """)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER
            )

            rgba = Gdk.RGBA()
            rgba.parse("rgba(0,0,0,0)")
            self.webview.set_background_color(rgba)

            # Load local HUD
            self.webview.load_uri(SERVER_URL)
            self.window.set_child(self.webview)

            # Check for backend setting changes periodically
            GLib.timeout_add(60, self.check_backend_sync)

        self.overlay_open = True
        self.apply_overlay_state(True)
        if self.webview:
            js = "if (window.setOverlayOpen) window.setOverlayOpen(true);"
            self.webview.evaluate_javascript(js, -1, None, None, None, None, None)

    def on_script_message(self, ucm, js_result):
        """Receives messages from web frontend."""
        try:
            val = js_result.to_json(0)
            data = json.loads(val)
            action = data.get("action")
            if action == "close_overlay":
                self.overlay_open = False
                state.overlay_open = False
                self.apply_overlay_state(False)
            elif action == "open_overlay":
                self.overlay_open = True
                state.overlay_open = True
                self.apply_overlay_state(True)
            elif action == "set_lock":
                locked = bool(data.get("locked"))
                self.is_locked = locked
                state.clickthrough = locked
                self.apply_lock_state(self.is_locked)
            elif action == "quit_app":
                print("[AegisPlus] Получен сигнал закрытия из интерфейса")
                self.quit_application()
        except Exception as e:
            print(f"[AegisPlus] Ошибка обработки WebKit сообщения: {e}")

    def on_sigusr1(self):
        """Toggles Steam-style overlay on/off on SIGUSR1 signal (global hotkey Super+O)."""
        self.overlay_open = not self.overlay_open
        print(f"[AegisPlus] Горячая клавиша: переключение оверлея = {self.overlay_open}")
        self.apply_overlay_state(self.overlay_open)

        if self.webview:
            js = f"if (window.setOverlayOpen) window.setOverlayOpen({str(self.overlay_open).lower()});"
            self.webview.evaluate_javascript(js, -1, None, None, None, None, None)

        return False

    def on_sigusr2(self):
        """Forces overlay to open on SIGUSR2 signal (desktop launcher / show action)."""
        self.overlay_open = True
        print("[AegisPlus] Команда запуска: принудительное открытие оверлея")
        self.apply_overlay_state(True)

        if self.webview:
            js = "if (window.setOverlayOpen) window.setOverlayOpen(true);"
            self.webview.evaluate_javascript(js, -1, None, None, None, None, None)

        return False

    def quit_application(self):
        print("[AegisPlus] Завершение работы AegisPlus...")
        remove_pid_file()
        os._exit(0)

    def check_backend_sync(self):
        """Syncs overlay window state and input region if backend state changed."""
        if getattr(state, "should_quit", False):
            print("[AegisPlus] Получена команда завершения через бэкенд")
            self.quit_application()
            return GLib.SOURCE_REMOVE

        force_show = getattr(state, "force_show_requested", False)
        if force_show:
            state.force_show_requested = False
            self.overlay_open = True
            state.overlay_open = True
            print("[AegisPlus] Принудительное открытие оверлея по запросу API")
            self.apply_overlay_state(True)
            if self.webview:
                js = "if (window.setOverlayOpen) window.setOverlayOpen(true);"
                self.webview.evaluate_javascript(js, -1, None, None, None, None, None)
        elif state.overlay_open != self.overlay_open:
            self.overlay_open = state.overlay_open
            print(f"[AegisPlus] Синхронизация бэкенда: оверлей = {self.overlay_open}")
            self.apply_overlay_state(self.overlay_open)
            if self.webview:
                js = f"if (window.setOverlayOpen) window.setOverlayOpen({str(self.overlay_open).lower()});"
                self.webview.evaluate_javascript(js, -1, None, None, None, None, None)

        if state.clickthrough != self.is_locked:
            self.is_locked = state.clickthrough
            self.apply_lock_state(self.is_locked)
        return GLib.SOURCE_CONTINUE

    def apply_overlay_state(self, open_state: bool):
        """
        When open_state is True:
        Window is visible and interactive (Steam Overlay mode).
        When open_state is False:
        Window is completely hidden via set_visible(False) (0% screen presence, 100% click-through).
        """
        if not self.window:
            return

        if open_state:
            self.window.set_visible(True)
            self.window.present()
            surface = self.window.get_surface()
            if surface:
                surface.set_input_region(None)
            print("[AegisPlus] Оверлей открыт (режим Steam Overlay): окно активно")
        else:
            self.window.set_visible(False)
            print("[AegisPlus] Оверлей скрыт: окно убрано, клики передаются в Dota 2")

    def apply_lock_state(self, locked: bool):
        if not self.window:
            return
        surface = self.window.get_surface()
        if not surface:
            return
        if locked:
            empty_region = cairo.Region()
            surface.set_input_region(empty_region)
            print("[AegisPlus] Режим «Лок» включен: 100% сквозной экран")
        else:
            surface.set_input_region(None)
            print("[AegisPlus] Режим «Меню» включен: оверлей интерактивен")

def main():
    write_pid_file()
    atexit.register(remove_pid_file)

    def sigterm_handler(sig, frame):
        remove_pid_file()
        os._exit(0)

    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGINT, sigterm_handler)

    # 1. Install / verify GSI config for Dota 2
    success, msg = ConfigManager.install_gsi_config()
    print(f"[AegisPlus GSI] {msg}")

    # 2. Start Background HTTP + SSE Server
    server_thread = threading.Thread(target=start_server, args=(3000,), daemon=True)
    server_thread.start()

    time.sleep(0.5)

    # 3. Launch GTK4 Overlay Application
    app = OverlayApplication()

    def handle_sigusr1(sig, frame):
        GLib.idle_add(app.on_sigusr1)

    def handle_sigusr2(sig, frame):
        GLib.idle_add(app.on_sigusr2)

    signal.signal(signal.SIGUSR1, handle_sigusr1)
    signal.signal(signal.SIGUSR2, handle_sigusr2)

    return app.run(sys.argv)

if __name__ == "__main__":
    sys.exit(main())
