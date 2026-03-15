"""Walk log entity."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class WalkLog:
    """Record of a walk/movement session."""
    id: Optional[int] = None
    logged_at: datetime = field(default_factory=datetime.now)
    distance_km: float = 0.0
    duration_minutes: int = 0
    mood_before: int = 3  # 1-5
    mood_after: int = 3   # 1-5
    points_earned: int = 0
    notes: str = ""
    
    @property
    def mood_improvement(self) -> int:
        return self.mood_after - self.mood_before
    
    def calculate_points(self, base: int = 20, km_bonus: int = 5, mood_bonus: int = 10) -> int:
        """Calculate points for this walk."""
        total = base
        total += int(self.distance_km * km_bonus)
        if self.mood_improvement > 0:
            total += mood_bonus
        return total
