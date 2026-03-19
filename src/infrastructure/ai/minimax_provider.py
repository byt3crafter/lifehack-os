"""MiniMax AI provider.

MiniMax exposes an OpenAI-compatible REST API, so this provider extends
OpenAIProvider with MiniMax-specific defaults.
"""
import os

from .openai_provider import OpenAIProvider

_MINIMAX_BASE_URL = 'https://api.minimax.io/v1'
_MINIMAX_DEFAULT_MODEL = 'MiniMax-M2'


class MiniMaxProvider(OpenAIProvider):
    """MiniMax provider using the OpenAI-compatible MiniMax API.

    Note: MiniMax M2 does NOT support vision/image input.
    Images are ignored — only text descriptions are analyzed.
    """

    def __init__(self, user_id: int = None):
        self._user_id = user_id
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

    def identify_food(self, description: str = '', image_base64: str = None) -> 'FoodIdentification':
        """MiniMax doesn't support images — use text description only."""
        if not description and image_base64:
            from .base import FoodIdentification
            return FoodIdentification(available=False)
        return super().identify_food(description, image_base64=None)

    def analyze_food(self, description: str, image_base64: str = None) -> 'FoodAnalysis':
        """MiniMax doesn't support images — use text description only."""
        if not description and image_base64:
            # Can't analyze an image without text on MiniMax
            from .base import FoodAnalysis
            return FoodAnalysis(
                estimated=False,
                description="MiniMax does not support image analysis. Please describe the food."
            )
        # Call parent without image (MiniMax ignores it anyway)
        return super().analyze_food(description, image_base64=None)
