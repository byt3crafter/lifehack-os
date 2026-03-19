"""ChatGPT OAuth provider — uses Codex Responses API with streaming.

Uses the OAuth JWT token against the ChatGPT backend Codex endpoint:
POST https://chatgpt.com/backend-api/codex/responses

This endpoint requires:
- stream: true (mandatory)
- instructions field (not system message)
- chatgpt-account-id header (extracted from JWT)
- Models: gpt-5.4, gpt-5.3-codex, etc. (not gpt-4o/gpt-4o-mini)
"""
import base64
import json
import os
import time
from typing import Optional

import requests

from .base import AIProvider, FoodAnalysis, FoodIdentification, Insight, log_ai_usage


class ChatGPTOAuthProvider(AIProvider):
    """ChatGPT OAuth provider using the Codex Responses API."""

    ENDPOINT = 'https://chatgpt.com/backend-api/codex/responses'
    DEFAULT_MODEL = 'gpt-5.4'

    def __init__(self):
        self.token = self._get_setting('openai_oauth_token') or ''
        self.model = self._get_setting('ai_chatgpt_model') or self.DEFAULT_MODEL
        self.account_id = self._extract_account_id(self.token) if self.token else ''

    @staticmethod
    def _get_setting(key: str) -> str:
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

    @staticmethod
    def _extract_account_id(token: str) -> str:
        """Extract chatgpt_account_id from the JWT payload."""
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return ''
            # Add padding
            payload_b64 = parts[1] + '=='
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            return payload.get('https://api.openai.com/auth', {}).get('chatgpt_account_id', '')
        except Exception:
            return ''

    def _call_codex(self, instructions: str, user_input: str, action: str = 'chat') -> str:
        """Call the Codex Responses API with streaming and return the full text."""
        start = time.time()
        try:
            resp = requests.post(
                self.ENDPOINT,
                headers={
                    'Authorization': f'Bearer {self.token}',
                    'Content-Type': 'application/json',
                    'chatgpt-account-id': self.account_id,
                    'OpenAI-Beta': 'responses=experimental',
                },
                json={
                    'model': self.model,
                    'instructions': instructions,
                    'input': [{'role': 'user', 'content': user_input}],
                    'stream': True,
                    'store': False,
                },
                timeout=60,
                stream=True,
            )
            duration_ms = int((time.time() - start) * 1000)

            if resp.status_code != 200:
                error_text = resp.text[:200]
                log_ai_usage('chatgpt_oauth', self.model, action, success=False,
                             error_message=f'HTTP {resp.status_code}: {error_text}',
                             duration_ms=duration_ms)
                return ''

            # Parse SSE stream
            full_text = ''
            input_tokens = 0
            output_tokens = 0
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode('utf-8')
                if not line.startswith('data: '):
                    continue
                try:
                    event = json.loads(line[6:])
                    etype = event.get('type', '')
                    if etype == 'response.output_text.delta':
                        full_text += event.get('delta', '')
                    elif etype == 'response.completed':
                        usage = event.get('response', {}).get('usage', {})
                        input_tokens = usage.get('input_tokens', 0)
                        output_tokens = usage.get('output_tokens', 0)
                        break
                except json.JSONDecodeError:
                    continue

            duration_ms = int((time.time() - start) * 1000)
            log_ai_usage('chatgpt_oauth', self.model, action,
                         input_tokens=input_tokens, output_tokens=output_tokens,
                         success=True, duration_ms=duration_ms)
            return full_text

        except Exception as exc:
            duration_ms = int((time.time() - start) * 1000)
            log_ai_usage('chatgpt_oauth', self.model, action, success=False,
                         error_message=str(exc), duration_ms=duration_ms)
            try:
                from web.routes.app_log import log_event
                import traceback
                log_event('error', 'ai', f'ChatGPT OAuth call failed: {exc}', traceback.format_exc())
            except Exception:
                pass
            return ''

    def _parse_json(self, text: str) -> dict:
        """Extract JSON from response text."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to find JSON in response
        for start_char in ('{', '['):
            start = text.find(start_char)
            if start == -1:
                continue
            end_char = '}' if start_char == '{' else ']'
            end = text.rfind(end_char) + 1
            if end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
        return {}

    def identify_food(self, description: str = '', image_base64: Optional[str] = None) -> FoodIdentification:
        # Codex Responses API does not support inline images.
        if not description and image_base64:
            return FoodIdentification(available=False)

        instructions = "You are a food recognition assistant. Return ONLY valid JSON, no other text."
        hint = f" The user says: {description}." if description else ""
        user_msg = (
            f"What food is this?{hint} Describe it briefly in one sentence.\n\n"
            'Return: {"description": "Avocado toast with fried egg", "confidence": "high"}'
        )
        response = self._call_codex(instructions, user_msg, action='food_identify')
        data = self._parse_json(response)

        if not data or not data.get('description'):
            return FoodIdentification(available=False)

        return FoodIdentification(
            description=data.get('description', ''),
            confidence=data.get('confidence', 'medium'),
            available=True,
        )

    def analyze_food(self, description: str, image_base64: Optional[str] = None) -> FoodAnalysis:
        instructions = "You are a nutrition analyst. Return ONLY valid JSON, no other text."
        food_ref = description if description else "the food in the image"
        user_msg = (
            f'Estimate the nutritional content of: {food_ref}\n\n'
            f'Return: {{"calories": number, "protein_g": number, "carbs_g": number, "fat_g": number, "description": "brief description"}}'
        )
        # Note: Codex Responses API doesn't support inline images yet
        # If only image provided with no description, ask user to describe
        if not description and image_base64:
            return FoodAnalysis(
                estimated=False,
                description="Please describe the food — ChatGPT OAuth doesn't support image analysis yet."
            )

        response = self._call_codex(instructions, user_msg, action='food_analysis')
        data = self._parse_json(response)
        if not data:
            return FoodAnalysis(estimated=False)

        return FoodAnalysis(
            calories=data.get('calories'),
            protein_g=data.get('protein_g'),
            carbs_g=data.get('carbs_g'),
            fat_g=data.get('fat_g'),
            description=data.get('description', description),
            estimated=True,
        )

    def generate_insight(self, user_state: dict) -> Optional[Insight]:
        instructions = "You are a personal discipline coach. Be direct and actionable. Return ONLY valid JSON."
        user_msg = (
            f'Based on this data, give ONE short insight (2 sentences max):\n'
            f'Stats: {user_state.get("total_xp", 0)} XP, '
            f'{user_state.get("habits_completed", 0)}/{user_state.get("habits_total", 0)} habits today, '
            f'best streak: {user_state.get("best_streak", 0)} days, '
            f'mood: {user_state.get("mood", "not logged")}\n\n'
            f'Return: {{"title": "short title", "content": "insight text", "type": "advice"}}'
        )
        response = self._call_codex(instructions, user_msg, action='generate_insight')
        data = self._parse_json(response)
        if not data or 'content' not in data:
            return None
        return Insight(
            title=data.get('title', 'Insight'),
            content=data['content'],
            insight_type=data.get('type', 'advice'),
        )

    def generate_weekly_report(self, weekly_data: dict) -> str:
        instructions = "Write concise weekly progress reports. Be encouraging but honest. 3-4 sentences max."
        user_msg = (
            f'Weekly data:\n'
            f'XP earned: {weekly_data.get("xp_earned", 0)}\n'
            f'Habits: {weekly_data.get("habits_completed", 0)}/{weekly_data.get("habits_possible", 0)}\n'
            f'Check-ins: {weekly_data.get("checkins", 0)}/7\n'
            f'Best streak: {weekly_data.get("best_streak", 0)} days\n'
            f'Mood trend: {weekly_data.get("mood_trend", "stable")}'
        )
        return self._call_codex(instructions, user_msg, action='weekly_report').strip()

    def is_available(self) -> bool:
        return bool(self.token and self.account_id)
