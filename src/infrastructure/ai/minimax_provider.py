"""MiniMax AI provider.

MiniMax exposes an OpenAI-compatible REST API, so this provider extends
OpenAIProvider with MiniMax-specific defaults.
"""
import os

from .openai_provider import OpenAIProvider

_MINIMAX_BASE_URL = 'https://api.minimax.io/v1'
_MINIMAX_DEFAULT_MODEL = 'MiniMax-M2'


class MiniMaxProvider(OpenAIProvider):
    """MiniMax provider using the OpenAI-compatible MiniMax API."""

    def __init__(self):
        self.api_key = (
            self._get_setting('ai_minimax_key')
            or os.environ.get('MINIMAX_API_KEY', '')
        )
        self.base_url = _MINIMAX_BASE_URL
        self.model = (
            self._get_setting('ai_minimax_model')
            or os.environ.get('MINIMAX_MODEL', _MINIMAX_DEFAULT_MODEL)
        )

    def is_available(self) -> bool:
        return bool(self.api_key)
