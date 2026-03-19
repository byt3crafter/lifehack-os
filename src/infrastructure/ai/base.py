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
class FoodIdentification:
    """Result of AI food identification (description only, no nutrition)."""
    description: str = ""
    confidence: str = "low"  # "high", "medium", "low"
    available: bool = False  # False if AI not configured or identification failed


@dataclass
class Insight:
    """AI-generated insight for the dashboard."""
    title: str = ""
    content: str = ""
    insight_type: str = "advice"  # advice, warning, celebration, tip
    priority: int = 0


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD based on provider/model pricing.

    Rates are approximate per 1M tokens (input, output).
    """
    pricing = {
        'gpt-4o': (2.50, 10.00),
        'gpt-4o-mini': (0.15, 0.60),
        'gpt-4.1-mini': (0.40, 1.60),
        'claude-sonnet-4-20250514': (3.00, 15.00),
        'claude-haiku-4-5-20251001': (0.80, 4.00),
        'claude-opus-4-20250514': (15.00, 75.00),
        'MiniMax-Text-01': (0.40, 1.10),
    }
    rates = pricing.get(model, (1.0, 3.0))  # default fallback
    input_cost = (input_tokens / 1_000_000) * rates[0]
    output_cost = (output_tokens / 1_000_000) * rates[1]
    return round(input_cost + output_cost, 6)


def log_ai_usage(
    provider: str,
    model: str,
    action: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    success: bool = True,
    error_message: str = '',
    duration_ms: int = 0,
) -> None:
    """Log an AI API call to the database.

    Failures are silently swallowed so that a logging error never interrupts
    the normal request flow.
    """
    try:
        from src.infrastructure.database import get_connection
        total = input_tokens + output_tokens
        cost = estimate_cost(provider, model, input_tokens, output_tokens)
        conn = get_connection()
        conn.execute(
            """INSERT INTO ai_usage_log
               (provider, model, action, input_tokens, output_tokens,
                total_tokens, cost_usd, success, error_message, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                provider,
                model,
                action,
                input_tokens,
                output_tokens,
                total,
                cost,
                1 if success else 0,
                error_message,
                duration_ms,
            ),
        )
        conn.commit()
    except Exception:
        pass


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    def identify_food(self, description: str = '', image_base64: Optional[str] = None) -> FoodIdentification:
        """Identify what food is present from a description or image.

        Returns a plain-language description without nutrition estimates.
        This is step 1 of the two-step analysis flow; call analyze_food
        afterwards with the confirmed description to get calories/macros.

        Args:
            description: Optional text hint from the user.
            image_base64: Optional base64-encoded image (JPEG/PNG/WebP).
        """
        ...

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
