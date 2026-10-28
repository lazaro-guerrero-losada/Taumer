"""
SharkHomeView: Super-minimalist focus space with live ASCII Sharks ocean animation,
frosted glass translucent input capsule, live stopwatch, and instant Obsidian logging.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('WebKit', '6.0')
from gi.repository import Gtk, WebKit, GLib

from models import JournalEntry, Task


class SharkHomeView(Gtk.Box):
    def __init__(self, storage, on_navigate_cb=None, on_journal_updated_cb=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.storage = storage
        self.on_navigate_cb = on_navigate_cb
        self.on_journal_updated_cb = on_journal_updated_cb

        # State tracking
        self.timer_running = False
        self.timer_seconds = 0
        self.current_title = ""
        self.current_project = "General"
        self.current_task_id = None
        self.session_start_dt = None
        self._page_loaded = False

        self._build_ui()

    def _build_ui(self):
        self.set_hexpand(True)
        self.set_vexpand(True)

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

        # Load HTML
        assets_dir = Path(__file__).resolve().parent / "shark_assets"
        html_file = assets_dir / "index.html"
        self.webview.load_uri(f"file://{html_file.resolve()}")

        self.append(self.webview)

    def _on_load_changed(self, webview, event):
        if event == WebKit.LoadEvent.FINISHED:
            self._page_loaded = True
            self.refresh()

    def _eval_js(self, script: str):
        if not self._page_loaded:
            return
        try:
            self.webview.evaluate_javascript(script, -1, None, None, None, None, None)
        except Exception as e:
            print(f"[SharkHomeView] JS eval error: {e}")

    def refresh(self):
        """Pushes latest projects and pending tasks into the Web view."""
        if not self._page_loaded:
            return

        # 1. Projects
        projects = self.storage.get_projects()
        p_names = [p.name for p in projects]
        if "General" not in p_names:
            p_names.insert(0, "General")
        proj_json = json.dumps(p_names)
        self._eval_js(f"window.setProjects({proj_json});")

        # 2. Pending tasks (undone tasks for quick selection)
        tasks = self.storage.get_tasks()
        pending = [t for t in tasks if t.status != "done"]
        tasks_data = [{"id": t.id, "title": t.title, "project": t.project} for t in pending]
        tasks_json = json.dumps(tasks_data)
        self._eval_js(f"window.setPendingTasks({tasks_json});")

    def _on_script_message(self, manager, js_result):
        try:
            raw = js_result.to_string()
            msg = json.loads(raw)
            action = msg.get("action")

            if action == "start_timer":
                self.timer_running = True
                self.timer_seconds = msg.get("seconds", 0)
                self.current_title = msg.get("title", "")
                self.current_project = msg.get("project", "General")
                self.current_task_id = msg.get("taskId")
                if not self.session_start_dt:
                    self.session_start_dt = datetime.now() - timedelta(seconds=self.timer_seconds)

            elif action in ("pause_timer", "stop_timer"):
                self.timer_running = False
                self.timer_seconds = msg.get("seconds", self.timer_seconds)

            elif action == "tick":
                self.timer_seconds = msg.get("seconds", self.timer_seconds)
                self.current_title = msg.get("title", self.current_title)
                self.current_project = msg.get("project", self.current_project)
                self.current_task_id = msg.get("taskId", self.current_task_id)

            elif action == "input_changed":
                self.current_title = msg.get("title", "")
                self.current_project = msg.get("project", self.current_project)
                self.current_task_id = msg.get("taskId", self.current_task_id)

            elif action == "project_changed":
                self.current_project = msg.get("project", "General")

            elif action == "reset_timer":
                self.timer_running = False
                self.timer_seconds = 0
                self.current_task_id = None
                self.session_start_dt = None

            elif action == "save_session":
                title = msg.get("title", "").strip() or "Focus Session"
                project = msg.get("project", "").strip() or "General"
                secs = msg.get("seconds", 0)
                task_id = msg.get("taskId")
                self._save_session_entry(title, project, secs, task_id)

            elif action == "navigate":
                target = msg.get("target")
                if target and self.on_navigate_cb:
                    self.on_navigate_cb(target)

            elif action == "open_url":
                url = msg.get("url")
                if url:
                    try:
                        import subprocess
                        subprocess.Popen(["xdg-open", url])
                    except Exception as e:
                        print(f"[SharkHomeView] Open URL error: {e}")

        except Exception as e:
            print(f"[SharkHomeView] Script message handler error: {e}")

    def _save_session_entry(self, title: str, project: str, secs: int, task_id=None):
        if secs <= 0:
            return

        mins = max(1, round(secs / 60))
        now = datetime.now()
        start_dt = now - timedelta(seconds=secs)
        start_str = start_dt.strftime("%H:%M")
        end_str = now.strftime("%H:%M")
        today_str = now.strftime("%Y-%m-%d")

        # If linked task, mark as completed
        desc = ""
        if task_id:
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

        # Reset local timer state
        self.timer_running = False
        self.timer_seconds = 0
        self.session_start_dt = None
        self.current_task_id = None

        if self.on_journal_updated_cb:
            self.on_journal_updated_cb()

    def start_focus_with_task(self, task: Task):
        """Called when user clicks 'Start Focus' on a task from another view."""
        self.current_title = task.title
        self.current_project = task.project
        self.current_task_id = task.id
        self.timer_seconds = 0
        self.timer_running = True
        self.session_start_dt = datetime.now()

        payload = json.dumps({
            "id": task.id,
            "title": task.title,
            "project": task.project
        })
        self._eval_js(f"window.startWithTask({payload});")

    def save_timer_if_active(self):
        """Silently auto-saves active session without prompts when window closes."""
        if not (self.timer_running or self.timer_seconds >= 60):
            return
        try:
            title = self.current_title.strip() or "Focus Session"
            self._save_session_entry(title, self.current_project, self.timer_seconds, self.current_task_id)
            self._eval_js("window.resetTimer();")
        except Exception as e:
            print(f"[SharkHomeView] Error auto-saving active timer on close: {e}")
