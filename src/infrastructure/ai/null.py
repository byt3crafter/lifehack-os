"""Null AI provider — app works fully without any AI."""
from typing import Optional

from .base import AIProvider, FoodAnalysis, Insight


class NullAIProvider(AIProvider):
    """No-op provider. All features degrade gracefully to manual input."""

    def analyze_food(self, description: str) -> FoodAnalysis:
        return FoodAnalysis(estimated=False)

    def generate_insight(self, user_state: dict) -> Optional[Insight]:
        return None

    def generate_weekly_report(self, weekly_data: dict) -> str:
        return ""

    def is_available(self) -> bool:
        return True  # Always available — does nothing
