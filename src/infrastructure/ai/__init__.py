"""AI provider abstraction — supports multiple backends."""
from .base import (
    AIProvider, FoodAnalysis, Insight,
    HabitPlan, HabitPlanPhase, AVAILABLE_AUTO_CHECKS,
    parse_habit_plan,
)
from .factory import get_ai_provider

__all__ = [
    'AIProvider', 'FoodAnalysis', 'Insight',
    'HabitPlan', 'HabitPlanPhase', 'AVAILABLE_AUTO_CHECKS',
    'parse_habit_plan',
    'get_ai_provider',
]
