"""
Main application window with Apple-style HeaderBar, sidebar navigation, and view switching.
Fully localized in English with clean monochrome typography.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk
from pathlib import Path

from storage import StorageManager
from watcher import WindowWatcher
from ui.shark_home_view import SharkHomeView
from ui.home_view import HomeView
from ui.tasks_view import TasksView
from ui.calendar_view import CalendarView, CalendarContainer
from ui.journal_view import JournalView
from ui.watcher_view import WatcherView
from ui.reports_view import ReportsView
from ui.dialogs import NewTaskDialog, NewJournalEntryDialog, SettingsDialog

class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, storage: StorageManager, watcher: WindowWatcher):
        super().__init__(application=app)
        self.storage = storage
        self.watcher = watcher

        self.set_title("Taumer — Tasks & Activity Tracker")
        self.set_default_size(1140, 750)
        self.set_icon_name("taumer")

        self.connect("close-request", self._on_close_request)

        self._build_ui()

    def _build_ui(self):
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root_box)

        # 1. Apple-style HeaderBar with Modern Brand Mark
        header = Adw.HeaderBar()
        
        brand_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        brand_box.set_valign(Gtk.Align.CENTER)
        
        logo_path = Path(__file__).resolve().parent.parent / "taumer.svg"
        if logo_path.exists():
            logo_img = Gtk.Image.new_from_file(str(logo_path))
            logo_img.set_pixel_size(28)
            brand_box.append(logo_img)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        title_box.set_valign(Gtk.Align.CENTER)
        
        main_title = Gtk.Label(label="Taumer")
        main_title.add_css_class("title")
        main_title.set_halign(Gtk.Align.START)
        subtitle = Gtk.Label(label="Task Tracker • Obsidian")
        subtitle.add_css_class("subtitle")
        subtitle.set_halign(Gtk.Align.START)
        
        title_box.append(main_title)
        title_box.append(subtitle)
        brand_box.append(title_box)
        header.set_title_widget(brand_box)

        # Quick action buttons in header
        new_task_btn = Gtk.Button(label="+ Task")
        new_task_btn.add_css_class("btn-primary")
        new_task_btn.connect("clicked", self._open_new_task)
        header.pack_end(new_task_btn)

        log_btn = Gtk.Button(label="Log Activity")
        log_btn.add_css_class("btn-secondary")
        log_btn.connect("clicked", self._open_new_journal)
        header.pack_end(log_btn)

        root_box.append(header)

        # 2. Main layout: Left sidebar + Right view stack
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.set_vexpand(True)
        root_box.append(main_box)

        # Sidebar (macOS style)
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        sidebar.set_size_request(205, -1)
        sidebar.add_css_class("sidebar-box")

        # Views Stack
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.add_css_class("content-view")
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)

        # Initialize Views
        self.shark_home_view = SharkHomeView(
            self.storage,
            on_navigate_cb=self._set_active_view,
            on_journal_updated_cb=self._on_data_updated
        )
        self.panel_view = HomeView(
            self.storage,
            on_navigate_cb=self._set_active_view,
            on_start_timer_cb=self._on_start_task_focus
        )
        self.journal_view = JournalView(self.storage)
        self.tasks_view = TasksView(self.storage, on_start_timer_cb=self._on_start_task_focus)
        self.calendar_view = CalendarContainer(self.storage)
        self.watcher_view = WatcherView(self.watcher, self.storage)
        self.reports_view = ReportsView(self.storage)

        self.stack.add_named(self.shark_home_view, "home")
        self.stack.add_named(self.panel_view, "panel")
        self.stack.add_named(self.tasks_view, "tasks")
        self.stack.add_named(self.calendar_view, "calendar")
        self.stack.add_named(self.journal_view, "journal")
        self.stack.add_named(self.watcher_view, "watcher")
        self.stack.add_named(self.reports_view, "reports")

        # Sidebar navigation buttons (Monochrome, clean symbols)
        self.nav_buttons = {}
        nav_items = [
            ("home", "⌂   Home"),
            ("panel", "◫   Panel"),
            ("tasks", "⊞   Tasks"),
            ("calendar", "◷   Calendar"),
            ("journal", "≡   Activity Journal"),
            ("watcher", "◈   Windows & Tabs"),
            ("reports", "▲   Reports & Analytics"),
        ]

        for name, label in nav_items:
            btn = Gtk.Button(label=label)
            btn.add_css_class("nav-button")
            btn.set_halign(Gtk.Align.FILL)
            btn.connect("clicked", self._on_nav_clicked, name)
            sidebar.append(btn)
            self.nav_buttons[name] = btn

        # Spacer in sidebar
        sidebar.append(Gtk.Box(vexpand=True))

        # Preferences button in sidebar
        self.btn_settings = Gtk.Button(label="⚙   Preferences")
        self.btn_settings.add_css_class("nav-button")
        self.btn_settings.set_halign(Gtk.Align.FILL)
        self.btn_settings.connect("clicked", self._open_settings_dialog)
        sidebar.append(self.btn_settings)

        # Bottom info in sidebar
        bottom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        bottom_box.set_margin_bottom(10)
        bottom_box.set_margin_start(4)
        lbl_vault = Gtk.Label(label="Obsidian Vault")
        lbl_vault.add_css_class("text-title")
        lbl_vault.set_halign(Gtk.Align.START)
        lbl_sub = Gtk.Label(label="Local • Private")
        lbl_sub.add_css_class("text-muted")
        lbl_sub.set_halign(Gtk.Align.START)
        bottom_box.append(lbl_vault)
        bottom_box.append(lbl_sub)
        sidebar.append(bottom_box)

        main_box.append(sidebar)
        main_box.append(self.stack)

        # Apply module visibility configuration
        self._apply_settings()

        # Default active view
        self._set_active_view("home")

    def _apply_settings(self):
        settings = self.storage.get_settings()
        enable_w = settings.get("enable_watcher", True)
        enable_r = settings.get("enable_reports", True)

        if "watcher" in self.nav_buttons:
            self.nav_buttons["watcher"].set_visible(enable_w)
        if "reports" in self.nav_buttons:
            self.nav_buttons["reports"].set_visible(enable_r)

        # If current active view was disabled, fall back to tasks
        curr = self.stack.get_visible_child_name()
        if (curr == "watcher" and not enable_w) or (curr == "reports" and not enable_r):
            self._set_active_view("tasks")

        # Control watcher thread state
        if self.watcher:
            if not enable_w and self.watcher.running:
                self.watcher.stop()
            elif enable_w and not self.watcher.running:
                self.watcher.start()

    def _open_settings_dialog(self, btn):
        dlg = SettingsDialog(self, self.storage, self._on_settings_saved)
        dlg.present()

    def _on_settings_saved(self):
        self._apply_settings()
        self._on_data_updated()

    def _on_nav_clicked(self, btn, view_name):
        self._set_active_view(view_name)

    def _set_active_view(self, view_name: str):
        self.stack.set_visible_child_name(view_name)
        for name, btn in self.nav_buttons.items():
            if name == view_name:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")

        current = self.stack.get_visible_child()
        if hasattr(current, "refresh"):
            current.refresh()

    def _on_start_task_focus(self, task):
        self._set_active_view("home")
        self.shark_home_view.start_focus_with_task(task)

    def _on_close_request(self, window):
        self.save_active_timer()
        return False

    def save_active_timer(self):
        if hasattr(self, "shark_home_view") and self.shark_home_view:
            self.shark_home_view.save_timer_if_active()
        if hasattr(self, "journal_view") and self.journal_view:
            self.journal_view.save_timer_if_active()

    def _open_new_task(self, btn):
        dlg = NewTaskDialog(self, self.storage, self._on_data_updated)
        dlg.present()

    def _open_new_journal(self, btn):
        dlg = NewJournalEntryDialog(self, self.storage, self._on_data_updated)
        dlg.present()

    def _on_data_updated(self):
        current = self.stack.get_visible_child()
        if hasattr(current, "refresh"):
            current.refresh()
        if hasattr(self, "panel_view") and current != self.panel_view:
            self.panel_view.refresh()
        if hasattr(self, "shark_home_view") and current != self.shark_home_view:
            self.shark_home_view.refresh()
