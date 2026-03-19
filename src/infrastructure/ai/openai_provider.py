"""OpenAI-compatible AI provider — works with OpenAI, Azure, Groq, Together, etc."""
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


class OpenAIProvider(AIProvider):
    """OpenAI-compatible API. Works with any endpoint that speaks the OpenAI format."""

    def __init__(self):
        self.api_key = self._get_setting('ai_openai_key') or os.environ.get('OPENAI_API_KEY', '')
        self.base_url = self._get_setting('ai_openai_url') or os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        self.model = self._get_setting('ai_openai_model') or os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')

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

    def _chat(self, system: str, user: str, image_base64: str = None, action: str = 'chat') -> str:
        """Send a chat completion request.

        When ``image_base64`` is provided the user turn is sent as a
        multipart content array so vision-capable models (e.g. gpt-4o) can
        use the image.
        """
        if image_base64:
            user_content = [
                {"type": "text", "text": user},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}",
                        "detail": "low"
                    }
                }
            ]
        else:
            user_content = user

        start = time.time()
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500
                },
                timeout=30
            )
            duration_ms = int((time.time() - start) * 1000)
            resp.raise_for_status()
            body = resp.json()
            usage = body.get('usage', {})
            input_tokens = usage.get('prompt_tokens', 0)
            output_tokens = usage.get('completion_tokens', 0)
            log_ai_usage(
                provider='openai',
                model=self.model,
                action=action,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                success=True,
                duration_ms=duration_ms,
            )
            return body["choices"][0]["message"]["content"]
        except Exception as exc:
            duration_ms = int((time.time() - start) * 1000)
            log_ai_usage(
                provider='openai',
                model=self.model,
                action=action,
                success=False,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
            try:
                from web.routes.app_log import log_event
                log_event('error', 'ai', f'OpenAI call failed [{action}]: {str(exc)}', traceback.format_exc())
            except Exception:
                pass
            return ""

    def _parse_json(self, text: str) -> dict:
        """Try to extract JSON from response, handling think tags and markdown."""
        import re
        # Strip <think>...</think> tags (MiniMax wraps responses in these)
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        # Strip markdown code blocks
        md_match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, flags=re.DOTALL)
        if md_match:
            text = md_match.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
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
        system = "You are a food recognition assistant. Return ONLY valid JSON, no other text."
        hint = f" The user says: {description}." if description else ""
        user = (
            f"What food is this?{hint} Describe it briefly in one sentence.\n\n"
            'Return: {"description": "Avocado toast with fried egg", "confidence": "high"}'
        )

        response = self._chat(system, user, image_base64=image_base64, action='food_identify')
        data = self._parse_json(response)

        if not data or not data.get('description'):
            return FoodIdentification(available=False)

        return FoodIdentification(
            description=data.get('description', ''),
            confidence=data.get('confidence', 'medium'),
            available=True,
        )

    def analyze_food(self, description: str, image_base64: str = None) -> FoodAnalysis:
        system = "You are a nutrition analyst. Return ONLY valid JSON, no other text."
        food_ref = description if description else "the food shown in the image"
        user = f"""Estimate the nutritional content of: {food_ref}

Return: {{"calories": number, "protein_g": number, "carbs_g": number, "fat_g": number, "description": "brief description"}}"""

        response = self._chat(system, user, image_base64=image_base64, action='food_analysis')
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
        system = "You are a personal discipline coach. Be direct, encouraging, and actionable. Return ONLY valid JSON."
        user = f"""Based on this data, give ONE short insight (2 sentences max):

Stats: {user_state.get('total_xp', 0)} XP, {user_state.get('habits_completed', 0)}/{user_state.get('habits_total', 0)} habits today, best streak: {user_state.get('best_streak', 0)} days, mood: {user_state.get('mood', 'not logged')}

Return: {{"title": "short title", "content": "insight text", "type": "advice"}}"""

        response = self._chat(system, user, action='generate_insight')
        data = self._parse_json(response)

        if not data or 'content' not in data:
            return None

        return Insight(
            title=data.get('title', 'Insight'),
            content=data['content'],
            insight_type=data.get('type', 'advice')
        )

    def generate_weekly_report(self, weekly_data: dict) -> str:
        system = "You write concise weekly progress reports. Be encouraging but honest. 3-4 sentences max."
        user = f"""Weekly data:
XP earned: {weekly_data.get('xp_earned', 0)}
Habits: {weekly_data.get('habits_completed', 0)}/{weekly_data.get('habits_possible', 0)}
Check-ins: {weekly_data.get('checkins', 0)}/7
Best streak: {weekly_data.get('best_streak', 0)} days
Mood trend: {weekly_data.get('mood_trend', 'stable')}"""

        return self._chat(system, user, action='weekly_report').strip()

    def generate_habit_plan(self, goal: str) -> Optional[HabitPlan]:
        """Generate a structured habit plan from a natural-language goal."""
        import json as _json
        checks_summary = _json.dumps(
            [{'check': c['check'], 'description': c['description']} for c in AVAILABLE_AUTO_CHECKS],
            indent=2,
        )
        system = (
            "You are a habit design expert. Return ONLY valid JSON, no other text. "
            "Design progressive, achievable habit plans with 3-4 phases."
        )
        user = f"""Create a structured habit plan for this goal: "{goal}"

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

        response = self._chat(system, user, action='generate_habit_plan')
        if not response:
            return None
        try:
            raw = self._parse_json(response)
            return parse_habit_plan(raw)
        except Exception:
            return None

    def chat_with_context(self, system_prompt: str, messages: list) -> str:
        """Send a multi-turn conversation using the OpenAI chat/completions endpoint."""
        start = time.time()
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": system_prompt}] + messages,
                    "temperature": 0.7,
                    "max_tokens": 1024,
                },
                timeout=60,
            )
            duration_ms = int((time.time() - start) * 1000)
            resp.raise_for_status()
            body = resp.json()
            usage = body.get("usage", {})
            log_ai_usage(
                provider="openai",
                model=self.model,
                action="chat",
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                success=True,
                duration_ms=duration_ms,
            )
            return body["choices"][0]["message"]["content"]
        except Exception as exc:
            duration_ms = int((time.time() - start) * 1000)
            log_ai_usage(
                provider="openai",
                model=self.model,
                action="chat",
                success=False,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
            try:
                from web.routes.app_log import log_event
                log_event("error", "ai", f"OpenAI chat_with_context failed: {exc}", traceback.format_exc())
            except Exception:
                pass
            return ""

    def is_available(self) -> bool:
        return bool(self.api_key)
