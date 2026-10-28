"""
Storage manager: Reads and writes tasks, journal logs, and reports
directly to/from Obsidian-compatible Markdown files with YAML frontmatter.
Apple-style clean monochrome output with guaranteed ID tracking and resilient deletion.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import yaml
import uuid

from config import (
    TRACKER_ROOT, VAULT_ROOT, DIARIO_DIR, TAREAS_DIR,
    PROYECTOS_DIR, REPORTES_DIR, CONFIG_FILE, CACHE_DIR
)
from models import Task, JournalEntry, Project, DailyReconciliation

TASKS_MD_FILE = TAREAS_DIR / "tareas.md"
TASKS_JSON_CACHE = TAREAS_DIR / "tareas.json"
PROJECTS_JSON_FILE = PROYECTOS_DIR / "proyectos.json"
RECONCILIATION_CACHE_FILE = CACHE_DIR / "reconciliations.json"

DEFAULT_WORK_TARGET_MINUTES = 420  # 7 hours
DEFAULT_BREAK_TARGET_MINUTES = 30 # 30 min

DEFAULT_PROJECTS = [
    {"name": "General", "icon": "■", "description": "General tasks and miscellaneous work", "obsidian_link": "[[General]]"},
    {"name": "Deep Work", "icon": "●", "description": "Focused deep work sessions", "obsidian_link": "[[Deep Work]]"},
    {"name": "Projects", "icon": "◈", "description": "Active projects and goals", "obsidian_link": "[[Projects]]"},
    {"name": "Personal", "icon": "▲", "description": "Personal development and daily habits", "obsidian_link": "[[Personal]]"},
]


class StorageManager:
    def __init__(self):
        self.projects: Dict[str, Project] = {}
        self.tasks: List[Task] = []
        self._load_projects()
        self._load_tasks()

    # ==========================================
    # PROJECTS MANAGEMENT
    # ==========================================
    def _load_projects(self):
        """Loads projects from disk and respects the user-defined projects list."""
        self.projects = {}

        # 1. Primary Source of Truth: user-saved projects in JSON
        if PROJECTS_JSON_FILE.exists():
            try:
                data = json.loads(PROJECTS_JSON_FILE.read_text(encoding="utf-8"))
                for item in data:
                    self.projects[item["name"]] = Project.from_dict(item)
            except Exception as e:
                print(f"Error loading custom projects: {e}")

        # 2. If no saved projects yet, populate with default project set
        if not self.projects:
            for p in DEFAULT_PROJECTS:
                self.projects[p["name"]] = Project.from_dict(p)
            self.save_projects()

    def save_projects(self):
        """Saves custom projects to JSON."""
        data = [p.to_dict() for p in self.projects.values()]
        PROJECTS_JSON_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_projects(self) -> List[Project]:
        return list(self.projects.values())

    def get_project_icon(self, name: str) -> str:
        if name in self.projects:
            return self.projects[name].icon
        return "●"

    def add_project(self, name: str, icon: str = "●", description: str = ""):
        self.projects[name] = Project(name=name, icon=icon, description=description, obsidian_link=f"[[{name}]]")
        self.save_projects()

    def update_project(self, old_name: str, new_name: str, icon: str, description: str):
        if old_name in self.projects:
            del self.projects[old_name]
        self.projects[new_name] = Project(name=new_name, icon=icon, description=description, obsidian_link=f"[[{new_name}]]")
        
        for t in self.tasks:
            if t.project == old_name:
                t.project = new_name
                t.icon = icon
        self.save_tasks()
        self.save_projects()

        # Update break project setting if matched
        settings = self.get_settings()
        if settings.get("break_project_name") == old_name:
            settings["break_project_name"] = new_name
            self.save_settings(settings)

        # Propagate project name change to existing journal files in Diario/
        if DIARIO_DIR.exists():
            for md_file in DIARIO_DIR.glob("*.md"):
                date_str = md_file.stem
                entries = self.load_journal_entries_for_date(date_str)
                updated = False
                for e in entries:
                    if e.project == old_name:
                        e.project = new_name
                        e.icon = icon
                        updated = True
                if updated:
                    self._write_journal_md(date_str, entries)

    def delete_project(self, name: str):
        if name in self.projects:
            del self.projects[name]
            self.save_projects()

    # ==========================================
    # TASKS MANAGEMENT
    # ==========================================
    def _load_tasks(self):
        """Loads tasks from JSON cache and ensures unique IDs."""
        if TASKS_JSON_CACHE.exists():
            try:
                data = json.loads(TASKS_JSON_CACHE.read_text(encoding="utf-8"))
                seen_ids = set()
                loaded = []
                for d in data:
                    if d.get("id") in seen_ids or not d.get("id"):
                        d["id"] = f"tsk_{uuid.uuid4().hex[:10]}"
                    seen_ids.add(d["id"])
                    if d.get("icon") and len(d["icon"]) > 1:
                        d["icon"] = "●"
                    loaded.append(Task.from_dict(d))
                self.tasks = loaded
                self.save_tasks()
                return
            except Exception as e:
                print(f"Error loading tasks cache: {e}")

        self.tasks = [
            Task(
                id=f"tsk_{uuid.uuid4().hex[:10]}",
                title="Diseñar curvas de la pista bézier",
                project="LedTrix",
                status="todo",
                priority="alta",
                estimated_minutes=60,
                scheduled_date=datetime.now().strftime("%Y-%m-%d"),
                scheduled_time="10:00",
                icon="●",
                notes="Definir radios mínimos para evitar descarrilamiento en curvas"
            ),
            Task(
                id=f"tsk_{uuid.uuid4().hex[:10]}",
                title="Resolver ejercicios capítulo 3 (Navier-Stokes)",
                project="Fluidos",
                status="todo",
                priority="alta",
                estimated_minutes=90,
                scheduled_date=datetime.now().strftime("%Y-%m-%d"),
                scheduled_time="11:30",
                icon="◈",
                notes="Foco en conservación de masa y cantidad de movimiento"
            ),
            Task(
                id=f"tsk_{uuid.uuid4().hex[:10]}",
                title="Planificar semana y revisar materias",
                project="Master",
                status="done",
                priority="media",
                estimated_minutes=45,
                scheduled_date=datetime.now().strftime("%Y-%m-%d"),
                scheduled_time="09:00",
                completed_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
                icon="■",
                notes="Revisados calendarios de entregas"
            ),
            Task(
                id=f"tsk_{uuid.uuid4().hex[:10]}",
                title="Comprar pulsadores y conectores para mando",
                project="LedTrix",
                status="todo",
                priority="media",
                estimated_minutes=30,
                icon="●"
            )
        ]
        self.save_tasks()

    def save_tasks(self):
        """Saves tasks to JSON cache and generates Obsidian-ready Tareas/tareas.md."""
        TASKS_JSON_CACHE.write_text(
            json.dumps([t.to_dict() for t in self.tasks], indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        lines = [
            "---",
            "tipo: tablero_tareas",
            f"actualizado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "tags:",
            "  - tracker/tareas",
            "---",
            "",
            "# Tablero de Tareas",
            "",
            "> [!NOTE]",
            "> Tareas sincronizadas automáticamente con la app nativa.",
            ""
        ]

        tasks_by_proj: Dict[str, List[Task]] = {}
        for t in self.tasks:
            tasks_by_proj.setdefault(t.project, []).append(t)

        for proj, t_list in tasks_by_proj.items():
            icon = self.get_project_icon(proj)
            lines.append(f"## {icon} [[{proj}]]")
            lines.append("")
            for t in t_list:
                check = "x" if t.status == "done" else " "
                prio_tag = f"#{t.priority}" if t.priority else ""
                if getattr(t, "actual_minutes", None):
                    dur_tag = f"⏳{t.actual_minutes}m (real)"
                elif getattr(t, "is_open_ended", False):
                    dur_tag = "⏳open"
                elif t.scheduled_duration:
                    dur_tag = f"⏳{t.scheduled_duration}m"
                elif t.estimated_minutes:
                    dur_tag = f"⏳~{t.estimated_minutes}m"
                else:
                    dur_tag = ""
                sched = f"📅 {t.scheduled_date} {t.scheduled_time or ''}".strip() if t.scheduled_date else ""
                meta = " ".join(filter(None, [prio_tag, dur_tag, sched]))
                meta_str = f" ({meta})" if meta else ""
                lines.append(f"- [{check}] {t.title}{meta_str} ^id-{t.id}")
                if t.notes:
                    lines.append(f"  - *Notas:* {t.notes}")
            lines.append("")

        TASKS_MD_FILE.write_text("\n".join(lines), encoding="utf-8")

    def get_tasks(self) -> List[Task]:
        return self.tasks

    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        for t in self.tasks:
            if t.id == task_id:
                return t
        return None

    def add_task(self, task: Task):
        if not task.id:
            task.id = f"tsk_{uuid.uuid4().hex[:10]}"
        self.tasks.append(task)
        self.save_tasks()

    def update_task(self, task_id: str, **kwargs):
        for t in self.tasks:
            if t.id == task_id:
                for k, v in kwargs.items():
                    if hasattr(t, k):
                        setattr(t, k, v)
                break
        self.save_tasks()

    def delete_task(self, task_id: str):
        self.tasks = [t for t in self.tasks if t.id != task_id]
        self.save_tasks()

    def complete_task(self, task_id: str, is_done: bool = True, actual_minutes: Optional[int] = None):
        """
        Marks a task as done or todo, records actual time spent, and automatically synchronizes
        with today's Activity Journal for work target reconciliation.
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        for t in self.tasks:
            if t.id == task_id:
                t.status = "done" if is_done else "todo"
                t.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M") if is_done else None
                if actual_minutes is not None:
                    t.actual_minutes = actual_minutes

                entry_id = f"log_tsk_{t.id}"
                if is_done:
                    # Automatically log into today's Activity Journal
                    start_t = t.scheduled_time if (t.scheduled_date == today_str and t.scheduled_time) else datetime.now().strftime("%H:%M")
                    dur = actual_minutes or t.actual_minutes or t.scheduled_duration or t.estimated_minutes or 30
                    entry = JournalEntry(
                        id=entry_id,
                        date=today_str,
                        start_time=start_t,
                        duration_minutes=dur,
                        project=t.project,
                        title=f"{t.title}",
                        description=f"Completed task: {t.notes}" if t.notes else "Completed task",
                        source="task_completed",
                        linked_task_id=t.id
                    )
                    self.save_journal_entry(entry)
                    t.logged_to_journal = True
                else:
                    # Uncompleted: remove the auto-generated journal entry
                    self.delete_journal_entry(today_str, entry_id)
                    t.logged_to_journal = False
                    t.actual_minutes = None
                break
        self.save_tasks()

    def log_event_to_journal(self, task_id: str, actual_minutes: Optional[int] = None) -> Optional[JournalEntry]:
        """
        Converts a scheduled calendar event into a logged activity in the journal.
        """
        for t in self.tasks:
            if t.id == task_id:
                date_str = t.scheduled_date or datetime.now().strftime("%Y-%m-%d")
                start_t = t.scheduled_time or datetime.now().strftime("%H:%M")
                dur = actual_minutes or t.actual_minutes or t.scheduled_duration or t.estimated_minutes or 30
                if actual_minutes is not None:
                    t.actual_minutes = actual_minutes
                    t.scheduled_duration = actual_minutes
                entry_id = f"log_evt_{t.id}"

                entry = JournalEntry(
                    id=entry_id,
                    date=date_str,
                    start_time=start_t,
                    duration_minutes=dur,
                    project=t.project,
                    title=f"Event: {t.title}",
                    description=t.notes or "Calendar event completed",
                    source="calendar_event",
                    linked_task_id=t.id
                )
                self.save_journal_entry(entry)
                t.logged_to_journal = True
                t.status = "done"
                t.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M")
                self.save_tasks()
                return entry
        return None

    # ==========================================
    # JOURNAL (DIARIO) MANAGEMENT
    # ==========================================
    def get_journal_file_path(self, date_str: str) -> Path:
        return DIARIO_DIR / f"{date_str}.md"

    def load_journal_entries_for_date(self, date_str: str) -> List[JournalEntry]:
        md_path = self.get_journal_file_path(date_str)
        if not md_path.exists():
            return []

        entries = []
        try:
            content = md_path.read_text(encoding="utf-8")
            in_table = False
            for line in content.splitlines():
                if "Registro de Actividades" in line or "Activity Log" in line:
                    in_table = True
                    continue
                if in_table and line.startswith("## "):
                    break
                if in_table and line.strip().startswith("|") and not line.strip().startswith("| :---"):
                    parts = [p.strip() for p in line.split("|")[1:-1]]
                    if len(parts) >= 4 and parts[0] not in ["Hora", "Time"]:
                        hora = parts[0]
                        if hora == "-":
                            continue
                        m_proj = re.search(r"\[\[(.*?)\]\]", parts[1])
                        if m_proj:
                            proj_raw = m_proj.group(1).strip()
                        else:
                            proj_raw = parts[1].replace("[[", "").replace("]]", "").strip()
                            if " " in proj_raw and len(proj_raw.split(" ", 1)[0]) <= 2:
                                proj_raw = proj_raw.split(" ", 1)[1].strip()
                        titulo = parts[2]
                        if "Sin actividades" in titulo or "No activities" in titulo:
                            continue
                        dur_str = parts[3].replace("m", "").replace("min", "").strip()
                        dur = int(dur_str) if dur_str.isdigit() else 30
                        notas_raw = parts[4] if len(parts) >= 5 else ""

                        # Extract persistent id from notes if present (^id-log_...)
                        entry_id = None
                        m = re.search(r"\^id-(log_[a-zA-Z0-9_]+)", notas_raw)
                        if m:
                            entry_id = m.group(1)
                            notas = notas_raw.replace(m.group(0), "").strip()
                        else:
                            # Deterministic ID based on start time & title
                            time_key = hora.replace(":", "").replace(" ", "").replace("-", "_")
                            safe_title = abs(hash(titulo)) % 1000000
                            entry_id = f"log_{time_key}_{safe_title}"
                            notas = notas_raw

                        linked_task_id = None
                        if entry_id and entry_id.startswith("log_tsk_"):
                            linked_task_id = entry_id[len("log_tsk_"):]
                        elif entry_id and entry_id.startswith("log_evt_"):
                            linked_task_id = entry_id[len("log_evt_"):]

                        start_time = hora.split("-")[0].strip() if "-" in hora else hora
                        end_time = hora.split("-")[1].strip() if "-" in hora else ""

                        entries.append(JournalEntry(
                            id=entry_id,
                            date=date_str,
                            start_time=start_time,
                            end_time=end_time,
                            duration_minutes=dur,
                            project=proj_raw,
                            title=titulo,
                            description=notas,
                            linked_task_id=linked_task_id
                        ))
        except Exception as e:
            print(f"Error parsing journal {date_str}: {e}")
        return entries

    def save_journal_entry(self, entry: JournalEntry):
        entries = self.load_journal_entries_for_date(entry.date)
        found = False
        for i, e in enumerate(entries):
            if e.id == entry.id or (e.start_time == entry.start_time and e.title == entry.title):
                entries[i] = entry
                found = True
                break
        if not found:
            entries.append(entry)

        entries.sort(key=lambda x: x.start_time or "00:00")
        self._write_journal_md(entry.date, entries)

    def update_journal_entry(self, date_str: str, entry_id: str, new_entry: JournalEntry):
        entries = self.load_journal_entries_for_date(date_str)
        for i, e in enumerate(entries):
            if e.id == entry_id or (e.start_time == new_entry.start_time and e.title == new_entry.title):
                entries[i] = new_entry
                break
        entries.sort(key=lambda x: x.start_time or "00:00")
        self._write_journal_md(date_str, entries)

    def delete_journal_entry(self, date_str: str, entry_id: str, start_time: str = "", title: str = ""):
        """Resiliently deletes an entry by id, or by matching start_time and title."""
        entries = self.load_journal_entries_for_date(date_str)
        new_entries = []
        for e in entries:
            # Match by ID or by exact start_time & title
            if e.id == entry_id:
                continue
            if start_time and title and e.start_time == start_time and e.title == title:
                continue
            new_entries.append(e)

        self._write_journal_md(date_str, new_entries)

    # ==========================================
    # SETTINGS & DAILY RECONCILIATION
    # ==========================================
    def get_settings(self) -> dict:
        defaults = {
            "daily_work_target_minutes": DEFAULT_WORK_TARGET_MINUTES,
            "daily_break_target_minutes": DEFAULT_BREAK_TARGET_MINUTES,
            "enable_watcher": True,
            "enable_reports": True,
            "watcher_min_duration_seconds": 60,
            "ignored_apps": "antigravity, main.py, agy, taumer, trazos, xprop, subagent",
            "break_project_name": "Break Time"
        }
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                defaults.update(data)
            except Exception:
                pass
        return defaults

    def get_break_project_name(self) -> str:
        settings = self.get_settings()
        bp = settings.get("break_project_name", "Break Time")
        if bp not in self.projects and "Break Time" in self.projects:
            bp = "Break Time"
        return bp

    def set_break_project_name(self, name: str):
        settings = self.get_settings()
        settings["break_project_name"] = name
        self.save_settings(settings)

    def save_settings(self, settings: dict):
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get_daily_reconciliation(self, date_str: str) -> DailyReconciliation:
        settings = self.get_settings()
        # 1. Try local cache
        if RECONCILIATION_CACHE_FILE.exists():
            try:
                cache = json.loads(RECONCILIATION_CACHE_FILE.read_text(encoding="utf-8"))
                if date_str in cache:
                    return DailyReconciliation.from_dict(cache[date_str])
            except Exception:
                pass

        # 2. Try Obsidian markdown frontmatter
        md_path = self.get_journal_file_path(date_str)
        if md_path.exists():
            try:
                content = md_path.read_text(encoding="utf-8")
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        fm = yaml.safe_load(parts[1]) or {}
                        if "target_work_minutes" in fm or "effective_work_minutes" in fm:
                            return DailyReconciliation(
                                date=date_str,
                                target_work_minutes=fm.get("target_work_minutes", settings["daily_work_target_minutes"]),
                                target_break_minutes=fm.get("target_break_minutes", settings["daily_break_target_minutes"]),
                                break_minutes=fm.get("break_minutes", 0),
                                gap_adjustment_minutes=fm.get("gap_adjustment_minutes", 0),
                                excluded_entry_ids=fm.get("excluded_entry_ids", []),
                                arrival_time=fm.get("arrival_time") or None,
                                departure_time=fm.get("departure_time") or None
                            )
            except Exception:
                pass

        # 3. Default reconciliation for date
        return DailyReconciliation(
            date=date_str,
            target_work_minutes=settings["daily_work_target_minutes"],
            target_break_minutes=settings["daily_break_target_minutes"]
        )

    def save_daily_reconciliation(self, recon: DailyReconciliation):
        # 1. Save to cache
        cache = {}
        if RECONCILIATION_CACHE_FILE.exists():
            try:
                cache = json.loads(RECONCILIATION_CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                cache = {}
        cache[recon.date] = recon.to_dict()
        try:
            RECONCILIATION_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            RECONCILIATION_CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"Error saving reconciliation cache: {e}")

        # 2. Sync to Obsidian daily note
        entries = self.load_journal_entries_for_date(recon.date)
        self._write_journal_md(recon.date, entries, recon=recon)

    def _write_journal_md(self, date_str: str, entries: List[JournalEntry], extra_notes: str = "", recon: DailyReconciliation = None):
        md_path = self.get_journal_file_path(date_str)

        total_minutes = sum(e.duration_minutes for e in entries)
        hours = total_minutes // 60
        mins = total_minutes % 60
        total_str = f"{hours}h {mins}m" if hours else f"{mins}m"

        if recon is None:
            recon = self.get_daily_reconciliation(date_str)

        break_project = self.get_break_project_name()
        effective_m = recon.calculate_effective_work_minutes(entries, break_project)
        credited_break_m = recon.calculate_credited_break_minutes(entries, break_project)
        remaining_m = recon.calculate_remaining_minutes(entries, break_project)
        total_break_m = recon.calculate_total_break_minutes(entries, break_project)
        break_diff_m = recon.calculate_break_difference_minutes(entries, break_project)

        eff_h = effective_m // 60
        eff_mins = effective_m % 60
        eff_str = f"{eff_h}h {eff_mins:02d}m"

        target_h = recon.target_work_minutes // 60
        target_mins = recon.target_work_minutes % 60
        target_str = f"{target_h}h {target_mins:02d}m"

        if remaining_m > 0:
            rem_h = remaining_m // 60
            rem_mins = remaining_m % 60
            rem_str = f"{rem_h}h {rem_mins:02d}m remaining"
            status_goal = "in_progress"
        else:
            overtime = abs(remaining_m)
            ot_h = overtime // 60
            ot_mins = overtime % 60
            rem_str = f"Goal Completed (+{ot_h}h {ot_mins:02d}m overtime)"
            status_goal = "completed"

        if break_diff_m > 0:
            break_status = f"{break_diff_m}m over budget"
        elif break_diff_m < 0:
            break_status = f"{abs(break_diff_m)}m under budget"
        else:
            break_status = "on budget"

        projects_set = list({f"[[{e.project}]]" for e in entries if e.project})

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            fecha_bonita = dt.strftime("%A, %B %d, %Y")
        except Exception:
            fecha_bonita = date_str

        completed_today = [t for t in self.tasks if t.completed_at and t.completed_at.startswith(date_str)]

        span_m = recon.calculate_workday_span_minutes()
        if span_m is not None:
            s_h = span_m // 60
            s_m = span_m % 60
            span_str = f"{s_h}h {s_m:02d}m"
        else:
            span_str = "N/A"

        expected_dep = recon.calculate_expected_departure_time(entries, break_project) or "N/A"

        lines = [
            "---",
            f"date: {date_str}",
            "type: daily_journal",
            f"arrival_time: \"{recon.arrival_time or ''}\"",
            f"departure_time: \"{recon.departure_time or ''}\"",
            f"workday_span_minutes: {span_m if span_m is not None else 0}",
            f"target_work_minutes: {recon.target_work_minutes}",
            f"target_break_minutes: {recon.target_break_minutes}",
            f"effective_work_minutes: {effective_m}",
            f"credited_break_minutes: {credited_break_m}",
            f"remaining_minutes: {remaining_m}",
            f"goal_status: \"{status_goal}\"",
            f"break_project: \"{break_project}\"",
            f"break_minutes: {total_break_m}",
            f"manual_break_minutes: {recon.break_minutes}",
            f"gap_adjustment_minutes: {recon.gap_adjustment_minutes}",
            f"total_logged_minutes: {total_minutes}",
            f"total_logged_time: \"{total_str}\"",
            "excluded_entry_ids:",
        ]
        for xid in recon.excluded_entry_ids:
            lines.append(f"  - \"{xid}\"")

        lines.append("projects:")
        for p in projects_set:
            lines.append(f"  - \"{p}\"")
        lines.extend([
            "tags:",
            "  - tracker/journal",
            "---",
            "",
            f"# Daily Journal — {fecha_bonita}",
            "",
            f"> **Total Productive Time:** `{total_str}` ({len(entries)} logged activities)",
            "",
            "## Workday Attendance",
            f"- **Arrival:** `{recon.arrival_time or 'Not recorded'}` | **Departure:** `{recon.departure_time or 'In progress / Not set'}`",
            f"- **Workday Span:** `{span_str}` | **Projected Departure:** `{expected_dep}`",
            "",
            "## Daily Work Target & Time Balance",
            f"- **Target Goal:** `{target_str}` (incl. `{recon.target_break_minutes}m` break) | **Effective Worked:** `{eff_str}`",
            f"- **Convergence to Target:** `{rem_str}`",
            f"- **Untracked Work Balance Adjustment:** `{recon.gap_adjustment_minutes:+d}m`",
            f"- **Break Time:** `{total_break_m}m / {recon.target_break_minutes}m` *({break_status}, {credited_break_m}m credited)* • Project: `[[{break_project}]]`",
            "",
            "## Activity Log",
            "| Time | Project | Title | Duration | Notes |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ])

        if entries:
            for e in entries:
                time_range = f"{e.start_time} - {e.end_time}" if e.end_time else e.start_time
                icon = self.get_project_icon(e.project)
                desc = e.description.replace("|", "/") if e.description else "-"
                excluded_tag = " [EXCLUDED]" if e.id in recon.excluded_entry_ids else ""
                id_tag = f" ^id-{e.id}" if e.id else ""
                lines.append(f"| {time_range} | {icon} [[{e.project}]] | {e.title}{excluded_tag} | {e.duration_minutes}m | {desc}{id_tag} |")
        else:
            lines.append("| - | - | No activities logged yet | - | - |")

        lines.extend([
            "",
            "## Notes & Learnings",
            extra_notes or "- Daily journal generated with Taumer.",
            "",
            "## Tasks Completed Today"
        ])

        if completed_today:
            for t in completed_today:
                lines.append(f"- [x] {t.title} [[{t.project}]]")
        else:
            lines.append("- *(No tasks marked completed today yet)*")

        lines.append("")
        md_path.write_text("\n".join(lines), encoding="utf-8")

    def save_report_markdown(self, title: str, filename: str, content: str) -> Path:
        report_file = REPORTES_DIR / filename
        report_file.write_text(content, encoding="utf-8")
        return report_file

    def set_workday_arrival(self, date_str: str, time_str: Optional[str]):
        recon = self.get_daily_reconciliation(date_str)
        recon.arrival_time = time_str
        self.save_daily_reconciliation(recon)

    def set_workday_departure(self, date_str: str, time_str: Optional[str]):
        recon = self.get_daily_reconciliation(date_str)
        recon.departure_time = time_str
        self.save_daily_reconciliation(recon)

    def get_undone_tasks(self) -> List[Task]:
        return [t for t in self.tasks if t.status != "done"]

    def get_today_scheduled_items(self, date_str: Optional[str] = None) -> List[Task]:
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        items = [t for t in self.tasks if t.scheduled_date == date_str]
        items.sort(key=lambda x: x.scheduled_time or "99:99")
        return items

    def get_missed_scheduled_tasks(self, include_today_overdue: bool = True) -> List[Task]:
        """
        Returns tasks scheduled in the past or earlier today that are not marked done.
        """
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        now_minutes = now.hour * 60 + now.minute

        missed = []
        for t in self.tasks:
            if t.status == "done":
                continue
            if getattr(t, "item_type", "task") == "event":
                continue
            if not t.scheduled_date:
                continue

            if t.scheduled_date < today_str:
                missed.append(t)
            elif include_today_overdue and t.scheduled_date == today_str and t.scheduled_time:
                try:
                    parts = t.scheduled_time.split(":")
                    start_m = int(parts[0]) * 60 + int(parts[1])
                    dur = t.scheduled_duration or t.estimated_minutes or 30
                    if now_minutes > (start_m + dur):
                        missed.append(t)
                except Exception:
                    pass

        missed.sort(key=lambda x: (x.scheduled_date or "", x.scheduled_time or "99:99"))
        return missed

    def recalendar_task(self, task_id: str, new_date: Optional[str] = None, new_time: Optional[str] = None):
        """
        Reschedules an uncompleted task to a new date and optional time.
        """
        if not new_date:
            new_date = datetime.now().strftime("%Y-%m-%d")

        for t in self.tasks:
            if t.id == task_id:
                t.scheduled_date = new_date
                t.scheduled_time = new_time
                break
        self.save_tasks()

    def recalendar_all_missed_to_today(self) -> int:
        """
        Moves all missed scheduled tasks from past dates to today's date.
        Clears scheduled_time so they become part of today's ready task pool.
        """
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        missed = self.get_missed_scheduled_tasks(include_today_overdue=False)
        count = 0
        for t in missed:
            t.scheduled_date = today_str
            t.scheduled_time = None
            count += 1
        if count > 0:
            self.save_tasks()
        return count

    def unassign_task_schedule(self, task_id: str):
        """
        Clears the scheduled date, time, and duration of a task so it returns to unassigned / undefined tasks.
        """
        for t in self.tasks:
            if t.id == task_id:
                t.scheduled_date = None
                t.scheduled_time = None
                t.scheduled_duration = None
                t.is_open_ended = True
                break
        self.save_tasks()
