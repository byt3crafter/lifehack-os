"""Ollama AI provider — free, local, private LLM."""
import json
import os
import time
import traceback
from typing import Optional

import requests

from .base import (
    AIProvider, FoodAnalysis, FoodIdentification, Insight, HabitPlan,
    AVAILABLE_AUTO_CHECKS, parse_habit_plan, log_ai_usage,
)


class OllamaProvider(AIProvider):
    """Local LLM via Ollama. Free, runs on your machine."""

    def __init__(self):
        self.base_url = self._get_setting('ai_ollama_url') or os.environ.get('OLLAMA_URL', 'http://localhost:11434')
        self.model = self._get_setting('ai_ollama_model') or os.environ.get('OLLAMA_MODEL', 'llama3')

    @staticmethod
    def _get_setting(key: str) -> str:
        """Read a value from app_settings. Returns '' on any error."""
        try:
            from src.infrastructure.database import get_connection
            conn = get_connection()
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
            if row and row['value']:
                return row['value']
        except Exception:
            pass
        return ''

    def _generate(self, prompt: str, images: list = None, action: str = 'chat') -> str:
        """Send a prompt to Ollama and return the response text.

        ``images`` is a list of base64-encoded image strings — only used
        with multimodal models such as llava.
        """
        start = time.time()
        try:
            payload = {"model": self.model, "prompt": prompt, "stream": False}
            if images:
                payload["images"] = images
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=60
            )
            duration_ms = int((time.time() - start) * 1000)
            resp.raise_for_status()
            body = resp.json()
            # Ollama returns prompt_eval_count (input) and eval_count (output)
            input_tokens = body.get('prompt_eval_count', 0)
            output_tokens = body.get('eval_count', 0)
            log_ai_usage(
                provider='ollama',
                model=self.model,
                action=action,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                success=True,
                duration_ms=duration_ms,
            )
            return body.get("response", "")
        except Exception as exc:
            duration_ms = int((time.time() - start) * 1000)
            log_ai_usage(
                provider='ollama',
                model=self.model,
                action=action,
                success=False,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
            try:
                from web.routes.app_log import log_event
                log_event('error', 'ai', f'Ollama call failed [{action}]: {str(exc)}', traceback.format_exc())
            except Exception:
                pass
            return ""

    def _parse_json(self, text: str) -> dict:
        """Try to extract JSON from LLM response."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to find JSON in response
        for start in (text.find('{'), text.find('[')):
            if start == -1:
                continue
            end = text.rfind('}') + 1 if text.find('{') == start else text.rfind(']') + 1
            if end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
        return {}

    def identify_food(self, description: str = '', image_base64: str = None) -> FoodIdentification:
        hint = f" The user says: {description}." if description else ""
        prompt = (
            f"What food is this?{hint} Describe it briefly in one sentence. "
            "Return ONLY a JSON object, no other text.\n\n"
            'JSON format: {"description": "Avocado toast with fried egg", "confidence": "high"}'
        )

        images = [image_base64] if image_base64 else None
        response = self._generate(prompt, images=images, action='food_identify')
        data = self._parse_json(response)

        if not data or not data.get('description'):
            return FoodIdentification(available=False)

        return FoodIdentification(
            description=data.get('description', ''),
            confidence=data.get('confidence', 'medium'),
            available=True,
        )

    def analyze_food(self, description: str, image_base64: str = None) -> FoodAnalysis:
        food_ref = description if description else "the food shown in the image"
        prompt = f"""Estimate the nutritional content of this food. Return ONLY a JSON object, no other text.

Food: {food_ref}

JSON format:
{{"calories": number, "protein_g": number, "carbs_g": number, "fat_g": number, "description": "brief description"}}"""

        images = [image_base64] if image_base64 else None
        response = self._generate(prompt, images=images, action='food_analysis')
        data = self._parse_json(response)

        if not data:
            return FoodAnalysis(estimated=False)

        return FoodAnalysis(
            calories=data.get('calories'),
            protein_g=data.get('protein_g'),
            carbs_g=data.get('carbs_g'),
            fat_g=data.get('fat_g'),
            description=data.get('description', description),
            estimated=True
        )

    def generate_insight(self, user_state: dict) -> Optional[Insight]:
        xp = user_state.get('total_xp', 0)
        habits_done = user_state.get('habits_completed', 0)
        habits_total = user_state.get('habits_total', 0)
        streak = user_state.get('best_streak', 0)
        mood = user_state.get('mood')

        prompt = f"""You are a personal discipline coach. Based on this user data, give ONE short, actionable insight (2 sentences max).

Stats: {xp} XP, {habits_done}/{habits_total} habits done today, best streak: {streak} days, mood: {mood or 'not logged'}

Return ONLY JSON: {{"title": "short title", "content": "1-2 sentence insight", "type": "advice"}}"""

        response = self._generate(prompt, action='generate_insight')
        data = self._parse_json(response)

        if not data or 'content' not in data:
            return None

        return Insight(
            title=data.get('title', 'Insight'),
            content=data['content'],
            insight_type=data.get('type', 'advice')
        )

    def generate_weekly_report(self, weekly_data: dict) -> str:
        prompt = f"""Write a brief weekly progress report (3-4 sentences) based on this data:

XP earned: {weekly_data.get('xp_earned', 0)}
Habits completed: {weekly_data.get('habits_completed', 0)}/{weekly_data.get('habits_possible', 0)}
Check-ins: {weekly_data.get('checkins', 0)}/7
Best streak: {weekly_data.get('best_streak', 0)} days
Mood trend: {weekly_data.get('mood_trend', 'stable')}

Be encouraging but honest. No fluff."""

        return self._generate(prompt, action='weekly_report').strip()

    def generate_habit_plan(self, goal: str) -> Optional[HabitPlan]:
        """Generate a structured habit plan from a natural-language goal."""
        import json as _json
        checks_summary = _json.dumps(
            [{'check': c['check'], 'description': c['description']} for c in AVAILABLE_AUTO_CHECKS],
            indent=2,
        )
        prompt = f"""You are a habit design expert. Return ONLY valid JSON, no other text.

Create a structured habit plan for this goal: "{goal}"

Available auto-verification checks (use these in verification_rule when applicable):
{checks_summary}

Return this exact JSON structure:
{{
  "name": "habit name (short)",
  "description": "brief description",
  "category": "health|fitness|mindset|learning|sobriety|productivity",
  "difficulty": "beginner|intermediate|advanced",
  "duration_weeks": 8,
  "phases": [
    {{
      "phase": 1,
      "name": "Phase name",
      "description": "what to do in this phase",
      "days": 14,
      "micro_tasks": [
        {{"name": "task name", "verification_rule": {{"type": "auto", "check": "food_log_count", "operator": ">=", "value": 2}}}},
        {{"name": "manual task", "verification_rule": {{"type": "manual"}}}}
      ]
    }}
  ]
}}"""

        response = self._generate(prompt, action='generate_habit_plan')
        if not response:
            return None
        try:
            raw = self._parse_json(response)
            return parse_habit_plan(raw)
        except Exception:
            return None

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False
