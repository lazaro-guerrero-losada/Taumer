"""
Journal View: Retrospective activity logger, task linking/completion,
live stopwatch with project selection, and Daily Work Target Reconciliation Compiler.
Tracks convergence to 0h, break compliance (under/over), and untracked time balance.
Engineered following Apple Human Interface Guidelines and UX laws.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from datetime import datetime, timedelta
import subprocess

from models import JournalEntry, Task, DailyReconciliation
from ui.dialogs import NewJournalEntryDialog, WorkGoalsDialog

class JournalView(Gtk.Box):
    def __init__(self, storage):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.storage = storage
        self.current_mode = "retro"  # "retro" or "live"
        self.timer_running = False
        self.timer_seconds = 0
        self.timer_id = None
        self.timer_start_dt = None
        self._cached_live_title = ""
        self._cached_live_proj = "General"

        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(22)
        self.set_margin_end(22)

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # 1. Top Header Bar: Title, Total Time Badge, Open in Obsidian
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lbl_title = Gtk.Label(label="Activity Journal")
        lbl_title.add_css_class("text-heading")
        lbl_title.set_halign(Gtk.Align.START)
        self.total_time_lbl = Gtk.Label(label="Today's Total: 0h 0m")
        self.total_time_lbl.add_css_class("tag-pill")
        self.total_time_lbl.set_halign(Gtk.Align.START)
        title_box.append(lbl_title)
        title_box.append(self.total_time_lbl)
        top_bar.append(title_box)

        top_bar.append(Gtk.Box(hexpand=True))

        obsidian_btn = Gtk.Button(label="Open in Obsidian")
        obsidian_btn.add_css_class("btn-secondary")
        obsidian_btn.connect("clicked", self._open_in_obsidian)
        top_bar.append(obsidian_btn)

        self.append(top_bar)

        # 2. Daily Work Target & Time Balance Reconciliation Card
        self.recon_card = self._build_reconciliation_card()
        self.append(self.recon_card)

        # 3. Left-aligned Folder-Tab Switcher (Apple segmented folder style)
        tab_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        tab_row.set_halign(Gtk.Align.START)

        self.folder_tabs = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.folder_tabs.add_css_class("folder-tabs-bar")

        self.btn_mode_retro = Gtk.Button(label="Log Activity")
        self.btn_mode_retro.add_css_class("folder-tab")
        self.btn_mode_retro.add_css_class("active")
        self.btn_mode_retro.connect("clicked", lambda b: self._switch_entry_mode("retro"))
        self.folder_tabs.append(self.btn_mode_retro)

        self.btn_mode_live = Gtk.Button(label="Live Timer")
        self.btn_mode_live.add_css_class("folder-tab")
        self.btn_mode_live.connect("clicked", lambda b: self._switch_entry_mode("live"))
        self.folder_tabs.append(self.btn_mode_live)

        tab_row.append(self.folder_tabs)
        self.append(tab_row)

        # 4. Dynamic Input Container (Compact, restrained width)
        self.input_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.input_container.set_halign(Gtk.Align.START)
        self.append(self.input_container)

        self._build_retrospective_form()
        self._build_live_timer_form()
        self._switch_entry_mode("retro")

        # 5. Feed Header of Today's Activities
        feed_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        feed_header.set_margin_top(8)

        lbl_f = Gtk.Label(label="Today's Logged Activities")
        lbl_f.add_css_class("text-title")
        feed_header.append(lbl_f)

        self.entries_count_lbl = Gtk.Label(label="0 entries")
        self.entries_count_lbl.add_css_class("tag-pill")
        feed_header.append(self.entries_count_lbl)
        self.append(feed_header)

        # 6. Scrolled feed
        self.feed_scrolled = Gtk.ScrolledWindow()
        self.feed_scrolled.set_vexpand(True)
        self.feed_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.feed_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.feed_scrolled.set_child(self.feed_box)
        self.append(self.feed_scrolled)

    def _build_reconciliation_card(self) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card-box")

        # Top line: Title + Subtitle + Set Goals button
        top_h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        icon_lbl = Gtk.Label(label="◷")
        icon_lbl.add_css_class("text-heading")
        top_h.append(icon_lbl)

        title_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        h_title = Gtk.Label(label="Daily Work Target & Time Balance Compiler")
        h_title.add_css_class("text-title")
        h_title.set_halign(Gtk.Align.START)
        h_sub = Gtk.Label(label="Hours converge to 0h • Break compliance • Untracked time gap balance")
        h_sub.add_css_class("text-muted")
        h_sub.set_halign(Gtk.Align.START)
        title_vbox.append(h_title)
        title_vbox.append(h_sub)
        top_h.append(title_vbox)

        top_h.append(Gtk.Box(hexpand=True))

        goals_btn = Gtk.Button(label="⚙ Set Goals")
        goals_btn.add_css_class("btn-secondary")
        goals_btn.connect("clicked", self._open_work_goals_dialog)
        top_h.append(goals_btn)

        card.append(top_h)

        # 4-Column KPI row
        kpi_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        kpi_row.set_hexpand(True)

        # Col 1: Daily Target
        col1 = self._create_recon_stat_column("Target Goal", "7h 00m", "Configured work target")
        self.target_goal_lbl = col1._val_lbl
        self.target_sub_lbl = col1._sub_lbl
        kpi_row.append(col1)

        # Col 2: Effective Worked
        col2 = self._create_recon_stat_column("Effective Worked", "0h 00m", "0m logged + 0m balance")
        self.effective_worked_lbl = col2._val_lbl
        self.effective_sub_lbl = col2._sub_lbl
        kpi_row.append(col2)

        # Col 3: Convergence to 0 (Remaining)
        col3 = self._create_recon_stat_column("Remaining to Goal", "7h 00m left", "Target converging to 0h")
        self.remaining_goal_lbl = col3._val_lbl
        self.remaining_sub_lbl = col3._sub_lbl
        kpi_row.append(col3)

        # Col 4: Break Time Tracker
        col4 = self._create_recon_stat_column("Break Time", "0m / 30m", "30m under budget")
        self.break_time_lbl = col4._val_lbl
        self.break_sub_lbl = col4._sub_lbl
        kpi_row.append(col4)

        card.append(kpi_row)

        # Progress bar
        self.goal_progress_bar = Gtk.ProgressBar()
        self.goal_progress_bar.set_fraction(0.0)
        card.append(self.goal_progress_bar)

        # Bottom Control Toolbar: Time Gap Balance Adjustment & Break Logger
        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        bottom_bar.set_margin_top(4)

        # --- Section 1: Untracked Time Balance (Gap Compensation) ---
        gap_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_g = Gtk.Label(label="Untracked Gap Balance:")
        lbl_g.add_css_class("text-muted")
        gap_box.append(lbl_g)

        self.gap_val_lbl = Gtk.Label(label="+0m")
        self.gap_val_lbl.add_css_class("tag-pill")
        gap_box.append(self.gap_val_lbl)

        # Quick gap buttons
        btn_g_m15 = Gtk.Button(label="-15m")
        btn_g_m15.add_css_class("btn-ghost")
        btn_g_m15.set_tooltip_text("Subtract 15 minutes of untracked time balance")
        btn_g_m15.connect("clicked", lambda b: self._adjust_gap(-15))
        gap_box.append(btn_g_m15)

        btn_g_zero = Gtk.Button(label="Reset (0)")
        btn_g_zero.add_css_class("btn-ghost")
        btn_g_zero.connect("clicked", lambda b: self._set_gap(0))
        gap_box.append(btn_g_zero)

        btn_g_p15 = Gtk.Button(label="+15m")
        btn_g_p15.add_css_class("btn-secondary")
        btn_g_p15.connect("clicked", lambda b: self._adjust_gap(15))
        gap_box.append(btn_g_p15)

        btn_g_p30 = Gtk.Button(label="+30m")
        btn_g_p30.add_css_class("btn-secondary")
        btn_g_p30.connect("clicked", lambda b: self._adjust_gap(30))
        gap_box.append(btn_g_p30)

        btn_g_p45 = Gtk.Button(label="+45m")
        btn_g_p45.add_css_class("btn-secondary")
        btn_g_p45.connect("clicked", lambda b: self._adjust_gap(45))
        gap_box.append(btn_g_p45)

        btn_g_p60 = Gtk.Button(label="+60m")
        btn_g_p60.add_css_class("btn-secondary")
        btn_g_p60.connect("clicked", lambda b: self._adjust_gap(60))
        gap_box.append(btn_g_p60)

        bottom_bar.append(gap_box)

        bottom_bar.append(Gtk.Box(hexpand=True))

        # --- Section 2: Break Project Selector & Quick Add ---
        break_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_bp = Gtk.Label(label="Break Project:")
        lbl_bp.add_css_class("text-muted")
        break_box.append(lbl_bp)

        self.break_proj_dropdown = Gtk.DropDown()
        self.break_proj_dropdown.connect("notify::selected", self._on_break_proj_selected)
        break_box.append(self.break_proj_dropdown)

        lbl_bk = Gtk.Label(label="Quick Add:")
        lbl_bk.add_css_class("text-muted")
        lbl_bk.set_margin_start(4)
        break_box.append(lbl_bk)

        btn_b_10 = Gtk.Button(label="+10m")
        btn_b_10.add_css_class("btn-secondary")
        btn_b_10.connect("clicked", lambda b: self._add_break(10))
        break_box.append(btn_b_10)

        btn_b_15 = Gtk.Button(label="+15m")
        btn_b_15.add_css_class("btn-secondary")
        btn_b_15.connect("clicked", lambda b: self._add_break(15))
        break_box.append(btn_b_15)

        btn_b_30 = Gtk.Button(label="+30m")
        btn_b_30.add_css_class("btn-secondary")
        btn_b_30.connect("clicked", lambda b: self._add_break(30))
        break_box.append(btn_b_30)

        btn_b_reset = Gtk.Button(label="Reset")
        btn_b_reset.add_css_class("btn-ghost")
        btn_b_reset.set_tooltip_text("Reset today's manual break time adjustment to 0")
        btn_b_reset.connect("clicked", lambda b: self._reset_break())
        break_box.append(btn_b_reset)

        bottom_bar.append(break_box)

        card.append(bottom_bar)
        return card

    def _create_recon_stat_column(self, title: str, main_val: str, sub_val: str) -> Gtk.Widget:
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.set_hexpand(True)

        lbl_t = Gtk.Label(label=title)
        lbl_t.add_css_class("text-muted")
        lbl_t.set_halign(Gtk.Align.START)
        col.append(lbl_t)

        lbl_v = Gtk.Label(label=main_val)
        lbl_v.add_css_class("text-heading")
        lbl_v.set_halign(Gtk.Align.START)
        col.append(lbl_v)

        lbl_s = Gtk.Label(label=sub_val)
        lbl_s.add_css_class("text-muted")
        lbl_s.set_halign(Gtk.Align.START)
        col.append(lbl_s)

        col._val_lbl = lbl_v
        col._sub_lbl = lbl_s
        return col

    def _open_work_goals_dialog(self, btn):
        win = self.get_root()
        today_str = datetime.now().strftime("%Y-%m-%d")
        dlg = WorkGoalsDialog(win, self.storage, self.refresh, current_date_str=today_str)
        dlg.present()

    def _adjust_gap(self, delta_m: int):
        today_str = datetime.now().strftime("%Y-%m-%d")
        recon = self.storage.get_daily_reconciliation(today_str)
        recon.gap_adjustment_minutes += delta_m
        self.storage.save_daily_reconciliation(recon)
        self.refresh()

    def _set_gap(self, val_m: int):
        today_str = datetime.now().strftime("%Y-%m-%d")
        recon = self.storage.get_daily_reconciliation(today_str)
        recon.gap_adjustment_minutes = val_m
        self.storage.save_daily_reconciliation(recon)
        self.refresh()

    def _on_break_proj_selected(self, dropdown, param):
        if getattr(self, "_updating_break_dropdown", False):
            return
        idx = dropdown.get_selected()
        projects = self.storage.get_projects()
        if 0 <= idx < len(projects):
            sel_name = projects[idx].name
            if sel_name != self.storage.get_break_project_name():
                self.storage.set_break_project_name(sel_name)
                self.refresh()

    def _add_break(self, mins: int):
        today_str = datetime.now().strftime("%Y-%m-%d")
        recon = self.storage.get_daily_reconciliation(today_str)
        recon.break_minutes += mins
        self.storage.save_daily_reconciliation(recon)
        self.refresh()

    def _reset_break(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        recon = self.storage.get_daily_reconciliation(today_str)
        recon.break_minutes = 0
        self.storage.save_daily_reconciliation(recon)
        self.refresh()

    def _toggle_entry_work(self, entry_id: str, is_work: bool):
        today_str = datetime.now().strftime("%Y-%m-%d")
        recon = self.storage.get_daily_reconciliation(today_str)
        if is_work:
            if entry_id in recon.excluded_entry_ids:
                recon.excluded_entry_ids.remove(entry_id)
        else:
            if entry_id not in recon.excluded_entry_ids:
                recon.excluded_entry_ids.append(entry_id)
        self.storage.save_daily_reconciliation(recon)
        self.refresh()

    def _build_retrospective_form(self):
        # Constrained card width for comfortable desktop view
        self.retro_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.retro_card.add_css_class("card-box")

        # Row 1: Title (340px) + Project Dropdown + Duration (65px) + Save Button
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.retro_title_entry = Gtk.Entry()
        self.retro_title_entry.set_size_request(340, -1)
        self.retro_title_entry.set_placeholder_text("What did you work on? (Press Enter to log)")
        self.retro_title_entry.connect("activate", self._on_enter_pressed)
        row1.append(self.retro_title_entry)

        self.retro_proj_dropdown = Gtk.DropDown()
        row1.append(self.retro_proj_dropdown)

        lbl_d = Gtk.Label(label="Mins:")
        lbl_d.add_css_class("text-muted")
        row1.append(lbl_d)

        self.retro_dur_entry = Gtk.Entry()
        self.retro_dur_entry.set_text("45")
        self.retro_dur_entry.set_size_request(60, -1)
        self.retro_dur_entry.connect("activate", self._on_enter_pressed)
        row1.append(self.retro_dur_entry)

        save_btn = Gtk.Button(label="Log Activity")
        save_btn.add_css_class("btn-primary")
        save_btn.connect("clicked", self._save_retrospective_log)
        row1.append(save_btn)

        self.retro_card.append(row1)

        # Row 2: Link Task Dropdown (260px) + Notes entry (340px)
        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.retro_task_dropdown = Gtk.DropDown()
        self.retro_task_dropdown.set_size_request(260, -1)
        self.retro_task_dropdown.connect("notify::selected", self._on_retro_task_selected)
        row2.append(self.retro_task_dropdown)

        self.retro_notes_entry = Gtk.Entry()
        self.retro_notes_entry.set_size_request(380, -1)
        self.retro_notes_entry.set_placeholder_text("Key notes or Obsidian links [[...]] (optional, press Enter)")
        self.retro_notes_entry.connect("activate", self._on_enter_pressed)
        row2.append(self.retro_notes_entry)

        self.retro_card.append(row2)

    def _build_live_timer_form(self):
        # Compact, ergonomically grouped stopwatch interface (Fitts's Law)
        self.live_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.live_card.add_css_class("card-box-accent")

        # Concept title (280px)
        self.live_concept_entry = Gtk.Entry()
        self.live_concept_entry.set_size_request(280, -1)
        self.live_concept_entry.set_placeholder_text("What are you working on right now?")
        self.live_concept_entry.connect("activate", lambda e: self._toggle_timer(None))
        self.live_concept_entry.connect("changed", self._on_live_concept_changed)
        self.live_card.append(self.live_concept_entry)

        # Project dropdown for live timer
        self.live_proj_dropdown = Gtk.DropDown()
        self.live_proj_dropdown.connect("notify::selected", self._on_live_proj_selected)
        self.live_card.append(self.live_proj_dropdown)

        # Big stopwatch counter readout
        self.stopwatch_lbl = Gtk.Label(label="00:00:00")
        self.stopwatch_lbl.add_css_class("text-heading")
        self.stopwatch_lbl.add_css_class("text-mono")
        self.stopwatch_lbl.set_margin_start(10)
        self.stopwatch_lbl.set_margin_end(10)
        self.live_card.append(self.stopwatch_lbl)

        # Primary action button: Start / Pause
        self.start_timer_btn = Gtk.Button(label="Start")
        self.start_timer_btn.add_css_class("btn-primary")
        self.start_timer_btn.connect("clicked", self._toggle_timer)
        self.live_card.append(self.start_timer_btn)

        # Secondary action button: Save Session
        self.save_timer_btn = Gtk.Button(label="Save Session")
        self.save_timer_btn.add_css_class("btn-secondary")
        self.save_timer_btn.set_sensitive(False)
        self.save_timer_btn.connect("clicked", self._save_live_session)
        self.live_card.append(self.save_timer_btn)

        # Discard / Delete timer session button
        self.delete_timer_btn = Gtk.Button(label="✕")
        self.delete_timer_btn.add_css_class("btn-secondary")
        self.delete_timer_btn.set_sensitive(False)
        self.delete_timer_btn.set_tooltip_text("Discard timer session")
        self.delete_timer_btn.connect("clicked", self._discard_live_session)
        self.live_card.append(self.delete_timer_btn)

    def _switch_entry_mode(self, mode: str):
        self.current_mode = mode
        while child := self.input_container.get_first_child():
            self.input_container.remove(child)

        if mode == "retro":
            self.btn_mode_retro.add_css_class("active")
            self.btn_mode_live.remove_css_class("active")
            self.input_container.append(self.retro_card)
        else:
            self.btn_mode_live.add_css_class("active")
            self.btn_mode_retro.remove_css_class("active")
            self.input_container.append(self.live_card)

    def _on_enter_pressed(self, entry):
        self._save_retrospective_log(None)

    def _on_retro_task_selected(self, dropdown, param):
        idx = dropdown.get_selected()
        if idx > 0 and idx - 1 < len(self.pending_tasks):
            t = self.pending_tasks[idx - 1]
            if not self.retro_title_entry.get_text().strip():
                self.retro_title_entry.set_text(t.title)
            # Match project
            for i, p in enumerate(self.storage.get_projects()):
                if p.name == t.project:
                    self.retro_proj_dropdown.set_selected(i)
                    break

    def _save_retrospective_log(self, btn):
        title = self.retro_title_entry.get_text().strip()
        if not title:
            return

        sel_idx = self.retro_proj_dropdown.get_selected()
        projects = self.storage.get_projects()
        proj = projects[sel_idx] if sel_idx < len(projects) else None
        proj_name = proj.name if proj else "General"

        dur_text = self.retro_dur_entry.get_text().strip()
        duration_mins = int(dur_text) if dur_text.isdigit() else 30
        notes = self.retro_notes_entry.get_text().strip()

        # Check if task linked and complete it
        task_idx = self.retro_task_dropdown.get_selected()
        linked_task = None
        if task_idx > 0 and task_idx - 1 < len(self.pending_tasks):
            linked_task = self.pending_tasks[task_idx - 1]
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            self.storage.update_task(linked_task.id, status="done", completed_at=now_str)
            if notes:
                notes = f"{notes} — Completed task: {linked_task.title}"
            else:
                notes = f"Completed task: {linked_task.title}"

        now = datetime.now()
        start_dt = now - timedelta(minutes=duration_mins)
        start_str = start_dt.strftime("%H:%M")
        end_str = now.strftime("%H:%M")

        entry = JournalEntry(
            date=now.strftime("%Y-%m-%d"),
            start_time=start_str,
            end_time=end_str,
            duration_minutes=duration_mins,
            project=proj_name,
            title=title,
            description=notes,
            source="manual",
            linked_task_id=linked_task.id if linked_task else None
        )
        self.storage.save_journal_entry(entry)

        # Clear form and refocus
        self.retro_title_entry.set_text("")
        self.retro_notes_entry.set_text("")
        self.retro_task_dropdown.set_selected(0)
        self.retro_title_entry.grab_focus()

        self.refresh()

    def _on_live_concept_changed(self, entry):
        self._cached_live_title = entry.get_text()

    def _on_live_proj_selected(self, dropdown, param):
        idx = dropdown.get_selected()
        projects = self.storage.get_projects()
        if idx < len(projects):
            self._cached_live_proj = projects[idx].name

    def start_focus_with_task(self, task: Task):
        current_title = ""
        try:
            current_title = self.live_concept_entry.get_text().strip()
        except Exception:
            pass

        if current_title and current_title == task.title.strip():
            self._switch_entry_mode("live")
            if not self.timer_running:
                self._toggle_timer(None)
            return

        # Auto-save any ongoing active session first so no time is lost
        if self.timer_running or self.timer_seconds > 0:
            self._save_live_session(btn=None)

        self._switch_entry_mode("live")
        self.live_concept_entry.set_text(task.title)
        self._cached_live_title = task.title
        projects = self.storage.get_projects()
        for i, p in enumerate(projects):
            if p.name == task.project:
                self.live_proj_dropdown.set_selected(i)
                self._cached_live_proj = p.name
                break
        if not self.timer_running:
            self._toggle_timer(None)

    def _resume_entry(self, entry: JournalEntry):
        """Resume tracking a previously logged journal entry in the live stopwatch."""
        current_title = ""
        try:
            current_title = self.live_concept_entry.get_text().strip()
        except Exception:
            pass

        # If already running for this exact entry, switch to live view and continue
        if current_title and current_title == (entry.title or "").strip():
            self._switch_entry_mode("live")
            if not self.timer_running:
                self._toggle_timer(None)
            return

        # Auto-save any other active session before switching
        if self.timer_running or self.timer_seconds > 0:
            self._save_live_session(btn=None)

        self._switch_entry_mode("live")
        self.live_concept_entry.set_text(entry.title or "")
        self._cached_live_title = entry.title or ""

        projects = self.storage.get_projects()
        found = False
        for i, p in enumerate(projects):
            if p.name == entry.project:
                self.live_proj_dropdown.set_selected(i)
                self._cached_live_proj = p.name
                found = True
                break
        if not found and len(projects) > 0:
            self.live_proj_dropdown.set_selected(0)
            self._cached_live_proj = projects[0].name

        # Reset timer counter and start immediately
        self.timer_seconds = 0
        self.stopwatch_lbl.set_text("00:00:00")
        if not self.timer_running:
            self._toggle_timer(None)

    def save_timer_if_active(self):
        """Silently auto-saves any active or running live timer session without prompts (e.g. on app exit)."""
        if not (self.timer_running or self.timer_seconds > 0):
            return
        try:
            self._save_live_session(btn=None)
        except Exception as e:
            print(f"Error auto-saving live session on exit: {e}")

    def _toggle_timer(self, btn):
        if not self.timer_running:
            self.timer_running = True
            self.timer_start_dt = datetime.now()
            self.start_timer_btn.set_label("Pause")
            self.save_timer_btn.set_sensitive(True)
            self.delete_timer_btn.set_sensitive(True)
            self.timer_id = GLib.timeout_add_seconds(1, self._on_timer_tick)
        else:
            self.timer_running = False
            self.start_timer_btn.set_label("Resume")
            if self.timer_id:
                GLib.source_remove(self.timer_id)
                self.timer_id = None

    def _discard_live_session(self, btn):
        if self.timer_id:
            GLib.source_remove(self.timer_id)
            self.timer_id = None
        self.timer_running = False
        self.timer_seconds = 0
        self.timer_start_dt = None
        self._cached_live_title = ""
        self.stopwatch_lbl.set_text("00:00:00")
        self.start_timer_btn.set_label("Start")
        self.save_timer_btn.set_sensitive(False)
        self.delete_timer_btn.set_sensitive(False)
        self.live_concept_entry.set_text("")

    def _on_timer_tick(self):
        if not self.timer_running:
            return False
        self.timer_seconds += 1
        h = self.timer_seconds // 3600
        m = (self.timer_seconds % 3600) // 60
        s = self.timer_seconds % 60
        self.stopwatch_lbl.set_text(f"{h:02d}:{m:02d}:{s:02d}")
        return True

    def _save_live_session(self, btn=None):
        if not (self.timer_running or self.timer_seconds > 0):
            return

        title = ""
        try:
            if hasattr(self, "live_concept_entry"):
                title = self.live_concept_entry.get_text().strip()
        except Exception:
            pass
        if not title:
            title = getattr(self, "_cached_live_title", "").strip() or "Focus session"

        proj_name = "General"
        try:
            if hasattr(self, "live_proj_dropdown"):
                sel_idx = self.live_proj_dropdown.get_selected()
                projects = self.storage.get_projects()
                if sel_idx < len(projects):
                    proj_name = projects[sel_idx].name
        except Exception:
            proj_name = getattr(self, "_cached_live_proj", "General") or "General"

        duration_mins = max(1, round(self.timer_seconds / 60))
        now = datetime.now()
        if self.timer_start_dt and self.timer_running and (now - self.timer_start_dt).total_seconds() >= self.timer_seconds:
            start_str = self.timer_start_dt.strftime("%H:%M")
        else:
            start_dt = now - timedelta(minutes=duration_mins)
            start_str = start_dt.strftime("%H:%M")
        end_str = now.strftime("%H:%M")
        if start_str == end_str and duration_mins >= 1:
            start_dt = now - timedelta(minutes=duration_mins)
            start_str = start_dt.strftime("%H:%M")

        entry = JournalEntry(
            date=now.strftime("%Y-%m-%d"),
            start_time=start_str,
            end_time=end_str,
            duration_minutes=duration_mins,
            project=proj_name,
            title=title,
            description="Live focus session",
            source="timer"
        )
        self.storage.save_journal_entry(entry)

        if self.timer_id:
            try:
                GLib.source_remove(self.timer_id)
            except Exception:
                pass
            self.timer_id = None
        self.timer_running = False
        self.timer_seconds = 0
        self.timer_start_dt = None
        self._cached_live_title = ""

        try:
            self.stopwatch_lbl.set_text("00:00:00")
            self.start_timer_btn.set_label("Start")
            self.save_timer_btn.set_sensitive(False)
            self.delete_timer_btn.set_sensitive(False)
            self.live_concept_entry.set_text("")
            self.refresh()
        except Exception:
            pass

    def _open_in_obsidian(self, btn):
        date_str = datetime.now().strftime("%Y-%m-%d")
        file_path = self.storage.get_journal_file_path(date_str)
        if not file_path.exists():
            self.storage._write_journal_md(date_str, [])
        try:
            subprocess.Popen(["xdg-open", str(file_path)])
        except Exception:
            pass

    def refresh(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        entries = self.storage.load_journal_entries_for_date(today_str)
        recon = self.storage.get_daily_reconciliation(today_str)
        break_project = self.storage.get_break_project_name()

        total_m = sum(e.duration_minutes for e in entries)
        hours = total_m // 60
        mins = total_m % 60
        self.total_time_lbl.set_text(f"Today's Total: {hours}h {mins}m")
        self.entries_count_lbl.set_text(f"{len(entries)} entries")

        # --- Update Reconciliation Dashboard Metrics ---
        effective_m = recon.calculate_effective_work_minutes(entries, break_project)
        credited_break_m = recon.calculate_credited_break_minutes(entries, break_project)
        remaining_m = recon.calculate_remaining_minutes(entries, break_project)
        total_break_m = recon.calculate_total_break_minutes(entries, break_project)
        break_diff_m = recon.calculate_break_difference_minutes(entries, break_project)

        target_h = recon.target_work_minutes // 60
        target_mins = recon.target_work_minutes % 60
        self.target_goal_lbl.set_text(f"{target_h}h {target_mins:02d}m")
        self.target_sub_lbl.set_text(f"Daily target (incl. {recon.target_break_minutes}m break)")

        eff_h = effective_m // 60
        eff_mins = effective_m % 60
        self.effective_worked_lbl.set_text(f"{eff_h}h {eff_mins:02d}m")

        break_names = {"break", "descanso"}
        if break_project:
            break_names.add(break_project.strip().lower())

        raw_work_m = sum(e.duration_minutes for e in entries if e.id not in recon.excluded_entry_ids and (not e.project or e.project.strip().lower() not in break_names))
        self.effective_sub_lbl.set_text(f"{raw_work_m // 60}h {raw_work_m % 60:02d}m tasks + {recon.gap_adjustment_minutes}m gap")

        # Goal convergence towards 0h (break time restas from total work needed)
        if remaining_m > 0:
            rem_h = remaining_m // 60
            rem_mins = remaining_m % 60
            self.remaining_goal_lbl.set_text(f"{rem_h}h {rem_mins:02d}m left")
            self.remaining_sub_lbl.set_text("Target converging to 0h")
        else:
            overtime_m = abs(remaining_m)
            ot_h = overtime_m // 60
            ot_mins = overtime_m % 60
            self.remaining_goal_lbl.set_text("✓ Goal Reached!")
            self.remaining_sub_lbl.set_text(f"+{ot_h}h {ot_mins:02d}m Overtime")

        # Break time status (logged + manual)
        self.break_time_lbl.set_text(f"{total_break_m}m / {recon.target_break_minutes}m")
        logged_break_m = sum(e.duration_minutes for e in entries if e.project and e.project.strip().lower() in break_names)
        sub_parts = []
        if total_break_m > 0:
            sub_parts.append(f"{credited_break_m}m credited")
        if break_diff_m > 0:
            sub_parts.append(f"{break_diff_m}m over")
        elif break_diff_m < 0:
            sub_parts.append(f"{abs(break_diff_m)}m under")
        else:
            sub_parts.append("on budget")
        self.break_sub_lbl.set_text(" • ".join(sub_parts))

        # Progress bar (work + credited break inside target hours)
        total_accounted_m = effective_m + credited_break_m
        fraction = min(1.0, max(0.0, total_accounted_m / max(recon.target_work_minutes, 1)))
        self.goal_progress_bar.set_fraction(fraction)

        # Gap badge
        self.gap_val_lbl.set_text(f"{recon.gap_adjustment_minutes:+d}m")

        # Update dropdowns
        projects = self.storage.get_projects()
        p_names = [f"{p.icon} {p.name}" for p in projects]
        self.retro_proj_dropdown.set_model(Gtk.StringList.new(p_names))
        self.live_proj_dropdown.set_model(Gtk.StringList.new(p_names))

        # Update break project dropdown without re-triggering signal
        self._updating_break_dropdown = True
        self.break_proj_dropdown.set_model(Gtk.StringList.new(p_names))
        for i, p in enumerate(projects):
            if p.name == break_project:
                self.break_proj_dropdown.set_selected(i)
                break
        self._updating_break_dropdown = False

        self.pending_tasks = [t for t in self.storage.get_tasks() if t.status != "done" and getattr(t, "item_type", "task") != "event"]
        task_names = ["Link task: (None)"] + [f"Complete: {t.title[:30]}..." if len(t.title) > 30 else f"Complete: {t.title}" for t in self.pending_tasks]
        self.retro_task_dropdown.set_model(Gtk.StringList.new(task_names))

        # Clear feed
        while child := self.feed_box.get_first_child():
            self.feed_box.remove(child)

        if not entries:
            empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            empty_box.set_valign(Gtk.Align.CENTER)
            empty_box.set_margin_top(36)
            lbl_e = Gtk.Label(label="No activities logged today")
            lbl_e.add_css_class("text-heading")
            lbl_sub = Gtk.Label(label="Log what you've worked on above to reconcile with your 7h daily work goal.")
            lbl_sub.add_css_class("text-muted")
            empty_box.append(lbl_e)
            empty_box.append(lbl_sub)
            self.feed_box.append(empty_box)
            return

        for e in entries:
            card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            card.add_css_class("card-box")

            # Checkbox: Count as Work
            is_break = bool(e.project and e.project.strip().lower() in break_names)
            is_excluded = e.id in recon.excluded_entry_ids
            is_work = not is_excluded and not is_break

            work_chk = Gtk.CheckButton(label="Work")
            work_chk.set_active(is_work)
            if is_break:
                work_chk.set_tooltip_text(f"Activity under break project '{break_project}' (auto-credited to break time, not effective work)")
            else:
                work_chk.set_tooltip_text("Check to count towards effective work hours, uncheck to deduct")
            work_chk.connect("toggled", lambda b, eid=e.id: self._toggle_entry_work(eid, b.get_active()))
            card.append(work_chk)

            # Time range & Duration pill
            time_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            time_box.set_size_request(85, -1)
            time_str = f"{e.start_time} - {e.end_time}" if e.end_time else e.start_time
            t_lbl = Gtk.Label(label=time_str)
            t_lbl.add_css_class("text-mono")
            dur_pill = Gtk.Label(label=f"{e.duration_minutes}m")
            dur_pill.add_css_class("tag-pill")
            time_box.append(t_lbl)
            time_box.append(dur_pill)
            card.append(time_box)

            # Details
            details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            details_box.set_hexpand(True)

            tags_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            proj_icon = self.storage.get_project_icon(e.project)
            proj_lbl = Gtk.Label(label=f"{proj_icon} {e.project}")
            proj_lbl.add_css_class("tag-pill-project")
            tags_row.append(proj_lbl)

            if is_break:
                bk_badge = Gtk.Label(label="☕ Break Time")
                bk_badge.add_css_class("tag-pill-alert")
                tags_row.append(bk_badge)
            elif is_excluded:
                ex_badge = Gtk.Label(label="Excluded from Work Target")
                ex_badge.add_css_class("tag-pill")
                tags_row.append(ex_badge)

            details_box.append(tags_row)

            title_lbl = Gtk.Label(label=e.title)
            title_lbl.add_css_class("text-title")
            title_lbl.set_halign(Gtk.Align.START)
            if is_excluded:
                title_lbl.add_css_class("text-muted")
            details_box.append(title_lbl)

            if e.description:
                desc_lbl = Gtk.Label(label=e.description)
                desc_lbl.add_css_class("text-muted")
                desc_lbl.set_halign(Gtk.Align.START)
                details_box.append(desc_lbl)

            card.append(details_box)

            # Action buttons: Resume, Edit & Delete
            actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

            resume_btn = Gtk.Button(label="▶ Resume")
            resume_btn.add_css_class("btn-secondary")
            resume_btn.set_tooltip_text("Resume this activity in Live Timer")
            resume_btn.connect("clicked", lambda b, entry=e: self._resume_entry(entry))
            actions_box.append(resume_btn)

            edit_btn = Gtk.Button(label="Edit")
            edit_btn.add_css_class("btn-secondary")
            edit_btn.connect("clicked", lambda b, entry=e: self._edit_entry(entry))
            actions_box.append(edit_btn)

            del_btn = Gtk.Button(label="✕")
            del_btn.add_css_class("btn-ghost")
            del_btn.set_tooltip_text("Delete activity from journal")
            del_btn.connect("clicked", lambda b, entry=e: self._delete_entry(entry))
            actions_box.append(del_btn)

            card.append(actions_box)
            self.feed_box.append(card)

    def _edit_entry(self, entry: JournalEntry):
        win = self.get_root()
        dlg = NewJournalEntryDialog(win, self.storage, self.refresh, edit_entry=entry)
        dlg.present()

    def _delete_entry(self, entry: JournalEntry):
        today_str = datetime.now().strftime("%Y-%m-%d")
        self.storage.delete_journal_entry(today_str, entry.id, entry.start_time, entry.title)
        self.refresh()
