"""Habit entity and related types."""
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional


class CompletionStatus(Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSED = "missed"
    SKIPPED = "skipped"


class Frequency(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"


@dataclass
class Habit:
    """A trackable habit."""
    id: Optional[int] = None
    name: str = ""
    category: str = "health"
    frequency: Frequency = Frequency.DAILY
    difficulty: int = 1  # 1-5
    points: int = 10
    active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    
    def calculate_points(self, streak: int = 0, multiplier_threshold: int = 7, multiplier: float = 1.5) -> int:
        """Calculate points for completing this habit, including streak bonus."""
        base = self.points * self.difficulty
        if streak >= multiplier_threshold:
            return int(base * multiplier)
        return base


@dataclass
class HabitCompletion:
    """Record of a habit completion."""
    id: Optional[int] = None
    habit_id: int = 0
    completed_at: datetime = field(default_factory=datetime.now)
    status: CompletionStatus = CompletionStatus.COMPLETE
    points_earned: int = 0
    notes: str = ""
    
    @property
    def date(self) -> date:
        return self.completed_at.date()
