#!/usr/bin/env python3
import json
import os
import signal
import sys
import threading
import time

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
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None
        self.webview = None
        self.is_locked = False

    def do_activate(self):
        if not self.window:
            self.window = Gtk.ApplicationWindow(application=self)
            self.window.set_title("AegisPlus Dota 2 Overlay")
            self.window.set_default_size(1920, 1080)
            self.window.set_decorated(False)

            # Apply CSS for transparent background
            css_provider = Gtk.CssProvider()
            css_provider.load_from_data(b"""
                window, .background {
                    background-color: transparent !important;
                    background: transparent !important;
                }
            """)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

            # Wayland Layer Shell support (Hyprland / Sway / wlroots)
            layer_shell_active = False
            if HAS_LAYER_SHELL:
                try:
                    if Gtk4LayerShell.is_supported():
                        Gtk4LayerShell.init_for_window(self.window)
                        Gtk4LayerShell.set_layer(self.window, Gtk4LayerShell.Layer.OVERLAY)
                        Gtk4LayerShell.set_keyboard_mode(self.window, Gtk4LayerShell.KeyboardMode.NONE)
                        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.TOP, True)
                        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.BOTTOM, True)
                        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.LEFT, True)
                        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.RIGHT, True)
                        layer_shell_active = True
                        print("[AegisPlus] Wayland Layer Shell (OVERLAY) успешно активирован")
                except Exception as e:
                    print(f"[AegisPlus] Layer Shell запущен с предупреждением: {e}")

            if not layer_shell_active:
                print("[AegisPlus] Запуск в режиме независимого прозрачного окна")

            # Setup WebKit UserContentManager to receive click-through toggle from JS
            ucm = WebKit.UserContentManager()
            ucm.register_script_message_handler("overlay")
            ucm.connect("script-message-received::overlay", self.on_script_message)

            self.webview = WebKit.WebView.new_with_user_content_manager(ucm)
            
            # Transparent background
            rgba = Gdk.RGBA()
            rgba.parse("rgba(0,0,0,0)")
            self.webview.set_background_color(rgba)

            # Load local HUD
            self.webview.load_uri(SERVER_URL)
            self.window.set_child(self.webview)

            # Listen for SIGUSR1 to toggle Lock/Menu mode via system hotkey
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.on_sigusr1)

            # Check for backend setting changes periodically
            GLib.timeout_add(500, self.check_backend_sync)

        self.window.present()

    def on_script_message(self, ucm, js_result):
        """Receives lock/unlock message from web frontend."""
        try:
            val = js_result.to_json(0)
            data = json.loads(val)
            if data.get("action") == "set_lock":
                locked = bool(data.get("locked"))
                self.is_locked = locked
                self.apply_lock_state(self.is_locked)
        except Exception as e:
            print(f"[AegisPlus] Ошибка обработки WebKit сообщения: {e}")

    def on_sigusr1(self):
        """Toggles Lock/Menu click-through on SIGUSR1 signal (system hotkey)."""
        self.is_locked = not self.is_locked
        print(f"[AegisPlus] Получен сигнал SIGUSR1: переключение режима Лок = {self.is_locked}")
        self.apply_lock_state(self.is_locked)

        if self.webview:
            js = f"if (window.setLockState) window.setLockState({str(self.is_locked).lower()});"
            self.webview.evaluate_javascript(js, -1, None, None, None, None, None)

        return GLib.SOURCE_CONTINUE

    def check_backend_sync(self):
        """Syncs overlay window input region if backend state changed."""
        if state.clickthrough != self.is_locked:
            self.is_locked = state.clickthrough
            self.apply_lock_state(self.is_locked)
        return GLib.SOURCE_CONTINUE

    def apply_lock_state(self, locked: bool):
        """
        In Locked mode:
        Sets input region to only the 'Меню / Лок' button coordinates (cairo.Region),
        passing all other clicks directly through to Dota 2!
        In Unlocked mode:
        Sets input region to None (full window clickable).
        """
        if not self.window:
            return

        surface = self.window.get_surface()
        if not surface:
            return

        if locked:
            # Strictly safe coordinates under Dota 2 settings gear (x=8, y=52, w=110, h=32)
            # Avoids overlapping Radiant hero portraits or any in-game HUD elements
            rect = cairo.RectangleInt(8, 52, 110, 32)
            region = cairo.Region(rect)
            surface.set_input_region(region)
            print("[AegisPlus] Режим «Лок» включен: 100% сквозной экран, кликабелен только бейдж (8, 52, 110, 32)")
        else:
            surface.set_input_region(None)
            print("[AegisPlus] Режим «Меню» включен: оверлей интерактивен")

def main():
    # 1. Install / verify GSI config for Dota 2
    success, msg = ConfigManager.install_gsi_config()
    print(f"[AegisPlus GSI] {msg}")

    # 2. Start Background HTTP + SSE Server
    server_thread = threading.Thread(target=start_server, args=(3000,), daemon=True)
    server_thread.start()

    time.sleep(0.5)

    # 3. Launch GTK4 Overlay Application
    app = OverlayApplication()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    return app.run(sys.argv)

if __name__ == "__main__":
    sys.exit(main())
