"""AI provider abstraction — supports multiple backends."""
from .base import AIProvider, FoodAnalysis, Insight
from .factory import get_ai_provider

__all__ = ['AIProvider', 'FoodAnalysis', 'Insight', 'get_ai_provider']
