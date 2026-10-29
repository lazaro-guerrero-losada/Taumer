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
                    try:
                        import subprocess
                        subprocess.Popen(["xdg-open", url])
                    except Exception as e:
                        print(f"[SharkHomeView] Open URL error: {e}")

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
