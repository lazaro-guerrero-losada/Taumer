"""
Data models for tasks, journal logs, projects, daily reconciliation, and window tracking.
Apple-style clean architecture with guaranteed unique UUIDs.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional
import uuid
from datetime import datetime

def generate_id(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

@dataclass
class Task:
    id: str = field(default_factory=lambda: generate_id("tsk"))
    title: str = ""
    project: str = "General"
    tags: List[str] = field(default_factory=list)
    status: str = "todo"  # 'todo', 'in_progress', 'done'
    priority: str = "medium"  # 'low', 'medium', 'high'
    estimated_minutes: int = 30
    scheduled_date: Optional[str] = None  # YYYY-MM-DD
    scheduled_time: Optional[str] = None  # HH:MM
    scheduled_duration: Optional[int] = 60  # minutes, None if open-ended
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
    completed_at: Optional[str] = None
    notes: str = ""
    icon: str = "●"
    item_type: str = "task"  # 'task' or 'event'
    logged_to_journal: bool = False  # True if activity log created from this item
    actual_minutes: Optional[int] = None
    is_open_ended: bool = False

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class JournalEntry:
    id: str = field(default_factory=lambda: generate_id("log"))
    date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    start_time: str = field(default_factory=lambda: datetime.now().strftime("%H:%M"))
    end_time: str = ""
    duration_minutes: int = 30
    project: str = "General"
    title: str = ""
    description: str = ""
    source: str = "manual"  # 'manual', 'timer', 'window_tracker'
    icon: str = "●"
    linked_task_id: Optional[str] = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DailyReconciliation:
    """
    Daily work target reconciliation, break tracker, and time balance adjustment.
    Tracks convergence of target hours (e.g. 7h -> 0), break budget adherence,
    workday attendance (arrival and departure), and manual untracked gap compensation.
    """
    date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    target_work_minutes: int = 420   # 7h default
    target_break_minutes: int = 30  # 30m default
    break_minutes: int = 0          # actual break time logged
    gap_adjustment_minutes: int = 0 # untracked time balance adjustment (+/- minutes)
    excluded_entry_ids: List[str] = field(default_factory=list) # entries excluded from effective work
    arrival_time: Optional[str] = None    # "HH:MM" e.g. "08:30"
    departure_time: Optional[str] = None  # "HH:MM" e.g. "17:00"

    def calculate_workday_span_minutes(self) -> Optional[int]:
        """Calculates total minutes between arrival and departure."""
        if not self.arrival_time:
            return None
        try:
            arr_h, arr_m = map(int, self.arrival_time.split(":"))
            arr_mins = arr_h * 60 + arr_m
            if self.departure_time:
                dep_h, dep_m = map(int, self.departure_time.split(":"))
                dep_mins = dep_h * 60 + dep_m
                return max(0, dep_mins - arr_mins)
            else:
                now = datetime.now()
                if self.date == now.strftime("%Y-%m-%d"):
                    cur_mins = now.hour * 60 + now.minute
                    return max(0, cur_mins - arr_mins)
        except Exception:
            pass
        return None

    def calculate_expected_departure_time(self, entries: List[JournalEntry] = None, break_project: str = "") -> Optional[str]:
        """
        Calculates projected departure time based on arrival time + target work minutes.
        The break time is included inside the target workday hours (e.g. 7h workday with 30m break inside = 7h span).
        Excess break beyond target_break_minutes extends departure time.
        E.g. Arrived at 08:25 + 420m (7h workday, including 30m break) = 15:25
        If break taken is 45m (15m over budget): 08:25 + 420m + 15m = 15:40
        """
        if not self.arrival_time:
            return None
        try:
            arr_h, arr_m = map(int, self.arrival_time.split(":"))
            actual_break = self.calculate_total_break_minutes(entries, break_project) if entries is not None else self.break_minutes
            excess_break = max(0, actual_break - self.target_break_minutes)
            total_duration = self.target_work_minutes + excess_break
            target_mins = arr_h * 60 + arr_m + total_duration
            target_h = (target_mins // 60) % 24
            target_m = target_mins % 60
            return f"{target_h:02d}:{target_m:02d}"
        except Exception:
            return None

    def calculate_total_break_minutes(self, entries: List[JournalEntry] = None, break_project: str = "") -> int:
        """
        Returns total break minutes: sum of all journal entries matching the break project
        plus any manual quick break adjustments (self.break_minutes).
        """
        break_names = {"break", "descanso"}
        if break_project:
            break_names.add(break_project.strip().lower())
        
        logged_break_m = 0
        if entries:
            for e in entries:
                if e.project and e.project.strip().lower() in break_names:
                    logged_break_m += e.duration_minutes

        return logged_break_m + self.break_minutes

    def calculate_credited_break_minutes(self, entries: List[JournalEntry] = None, break_project: str = "") -> int:
        """
        Returns break minutes that count towards the daily target (up to target_break_minutes).
        Because the break is inside the target workday hours, break time restas (subtracts) from the required work.
        """
        total_break = self.calculate_total_break_minutes(entries, break_project)
        return min(total_break, self.target_break_minutes)

    def calculate_effective_work_minutes(self, entries: List[JournalEntry], break_project: str = "") -> int:
        """Returns total effective work minutes (excluding break project and excluded entries + gap adjustments)."""
        work_m = 0
        break_names = {"break", "descanso"}
        if break_project:
            break_names.add(break_project.strip().lower())

        for e in entries:
            is_break = bool(e.project and e.project.strip().lower() in break_names)
            if e.id not in self.excluded_entry_ids and not is_break:
                work_m += e.duration_minutes
        return max(0, work_m + self.gap_adjustment_minutes)

    def calculate_remaining_minutes(self, entries: List[JournalEntry], break_project: str = "") -> int:
        """
        Calculates remaining minutes to meet daily target (converges to 0).
        The break time restas (subtracts) from the total amount of time to work.
        Remaining = target_work_minutes - effective_work_minutes - credited_break_minutes.
        Positive = hours left to work. Negative = overtime.
        """
        effective = self.calculate_effective_work_minutes(entries, break_project)
        credited_break = self.calculate_credited_break_minutes(entries, break_project)
        return self.target_work_minutes - effective - credited_break

    def calculate_break_difference_minutes(self, entries: List[JournalEntry] = None, break_project: str = "") -> int:
        """
        Difference between actual total break (logged + manual) and target break.
        Negative = under budget (e.g. -10m). Positive = over budget (e.g. +15m).
        """
        total_break = self.calculate_total_break_minutes(entries, break_project)
        return total_break - self.target_break_minutes

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Project:
    name: str
    icon: str = "●"
    color: str = "#48484a"
    description: str = ""
    target_hours_week: float = 10.0
    obsidian_link: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class WindowActivityItem:
    app: str
    title: str
    duration_seconds: float
    last_seen: str
    icon_name: str = "application-x-executable"
