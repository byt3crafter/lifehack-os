"""Replacement action entities for alcohol substitution."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ReplacementAction:
    """A defined replacement behavior for alcohol urges."""
    id: Optional[int] = None
    name: str = ""
    category: str = "general"
    points: int = 30
    active: bool = True
    
    
@dataclass
class ReplacementLog:
    """Record of successfully redirecting an urge."""
    id: Optional[int] = None
    action_id: int = 0
    action_name: str = ""  # Denormalized for display
    logged_at: datetime = field(default_factory=datetime.now)
    urge_level: int = 3  # 1-5
    points_earned: int = 0
    notes: str = ""
    
    def calculate_points(self, base: int = 30, high_urge_bonus: int = 20) -> int:
        """Calculate points for redirecting this urge."""
        total = base
        if self.urge_level >= 4:
            total += high_urge_bonus
        return total
