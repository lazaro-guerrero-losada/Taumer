"""
Journal View: Retrospective activity logger, task linking/completion,
live stopwatch with project selection, and Daily Work Target Reconciliation Compiler.
Tracks convergence to 0h, break compliance (under/over), and untracked time balance.
Engineered following Apple Human Interface Guidelines and UX laws.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo
import cairo
import math
from datetime import datetime, timedelta
import subprocess

from models import JournalEntry, Task, DailyReconciliation
from ui.dialogs import NewJournalEntryDialog, WorkGoalsDialog, NewTaskDialog, EditWorkdayDialog
from ui.calendar_view import format_minutes_to_time, parse_time_minutes

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

        # Day Timeline state
        self.top_card_mode = "reconciliation"
        self.timeline_mode = "compact"  # "compact" (default: colors only) or "expanded" (details)
        self.timeline_items = []
        self.timeline_gaps = []
        self.scale_start_m = 480  # 08:00
        self.scale_end_m = 1260   # 21:00 default minimum end
        self.is_dragging = False
        self.drag_action = None   # "draw", "move-task", "resize-left", "resize-right"
        self.active_drag_item = None
        self.drag_start_x = 0
        self.drag_cur_x = 0
        self.drag_start_offset_m = 0
        self.drag_has_moved = False
        self.orig_start_m = None
        self.orig_end_m = None
        self.orig_duration_m = None
        self.live_drag_start_m = None
        self.live_drag_end_m = None
        self.sel_start_m = None
        self.sel_end_m = None
        self.hover_x = -1
        self.hover_y = -1
        self.hover_m = None
        self.hover_edge = None    # None, "left", "right"
        self.hovered_item_id = None
        self.hovered_gap_idx = None
        self._timeline_popover = None

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

        # 2. Top Banner Card Stack: Daily Work Target Reconciliation <-> Day Activity Timeline
        self.top_cards_stack = Gtk.Stack()
        self.top_cards_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.top_cards_stack.set_transition_duration(250)

        self.recon_card = self._build_reconciliation_card()
        self.timeline_card = self._build_timeline_card()
        self.top_cards_stack.add_named(self.recon_card, "reconciliation")
        self.top_cards_stack.add_named(self.timeline_card, "timeline")
        self.append(self.top_cards_stack)

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

        # Top line: Title + Navigation Buttons (< and >) + Set Goals button
        top_h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        icon_lbl = Gtk.Label(label="◷")
        icon_lbl.add_css_class("text-heading")
        top_h.append(icon_lbl)

        h_title = Gtk.Label(label="Daily Work Target & Time Balance Compiler")
        h_title.add_css_class("text-title")
        h_title.set_halign(Gtk.Align.START)
        top_h.append(h_title)

        top_h.append(Gtk.Box(hexpand=True))

        # View switcher in Card 1: < and > buttons
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        nav_box.add_css_class("segmented-bar")

        btn_prev = Gtk.Button(label="<")
        btn_prev.add_css_class("segmented-btn")
        btn_prev.add_css_class("nav-chevron-btn")
        btn_prev.set_tooltip_text("Switch to Day Activity Timeline")
        btn_prev.connect("clicked", lambda b: self._switch_top_card("timeline"))

        btn_next = Gtk.Button(label=">")
        btn_next.add_css_class("segmented-btn")
        btn_next.add_css_class("nav-chevron-btn")
        btn_next.set_tooltip_text("Switch to Day Activity Timeline")
        btn_next.connect("clicked", lambda b: self._switch_top_card("timeline"))

        nav_box.append(btn_prev)
        nav_box.append(btn_next)
        top_h.append(nav_box)

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

        # Swipe gesture to switch to Day Timeline
        swipe1 = Gtk.GestureSwipe()
        def on_swipe_recon(g, vx, vy):
            if vx < -120:  # Fast swipe left -> Day Timeline
                self._switch_top_card("timeline")
        swipe1.connect("swipe", on_swipe_recon)
        card.add_controller(swipe1)

        return card

    def _switch_top_card(self, target: str):
        if self.top_card_mode == target:
            return
        if target == "timeline":
            self.top_cards_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
            self.top_card_mode = target
            self.top_cards_stack.set_visible_child_name("timeline")
            self._refresh_timeline()
        else:
            self.top_cards_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_RIGHT)
            self.top_card_mode = target
            self.top_cards_stack.set_visible_child_name("reconciliation")

    def _build_timeline_card(self) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("card-box")

        # Top line: Title + Navigation Buttons (< and >) + Workday Settings button
        top_h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        icon_lbl = Gtk.Label(label="▤")
        icon_lbl.add_css_class("text-heading")
        top_h.append(icon_lbl)

        h_title = Gtk.Label(label="Day Activity Timeline & Gap Analyzer")
        h_title.add_css_class("text-title")
        h_title.set_halign(Gtk.Align.START)
        top_h.append(h_title)

        top_h.append(Gtk.Box(hexpand=True))

        # View switcher in Card 2: < and > buttons
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        nav_box.add_css_class("segmented-bar")

        btn_prev = Gtk.Button(label="<")
        btn_prev.add_css_class("segmented-btn")
        btn_prev.add_css_class("nav-chevron-btn")
        btn_prev.set_tooltip_text("Switch to Goals & Balance")
        btn_prev.connect("clicked", lambda b: self._switch_top_card("reconciliation"))

        btn_next = Gtk.Button(label=">")
        btn_next.add_css_class("segmented-btn")
        btn_next.add_css_class("nav-chevron-btn")
        btn_next.set_tooltip_text("Switch to Goals & Balance")
        btn_next.connect("clicked", lambda b: self._switch_top_card("reconciliation"))

        nav_box.append(btn_prev)
        nav_box.append(btn_next)
        top_h.append(nav_box)

        self.timeline_workday_btn = Gtk.Button(label="⚙ Workday Hours")
        self.timeline_workday_btn.add_css_class("btn-secondary")
        self.timeline_workday_btn.connect("clicked", self._open_workday_dialog)
        top_h.append(self.timeline_workday_btn)

        card.append(top_h)

        # Stat pills & scale mode switcher row
        stats_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        stats_row.set_margin_top(1)

        self.tl_stat_logged = Gtk.Label(label="Logged: 0h 0m")
        self.tl_stat_logged.add_css_class("tag-pill-success")
        stats_row.append(self.tl_stat_logged)

        self.tl_stat_gaps = Gtk.Label(label="Gaps: 0m")
        self.tl_stat_gaps.add_css_class("tag-pill-gap")
        stats_row.append(self.tl_stat_gaps)

        stats_row.append(Gtk.Box(hexpand=True))

        # Single mode toggle button: "><" (minimal) vs "<>" (expanded)
        self.btn_timeline_toggle = Gtk.Button(label="><")
        self.btn_timeline_toggle.add_css_class("mode-toggle-btn")
        self.btn_timeline_toggle.set_tooltip_text("Expand timeline details (<>)")
        self.btn_timeline_toggle.connect("clicked", lambda b: self._toggle_timeline_mode())
        stats_row.append(self.btn_timeline_toggle)

        card.append(stats_row)

        # Timeline ScrolledWindow for horizontal sliding / responsiveness
        self.timeline_scrolled = Gtk.ScrolledWindow()
        self.timeline_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.timeline_scrolled.set_vexpand(False)
        self.timeline_scrolled.set_hexpand(True)

        # Timeline DrawingArea
        self.timeline_area = Gtk.DrawingArea()
        self.timeline_area.set_content_height(46)
        self.timeline_area.set_vexpand(False)
        self.timeline_area.set_hexpand(True)
        self.timeline_area.set_has_tooltip(True)
        self.timeline_area.set_draw_func(self._on_draw_timeline)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_timeline_drag_begin)
        drag.connect("drag-update", self._on_timeline_drag_update)
        drag.connect("drag-end", self._on_timeline_drag_end)
        self.timeline_area.add_controller(drag)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_timeline_motion)
        motion.connect("leave", self._on_timeline_leave)
        self.timeline_area.add_controller(motion)

        self.timeline_area.connect("query-tooltip", self._on_timeline_tooltip)

        self.timeline_scrolled.set_child(self.timeline_area)
        card.append(self.timeline_scrolled)

        # Bottom toolbar with quick action shortcuts, slide buttons, and legend
        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bottom_bar.set_margin_top(2)

        btn_new_act = Gtk.Button(label="+ Log Activity")
        btn_new_act.add_css_class("btn-secondary")
        btn_new_act.set_tooltip_text("Open Activity Logger modal")
        btn_new_act.connect("clicked", lambda b: self._open_new_activity_modal())
        bottom_bar.append(btn_new_act)

        btn_new_tsk = Gtk.Button(label="+ New Task")
        btn_new_tsk.add_css_class("btn-secondary")
        btn_new_tsk.set_tooltip_text("Schedule a new task for today")
        btn_new_tsk.connect("clicked", lambda b: self._open_new_task_modal())
        bottom_bar.append(btn_new_tsk)

        # Siding / sliding buttons
        btn_slide_l = Gtk.Button(label="◀ Slide")
        btn_slide_l.add_css_class("btn-ghost")
        btn_slide_l.set_tooltip_text("Slide earlier in the day")
        btn_slide_l.connect("clicked", lambda b: self._slide_timeline(-220))
        bottom_bar.append(btn_slide_l)

        btn_slide_r = Gtk.Button(label="Slide ▶")
        btn_slide_r.add_css_class("btn-ghost")
        btn_slide_r.set_tooltip_text("Slide later in the day (up to 21:00+)")
        btn_slide_r.connect("clicked", lambda b: self._slide_timeline(220))
        bottom_bar.append(btn_slide_r)

        bottom_bar.append(Gtk.Box(hexpand=True))

        leg_work = Gtk.Label(label="■ Work Activity")
        leg_work.add_css_class("tag-pill-success")
        bottom_bar.append(leg_work)

        leg_break = Gtk.Label(label="■ Break Time")
        leg_break.add_css_class("tag-pill-high")
        bottom_bar.append(leg_break)

        leg_gap = Gtk.Label(label="╍╍ Untracked Gap")
        leg_gap.add_css_class("tag-pill")
        bottom_bar.append(leg_gap)

        card.append(bottom_bar)

        # Swipe gesture on header and bottom bar of Card 2
        swipe2 = Gtk.GestureSwipe()
        def on_swipe_tl(g, vx, vy):
            if vx > 120:  # Fast swipe right -> back to reconciliation
                self._switch_top_card("reconciliation")
        swipe2.connect("swipe", on_swipe_tl)
        top_h.add_controller(swipe2)

        swipe3 = Gtk.GestureSwipe()
        swipe3.connect("swipe", on_swipe_tl)
        bottom_bar.add_controller(swipe3)

        return card

    def _toggle_timeline_mode(self):
        new_mode = "expanded" if self.timeline_mode == "compact" else "compact"
        self._set_timeline_mode(new_mode)

    def _set_timeline_mode(self, mode: str):
        if self.timeline_mode == mode:
            return
        self.timeline_mode = mode
        if mode == "compact":
            if hasattr(self, "btn_timeline_toggle"):
                self.btn_timeline_toggle.set_label("><")
                self.btn_timeline_toggle.set_tooltip_text("Expand timeline details (<>)")
            self.timeline_area.set_content_height(42)
        else:
            if hasattr(self, "btn_timeline_toggle"):
                self.btn_timeline_toggle.set_label("<>")
                self.btn_timeline_toggle.set_tooltip_text("Compress to minimal colors (><)")
            self.timeline_area.set_content_height(80)
            GLib.timeout_add(100, self._scroll_to_now)

        self._refresh_timeline()

    def _slide_timeline(self, delta: float):
        hadj = self.timeline_scrolled.get_hadjustment()
        if hadj:
            cur = hadj.get_value()
            page = hadj.get_page_size()
            max_v = max(hadj.get_lower(), hadj.get_upper() - page)
            new_v = max(hadj.get_lower(), min(max_v, cur + delta))
            hadj.set_value(new_v)

    def _scroll_to_now(self):
        hadj = self.timeline_scrolled.get_hadjustment()
        if not hadj:
            return False
        now = datetime.now()
        now_m = now.hour * 60 + now.minute
        now_x = self._minute_to_x(now_m)
        page = hadj.get_page_size()
        max_v = max(hadj.get_lower(), hadj.get_upper() - page)
        target = max(hadj.get_lower(), min(max_v, now_x - page / 2.0))
        hadj.set_value(target)
        return False

    def _open_workday_dialog(self, btn):
        win = self.get_root()
        today_str = datetime.now().strftime("%Y-%m-%d")
        dlg = EditWorkdayDialog(win, self.storage, today_str, self.refresh)
        dlg.present()

    def _open_new_activity_modal(self, prefill_start=None, prefill_dur=30):
        win = self.get_root()
        now_str = datetime.now().strftime("%H:%M")
        dlg = NewJournalEntryDialog(
            win,
            self.storage,
            self.refresh,
            prefill={
                "start_time": prefill_start or now_str,
                "duration_minutes": prefill_dur,
                "title": "",
                "project": "General"
            }
        )
        dlg.present()

    def _open_new_task_modal(self, prefill_start=None, prefill_dur=30):
        win = self.get_root()
        today_str = datetime.now().strftime("%Y-%m-%d")
        now_str = datetime.now().strftime("%H:%M")
        dlg = NewTaskDialog(
            win,
            self.storage,
            self.refresh,
            default_type="task",
            prefill_date=today_str,
            prefill_time=prefill_start or now_str,
            prefill_duration=prefill_dur
        )
        dlg.present()

    def _apply_item_time_change(self, item, new_start_m: int, new_end_m: int):
        new_dur = max(5, new_end_m - new_start_m)
        new_start_str = format_minutes_to_time(new_start_m)
        new_end_str = format_minutes_to_time(new_end_m)

        entry = item.get("entry")
        if entry:
            entry.start_time = new_start_str
            entry.end_time = new_end_str
            entry.duration_minutes = new_dur
            self.storage.update_journal_entry(entry.date, entry.id, entry)
            if entry.linked_task_id:
                self.storage.update_task(entry.linked_task_id, scheduled_time=new_start_str, scheduled_duration=new_dur)

        task = item.get("task")
        if task:
            self.storage.update_task(task.id, scheduled_time=new_start_str, scheduled_duration=new_dur)

        self.refresh()

    def _open_item_edit_modal(self, item):
        win = self.get_root()
        entry = item.get("entry")
        task = item.get("task")
        if entry:
            dlg = NewJournalEntryDialog(win, self.storage, self.refresh, edit_entry=entry)
            dlg.present()
        elif task:
            today_str = datetime.now().strftime("%Y-%m-%d")
            dlg = NewTaskDialog(win, self.storage, self.refresh, edit_task=task, default_type="task", prefill_date=today_str)
            dlg.present()

    def _calculate_k_and_width(self):
        elapsed_minutes = max(30, self.scale_end_m - self.scale_start_m)
        elapsed_hours = elapsed_minutes / 60.0

        scrolled_w = self.timeline_scrolled.get_width() if hasattr(self, "timeline_scrolled") else 900
        if scrolled_w <= 100:
            scrolled_w = 900
        avail_w = max(350, scrolled_w - 28)

        k_ideal = avail_w / elapsed_hours

        if getattr(self, "timeline_mode", "compact") == "compact":
            # Minimal mode: only color blocks, no text labels
            k_min = 70.0
            k_max = 240.0
        else:
            # Expanded mode: wider to show full task titles and timestamps
            k_min = 150.0
            k_max = 340.0

        k = max(k_min, min(k_max, k_ideal))
        track_w = max(avail_w, int(elapsed_hours * k))
        content_w = track_w + 28
        return k, track_w, content_w

    def _get_track_rect(self, width, height):
        track_x = 14
        k, track_w, _ = self._calculate_k_and_width()
        actual_w = max(track_w, width - 28)
        if getattr(self, "timeline_mode", "compact") == "compact":
            track_y = 14
            track_h = max(22, height - 20)
        else:
            track_y = 18
            track_h = max(46, height - 24)
        return track_x, track_y, actual_w, track_h

    def _minute_to_x(self, m: int) -> float:
        w = self.timeline_area.get_width()
        h = self.timeline_area.get_height()
        track_x, track_y, track_w, track_h = self._get_track_rect(w, h)
        total = max(1, self.scale_end_m - self.scale_start_m)
        return track_x + (m - self.scale_start_m) / float(total) * track_w

    def _x_to_minute(self, x: float) -> int:
        w = self.timeline_area.get_width()
        h = self.timeline_area.get_height()
        track_x, track_y, track_w, track_h = self._get_track_rect(w, h)
        total = max(1, self.scale_end_m - self.scale_start_m)
        rel_x = max(0.0, min(1.0, (x - track_x) / float(track_w)))
        m = self.scale_start_m + rel_x * total
        snapped = int(round(m / 5.0) * 5)
        return max(self.scale_start_m, min(self.scale_end_m, snapped))

    def _refresh_timeline(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        entries = self.storage.load_journal_entries_for_date(today_str)
        recon = self.storage.get_daily_reconciliation(today_str)
        break_project = self.storage.get_break_project_name().strip().lower()
        break_names = {"break", "descanso"}
        if break_project:
            break_names.add(break_project)

        # 1. Parse items (both logged journal entries and today's scheduled tasks)
        self.timeline_items = []
        entry_starts = []
        entry_ends = []
        linked_task_ids = set()

        for e in entries:
            if e.linked_task_id:
                linked_task_ids.add(e.linked_task_id)
            sm = parse_time_minutes(e.start_time)
            if sm is None:
                continue
            dur = e.duration_minutes or 30
            em = sm + dur
            entry_starts.append(sm)
            entry_ends.append(em)
            is_break = bool(e.project and e.project.strip().lower() in break_names)
            self.timeline_items.append({
                "id": e.id,
                "title": e.title or "(Untitled)",
                "project": e.project or "General",
                "icon": e.icon or "●",
                "start_m": sm,
                "duration_m": dur,
                "end_m": em,
                "is_break": is_break,
                "is_task": False,
                "entry": e,
                "task": None
            })

        # Load scheduled tasks for today not yet logged as entries
        tasks = self.storage.get_tasks()
        for t in tasks:
            if t.id in linked_task_ids:
                continue
            if getattr(t, "scheduled_date", None) == today_str and getattr(t, "scheduled_time", None):
                sm = parse_time_minutes(t.scheduled_time)
                if sm is None:
                    continue
                dur = getattr(t, "scheduled_duration", None) or getattr(t, "estimated_minutes", None) or 30
                em = sm + dur
                entry_starts.append(sm)
                entry_ends.append(em)
                self.timeline_items.append({
                    "id": t.id,
                    "title": t.title or "(Untitled Task)",
                    "project": t.project or "General",
                    "icon": "⊞",
                    "start_m": sm,
                    "duration_m": dur,
                    "end_m": em,
                    "is_break": False,
                    "is_task": True,
                    "entry": None,
                    "task": t
                })

        self.timeline_items.sort(key=lambda it: it["start_m"])

        # 2. Determine Scale Start Minute: Exactly the Arrival Time
        arr_m = parse_time_minutes(recon.arrival_time) if recon.arrival_time else None
        if arr_m is not None:
            self.scale_start_m = arr_m
        elif entry_starts:
            self.scale_start_m = min(entry_starts)
        else:
            self.scale_start_m = 8 * 60  # 08:00 default fallback

        if entry_starts and min(entry_starts) < self.scale_start_m:
            self.scale_start_m = min(entry_starts)

        # 3. Determine Scale End Minute: Right limit is NOW (or latest logged/scheduled item)
        now = datetime.now()
        now_m = now.hour * 60 + now.minute
        last_entry_m = max(entry_ends, default=now_m)
        self.scale_end_m = max(now_m, last_entry_m)

        # Minimum span of at least 30 minutes
        if self.scale_end_m - self.scale_start_m < 30:
            self.scale_end_m = self.scale_start_m + 30

        # Adjust width dynamically based on k parameter and elapsed hours
        k, track_w, content_w = self._calculate_k_and_width()
        scrolled_w = self.timeline_scrolled.get_width() if hasattr(self, "timeline_scrolled") else 900
        if content_w > scrolled_w:
            self.timeline_area.set_content_width(content_w)
            self.timeline_area.set_hexpand(False)
        else:
            self.timeline_area.set_content_width(0)
            self.timeline_area.set_hexpand(True)

        # 4. Calculate Gaps
        self.timeline_gaps = []
        cur_m = self.scale_start_m
        limit_m = min(now_m, self.scale_end_m)

        for it in self.timeline_items:
            if it["start_m"] > cur_m and cur_m < limit_m:
                gap_end = min(it["start_m"], limit_m)
                if gap_end - cur_m >= 5:
                    self.timeline_gaps.append({
                        "start_m": cur_m,
                        "end_m": gap_end,
                        "duration_m": gap_end - cur_m
                    })
            cur_m = max(cur_m, it["end_m"])

        if cur_m < limit_m and limit_m - cur_m >= 5:
            self.timeline_gaps.append({
                "start_m": cur_m,
                "end_m": limit_m,
                "duration_m": limit_m - cur_m
            })

        # 5. Update Stat Badges (Only Logged and Gaps, as requested)
        total_logged_m = sum(it["duration_m"] for it in self.timeline_items if not it.get("is_task"))
        tl_h, tl_mins = total_logged_m // 60, total_logged_m % 60
        self.tl_stat_logged.set_text(f"Logged: {tl_h}h {tl_mins:02d}m")

        total_gap_m = sum(g["duration_m"] for g in self.timeline_gaps)
        tg_h, tg_mins = total_gap_m // 60, total_gap_m % 60
        gap_text = f"Gaps: {tg_h}h {tg_mins:02d}m" if tg_h > 0 else f"Gaps: {tg_mins}m"
        self.tl_stat_gaps.set_text(f"{gap_text}")

        if recon.arrival_time:
            arr_text = f"Workday: {recon.arrival_time}"
            if recon.departure_time:
                arr_text += f" – {recon.departure_time}"
            self.timeline_workday_btn.set_label(f"⚙ {arr_text}")
        else:
            self.timeline_workday_btn.set_label("⚙ Workday Hours")

        self.timeline_area.queue_draw()

    def _on_draw_timeline(self, area, cr, width, height):
        track_x, track_y, track_w, track_h = self._get_track_rect(width, height)
        total_span = max(1, self.scale_end_m - self.scale_start_m)

        def draw_rounded(x, y, w, h, r):
            r = min(r, w / 2.0, h / 2.0)
            cr.new_sub_path()
            cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
            cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
            cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
            cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
            cr.close_path()

        # 1. Base Track Groove
        draw_rounded(track_x, track_y, track_w, track_h, 7)
        cr.set_source_rgb(0.965, 0.965, 0.972)
        cr.fill_preserve()
        cr.set_source_rgb(0.886, 0.886, 0.906)
        cr.set_line_width(1.0)
        cr.stroke()

        # 2. Hour Ticks and Guidelines
        pango_desc = Pango.FontDescription("sans 8.5")

        now = datetime.now()
        now_m = now.hour * 60 + now.minute
        now_x = track_x + (now_m - self.scale_start_m) / float(total_span) * track_w

        # Start tick at arrival
        start_x = track_x
        cr.set_line_width(1.0)
        cr.move_to(start_x, track_y - 5)
        cr.line_to(start_x, track_y)
        cr.set_source_rgb(0.55, 0.60, 0.68)
        cr.stroke()

        start_lbl = format_minutes_to_time(self.scale_start_m)
        layout_s = PangoCairo.create_layout(cr)
        layout_s.set_font_description(pango_desc)
        layout_s.set_text(start_lbl, -1)
        _, s_log_r = layout_s.get_pixel_extents()
        cr.move_to(start_x - s_log_r.width / 2.0, 2)
        cr.set_source_rgb(0.42, 0.48, 0.56)
        PangoCairo.show_layout(cr, layout_s)

        first_h = (self.scale_start_m + 59) // 60
        last_h = self.scale_end_m // 60

        for h in range(first_h, last_h + 1):
            m = h * 60
            if m <= self.scale_start_m or m >= self.scale_end_m:
                continue
            x = track_x + (m - self.scale_start_m) / float(total_span) * track_w

            # Top tick
            cr.set_line_width(1.0)
            cr.move_to(x, track_y - 5)
            cr.line_to(x, track_y)
            cr.set_source_rgb(0.65, 0.70, 0.76)
            cr.stroke()

            # Subtle dashed vertical guideline inside track
            cr.set_dash([2, 4])
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.05)
            cr.move_to(x, track_y)
            cr.line_to(x, track_y + track_h)
            cr.stroke()
            cr.set_dash([])

            # Don't draw text label if it's too close to start_x or now_x
            if abs(x - start_x) >= 32 and abs(x - now_x) >= 32:
                layout = PangoCairo.create_layout(cr)
                layout.set_font_description(pango_desc)
                layout.set_text(f"{h:02d}:00", -1)
                ink, log_r = layout.get_pixel_extents()
                cr.move_to(x - log_r.width / 2.0, 2)
                cr.set_source_rgb(0.42, 0.48, 0.56)
                PangoCairo.show_layout(cr, layout)

            # Half-hour tick
            m_half = m + 30
            if self.scale_start_m <= m_half <= self.scale_end_m:
                hx = track_x + (m_half - self.scale_start_m) / float(total_span) * track_w
                if abs(hx - now_x) >= 15:
                    cr.move_to(hx, track_y - 3)
                    cr.line_to(hx, track_y)
                    cr.set_source_rgba(0.65, 0.70, 0.76, 0.6)
                    cr.stroke()

        # 4. Activities / Tasks
        is_compact = (getattr(self, "timeline_mode", "compact") == "compact")

        # 3. Untracked Gaps
        gap_pango = Pango.FontDescription("sans 8")
        for idx, g in enumerate(self.timeline_gaps):
            gx1 = track_x + (g["start_m"] - self.scale_start_m) / float(total_span) * track_w
            gx2 = track_x + (g["end_m"] - self.scale_start_m) / float(total_span) * track_w
            gw = max(2.0, gx2 - gx1)

            is_h = (self.hovered_gap_idx == idx)
            draw_rounded(gx1 + 1, track_y + 2, gw - 2, track_h - 4, 4 if is_compact else 5)
            if is_h:
                cr.set_source_rgba(0.28, 0.33, 0.41, 0.12)
            else:
                cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
            cr.fill_preserve()

            cr.set_dash([3, 3])
            if is_h:
                cr.set_source_rgba(0.28, 0.33, 0.41, 0.85)
                cr.set_line_width(1.5)
            else:
                cr.set_source_rgba(0.68, 0.72, 0.78, 0.80)
                cr.set_line_width(1.0)
            cr.stroke()
            cr.set_dash([])

            if not is_compact and gw >= 44 and g["duration_m"] >= 15:
                gl = PangoCairo.create_layout(cr)
                gl.set_font_description(gap_pango)
                gl.set_text(f"+{g['duration_m']}m gap", -1)
                ink, log_r = gl.get_pixel_extents()
                cr.move_to(gx1 + (gw - log_r.width) / 2.0, track_y + (track_h - log_r.height) / 2.0)
                cr.set_source_rgb(0.55, 0.62, 0.70)
                PangoCairo.show_layout(cr, gl)

        title_pango = Pango.FontDescription("sans bold 8.5")
        sub_pango = Pango.FontDescription("sans 7.5")

        for it in self.timeline_items:
            ax1 = track_x + (it["start_m"] - self.scale_start_m) / float(total_span) * track_w
            ax2 = track_x + (it["end_m"] - self.scale_start_m) / float(total_span) * track_w
            aw = max(14.0, ax2 - ax1)

            is_h = (self.hovered_item_id == it["id"])
            draw_rounded(ax1 + 1, track_y + 2, aw - 2, track_h - 4, 4 if is_compact else 5)

            if it["is_break"]:
                if is_h:
                    cr.set_source_rgb(0.95, 0.90, 0.92)
                else:
                    cr.set_source_rgb(0.97, 0.94, 0.95)
                cr.fill_preserve()
                if is_h:
                    cr.set_source_rgb(0.510, 0.400, 0.455)
                    cr.set_line_width(1.5)
                else:
                    cr.set_source_rgb(0.90, 0.82, 0.85)
                    cr.set_line_width(1.0)
                cr.stroke()
                text_r, text_g, text_b = 0.510, 0.400, 0.455
            elif it.get("is_task"):
                # Scheduled task (not yet logged)
                if is_h:
                    cr.set_source_rgb(0.90, 0.93, 0.97)
                else:
                    cr.set_source_rgb(0.94, 0.96, 0.98)
                cr.fill_preserve()
                if is_h:
                    cr.set_source_rgb(0.25, 0.35, 0.48)
                    cr.set_line_width(1.5)
                else:
                    cr.set_source_rgb(0.78, 0.84, 0.90)
                    cr.set_line_width(1.0)
                cr.stroke()
                text_r, text_g, text_b = 0.20, 0.30, 0.42
            else:
                # Regular logged work activity
                if is_h:
                    cr.set_source_rgb(0.91, 0.94, 0.90)
                else:
                    cr.set_source_rgb(0.94, 0.96, 0.94)
                cr.fill_preserve()
                if is_h:
                    cr.set_source_rgb(0.12, 0.16, 0.23)
                    cr.set_line_width(1.5)
                else:
                    cr.set_source_rgb(0.83, 0.87, 0.83)
                    cr.set_line_width(1.0)
                cr.stroke()
                text_r, text_g, text_b = 0.12, 0.16, 0.23

            # Compact mode: User requested NO task name inside blocks, pure clean colors
            if not is_compact:
                cr.save()
                draw_rounded(ax1 + 3, track_y + 3, max(1.0, aw - 6), max(1.0, track_h - 6), 3)
                cr.clip()

                t_layout = PangoCairo.create_layout(cr)
                t_layout.set_font_description(title_pango)
                t_layout.set_text(f"{it['icon']} {it['title']}", -1)
                cr.move_to(ax1 + 5, track_y + 4)
                cr.set_source_rgb(text_r, text_g, text_b)
                PangoCairo.show_layout(cr, t_layout)

                if aw >= 56:
                    s_layout = PangoCairo.create_layout(cr)
                    s_layout.set_font_description(sub_pango)
                    time_sub = f"{format_minutes_to_time(it['start_m'])}–{format_minutes_to_time(it['end_m'])} ({it['duration_m']}m)"
                    s_layout.set_text(time_sub, -1)
                    cr.move_to(ax1 + 5, track_y + 20)
                    cr.set_source_rgba(text_r, text_g, text_b, 0.75)
                    PangoCairo.show_layout(cr, s_layout)

                cr.restore()

                # On hover: draw subtle vertical resize grip handles on left and right borders
                if is_h and (not self.is_dragging or self.active_drag_item != it):
                    cr.set_line_width(2.0)
                    cr.set_source_rgba(text_r, text_g, text_b, 0.70)
                    # Left vertical resize handle
                    cr.move_to(ax1 + 2, track_y + 7)
                    cr.line_to(ax1 + 2, track_y + track_h - 7)
                    cr.stroke()
                    # Right vertical resize handle
                    cr.move_to(ax1 + aw - 2, track_y + 7)
                    cr.line_to(ax1 + aw - 2, track_y + track_h - 7)
                    cr.stroke()

        # 5. Current Time Line (NOW) - Shark Grey-Pink (Dusty Mauve: #826674 -> 0.510, 0.400, 0.455)
        now = datetime.now()
        now_m = now.hour * 60 + now.minute
        if self.scale_start_m <= now_m <= self.scale_end_m:
            nx = track_x + (now_m - self.scale_start_m) / float(total_span) * track_w
            cr.set_source_rgb(0.510, 0.400, 0.455)
            cr.set_line_width(1.5)
            cr.move_to(nx, track_y - 6)
            cr.line_to(nx, track_y + track_h + 2)
            cr.stroke()

            draw_rounded(nx - 14, track_y - 14, 28, 12, 6)
            cr.set_source_rgb(0.510, 0.400, 0.455)
            cr.fill()

            now_layout = PangoCairo.create_layout(cr)
            now_desc = Pango.FontDescription("sans bold 7")
            now_layout.set_font_description(now_desc)
            now_layout.set_text("NOW", -1)
            ink, log_r = now_layout.get_pixel_extents()
            cr.move_to(nx - log_r.width / 2.0, track_y - 13)
            cr.set_source_rgb(1.0, 1.0, 1.0)
            PangoCairo.show_layout(cr, now_layout)

        # 6. Live Selection Rectangle (while drawing a new task)
        if self.is_dragging and self.drag_action == "draw" and self.sel_start_m is not None and self.sel_end_m is not None:
            sx1 = self._minute_to_x(self.sel_start_m)
            sx2 = self._minute_to_x(self.sel_end_m)
            rx = min(sx1, sx2)
            rw = max(4.0, abs(sx2 - sx1))

            draw_rounded(rx, track_y, rw, track_h, 6)
            cr.set_source_rgba(0.32, 0.36, 0.31, 0.22)
            cr.fill_preserve()

            cr.set_dash([4, 2])
            cr.set_source_rgba(0.18, 0.22, 0.17, 0.95)
            cr.set_line_width(1.5)
            cr.stroke()
            cr.set_dash([])

            dur_mins = self.sel_end_m - self.sel_start_m
            b_text = f"{format_minutes_to_time(self.sel_start_m)} – {format_minutes_to_time(self.sel_end_m)} ({dur_mins}m)"
            b_layout = PangoCairo.create_layout(cr)
            b_desc = Pango.FontDescription("sans bold 8.5")
            b_layout.set_font_description(b_desc)
            b_layout.set_text(b_text, -1)
            ink, log_r = b_layout.get_pixel_extents()

            bw = log_r.width + 14
            bh = log_r.height + 6
            bx = max(track_x, min(track_x + track_w - bw, rx + (rw - bw) / 2.0))
            by = max(1.0, track_y - bh - 3)

            draw_rounded(bx, by, bw, bh, 5)
            cr.set_source_rgb(0.12, 0.16, 0.23)
            cr.fill()

            cr.move_to(bx + 7, by + 3)
            cr.set_source_rgb(1.0, 1.0, 1.0)
            PangoCairo.show_layout(cr, b_layout)

        # 7. Live Drag State for Moving or Resizing an Existing Task
        elif self.is_dragging and self.active_drag_item and self.live_drag_start_m is not None and self.live_drag_end_m is not None:
            it = self.active_drag_item
            lx1 = self._minute_to_x(self.live_drag_start_m)
            lx2 = self._minute_to_x(self.live_drag_end_m)
            rx = min(lx1, lx2)
            rw = max(16.0, abs(lx2 - lx1))

            # Render moving ghost block
            draw_rounded(rx, track_y, rw, track_h, 5)
            if it.get("is_break"):
                cr.set_source_rgba(0.97, 0.94, 0.95, 0.90)
                cr.fill_preserve()
                cr.set_source_rgb(0.510, 0.400, 0.455)
            else:
                cr.set_source_rgba(0.92, 0.95, 0.91, 0.90)
                cr.fill_preserve()
                cr.set_source_rgb(0.12, 0.16, 0.23)
            cr.set_line_width(2.0)
            cr.stroke()

            # Floating badge with updated start-end and duration
            dur_mins = max(5, self.live_drag_end_m - self.live_drag_start_m)
            action_icon = "↔" if "resize" in (self.drag_action or "") else "◷"
            b_text = f"{action_icon} {format_minutes_to_time(self.live_drag_start_m)} – {format_minutes_to_time(self.live_drag_end_m)} ({dur_mins}m)"
            if "resize" in (self.drag_action or ""):
                orig_dur = self.orig_duration_m or (self.orig_end_m - self.orig_start_m)
                diff = dur_mins - orig_dur
                if diff != 0:
                    sign = "+" if diff > 0 else ""
                    b_text += f" [{sign}{diff}m]"

            b_layout = PangoCairo.create_layout(cr)
            b_desc = Pango.FontDescription("sans bold 8.5")
            b_layout.set_font_description(b_desc)
            b_layout.set_text(b_text, -1)
            ink, log_r = b_layout.get_pixel_extents()

            bw = log_r.width + 16
            bh = log_r.height + 6
            bx = max(track_x, min(track_x + track_w - bw, rx + (rw - bw) / 2.0))
            by = max(1.0, track_y - bh - 4)

            draw_rounded(bx, by, bw, bh, 5)
            cr.set_source_rgb(0.12, 0.16, 0.23)
            cr.fill()

            cr.move_to(bx + 8, by + 3)
            cr.set_source_rgb(1.0, 1.0, 1.0)
            PangoCairo.show_layout(cr, b_layout)

    def _on_timeline_motion(self, controller, x, y):
        self.hover_x = x
        self.hover_y = y
        old_item = self.hovered_item_id
        old_gap = self.hovered_gap_idx
        old_edge = self.hover_edge

        track_x, track_y, track_w, track_h = self._get_track_rect(
            self.timeline_area.get_width(), self.timeline_area.get_height()
        )
        self.hovered_item_id = None
        self.hovered_gap_idx = None
        self.hover_edge = None

        if track_y - 2 <= y <= track_y + track_h + 2 and track_x <= x <= track_x + track_w:
            m = self._x_to_minute(x)
            self.hover_m = m

            for it in self.timeline_items:
                ax1 = self._minute_to_x(it["start_m"])
                ax2 = self._minute_to_x(it["end_m"])
                aw = max(1.0, ax2 - ax1)
                edge_margin = min(6.0, aw / 3.5)
                if ax1 - edge_margin <= x <= ax2 + edge_margin:
                    self.hovered_item_id = it["id"]
                    dist_l = abs(x - ax1)
                    dist_r = abs(x - ax2)
                    if dist_l <= edge_margin or dist_r <= edge_margin:
                        if dist_r < dist_l:
                            self.hover_edge = "right"
                            self.timeline_area.set_cursor_from_name("ew-resize")
                        else:
                            self.hover_edge = "left"
                            self.timeline_area.set_cursor_from_name("ew-resize")
                    else:
                        self.hover_edge = None
                        self.timeline_area.set_cursor_from_name("grab")
                    break

            if not self.hovered_item_id:
                for idx, g in enumerate(self.timeline_gaps):
                    if g["start_m"] <= m <= g["end_m"]:
                        self.hovered_gap_idx = idx
                        break
                self.timeline_area.set_cursor_from_name("crosshair")
        else:
            self.hover_m = None
            self.timeline_area.set_cursor_from_name("default")

        if (self.hovered_item_id != old_item or 
            self.hovered_gap_idx != old_gap or 
            self.hover_edge != old_edge or 
            self.is_dragging):
            self.timeline_area.queue_draw()

    def _on_timeline_leave(self, controller):
        self.hover_x = -1
        self.hover_y = -1
        self.hover_m = None
        self.hovered_item_id = None
        self.hovered_gap_idx = None
        self.hover_edge = None
        self.timeline_area.set_cursor_from_name("default")
        self.timeline_area.queue_draw()

    def _on_timeline_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        if self.is_dragging:
            return False
        track_x, track_y, track_w, track_h = self._get_track_rect(
            self.timeline_area.get_width(), self.timeline_area.get_height()
        )
        if not (track_y <= y <= track_y + track_h and track_x <= x <= track_x + track_w):
            return False

        m = self._x_to_minute(x)
        for it in self.timeline_items:
            if it["start_m"] <= m <= it["end_m"]:
                kind = "Break Activity" if it["is_break"] else ("Scheduled Task" if it.get("is_task") else "Work Activity")
                time_range = f"{format_minutes_to_time(it['start_m'])} – {format_minutes_to_time(it['end_m'])}"
                txt = f"{it['icon']} {it['title']}\n{kind} • {it['project']} • {it['duration_m']}m\nTime: {time_range}\n\n👉 Drag body to reschedule • Drag edges to resize\n(Click to view / edit)"
                tooltip.set_text(txt)
                return True

        for g in self.timeline_gaps:
            if g["start_m"] <= m <= g["end_m"]:
                time_range = f"{format_minutes_to_time(g['start_m'])} – {format_minutes_to_time(g['end_m'])}"
                txt = f"⏱ Untracked Gap: {g['duration_m']} min\nTime: {time_range}\n\n👉 Click or drag across this gap to log what you did or create a task"
                tooltip.set_text(txt)
                return True

        now = datetime.now()
        now_m = now.hour * 60 + now.minute
        if m > now_m:
            txt = f"Upcoming workday time: {format_minutes_to_time(m)}\n👉 Click & drag to schedule a task or plan this time"
            tooltip.set_text(txt)
            return True

        return False

    def _on_timeline_drag_begin(self, gesture, start_x, start_y):
        track_x, track_y, track_w, track_h = self._get_track_rect(
            self.timeline_area.get_width(), self.timeline_area.get_height()
        )
        if not (track_y - 8 <= start_y <= track_y + track_h + 8 and track_x <= start_x <= track_x + track_w):
            self.is_dragging = False
            return

        self.is_dragging = True
        self.drag_start_x = start_x
        self.drag_cur_x = start_x
        self.drag_action = None
        self.active_drag_item = None
        self.drag_has_moved = False

        # Check if clicking on an item (left edge, right edge, or body)
        for it in self.timeline_items:
            ax1 = self._minute_to_x(it["start_m"])
            ax2 = self._minute_to_x(it["end_m"])
            aw = max(1.0, ax2 - ax1)
            edge_margin = min(6.0, aw / 3.5)
            if ax1 - edge_margin <= start_x <= ax2 + edge_margin:
                self.active_drag_item = it
                self.orig_start_m = it["start_m"]
                self.orig_end_m = it["end_m"]
                self.orig_duration_m = it["duration_m"]
                self.live_drag_start_m = it["start_m"]
                self.live_drag_end_m = it["end_m"]

                dist_l = abs(start_x - ax1)
                dist_r = abs(start_x - ax2)
                if dist_l <= edge_margin or dist_r <= edge_margin:
                    if dist_r < dist_l:
                        self.drag_action = "resize-right"
                        self.timeline_area.set_cursor_from_name("ew-resize")
                    else:
                        self.drag_action = "resize-left"
                        self.timeline_area.set_cursor_from_name("ew-resize")
                else:
                    self.drag_action = "move-task"
                    click_m = self._x_to_minute(start_x)
                    self.drag_start_offset_m = click_m - it["start_m"]
                    self.timeline_area.set_cursor_from_name("grabbing")
                break

        if not self.drag_action:
            # Drawing a new task in empty gap / track
            self.drag_action = "draw"
            m = self._x_to_minute(start_x)
            self.sel_start_m = m
            self.sel_end_m = m
            self.timeline_area.set_cursor_from_name("crosshair")

        self.timeline_area.queue_draw()

    def _on_timeline_drag_update(self, gesture, offset_x, offset_y):
        if not self.is_dragging:
            return

        if abs(offset_x) > 3:
            self.drag_has_moved = True

        cur_x = self.drag_start_x + offset_x
        self.drag_cur_x = cur_x

        if self.drag_action == "move-task":
            cur_m = self._x_to_minute(cur_x)
            new_start_m = cur_m - self.drag_start_offset_m
            new_start_m = max(self.scale_start_m, min(self.scale_end_m - self.orig_duration_m, new_start_m))
            new_start_m = int(round(new_start_m / 5.0) * 5)
            self.live_drag_start_m = new_start_m
            self.live_drag_end_m = new_start_m + self.orig_duration_m

        elif self.drag_action == "resize-right":
            cur_m = self._x_to_minute(cur_x)
            new_end_m = max(self.orig_start_m + 5, min(self.scale_end_m, cur_m))
            new_end_m = int(round(new_end_m / 5.0) * 5)
            self.live_drag_start_m = self.orig_start_m
            self.live_drag_end_m = new_end_m

        elif self.drag_action == "resize-left":
            cur_m = self._x_to_minute(cur_x)
            new_start_m = min(self.orig_end_m - 5, max(self.scale_start_m, cur_m))
            new_start_m = int(round(new_start_m / 5.0) * 5)
            self.live_drag_start_m = new_start_m
            self.live_drag_end_m = self.orig_end_m

        elif self.drag_action == "draw":
            m1 = self._x_to_minute(self.drag_start_x)
            m2 = self._x_to_minute(cur_x)
            self.sel_start_m = min(m1, m2)
            self.sel_end_m = max(m1, m2)

        self.timeline_area.queue_draw()

    def _on_timeline_drag_end(self, gesture, offset_x, offset_y):
        if not self.is_dragging:
            return
        self.is_dragging = False

        action = self.drag_action
        has_moved = self.drag_has_moved and abs(offset_x) >= 4
        item = self.active_drag_item

        if action == "move-task":
            if has_moved and self.live_drag_start_m is not None and self.live_drag_start_m != self.orig_start_m:
                self._apply_item_time_change(item, self.live_drag_start_m, self.live_drag_end_m)
            else:
                self._open_item_edit_modal(item)

        elif action in ("resize-left", "resize-right"):
            if has_moved and self.live_drag_start_m is not None and (self.live_drag_start_m != self.orig_start_m or self.live_drag_end_m != self.orig_end_m):
                self._apply_item_time_change(item, self.live_drag_start_m, self.live_drag_end_m)
            else:
                self._open_item_edit_modal(item)

        elif action == "draw":
            start_m = self.sel_start_m if self.sel_start_m is not None else self._x_to_minute(self.drag_start_x)
            end_m = self.sel_end_m if self.sel_end_m is not None else start_m
            dur = end_m - start_m

            if dur >= 5 and has_moved:
                self._show_timeline_creation_popover(start_m, end_m)
            else:
                clicked_m = start_m
                clicked_gap = next((g for g in self.timeline_gaps if g["start_m"] <= clicked_m <= g["end_m"]), None)
                if clicked_gap:
                    self.sel_start_m = clicked_gap["start_m"]
                    self.sel_end_m = clicked_gap["end_m"]
                    self._show_timeline_creation_popover(clicked_gap["start_m"], clicked_gap["end_m"])
                else:
                    self.sel_start_m = clicked_m
                    self.sel_end_m = min(self.scale_end_m, clicked_m + 30)
                    self._show_timeline_creation_popover(self.sel_start_m, self.sel_end_m)

        self.drag_action = None
        self.active_drag_item = None
        self.timeline_area.set_cursor_from_name("default")
        self.timeline_area.queue_draw()

    def _show_timeline_creation_popover(self, start_m: int, end_m: int):
        dur_m = max(5, end_m - start_m)
        start_str = format_minutes_to_time(start_m)
        end_str = format_minutes_to_time(end_m)
        today_str = datetime.now().strftime("%Y-%m-%d")

        if hasattr(self, "_timeline_popover") and self._timeline_popover:
            self._timeline_popover.popdown()

        popover = Gtk.Popover()
        popover.add_css_class("calendar-popover")
        popover.set_parent(self.timeline_area)
        self._timeline_popover = popover

        x1 = self._minute_to_x(start_m)
        x2 = self._minute_to_x(end_m)
        track_x, track_y, track_w, track_h = self._get_track_rect(
            self.timeline_area.get_width(), self.timeline_area.get_height()
        )
        rect = Gdk.Rectangle()
        rect.x = int(min(x1, x2))
        rect.y = int(track_y)
        rect.width = int(max(20.0, abs(x2 - x1)))
        rect.height = int(track_h)
        popover.set_pointing_to(rect)

        pop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        pop_box.set_margin_top(10)
        pop_box.set_margin_bottom(10)
        pop_box.set_margin_start(12)
        pop_box.set_margin_end(12)

        # Header with time slot info
        h_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_title = Gtk.Label(label="Selected Time Slot:")
        lbl_title.add_css_class("text-muted")
        h_box.append(lbl_title)

        lbl_slot = Gtk.Label(label=f"{start_str} – {end_str} ({dur_m}m)")
        lbl_slot.add_css_class("tag-pill-project")
        h_box.append(lbl_slot)
        pop_box.append(h_box)

        # Option 1: Log Completed Activity in Journal
        btn_log = Gtk.Button()
        btn_log.add_css_class("card-box")
        btn_log_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        l1 = Gtk.Label(label="◷ Log Completed Activity")
        l1.add_css_class("text-title")
        l1.set_halign(Gtk.Align.START)
        l2 = Gtk.Label(label="Record what you did in this gap into today's Activity Journal")
        l2.add_css_class("text-muted")
        l2.set_halign(Gtk.Align.START)
        btn_log_box.append(l1)
        btn_log_box.append(l2)
        btn_log.set_child(btn_log_box)

        def on_log_clicked(b):
            popover.popdown()
            win = self.get_root()
            dlg = NewJournalEntryDialog(
                win,
                self.storage,
                self.refresh,
                prefill={
                    "start_time": start_str,
                    "duration_minutes": dur_m,
                    "title": "",
                    "project": "General"
                }
            )
            dlg.present()

        btn_log.connect("clicked", on_log_clicked)
        pop_box.append(btn_log)

        # Option 2: Create Scheduled Task
        btn_task = Gtk.Button()
        btn_task.add_css_class("card-box")
        btn_task_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        t1 = Gtk.Label(label="⊞ Create Scheduled Task")
        t1.add_css_class("text-title")
        t1.set_halign(Gtk.Align.START)
        t2 = Gtk.Label(label="Schedule a task for this time slot")
        t2.add_css_class("text-muted")
        t2.set_halign(Gtk.Align.START)
        btn_task_box.append(t1)
        btn_task_box.append(t2)
        btn_task.set_child(btn_task_box)

        def on_task_clicked(b):
            popover.popdown()
            win = self.get_root()
            dlg = NewTaskDialog(
                win,
                self.storage,
                self.refresh,
                default_type="task",
                prefill_date=today_str,
                prefill_time=start_str,
                prefill_duration=dur_m
            )
            dlg.present()

        btn_task.connect("clicked", on_task_clicked)
        pop_box.append(btn_task)

        # Option 3: Quick prefill into form below
        btn_fill = Gtk.Button(label=f"⚡ Fill into 'Log Activity' form below ({start_str}, {dur_m}m)")
        btn_fill.add_css_class("btn-secondary")
        def on_fill_clicked(b):
            popover.popdown()
            self._switch_entry_mode("retro")
            self.retro_dur_entry.set_text(str(dur_m))
            self.retro_title_entry.grab_focus()
        btn_fill.connect("clicked", on_fill_clicked)
        pop_box.append(btn_fill)

        def on_pop_closed(p):
            self.sel_start_m = None
            self.sel_end_m = None
            self.timeline_area.queue_draw()

        popover.connect("closed", on_pop_closed)
        popover.set_child(pop_box)
        popover.popup()

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

        # Refresh Day Timeline view
        self._refresh_timeline()

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
