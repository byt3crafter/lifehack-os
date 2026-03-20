"""AI provider factory — returns the configured provider for a given task.

Supports per-user AI settings via user_settings/user_integrations tables.
Falls back to global app_settings for backward compatibility.
"""
import os
from typing import Optional

from .base import AIProvider
from .null import NullAIProvider


def _get_setting(key: str, user_id: Optional[int] = None) -> str:
    """Read a setting value, respecting BYOK preference.

    Resolution:
      - BYOK enabled:  user_settings → app_settings → ''
      - BYOK disabled: app_settings only → ''

    When ``user_id`` is None the global app_settings path is used directly.
    """
    try:
        from src.infrastructure.database import get_connection
        conn = get_connection()

        if user_id is not None:
            # Check whether this user has BYOK enabled
            user = conn.execute(
                "SELECT byok_enabled FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            byok = user and user['byok_enabled']

            if byok:
                # BYOK path: use the user's own keys first
                row = conn.execute(
                    "SELECT value FROM user_settings WHERE user_id = ? AND key = ?",
                    (user_id, key),
                ).fetchone()
                if row and row['value']:
                    return row['value']
            # If BYOK is off (or the user has no personal key), fall through
            # to the global app_settings below — intentionally no early return.

        # Global fallback (admin's / app-level keys)
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
        if row and row['value']:
            return row['value']
    except Exception:
        pass
    return ''


def _make_provider(name: str, user_id: Optional[int] = None) -> AIProvider:
    """Create a provider instance by name."""
    if name == 'ollama':
        from .ollama import OllamaProvider
        return OllamaProvider(user_id=user_id)
    elif name == 'openai':
        from .openai_provider import OpenAIProvider
        return OpenAIProvider(user_id=user_id)
    elif name == 'anthropic':
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(user_id=user_id)
    elif name == 'minimax':
        from .minimax_provider import MiniMaxProvider
        return MiniMaxProvider(user_id=user_id)
    elif name == 'chatgpt_oauth':
        from .chatgpt_oauth_provider import ChatGPTOAuthProvider
        return ChatGPTOAuthProvider(user_id=user_id)
    else:
        return NullAIProvider()


def get_ai_provider(task: str = 'default', user_id: Optional[int] = None) -> AIProvider:
    """Get AI provider for a specific task.

    Args:
        task: 'food', 'insights', 'reports', 'habits', 'default'
        user_id: When given, per-user settings take priority over global.

    Resolution order:
    1. user_settings ``ai_provider_{task}`` (if user_id given).
    2. user_settings ``ai_provider_default`` (if user_id given).
    3. app_settings ``ai_provider_{task}`` (global per-task).
    4. app_settings ``ai_provider_default`` (global default).
    5. app_settings ``ai_provider`` (backwards compat).
    6. ``LIFEHACK_AI_PROVIDER`` environment variable (Docker fallback).
    """
    provider_name = (
        _get_setting(f'ai_provider_{task}', user_id)
        or _get_setting('ai_provider_default', user_id)
        or _get_setting('ai_provider', user_id)
        or os.environ.get('LIFEHACK_AI_PROVIDER', 'none')
    ).lower()

    return _make_provider(provider_name, user_id)
