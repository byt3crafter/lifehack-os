"""Daily check-in entity."""
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional


@dataclass
class DailyCheckin:
    """Daily reflection and check-in."""
    id: Optional[int] = None
    date: date = field(default_factory=date.today)
    completed_today: str = ""
    avoided_alcohol: bool = True
    worked_on_future: bool = False
    mood: int = 3  # 1-5
    energy: int = 3  # 1-5
    improvement_note: str = ""
    points_earned: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    
    def calculate_points(self, base: int = 15, sobriety_bonus: int = 25, future_bonus: int = 10) -> int:
        """Calculate total points for this check-in."""
        total = base
        if self.avoided_alcohol:
            total += sobriety_bonus
        if self.worked_on_future:
            total += future_bonus
        return total
