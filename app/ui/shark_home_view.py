"""
SharkHomeView: Super-minimalist focus space with live ASCII Sharks ocean animation,
frosted glass translucent input capsule, live stopwatch, and instant Obsidian logging.
Includes native GTK fallback for environments where WebKit is not available (e.g. Windows).
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
import gi
gi.require_version('Gtk', '4.0')
try:
    gi.require_version('WebKit', '6.0')
    from gi.repository import WebKit
    HAS_WEBKIT = True
except Exception:
    HAS_WEBKIT = False
from gi.repository import Gtk, GLib

from models import JournalEntry, Task
from config import open_file_or_url


class SharkHomeView(Gtk.Box):
    def __init__(self, storage, on_navigate_cb=None, on_journal_updated_cb=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.storage = storage
        self.on_navigate_cb = on_navigate_cb
        self.on_journal_updated_cb = on_journal_updated_cb

        # State tracking for primary and parallel focus slots
        self.slots = {
            0: {
                "active": True,
                "running": False,
                "seconds": 0,
                "title": "",
                "project": "General",
                "task_id": None,
                "start_dt": None,
            },
            1: {
                "active": False,
                "running": False,
                "seconds": 0,
                "title": "",
                "project": "General",
                "task_id": None,
                "start_dt": None,
            }
        }
        self._page_loaded = False

        self._build_ui()

    @property
    def timer_running(self) -> bool:
        return self.slots[0]["running"] or (self.slots[1]["active"] and self.slots[1]["running"])

    @property
    def timer_seconds(self) -> int:
        return self.slots[0]["seconds"]

    @property
    def current_title(self) -> str:
        return self.slots[0]["title"]

    @property
    def current_project(self) -> str:
        return self.slots[0]["project"]

    @property
    def current_task_id(self):
        return self.slots[0]["task_id"]

    def _build_ui(self):
        self.set_hexpand(True)
        self.set_vexpand(True)

        if HAS_WEBKIT:
            self._build_webkit_ui()
        else:
            self._build_native_gtk_ui()

    def _build_webkit_ui(self):
        # WebKit WebView
        self.webview = WebKit.WebView()
        self.webview.set_hexpand(True)
        self.webview.set_vexpand(True)

        # Enable modern web features
        settings = self.webview.get_settings()
        settings.set_enable_webgl(True)
        settings.set_enable_developer_extras(False)
        settings.set_allow_file_access_from_file_urls(True)
        settings.set_allow_universal_access_from_file_urls(True)

        # Connect Script Message Handler
        ucm = self.webview.get_user_content_manager()
        ucm.register_script_message_handler("taumer")
        ucm.connect("script-message-received::taumer", self._on_script_message)
        ucm.register_script_message_handler("trazos")
        ucm.connect("script-message-received::trazos", self._on_script_message)

        # Connect load event
        self.webview.connect("load-changed", self._on_load_changed)

        # Load HTML with configured background theme
        assets_dir = Path(__file__).resolve().parent / "shark_assets"
        html_file = assets_dir / "index.html"
        bg_theme = self.storage.get_settings().get("background_theme", "sharks")
        self.webview.load_uri(f"file://{html_file.resolve()}?theme={bg_theme}")

        self.append(self.webview)

    def _build_native_gtk_ui(self):
        self._page_loaded = True
        self._gtk_pending_tasks = []

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_hexpand(True)
        outer.set_vexpand(True)
        outer.set_valign(Gtk.Align.CENTER)
        outer.set_halign(Gtk.Align.CENTER)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        card.set_size_request(500, -1)
        card.add_css_class("card")
        card.set_margin_top(32)
        card.set_margin_bottom(32)
        card.set_margin_start(32)
        card.set_margin_end(32)

        # Header tag
        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tag = Gtk.Label(label="FOCUS SPACE")
        tag.add_css_class("badge")
        top_box.append(tag)
        card.append(top_box)

        # Large Elapsed Timer Display
        self.gtk_timer_lbl = Gtk.Label(label="00:00:00")
        self.gtk_timer_lbl.add_css_class("title")
        self.gtk_timer_lbl.set_margin_top(8)
        self.gtk_timer_lbl.set_margin_bottom(8)
        card.append(self.gtk_timer_lbl)

        # Focus concept or task title input
        self.gtk_title_entry = Gtk.Entry()
        self.gtk_title_entry.set_placeholder_text("What are you focusing on?")
        self.gtk_title_entry.connect("changed", self._on_gtk_title_changed)
        card.append(self.gtk_title_entry)

        # Selectors row
        sel_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        self.gtk_proj_model = Gtk.StringList()
        self.gtk_proj_dropdown = Gtk.DropDown.new(self.gtk_proj_model, None)
        self.gtk_proj_dropdown.set_hexpand(True)
        self.gtk_proj_dropdown.connect("notify::selected", self._on_gtk_proj_changed)
        sel_row.append(self.gtk_proj_dropdown)

        self.gtk_task_model = Gtk.StringList()
        self.gtk_task_dropdown = Gtk.DropDown.new(self.gtk_task_model, None)
        self.gtk_task_dropdown.set_hexpand(True)
        self.gtk_task_dropdown.connect("notify::selected", self._on_gtk_task_dropdown_changed)
        sel_row.append(self.gtk_task_dropdown)

        card.append(sel_row)

        # Buttons row
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_row.set_halign(Gtk.Align.CENTER)

        self.gtk_btn_start = Gtk.Button(label="▶  Start Focus")
        self.gtk_btn_start.add_css_class("btn-primary")
        self.gtk_btn_start.connect("clicked", self._on_gtk_toggle_timer)
        btn_row.append(self.gtk_btn_start)

        self.gtk_btn_save = Gtk.Button(label="✓  Save Session")
        self.gtk_btn_save.add_css_class("btn-secondary")
        self.gtk_btn_save.connect("clicked", self._on_gtk_save_clicked)
        btn_row.append(self.gtk_btn_save)

        self.gtk_btn_reset = Gtk.Button(label="↺  Reset")
        self.gtk_btn_reset.add_css_class("nav-button")
        self.gtk_btn_reset.connect("clicked", self._on_gtk_reset_clicked)
        btn_row.append(self.gtk_btn_reset)

        card.append(btn_row)
        outer.append(card)
        scrolled.set_child(outer)
        self.append(scrolled)

        # Start GTK heartbeat
        GLib.timeout_add_seconds(1, self._on_gtk_heartbeat)

    def _on_gtk_heartbeat(self):
        s = self.slots[0]
        if s["running"]:
            s["seconds"] += 1
            secs = s["seconds"]
            hrs = secs // 3600
            mins = (secs % 3600) // 60
            scs = secs % 60
            self.gtk_timer_lbl.set_label(f"{hrs:02d}:{mins:02d}:{scs:02d}")
        return True

    def _on_gtk_title_changed(self, entry):
        self.slots[0]["title"] = entry.get_text().strip()

    def _on_gtk_proj_changed(self, dropdown, param):
        idx = dropdown.get_selected()
        if idx >= 0 and idx < self.gtk_proj_model.get_n_items():
            self.slots[0]["project"] = self.gtk_proj_model.get_string(idx)

    def _on_gtk_task_dropdown_changed(self, dropdown, param):
        idx = dropdown.get_selected()
        if idx > 0 and (idx - 1) < len(self._gtk_pending_tasks):
            task = self._gtk_pending_tasks[idx - 1]
            self.gtk_title_entry.set_text(task.title)
            self.slots[0]["title"] = task.title
            self.slots[0]["task_id"] = task.id
            self.slots[0]["project"] = task.project
            # Set project dropdown
            for p_idx in range(self.gtk_proj_model.get_n_items()):
                if self.gtk_proj_model.get_string(p_idx) == task.project:
                    self.gtk_proj_dropdown.set_selected(p_idx)
                    break

    def _on_gtk_toggle_timer(self, btn):
        s = self.slots[0]
        s["running"] = not s["running"]
        if s["running"]:
            if not s["start_dt"]:
                s["start_dt"] = datetime.now() - timedelta(seconds=s["seconds"])
            if not s["title"]:
                s["title"] = self.gtk_title_entry.get_text().strip() or "Focus Session"
            self.gtk_btn_start.set_label("⏸  Pause")
            self.gtk_btn_start.remove_css_class("btn-primary")
            self.gtk_btn_start.add_css_class("btn-secondary")
        else:
            self.gtk_btn_start.set_label("▶  Resume")
            self.gtk_btn_start.remove_css_class("btn-secondary")
            self.gtk_btn_start.add_css_class("btn-primary")

    def _on_gtk_save_clicked(self, btn):
        s = self.slots[0]
        secs = s["seconds"]
        title = self.gtk_title_entry.get_text().strip() or s["title"] or "Focus Session"
        proj = s.get("project") or "General"
        task_id = s.get("task_id")
        self._save_session_entry(title, proj, secs, task_id)
        self._on_gtk_reset_clicked(None)

    def _on_gtk_reset_clicked(self, btn):
        s = self.slots[0]
        s["running"] = False
        s["seconds"] = 0
        s["start_dt"] = None
        s["task_id"] = None
        self.gtk_timer_lbl.set_label("00:00:00")
        self.gtk_btn_start.set_label("▶  Start Focus")
        self.gtk_btn_start.remove_css_class("btn-secondary")
        self.gtk_btn_start.add_css_class("btn-primary")

    def _on_load_changed(self, webview, event):
        if HAS_WEBKIT and event == WebKit.LoadEvent.FINISHED:
            self._page_loaded = True
            self.refresh()

    def _eval_js(self, script: str):
        if not HAS_WEBKIT or not self._page_loaded:
            return
        try:
            self.webview.evaluate_javascript(script, -1, None, None, None, None, None)
        except Exception as e:
            print(f"[SharkHomeView] JS eval error: {e}")

    def set_background_theme(self, theme: str):
        if not HAS_WEBKIT or not self._page_loaded:
            return
        self._eval_js(f"if (window.setBackgroundTheme) window.setBackgroundTheme({json.dumps(theme)});")

    def refresh(self):
        """Pushes latest projects, pending tasks, and background theme into the view."""
        if not self._page_loaded:
            return

        if not HAS_WEBKIT:
            # Refresh project list in GTK dropdown
            projects = self.storage.get_projects()
            p_names = [p.name for p in projects]
            if "General" not in p_names:
                p_names.insert(0, "General")

            while self.gtk_proj_model.get_n_items() > 0:
                self.gtk_proj_model.remove(0)
            for p in p_names:
                self.gtk_proj_model.append(p)

            # Refresh pending tasks in GTK dropdown
            tasks = self.storage.get_tasks()
            pending = [t for t in tasks if t.status != "done" and getattr(t, "item_type", "task") != "event"]
            self._gtk_pending_tasks = pending
            while self.gtk_task_model.get_n_items() > 0:
                self.gtk_task_model.remove(0)
            self.gtk_task_model.append("— Pick a pending task —")
            for t in pending:
                self.gtk_task_model.append(f"{t.title} ({t.project})")
            return

        # 0. Background theme
        bg_theme = self.storage.get_settings().get("background_theme", "sharks")
        self.set_background_theme(bg_theme)

        # 1. Projects
        projects = self.storage.get_projects()
        p_names = [p.name for p in projects]
        if "General" not in p_names:
            p_names.insert(0, "General")
        proj_json = json.dumps(p_names)
        self._eval_js(f"window.setProjects({proj_json});")

        # 2. Pending tasks (undone tasks for quick selection, events excluded)
        tasks = self.storage.get_tasks()
        pending = [t for t in tasks if t.status != "done" and getattr(t, "item_type", "task") != "event"]
        tasks_data = [{"id": t.id, "title": t.title, "project": t.project} for t in pending]
        tasks_json = json.dumps(tasks_data)
        self._eval_js(f"window.setPendingTasks({tasks_json});")

    def _on_script_message(self, manager, js_result):
        try:
            raw = js_result.to_string()
            msg = json.loads(raw)
            action = msg.get("action")
            slot_idx = msg.get("slot", 0)

            if action == "start_timer":
                s = self.slots.get(slot_idx, self.slots[0])
                s["active"] = True
                s["running"] = True
                s["seconds"] = msg.get("seconds", 0)
                s["title"] = msg.get("title", s["title"])
                s["project"] = msg.get("project", s["project"]) or "General"
                s["task_id"] = msg.get("taskId", s["task_id"])
                s["start_dt"] = datetime.now() - timedelta(seconds=s["seconds"])

            elif action in ("pause_timer", "stop_timer"):
                s = self.slots.get(slot_idx, self.slots[0])
                s["running"] = False
                s["seconds"] = msg.get("seconds", s["seconds"])

            elif action == "tick":
                s = self.slots.get(slot_idx, self.slots[0])
                s["seconds"] = msg.get("seconds", s["seconds"])
                s["title"] = msg.get("title", s["title"])
                s["project"] = msg.get("project", s["project"]) or "General"
                s["task_id"] = msg.get("taskId", s["task_id"])

            elif action == "input_changed":
                s = self.slots.get(slot_idx, self.slots[0])
                s["title"] = msg.get("title", "")
                if "project" in msg:
                    s["project"] = msg.get("project")
                if "taskId" in msg:
                    s["task_id"] = msg.get("taskId")

            elif action == "project_changed":
                s = self.slots.get(slot_idx, self.slots[0])
                s["project"] = msg.get("project", "General")

            elif action == "add_parallel_slot":
                s1 = self.slots[1]
                s1["active"] = True
                s1["running"] = False
                s1["seconds"] = 0
                s1["title"] = ""
                s1["project"] = "General"
                s1["task_id"] = None
                s1["start_dt"] = None

            elif action == "reset_timer":
                s = self.slots.get(slot_idx, self.slots[0])
                s["running"] = False
                s["seconds"] = 0
                s["task_id"] = None
                s["start_dt"] = None
                s["title"] = ""
                s["project"] = "General"

            elif action == "delete_slot":
                target_slot = msg.get("slot", 1)
                s = self.slots.get(target_slot, self.slots[1])
                s["active"] = False
                s["running"] = False
                s["seconds"] = 0
                s["task_id"] = None
                s["start_dt"] = None
                s["title"] = ""
                s["project"] = "General"

            elif action == "promote_slot_1":
                slot0_data = msg.get("slot0", {})
                s0 = self.slots[0]
                s0["active"] = True
                s0["running"] = slot0_data.get("running", False)
                s0["seconds"] = slot0_data.get("seconds", 0)
                s0["title"] = slot0_data.get("title", "")
                s0["project"] = slot0_data.get("project", "General")
                s0["task_id"] = slot0_data.get("taskId")
                if s0["running"]:
                    s0["start_dt"] = datetime.now() - timedelta(seconds=s0["seconds"])
                else:
                    s0["start_dt"] = None

                # Reset parallel slot 1
                s1 = self.slots[1]
                s1["active"] = False
                s1["running"] = False
                s1["seconds"] = 0
                s1["task_id"] = None
                s1["start_dt"] = None
                s1["title"] = ""
                s1["project"] = "General"

            elif action == "save_session":
                title = msg.get("title", "").strip() or ("Focus Session" if slot_idx == 0 else "Parallel Session")
                project = msg.get("project", "").strip() or "General"
                secs = msg.get("seconds", 0)
                task_id = msg.get("taskId")
                self._save_session_entry(title, project, secs, task_id, is_closing=False)

                # Reset the saved slot
                s = self.slots.get(slot_idx, self.slots[0])
                s["running"] = False
                s["seconds"] = 0
                s["start_dt"] = None
                s["title"] = ""
                s["task_id"] = None
                if slot_idx == 1:
                    s["active"] = False

            elif action == "navigate":
                target = msg.get("target")
                if target and self.on_navigate_cb:
                    self.on_navigate_cb(target)

            elif action == "open_url":
                url = msg.get("url")
                if url:
                    open_file_or_url(url)

        except Exception as e:
            print(f"[SharkHomeView] Script message handler error: {e}")

    def _save_session_entry(self, title: str, project: str, secs: int, task_id=None, is_closing=False):
        if secs <= 0:
            return

        mins = max(1, round(secs / 60))
        now = datetime.now()
        start_dt = now - timedelta(minutes=mins)
        start_str = start_dt.strftime("%H:%M")
        end_str = now.strftime("%H:%M")
        if start_str == end_str and mins >= 1:
            start_dt = now - timedelta(minutes=mins)
            start_str = start_dt.strftime("%H:%M")
        today_str = now.strftime("%Y-%m-%d")

        # If linked task and user explicitly logged it, mark task completed
        desc = "Live focus session"
        if task_id and not is_closing:
            try:
                task = self.storage.get_task(task_id)
                if task:
                    self.storage.update_task(task_id, status="done", completed_at=now.strftime("%Y-%m-%d %H:%M"))
                    desc = f"Completed task: {task.title}"
            except Exception:
                pass

        entry = JournalEntry(
            date=today_str,
            start_time=start_str,
            end_time=end_str,
            duration_minutes=mins,
            project=project or "General",
            title=title,
            description=desc,
            source="timer",
            linked_task_id=task_id
        )
        self.storage.save_journal_entry(entry)

        if self.on_journal_updated_cb:
            self.on_journal_updated_cb()

    def start_focus_with_task(self, task: Task):
        """Called when user clicks 'Start Focus' on a task from another view."""
        s = self.slots[0]
        s["title"] = task.title
        s["project"] = task.project
        s["task_id"] = task.id
        s["seconds"] = 0
        s["running"] = True
        s["start_dt"] = datetime.now()

        if not HAS_WEBKIT:
            self.gtk_title_entry.set_text(task.title)
            for p_idx in range(self.gtk_proj_model.get_n_items()):
                if self.gtk_proj_model.get_string(p_idx) == task.project:
                    self.gtk_proj_dropdown.set_selected(p_idx)
                    break
            self.gtk_btn_start.set_label("⏸  Pause")
            self.gtk_btn_start.remove_css_class("btn-primary")
            self.gtk_btn_start.add_css_class("btn-secondary")
            return

        payload = json.dumps({
            "id": task.id,
            "title": task.title,
            "project": task.project
        })
        self._eval_js(f"window.startWithTask({payload});")

    def save_timer_if_active(self):
        """Silently auto-saves any active or running live timer session without prompts when window closes."""
        for slot_idx, slot in self.slots.items():
            if slot_idx == 1 and not slot.get("active", False):
                continue
            is_running = slot.get("running", False)
            recorded_secs = slot.get("seconds", 0)
            start_dt = slot.get("start_dt")

            if is_running and start_dt:
                elapsed = int((datetime.now() - start_dt).total_seconds())
                secs = max(recorded_secs, elapsed, 1)
            else:
                secs = recorded_secs

            if is_running or secs > 0:
                title = (slot.get("title") or "").strip()
                if not title:
                    title = "Focus Session" if slot_idx == 0 else "Parallel Session"
                project = slot.get("project") or "General"
                task_id = slot.get("task_id")
                try:
                    self._save_session_entry(title, project, secs, task_id, is_closing=True)
                except Exception as e:
                    print(f"[SharkHomeView] Error auto-saving slot {slot_idx} on close: {e}")

                # Reset slot so subsequent calls won't duplicate
                slot["running"] = False
                slot["seconds"] = 0
                slot["start_dt"] = None
