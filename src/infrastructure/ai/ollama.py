"""Ollama AI provider — free, local, private LLM."""
import json
import os
from typing import Optional

import requests

from .base import AIProvider, FoodAnalysis, Insight


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

    def _generate(self, prompt: str) -> str:
        """Send a prompt to Ollama and return the response text."""
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=60
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception:
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

    def analyze_food(self, description: str) -> FoodAnalysis:
        prompt = f"""Estimate the nutritional content of this food. Return ONLY a JSON object, no other text.

Food: {description}

JSON format:
{{"calories": number, "protein_g": number, "carbs_g": number, "fat_g": number, "description": "brief description"}}"""

        response = self._generate(prompt)
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

        response = self._generate(prompt)
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

        return self._generate(prompt).strip()

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False
