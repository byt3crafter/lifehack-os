"""Domain services."""
from .habit_strength import (
    calculate_strength_change,
    get_strength_label,
    should_unlock_next_phase,
)

__all__ = [
    'calculate_strength_change',
    'get_strength_label',
    'should_unlock_next_phase',
]
