"""OpenAI-compatible AI provider — works with OpenAI, Azure, Groq, Together, etc."""
import json
import os
from typing import Optional

import requests

from .base import AIProvider, FoodAnalysis, Insight


class OpenAIProvider(AIProvider):
    """OpenAI-compatible API. Works with any endpoint that speaks the OpenAI format."""

    def __init__(self):
        self.api_key = os.environ.get('OPENAI_API_KEY', '')
        self.base_url = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        self.model = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')

    def _chat(self, system: str, user: str) -> str:
        """Send a chat completion request."""
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
                        {"role": "user", "content": user}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500
                },
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            return ""

    def _parse_json(self, text: str) -> dict:
        """Try to extract JSON from response."""
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

    def analyze_food(self, description: str) -> FoodAnalysis:
        system = "You are a nutrition analyst. Return ONLY valid JSON, no other text."
        user = f"""Estimate the nutritional content of: {description}

Return: {{"calories": number, "protein_g": number, "carbs_g": number, "fat_g": number, "description": "brief description"}}"""

        response = self._chat(system, user)
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

        response = self._chat(system, user)
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

        return self._chat(system, user).strip()

    def is_available(self) -> bool:
        return bool(self.api_key)
