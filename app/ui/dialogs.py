"""
Dialogs for tasks, retrospective journal entries, and project management.
Apple-style clean, user-friendly modals with monochrome typography and restrained input widths.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk
import re
from datetime import datetime, timedelta
from models import Task, JournalEntry, Project

def normalize_date_input(text: str) -> str | None:
    if not text:
        return None
    text = text.strip()
    if not text:
        return None
    low = text.lower()
    # Strip ordinal suffixes like 1st, 2nd, 3rd, 4th
    low = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", low)
    now = datetime.now()
    if low in ["today", "hoy"]:
        return now.strftime("%Y-%m-%d")
    if low in ["tomorrow", "mañana", "manana"]:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")

    # 1. YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text

    # 2. DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    m = re.match(r"^(\d{1,2})[/\.-](\d{1,2})[/\.-](\d{4})$", text)
    if m:
        d, m_val, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{m_val:02d}-{d:02d}"

    # 3. DD/MM or DD-MM (assumes current year)
    m = re.match(r"^(\d{1,2})[/\.-](\d{1,2})$", text)
    if m:
        d, m_val = int(m.group(1)), int(m.group(2))
        return f"{now.year:04d}-{m_val:02d}-{d:02d}"

    # 4. Words like "4 nov", "4 de noviembre", "nov 4", "4th november", "4th of november"
    months_map = {
        "septiembre": 9, "september": 9,
        "noviembre": 11, "november": 11,
        "diciembre": 12, "december": 12,
        "febrero": 2, "february": 2,
        "octubre": 10, "october": 10,
        "enero": 1, "january": 1,
        "agosto": 8, "august": 8,
        "marzo": 3, "march": 3,
        "abril": 4, "april": 4,
        "junio": 6, "julio": 7,
        "june": 6, "july": 7,
        "mayo": 5, "may": 5,
        "sept": 9, "sep": 9,
        "ene": 1, "jan": 1,
        "feb": 2, "mar": 3,
        "abr": 4, "apr": 4,
        "jun": 6, "jul": 7,
        "ago": 8, "aug": 8,
        "oct": 10, "nov": 11,
        "dic": 12, "dec": 12
    }
    for name, month_num in months_map.items():
        if name in low:
            day_matches = re.findall(r"\b\d{1,2}\b", low)
            if day_matches:
                day_num = int(day_matches[0])
                year_num = now.year
                year_matches = re.findall(r"\b20\d{2}\b", low)
                if year_matches:
                    year_num = int(year_matches[0])
                return f"{year_num:04d}-{month_num:02d}-{day_num:02d}"

    return text

def parse_time_minutes(t_str: str | None) -> int | None:
    """Parses 'HH:MM' string to minutes from midnight."""
    if not t_str or ":" not in t_str:
        return None
    try:
        parts = t_str.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return None

def parse_duration_input(text: str | None, default: int = 30) -> int:
    """
    Parses flexible duration inputs into integer minutes.
    Supports: '45', '45m', '45 min', '1h', '1.5h', '1h 30m', '90'
    """
    if not text:
        return default
    text = text.strip().lower()
    m_h = re.match(r"^(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours|hora|horas)$", text)
    if m_h:
        return max(1, int(float(m_h.group(1)) * 60))
    m_hm = re.match(r"^(\d+)\s*(?:h|hr|hora)\s*(\d+)?\s*(?:m|min)?$", text)
    if m_hm:
        h = int(m_hm.group(1))
        m = int(m_hm.group(2)) if m_hm.group(2) else 0
        return max(1, h * 60 + m)
    digits = re.findall(r"\d+", text)
    if digits:
        return max(1, int(digits[0]))
    return default

class NewTaskDialog(Gtk.Window):
    def __init__(self, parent, storage, on_saved_cb, edit_task: Task = None, default_type: str = "task", prefill_date: str = None, prefill_time: str = None):
        super().__init__(transient_for=parent, modal=True)
        self.storage = storage
        self.on_saved_cb = on_saved_cb
        self.edit_task = edit_task
        self.default_type = default_type
        self.prefill_date = prefill_date
        self.prefill_time = prefill_time

        # Check if editing existing task in storage
        self.is_editing_existing = False
        if self.edit_task and getattr(self.edit_task, "id", None):
            self.is_editing_existing = any(t.id == self.edit_task.id for t in self.storage.tasks)

        self.item_type = getattr(self.edit_task, "item_type", self.default_type) if self.edit_task else self.default_type

        title_text = ("Edit Event" if self.item_type == "event" else "Edit Task") if self.is_editing_existing else ("New Event" if self.item_type == "event" else "New Task")
        self.set_title(title_text)
        self.set_default_size(480, 520)
        self.add_css_class("card-box")

        self._build_ui()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_margin_top(18)
        vbox.set_margin_bottom(18)
        vbox.set_margin_start(22)
        vbox.set_margin_end(22)
        self.set_child(vbox)

        # Header with Type Selector (Task vs Event)
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.header_lbl = Gtk.Label(label="Edit Event" if (self.edit_task and getattr(self.edit_task, "item_type", "task") == "event") else ("Edit Task" if self.edit_task else "New Item"))
        self.header_lbl.add_css_class("text-heading")
        self.header_lbl.set_halign(Gtk.Align.START)
        top_row.append(self.header_lbl)
        top_row.append(Gtk.Box(hexpand=True))

        # Task vs Event Segmented Bar
        self.type_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.type_bar.add_css_class("segmented-bar")
        self.btn_type_task = Gtk.Button(label="⊞ Task")
        self.btn_type_task.add_css_class("segmented-btn")
        self.btn_type_event = Gtk.Button(label="◈ Event")
        self.btn_type_event.add_css_class("segmented-btn")

        self.item_type = getattr(self.edit_task, "item_type", self.default_type) if self.edit_task else self.default_type
        if self.item_type == "event":
            self.btn_type_event.add_css_class("active")
        else:
            self.btn_type_task.add_css_class("active")

        def select_type(t_type):
            self.item_type = t_type
            if t_type == "event":
                self.btn_type_event.add_css_class("active")
                self.btn_type_task.remove_css_class("active")
                self.header_lbl.set_text("Edit Event" if self.is_editing_existing else "New Event")
                self.lbl_t.set_text("Event Title")
                self.title_entry.set_placeholder_text("e.g. Team Standup, Client Call, or Lecture")
                self.lbl_dur.set_text("Duration (min)")
                if not self.date_entry.get_text().strip():
                    self.date_entry.set_text(self.prefill_date or datetime.now().strftime("%Y-%m-%d"))
                if not self.time_entry.get_text().strip():
                    self.time_entry.set_text(self.prefill_time or "10:00")
            else:
                self.btn_type_task.add_css_class("active")
                self.btn_type_event.remove_css_class("active")
                self.header_lbl.set_text("Edit Task" if self.is_editing_existing else "New Task")
                self.lbl_t.set_text("Task Title")
                self.title_entry.set_placeholder_text("e.g. Design track curve or Study Navier-Stokes")
                self.lbl_dur.set_text("Planned Slot (min)")

            self.open_ended_box.set_visible(True)
            self.dur_entry.set_sensitive(True)
            if self.chk_open_ended.get_active():
                self.dur_entry.set_placeholder_text("Undefined / Open-ended")
            elif not self.dur_entry.get_text().strip():
                self.dur_entry.set_text("60" if t_type == "event" else "30")

        self.btn_type_task.connect("clicked", lambda b: select_type("task"))
        self.btn_type_event.connect("clicked", lambda b: select_type("event"))
        self.type_bar.append(self.btn_type_task)
        self.type_bar.append(self.btn_type_event)
        top_row.append(self.type_bar)
        vbox.append(top_row)

        # Title entry
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.lbl_t = Gtk.Label(label="Event Title" if self.item_type == "event" else "Task Title")
        self.lbl_t.add_css_class("text-muted")
        self.lbl_t.set_halign(Gtk.Align.START)
        self.title_entry = Gtk.Entry()
        self.title_entry.set_placeholder_text("e.g. Design track curve or Study Navier-Stokes" if self.item_type != "event" else "e.g. Team Standup, Client Call, or Lecture")
        if self.edit_task and getattr(self.edit_task, "title", None):
            self.title_entry.set_text(self.edit_task.title)
        self.title_entry.connect("activate", self._on_save)
        title_box.append(self.lbl_t)
        title_box.append(self.title_entry)
        vbox.append(title_box)

        # Project and Priority
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        vbox.append(row1)

        # Project dropdown
        proj_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        proj_box.set_hexpand(True)
        lbl_p = Gtk.Label(label="Project / Context")
        lbl_p.add_css_class("text-muted")
        lbl_p.set_halign(Gtk.Align.START)
        
        self.proj_dropdown = Gtk.DropDown()
        self.projects = self.storage.get_projects()
        proj_names = [f"{p.icon} {p.name}" for p in self.projects]
        self.proj_dropdown.set_model(Gtk.StringList.new(proj_names))
        
        active_proj = self.edit_task.project if (self.edit_task and getattr(self.edit_task, "project", None)) else "General"
        for i, p in enumerate(self.projects):
            if p.name == active_proj:
                self.proj_dropdown.set_selected(i)
                break

        proj_box.append(lbl_p)
        proj_box.append(self.proj_dropdown)
        row1.append(proj_box)

        # Priority dropdown
        prio_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_pr = Gtk.Label(label="Priority")
        lbl_pr.add_css_class("text-muted")
        lbl_pr.set_halign(Gtk.Align.START)
        self.prio_dropdown = Gtk.DropDown()
        self.prio_dropdown.set_model(Gtk.StringList.new(["Low", "Medium", "High"]))
        
        prio_map = {"baja": 0, "low": 0, "media": 1, "medium": 1, "alta": 2, "high": 2}
        cur_prio = (self.edit_task.priority.lower() if self.edit_task and getattr(self.edit_task, "priority", None) else "medium")
        self.prio_dropdown.set_selected(prio_map.get(cur_prio, 1))

        prio_box.append(lbl_pr)
        prio_box.append(self.prio_dropdown)
        row1.append(prio_box)

        # Scheduled Date, Scheduled Time & Duration
        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vbox.append(row2)

        # Scheduled Date (YYYY-MM-DD)
        date_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        date_box.set_hexpand(True)
        lbl_date = Gtk.Label(label="Scheduled Date")
        lbl_date.add_css_class("text-muted")
        lbl_date.set_halign(Gtk.Align.START)
        self.date_entry = Gtk.Entry()
        self.date_entry.set_placeholder_text("YYYY-MM-DD or 4/11")
        if self.edit_task and getattr(self.edit_task, "scheduled_date", None):
            self.date_entry.set_text(self.edit_task.scheduled_date)
        elif self.prefill_date:
            self.date_entry.set_text(self.prefill_date)
        elif self.item_type == "event":
            self.date_entry.set_text(datetime.now().strftime("%Y-%m-%d"))
        self.date_entry.connect("activate", self._on_save)
        date_box.append(lbl_date)
        date_box.append(self.date_entry)
        row2.append(date_box)

        # Scheduled Time (HH:MM)
        sched_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sched_box.set_hexpand(True)
        lbl_sched = Gtk.Label(label="Time (HH:MM)")
        lbl_sched.add_css_class("text-muted")
        lbl_sched.set_halign(Gtk.Align.START)
        self.time_entry = Gtk.Entry()
        self.time_entry.set_placeholder_text("e.g. 10:00")
        if self.edit_task and getattr(self.edit_task, "scheduled_time", None):
            self.time_entry.set_text(self.edit_task.scheduled_time)
        elif self.prefill_time:
            self.time_entry.set_text(self.prefill_time)
        elif self.item_type == "event":
            self.time_entry.set_text("10:00")
        self.time_entry.connect("activate", self._on_save)
        sched_box.append(lbl_sched)
        sched_box.append(self.time_entry)
        row2.append(sched_box)

        # Duration & Open-ended Event Option
        dur_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        dur_box.set_hexpand(True)
        self.lbl_dur = Gtk.Label(label="Duration (min)" if self.item_type == "event" else "Planned Slot (min)")
        self.lbl_dur.add_css_class("text-muted")
        self.lbl_dur.set_halign(Gtk.Align.START)
        
        self.dur_entry = Gtk.Entry()
        if self.edit_task:
            init_open = getattr(self.edit_task, "is_open_ended", False) or (self.edit_task.scheduled_duration is None)
        else:
            init_open = True
        
        self.dur_entry.set_sensitive(True)
        if init_open:
            self.dur_entry.set_text("")
            self.dur_entry.set_placeholder_text("Undefined / Open-ended")
        else:
            default_dur_val = self.edit_task.scheduled_duration or self.edit_task.estimated_minutes
            self.dur_entry.set_text(str(default_dur_val) if default_dur_val else "30")
            self.dur_entry.set_placeholder_text("e.g. 60" if self.item_type == "event" else "e.g. 30 (visual slot)")
        
        self.dur_entry.connect("activate", self._on_save)
        dur_box.append(self.lbl_dur)
        dur_box.append(self.dur_entry)

        # Open-ended check for tasks & events (duration undefined, prompt on completion)
        self.open_ended_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.open_ended_box.set_margin_top(2)
        self.chk_open_ended = Gtk.CheckButton(label="Open-ended (duration undefined, ask when completing)")
        self.chk_open_ended.set_active(init_open)

        self._updating_dur = False

        def on_open_toggled(chk):
            if self._updating_dur:
                return
            active = chk.get_active()
            self._updating_dur = True
            if active:
                self.dur_entry.set_text("")
                self.dur_entry.set_placeholder_text("Undefined / Open-ended")
            else:
                if not self.dur_entry.get_text().strip():
                    self.dur_entry.set_text("60" if self.item_type == "event" else "30")
            self._updating_dur = False

        def on_dur_changed(entry):
            if self._updating_dur:
                return
            text = entry.get_text().strip()
            self._updating_dur = True
            if text:
                self.chk_open_ended.set_active(False)
            else:
                self.chk_open_ended.set_active(True)
                self.dur_entry.set_placeholder_text("Undefined / Open-ended")
            self._updating_dur = False

        self.chk_open_ended.connect("toggled", on_open_toggled)
        self.dur_entry.connect("changed", on_dur_changed)
        self.open_ended_box.append(self.chk_open_ended)
        self.open_ended_box.set_visible(True)
        dur_box.append(self.open_ended_box)
        row2.append(dur_box)

        # Notes
        notes_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_n = Gtk.Label(label="Notes / Obsidian Links")
        lbl_n.add_css_class("text-muted")
        lbl_n.set_halign(Gtk.Align.START)
        self.notes_entry = Gtk.Entry()
        self.notes_entry.set_placeholder_text("Notes, links [[...]] or details")
        if self.edit_task and getattr(self.edit_task, "notes", None):
            self.notes_entry.set_text(self.edit_task.notes)
        self.notes_entry.connect("activate", self._on_save)
        notes_box.append(lbl_n)
        notes_box.append(self.notes_entry)
        vbox.append(notes_box)

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(12)
        vbox.append(btn_box)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.add_css_class("btn-secondary")
        cancel_btn.connect("clicked", lambda b: self.close())
        btn_box.append(cancel_btn)

        save_btn_label = "Save Changes" if self.is_editing_existing else ("Create Event" if self.item_type == "event" else "Create Task")
        save_btn = Gtk.Button(label=save_btn_label)
        save_btn.add_css_class("btn-primary")
        save_btn.connect("clicked", self._on_save)
        btn_box.append(save_btn)

    def _on_save(self, *args):
        title = self.title_entry.get_text().strip()
        if not title:
            return

        sel_idx = self.proj_dropdown.get_selected()
        selected_proj = self.projects[sel_idx] if sel_idx < len(self.projects) else None
        proj_name = selected_proj.name if selected_proj else "General"
        icon = selected_proj.icon if selected_proj else "●"

        prio_idx = self.prio_dropdown.get_selected()
        prio_names = ["low", "medium", "high"]
        prio = prio_names[prio_idx] if prio_idx < len(prio_names) else "medium"

        dur_text = self.dur_entry.get_text().strip()
        parsed_dur = parse_duration_input(dur_text, default=0) if dur_text else 0

        if self.chk_open_ended.get_active() or not dur_text or parsed_dur <= 0:
            is_open_ended = True
            dur = None
        else:
            is_open_ended = False
            dur = parsed_dur

        raw_date = self.date_entry.get_text().strip()
        sched_date = normalize_date_input(raw_date)

        sched_time = self.time_entry.get_text().strip() or None
        if sched_time and not sched_date:
            sched_date = datetime.now().strftime("%Y-%m-%d")

        notes = self.notes_entry.get_text().strip()

        if self.is_editing_existing:
            self.storage.update_task(
                self.edit_task.id,
                title=title,
                project=proj_name,
                priority=prio,
                estimated_minutes=(dur or 30),
                scheduled_duration=dur,
                is_open_ended=is_open_ended,
                scheduled_date=sched_date,
                scheduled_time=sched_time,
                notes=notes,
                icon=icon,
                item_type=self.item_type
            )
        else:
            task = Task(
                title=title,
                project=proj_name,
                priority=prio,
                estimated_minutes=(dur or 30),
                scheduled_duration=dur,
                is_open_ended=is_open_ended,
                scheduled_date=sched_date,
                scheduled_time=sched_time,
                notes=notes,
                icon=icon,
                item_type=self.item_type
            )
            self.storage.add_task(task)

        if self.on_saved_cb:
            self.on_saved_cb()
        self.close()


class TaskCompletionDialog(Gtk.Window):
    """
    Apple-style modal prompting the user for the actual duration spent
    when completing a task or logging an event.
    """
    def __init__(self, parent, storage, task: Task, is_event: bool = False, on_done_cb = None, on_cancel_cb = None):
        super().__init__(transient_for=parent, modal=True)
        self.storage = storage
        self.task = task
        self.is_event = is_event
        self.on_done_cb = on_done_cb
        self.on_cancel_cb = on_cancel_cb
        self.completed_confirmed = False

        title_text = "Log Event Duration" if is_event else "Complete Task"
        self.set_title(title_text)
        self.set_default_size(440, 360)
        self.set_resizable(False)
        self.add_css_class("card-box")

        self.connect("close-request", self._on_window_close)
        self._build_ui()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        vbox.set_margin_start(24)
        vbox.set_margin_end(24)
        self.set_child(vbox)

        # 1. Header: Icon + Title
        h_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_head = Gtk.Label(label="◈ Log Event" if self.is_event else "✓ Complete Task")
        lbl_head.add_css_class("text-heading")
        lbl_head.set_halign(Gtk.Align.START)
        h_box.append(lbl_head)
        h_box.append(Gtk.Box(hexpand=True))

        proj_pill = Gtk.Label(label=f"{self.task.icon} {self.task.project}")
        proj_pill.add_css_class("tag-pill-project")
        h_box.append(proj_pill)
        vbox.append(h_box)

        # 2. Task / Event Title Card
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title_box.add_css_class("report-row-card")
        
        lbl_item_title = Gtk.Label(label=self.task.title)
        lbl_item_title.add_css_class("text-title")
        lbl_item_title.set_halign(Gtk.Align.START)
        lbl_item_title.set_wrap(True)
        title_box.append(lbl_item_title)

        is_open = getattr(self.task, "is_open_ended", False) or (self.task.scheduled_duration is None)
        if self.task.scheduled_time:
            time_info = f"Scheduled: {self.task.scheduled_time}"
            if not is_open and self.task.scheduled_duration:
                time_info += f" ({self.task.scheduled_duration}m planned slot)"
            else:
                time_info += " (open-ended)"
            lbl_time_info = Gtk.Label(label=time_info)
            lbl_time_info.add_css_class("text-muted")
            lbl_time_info.set_halign(Gtk.Align.START)
            title_box.append(lbl_time_info)

        vbox.append(title_box)

        # 3. Question / Prompt
        prompt_txt = "How long did this event last?" if self.is_event else "How much time did it take you to complete?"
        lbl_prompt = Gtk.Label(label=prompt_txt)
        lbl_prompt.add_css_class("text-title")
        lbl_prompt.set_halign(Gtk.Align.START)
        vbox.append(lbl_prompt)

        # Calculate initial smart duration
        suggested_m = 30
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        
        if (self.is_event or is_open) and self.task.scheduled_time and self.task.scheduled_date == today_str:
            sm = parse_time_minutes(self.task.scheduled_time)
            if sm is not None:
                now_m = now.hour * 60 + now.minute
                if now_m > sm:
                    suggested_m = max(10, now_m - sm)
        elif not is_open and self.task.scheduled_duration:
            suggested_m = self.task.scheduled_duration
        elif not is_open and self.task.estimated_minutes:
            suggested_m = self.task.estimated_minutes

        # Quick preset chips
        preset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        presets = [("15m", 15), ("30m", 30), ("45m", 45), ("1h", 60), ("1h 30m", 90), ("2h", 120)]
        for label, val in presets:
            btn_p = Gtk.Button(label=label)
            btn_p.add_css_class("btn-secondary")
            btn_p.add_css_class("preset-chip-btn")
            btn_p.connect("clicked", lambda b, v=val: self._select_preset(v))
            preset_box.append(btn_p)
        vbox.append(preset_box)

        # Duration Entry Row
        dur_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        dur_row.set_margin_top(4)
        
        self.dur_entry = Gtk.Entry()
        self.dur_entry.set_text(str(suggested_m))
        self.dur_entry.set_hexpand(True)
        self.dur_entry.connect("activate", lambda e: self._on_confirm())
        dur_row.append(self.dur_entry)

        lbl_min = Gtk.Label(label="minutes")
        lbl_min.add_css_class("text-muted")
        dur_row.append(lbl_min)
        vbox.append(dur_row)

        vbox.append(Gtk.Box(vexpand=True))

        # Bottom Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_halign(Gtk.Align.END)
        
        btn_cancel = Gtk.Button(label="Cancel")
        btn_cancel.add_css_class("btn-secondary")
        btn_cancel.connect("clicked", lambda b: self._on_cancel())
        btn_box.append(btn_cancel)

        btn_confirm = Gtk.Button(label="Log to Journal" if self.is_event else "Save & Complete")
        btn_confirm.add_css_class("btn-primary")
        btn_confirm.connect("clicked", lambda b: self._on_confirm())
        btn_box.append(btn_confirm)
        vbox.append(btn_box)

    def _select_preset(self, minutes: int):
        self.dur_entry.set_text(str(minutes))
        self.dur_entry.grab_focus()

    def _on_confirm(self):
        self.completed_confirmed = True
        raw_text = self.dur_entry.get_text()
        actual_m = parse_duration_input(raw_text, default=30)
        
        if self.is_event:
            self.storage.log_event_to_journal(self.task.id, actual_minutes=actual_m)
        else:
            self.storage.complete_task(self.task.id, is_done=True, actual_minutes=actual_m)
            
        if self.on_done_cb:
            self.on_done_cb()
        self.close()

    def _on_cancel(self):
        if not self.completed_confirmed and self.on_cancel_cb:
            self.on_cancel_cb()
        self.close()

    def _on_window_close(self, win):
        if not self.completed_confirmed and self.on_cancel_cb:
            self.on_cancel_cb()
        return False


class NewJournalEntryDialog(Gtk.Window):
    """
    Retrospective Activity Logger & Editor:
    Lets user log what they've ALREADY done or edit existing entries,
    specify duration/time, project, and optionally link/complete a pending task.
    """
    def __init__(self, parent, storage, on_saved_cb, prefill: dict = None, edit_entry: JournalEntry = None):
        super().__init__(transient_for=parent, modal=True)
        self.storage = storage
        self.on_saved_cb = on_saved_cb
        self.edit_entry = edit_entry
        self.prefill = prefill or {}
        if self.edit_entry:
            self.prefill = {
                "title": self.edit_entry.title,
                "project": self.edit_entry.project,
                "start_time": self.edit_entry.start_time,
                "duration_minutes": self.edit_entry.duration_minutes,
                "description": self.edit_entry.description,
                "source": self.edit_entry.source
            }

        self.set_title("Edit Activity Log" if self.edit_entry else "Log Completed Activity")
        self.set_default_size(480, 500)
        self.add_css_class("card-box")

        self._build_ui()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_margin_top(18)
        vbox.set_margin_bottom(18)
        vbox.set_margin_start(22)
        vbox.set_margin_end(22)
        self.set_child(vbox)

        # Header
        header_lbl = Gtk.Label(label="Edit Activity Log" if self.edit_entry else "Log Completed Activity")
        header_lbl.add_css_class("text-heading")
        header_lbl.set_halign(Gtk.Align.START)
        vbox.append(header_lbl)

        sub_lbl = Gtk.Label(label="Update your logged activity, project, time spent, or related notes." if self.edit_entry else "Record what you've worked on, time spent, and complete related tasks.")
        sub_lbl.add_css_class("text-muted")
        sub_lbl.set_halign(Gtk.Align.START)
        vbox.append(sub_lbl)

        # Title
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_t = Gtk.Label(label="What did you do? (Concept or Title)")
        lbl_t.add_css_class("text-muted")
        lbl_t.set_halign(Gtk.Align.START)
        self.title_entry = Gtk.Entry()
        self.title_entry.set_placeholder_text("e.g. Navier-Stokes equations or Chassis 3D model")
        if "title" in self.prefill:
            self.title_entry.set_text(self.prefill["title"])
        self.title_entry.connect("activate", self._on_save)
        title_box.append(lbl_t)
        title_box.append(self.title_entry)
        vbox.append(title_box)

        # Project and Link Task row
        row_proj = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        vbox.append(row_proj)

        # Project dropdown
        proj_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        proj_box.set_hexpand(True)
        lbl_p = Gtk.Label(label="Project")
        lbl_p.add_css_class("text-muted")
        lbl_p.set_halign(Gtk.Align.START)
        self.proj_dropdown = Gtk.DropDown()
        self.projects = self.storage.get_projects()
        proj_names = [f"{p.icon} {p.name}" for p in self.projects]
        self.proj_dropdown.set_model(Gtk.StringList.new(proj_names))

        active_proj = self.prefill.get("project", "General")
        for i, p in enumerate(self.projects):
            if p.name.lower() == active_proj.lower():
                self.proj_dropdown.set_selected(i)
                break

        proj_box.append(lbl_p)
        proj_box.append(self.proj_dropdown)
        row_proj.append(proj_box)

        # Linked Task Dropdown
        task_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        task_box.set_hexpand(True)
        lbl_task = Gtk.Label(label="Link / Complete Task")
        lbl_task.add_css_class("text-muted")
        lbl_task.set_halign(Gtk.Align.START)

        self.pending_tasks = [t for t in self.storage.get_tasks() if t.status != "done"]
        task_names = ["(None / Free activity)"] + [f"✓ {t.title[:28]}..." if len(t.title) > 28 else f"✓ {t.title}" for t in self.pending_tasks]
        self.task_dropdown = Gtk.DropDown()
        self.task_dropdown.set_model(Gtk.StringList.new(task_names))
        self.task_dropdown.connect("notify::selected", self._on_task_selected)

        task_box.append(lbl_task)
        task_box.append(self.task_dropdown)
        row_proj.append(task_box)

        # Time range & Duration
        row_time = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        vbox.append(row_time)

        # Start Time
        st_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        st_box.set_hexpand(True)
        lbl_st = Gtk.Label(label="Start Time (HH:MM)")
        lbl_st.add_css_class("text-muted")
        lbl_st.set_halign(Gtk.Align.START)
        self.start_entry = Gtk.Entry()
        self.start_entry.set_text(self.prefill.get("start_time", datetime.now().strftime("%H:%M")))
        self.start_entry.connect("activate", self._on_save)
        st_box.append(lbl_st)
        st_box.append(self.start_entry)
        row_time.append(st_box)

        # Duration
        dur_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        dur_box.set_hexpand(True)
        lbl_d = Gtk.Label(label="Duration (minutes)")
        lbl_d.add_css_class("text-muted")
        lbl_d.set_halign(Gtk.Align.START)
        self.dur_entry = Gtk.Entry()
        self.dur_entry.set_text(str(self.prefill.get("duration_minutes", 30)))
        self.dur_entry.connect("activate", self._on_save)
        dur_box.append(lbl_d)
        dur_box.append(self.dur_entry)
        row_time.append(dur_box)

        # Description / Notes
        desc_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_desc = Gtk.Label(label="Notes / Summary for Obsidian")
        lbl_desc.add_css_class("text-muted")
        lbl_desc.set_halign(Gtk.Align.START)
        self.desc_entry = Gtk.Entry()
        self.desc_entry.set_placeholder_text("What did you learn or accomplish?")
        if "description" in self.prefill:
            self.desc_entry.set_text(self.prefill["description"])
        self.desc_entry.connect("activate", self._on_save)
        desc_box.append(lbl_desc)
        desc_box.append(self.desc_entry)
        vbox.append(desc_box)

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(12)
        vbox.append(btn_box)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.add_css_class("btn-secondary")
        cancel_btn.connect("clicked", lambda b: self.close())
        btn_box.append(cancel_btn)

        save_btn = Gtk.Button(label="Update Journal Entry" if self.edit_entry else "Save to Journal")
        save_btn.add_css_class("btn-primary")
        save_btn.connect("clicked", self._on_save)
        btn_box.append(save_btn)

    def _on_task_selected(self, dropdown, param):
        idx = dropdown.get_selected()
        if idx > 0 and idx - 1 < len(self.pending_tasks):
            task = self.pending_tasks[idx - 1]
            if not self.title_entry.get_text().strip():
                self.title_entry.set_text(task.title)
            # Select project if matches
            for i, p in enumerate(self.projects):
                if p.name == task.project:
                    self.proj_dropdown.set_selected(i)
                    break

    def _on_save(self, *args):
        title = self.title_entry.get_text().strip()
        if not title:
            return

        sel_idx = self.proj_dropdown.get_selected()
        selected_proj = self.projects[sel_idx] if sel_idx < len(self.projects) else None
        proj_name = selected_proj.name if selected_proj else "General"

        start_time = self.start_entry.get_text().strip()
        dur_str = self.dur_entry.get_text().strip()
        dur = int(dur_str) if dur_str.isdigit() else 30
        desc = self.desc_entry.get_text().strip()

        # Check if a task is linked & complete it
        task_idx = self.task_dropdown.get_selected()
        linked_task = None
        if task_idx > 0 and task_idx - 1 < len(self.pending_tasks):
            linked_task = self.pending_tasks[task_idx - 1]
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            self.storage.update_task(linked_task.id, status="done", completed_at=now_str)
            if not desc:
                desc = f"Completed task: {linked_task.title}"
            else:
                desc = f"{desc} (Completed task: {linked_task.title})"

        # Calculate end time
        end_time = ""
        try:
            sh, sm = map(int, start_time.split(":"))
            total_m = sh * 60 + sm + dur
            end_time = f"{(total_m // 60) % 24:02d}:{total_m % 60:02d}"
        except Exception:
            pass

        if self.edit_entry:
            entry = JournalEntry(
                id=self.edit_entry.id,
                date=self.edit_entry.date,
                start_time=start_time,
                end_time=end_time,
                duration_minutes=dur,
                project=proj_name,
                title=title,
                description=desc,
                source=self.prefill.get("source", self.edit_entry.source),
                linked_task_id=linked_task.id if linked_task else self.edit_entry.linked_task_id
            )
            self.storage.update_journal_entry(self.edit_entry.date, self.edit_entry.id, entry)
        else:
            entry = JournalEntry(
                date=datetime.now().strftime("%Y-%m-%d"),
                start_time=start_time,
                end_time=end_time,
                duration_minutes=dur,
                project=proj_name,
                title=title,
                description=desc,
                source=self.prefill.get("source", "manual"),
                linked_task_id=linked_task.id if linked_task else None
            )
            self.storage.save_journal_entry(entry)

        if self.on_saved_cb:
            self.on_saved_cb()
        self.close()


class ManageProjectsDialog(Gtk.Window):
    """
    Project Manager:
    Create, edit, and organize projects with monochrome symbols and descriptions.
    """
    def __init__(self, parent, storage, on_changed_cb):
        super().__init__(transient_for=parent, modal=True)
        self.storage = storage
        self.on_changed_cb = on_changed_cb
        self.selected_project = None

        self.set_title("Manage Projects")
        self.set_default_size(580, 460)
        self.add_css_class("card-box")

        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_margin_top(18)
        vbox.set_margin_bottom(18)
        vbox.set_margin_start(22)
        vbox.set_margin_end(22)
        self.set_child(vbox)

        # Header
        top_h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        lbl_h = Gtk.Label(label="Projects & Contexts")
        lbl_h.add_css_class("text-heading")
        top_h.append(lbl_h)

        top_h.append(Gtk.Box(hexpand=True))

        new_btn = Gtk.Button(label="+ New Project")
        new_btn.add_css_class("btn-primary")
        new_btn.connect("clicked", self._on_new_project_click)
        top_h.append(new_btn)
        vbox.append(top_h)

        # 2-column pane: Left list, Right edit form
        paned = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        paned.set_vexpand(True)
        vbox.append(paned)

        # Left list
        left_scrolled = Gtk.ScrolledWindow()
        left_scrolled.set_size_request(210, -1)
        left_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.proj_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        left_scrolled.set_child(self.proj_list_box)
        paned.append(left_scrolled)

        # Right edit form
        self.form_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.form_box.set_hexpand(True)
        self.form_box.add_css_class("card-box-accent")

        lbl_edit = Gtk.Label(label="Project Details")
        lbl_edit.add_css_class("text-title")
        lbl_edit.set_halign(Gtk.Align.START)
        self.form_box.append(lbl_edit)

        # Name
        name_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_n = Gtk.Label(label="Project Name")
        lbl_n.add_css_class("text-muted")
        lbl_n.set_halign(Gtk.Align.START)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_placeholder_text("e.g. LedTrix, Fluids, Thesis...")
        name_box.append(lbl_n)
        name_box.append(self.name_entry)
        self.form_box.append(name_box)

        # Symbol dropdown
        sym_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_s = Gtk.Label(label="Monochrome Symbol")
        lbl_s.add_css_class("text-muted")
        lbl_s.set_halign(Gtk.Align.START)
        self.sym_dropdown = Gtk.DropDown()
        self.symbols = ["●", "◈", "■", "▲", "◆", "○", "▪", "▫", "★", "⊞", "≡"]
        self.sym_dropdown.set_model(Gtk.StringList.new(self.symbols))
        sym_box.append(lbl_s)
        sym_box.append(self.sym_dropdown)
        self.form_box.append(sym_box)

        # Description
        desc_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_d = Gtk.Label(label="Description / Goals")
        lbl_d.add_css_class("text-muted")
        lbl_d.set_halign(Gtk.Align.START)
        self.desc_entry = Gtk.Entry()
        self.desc_entry.set_placeholder_text("Brief description or scope")
        desc_box.append(lbl_d)
        desc_box.append(self.desc_entry)
        self.form_box.append(desc_box)

        # Form action buttons
        act_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        act_box.set_margin_top(10)

        self.delete_btn = Gtk.Button(label="Delete")
        self.delete_btn.add_css_class("btn-danger")
        self.delete_btn.connect("clicked", self._on_delete_project)
        act_box.append(self.delete_btn)

        act_box.append(Gtk.Box(hexpand=True))

        save_p_btn = Gtk.Button(label="Save Project")
        save_p_btn.add_css_class("btn-primary")
        save_p_btn.connect("clicked", self._on_save_project)
        act_box.append(save_p_btn)
        self.form_box.append(act_box)

        paned.append(self.form_box)

        # Close button at bottom
        close_btn = Gtk.Button(label="Close")
        close_btn.add_css_class("btn-secondary")
        close_btn.set_halign(Gtk.Align.END)
        close_btn.connect("clicked", lambda b: self.close())
        vbox.append(close_btn)

    def _refresh_list(self):
        while child := self.proj_list_box.get_first_child():
            self.proj_list_box.remove(child)

        projects = self.storage.get_projects()
        for p in projects:
            row_btn = Gtk.Button()
            row_btn.add_css_class("nav-button")
            
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            icon_lbl = Gtk.Label(label=p.icon)
            name_lbl = Gtk.Label(label=p.name)
            name_lbl.add_css_class("text-title")
            box.append(icon_lbl)
            box.append(name_lbl)
            row_btn.set_child(box)

            row_btn.connect("clicked", lambda b, proj=p: self._select_project(proj))
            self.proj_list_box.append(row_btn)

        if projects and not self.selected_project:
            self._select_project(projects[0])

    def _select_project(self, project: Project):
        self.selected_project = project
        self.name_entry.set_text(project.name)
        self.desc_entry.set_text(project.description or "")
        sym = project.icon or "●"
        if sym in self.symbols:
            self.sym_dropdown.set_selected(self.symbols.index(sym))
        else:
            self.sym_dropdown.set_selected(0)
        self.delete_btn.set_sensitive(project.name != "General")

    def _on_new_project_click(self, btn):
        self.selected_project = None
        self.name_entry.set_text("")
        self.desc_entry.set_text("")
        self.sym_dropdown.set_selected(0)
        self.delete_btn.set_sensitive(False)
        self.name_entry.grab_focus()

    def _on_save_project(self, btn):
        name = self.name_entry.get_text().strip()
        if not name:
            return

        sym_idx = self.sym_dropdown.get_selected()
        symbol = self.symbols[sym_idx] if sym_idx < len(self.symbols) else "●"
        desc = self.desc_entry.get_text().strip()

        if self.selected_project:
            old_name = self.selected_project.name
            self.storage.update_project(old_name, name, symbol, desc)
        else:
            self.storage.add_project(name, symbol, desc)

        self._refresh_list()
        if self.on_changed_cb:
            self.on_changed_cb()

    def _on_delete_project(self, btn):
        if self.selected_project and self.selected_project.name != "General":
            self.storage.delete_project(self.selected_project.name)
            self.selected_project = None
            self._refresh_list()
            if self.on_changed_cb:
                self.on_changed_cb()


class WorkGoalsDialog(Gtk.Window):
    """
    Configures daily work target hours (e.g. 7h daily) and daily break target (e.g. 30min).
    Apple-style clean modal dialog.
    """
    def __init__(self, parent, storage, on_saved_cb, current_date_str: str = None):
        super().__init__(transient_for=parent, modal=True)
        self.storage = storage
        self.on_saved_cb = on_saved_cb
        self.current_date_str = current_date_str or datetime.now().strftime("%Y-%m-%d")

        self.set_title("Set Daily Work & Break Goals")
        self.set_default_size(440, 360)
        self.add_css_class("card-box")

        self._build_ui()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        vbox.set_margin_start(24)
        vbox.set_margin_end(24)
        self.set_child(vbox)

        # Header
        lbl_h = Gtk.Label(label="Daily Work & Break Goals")
        lbl_h.add_css_class("text-heading")
        lbl_h.set_halign(Gtk.Align.START)
        vbox.append(lbl_h)

        lbl_sub = Gtk.Label(label="Configure your daily workday target and break budget. The break time is included inside your workday hours and subtracts from the total work needed.")
        lbl_sub.add_css_class("text-muted")
        lbl_sub.set_halign(Gtk.Align.START)
        lbl_sub.set_wrap(True)
        vbox.append(lbl_sub)

        # Current values
        settings = self.storage.get_settings()
        recon = self.storage.get_daily_reconciliation(self.current_date_str)

        cur_work_total = recon.target_work_minutes
        cur_h = cur_work_total // 60
        cur_m = cur_work_total % 60
        cur_break = recon.target_break_minutes

        # Work Target Row
        work_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        lbl_w = Gtk.Label(label="Daily Work Target")
        lbl_w.add_css_class("text-title")
        lbl_w.set_halign(Gtk.Align.START)
        work_box.append(lbl_w)

        row_w = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        lbl_hours = Gtk.Label(label="Hours:")
        lbl_hours.add_css_class("text-muted")
        row_w.append(lbl_hours)

        self.hours_spin = Gtk.SpinButton.new_with_range(1, 24, 1)
        self.hours_spin.set_value(cur_h)
        row_w.append(self.hours_spin)

        lbl_mins = Gtk.Label(label="Minutes:")
        lbl_mins.add_css_class("text-muted")
        lbl_mins.set_margin_start(8)
        row_w.append(lbl_mins)

        self.mins_spin = Gtk.SpinButton.new_with_range(0, 55, 5)
        self.mins_spin.set_value(cur_m)
        row_w.append(self.mins_spin)

        work_box.append(row_w)
        vbox.append(work_box)

        # Break Target Row
        break_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        lbl_b = Gtk.Label(label="Daily Break Allowance (included inside workday target):")
        lbl_b.add_css_class("text-title")
        lbl_b.set_halign(Gtk.Align.START)
        break_box.append(lbl_b)

        row_b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_bm = Gtk.Label(label="Break Minutes:")
        lbl_bm.add_css_class("text-muted")
        row_b.append(lbl_bm)

        self.break_spin = Gtk.SpinButton.new_with_range(0, 180, 5)
        self.break_spin.set_value(cur_break)
        row_b.append(self.break_spin)
        break_box.append(row_b)
        vbox.append(break_box)

        # Break Project selector
        bp_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_bp_g = Gtk.Label(label="Designated Break Project (auto-counts towards break):")
        lbl_bp_g.add_css_class("text-muted")
        lbl_bp_g.set_halign(Gtk.Align.START)
        bp_box.append(lbl_bp_g)

        self.goals_projects = self.storage.get_projects()
        p_names = [f"{p.icon} {p.name}" for p in self.goals_projects]
        self.goals_bp_dropdown = Gtk.DropDown()
        self.goals_bp_dropdown.set_model(Gtk.StringList.new(p_names))
        cur_bp = self.storage.get_break_project_name()
        for i, p in enumerate(self.goals_projects):
            if p.name == cur_bp:
                self.goals_bp_dropdown.set_selected(i)
                break
        bp_box.append(self.goals_bp_dropdown)
        vbox.append(bp_box)

        # Checkbox: Set as default for future days
        self.chk_default = Gtk.CheckButton(label="Save as default target for future days")
        self.chk_default.set_active(True)
        vbox.append(self.chk_default)

        # Spacer
        vbox.append(Gtk.Box(vexpand=True))

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_halign(Gtk.Align.END)
        vbox.append(btn_box)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.add_css_class("btn-secondary")
        cancel_btn.connect("clicked", lambda b: self.close())
        btn_box.append(cancel_btn)

        save_btn = Gtk.Button(label="Save Goals")
        save_btn.add_css_class("btn-primary")
        save_btn.connect("clicked", self._on_save)
        btn_box.append(save_btn)

    def _on_save(self, btn):
        h = int(self.hours_spin.get_value())
        m = int(self.mins_spin.get_value())
        total_work = h * 60 + m
        total_break = int(self.break_spin.get_value())

        # Update break project
        sel_idx = self.goals_bp_dropdown.get_selected()
        if 0 <= sel_idx < len(self.goals_projects):
            self.storage.set_break_project_name(self.goals_projects[sel_idx].name)

        # Update settings if default
        if self.chk_default.get_active():
            settings = self.storage.get_settings()
            settings["daily_work_target_minutes"] = total_work
            settings["daily_break_target_minutes"] = total_break
            self.storage.save_settings(settings)

        # Update reconciliation for date
        recon = self.storage.get_daily_reconciliation(self.current_date_str)
        recon.target_work_minutes = total_work
        recon.target_break_minutes = total_break
        self.storage.save_daily_reconciliation(recon)

        if self.on_saved_cb:
            self.on_saved_cb()
        self.close()


class SettingsDialog(Gtk.Window):
    """
    Preferences and module customization dialog for open source deployment.
    Allows enabling/disabling Windows & Tabs watcher, AI Reports,
    setting default daily work targets, and managing privacy/noise filters.
    """
    def __init__(self, parent, storage, on_saved_cb=None):
        super().__init__(transient_for=parent, modal=True)
        self.storage = storage
        self.on_saved_cb = on_saved_cb

        self.set_title("Preferences & Module Configuration")
        self.set_default_size(520, 580)
        self.add_css_class("card-box")

        self._build_ui()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        vbox.set_margin_start(24)
        vbox.set_margin_end(24)
        self.set_child(vbox)

        # Header
        top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        h_lbl = Gtk.Label(label="Preferences & Modules")
        h_lbl.add_css_class("text-heading")
        h_lbl.set_halign(Gtk.Align.START)
        s_lbl = Gtk.Label(label="Customize active features, daily targets, and privacy filters for your workflow.")
        s_lbl.add_css_class("text-muted")
        s_lbl.set_halign(Gtk.Align.START)
        top.append(h_lbl)
        top.append(s_lbl)
        vbox.append(top)

        settings = self.storage.get_settings()

        # Section 1: Modules Customization
        sec1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sec1.add_css_class("card-box-accent")

        lbl_sec1 = Gtk.Label(label="FEATURE MODULES")
        lbl_sec1.add_css_class("text-muted")
        lbl_sec1.set_halign(Gtk.Align.START)
        sec1.append(lbl_sec1)

        # Switch 1: Windows & Tabs Tracker
        row_w = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        info_w = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_w.set_hexpand(True)
        lbl_w1 = Gtk.Label(label="Windows & Tabs Tracker (Activity Session)")
        lbl_w1.add_css_class("text-title")
        lbl_w1.set_halign(Gtk.Align.START)
        lbl_w2 = Gtk.Label(label="Monitor open Firefox tabs and active window titles. Uncheck to disable background tracking.")
        lbl_w2.add_css_class("text-muted")
        lbl_w2.set_halign(Gtk.Align.START)
        lbl_w2.set_wrap(True)
        info_w.append(lbl_w1)
        info_w.append(lbl_w2)
        row_w.append(info_w)

        self.switch_watcher = Gtk.Switch()
        self.switch_watcher.set_active(settings.get("enable_watcher", True))
        self.switch_watcher.set_valign(Gtk.Align.CENTER)
        row_w.append(self.switch_watcher)
        sec1.append(row_w)

        # Switch 2: AI Reports & Analytics
        row_r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        info_r = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_r.set_hexpand(True)
        lbl_r1 = Gtk.Label(label="Reports & Analytics (AI Manager)")
        lbl_r1.add_css_class("text-title")
        lbl_r1.set_halign(Gtk.Align.START)
        lbl_r2 = Gtk.Label(label="Work compliance metrics, project distribution charts, and Markdown retrospectives.")
        lbl_r2.add_css_class("text-muted")
        lbl_r2.set_halign(Gtk.Align.START)
        lbl_r2.set_wrap(True)
        info_r.append(lbl_r1)
        info_r.append(lbl_r2)
        row_r.append(info_r)

        self.switch_reports = Gtk.Switch()
        self.switch_reports.set_active(settings.get("enable_reports", True))
        self.switch_reports.set_valign(Gtk.Align.CENTER)
        row_r.append(self.switch_reports)
        sec1.append(row_r)

        vbox.append(sec1)

        # Section 2: Daily Work Targets
        sec2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sec2.add_css_class("card-box-accent")
        lbl_sec2 = Gtk.Label(label="DAILY WORK TARGETS (DEFAULT)")
        lbl_sec2.add_css_class("text-muted")
        lbl_sec2.set_halign(Gtk.Align.START)
        sec2.append(lbl_sec2)

        targets_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)

        # Work hours
        w_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_tw = Gtk.Label(label="Daily Work Goal:")
        lbl_tw.add_css_class("text-muted")
        lbl_tw.set_halign(Gtk.Align.START)
        w_box.append(lbl_tw)
        spins_w = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        total_w = settings.get("daily_work_target_minutes", 420)
        self.spin_wh = Gtk.SpinButton.new_with_range(1, 24, 1)
        self.spin_wh.set_value(total_w // 60)
        self.spin_wm = Gtk.SpinButton.new_with_range(0, 59, 5)
        self.spin_wm.set_value(total_w % 60)
        spins_w.append(self.spin_wh)
        spins_w.append(Gtk.Label(label="h"))
        spins_w.append(self.spin_wm)
        spins_w.append(Gtk.Label(label="m"))
        w_box.append(spins_w)
        targets_row.append(w_box)

        # Break
        b_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_tb = Gtk.Label(label="Daily Break Budget:")
        lbl_tb.add_css_class("text-muted")
        lbl_tb.set_halign(Gtk.Align.START)
        b_box.append(lbl_tb)
        spins_b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.spin_bm = Gtk.SpinButton.new_with_range(0, 180, 5)
        self.spin_bm.set_value(settings.get("daily_break_target_minutes", 30))
        spins_b.append(self.spin_bm)
        spins_b.append(Gtk.Label(label="minutes"))
        b_box.append(spins_b)
        targets_row.append(b_box)

        sec2.append(targets_row)

        # Break Project Selector
        bp_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_bp_s = Gtk.Label(label="Designated Break Project:")
        lbl_bp_s.add_css_class("text-muted")
        lbl_bp_s.set_halign(Gtk.Align.START)
        bp_row.append(lbl_bp_s)

        self.dropdown_bp = Gtk.DropDown()
        self.settings_projects = self.storage.get_projects()
        p_names = [f"{p.icon} {p.name}" for p in self.settings_projects]
        self.dropdown_bp.set_model(Gtk.StringList.new(p_names))
        cur_bp = self.storage.get_break_project_name()
        for i, p in enumerate(self.settings_projects):
            if p.name == cur_bp:
                self.dropdown_bp.set_selected(i)
                break
        bp_row.append(self.dropdown_bp)
        sec2.append(bp_row)
        vbox.append(sec2)

        # Section 3: Privacy & Noise Filter
        sec3 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sec3.add_css_class("card-box-accent")
        lbl_sec3 = Gtk.Label(label="PRIVACY & SYSTEM NOISE FILTERS")
        lbl_sec3.add_css_class("text-muted")
        lbl_sec3.set_halign(Gtk.Align.START)
        sec3.append(lbl_sec3)

        row_f = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        lbl_f = Gtk.Label(label="Ignore sessions shorter than:")
        lbl_f.add_css_class("text-title")
        row_f.append(lbl_f)
        self.spin_thresh = Gtk.SpinButton.new_with_range(10, 300, 10)
        self.spin_thresh.set_value(settings.get("watcher_min_duration_seconds", 60))
        row_f.append(self.spin_thresh)
        row_f.append(Gtk.Label(label="seconds (filters out micro switches)"))
        sec3.append(row_f)

        ign_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_ign = Gtk.Label(label="Ignored App and Window Tokens (comma-separated):")
        lbl_ign.add_css_class("text-muted")
        lbl_ign.set_halign(Gtk.Align.START)
        ign_box.append(lbl_ign)
        self.ign_entry = Gtk.Entry()
        self.ign_entry.set_text(settings.get("ignored_apps", "antigravity, main.py, agy, taumer, trazos, xprop, subagent"))
        ign_box.append(self.ign_entry)
        sec3.append(ign_box)

        # Purge button
        purge_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_purge = Gtk.Button(label="Purge Noise & Micro Sessions from History")
        btn_purge.add_css_class("btn-secondary")
        self.lbl_purge_status = Gtk.Label(label="")
        self.lbl_purge_status.add_css_class("text-muted")
        btn_purge.connect("clicked", self._on_purge_noise)
        purge_row.append(btn_purge)
        purge_row.append(self.lbl_purge_status)
        sec3.append(purge_row)

        vbox.append(sec3)

        # Action Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(10)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.add_css_class("btn-secondary")
        cancel_btn.connect("clicked", lambda b: self.close())
        btn_box.append(cancel_btn)

        save_btn = Gtk.Button(label="Save Preferences")
        save_btn.add_css_class("btn-primary")
        save_btn.connect("clicked", self._on_save_preferences)
        btn_box.append(save_btn)

        vbox.append(btn_box)

    def _on_purge_noise(self, btn):
        import sqlite3
        from config import LOCAL_DB_FILE
        try:
            conn = sqlite3.connect(LOCAL_DB_FILE)
            c = conn.cursor()
            c.execute("""
                DELETE FROM window_events 
                WHERE duration_seconds < 60
                   OR LOWER(app) IN ('main.py', 'antigravity', 'taumer', 'trazos', 'agy', 'xprop', 'unknown', 'subagent')
                   OR LOWER(title) LIKE '%antigravity%'
                   OR LOWER(title) LIKE '%main.py%'
                   OR LOWER(title) LIKE '%taumer%'
                   OR LOWER(title) LIKE '%trazos%'
            """)
            deleted = c.rowcount
            conn.commit()
            conn.close()
            self.lbl_purge_status.set_text(f"Purged {deleted} noise sessions ✓")
        except Exception as e:
            self.lbl_purge_status.set_text(f"Error purging: {e}")

    def _on_save_preferences(self, btn):
        settings = self.storage.get_settings()
        settings["enable_watcher"] = self.switch_watcher.get_active()
        settings["enable_reports"] = self.switch_reports.get_active()
        settings["daily_work_target_minutes"] = int(self.spin_wh.get_value()) * 60 + int(self.spin_wm.get_value())
        settings["daily_break_target_minutes"] = int(self.spin_bm.get_value())
        sel_bp_idx = self.dropdown_bp.get_selected()
        if 0 <= sel_bp_idx < len(self.settings_projects):
            settings["break_project_name"] = self.settings_projects[sel_bp_idx].name
        settings["watcher_min_duration_seconds"] = int(self.spin_thresh.get_value())
        settings["ignored_apps"] = self.ign_entry.get_text().strip()
        self.storage.save_settings(settings)

        if self.on_saved_cb:
            self.on_saved_cb()
        self.close()


class EditWorkdayDialog(Gtk.Window):
    def __init__(self, parent, storage, date_str: str, on_saved_cb):
        super().__init__(transient_for=parent, modal=True)
        self.storage = storage
        self.date_str = date_str
        self.on_saved_cb = on_saved_cb

        self.set_title("Edit Workday Attendance")
        self.set_default_size(400, 360)
        self.add_css_class("card-box")

        self.recon = self.storage.get_daily_reconciliation(self.date_str)
        self._build_ui()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        vbox.set_margin_top(18)
        vbox.set_margin_bottom(18)
        vbox.set_margin_start(22)
        vbox.set_margin_end(22)
        self.set_child(vbox)

        # Header
        top_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lbl_h = Gtk.Label(label="Workday Attendance")
        lbl_h.add_css_class("text-heading")
        lbl_h.set_halign(Gtk.Align.START)
        top_box.append(lbl_h)

        try:
            dt = datetime.strptime(self.date_str, "%Y-%m-%d")
            d_str = dt.strftime("%A, %B %d, %Y")
        except Exception:
            d_str = self.date_str

        lbl_sub = Gtk.Label(label=f"Date: {d_str}")
        lbl_sub.add_css_class("text-muted")
        lbl_sub.set_halign(Gtk.Align.START)
        top_box.append(lbl_sub)
        vbox.append(top_box)

        # Arrival field
        arr_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        lbl_arr = Gtk.Label(label="Arrival Time (Check-In)")
        lbl_arr.add_css_class("text-title")
        lbl_arr.set_halign(Gtk.Align.START)
        arr_box.append(lbl_arr)

        arr_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.entry_arr = Gtk.Entry()
        self.entry_arr.set_placeholder_text("08:30")
        self.entry_arr.set_text(self.recon.arrival_time or "")
        self.entry_arr.set_size_request(130, -1)
        arr_row.append(self.entry_arr)

        btn_arr_now = Gtk.Button(label="Now")
        btn_arr_now.add_css_class("btn-secondary")
        btn_arr_now.connect("clicked", lambda b: self.entry_arr.set_text(datetime.now().strftime("%H:%M")))
        arr_row.append(btn_arr_now)

        btn_arr_clear = Gtk.Button(label="Clear")
        btn_arr_clear.add_css_class("btn-secondary")
        btn_arr_clear.connect("clicked", lambda b: self.entry_arr.set_text(""))
        arr_row.append(btn_arr_clear)

        arr_box.append(arr_row)
        vbox.append(arr_box)

        # Departure field
        dep_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        lbl_dep = Gtk.Label(label="Departure Time (Check-Out)")
        lbl_dep.add_css_class("text-title")
        lbl_dep.set_halign(Gtk.Align.START)
        dep_box.append(lbl_dep)

        dep_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.entry_dep = Gtk.Entry()
        self.entry_dep.set_placeholder_text("17:00")
        self.entry_dep.set_text(self.recon.departure_time or "")
        self.entry_dep.set_size_request(130, -1)
        dep_row.append(self.entry_dep)

        btn_dep_now = Gtk.Button(label="Now")
        btn_dep_now.add_css_class("btn-secondary")
        btn_dep_now.connect("clicked", lambda b: self.entry_dep.set_text(datetime.now().strftime("%H:%M")))
        dep_row.append(btn_dep_now)

        btn_dep_clear = Gtk.Button(label="Clear")
        btn_dep_clear.add_css_class("btn-secondary")
        btn_dep_clear.connect("clicked", lambda b: self.entry_dep.set_text(""))
        dep_row.append(btn_dep_clear)

        dep_box.append(dep_row)
        vbox.append(dep_box)

        # Hint / calculation info
        hint_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        target_h = self.recon.target_work_minutes // 60
        target_m = self.recon.target_work_minutes % 60
        lbl_hint = Gtk.Label(label=f"Daily Target: {target_h}h {target_m:02d}m (incl. {self.recon.target_break_minutes}m break)")
        lbl_hint.add_css_class("text-muted")
        lbl_hint.set_halign(Gtk.Align.START)
        hint_box.append(lbl_hint)
        vbox.append(hint_box)

        # Status / error label
        self.lbl_error = Gtk.Label(label="")
        self.lbl_error.add_css_class("text-muted")
        self.lbl_error.set_halign(Gtk.Align.START)
        vbox.append(self.lbl_error)

        vbox.append(Gtk.Box(vexpand=True))

        # Bottom buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_clear_all = Gtk.Button(label="Clear Both")
        btn_clear_all.add_css_class("btn-secondary")
        btn_clear_all.connect("clicked", self._on_clear_both)
        btn_box.append(btn_clear_all)

        btn_box.append(Gtk.Box(hexpand=True))

        btn_cancel = Gtk.Button(label="Cancel")
        btn_cancel.add_css_class("btn-secondary")
        btn_cancel.connect("clicked", lambda b: self.close())
        btn_box.append(btn_cancel)

        btn_save = Gtk.Button(label="Save Attendance")
        btn_save.add_css_class("btn-primary")
        btn_save.connect("clicked", self._on_save)
        btn_box.append(btn_save)

        vbox.append(btn_box)

    def _on_clear_both(self, btn):
        self.entry_arr.set_text("")
        self.entry_dep.set_text("")

    def _on_save(self, btn):
        arr = self.entry_arr.get_text().strip()
        dep = self.entry_dep.get_text().strip()

        for val, name in [(arr, "Arrival"), (dep, "Departure")]:
            if val:
                try:
                    parts = val.split(":")
                    if len(parts) != 2:
                        raise ValueError()
                    h, m = int(parts[0]), int(parts[1])
                    if not (0 <= h <= 23 and 0 <= m <= 59):
                        raise ValueError()
                except Exception:
                    self.lbl_error.set_text(f"Invalid format for {name}. Use HH:MM (e.g. 08:30)")
                    return

        self.recon.arrival_time = arr if arr else None
        self.recon.departure_time = dep if dep else None
        self.storage.save_daily_reconciliation(self.recon)

        if self.on_saved_cb:
            self.on_saved_cb()
        self.close()
