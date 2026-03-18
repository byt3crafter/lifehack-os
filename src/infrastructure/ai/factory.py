"""AI provider factory — returns the configured provider."""
import os

from .base import AIProvider
from .null import NullAIProvider


def _get_setting(key: str) -> str:
    """Read a single value from the app_settings table. Returns '' on any error."""
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


def get_ai_provider() -> AIProvider:
    """Get the AI provider.

    Resolution order for the provider type:
    1. ``ai_provider`` row in app_settings (configurable from the UI).
    2. ``LIFEHACK_AI_PROVIDER`` environment variable (legacy / Docker fallback).

    Options: none (default), ollama, openai
    """
    provider = (
        _get_setting('ai_provider')
        or os.environ.get('LIFEHACK_AI_PROVIDER', 'none')
    ).lower()

    if provider == 'ollama':
        from .ollama import OllamaProvider
        return OllamaProvider()
    elif provider == 'openai':
        from .openai_provider import OpenAIProvider
        return OpenAIProvider()
    else:
        return NullAIProvider()
