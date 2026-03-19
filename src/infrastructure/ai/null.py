"""Null AI provider — app works fully without any AI."""
from typing import Optional

from .base import AIProvider, FoodAnalysis, FoodIdentification, Insight, HabitPlan


class NullAIProvider(AIProvider):
    """No-op provider. All features degrade gracefully to manual input."""

    def identify_food(self, description: str = '', image_base64: Optional[str] = None) -> FoodIdentification:
        return FoodIdentification(available=False)

    def analyze_food(self, description: str, image_base64: Optional[str] = None) -> FoodAnalysis:
        return FoodAnalysis(estimated=False)

    def generate_insight(self, user_state: dict) -> Optional[Insight]:
        return None

    def generate_weekly_report(self, weekly_data: dict) -> str:
        return ""

    def generate_habit_plan(self, goal: str) -> Optional[HabitPlan]:
        return None

    def is_available(self) -> bool:
        return True  # Always available — does nothing
