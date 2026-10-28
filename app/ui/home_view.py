"""
Home View: Apple-style Dashboard with Workday Attendance (Arrival & Departure),
Daily Goal Convergence, and Tiny Reports of Undone Tasks & Today's Schedule.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from datetime import datetime
from models import Task
from ui.dialogs import NewTaskDialog, EditWorkdayDialog, TaskCompletionDialog


class HomeView(Gtk.Box):
    def __init__(self, storage, on_navigate_cb=None, on_start_timer_cb=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.storage = storage
        self.on_navigate_cb = on_navigate_cb
        self.on_start_timer_cb = on_start_timer_cb

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Top-level scrolled window for graceful scaling on any display
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        self.append(scrolled)

        # Content container
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.content_box.set_margin_top(16)
        self.content_box.set_margin_bottom(24)
        self.content_box.set_margin_start(24)
        self.content_box.set_margin_end(24)
        scrolled.set_child(self.content_box)

        # 1. Header / Greeting Bar
        self._build_header_bar()

        # 2. Hero Card: Workday Presence (Arrival & Departure)
        self._build_workday_card()

        # 3. Middle Metrics Strip (3 cards: Pending Tasks, Schedule, Goal Target)
        self._build_metrics_strip()

        # 4. Bottom Two-Column Dashboard (Tiny Reports: Undone Tasks & Today's Schedule)
        self._build_tiny_reports()

    def _build_header_bar(self):
        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        # Title & Subtitle
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.lbl_greeting = Gtk.Label()
        self.lbl_greeting.add_css_class("text-heading")
        self.lbl_greeting.set_halign(Gtk.Align.START)
        title_box.append(self.lbl_greeting)

        self.lbl_date_sub = Gtk.Label()
        self.lbl_date_sub.add_css_class("text-muted")
        self.lbl_date_sub.set_halign(Gtk.Align.START)
        title_box.append(self.lbl_date_sub)

        header_row.append(title_box)
        header_row.append(Gtk.Box(hexpand=True))

        # Quick Actions
        btn_new_task = Gtk.Button(label="+ Task")
        btn_new_task.add_css_class("btn-primary")
        btn_new_task.connect("clicked", lambda b: self._open_new_item("task"))
        header_row.append(btn_new_task)

        btn_new_event = Gtk.Button(label="+ Schedule")
        btn_new_event.add_css_class("btn-secondary")
        btn_new_event.connect("clicked", lambda b: self._open_new_item("event"))
        header_row.append(btn_new_event)

        btn_refresh = Gtk.Button(label="⟳ Refresh")
        btn_refresh.add_css_class("btn-secondary")
        btn_refresh.connect("clicked", lambda b: self.refresh())
        header_row.append(btn_refresh)

        self.content_box.append(header_row)

    def _build_workday_card(self):
        self.card_workday = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.card_workday.add_css_class("home-hero-card")

        # Top row of Workday Card: Title + Status Pill
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_w_title = Gtk.Label(label="⏱ Workday Attendance & Presence")
        lbl_w_title.add_css_class("text-title")
        lbl_w_title.set_halign(Gtk.Align.START)
        top_row.append(lbl_w_title)

        top_row.append(Gtk.Box(hexpand=True))

        self.lbl_status_pill = Gtk.Label()
        self.lbl_status_pill.set_halign(Gtk.Align.END)
        top_row.append(self.lbl_status_pill)
        self.card_workday.append(top_row)

        # Two Columns: Left = Arrival (Check-In), Right = Departure (Check-Out)
        slots_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        slots_row.set_homogeneous(True)

        # Arrival Column
        self.slot_arr = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.slot_arr.add_css_class("home-workday-slot")

        lbl_arr_tag = Gtk.Label(label="ARRIVAL (CHECK-IN)")
        lbl_arr_tag.add_css_class("text-muted")
        lbl_arr_tag.set_halign(Gtk.Align.START)
        self.slot_arr.append(lbl_arr_tag)

        self.lbl_arr_time = Gtk.Label(label="--:--")
        self.lbl_arr_time.add_css_class("workday-time-large")
        self.lbl_arr_time.set_halign(Gtk.Align.START)
        self.slot_arr.append(self.lbl_arr_time)

        self.lbl_arr_sub = Gtk.Label(label="Not recorded yet")
        self.lbl_arr_sub.add_css_class("text-muted")
        self.lbl_arr_sub.set_halign(Gtk.Align.START)
        self.slot_arr.append(self.lbl_arr_sub)

        self.box_arr_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.box_arr_actions.set_margin_top(4)
        self.slot_arr.append(self.box_arr_actions)
        slots_row.append(self.slot_arr)

        # Departure Column
        self.slot_dep = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.slot_dep.add_css_class("home-workday-slot")

        lbl_dep_tag = Gtk.Label(label="DEPARTURE (CHECK-OUT)")
        lbl_dep_tag.add_css_class("text-muted")
        lbl_dep_tag.set_halign(Gtk.Align.START)
        self.slot_dep.append(lbl_dep_tag)

        self.lbl_dep_time = Gtk.Label(label="--:--")
        self.lbl_dep_time.add_css_class("workday-time-large")
        self.lbl_dep_time.set_halign(Gtk.Align.START)
        self.slot_dep.append(self.lbl_dep_time)

        self.lbl_dep_sub = Gtk.Label(label="Projected departure based on target")
        self.lbl_dep_sub.add_css_class("text-muted")
        self.lbl_dep_sub.set_halign(Gtk.Align.START)
        self.slot_dep.append(self.lbl_dep_sub)

        self.box_dep_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.box_dep_actions.set_margin_top(4)
        self.slot_dep.append(self.box_dep_actions)
        slots_row.append(self.slot_dep)

        self.card_workday.append(slots_row)

        # Card Footer: manual edit link and live summary
        footer_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        footer_row.set_margin_top(2)

        btn_edit_manual = Gtk.Button(label="✎ Edit Workday Times")
        btn_edit_manual.add_css_class("btn-secondary")
        btn_edit_manual.connect("clicked", lambda b: self._open_edit_workday())
        footer_row.append(btn_edit_manual)

        footer_row.append(Gtk.Box(hexpand=True))

        self.lbl_workday_summary = Gtk.Label()
        self.lbl_workday_summary.add_css_class("text-muted")
        self.lbl_workday_summary.set_halign(Gtk.Align.END)
        footer_row.append(self.lbl_workday_summary)

        self.card_workday.append(footer_row)
        self.content_box.append(self.card_workday)

    def _build_metrics_strip(self):
        metrics_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        metrics_row.set_homogeneous(True)

        # Card 1: Pending Tasks
        c1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        c1.add_css_class("metric-card")

        c1_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_c1_title = Gtk.Label(label="Undone Tasks")
        lbl_c1_title.add_css_class("text-title")
        lbl_c1_title.set_halign(Gtk.Align.START)
        c1_top.append(lbl_c1_title)
        c1_top.append(Gtk.Box(hexpand=True))
        btn_c1 = Gtk.Button(label="View →")
        btn_c1.add_css_class("btn-ghost")
        btn_c1.connect("clicked", lambda b: self._navigate("tasks"))
        c1_top.append(btn_c1)
        c1.append(c1_top)

        self.lbl_m_tasks_val = Gtk.Label(label="0")
        self.lbl_m_tasks_val.add_css_class("metric-number")
        self.lbl_m_tasks_val.set_halign(Gtk.Align.START)
        c1.append(self.lbl_m_tasks_val)

        self.lbl_m_tasks_sub = Gtk.Label(label="All caught up")
        self.lbl_m_tasks_sub.add_css_class("text-muted")
        self.lbl_m_tasks_sub.set_halign(Gtk.Align.START)
        c1.append(self.lbl_m_tasks_sub)
        metrics_row.append(c1)

        # Card 2: Today's Schedule
        c2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        c2.add_css_class("metric-card")

        c2_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_c2_title = Gtk.Label(label="Scheduled Today")
        lbl_c2_title.add_css_class("text-title")
        lbl_c2_title.set_halign(Gtk.Align.START)
        c2_top.append(lbl_c2_title)
        c2_top.append(Gtk.Box(hexpand=True))
        btn_c2 = Gtk.Button(label="Calendar →")
        btn_c2.add_css_class("btn-ghost")
        btn_c2.connect("clicked", lambda b: self._navigate("calendar"))
        c2_top.append(btn_c2)
        c2.append(c2_top)

        self.lbl_m_sched_val = Gtk.Label(label="0")
        self.lbl_m_sched_val.add_css_class("metric-number")
        self.lbl_m_sched_val.set_halign(Gtk.Align.START)
        c2.append(self.lbl_m_sched_val)

        self.lbl_m_sched_sub = Gtk.Label(label="No events scheduled")
        self.lbl_m_sched_sub.add_css_class("text-muted")
        self.lbl_m_sched_sub.set_halign(Gtk.Align.START)
        c2.append(self.lbl_m_sched_sub)
        metrics_row.append(c2)

        # Card 3: Target Hours Convergence
        c3 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        c3.add_css_class("metric-card")

        c3_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_c3_title = Gtk.Label(label="Daily Work Goal")
        lbl_c3_title.add_css_class("text-title")
        lbl_c3_title.set_halign(Gtk.Align.START)
        c3_top.append(lbl_c3_title)
        c3_top.append(Gtk.Box(hexpand=True))
        btn_c3 = Gtk.Button(label="Journal →")
        btn_c3.add_css_class("btn-ghost")
        btn_c3.connect("clicked", lambda b: self._navigate("journal"))
        c3_top.append(btn_c3)
        c3.append(c3_top)

        self.lbl_m_target_val = Gtk.Label(label="7h 00m remaining")
        self.lbl_m_target_val.add_css_class("metric-number")
        self.lbl_m_target_val.set_halign(Gtk.Align.START)
        c3.append(self.lbl_m_target_val)

        self.lbl_m_target_sub = Gtk.Label(label="Effective work: 0h 00m / 7h 00m")
        self.lbl_m_target_sub.add_css_class("text-muted")
        self.lbl_m_target_sub.set_halign(Gtk.Align.START)
        c3.append(self.lbl_m_target_sub)
        metrics_row.append(c3)

        self.content_box.append(metrics_row)

    def _build_tiny_reports(self):
        reports_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        reports_row.set_homogeneous(True)

        # Left Column: Undone Tasks
        panel_tasks = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel_tasks.add_css_class("report-panel")

        t_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_t_title = Gtk.Label(label="Undone Tasks")
        lbl_t_title.add_css_class("text-title")
        lbl_t_title.set_halign(Gtk.Align.START)
        t_header.append(lbl_t_title)

        self.lbl_t_badge = Gtk.Label(label="0")
        self.lbl_t_badge.add_css_class("tag-pill")
        t_header.append(self.lbl_t_badge)

        t_header.append(Gtk.Box(hexpand=True))

        btn_view_all_tasks = Gtk.Button(label="View All Tasks →")
        btn_view_all_tasks.add_css_class("btn-ghost")
        btn_view_all_tasks.connect("clicked", lambda b: self._navigate("tasks"))
        t_header.append(btn_view_all_tasks)
        panel_tasks.append(t_header)

        self.tasks_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        panel_tasks.append(self.tasks_list_box)
        reports_row.append(panel_tasks)

        # Right Column: Today's Schedule & Events
        panel_sched = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel_sched.add_css_class("report-panel")

        s_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_s_title = Gtk.Label(label="Today's Schedule & Events")
        lbl_s_title.add_css_class("text-title")
        lbl_s_title.set_halign(Gtk.Align.START)
        s_header.append(lbl_s_title)

        self.lbl_s_badge = Gtk.Label(label="0")
        self.lbl_s_badge.add_css_class("tag-pill")
        s_header.append(self.lbl_s_badge)

        s_header.append(Gtk.Box(hexpand=True))

        btn_open_cal = Gtk.Button(label="Open Calendar →")
        btn_open_cal.add_css_class("btn-ghost")
        btn_open_cal.connect("clicked", lambda b: self._navigate("calendar"))
        s_header.append(btn_open_cal)
        panel_sched.append(s_header)

        self.sched_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        panel_sched.append(self.sched_list_box)
        reports_row.append(panel_sched)

        # Reminder strip for uncompleted calendar tasks from previous days
        self.missed_reminder_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content_box.append(self.missed_reminder_box)

        self.content_box.append(reports_row)

    def refresh(self):
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        # 1. Update Greeting & Date
        hour = now.hour
        if hour < 12:
            greet = "Good morning"
        elif hour < 19:
            greet = "Good afternoon"
        else:
            greet = "Good evening"

        self.lbl_greeting.set_text(f"{greet}, Lázaro")
        self.lbl_date_sub.set_text(now.strftime("%A, %B %d, %Y • Daily Overview & Attendance"))

        # 2. Fetch Data
        recon = self.storage.get_daily_reconciliation(today_str)
        entries = self.storage.load_journal_entries_for_date(today_str)
        undone_tasks = self.storage.get_undone_tasks()
        today_items = self.storage.get_today_scheduled_items(today_str)

        # 3. Workday Attendance State
        self._update_workday_card(recon, entries, today_str, now)

        # 4. Metrics Strip
        self._update_metrics(recon, entries, undone_tasks, today_items)

        # 5. Missed Scheduled Tasks Reminder Banner
        while child := self.missed_reminder_box.get_first_child():
            self.missed_reminder_box.remove(child)

        missed_past = self.storage.get_missed_scheduled_tasks(include_today_overdue=False)
        if missed_past:
            rem_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            rem_bar.add_css_class("home-reminder-strip")
            rem_bar.set_margin_bottom(12)

            lbl_warn = Gtk.Label(label="⚠️")
            rem_bar.append(lbl_warn)

            txt = f"Reminder: You have {len(missed_past)} scheduled task(s) from previous days that were not completed."
            lbl_msg = Gtk.Label(label=txt)
            lbl_msg.add_css_class("text-title")
            lbl_msg.set_halign(Gtk.Align.START)
            rem_bar.append(lbl_msg)

            rem_bar.append(Gtk.Box(hexpand=True))

            btn_rec_all = Gtk.Button(label="⟳ Recalendar All to Today")
            btn_rec_all.add_css_class("btn-secondary")
            btn_rec_all.set_tooltip_text("Move all missed tasks from past days onto today's schedule")
            btn_rec_all.connect("clicked", lambda b: self._on_recalendar_all_to_today())
            rem_bar.append(btn_rec_all)

            btn_go_cal = Gtk.Button(label="Open Calendar →")
            btn_go_cal.add_css_class("btn-ghost")
            btn_go_cal.connect("clicked", lambda b: self._navigate("calendar"))
            rem_bar.append(btn_go_cal)

            self.missed_reminder_box.append(rem_bar)

        # 6. Tiny Reports Lists
        self._update_tasks_report(undone_tasks)
        self._update_schedule_report(today_items)

    def _update_workday_card(self, recon, entries, today_str, now):
        arr = recon.arrival_time
        dep = recon.departure_time

        # Clear existing dynamic action buttons in slots
        while child := self.box_arr_actions.get_first_child():
            self.box_arr_actions.remove(child)
        while child := self.box_dep_actions.get_first_child():
            self.box_dep_actions.remove(child)

        # Clean old pill classes
        self.lbl_status_pill.remove_css_class("status-pill-active")
        self.lbl_status_pill.remove_css_class("status-pill-idle")
        self.lbl_status_pill.remove_css_class("status-pill-done")

        break_project = self.storage.get_break_project_name()
        span_m = recon.calculate_workday_span_minutes()
        proj_dep = recon.calculate_expected_departure_time(entries, break_project)
        effective_m = recon.calculate_effective_work_minutes(entries, break_project)
        total_break_m = recon.calculate_total_break_minutes(entries, break_project)

        target_h = recon.target_work_minutes // 60
        target_m = recon.target_work_minutes % 60

        # Arrival Column Display
        if arr:
            self.lbl_arr_time.set_text(arr)
            self.lbl_arr_sub.set_text(f"Checked in at {arr}")

            btn_edit_arr = Gtk.Button(label="✎ Edit")
            btn_edit_arr.add_css_class("btn-secondary")
            btn_edit_arr.connect("clicked", lambda b: self._open_edit_workday())
            self.box_arr_actions.append(btn_edit_arr)

            btn_clear_arr = Gtk.Button(label="Clear")
            btn_clear_arr.add_css_class("btn-secondary")
            btn_clear_arr.connect("clicked", lambda b: self._clear_arrival(today_str))
            self.box_arr_actions.append(btn_clear_arr)
        else:
            self.lbl_arr_time.set_text("--:--")
            self.lbl_arr_sub.set_text("Not recorded yet")

            btn_arrived_now = Gtk.Button(label="⦿ Arrived Now")
            btn_arrived_now.add_css_class("btn-primary")
            btn_arrived_now.connect("clicked", lambda b: self._set_arrival_now(today_str))
            self.box_arr_actions.append(btn_arrived_now)

        # Departure Column Display
        if dep:
            self.lbl_dep_time.set_text(dep)
            if span_m is not None:
                self.lbl_dep_sub.set_text(f"Workday span: {span_m // 60}h {span_m % 60:02d}m")
            else:
                self.lbl_dep_sub.set_text(f"Left at {dep}")

            btn_edit_dep = Gtk.Button(label="✎ Edit")
            btn_edit_dep.add_css_class("btn-secondary")
            btn_edit_dep.connect("clicked", lambda b: self._open_edit_workday())
            self.box_dep_actions.append(btn_edit_dep)

            btn_clear_dep = Gtk.Button(label="Clear")
            btn_clear_dep.add_css_class("btn-secondary")
            btn_clear_dep.connect("clicked", lambda b: self._clear_departure(today_str))
            self.box_dep_actions.append(btn_clear_dep)
        else:
            self.lbl_dep_time.set_text("--:--")
            if arr:
                excess_break = max(0, total_break_m - recon.target_break_minutes)
                if excess_break > 0:
                    break_hint = f"{target_h}h incl. break + {excess_break}m extra"
                else:
                    break_hint = f"{target_h}h, incl. {recon.target_break_minutes}m break"
                self.lbl_dep_sub.set_text(f"Projected departure: {proj_dep or 'N/A'} ({break_hint})")

                btn_left_now = Gtk.Button(label="⏏ Left Now")
                btn_left_now.add_css_class("btn-primary")
                btn_left_now.connect("clicked", lambda b: self._set_departure_now(today_str))
                self.box_dep_actions.append(btn_left_now)
            else:
                self.lbl_dep_sub.set_text(f"Target: {target_h}h {target_m:02d}m workday (incl. {recon.target_break_minutes}m break)")
                btn_set_dep = Gtk.Button(label="Set Departure...")
                btn_set_dep.add_css_class("btn-secondary")
                btn_set_dep.connect("clicked", lambda b: self._open_edit_workday())
                self.box_dep_actions.append(btn_set_dep)

        # Workday overall status pill & summary text
        if arr and dep:
            self.lbl_status_pill.set_text("✓ Workday Completed")
            self.lbl_status_pill.add_css_class("status-pill-done")
            s_str = f"{span_m // 60}h {span_m % 60:02d}m" if span_m is not None else "--"
            self.lbl_workday_summary.set_text(f"Total workday span: {s_str}  •  Effective worked: {effective_m // 60}h {effective_m % 60:02d}m")
        elif arr and not dep:
            self.lbl_status_pill.set_text("● In Office / Active")
            self.lbl_status_pill.add_css_class("status-pill-active")
            elapsed = f"{span_m // 60}h {span_m % 60:02d}m" if span_m is not None else "--"
            self.lbl_workday_summary.set_text(f"Elapsed: {elapsed}  •  Daily Target: {target_h}h {target_m:02d}m (incl. {recon.target_break_minutes}m break)  •  Break: {total_break_m}m / {recon.target_break_minutes}m")
        else:
            self.lbl_status_pill.set_text("○ Not Checked In")
            self.lbl_status_pill.add_css_class("status-pill-idle")
            self.lbl_workday_summary.set_text(f"Daily Target: {target_h}h {target_m:02d}m (incl. {recon.target_break_minutes}m break)  •  Break Budget: {recon.target_break_minutes}m")

    def _update_metrics(self, recon, entries, undone_tasks, today_items):
        break_project = self.storage.get_break_project_name()
        # 1. Undone tasks metric
        count_tasks = len(undone_tasks)
        self.lbl_m_tasks_val.set_text(str(count_tasks))
        high_prio = sum(1 for t in undone_tasks if t.priority == "high" or t.priority == "alta")
        if count_tasks == 0:
            self.lbl_m_tasks_sub.set_text("All caught up! ✓")
        elif high_prio > 0:
            self.lbl_m_tasks_sub.set_text(f"{high_prio} high priority pending")
        else:
            self.lbl_m_tasks_sub.set_text(f"{count_tasks} pending tasks")

        # 2. Today's schedule metric
        count_sched = len(today_items)
        self.lbl_m_sched_val.set_text(str(count_sched))
        missed_past = self.storage.get_missed_scheduled_tasks(include_today_overdue=False)
        if count_sched == 0:
            if missed_past:
                self.lbl_m_sched_sub.set_text(f"⚠️ {len(missed_past)} uncompleted from past days")
            else:
                self.lbl_m_sched_sub.set_text("Free schedule for today")
        else:
            if missed_past:
                self.lbl_m_sched_sub.set_text(f"⚠️ {len(missed_past)} past uncompleted tasks")
            else:
                next_item = today_items[0]
                t_str = f" at {next_item.scheduled_time}" if next_item.scheduled_time else ""
                self.lbl_m_sched_sub.set_text(f"Next: {next_item.title[:22]}{t_str}")

        # 3. Goal convergence metric
        eff_m = recon.calculate_effective_work_minutes(entries, break_project)
        credited_b = recon.calculate_credited_break_minutes(entries, break_project)
        rem_m = recon.calculate_remaining_minutes(entries, break_project)
        if rem_m > 0:
            self.lbl_m_target_val.set_text(f"{rem_m // 60}h {rem_m % 60:02d}m left")
        else:
            overtime = abs(rem_m)
            self.lbl_m_target_val.set_text(f"Goal Met (+{overtime // 60}h {overtime % 60:02d}m)")

        target_h = recon.target_work_minutes // 60
        target_m = recon.target_work_minutes % 60
        if credited_b > 0:
            self.lbl_m_target_sub.set_text(f"Effective: {eff_m // 60}h {eff_m % 60:02d}m + {credited_b}m break / {target_h}h {target_m:02d}m")
        else:
            self.lbl_m_target_sub.set_text(f"Effective: {eff_m // 60}h {eff_m % 60:02d}m / {target_h}h {target_m:02d}m (incl. {recon.target_break_minutes}m break)")

    def _update_tasks_report(self, undone_tasks):
        self.lbl_t_badge.set_text(str(len(undone_tasks)))

        while child := self.tasks_list_box.get_first_child():
            self.tasks_list_box.remove(child)

        if not undone_tasks:
            empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            empty_box.set_margin_top(16)
            empty_box.set_margin_bottom(16)
            empty_box.set_halign(Gtk.Align.CENTER)

            lbl_empty = Gtk.Label(label="✓ All tasks completed! No pending items.")
            lbl_empty.add_css_class("text-muted")
            empty_box.append(lbl_empty)

            btn_add = Gtk.Button(label="+ Create New Task")
            btn_add.add_css_class("btn-secondary")
            btn_add.set_halign(Gtk.Align.CENTER)
            btn_add.connect("clicked", lambda b: self._open_new_item("task"))
            empty_box.append(btn_add)

            self.tasks_list_box.append(empty_box)
            return

        # Show up to 7 undone tasks
        for t in undone_tasks[:7]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("report-row-card")

            # Checkbox to complete task directly from Home!
            chk = Gtk.CheckButton()
            chk.set_active(False)
            chk.connect("toggled", self._on_task_checked, t.id)
            row.append(chk)

            # Project Tag
            lbl_proj = Gtk.Label(label=f"{t.icon} {t.project}")
            lbl_proj.add_css_class("tag-pill-project")
            row.append(lbl_proj)

            # Title
            lbl_title = Gtk.Label(label=t.title)
            lbl_title.add_css_class("text-title")
            lbl_title.set_halign(Gtk.Align.START)
            lbl_title.set_hexpand(True)
            lbl_title.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
            row.append(lbl_title)

            # High priority tag
            if t.priority in ["high", "alta"]:
                lbl_prio = Gtk.Label(label="High")
                lbl_prio.add_css_class("tag-pill-high")
                row.append(lbl_prio)

            # Scheduled time tag if scheduled today
            if t.scheduled_date == datetime.now().strftime("%Y-%m-%d") and t.scheduled_time:
                lbl_time = Gtk.Label(label=f"◷ {t.scheduled_time}")
                lbl_time.add_css_class("tag-pill")
                row.append(lbl_time)

            # Focus Timer Launch button
            btn_focus = Gtk.Button(label="▷ Focus")
            btn_focus.add_css_class("btn-secondary")
            btn_focus.connect("clicked", lambda b, task=t: self._on_start_focus(task))
            row.append(btn_focus)

            self.tasks_list_box.append(row)

    def _update_schedule_report(self, today_items):
        now = datetime.now()
        self.lbl_s_badge.set_text(str(len(today_items)))

        while child := self.sched_list_box.get_first_child():
            self.sched_list_box.remove(child)

        if not today_items:
            empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            empty_box.set_margin_top(16)
            empty_box.set_margin_bottom(16)
            empty_box.set_halign(Gtk.Align.CENTER)

            lbl_empty = Gtk.Label(label="◷ No events or tasks scheduled for today.")
            lbl_empty.add_css_class("text-muted")
            empty_box.append(lbl_empty)

            btn_sched = Gtk.Button(label="+ Schedule an Event / Task")
            btn_sched.add_css_class("btn-secondary")
            btn_sched.set_halign(Gtk.Align.CENTER)
            btn_sched.connect("clicked", lambda b: self._open_new_item("event"))
            empty_box.append(btn_sched)

            self.sched_list_box.append(empty_box)
            return

        for item in today_items[:7]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("report-row-card")

            # Time Badge
            t_str = item.scheduled_time or "All day"
            dur_str = f" ({item.scheduled_duration}m)" if item.scheduled_duration else ""
            lbl_time = Gtk.Label(label=f"◷ {t_str}{dur_str}")
            lbl_time.add_css_class("tag-pill")
            row.append(lbl_time)

            # Type Badge (Event vs Task)
            is_event = (getattr(item, "item_type", "task") == "event")
            lbl_type = Gtk.Label(label="◈ Event" if is_event else "⊞ Task")
            lbl_type.add_css_class("tag-pill-high" if is_event else "tag-pill")
            row.append(lbl_type)

            # Project Tag
            lbl_proj = Gtk.Label(label=f"{item.icon} {item.project}")
            lbl_proj.add_css_class("tag-pill-project")
            row.append(lbl_proj)

            # Title
            lbl_title = Gtk.Label(label=item.title)
            lbl_title.add_css_class("text-title")
            lbl_title.set_halign(Gtk.Align.START)
            lbl_title.set_hexpand(True)
            lbl_title.set_ellipsize(3)
            row.append(lbl_title)

            # Action: If Event, show "Log to Journal"; if Task, show completion status or Done button
            if is_event:
                if getattr(item, "logged_to_journal", False):
                    lbl_logged = Gtk.Label(label="Logged ✓")
                    lbl_logged.add_css_class("text-muted")
                    row.append(lbl_logged)
                else:
                    btn_log = Gtk.Button(label="+ Log")
                    btn_log.add_css_class("btn-secondary")
                    btn_log.connect("clicked", lambda b, it=item: self._on_log_event(it))
                    row.append(btn_log)
            else:
                chk = Gtk.CheckButton()
                chk.set_active(item.status == "done")
                chk.connect("toggled", self._on_task_checked, item.id)
                row.append(chk)

                # Check if task is overdue / missed today
                if item.status != "done" and item.scheduled_time:
                    now_m = now.hour * 60 + now.minute
                    try:
                        parts = item.scheduled_time.split(":")
                        start_m = int(parts[0]) * 60 + int(parts[1])
                        dur = item.scheduled_duration or 30
                        if now_m > (start_m + dur):
                            lbl_over = Gtk.Label(label="⚠️ Missed")
                            lbl_over.add_css_class("tag-pill-alert")
                            row.append(lbl_over)

                            btn_rec = Gtk.Button(label="⟳ Recalendar")
                            btn_rec.add_css_class("btn-secondary")
                            btn_rec.set_tooltip_text("Reschedule this uncompleted task")
                            btn_rec.connect("clicked", lambda b, it=item: self._on_recalendar_task(it))
                            row.append(btn_rec)
                    except Exception:
                        pass

            self.sched_list_box.append(row)

    # -------------------------------------------------------------
    # Callbacks & Event Handlers
    # -------------------------------------------------------------
    def _on_recalendar_task(self, task):
        win = self.get_root()
        dlg = NewTaskDialog(win, self.storage, self.refresh, edit_task=task)
        dlg.present()

    def _on_recalendar_all_to_today(self):
        self.storage.recalendar_all_missed_to_today()
        self.refresh()

    def _set_arrival_now(self, date_str):
        now_time = datetime.now().strftime("%H:%M")
        self.storage.set_workday_arrival(date_str, now_time)
        self.refresh()

    def _set_departure_now(self, date_str):
        now_time = datetime.now().strftime("%H:%M")
        self.storage.set_workday_departure(date_str, now_time)
        self.refresh()

    def _clear_arrival(self, date_str):
        self.storage.set_workday_arrival(date_str, None)
        self.refresh()

    def _clear_departure(self, date_str):
        self.storage.set_workday_departure(date_str, None)
        self.refresh()

    def _open_edit_workday(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        dlg = EditWorkdayDialog(self.get_root(), self.storage, today_str, self.refresh)
        dlg.present()

    def _open_new_item(self, item_type: str):
        dlg = NewTaskDialog(self.get_root(), self.storage, self.refresh, default_type=item_type)
        dlg.present()

    def _on_task_checked(self, chk, task_id):
        is_done = chk.get_active()
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
                chk.set_active(False)

            win = self.get_root()
            dlg = TaskCompletionDialog(win, self.storage, task, is_event=False, on_done_cb=self.refresh, on_cancel_cb=on_cancel)
            dlg.present()

    def _on_start_focus(self, task):
        if self.on_start_timer_cb:
            self.on_start_timer_cb(task)

    def _on_log_event(self, item):
        win = self.get_root()
        dlg = TaskCompletionDialog(win, self.storage, item, is_event=True, on_done_cb=self.refresh)
        dlg.present()

    def _navigate(self, view_name: str):
        if self.on_navigate_cb:
            self.on_navigate_cb(view_name)
