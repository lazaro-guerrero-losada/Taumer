"""
Reports View: Focus analytics, project velocity, stalled alerts, and AI retrospective generator.
Includes daily work target compliance, effective hours convergence, and break adherence.
Apple-style clean light interface with English localization.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
import subprocess
from datetime import datetime

from agent import RetrospectiveAgent

class ReportsView(Gtk.Box):
    def __init__(self, storage):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.storage = storage
        self.agent = RetrospectiveAgent(storage)
        self.selected_days = 7

        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(22)
        self.set_margin_end(22)

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # 1. Top Bar
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        lbl_title = Gtk.Label(label="Reports & Analytics")
        lbl_title.add_css_class("text-heading")
        top_bar.append(lbl_title)

        top_bar.append(Gtk.Box(hexpand=True))

        # Period filter segmented control
        p_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        p_box.add_css_class("segmented-bar")

        self.btn_7 = Gtk.Button(label="Week (7d)")
        self.btn_7.add_css_class("segmented-btn")
        self.btn_7.add_css_class("active")
        self.btn_7.connect("clicked", lambda b: self._set_period(7))
        p_box.append(self.btn_7)

        self.btn_30 = Gtk.Button(label="Month (30d)")
        self.btn_30.add_css_class("segmented-btn")
        self.btn_30.connect("clicked", lambda b: self._set_period(30))
        p_box.append(self.btn_30)

        top_bar.append(p_box)

        # AI Agent generate button
        ai_btn = Gtk.Button(label="Generate AI Report")
        ai_btn.add_css_class("btn-primary")
        ai_btn.connect("clicked", self._generate_ai_report)
        top_bar.append(ai_btn)

        self.append(top_bar)

        # 2. Scrolled content container
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.scrolled.set_child(self.content_box)
        self.append(self.scrolled)

    def _set_period(self, days: int):
        self.selected_days = days
        if days == 7:
            self.btn_7.add_css_class("active")
            self.btn_30.remove_css_class("active")
        else:
            self.btn_30.add_css_class("active")
            self.btn_7.remove_css_class("active")
        self.refresh()

    def _generate_ai_report(self, btn):
        report_path, report_content = self.agent.generate_markdown_report(self.selected_days)
        try:
            subprocess.Popen(["xdg-open", str(report_path)])
        except Exception:
            pass
        self.refresh()

    def refresh(self):
        while child := self.content_box.get_first_child():
            self.content_box.remove(child)

        data = self.agent.analyze_period(self.selected_days)

        # 1. Daily Work Target & Convergence KPI Row
        target_kpi_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        compliance_sub = f"{data['days_goal_met_count']} of {data['days_worked_count']} active days met goal"
        target_kpi_row.append(self._create_kpi_card("Goal Compliance", f"{data['compliance_percent']}% Met", compliance_sub))

        eff_sub = f"Target: {data['target_work_hours']}h (Net: {data['overtime_or_deficit_hours']:+0.1f}h)"
        target_kpi_row.append(self._create_kpi_card("Effective Work", f"{data['effective_work_hours']}h", eff_sub))

        target_kpi_row.append(self._create_kpi_card("Daily Average", f"{data['avg_effective_daily_hours']}h / day", f"{data['days_worked_count']} active days tracked"))

        break_sub = f"Avg {data['avg_break_daily_minutes']}m / day"
        target_kpi_row.append(self._create_kpi_card("Break Time", f"{data['total_break_minutes']}m", break_sub))

        self.content_box.append(target_kpi_row)

        # 2. General Activity & Project Health KPI Row
        kpi_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        kpi_row.append(self._create_kpi_card("Total Active Time", f"{data['total_hours']}h", f"{data['entries_count']} logged work sessions"))
        kpi_row.append(self._create_kpi_card("Completed Tasks", str(data["completed_tasks_count"]), f"{data['pending_tasks_count']} tasks queued"))
        kpi_row.append(self._create_kpi_card("Active Projects", str(len(data["active_projects"])), "progressed this period"))
        kpi_row.append(self._create_kpi_card("Stalled Projects", str(len(data["stalled_projects"])), "attention recommended"))
        self.content_box.append(kpi_row)

        # 3. Project Focus Breakdown
        breakdown_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        breakdown_box.add_css_class("card-box")

        lbl_b = Gtk.Label(label="Time Distribution by Project")
        lbl_b.add_css_class("text-title")
        lbl_b.set_halign(Gtk.Align.START)
        breakdown_box.append(lbl_b)

        if not data["active_projects"]:
            lbl_none = Gtk.Label(label="No activities recorded during this period yet.")
            lbl_none.add_css_class("text-muted")
            breakdown_box.append(lbl_none)
        else:
            for p in data["active_projects"]:
                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                
                header_r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                name_lbl = Gtk.Label(label=f"{p['icon']} {p['name']}")
                name_lbl.add_css_class("text-title")
                header_r.append(name_lbl)

                header_r.append(Gtk.Box(hexpand=True))

                stat_lbl = Gtk.Label(label=f"{p['hours']}h  ({p['percent']}%)")
                stat_lbl.add_css_class("text-mono")
                header_r.append(stat_lbl)

                status_tag = "In Focus" if p["percent"] >= 35 else "In Progress"
                tag_lbl = Gtk.Label(label=status_tag)
                tag_lbl.add_css_class("tag-pill")
                header_r.append(tag_lbl)
                row.append(header_r)

                # Progress Bar
                pbar = Gtk.ProgressBar()
                pbar.set_fraction(p["percent"] / 100.0)
                row.append(pbar)

                breakdown_box.append(row)

        self.content_box.append(breakdown_box)

        # 4. Stalled / Inactive Projects Alert
        if data["stalled_projects"]:
            stalled_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            stalled_box.add_css_class("card-box")

            lbl_s = Gtk.Label(label="Projects Without Recent Focus (Action Recommended)")
            lbl_s.add_css_class("text-title")
            lbl_s.set_halign(Gtk.Align.START)
            stalled_box.append(lbl_s)

            for p in data["stalled_projects"][:5]:
                item_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                p_lbl = Gtk.Label(label=f"{p['icon']} {p['name']}")
                p_lbl.add_css_class("tag-pill-project")
                item_row.append(p_lbl)

                info_lbl = Gtk.Label(label=f"0 logged hours ({p['tasks_pending']} pending tasks)")
                info_lbl.add_css_class("text-muted")
                item_row.append(info_lbl)
                stalled_box.append(item_row)

            self.content_box.append(stalled_box)

    def _create_kpi_card(self, title: str, main_stat: str, sub_stat: str) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        card.add_css_class("card-box")
        card.set_hexpand(True)

        lbl_t = Gtk.Label(label=title)
        lbl_t.add_css_class("text-muted")
        lbl_t.set_halign(Gtk.Align.START)
        card.append(lbl_t)

        lbl_m = Gtk.Label(label=main_stat)
        lbl_m.add_css_class("text-heading")
        lbl_m.set_halign(Gtk.Align.START)
        card.append(lbl_m)

        lbl_s = Gtk.Label(label=sub_stat)
        lbl_s.add_css_class("text-muted")
        lbl_s.set_halign(Gtk.Align.START)
        card.append(lbl_s)

        return card
