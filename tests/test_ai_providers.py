"""Tests for AI provider abstraction layer.

These tests stay entirely within the domain — no Flask, no database.
Network calls are tested via lightweight stubs so we never require a running
Ollama or OpenAI service.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.ai.base import FoodAnalysis, Insight, AIProvider
from src.infrastructure.ai.null import NullAIProvider
from src.infrastructure.ai.factory import get_ai_provider
from src.infrastructure.ai.ollama import OllamaProvider
from src.infrastructure.ai.openai_provider import OpenAIProvider


# ---------------------------------------------------------------------------
# NullAIProvider
# ---------------------------------------------------------------------------

class TestNullAIProvider:
    def setup_method(self):
        self.provider = NullAIProvider()

    def test_is_available_returns_true(self):
        assert self.provider.is_available() is True

    def test_analyze_food_returns_food_analysis(self):
        result = self.provider.analyze_food("scrambled eggs")
        assert isinstance(result, FoodAnalysis)

    def test_analyze_food_estimated_is_false(self):
        result = self.provider.analyze_food("scrambled eggs")
        assert result.estimated is False

    def test_analyze_food_calories_is_none(self):
        result = self.provider.analyze_food("anything")
        assert result.calories is None

    def test_generate_insight_returns_none(self):
        result = self.provider.generate_insight({"total_xp": 100})
        assert result is None

    def test_generate_weekly_report_returns_empty_string(self):
        result = self.provider.generate_weekly_report({"xp_earned": 500})
        assert result == ""

    def test_conforms_to_ai_provider_interface(self):
        assert isinstance(self.provider, AIProvider)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestAIProviderFactory:
    def test_factory_returns_null_provider_by_default(self):
        with patch.dict("os.environ", {"LIFEHACK_AI_PROVIDER": "none"}):
            provider = get_ai_provider()
        assert isinstance(provider, NullAIProvider)

    def test_factory_returns_null_when_env_not_set(self):
        env = {"LIFEHACK_AI_PROVIDER": ""}
        with patch.dict("os.environ", env, clear=False):
            # Empty string falls through to else branch → NullAIProvider
            import importlib
            import src.infrastructure.ai.factory as factory_mod
            importlib.reload(factory_mod)
            provider = factory_mod.get_ai_provider()
        assert isinstance(provider, NullAIProvider)

    def test_factory_returns_ollama_provider(self):
        with patch.dict("os.environ", {"LIFEHACK_AI_PROVIDER": "ollama"}):
            provider = get_ai_provider()
        assert isinstance(provider, OllamaProvider)

    def test_factory_returns_openai_provider(self):
        with patch.dict("os.environ", {"LIFEHACK_AI_PROVIDER": "openai"}):
            provider = get_ai_provider()
        assert isinstance(provider, OpenAIProvider)

    def test_factory_case_insensitive(self):
        with patch.dict("os.environ", {"LIFEHACK_AI_PROVIDER": "OLLAMA"}):
            provider = get_ai_provider()
        assert isinstance(provider, OllamaProvider)


# ---------------------------------------------------------------------------
# OllamaProvider._parse_json
# ---------------------------------------------------------------------------

class TestOllamaProviderParseJson:
    def setup_method(self):
        self.provider = OllamaProvider()

    def test_parses_clean_json(self):
        text = '{"calories": 350, "protein_g": 10}'
        result = self.provider._parse_json(text)
        assert result == {"calories": 350, "protein_g": 10}

    def test_parses_json_embedded_in_text(self):
        text = 'Here is the result: {"calories": 200} — hope that helps!'
        result = self.provider._parse_json(text)
        assert result["calories"] == 200

    def test_returns_empty_dict_for_invalid_json(self):
        text = "This is not JSON at all."
        result = self.provider._parse_json(text)
        assert result == {}

    def test_returns_empty_dict_for_empty_string(self):
        result = self.provider._parse_json("")
        assert result == {}

    def test_parses_json_array(self):
        text = '[{"name": "a"}, {"name": "b"}]'
        result = self.provider._parse_json(text)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_returns_empty_dict_for_malformed_braces(self):
        text = "{ not valid json }"
        result = self.provider._parse_json(text)
        assert result == {}

    def test_analyze_food_returns_false_when_generate_fails(self):
        with patch.object(self.provider, "_generate", return_value=""):
            result = self.provider.analyze_food("chicken breast")
        assert result.estimated is False

    def test_analyze_food_returns_estimated_true_on_valid_response(self):
        fake_response = '{"calories": 165, "protein_g": 31, "carbs_g": 0, "fat_g": 4, "description": "chicken"}'
        with patch.object(self.provider, "_generate", return_value=fake_response):
            result = self.provider.analyze_food("chicken breast")
        assert result.estimated is True
        assert result.calories == 165
        assert result.protein_g == 31

    def test_generate_insight_returns_none_on_empty_response(self):
        with patch.object(self.provider, "_generate", return_value=""):
            result = self.provider.generate_insight({"total_xp": 100})
        assert result is None

    def test_generate_insight_returns_insight_on_valid_response(self):
        fake = '{"title": "Keep it up", "content": "You are doing great.", "type": "advice"}'
        with patch.object(self.provider, "_generate", return_value=fake):
            result = self.provider.generate_insight({"total_xp": 500})
        assert isinstance(result, Insight)
        assert result.title == "Keep it up"
        assert result.content == "You are doing great."

    def test_is_available_returns_false_when_request_fails(self):
        with patch("requests.get", side_effect=Exception("Connection refused")):
            assert self.provider.is_available() is False

    def test_is_available_returns_true_when_request_succeeds(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("requests.get", return_value=mock_resp):
            assert self.provider.is_available() is True


# ---------------------------------------------------------------------------
# OpenAIProvider._parse_json
# ---------------------------------------------------------------------------

class TestOpenAIProviderParseJson:
    def setup_method(self):
        self.provider = OpenAIProvider()

    def test_parses_clean_json(self):
        text = '{"title": "Insight", "content": "Do more."}'
        result = self.provider._parse_json(text)
        assert result["title"] == "Insight"

    def test_parses_json_embedded_in_prose(self):
        text = 'Sure! Here you go: {"calories": 500} — enjoy.'
        result = self.provider._parse_json(text)
        assert result["calories"] == 500

    def test_returns_empty_dict_for_garbage_input(self):
        assert self.provider._parse_json("no json here") == {}

    def test_returns_empty_dict_for_empty_string(self):
        assert self.provider._parse_json("") == {}

    def test_analyze_food_returns_not_estimated_on_empty_chat(self):
        with patch.object(self.provider, "_chat", return_value=""):
            result = self.provider.analyze_food("pasta")
        assert result.estimated is False

    def test_analyze_food_returns_estimated_true_on_valid_response(self):
        fake = '{"calories": 400, "protein_g": 14, "carbs_g": 70, "fat_g": 8, "description": "pasta"}'
        with patch.object(self.provider, "_chat", return_value=fake):
            result = self.provider.analyze_food("pasta")
        assert result.estimated is True
        assert result.calories == 400

    def test_generate_insight_returns_none_on_empty_response(self):
        with patch.object(self.provider, "_chat", return_value=""):
            result = self.provider.generate_insight({"total_xp": 0})
        assert result is None

    def test_generate_insight_returns_insight_object(self):
        fake = '{"title": "Nice work", "content": "Keep going!", "type": "celebration"}'
        with patch.object(self.provider, "_chat", return_value=fake):
            result = self.provider.generate_insight({"total_xp": 1000})
        assert isinstance(result, Insight)
        assert result.insight_type == "celebration"

    def test_is_available_true_when_api_key_set(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test123"}):
            provider = OpenAIProvider()
        assert provider.is_available() is True

    def test_is_available_false_when_no_api_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            provider = OpenAIProvider()
        assert provider.is_available() is False
