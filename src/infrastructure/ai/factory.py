"""AI provider factory — returns the configured provider for a given task."""
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


def _make_provider(name: str) -> AIProvider:
    """Create a provider instance by name."""
    if name == 'ollama':
        from .ollama import OllamaProvider
        return OllamaProvider()
    elif name == 'openai':
        from .openai_provider import OpenAIProvider
        return OpenAIProvider()
    elif name == 'anthropic':
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    elif name == 'minimax':
        from .minimax_provider import MiniMaxProvider
        return MiniMaxProvider()
    elif name == 'chatgpt_oauth':
        from .chatgpt_oauth_provider import ChatGPTOAuthProvider
        return ChatGPTOAuthProvider()
    else:
        return NullAIProvider()


def get_ai_provider(task: str = 'default') -> AIProvider:
    """Get AI provider for a specific task.

    Tasks: 'food', 'insights', 'reports', 'default'

    Resolution order:
    1. ``ai_provider_{task}`` row in app_settings (per-task override).
    2. ``ai_provider_default`` row in app_settings (global default).
    3. ``ai_provider`` row in app_settings (backwards compat).
    4. ``LIFEHACK_AI_PROVIDER`` environment variable (legacy / Docker fallback).

    Options: none (default), ollama, openai, anthropic, chatgpt_oauth, minimax
    """
    provider_name = (
        _get_setting(f'ai_provider_{task}')
        or _get_setting('ai_provider_default')
        or _get_setting('ai_provider')  # backwards compat
        or os.environ.get('LIFEHACK_AI_PROVIDER', 'none')
    ).lower()

    return _make_provider(provider_name)
