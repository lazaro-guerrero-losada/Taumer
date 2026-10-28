"""
Agentic Retrospective & Analytics Generator.
Analyzes weekly/monthly daily logs, tasks, and daily work target convergence (e.g. 7h goal, break compliance).
Detects neglected areas, calculates effective work vs target, and writes structured Obsidian reports in clean monochrome style.
English localization.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any
import os

from config import DIARIO_DIR, REPORTES_DIR
from storage import StorageManager
from models import DailyReconciliation

class RetrospectiveAgent:
    def __init__(self, storage: StorageManager):
        self.storage = storage

    def analyze_period(self, days: int = 7) -> Dict[str, Any]:
        today = datetime.now()
        date_list = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]

        project_minutes: Dict[str, int] = {}
        daily_minutes: Dict[str, int] = {d: 0 for d in date_list}
        all_entries = []

        total_target_work_m = 0
        total_effective_work_m = 0
        total_break_m = 0
        total_target_break_m = 0
        days_goal_met_count = 0
        days_worked_count = 0

        for d_str in date_list:
            entries = self.storage.load_journal_entries_for_date(d_str)
            recon = self.storage.get_daily_reconciliation(d_str)

            eff_m = recon.calculate_effective_work_minutes(entries)
            total_target_work_m += recon.target_work_minutes
            total_effective_work_m += eff_m
            total_break_m += recon.break_minutes
            total_target_break_m += recon.target_break_minutes

            if eff_m > 0:
                days_worked_count += 1
            if recon.calculate_remaining_minutes(entries) <= 0 and recon.target_work_minutes > 0:
                days_goal_met_count += 1

            for e in entries:
                all_entries.append(e)
                dur = e.duration_minutes
                proj = e.project or "General"
                project_minutes[proj] = project_minutes.get(proj, 0) + dur
                daily_minutes[d_str] = daily_minutes.get(d_str, 0) + dur

        total_minutes = sum(project_minutes.values())

        tasks = self.storage.get_tasks()
        completed_recent = [
            t for t in tasks 
            if t.status == "done" and t.completed_at and any(t.completed_at.startswith(d) for d in date_list)
        ]
        pending_tasks = [t for t in tasks if t.status != "done"]

        all_projects = self.storage.get_projects()
        active_projects = []
        stalled_projects = []

        for p in all_projects:
            mins = project_minutes.get(p.name, 0)
            p_tasks_pending = [t for t in pending_tasks if t.project == p.name]
            p_tasks_done = [t for t in completed_recent if t.project == p.name]

            item = {
                "name": p.name,
                "icon": p.icon,
                "minutes": mins,
                "hours": round(mins / 60, 1),
                "percent": round((mins / total_minutes * 100), 1) if total_minutes > 0 else 0,
                "tasks_done": len(p_tasks_done),
                "tasks_pending": len(p_tasks_pending)
            }

            if mins > 0 or len(p_tasks_done) > 0:
                active_projects.append(item)
            else:
                stalled_projects.append(item)

        active_projects.sort(key=lambda x: x["minutes"], reverse=True)

        compliance_pct = round((days_goal_met_count / max(days_worked_count, 1)) * 100) if days_worked_count > 0 else 0
        effective_hours = round(total_effective_work_m / 60, 1)
        target_hours = round(total_target_work_m / 60, 1)
        overtime_or_deficit_h = round((total_effective_work_m - total_target_work_m) / 60, 1)
        avg_eff_daily_h = round((total_effective_work_m / 60) / max(days_worked_count, 1), 1)
        avg_break_daily_m = round(total_break_m / max(days_worked_count, 1)) if days_worked_count > 0 else 0

        return {
            "days": days,
            "start_date": date_list[-1],
            "end_date": date_list[0],
            "total_minutes": total_minutes,
            "total_hours": round(total_minutes / 60, 1),
            "effective_work_hours": effective_hours,
            "target_work_hours": target_hours,
            "compliance_percent": compliance_pct,
            "days_goal_met_count": days_goal_met_count,
            "days_worked_count": days_worked_count,
            "total_break_minutes": total_break_m,
            "total_target_break_minutes": total_target_break_m,
            "avg_effective_daily_hours": avg_eff_daily_h,
            "avg_break_daily_minutes": avg_break_daily_m,
            "overtime_or_deficit_hours": overtime_or_deficit_h,
            "project_minutes": project_minutes,
            "daily_minutes": daily_minutes,
            "active_projects": active_projects,
            "stalled_projects": stalled_projects,
            "completed_tasks_count": len(completed_recent),
            "pending_tasks_count": len(pending_tasks),
            "entries_count": len(all_entries)
        }

    def generate_markdown_report(self, days: int = 7) -> tuple:
        data = self.analyze_period(days)
        today = datetime.now()
        week_num = today.isocalendar()[1]
        year = today.year

        period_name = f"Week {week_num} ({year})" if days == 7 else f"Past {days} Days"
        filename = f"Report-Week-{week_num}-{year}.md" if days == 7 else f"Report-{today.strftime('%Y-%m-%d')}.md"

        lines = [
            "---",
            "type: retrospective_report",
            f"period: \"{period_name}\"",
            f"generated: \"{today.strftime('%Y-%m-%d %H:%M')}\"",
            f"effective_work_hours: {data['effective_work_hours']}",
            f"target_work_hours: {data['target_work_hours']}",
            f"goal_compliance_percent: {data['compliance_percent']}",
            f"completed_tasks: {data['completed_tasks_count']}",
            "tags:",
            "  - tracker/report",
            "---",
            "",
            f"# Retrospective Report — {period_name}",
            "",
            "> [!NOTE]",
            f"> Productivity, effective work convergence, and break compliance report automatically generated for `{data['start_date']}` to `{data['end_date']}`.",
            "",
            "## Executive Summary",
            f"- **Effective Work Delivered:** `{data['effective_work_hours']} hours` (Target: `{data['target_work_hours']} hours`)",
            f"- **Work Goal Compliance:** `{data['days_goal_met_count']} of {data['days_worked_count']} active days met target` ({data['compliance_percent']}%)",
            f"- **Net Balance / Overtime:** `{data['overtime_or_deficit_hours']:+0.1f} hours`",
            f"- **Break Adherence:** `{data['total_break_minutes']}m` logged across period (Avg `{data['avg_break_daily_minutes']}m`/day)",
            f"- **Completed Tasks:** `{data['completed_tasks_count']}` tasks finished ({data['pending_tasks_count']} in queue)",
            "",
            "## Daily Work Goal & Target Compliance",
            f"- **Daily Work Requirement:** Evaluated against configured daily target hours converging to 0.",
            f"- **Average Effective Daily Output:** `{data['avg_effective_daily_hours']}h` per active day.",
            f"- **Total Break Time Taken:** `{data['total_break_minutes']}m` logged across {data['days_worked_count']} active days.",
            "",
            "## Project Focus Breakdown",
            "| Project | Hours | % of Time | Tasks Done | Status |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]

        for p in data["active_projects"]:
            state = "In Focus" if p["percent"] >= 35 else "In Progress"
            lines.append(f"| {p['icon']} [[{p['name']}]] | `{p['hours']}h` | {p['percent']}% | {p['tasks_done']} | {state} |")

        if not data["active_projects"]:
            lines.append("| *(No activity logged in this period)* | - | - | - | - |")

        lines.extend([
            "",
            "## Inactive / Stalled Projects",
        ])

        if data["stalled_projects"]:
            for p in data["stalled_projects"][:6]:
                lines.append(f"- {p['icon']} [[{p['name']}]]: `{p['tasks_pending']}` pending tasks but 0 hours dedicated this period.")
        else:
            lines.append("- *Great: No stalled projects detected in this period.*")

        lines.extend([
            "",
            "## Insights & Recommendations",
        ])

        insights = []
        if data["compliance_percent"] >= 80:
            insights.append(f"1. **Strong Work Goal Consistency:** You met your daily work target on {data['compliance_percent']}% of active days. Excellent discipline!")
        elif data["days_worked_count"] > 0:
            insights.append(f"1. **Target Convergence Opportunity:** Daily work goal was achieved on {data['days_goal_met_count']}/{data['days_worked_count']} days. Reconcile untracked time gaps or adjust break blocks.")

        if data["active_projects"]:
            top = data["active_projects"][0]
            insights.append(f"2. **Concentration of Effort:** Your primary project was [[{top['name']}]] taking {top['percent']}% of total logged time.")

        if len(data["stalled_projects"]) > 2:
            stalled_names = ", ".join([f"[[{p['name']}]]" for p in data["stalled_projects"][:3]])
            insights.append(f"3. **Attention Required:** You have stalled projects ({stalled_names}). If these remain active priorities, schedule a dedicated focus block to resume momentum.")

        for ins in insights:
            lines.append(ins)

        lines.extend([
            "",
            "---",
            "*Obsidian-native report. Internal wiki-links `[[...]]` seamlessly integrate with your knowledge graph.*"
        ])

        report_path = REPORTES_DIR / filename
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path, "\n".join(lines)
