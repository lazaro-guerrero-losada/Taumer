"""
Calendar & Time-Blocking View:
- True-Time Canvas Timeline: Accurate minute-level positioning across hour borders (e.g. 10:46 to 11:07).
- Parallel side-by-side collision layout: Overlapping tasks and events appear next to each other in equal columns.
- Superior and Inferior limit resizing: Drag top edge to adjust start time, drag bottom edge to adjust duration.
- Task vs Event scheduling: Distinct styles and one-click '+ Log to Journal' on finished events.
- Direct synchronization with Obsidian markdown files and Activity Journal reconciliation.
- 1-Day, 3-Days, 5-Days (Workweek), and Month views.
- Fully localized in English with Apple Human Interface Guidelines aesthetic.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('WebKit', '6.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, GLib, Pango, WebKit
from datetime import datetime, timedelta
from pathlib import Path
import calendar
from typing import Optional, List, Dict
from models import Task, JournalEntry
from ui.dialogs import NewTaskDialog, TaskCompletionDialog

def create_sidebar_stage_icon(stage: str) -> Gtk.Widget:
    """
    Renders an SVG icon matching Antigravity / modern IDE sidebar panels with 3 stages:
    - 'normal': Window outline with divider near right edge (compact drawer, 180px)
    - 'wide': Window outline with divider near middle-right (expanded drawer, 360px)
    - 'closed': Clean window outline without inner divider (drawer closed)
    """
    if stage == 'wide':
        inner = '''
        <rect x="8" y="3" width="10" height="14" rx="1" fill="#475569" fill-opacity="0.22" />
        <line x1="8" y1="3" x2="8" y2="17" stroke="#475569" stroke-width="1.5" />
        '''
        rect_stroke = '#475569'
    elif stage == 'normal':
        inner = '''
        <rect x="13" y="3" width="5" height="14" rx="1" fill="#475569" fill-opacity="0.22" />
        <line x1="13" y1="3" x2="13" y2="17" stroke="#475569" stroke-width="1.5" />
        '''
        rect_stroke = '#475569'
    else:  # closed
        inner = ''
        rect_stroke = '#8e8e93'

    svg = f'''<svg width="20" height="20" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
        <rect x="2" y="3" width="16" height="14" rx="2.5" fill="none" stroke="{rect_stroke}" stroke-width="1.5" />
        {inner}
    </svg>'''

    try:
        loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
        loader.write(svg.encode('utf-8'))
        loader.close()
        pixbuf = loader.get_pixbuf()
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        return Gtk.Image.new_from_paintable(texture)
    except Exception:
        fallback_map = {"normal": "◫", "wide": "▥", "closed": "◻"}
        return Gtk.Label(label=fallback_map.get(stage, "◫"))

DAY_START_HOUR = 7   # 07:00
DAY_END_HOUR = 23    # 23:00
TOTAL_HOURS = DAY_END_HOUR - DAY_START_HOUR # 16 hours
HOUR_HEIGHT = 64     # pixels per hour
TOTAL_HEIGHT = TOTAL_HOURS * HOUR_HEIGHT   # 1024 pixels

DRAWER_NORMAL_WIDTH = 180  # Compact drawer width (half size of wide)
DRAWER_WIDE_WIDTH = 360    # Widely expanded drawer width (2x normal)

def parse_time_minutes(t_str: Optional[str]) -> Optional[int]:
    """Parses 'HH:MM' string to minutes from midnight."""
    if not t_str or ":" not in t_str:
        return None
    try:
        parts = t_str.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return None

def format_minutes_to_time(minutes: int) -> str:
    """Formats minutes from midnight into 'HH:MM'."""
    minutes = max(0, min(24 * 60 - 1, minutes))
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

def layout_parallel_items(items: list) -> list:
    """
    Groups overlapping scheduled tasks/events into parallel side-by-side columns.
    Returns a list of dicts:
    [{'item': Task, 'col': int, 'total_cols': int, 'start_m': int, 'end_m': int, 'dur': int}, ...]
    """
    parsed = []
    for it in items:
        sm = parse_time_minutes(it.scheduled_time)
        if sm is None:
            continue
        dur = it.scheduled_duration or it.estimated_minutes or 45
        dur = max(10, dur)
        # Collision end accounts for minimum visual card height (~48 minutes) to prevent text clipping
        em = sm + max(48, dur)
        parsed.append({'item': it, 'start_m': sm, 'end_m': em, 'dur': dur})

    if not parsed:
        return []

    # Sort primarily by start time, secondarily by duration descending
    parsed.sort(key=lambda x: (x['start_m'], -x['dur']))

    clusters = []
    current_cluster = []
    cluster_end = -1

    for p in parsed:
        if not current_cluster:
            current_cluster.append(p)
            cluster_end = p['end_m']
        else:
            if p['start_m'] < cluster_end:
                current_cluster.append(p)
                cluster_end = max(cluster_end, p['end_m'])
            else:
                clusters.append(current_cluster)
                current_cluster = [p]
                cluster_end = p['end_m']
    if current_cluster:
        clusters.append(current_cluster)

    results = []
    for cluster in clusters:
        columns = []
        assigned = []
        for p in cluster:
            placed = False
            for col_idx, col_end in enumerate(columns):
                if p['start_m'] >= col_end:
                    columns[col_idx] = p['end_m']
                    assigned.append((p, col_idx))
                    placed = True
                    break
            if not placed:
                col_idx = len(columns)
                columns.append(p['end_m'])
                assigned.append((p, col_idx))

        total_cols = len(columns)
        for p, col_idx in assigned:
            results.append({
                'item': p['item'],
                'col': col_idx,
                'total_cols': total_cols,
                'start_m': p['start_m'],
                'end_m': p['end_m'],
                'dur': p['dur']
            })
    return results


class CalendarView(Gtk.Box):
    def __init__(self, storage):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.storage = storage
        self.current_date = datetime.now()
        self.active_mode = "1d"  # "1d", "3d", "5d", "month"
        self.drawer_stage = "normal"  # "normal" (180px), "wide" (360px), "closed" (hidden)
        self.missed_banner_dismissed = False

        self.add_css_class("calendar-view")
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(22)
        self.set_margin_end(22)

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # 1. Top Navigation & Control Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        # Date Navigator
        nav_arrows = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        prev_btn = Gtk.Button(label="◀")
        prev_btn.add_css_class("btn-secondary")
        prev_btn.connect("clicked", lambda b: self._change_period(-1))
        nav_arrows.append(prev_btn)

        today_btn = Gtk.Button(label="Today")
        today_btn.add_css_class("btn-secondary")
        today_btn.connect("clicked", lambda b: self._go_today())
        nav_arrows.append(today_btn)

        next_btn = Gtk.Button(label="▶")
        next_btn.add_css_class("btn-secondary")
        next_btn.connect("clicked", lambda b: self._change_period(1))
        nav_arrows.append(next_btn)
        toolbar.append(nav_arrows)

        # Date title
        self.date_label = Gtk.Label()
        self.date_label.add_css_class("text-heading")
        self.date_label.set_margin_start(10)
        toolbar.append(self.date_label)

        toolbar.append(Gtk.Box(hexpand=True))

        # Floating guide label for interactive resize / drag preview
        self.guide_label = Gtk.Label(label="")
        self.guide_label.add_css_class("drop-indicator")
        self.guide_label.set_visible(False)
        toolbar.append(self.guide_label)

        # View switcher segmented bar
        self.mode_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.mode_bar.add_css_class("segmented-bar")

        self.mode_buttons = {}
        modes = [("1d", "1 Day"), ("3d", "3 Days"), ("5d", "5 Days"), ("month", "Month")]
        for m_id, label in modes:
            btn = Gtk.Button(label=label)
            btn.add_css_class("segmented-btn")
            if m_id == self.active_mode:
                btn.add_css_class("active")
            btn.connect("clicked", self._on_mode_clicked, m_id)
            self.mode_bar.append(btn)
            self.mode_buttons[m_id] = btn

        toolbar.append(self.mode_bar)

        new_block_btn = Gtk.Button(label="+ Schedule")
        new_block_btn.add_css_class("btn-primary")
        new_block_btn.connect("clicked", self._open_schedule_dialog)
        toolbar.append(new_block_btn)

        # 3-Stage Unassigned Drawer Toggle Button (Antigravity sidebar panel style)
        self.btn_stage_drawer = Gtk.Button()
        self.btn_stage_drawer.add_css_class("btn-secondary")
        self.btn_stage_drawer.connect("clicked", self._cycle_drawer_stage)

        btn_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.stage_icon_slot = Gtk.Box()
        self.stage_btn_label = Gtk.Label(label="Tasks: Normal")
        btn_inner.append(self.stage_icon_slot)
        btn_inner.append(self.stage_btn_label)
        self.btn_stage_drawer.set_child(btn_inner)
        toolbar.append(self.btn_stage_drawer)

        self.append(toolbar)

        # 2. Main content container
        self.content_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content_area.set_vexpand(True)
        self.content_area.set_hexpand(True)
        self.append(self.content_area)

    def _cycle_drawer_stage(self, btn=None):
        cycle = {"normal": "wide", "wide": "closed", "closed": "normal"}
        self.drawer_stage = cycle.get(self.drawer_stage, "normal")
        self.refresh()

    def _set_drawer_stage(self, stage: str):
        self.drawer_stage = stage
        self.refresh()

    def _on_mode_clicked(self, btn, m_id):
        self.active_mode = m_id
        for mid, b in self.mode_buttons.items():
            if mid == m_id:
                b.add_css_class("active")
            else:
                b.remove_css_class("active")
        self.refresh()

    def _change_period(self, direction: int):
        if self.active_mode == "1d":
            self.current_date += timedelta(days=direction)
        elif self.active_mode == "3d":
            self.current_date += timedelta(days=direction * 3)
        elif self.active_mode == "5d":
            self.current_date += timedelta(days=direction * 7)
        elif self.active_mode == "month":
            year = self.current_date.year
            month = self.current_date.month + direction
            if month < 1:
                month = 12
                year -= 1
            elif month > 12:
                month = 1
                year += 1
            self.current_date = self.current_date.replace(year=year, month=month, day=1)
        self.refresh()

    def _go_today(self):
        self.current_date = datetime.now()
        self.refresh()

    def _open_schedule_dialog(self, btn):
        win = self.get_root()
        dlg = NewTaskDialog(
            win,
            self.storage,
            self.refresh,
            default_type="event",
            prefill_date=self.current_date.strftime("%Y-%m-%d"),
            prefill_time="10:00"
        )
        dlg.present()

    def refresh(self):
        while child := self.content_area.get_first_child():
            self.content_area.remove(child)

        days_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        months_en = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

        all_tasks = self.storage.get_tasks()
        today_str = datetime.now().strftime("%Y-%m-%d")
        past_missed = [t for t in all_tasks if t.status != "done" and t.scheduled_date and t.scheduled_date < today_str]
        pending_unassigned = [t for t in all_tasks if t.status != "done" and not t.scheduled_time and (not t.scheduled_date or t.scheduled_date >= today_str)]

        # Check for uncompleted scheduled tasks (reminders & recalendar suggestions)
        missed_tasks = self.storage.get_missed_scheduled_tasks(include_today_overdue=True)
        if missed_tasks:
            self.content_area.append(self._build_missed_banner(missed_tasks))

        # Update 3-stage drawer button state
        while ch := self.stage_icon_slot.get_first_child():
            self.stage_icon_slot.remove(ch)
        self.stage_icon_slot.append(create_sidebar_stage_icon(self.drawer_stage))

        label_map = {
            "normal": "Tasks: Normal",
            "wide": "Tasks: Widely",
            "closed": "Tasks: Close"
        }
        tooltip_map = {
            "normal": f"Unassigned Tasks Drawer: Normal ({DRAWER_NORMAL_WIDTH}px) — Click for Widely",
            "wide": f"Unassigned Tasks Drawer: Widely ({DRAWER_WIDE_WIDTH}px) — Click to Close",
            "closed": "Unassigned Tasks Drawer: Closed — Click for Normal"
        }
        self.stage_btn_label.set_text(label_map.get(self.drawer_stage, "Tasks"))
        self.btn_stage_drawer.set_tooltip_text(tooltip_map.get(self.drawer_stage, ""))
        if self.drawer_stage == "closed":
            self.btn_stage_drawer.remove_css_class("active")
        else:
            self.btn_stage_drawer.add_css_class("active")

        if self.active_mode == "month":
            self.btn_stage_drawer.set_visible(False)
            self.date_label.set_text(f"{months_en[self.current_date.month-1]} {self.current_date.year}")
            self._render_month_view()
        elif self.active_mode in ["3d", "5d"]:
            self.btn_stage_drawer.set_visible(False)
            num_days = 3 if self.active_mode == "3d" else 5
            start_date = self.current_date
            if self.active_mode == "5d":
                start_date = self.current_date - timedelta(days=self.current_date.weekday())
            end_date = start_date + timedelta(days=num_days - 1)
            self.date_label.set_text(f"{months_en[start_date.month-1][:3]} {start_date.day} – {months_en[end_date.month-1][:3]} {end_date.day}, {start_date.year}")
            self._render_multiday_view(start_date, num_days)
        else:
            self.btn_stage_drawer.set_visible(True)
            fecha_txt = f"{days_en[self.current_date.weekday()]}, {months_en[self.current_date.month-1]} {self.current_date.day}, {self.current_date.year}"
            self.date_label.set_text(fecha_txt)
            self._render_1day_view(pending_unassigned, past_missed)

    def _build_missed_banner(self, missed_tasks: list) -> Gtk.Widget:
        if getattr(self, "missed_banner_dismissed", False):
            bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            bar.add_css_class("home-reminder-strip")
            bar.set_margin_bottom(6)

            lbl_ic = Gtk.Label(label="⚠️")
            bar.append(lbl_ic)

            lbl_txt = Gtk.Label(label=f"Reminder: {len(missed_tasks)} calendar task(s) were not completed.")
            lbl_txt.add_css_class("text-title")
            bar.append(lbl_txt)

            bar.append(Gtk.Box(hexpand=True))

            btn_all = Gtk.Button(label="⟳ Recalendar All to Today")
            btn_all.add_css_class("btn-secondary")
            btn_all.connect("clicked", lambda b: self._recalendar_all_missed_to_today())
            bar.append(btn_all)

            btn_show = Gtk.Button(label="Review Tasks ↓")
            btn_show.add_css_class("btn-secondary")
            def _unhide(b):
                self.missed_banner_dismissed = False
                self.refresh()
            btn_show.connect("clicked", _unhide)
            bar.append(btn_show)
            return bar

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("calendar-missed-banner")

        # Top header
        top_h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        lbl_ic = Gtk.Label(label="⚠️")
        lbl_ic.add_css_class("text-heading")
        top_h.append(lbl_ic)

        title_v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        h_lbl = Gtk.Label(label=f"Missed & Uncompleted Calendar Tasks ({len(missed_tasks)})")
        h_lbl.add_css_class("text-title")
        h_lbl.set_halign(Gtk.Align.START)
        s_lbl = Gtk.Label(label="These tasks were scheduled in your calendar but not marked done. Reschedule or complete them:")
        s_lbl.add_css_class("text-muted")
        s_lbl.set_halign(Gtk.Align.START)
        title_v.append(h_lbl)
        title_v.append(s_lbl)
        top_h.append(title_v)

        top_h.append(Gtk.Box(hexpand=True))

        btn_all_today = Gtk.Button(label="⟳ Recalendar All to Today")
        btn_all_today.add_css_class("btn-secondary")
        btn_all_today.set_tooltip_text("Move all missed tasks from past days onto today's schedule")
        btn_all_today.connect("clicked", lambda b: self._recalendar_all_missed_to_today())
        top_h.append(btn_all_today)

        btn_hide = Gtk.Button(label="✕ Hide")
        btn_hide.add_css_class("btn-ghost")
        btn_hide.set_tooltip_text("Collapse this reminder")
        def _hide(b):
            self.missed_banner_dismissed = True
            self.refresh()
        btn_hide.connect("clicked", _hide)
        top_h.append(btn_hide)

        card.append(top_h)

        # List rows (up to 4 items)
        today_str = datetime.now().strftime("%Y-%m-%d")
        for t in missed_tasks[:4]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("calendar-missed-row")

            is_past_day = bool(t.scheduled_date and t.scheduled_date < today_str)
            if is_past_day:
                time_txt = f"⚠️ Missed: {t.scheduled_date}" + (f" at {t.scheduled_time}" if t.scheduled_time else "")
            else:
                time_txt = f"⚠️ Overdue: Today at {t.scheduled_time}"
            lbl_sched = Gtk.Label(label=time_txt)
            lbl_sched.add_css_class("tag-pill-alert")
            row.append(lbl_sched)

            lbl_p = Gtk.Label(label=f"{t.icon} {t.project}")
            lbl_p.add_css_class("tag-pill-project")
            row.append(lbl_p)

            lbl_t = Gtk.Label(label=t.title)
            lbl_t.add_css_class("text-title")
            lbl_t.set_halign(Gtk.Align.START)
            lbl_t.set_hexpand(True)
            lbl_t.set_ellipsize(Pango.EllipsizeMode.END)
            row.append(lbl_t)

            btn_t_today = Gtk.Button(label="⟳ Today")
            btn_t_today.add_css_class("btn-secondary")
            btn_t_today.set_tooltip_text("Reschedule to today")
            btn_t_today.connect("clicked", lambda b, tid=t.id: self._quick_recalendar(tid, "today"))
            row.append(btn_t_today)

            btn_t_tom = Gtk.Button(label="⟳ Tomorrow")
            btn_t_tom.add_css_class("btn-secondary")
            btn_t_tom.set_tooltip_text("Reschedule to tomorrow 09:00")
            btn_t_tom.connect("clicked", lambda b, tid=t.id: self._quick_recalendar(tid, "tomorrow"))
            row.append(btn_t_tom)

            btn_t_pick = Gtk.Button(label="📅 Reschedule...")
            btn_t_pick.add_css_class("btn-secondary")
            btn_t_pick.set_tooltip_text("Open calendar date & time picker")
            btn_t_pick.connect("clicked", lambda b, task=t: self._open_reschedule_dialog(task))
            row.append(btn_t_pick)

            btn_t_done = Gtk.Button(label="Done ✓")
            btn_t_done.add_css_class("btn-secondary")
            btn_t_done.set_tooltip_text("Mark task as completed")
            btn_t_done.connect("clicked", lambda b, task=t: self._prompt_complete_task(task))
            row.append(btn_t_done)

            btn_t_un = Gtk.Button(label="✕")
            btn_t_un.add_css_class("btn-ghost")
            btn_t_un.set_tooltip_text("Send back to Unassigned backlog without date")
            btn_t_un.connect("clicked", lambda b, tid=t.id: self._unassign_task(tid))
            row.append(btn_t_un)

            card.append(row)

        if len(missed_tasks) > 4:
            more_lbl = Gtk.Label(label=f"+ {len(missed_tasks) - 4} more missed tasks visible in the right Tasks drawer")
            more_lbl.add_css_class("text-muted")
            more_lbl.set_halign(Gtk.Align.START)
            card.append(more_lbl)

        return card

    def _quick_recalendar(self, task_id: str, when: str):
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        if when == "today":
            if now.hour < 20:
                if now.minute < 30:
                    next_time = f"{now.hour:02d}:30"
                else:
                    next_time = f"{now.hour + 1:02d}:00"
            else:
                next_time = None
            self.storage.update_task(task_id, scheduled_date=today_str, scheduled_time=next_time)
        elif when == "tomorrow":
            self.storage.update_task(task_id, scheduled_date=tomorrow_str, scheduled_time="09:00")
        self.refresh()

    def _recalendar_all_missed_to_today(self):
        self.storage.recalendar_all_missed_to_today()
        self.refresh()

    def _unassign_task(self, task_id: str):
        self.storage.unassign_task_schedule(task_id)
        self.refresh()

    def _open_reschedule_dialog(self, task: Task):
        win = self.get_root()
        dlg = NewTaskDialog(win, self.storage, self.refresh, edit_task=task)
        dlg.present()

    # ==========================================
    # 1-DAY VIEW (True-Time Canvas + Side-by-Side Parallel Items)
    # ==========================================
    def _render_1day_view(self, pending_unassigned: list, past_missed: list = None):
        paned = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        paned.set_vexpand(True)
        paned.set_hexpand(True)
        self.content_area.append(paned)

        # 1. Main Timeline Canvas on LEFT (hexpand=True)
        date_str = self.current_date.strftime("%Y-%m-%d")
        timeline_widget = self._create_day_timeline(date_str, show_ruler=True)
        paned.append(timeline_widget)

        # 2. Unassigned Tasks Drawer on RIGHT (180px in normal, 360px in wide)
        if self.drawer_stage != "closed":
            is_normal = (self.drawer_stage == "normal")
            drawer_width = DRAWER_NORMAL_WIDTH if is_normal else DRAWER_WIDE_WIDTH
            right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            right_box.set_hexpand(False)
            right_box.set_halign(Gtk.Align.END)
            right_box.set_size_request(drawer_width, -1)
            right_box.add_css_class("card-box")

            r_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            total_drawer_items = len(pending_unassigned) + (len(past_missed) if past_missed else 0)
            lbl_title_txt = f"Tasks ({total_drawer_items})" if is_normal else f"Tasks & Missed ({total_drawer_items})"
            lbl_side = Gtk.Label(label=lbl_title_txt)
            lbl_side.add_css_class("text-title")
            r_header.append(lbl_side)

            r_header.append(Gtk.Box(hexpand=True))

            # Width toggle button (switch between Normal 180px and Widely 360px)
            toggle_width_btn = Gtk.Button(label="↔" if is_normal else "↔ Normal")
            toggle_width_btn.add_css_class("btn-ghost")
            toggle_width_btn.set_tooltip_text(f"Switch width (Normal {DRAWER_NORMAL_WIDTH}px / Widely {DRAWER_WIDE_WIDTH}px)")
            toggle_width_btn.connect("clicked", lambda b: self._set_drawer_stage("wide" if self.drawer_stage == "normal" else "normal"))
            r_header.append(toggle_width_btn)

            close_drawer_btn = Gtk.Button(label="✕")
            close_drawer_btn.add_css_class("btn-ghost")
            close_drawer_btn.set_tooltip_text("Close drawer")
            close_drawer_btn.connect("clicked", lambda b: self._set_drawer_stage("closed"))
            r_header.append(close_drawer_btn)
            right_box.append(r_header)

            lbl_hint_txt = "Drag to timeline:" if is_normal else "Drag tasks onto your timeline:"
            lbl_hint = Gtk.Label(label=lbl_hint_txt)
            lbl_hint.add_css_class("text-muted")
            lbl_hint.set_halign(Gtk.Align.START)
            lbl_hint.set_wrap(True)
            lbl_hint.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            right_box.append(lbl_hint)

            scrolled_right = Gtk.ScrolledWindow()
            scrolled_right.set_vexpand(True)
            scrolled_right.set_hexpand(False)
            scrolled_right.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            pending_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            pending_list.set_hexpand(False)
            scrolled_right.set_child(pending_list)
            right_box.append(scrolled_right)
            paned.append(right_box)

            # Section A: Past Missed Tasks (Tasks that didn't go done in previous calendar schedules)
            if past_missed:
                sec_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                sec_header.set_margin_top(4)
                sec_lbl = Gtk.Label(label="⚠️ Missed" if is_normal else f"⚠️ Needs Recalendaring ({len(past_missed)})")
                sec_lbl.add_css_class("tag-pill-alert")
                sec_header.append(sec_lbl)
                pending_list.append(sec_header)

                for t in past_missed:
                    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                    card.add_css_class("card-box-accent")
                    card.add_css_class("draggable-card")
                    self._make_widget_draggable(card, t.id)

                    top_r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                    date_tag = t.scheduled_date[5:] if t.scheduled_date else "Past"
                    dur_lbl = Gtk.Label(label=f"⚠️ {date_tag}")
                    dur_lbl.add_css_class("tag-pill-alert")
                    top_r.append(dur_lbl)

                    top_r.append(Gtk.Box(hexpand=True))

                    btn_tod = Gtk.Button(label="⟳ Today")
                    btn_tod.add_css_class("btn-secondary")
                    btn_tod.set_tooltip_text("Reschedule to today")
                    btn_tod.connect("clicked", lambda b, tid=t.id: self._quick_recalendar(tid, "today"))
                    top_r.append(btn_tod)

                    card.append(top_r)

                    t_lbl = Gtk.Label(label=t.title)
                    t_lbl.set_halign(Gtk.Align.START)
                    t_lbl.add_css_class("text-title")
                    t_lbl.set_wrap(True)
                    t_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                    card.append(t_lbl)
                    pending_list.append(card)

                pending_list.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

            # Section B: General Unassigned Tasks
            if pending_unassigned:
                for t in pending_unassigned:
                    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                    card.add_css_class("card-box-accent")
                    card.add_css_class("draggable-card")
                    self._make_widget_draggable(card, t.id)

                    top_r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                    proj_lbl = Gtk.Label(label=f"{t.icon} {t.project}")
                    proj_lbl.add_css_class("tag-pill-project")
                    proj_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                    proj_lbl.set_max_width_chars(8 if is_normal else 20)
                    top_r.append(proj_lbl)

                    dur_lbl = Gtk.Label(label=f"{t.estimated_minutes}m")
                    dur_lbl.add_css_class("tag-pill")
                    top_r.append(dur_lbl)

                    top_r.append(Gtk.Box(hexpand=True))
                    drag_hint = Gtk.Label(label="⠿")
                    drag_hint.add_css_class("text-muted")
                    top_r.append(drag_hint)
                    card.append(top_r)

                    t_lbl = Gtk.Label(label=t.title)
                    t_lbl.set_halign(Gtk.Align.START)
                    t_lbl.add_css_class("text-title")
                    t_lbl.set_wrap(True)
                    t_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                    card.append(t_lbl)
                    pending_list.append(card)
            elif not past_missed:
                lbl_none = Gtk.Label(label="All tasks are scheduled")
                lbl_none.add_css_class("text-muted")
                lbl_none.set_margin_top(16)
                pending_list.append(lbl_none)

    # ==========================================
    # TRUE-TIME CANVAS TIMELINE GENERATOR
    # ==========================================
    def _create_day_timeline(self, date_str: str, show_ruler: bool = True) -> Gtk.Widget:
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        container.set_vexpand(True)
        container.set_hexpand(True)

        # Untimed / All-Day scheduled items strip
        all_tasks = self.storage.get_tasks()
        day_tasks = [t for t in all_tasks if t.scheduled_date == date_str or (t.scheduled_time and not t.scheduled_date and date_str == datetime.now().strftime("%Y-%m-%d"))]
        untimed_tasks = [t for t in day_tasks if parse_time_minutes(t.scheduled_time) is None]

        if untimed_tasks:
            all_day_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            all_day_box.add_css_class("all-day-strip")

            lbl_ad = Gtk.Label(label="All-Day")
            lbl_ad.add_css_class("tag-pill")
            all_day_box.append(lbl_ad)

            for ut in untimed_tasks:
                u_done = (ut.status == "done" or getattr(ut, "logged_to_journal", False))
                u_item_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                if u_done:
                    u_item_box.add_css_class("tag-pill-completed")
                else:
                    u_item_box.add_css_class("tag-pill-project")

                txt = f"{ut.icon} {ut.title}" if getattr(ut, "icon", None) else ut.title
                u_lbl = Gtk.Label(label=txt)
                if u_done:
                    u_lbl.add_css_class("calendar-card-title-completed")
                u_item_box.append(u_lbl)

                btn_chk = Gtk.Button(label="✓" if u_done else "○")
                btn_chk.add_css_class("btn-ghost")
                btn_chk.connect("clicked", lambda b, it=ut: self._prompt_complete_task(it))
                u_item_box.append(btn_chk)

                edit_g = Gtk.GestureClick.new()
                def on_ad_clicked(g, n, x, y, item=ut):
                    if n == 2:
                        win = self.get_root()
                        dlg = NewTaskDialog(win, self.storage, self.refresh, edit_task=item)
                        dlg.present()
                edit_g.connect("released", on_ad_clicked)
                u_item_box.add_controller(edit_g)

                all_day_box.append(u_item_box)

            container.append(all_day_box)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        container.append(scrolled)

        timeline_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        scrolled.set_child(timeline_inner)

        # 1. Left Time Ruler (07:00 to 23:00)
        if show_ruler:
            ruler_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            ruler_box.set_size_request(58, TOTAL_HEIGHT)
            ruler_box.set_valign(Gtk.Align.START)

            for hour in range(DAY_START_HOUR, DAY_END_HOUR):
                h_cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
                h_cell.set_size_request(58, HOUR_HEIGHT)

                h_lbl = Gtk.Label(label=f"{hour:02d}:00")
                h_lbl.add_css_class("text-mono")
                h_lbl.set_halign(Gtk.Align.END)
                h_cell.append(h_lbl)

                q_lbl = Gtk.Label(label=":30")
                q_lbl.add_css_class("text-muted")
                q_lbl.set_opacity(0.4)
                q_lbl.set_halign(Gtk.Align.END)
                q_lbl.set_margin_top(16)
                h_cell.append(q_lbl)

                ruler_box.append(h_cell)
            timeline_inner.append(ruler_box)

        # 2. Main Timeline Canvas Area (Overlay: Background Grid + Foreground Fixed)
        overlay = Gtk.Overlay()
        overlay.set_hexpand(True)
        overlay.set_vexpand(True)
        overlay.add_css_class("timeline-canvas")
        timeline_inner.append(overlay)

        # Background Grid (16 hour slots with horizontal line markers)
        bg_grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bg_grid.set_size_request(-1, TOTAL_HEIGHT)

        for hour in range(DAY_START_HOUR, DAY_END_HOUR):
            hour_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            hour_slot.set_size_request(-1, HOUR_HEIGHT)

            # Top hour solid separator line
            h_sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            h_sep.set_opacity(0.35)
            hour_slot.append(h_sep)

            # Half-hour spacer
            half_box = Gtk.Box()
            half_box.set_size_request(-1, (HOUR_HEIGHT // 2) - 1)
            hour_slot.append(half_box)

            # Half-hour subtle divider
            m_sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            m_sep.set_opacity(0.15)
            hour_slot.append(m_sep)

            bg_grid.append(hour_slot)

        overlay.set_child(bg_grid)

        # Foreground Fixed for dynamic minute-level and parallel cards
        fixed_canvas = Gtk.Fixed()
        fixed_canvas.set_size_request(-1, TOTAL_HEIGHT)
        overlay.add_overlay(fixed_canvas)

        # Fetch tasks and events for this date
        all_tasks = self.storage.get_tasks()
        day_tasks = [t for t in all_tasks if t.scheduled_date == date_str or (t.scheduled_time and not t.scheduled_date and date_str == datetime.now().strftime("%Y-%m-%d"))]

        # Calculate parallel side-by-side assignments
        parallel_layout = layout_parallel_items(day_tasks)

        # Store widgets and layout info for responsive width recalculations
        card_placements = []

        for p in parallel_layout:
            task_item = p['item']
            start_m = p['start_m']
            dur = p['dur']
            col = p['col']
            total_cols = p['total_cols']

            # Top Y offset: minutes from DAY_START_HOUR (07:00)
            mins_from_start = max(0, start_m - (DAY_START_HOUR * 60))
            top_y = int(mins_from_start * (HOUR_HEIGHT / 60.0))
            card_height = max(52, int(dur * (HOUR_HEIGHT / 60.0)))

            card_widget = self._build_canvas_item_card(task_item, start_m, dur, date_str)
            fixed_canvas.put(card_widget, 0, top_y)

            card_placements.append({
                "widget": card_widget,
                "col": col,
                "total_cols": total_cols,
                "top_y": top_y,
                "height": card_height
            })

        # Responsive Tick Callback: automatically adjusts card widths and X offsets to canvas width
        last_allocated_width = [-1]

        def on_canvas_tick(widget, frame_clock):
            curr_w = widget.get_width()
            if curr_w > 50 and curr_w != last_allocated_width[0]:
                last_allocated_width[0] = curr_w
                gap = 6
                margin_left = 6
                margin_right = 6
                net_w = max(100, curr_w - margin_left - margin_right)

                for cp in card_placements:
                    w_child = cp["widget"]
                    t_cols = cp["total_cols"]
                    c_idx = cp["col"]
                    y_pos = cp["top_y"]
                    h_pos = cp["height"]

                    col_w = max(40, int((net_w - (t_cols - 1) * gap) / t_cols))
                    x_pos = int(margin_left + c_idx * (col_w + gap))

                    w_child.set_size_request(col_w, h_pos)
                    fixed_canvas.move(w_child, x_pos, y_pos)

            return GLib.SOURCE_CONTINUE

        fixed_canvas.add_tick_callback(on_canvas_tick)

        # Drop Target on canvas to schedule any task by dropping with minute precision
        self._attach_canvas_drop_target(fixed_canvas, date_str)

        # Click on empty canvas space to quickly schedule at that exact minute
        click_gesture = Gtk.GestureClick.new()
        def on_canvas_clicked(gesture, n_press, x, y):
            # Calculate clicked minute
            fraction = max(0.0, min(1.0, y / float(TOTAL_HEIGHT)))
            clicked_min = int(DAY_START_HOUR * 60 + fraction * (TOTAL_HOURS * 60))
            time_str = format_minutes_to_time(clicked_min)
            self._schedule_at_slot(date_str, time_str)

        click_gesture.connect("released", on_canvas_clicked)
        bg_grid.add_controller(click_gesture)

        return container

    # ==========================================
    # CARD BUILDER WITH SUPERIOR/INFERIOR RESIZE HANDLERS
    # ==========================================
    def _build_canvas_item_card(self, item: Task, start_m: int, dur: int, date_str: str) -> Gtk.Widget:
        is_event = (getattr(item, "item_type", "task") == "event")
        is_open_ended = getattr(item, "is_open_ended", False) or (item.scheduled_duration is None)
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        now_m = now.hour * 60 + now.minute

        is_completed = (item.status == "done" or (is_event and getattr(item, "logged_to_journal", False)))

        is_overdue = False
        if not is_event and not is_completed:
            if date_str < today_str:
                is_overdue = True
            elif date_str == today_str and now_m > (start_m + dur):
                is_overdue = True

        frame = Gtk.Frame()
        if is_completed:
            if is_event:
                frame.add_css_class("calendar-event-card-completed")
            else:
                frame.add_css_class("calendar-task-card-completed")
        elif is_event:
            if is_open_ended:
                frame.add_css_class("calendar-event-card-open")
            else:
                frame.add_css_class("calendar-event-card")
        elif is_overdue:
            frame.add_css_class("calendar-task-card-overdue")
        elif is_open_ended:
            frame.add_css_class("calendar-task-card-open")
        else:
            frame.add_css_class("calendar-task-card")
        frame.add_css_class("draggable-card")

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        card.set_margin_start(4)
        card.set_margin_end(4)
        card.set_margin_top(1)
        card.set_margin_bottom(1)
        frame.set_child(card)

        # 1. Superior Limit Resize Handle (Top Edge)
        top_handle = Gtk.Box()
        top_handle.add_css_class("resize-handle-top")
        top_handle.set_cursor(Gdk.Cursor.new_from_name("ns-resize", None))
        card.append(top_handle)

        drag_top = Gtk.GestureDrag.new()
        def on_top_drag_update(gesture, ox, oy):
            delta_m = int(oy / (HOUR_HEIGHT / 60.0))
            new_start = max(DAY_START_HOUR * 60, min(start_m + dur - 10, start_m + delta_m))
            new_dur = (start_m + dur) - new_start
            self.guide_label.set_text(f"◷ Resizing: {format_minutes_to_time(new_start)} – {format_minutes_to_time(new_start + new_dur)} ({new_dur}m)")
            self.guide_label.set_visible(True)

        def on_top_drag_end(gesture, ox, oy):
            self.guide_label.set_visible(False)
            delta_m = int(oy / (HOUR_HEIGHT / 60.0))
            new_start = max(DAY_START_HOUR * 60, min(start_m + dur - 10, start_m + delta_m))
            new_dur = max(10, (start_m + dur) - new_start)
            new_time_str = format_minutes_to_time(new_start)
            self.storage.update_task(item.id, scheduled_time=new_time_str, scheduled_duration=new_dur, estimated_minutes=new_dur, is_open_ended=False)
            self.refresh()

        drag_top.connect("drag-update", on_top_drag_update)
        drag_top.connect("drag-end", on_top_drag_end)
        top_handle.add_controller(drag_top)

        # 2. Card Content (Middle Body)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        content_box.set_vexpand(True)

        # Header Row: Time range, Project badge, Action button
        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        if is_open_ended and not is_completed:
            time_str = f"{format_minutes_to_time(start_m)} – ?"
        else:
            time_str = f"{format_minutes_to_time(start_m)} – {format_minutes_to_time(start_m + dur)}"
        time_badge = Gtk.Label(label=time_str)
        if is_completed:
            time_badge.add_css_class("tag-pill-completed")
        else:
            time_badge.add_css_class("tag-pill")
        header_row.append(time_badge)

        if is_open_ended and not is_completed:
            type_badge = Gtk.Label(label="◈ Open-ended" if is_event else f"{item.icon} Open-ended")
        else:
            type_badge = Gtk.Label(label=f"◈ Event" if is_event else f"{item.icon} {item.project}")
        if is_completed:
            type_badge.add_css_class("tag-pill-completed")
        else:
            type_badge.add_css_class("tag-pill-project")
        header_row.append(type_badge)

        header_row.append(Gtk.Box(hexpand=True))

        if is_event:
            # Event action: Log to Journal (prompts for actual duration)
            btn_log = Gtk.Button(label="Logged ✓" if item.logged_to_journal else "+ Log to Journal")
            btn_log.add_css_class("btn-secondary" if item.logged_to_journal else "btn-primary")
            if not item.logged_to_journal:
                btn_log.connect("clicked", lambda b, it=item: self._prompt_log_event(it))
            header_row.append(btn_log)
        else:
            # Task action: Complete / Done (prompts for actual duration)
            btn_c = Gtk.Button(label="Done ✓" if item.status == "done" else "Complete")
            btn_c.add_css_class("btn-secondary" if item.status == "done" else "btn-primary")
            btn_c.connect("clicked", lambda b, it=item: self._prompt_complete_task(it))
            header_row.append(btn_c)

            if is_overdue:
                overdue_badge = Gtk.Label(label="⚠️ Missed")
                overdue_badge.add_css_class("tag-pill-alert")
                header_row.append(overdue_badge)

                btn_recal = Gtk.Button(label="⟳ Recalendar")
                btn_recal.add_css_class("btn-secondary")
                btn_recal.set_tooltip_text("Reschedule this uncompleted task")
                btn_recal.connect("clicked", lambda b, task=item: self._open_reschedule_dialog(task))
                header_row.append(btn_recal)

        content_box.append(header_row)

        # Title & Notes
        title_lbl = Gtk.Label(label=item.title)
        title_lbl.add_css_class("text-title")
        title_lbl.set_halign(Gtk.Align.START)
        title_lbl.set_wrap(False)
        title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        if is_completed:
            title_lbl.add_css_class("calendar-card-title-completed")
            title_lbl.add_css_class("text-muted")
        content_box.append(title_lbl)

        # Double-click to edit card
        edit_gesture = Gtk.GestureClick.new()
        def on_card_clicked(gesture, n_press, x, y):
            if n_press == 2:
                win = self.get_root()
                dlg = NewTaskDialog(win, self.storage, self.refresh, edit_task=item)
                dlg.present()
        edit_gesture.connect("released", on_card_clicked)
        content_box.add_controller(edit_gesture)

        card.append(content_box)

        # Make center body draggable across time and dates
        self._make_widget_draggable(card, item.id)

        # 3. Inferior Limit Resize Handle (Bottom Edge)
        bot_handle = Gtk.Box()
        bot_handle.add_css_class("resize-handle-bottom")
        bot_handle.set_cursor(Gdk.Cursor.new_from_name("ns-resize", None))
        card.append(bot_handle)

        drag_bot = Gtk.GestureDrag.new()
        def on_bot_drag_update(gesture, ox, oy):
            delta_m = int(oy / (HOUR_HEIGHT / 60.0))
            new_dur = max(10, dur + delta_m)
            self.guide_label.set_text(f"◷ Resizing: {format_minutes_to_time(start_m)} – {format_minutes_to_time(start_m + new_dur)} ({new_dur}m)")
            self.guide_label.set_visible(True)

        def on_bot_drag_end(gesture, ox, oy):
            self.guide_label.set_visible(False)
            delta_m = int(oy / (HOUR_HEIGHT / 60.0))
            new_dur = max(10, dur + delta_m)
            self.storage.update_task(item.id, scheduled_duration=new_dur, estimated_minutes=new_dur)
            self.refresh()

        drag_bot.connect("drag-update", on_bot_drag_update)
        drag_bot.connect("drag-end", on_bot_drag_end)
        bot_handle.add_controller(drag_bot)

        # Make frame draggable across time and dates
        self._make_widget_draggable(frame, item.id)

        return frame

    # ==========================================
    # DRAG & DROP CONTROLLERS
    # ==========================================
    def _make_widget_draggable(self, widget: Gtk.Widget, task_id: str):
        drag_source = Gtk.DragSource.new()
        drag_source.set_actions(Gdk.DragAction.MOVE)

        def on_prepare(ds, x, y, tid=task_id):
            val = GObject.Value(GObject.TYPE_STRING, tid)
            return Gdk.ContentProvider.new_for_value(val)

        drag_source.connect("prepare", on_prepare)
        widget.add_controller(drag_source)

    def _attach_canvas_drop_target(self, widget: Gtk.Widget, target_date: str):
        drop_target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)

        def on_motion(dt, x, y):
            fraction = max(0.0, min(1.0, y / float(TOTAL_HEIGHT)))
            min_val = int(DAY_START_HOUR * 60 + fraction * (TOTAL_HOURS * 60))
            time_str = format_minutes_to_time(min_val)
            self.guide_label.set_text(f"◷ Drop to schedule at {time_str}")
            self.guide_label.set_visible(True)
            return Gdk.DragAction.MOVE

        def on_leave(dt):
            self.guide_label.set_visible(False)

        def on_drop(dt, val, x, y):
            self.guide_label.set_visible(False)
            task_id = str(val)
            fraction = max(0.0, min(1.0, y / float(TOTAL_HEIGHT)))
            min_val = int(DAY_START_HOUR * 60 + fraction * (TOTAL_HOURS * 60))
            scheduled_time = format_minutes_to_time(min_val)
            self._on_task_dropped(task_id, target_date, scheduled_time)
            return True

        drop_target.connect("motion", on_motion)
        drop_target.connect("leave", on_leave)
        drop_target.connect("drop", on_drop)
        widget.add_controller(drop_target)

    def _on_task_dropped(self, task_id: str, target_date: str, target_time: str):
        self.storage.update_task(task_id, scheduled_date=target_date, scheduled_time=target_time)
        self.refresh()

    def _complete_task(self, task_id: str, is_done: bool):
        self.storage.complete_task(task_id, is_done)
        self.refresh()

    def _prompt_complete_task(self, item: Task):
        if item.status == "done":
            self.storage.complete_task(item.id, False)
            self.refresh()
        else:
            win = self.get_root()
            dlg = TaskCompletionDialog(win, self.storage, item, is_event=False, on_done_cb=self.refresh)
            dlg.present()

    def _log_event_to_journal(self, task_id: str):
        self.storage.log_event_to_journal(task_id)
        self.refresh()

    def _prompt_log_event(self, item: Task):
        win = self.get_root()
        dlg = TaskCompletionDialog(win, self.storage, item, is_event=True, on_done_cb=self.refresh)
        dlg.present()

    def _schedule_at_slot(self, date_str: str, hour_str: str):
        win = self.get_root()
        dlg = NewTaskDialog(
            win,
            self.storage,
            self.refresh,
            default_type="task",
            prefill_date=date_str,
            prefill_time=hour_str
        )
        dlg.present()

    # ==========================================
    # MULTI-DAY & MONTH VIEWS
    # ==========================================
    def _render_multiday_view(self, start_date: datetime, num_days: int):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        self.content_area.append(scrolled)

        columns_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        columns_box.set_hexpand(True)
        scrolled.set_child(columns_box)

        days_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        for day_idx in range(num_days):
            d_current = start_date + timedelta(days=day_idx)
            d_str = d_current.strftime("%Y-%m-%d")
            is_today = (d_current.date() == datetime.now().date())

            col_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            col_box.set_hexpand(True)
            col_box.add_css_class("card-box")

            header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            lbl_w = Gtk.Label(label=f"{days_short[d_current.weekday()]} {d_current.day}")
            lbl_w.add_css_class("text-heading" if is_today else "text-title")
            header_box.append(lbl_w)
            col_box.append(header_box)

            # Render individual day timeline (show ruler only on the first day)
            day_timeline = self._create_day_timeline(d_str, show_ruler=(day_idx == 0))
            col_box.append(day_timeline)
            columns_box.append(col_box)

    def _render_month_view(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        self.content_area.append(scrolled)

        month_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scrolled.set_child(month_box)

        days_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for dname in day_names:
            lbl = Gtk.Label(label=dname)
            lbl.add_css_class("text-title")
            lbl.set_hexpand(True)
            days_header.append(lbl)
        month_box.append(days_header)

        cal = calendar.monthcalendar(self.current_date.year, self.current_date.month)
        all_tasks = self.storage.get_tasks()

        for week in cal:
            week_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            week_row.set_vexpand(True)
            for day in week:
                cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                cell.set_hexpand(True)
                cell.set_size_request(100, 80)
                cell.add_css_class("card-box")

                if day != 0:
                    d_obj = datetime(self.current_date.year, self.current_date.month, day)
                    d_str = d_obj.strftime("%Y-%m-%d")
                    is_today = (d_obj.date() == datetime.now().date())

                    day_lbl = Gtk.Label(label=str(day))
                    day_lbl.add_css_class("text-heading" if is_today else "text-title")
                    day_lbl.set_halign(Gtk.Align.START)
                    cell.append(day_lbl)

                    day_tasks = [t for t in all_tasks if t.scheduled_date == d_str]
                    if day_tasks:
                        done_count = sum(1 for t in day_tasks if t.status == "done" or getattr(t, "logged_to_journal", False))
                        pending_count = len(day_tasks) - done_count

                        pills_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                        pills_box.set_halign(Gtk.Align.START)

                        if pending_count > 0:
                            t_pill = Gtk.Label(label=f"{pending_count} pending")
                            t_pill.add_css_class("tag-pill")
                            pills_box.append(t_pill)
                        if done_count > 0:
                            d_pill = Gtk.Label(label=f"{done_count} completed")
                            d_pill.add_css_class("tag-pill-completed")
                            d_pill.set_halign(Gtk.Align.START)
                            pills_box.append(d_pill)

                        cell.append(pills_box)

                    jump_btn = Gtk.Button(label="View day")
                    jump_btn.add_css_class("btn-ghost")
                    jump_btn.connect("clicked", lambda b, dobj=d_obj: self._jump_to_day(dobj))
                    cell.append(jump_btn)
                else:
                    cell.set_sensitive(False)

                week_row.append(cell)
            month_box.append(week_row)

    def _jump_to_day(self, d_obj: datetime):
        self.current_date = d_obj
        self.active_mode = "1d"
        for mid, b in self.mode_buttons.items():
            if mid == "1d":
                b.add_css_class("active")
            else:
                b.remove_css_class("active")
        self.refresh()


class CalendarContainer(Gtk.Overlay):
    """
    Calendar tab container with live ASCII Sharks ocean animation swimming behind
    the translucent frosted glass timeline canvas and drawer.
    """
    def __init__(self, storage):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)

        # Bottom Layer: Ambient ASCII Sharks Ocean Engine
        self.webview = WebKit.WebView()
        self.webview.set_hexpand(True)
        self.webview.set_vexpand(True)
        settings = self.webview.get_settings()
        settings.set_enable_webgl(True)
        settings.set_allow_file_access_from_file_urls(True)
        settings.set_allow_universal_access_from_file_urls(True)

        assets_dir = Path(__file__).resolve().parent / "shark_assets"
        html_file = assets_dir / "calendar_sharks.html"
        self.webview.load_uri(html_file.as_uri())

        self.set_child(self.webview)

        # Top Layer: Interactive Calendar View with Translucent Canvas
        self.cal_view = CalendarView(storage)
        self.add_overlay(self.cal_view)

    def refresh(self):
        if hasattr(self.cal_view, "refresh"):
            self.cal_view.refresh()

    def __getattr__(self, name):
        return getattr(self.cal_view, name)
