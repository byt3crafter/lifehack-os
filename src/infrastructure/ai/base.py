"""Abstract AI provider interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


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


@dataclass
class HabitPlanPhase:
    """A single phase within an AI-generated habit plan."""
    phase: int = 1
    name: str = ""
    description: str = ""
    days: int = 14
    micro_tasks: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class HabitPlan:
    """AI-generated habit plan from a user goal description."""
    name: str = ""
    description: str = ""
    category: str = "health"
    difficulty: str = "beginner"
    duration_weeks: int = 8
    phases: List[HabitPlanPhase] = field(default_factory=list)


# Available auto-verification checks the AI can reference when building plans.
AVAILABLE_AUTO_CHECKS = [
    {"check": "food_log_count", "description": "Count of food log entries today", "example": {"type": "auto", "check": "food_log_count", "operator": ">=", "value": 2}},
    {"check": "walk_count", "description": "Count of walk/exercise sessions today", "example": {"type": "auto", "check": "walk_count", "operator": ">=", "value": 1}},
    {"check": "walk_km", "description": "Total distance walked today in km", "example": {"type": "auto", "check": "walk_km", "operator": ">=", "value": 3}},
    {"check": "checkin_done", "description": "Daily check-in submitted today", "example": {"type": "auto", "check": "checkin_done"}},
    {"check": "deep_work_minutes", "description": "Total deep work session minutes today", "example": {"type": "auto", "check": "deep_work_minutes", "operator": ">=", "value": 60}},
    {"check": "calories_under_goal", "description": "Total calories logged is under daily goal", "example": {"type": "auto", "check": "calories_under_goal"}},
    {"check": "no_alcohol", "description": "Avoided alcohol flag set in today's check-in", "example": {"type": "auto", "check": "no_alcohol"}},
    {"check": "replacement_count", "description": "Count of replacement actions logged today", "example": {"type": "auto", "check": "replacement_count", "operator": ">=", "value": 1}},
    {"check": "fasting_hours", "description": "Completed fasting duration in hours today", "example": {"type": "auto", "check": "fasting_hours", "operator": ">=", "value": 16}},
]


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


def parse_habit_plan(data: dict) -> Optional['HabitPlan']:
    """Parse a raw dict from an AI response into a HabitPlan.

    The dict should look like::

        {
            "name": "Sobriety Journey",
            "description": "...",
            "category": "health",
            "difficulty": "beginner",
            "duration_weeks": 8,
            "phases": [
                {
                    "phase": 1,
                    "name": "Phase 1",
                    "description": "...",
                    "days": 14,
                    "micro_tasks": [
                        {"name": "Log every meal", "verification_rule": {"type": "auto", "check": "food_log_count", "operator": ">=", "value": 2}},
                        {"name": "Do something manually", "verification_rule": {"type": "manual"}}
                    ]
                }
            ]
        }

    Returns None if the data is too malformed to use.
    """
    if not isinstance(data, dict):
        return None
    name = (data.get('name') or '').strip()
    if not name:
        return None

    raw_phases = data.get('phases', [])
    if not isinstance(raw_phases, list) or not raw_phases:
        return None

    phases: List[HabitPlanPhase] = []
    for i, p in enumerate(raw_phases):
        if not isinstance(p, dict):
            continue
        raw_tasks = p.get('micro_tasks', [])
        parsed_tasks: List[Dict[str, Any]] = []
        for t in raw_tasks:
            if isinstance(t, str):
                # Backwards-compat: plain string task name — manual verification
                parsed_tasks.append({
                    'name': t.strip(),
                    'verification_rule': {'type': 'manual'},
                })
            elif isinstance(t, dict):
                task_name = (t.get('name') or '').strip()
                if not task_name:
                    continue
                vr = t.get('verification_rule', {'type': 'manual'})
                if not isinstance(vr, dict):
                    vr = {'type': 'manual'}
                parsed_tasks.append({'name': task_name, 'verification_rule': vr})

        phases.append(HabitPlanPhase(
            phase=p.get('phase', i + 1),
            name=(p.get('name') or f'Phase {i + 1}').strip(),
            description=(p.get('description') or '').strip(),
            days=int(p.get('days', 14) or 14),
            micro_tasks=parsed_tasks,
        ))

    if not phases:
        return None

    return HabitPlan(
        name=name,
        description=(data.get('description') or '').strip(),
        category=(data.get('category') or 'health').strip(),
        difficulty=(data.get('difficulty') or 'beginner').strip(),
        duration_weeks=int(data.get('duration_weeks', 8) or 8),
        phases=phases,
    )


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
    def generate_habit_plan(self, goal: str) -> Optional['HabitPlan']:
        """Generate a structured habit plan from a user goal description.

        Args:
            goal: Natural-language description of the habit goal, e.g.
                  "I want to stop drinking alcohol and build healthy habits".

        Returns:
            A HabitPlan dataclass or None if generation failed.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and reachable."""
        ...

    def chat_with_context(self, system_prompt: str, messages: List[Dict[str, Any]]) -> str:
        """Send a multi-turn conversation to the AI.

        Args:
            system_prompt: Full system prompt including live context data.
            messages: Ordered list of prior turns plus the current user message.
                      Each item is ``{"role": "user"|"assistant", "content": "..."}``.

        Returns:
            The AI response text, or '' on failure.

        The default implementation collapses the conversation history into a
        single user message so that providers without native multi-turn support
        (Ollama, Anthropic single-message path, etc.) still work correctly.
        Providers that natively support multi-turn conversations should override
        this method and pass the messages array directly to their API.
        """
        # Build a compact conversation string from the message history
        history_lines = []
        for m in messages[:-1]:  # all except the last (current) user message
            role_label = "User" if m.get("role") == "user" else "Assistant"
            history_lines.append(f"{role_label}: {m.get('content', '')}")

        current_message = messages[-1].get("content", "") if messages else ""

        if history_lines:
            combined = (
                "Conversation so far:\n"
                + "\n".join(history_lines)
                + f"\n\nUser: {current_message}"
            )
        else:
            combined = current_message

        # Delegate to the existing single-message pathway via generate_insight
        # but we cannot use that (it returns an Insight dataclass). Instead we
        # call the internal helpers that each concrete subclass exposes.
        # Subclasses that override this method bypass this logic entirely.
        return self._chat_fallback(system_prompt, combined)

    def _chat_fallback(self, system_prompt: str, user_message: str) -> str:
        """Fallback: subclasses may override to call their internal _chat/_generate/_messages.

        Base implementation returns '' — concrete providers override either
        ``chat_with_context`` directly or ``_chat_fallback``.
        """
        return ""
