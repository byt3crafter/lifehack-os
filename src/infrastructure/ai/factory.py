"""AI provider factory — returns the configured provider."""
import os

from .base import AIProvider
from .null import NullAIProvider


def get_ai_provider() -> AIProvider:
    """Get the AI provider based on LIFEHACK_AI_PROVIDER env var.

    Options: none (default), ollama, openai
    """
    provider = os.environ.get('LIFEHACK_AI_PROVIDER', 'none').lower()

    if provider == 'ollama':
        from .ollama import OllamaProvider
        return OllamaProvider()
    elif provider == 'openai':
        from .openai_provider import OpenAIProvider
        return OpenAIProvider()
    else:
        return NullAIProvider()
