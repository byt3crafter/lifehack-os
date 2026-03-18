"""Abstract AI provider interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class FoodAnalysis:
    """Result of AI food analysis."""
    calories: Optional[float] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    description: str = ""
    estimated: bool = False  # True if AI estimated, False if manual


@dataclass
class Insight:
    """AI-generated insight for the dashboard."""
    title: str = ""
    content: str = ""
    insight_type: str = "advice"  # advice, warning, celebration, tip
    priority: int = 0


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    def analyze_food(self, description: str, image_base64: Optional[str] = None) -> FoodAnalysis:
        """Estimate nutrition from a food description or image.

        Args:
            description: Text description of the food item.
            image_base64: Optional base64-encoded image (JPEG/PNG/WebP).
                          When provided, providers that support vision will
                          use the image as the primary signal.
        """
        ...

    @abstractmethod
    def generate_insight(self, user_state: dict) -> Optional[Insight]:
        """Generate a personalized insight based on user data."""
        ...

    @abstractmethod
    def generate_weekly_report(self, weekly_data: dict) -> str:
        """Generate a narrative weekly summary."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and reachable."""
        ...
