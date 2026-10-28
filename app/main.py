#!/usr/bin/env python3
"""
Taumer — Native Linux Mint Task & Focus Tracker with Obsidian Integration.
"""

import sys
import os
from pathlib import Path

# Add app directory to sys.path
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, Adw, Gio

from storage import StorageManager
from watcher import WindowWatcher
from ui.main_window import MainWindow

class TrackerApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.taumer",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )
        self.storage = None
        self.watcher = None
        self.window = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        # Apple-style modern monochrome Light Mode
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)

        # Register app icon search path
        display = Gdk.Display.get_default()
        if display:
            theme = Gtk.IconTheme.get_for_display(display)
            theme.add_search_path(str(APP_DIR))

        self._load_css()

        # Initialize storage and watcher
        self.storage = StorageManager()
        self.watcher = WindowWatcher()
        self.watcher.start()

        # Graceful shutdown handler for external termination signals
        import signal
        def sig_handler(signum, frame):
            if self.window and hasattr(self.window, "save_active_timer"):
                self.window.save_active_timer()
            sys.exit(0)

        try:
            signal.signal(signal.SIGINT, sig_handler)
            signal.signal(signal.SIGTERM, sig_handler)
        except Exception:
            pass

    def _load_css(self):
        css_file = APP_DIR / "style.css"
        if css_file.exists():
            provider = Gtk.CssProvider()
            provider.load_from_path(str(css_file))
            display = Gdk.Display.get_default()
            if display:
                Gtk.StyleContext.add_provider_for_display(
                    display,
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )

    def do_activate(self):
        if not self.window:
            self.window = MainWindow(self, self.storage, self.watcher)
        self.window.present()

    def do_shutdown(self):
        if self.window and hasattr(self.window, "save_active_timer"):
            self.window.save_active_timer()
        if self.watcher:
            self.watcher.stop()
        Adw.Application.do_shutdown(self)


def main():
    app = TrackerApplication()
    return app.run(sys.argv)

if __name__ == "__main__":
    sys.exit(main())
