"""Anthropic Claude API provider."""
import json
import os
import time
import traceback
from typing import Optional

import requests

from .base import AIProvider, FoodAnalysis, Insight, log_ai_usage

_ANTHROPIC_API_VERSION = "2023-06-01"


class AnthropicProvider(AIProvider):
    """Anthropic Claude API provider."""

    def __init__(self):
        self.api_key = self._get_setting('ai_anthropic_key') or os.environ.get('ANTHROPIC_API_KEY', '')
        self.model = (
            self._get_setting('ai_anthropic_model')
            or os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')
        )
        self.base_url = 'https://api.anthropic.com/v1'

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

    def _messages(self, system: str, user_content, action: str = 'chat') -> str:
        """Call the Anthropic messages API.

        ``user_content`` may be a plain string or a list of content blocks
        (for multimodal requests that include an image).
        """
        if isinstance(user_content, str):
            user_content = [{"type": "text", "text": user_content}]

        start = time.time()
        try:
            resp = requests.post(
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": _ANTHROPIC_API_VERSION,
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 512,
                    "system": system,
                    "messages": [
                        {"role": "user", "content": user_content}
                    ],
                },
                timeout=30,
            )
            duration_ms = int((time.time() - start) * 1000)
            resp.raise_for_status()
            data = resp.json()
            usage = data.get('usage', {})
            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)
            log_ai_usage(
                provider='anthropic',
                model=self.model,
                action=action,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                success=True,
                duration_ms=duration_ms,
            )
            # Content is a list of blocks; grab the first text block.
            for block in data.get("content", []):
                if block.get("type") == "text":
                    return block["text"]
        except Exception as exc:
            duration_ms = int((time.time() - start) * 1000)
            log_ai_usage(
                provider='anthropic',
                model=self.model,
                action=action,
                success=False,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
            try:
                from web.routes.app_log import log_event
                log_event('error', 'ai', f'Anthropic call failed [{action}]: {str(exc)}', traceback.format_exc())
            except Exception:
                pass
        return ""

    def _parse_json(self, text: str) -> dict:
        """Try to extract JSON from a response string."""
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

    def analyze_food(self, description: str, image_base64: str = None) -> FoodAnalysis:
        system = "You are a nutrition analyst. Return ONLY valid JSON, no other text."
        food_ref = description if description else "the food shown in the image"
        text_prompt = (
            f"Estimate the nutritional content of: {food_ref}\n\n"
            'Return: {"calories": number, "protein_g": number, "carbs_g": number, '
            '"fat_g": number, "description": "brief description"}'
        )

        if image_base64:
            user_content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_base64,
                    },
                },
                {"type": "text", "text": text_prompt},
            ]
        else:
            user_content = text_prompt

        response = self._messages(system, user_content, action='food_analysis')
        data = self._parse_json(response)

        if not data:
            return FoodAnalysis(estimated=False)

        return FoodAnalysis(
            calories=data.get('calories'),
            protein_g=data.get('protein_g'),
            carbs_g=data.get('carbs_g'),
            fat_g=data.get('fat_g'),
            description=data.get('description', food_ref),
            estimated=True,
        )

    def generate_insight(self, user_state: dict) -> Optional[Insight]:
        system = "You are a personal discipline coach. Be direct, encouraging, and actionable. Return ONLY valid JSON."
        user = (
            "Based on this data, give ONE short insight (2 sentences max):\n\n"
            f"Stats: {user_state.get('total_xp', 0)} XP, "
            f"{user_state.get('habits_completed', 0)}/{user_state.get('habits_total', 0)} habits today, "
            f"best streak: {user_state.get('best_streak', 0)} days, "
            f"mood: {user_state.get('mood', 'not logged')}\n\n"
            'Return: {"title": "short title", "content": "insight text", "type": "advice"}'
        )

        response = self._messages(system, user, action='generate_insight')
        data = self._parse_json(response)

        if not data or 'content' not in data:
            return None

        return Insight(
            title=data.get('title', 'Insight'),
            content=data['content'],
            insight_type=data.get('type', 'advice'),
        )

    def generate_weekly_report(self, weekly_data: dict) -> str:
        system = "You write concise weekly progress reports. Be encouraging but honest. 3-4 sentences max."
        user = (
            "Weekly data:\n"
            f"XP earned: {weekly_data.get('xp_earned', 0)}\n"
            f"Habits: {weekly_data.get('habits_completed', 0)}/{weekly_data.get('habits_possible', 0)}\n"
            f"Check-ins: {weekly_data.get('checkins', 0)}/7\n"
            f"Best streak: {weekly_data.get('best_streak', 0)} days\n"
            f"Mood trend: {weekly_data.get('mood_trend', 'stable')}"
        )
        return self._messages(system, user, action='weekly_report').strip()

    def is_available(self) -> bool:
        return bool(self.api_key)
