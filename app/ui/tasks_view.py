"""
Tasks view: Apple-style task board with project management, filtering, and Obsidian sync.
Refined UI with restrained input widths and English localization.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from datetime import datetime
from models import Task
from ui.dialogs import NewTaskDialog, ManageProjectsDialog, TaskCompletionDialog

class TasksView(Gtk.Box):
    def __init__(self, storage, on_start_timer_cb = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.storage = storage
        self.on_start_timer_cb = on_start_timer_cb
        self.selected_project_filter = "All"
        self.selected_status_filter = "Pending"
        self.search_query = ""

        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(22)
        self.set_margin_end(22)

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # 1. Top bar: Title + Action buttons (Projects, New Task)
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        lbl_title = Gtk.Label(label="Tasks")
        lbl_title.add_css_class("text-heading")
        top_bar.append(lbl_title)

        top_bar.append(Gtk.Box(hexpand=True))

        manage_proj_btn = Gtk.Button(label="⚙ Projects")
        manage_proj_btn.add_css_class("btn-secondary")
        manage_proj_btn.connect("clicked", self._open_manage_projects)
        top_bar.append(manage_proj_btn)

        new_btn = Gtk.Button(label="+ New Task")
        new_btn.add_css_class("btn-primary")
        new_btn.connect("clicked", self._open_new_task_dialog)
        top_bar.append(new_btn)

        self.append(top_bar)

        # 2. Inline quick add bar (Restrained width, not stretching across full screen)
        quick_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        quick_container.set_halign(Gtk.Align.START)

        quick_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        quick_box.add_css_class("card-box")

        self.quick_entry = Gtk.Entry()
        self.quick_entry.set_size_request(380, -1)
        self.quick_entry.set_placeholder_text("Add a quick task... (Press Enter)")
        self.quick_entry.connect("activate", self._on_quick_add)
        quick_box.append(self.quick_entry)

        self.quick_proj_dropdown = Gtk.DropDown()
        self._update_quick_projects()
        quick_box.append(self.quick_proj_dropdown)

        add_btn = Gtk.Button(label="Add")
        add_btn.add_css_class("btn-secondary")
        add_btn.connect("clicked", self._on_quick_add)
        quick_box.append(add_btn)

        quick_container.append(quick_box)
        self.append(quick_container)

        # 3. Filter Bar (Segmented Control style)
        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        # Search entry
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search tasks...")
        self.search_entry.set_size_request(200, -1)
        self.search_entry.connect("search-changed", self._on_search_changed)
        filter_box.append(self.search_entry)

        # Status filter segmented bar
        self.segmented_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.segmented_box.add_css_class("segmented-bar")

        self.status_buttons = {}
        for st in ["Pending", "All", "Completed"]:
            btn = Gtk.Button(label=st)
            btn.add_css_class("segmented-btn")
            if st == self.selected_status_filter:
                btn.add_css_class("active")
            btn.connect("clicked", self._on_status_filter_clicked, st)
            self.segmented_box.append(btn)
            self.status_buttons[st] = btn

        filter_box.append(self.segmented_box)

        # Project filter dropdown
        lbl_p = Gtk.Label(label="Project:")
        lbl_p.add_css_class("text-muted")
        lbl_p.set_margin_start(6)
        filter_box.append(lbl_p)

        self.filter_proj_dropdown = Gtk.DropDown()
        self._update_filter_projects()
        self.filter_proj_dropdown.connect("notify::selected", self._on_project_filter_changed)
        filter_box.append(self.filter_proj_dropdown)

        self.append(filter_box)

        # 4. Scrolled task list
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        self.scrolled.set_hexpand(True)
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.tasks_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.scrolled.set_child(self.tasks_container)
        self.append(self.scrolled)

    def _open_manage_projects(self, btn):
        win = self.get_root()
        dlg = ManageProjectsDialog(win, self.storage, self._on_projects_changed)
        dlg.present()

    def _on_projects_changed(self):
        self._update_quick_projects()
        self._update_filter_projects()
        self.refresh()

    def _update_quick_projects(self):
        projects = self.storage.get_projects()
        names = [f"{p.icon} {p.name}" for p in projects]
        self.quick_proj_dropdown.set_model(Gtk.StringList.new(names))

    def _update_filter_projects(self):
        projects = self.storage.get_projects()
        names = ["All Projects"] + [f"{p.icon} {p.name}" for p in projects]
        self.filter_proj_dropdown.set_model(Gtk.StringList.new(names))

    def _on_search_changed(self, entry):
        self.search_query = entry.get_text().strip().lower()
        self.refresh()

    def _on_status_filter_clicked(self, btn, status):
        self.selected_status_filter = status
        for st, b in self.status_buttons.items():
            if st == status:
                b.add_css_class("active")
            else:
                b.remove_css_class("active")
        self.refresh()

    def _on_project_filter_changed(self, dropdown, param):
        idx = dropdown.get_selected()
        if idx == 0:
            self.selected_project_filter = "All"
        else:
            projects = self.storage.get_projects()
            if idx - 1 < len(projects):
                self.selected_project_filter = projects[idx - 1].name
        self.refresh()

    def _on_quick_add(self, *args):
        text = self.quick_entry.get_text().strip()
        if not text:
            return
        
        sel_idx = self.quick_proj_dropdown.get_selected()
        projects = self.storage.get_projects()
        proj = projects[sel_idx] if sel_idx < len(projects) else None
        proj_name = proj.name if proj else "General"
        icon = proj.icon if proj else "●"

        task = Task(
            title=text,
            project=proj_name,
            icon=icon,
            priority="medium",
            estimated_minutes=30,
            scheduled_duration=None,
            is_open_ended=True
        )
        self.storage.add_task(task)
        self.quick_entry.set_text("")
        self.refresh()

    def _open_new_task_dialog(self, btn):
        win = self.get_root()
        dlg = NewTaskDialog(win, self.storage, self.refresh)
        dlg.present()

    def refresh(self):
        while child := self.tasks_container.get_first_child():
            self.tasks_container.remove(child)

        all_tasks = self.storage.get_tasks()

        filtered = []
        for t in all_tasks:
            # Events only belong in the calendar, not in the tasks section
            if getattr(t, "item_type", "task") == "event":
                continue
            if self.selected_status_filter == "Pending" and t.status == "done":
                continue
            if self.selected_status_filter == "Completed" and t.status != "done":
                continue
            if self.selected_project_filter != "All" and t.project != self.selected_project_filter:
                continue
            if self.search_query and (self.search_query not in t.title.lower() and self.search_query not in t.project.lower()):
                continue
            filtered.append(t)

        if not filtered:
            empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            empty_box.set_valign(Gtk.Align.CENTER)
            empty_box.set_halign(Gtk.Align.CENTER)
            empty_box.set_margin_top(48)
            
            lbl_e = Gtk.Label(label="No tasks found in this view")
            lbl_e.add_css_class("text-heading")
            lbl_sub = Gtk.Label(label="Create a new task above or adjust the active filters.")
            lbl_sub.add_css_class("text-muted")
            empty_box.append(lbl_e)
            empty_box.append(lbl_sub)
            self.tasks_container.append(empty_box)
            return

        for t in filtered:
            card = self._create_task_card(t)
            self.tasks_container.append(card)

    def _create_task_card(self, task: Task) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.add_css_class("card-box")

        # Checkbutton
        chk = Gtk.CheckButton()
        chk.set_active(task.status == "done")
        chk.connect("toggled", lambda b, tid=task.id: self._toggle_task(tid, b.get_active(), chk=b))
        card.append(chk)

        # Center content
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        center_box.set_hexpand(True)

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        
        # Project pill
        proj_lbl = Gtk.Label(label=f"{task.icon} {task.project}")
        proj_lbl.add_css_class("tag-pill-project")
        top_row.append(proj_lbl)

        # Priority pill
        if task.priority:
            prio_l = task.priority.lower()
            prio_css = "tag-pill-high" if prio_l in ["alta", "high"] else "tag-pill"
            prio_sym = "●" if prio_l in ["alta", "high"] else "○"
            prio_lbl = Gtk.Label(label=f"{prio_sym} {task.priority.capitalize()}")
            prio_lbl.add_css_class(prio_css)
            top_row.append(prio_lbl)

        # Duration badge
        is_open = getattr(task, "is_open_ended", False) or (task.scheduled_duration is None)
        if task.status == "done" and getattr(task, "actual_minutes", None):
            dur_lbl = Gtk.Label(label=f"✓ {task.actual_minutes}m")
            dur_lbl.add_css_class("tag-pill-completed")
        elif is_open and task.status != "done":
            dur_lbl = Gtk.Label(label="◈ Open-ended")
            dur_lbl.add_css_class("tag-pill-open")
        else:
            dur_val = task.scheduled_duration or task.estimated_minutes
            dur_lbl = Gtk.Label(label=f"{dur_val}m" if dur_val else "◈ Open-ended")
            dur_lbl.add_css_class("tag-pill")
        top_row.append(dur_lbl)

        # Scheduled badge
        if task.scheduled_time:
            time_lbl = Gtk.Label(label=f"◷ {task.scheduled_time}")
            time_lbl.add_css_class("tag-pill")
            top_row.append(time_lbl)

        center_box.append(top_row)

        # Title
        title_lbl = Gtk.Label(label=task.title)
        title_lbl.set_halign(Gtk.Align.START)
        title_lbl.add_css_class("text-title")
        if task.status == "done":
            title_lbl.add_css_class("text-muted")
        center_box.append(title_lbl)

        # Notes if any
        if task.notes:
            notes_lbl = Gtk.Label(label=task.notes)
            notes_lbl.set_halign(Gtk.Align.START)
            notes_lbl.add_css_class("text-muted")
            center_box.append(notes_lbl)

        card.append(center_box)

        # Actions
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        
        # Focus button
        if self.on_start_timer_cb and task.status != "done":
            focus_btn = Gtk.Button(label="Focus")
            focus_btn.add_css_class("btn-secondary")
            focus_btn.set_tooltip_text("Start live stopwatch in Journal")
            focus_btn.connect("clicked", lambda b, t=task: self.on_start_timer_cb(t))
            actions_box.append(focus_btn)

        # Edit button
        edit_btn = Gtk.Button(label="Edit")
        edit_btn.add_css_class("btn-ghost")
        edit_btn.connect("clicked", lambda b, t=task: self._edit_task(t))
        actions_box.append(edit_btn)

        # Delete button
        del_btn = Gtk.Button(label="✕")
        del_btn.add_css_class("btn-ghost")
        del_btn.set_tooltip_text("Delete task")
        del_btn.connect("clicked", lambda b, tid=task.id: self._delete_task(tid))
        actions_box.append(del_btn)

        card.append(actions_box)
        return card

    def _toggle_task(self, task_id: str, is_done: bool, chk=None):
        if not is_done:
            self.storage.complete_task(task_id, False)
            self.refresh()
        else:
            task = self.storage.get_task_by_id(task_id)
            if not task:
                self.storage.complete_task(task_id, True)
                self.refresh()
                return

            def on_cancel():
                if chk:
                    chk.set_active(False)

            win = self.get_root()
            dlg = TaskCompletionDialog(win, self.storage, task, is_event=False, on_done_cb=self.refresh, on_cancel_cb=on_cancel)
            dlg.present()

    def _edit_task(self, task: Task):
        win = self.get_root()
        dlg = NewTaskDialog(win, self.storage, self.refresh, edit_task=task)
        dlg.present()

    def _delete_task(self, task_id: str):
        self.storage.delete_task(task_id)
        self.refresh()
