"""Deep work session entity."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DeepWorkSession:
    """Record of a focused work session."""
    id: Optional[int] = None
    project_id: Optional[int] = None
    project_name: str = ""  # Denormalized
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: Optional[datetime] = None
    duration_minutes: int = 0
    points_earned: int = 0
    notes: str = ""
    
    @property
    def is_active(self) -> bool:
        return self.ended_at is None
    
    def calculate_points(self, points_per_30min: int = 15, minimum_minutes: int = 25) -> int:
        """Calculate points for this session."""
        if self.duration_minutes < minimum_minutes:
            return 0
        blocks = self.duration_minutes // 30
        return blocks * points_per_30min
    
    def end(self) -> None:
        """End the session and calculate duration."""
        self.ended_at = datetime.now()
        self.duration_minutes = int((self.ended_at - self.started_at).total_seconds() / 60)
