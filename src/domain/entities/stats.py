"""User stats, streaks, and point ledger entities."""
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional, List


class StreakType(Enum):
    HABIT = "habit"
    SOBRIETY = "sobriety"
    CHECKIN = "checkin"
    WALK = "walk"


@dataclass
class Streak:
    """Tracks a streak for a specific activity."""
    id: Optional[int] = None
    type: StreakType = StreakType.HABIT
    reference_id: Optional[int] = None  # e.g., habit_id
    current_count: int = 0
    best_count: int = 0
    last_date: Optional[date] = None
    
    def increment(self, for_date: date = None) -> None:
        """Increment streak for today."""
        if for_date is None:
            for_date = date.today()
        
        if self.last_date is None:
            self.current_count = 1
        elif (for_date - self.last_date).days == 1:
            self.current_count += 1
        elif (for_date - self.last_date).days > 1:
            self.current_count = 1  # Reset
        # Same day = no change
        
        self.last_date = for_date
        self.best_count = max(self.best_count, self.current_count)
    
    def reset(self) -> None:
        """Reset current streak."""
        self.current_count = 0


@dataclass
class UserStats:
    """Overall user statistics."""
    id: Optional[int] = None
    total_xp: int = 0
    level: int = 1
    sobriety_start_date: Optional[date] = None
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def sobriety_days(self) -> int:
        if self.sobriety_start_date is None:
            return 0
        return (date.today() - self.sobriety_start_date).days
    
    def calculate_level(self, xp_per_level: int = 500) -> int:
        """Calculate level from XP."""
        return max(1, (self.total_xp // xp_per_level) + 1)
    
    def add_xp(self, amount: int) -> None:
        """Add XP and recalculate level."""
        self.total_xp += amount
        self.level = self.calculate_level()
    
    def xp_for_next_level(self, xp_per_level: int = 500) -> int:
        """XP needed to reach next level."""
        next_level_total = self.level * xp_per_level
        return next_level_total - self.total_xp


@dataclass  
class PointLedgerEntry:
    """Audit log entry for all point changes."""
    id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)
    source_type: str = ""  # habit, project, checkin, walk, replacement, penalty
    source_id: Optional[int] = None
    points: int = 0
    reason: str = ""
