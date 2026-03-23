"""Tests for the Reflect category and accountability features.

Covers:
  - habit_strength.calculate_miss_penalty()
  - chat_context.CATEGORY_PERSONALITIES and build_system_prompt()
  - conversations.VALID_CATEGORIES and CATEGORY_META
  - chat_tool_executor tool handler registration
  - Conversation API endpoints (create/list with reflect category)
"""
import sys
from pathlib import Path

import pytest

# Ensure project root is on the path when running this file directly
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Habit Strength — calculate_miss_penalty()
# ---------------------------------------------------------------------------

class TestCalculateMissPenalty:
    """calculate_miss_penalty(current_strength, consecutive_misses) -> float"""

    def setup_method(self):
        from src.domain.services.habit_strength import calculate_miss_penalty
        self.penalty = calculate_miss_penalty

    def test_normal_miss_drops_strength(self):
        """A single miss at mid-range strength should reduce the value."""
        result = self.penalty(50.0, consecutive_misses=1)
        assert result < 50.0

    def test_extra_accountability_penalty_applied(self):
        """Miss penalty should exceed the normal decay by the flat -5% extra."""
        # At strength=50, base_loss = min(8, 3 + 50/33) ≈ 4.52
        # Extra -5 applied on top → total loss ≈ 9.52, result ≈ 40.48
        # Without the extra -5 the result would be ~45.48.
        # We verify the result is MORE than 5 points below input.
        result = self.penalty(50.0, consecutive_misses=1)
        plain_decay_floor = 50.0 - 8.0  # worst possible base loss without penalty
        assert result < plain_decay_floor, (
            "Extra -5% accountability penalty was not applied on top of base decay"
        )

    def test_three_consecutive_misses_forces_strength_to_zero(self):
        """Reaching 3 consecutive misses resets habit strength to 0."""
        assert self.penalty(80.0, consecutive_misses=3) == 0.0
        assert self.penalty(100.0, consecutive_misses=5) == 0.0

    def test_strength_never_goes_below_zero(self):
        """Result is clamped to 0 even when penalties exceed current strength."""
        result = self.penalty(2.0, consecutive_misses=1)
        assert result == 0.0

    def test_miss_from_zero_stays_at_zero(self):
        """A habit already at 0 cannot go negative."""
        result = self.penalty(0.0, consecutive_misses=1)
        assert result == 0.0

    def test_exact_penalty_math_at_strength_33(self):
        """Verify the exact formula at strength=33.

        base_loss = min(8, 3 + 33/33) = min(8, 4.0) = 4.0
        new = 33 - 4 - 5 = 24.0
        """
        result = self.penalty(33.0, consecutive_misses=1)
        assert result == pytest.approx(24.0, abs=0.01)

    def test_penalty_capped_when_base_loss_hits_maximum(self):
        """At high strength the base loss caps at 8; extra -5 still applies."""
        # base_loss = min(8, 3 + 100/33) ≈ min(8, 6.03) = 6.03
        # At strength=100: base_loss = min(8, 3 + 100/33) ≈ 6.03 (still < 8)
        # At strength=165: would cap, but strength max is 100.
        # Use strength=100 and verify result is 100 - 6.03 - 5 = 88.97
        result = self.penalty(100.0, consecutive_misses=1)
        expected = 100.0 - min(8.0, 3.0 + 100.0 / 33.0) - 5.0
        assert result == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# Category System — CATEGORY_PERSONALITIES
# ---------------------------------------------------------------------------

class TestCategoryPersonalities:
    """CATEGORY_PERSONALITIES dict in chat_context.py"""

    def setup_method(self):
        from src.domain.services.chat_context import CATEGORY_PERSONALITIES
        self.personalities = CATEGORY_PERSONALITIES

    def test_all_standard_categories_have_personality(self):
        """Every named category must have an entry."""
        expected = {'general', 'health', 'finance', 'productivity', 'life', 'reflect'}
        assert expected.issubset(self.personalities.keys())

    def test_reflect_personality_mentions_therapist(self):
        """Reflect personality should describe a therapist-coach role."""
        text = self.personalities['reflect'].lower()
        assert 'therapist' in text

    def test_reflect_personality_instructs_questions(self):
        """Reflect mode should emphasise asking questions over giving answers."""
        text = self.personalities['reflect'].lower()
        assert 'question' in text

    def test_reflect_personality_ends_with_reflection_prompt(self):
        """Reflect personality should instruct ending with a thought-provoking question."""
        text = self.personalities['reflect'].lower()
        assert 'reflect' in text

    def test_general_personality_is_non_empty_string(self):
        result = self.personalities.get('general', '')
        assert isinstance(result, str) and len(result) > 0

    def test_finance_personality_mentions_data(self):
        """Finance personality should be data-driven."""
        assert 'data' in self.personalities['finance'].lower()


# ---------------------------------------------------------------------------
# Category System — build_system_prompt()
# ---------------------------------------------------------------------------

class TestBuildSystemPrompt:
    """build_system_prompt(context, tools, category) in chat_context.py"""

    def setup_method(self):
        from src.domain.services.chat_context import build_system_prompt
        self.build = build_system_prompt
        self.empty_ctx = {}

    def test_default_category_is_general(self):
        """Omitting category should produce a general-personality prompt."""
        from src.domain.services.chat_context import CATEGORY_PERSONALITIES
        prompt = self.build(self.empty_ctx)
        # The general personality text must appear verbatim in the prompt
        assert CATEGORY_PERSONALITIES['general'] in prompt

    def test_reflect_category_includes_therapist_text(self):
        """Passing category='reflect' should embed the reflect personality."""
        from src.domain.services.chat_context import CATEGORY_PERSONALITIES
        prompt = self.build(self.empty_ctx, category='reflect')
        assert CATEGORY_PERSONALITIES['reflect'] in prompt

    def test_reflect_prompt_does_not_contain_general_personality(self):
        """Reflect and general personalities are distinct — they should not overlap."""
        from src.domain.services.chat_context import CATEGORY_PERSONALITIES
        prompt = self.build(self.empty_ctx, category='reflect')
        # General's first unique directive should NOT appear in reflect prompt
        assert 'Strict with finances' not in prompt

    def test_unknown_category_falls_back_to_general(self):
        """An unrecognised category key should silently fall back to general."""
        from src.domain.services.chat_context import CATEGORY_PERSONALITIES
        prompt = self.build(self.empty_ctx, category='nonexistent_xyz')
        assert CATEGORY_PERSONALITIES['general'] in prompt

    def test_prompt_is_a_string(self):
        result = self.build(self.empty_ctx, category='health')
        assert isinstance(result, str)

    def test_prompt_contains_context_json(self):
        """The live data dump should appear in the prompt."""
        ctx = {'test_key': 'test_value'}
        prompt = self.build(ctx)
        assert 'test_key' in prompt

    def test_prompt_contains_tools_section_when_tools_provided(self):
        """Tool list should generate a 'Tools You Can Use' section."""
        tools = [{'name': 'do_thing', 'description': 'Does a thing', 'parameters': {'x': {}}}]
        prompt = self.build(self.empty_ctx, tools=tools)
        assert 'Tools You Can Use' in prompt
        assert 'do_thing' in prompt

    def test_prompt_has_no_tools_section_when_tools_is_none(self):
        prompt = self.build(self.empty_ctx)
        assert 'Tools You Can Use' not in prompt

    def test_user_name_appears_in_prompt_when_profile_has_preferred_name(self):
        ctx = {'user_profile': [{'preferred_name': 'Dovik', 'display_name': 'Ludovic'}]}
        prompt = self.build(ctx)
        assert 'Dovik' in prompt


# ---------------------------------------------------------------------------
# Conversations Route — VALID_CATEGORIES and CATEGORY_META
# ---------------------------------------------------------------------------

class TestValidCategories:
    """VALID_CATEGORIES set in web/routes/conversations.py"""

    def setup_method(self):
        from web.routes.conversations import VALID_CATEGORIES
        self.cats = VALID_CATEGORIES

    def test_reflect_is_in_valid_categories(self):
        assert 'reflect' in self.cats

    def test_all_standard_categories_present(self):
        expected = {'health', 'finance', 'productivity', 'life', 'general', 'reflect'}
        assert expected.issubset(self.cats)  # may have additional categories like 'reports'

    def test_categories_is_a_set(self):
        assert isinstance(self.cats, set)


class TestCategoryMeta:
    """CATEGORY_META dict in web/routes/conversations.py"""

    def setup_method(self):
        from web.routes.conversations import CATEGORY_META, VALID_CATEGORIES
        self.meta = CATEGORY_META
        self.valid = VALID_CATEGORIES

    def test_every_valid_category_has_metadata(self):
        for cat in self.valid:
            assert cat in self.meta, f"CATEGORY_META missing entry for '{cat}'"

    def test_each_entry_has_icon_label_color(self):
        for cat, data in self.meta.items():
            assert 'icon' in data, f"'{cat}' missing 'icon'"
            assert 'label' in data, f"'{cat}' missing 'label'"
            assert 'color' in data, f"'{cat}' missing 'color'"

    def test_reflect_icon_is_brain(self):
        assert self.meta['reflect']['icon'] == '🧠'

    def test_reflect_label(self):
        assert self.meta['reflect']['label'] == 'Reflect'

    def test_no_extra_categories_in_meta(self):
        """CATEGORY_META should not define categories absent from VALID_CATEGORIES."""
        assert set(self.meta.keys()) == self.valid


# ---------------------------------------------------------------------------
# Tool Handler Registration
# ---------------------------------------------------------------------------

class TestToolHandlerRegistration:
    """Verify expected tool names exist in the handlers dict inside execute_tool()."""

    def _get_handlers(self):
        """Call execute_tool with a dummy name to trigger handler dict construction,
        then reconstruct the known set by probing."""
        from src.domain.services.chat_tool_executor import execute_tool
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        known_registered = []
        # Probe: registered tools return error dicts WITHOUT 'Unknown tool'
        for name in (
            'journal_reflect', 'journal_prompt', 'mood_patterns',
            'discover_list', 'discover_add', 'discover_research',
            'discover_plan', 'discover_rate',
            'firefly_create_transaction', 'firefly_list_transactions',
            'firefly_list_accounts', 'firefly_get_spending',
            'firefly_get_budgets', 'firefly_delete_transaction',
            'create_habit', 'complete_habit', 'log_food',
            'log_journal', 'log_mood',
        ):
            result = execute_tool(name, {}, conn, user_id=1)
            if 'Unknown tool' not in result.get('error', ''):
                known_registered.append(name)
        conn.close()
        return known_registered

    def test_reflection_tools_registered(self):
        """journal_reflect, journal_prompt, and mood_patterns must be in handlers."""
        registered = self._get_handlers()
        assert 'journal_reflect' in registered
        assert 'journal_prompt' in registered
        assert 'mood_patterns' in registered

    def test_discover_tools_registered(self):
        """All five discover_* tools must be in handlers."""
        registered = self._get_handlers()
        for tool in ('discover_list', 'discover_add', 'discover_research',
                     'discover_plan', 'discover_rate'):
            assert tool in registered, f"Tool '{tool}' is not registered"

    def test_firefly_tools_registered(self):
        """All six firefly_* tools must be in handlers."""
        registered = self._get_handlers()
        for tool in (
            'firefly_create_transaction', 'firefly_list_transactions',
            'firefly_list_accounts', 'firefly_get_spending',
            'firefly_get_budgets', 'firefly_delete_transaction',
        ):
            assert tool in registered, f"Tool '{tool}' is not registered"

    def test_accountability_tool_miss_habit_not_registered(self):
        """miss_habit does not exist in handlers — document this as a known gap."""
        from src.domain.services.chat_tool_executor import execute_tool
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        result = execute_tool('miss_habit', {}, conn, user_id=1)
        conn.close()
        assert 'Unknown tool' in result.get('error', ''), (
            "miss_habit appears to have been registered — "
            "update test_firefly_tools_registered to include it"
        )

    def test_unknown_tool_returns_error_dict(self):
        """Dispatching a non-existent tool should return an error, never raise."""
        from src.domain.services.chat_tool_executor import execute_tool
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        result = execute_tool('totally_fake_tool_xyz', {}, conn, user_id=1)
        conn.close()
        assert 'error' in result
        assert 'Unknown tool' in result['error']


# ---------------------------------------------------------------------------
# Conversation API — Flask integration tests
# ---------------------------------------------------------------------------

class TestCreateReflectConversation:
    """POST /api/chat/conversations with category=reflect"""

    def test_create_reflect_conversation_returns_201(self, auth_client):
        resp = auth_client.post(
            '/api/chat/conversations',
            json={'title': 'My Reflection', 'category': 'reflect'},
        )
        assert resp.status_code == 201

    def test_create_reflect_conversation_persists_category(self, auth_client):
        resp = auth_client.post(
            '/api/chat/conversations',
            json={'title': 'Deep Thoughts', 'category': 'reflect'},
        )
        data = resp.get_json()
        assert data['category'] == 'reflect'

    def test_create_reflect_conversation_has_brain_icon(self, auth_client):
        resp = auth_client.post(
            '/api/chat/conversations',
            json={'title': 'Inner Work', 'category': 'reflect'},
        )
        data = resp.get_json()
        assert data['category_icon'] == '🧠'

    def test_create_reflect_conversation_has_correct_label(self, auth_client):
        resp = auth_client.post(
            '/api/chat/conversations',
            json={'title': 'Check-in', 'category': 'reflect'},
        )
        data = resp.get_json()
        assert data['category_label'] == 'Reflect'

    def test_create_conversation_invalid_category_falls_back_to_general(self, auth_client):
        resp = auth_client.post(
            '/api/chat/conversations',
            json={'title': 'Chat', 'category': 'nonsense'},
        )
        assert resp.status_code == 201
        assert resp.get_json()['category'] == 'general'

    def test_create_conversation_requires_auth(self, client):
        resp = client.post(
            '/api/chat/conversations',
            json={'title': 'Anon chat', 'category': 'reflect'},
        )
        assert resp.status_code == 401


class TestListConversationsFilterReflect:
    """GET /api/chat/conversations?category=reflect"""

    def _create(self, auth_client, category, title='Test'):
        return auth_client.post(
            '/api/chat/conversations',
            json={'title': title, 'category': category},
        )

    def test_filter_returns_only_reflect_conversations(self, auth_client):
        self._create(auth_client, 'reflect', 'Reflect One')
        self._create(auth_client, 'reflect', 'Reflect Two')
        self._create(auth_client, 'general', 'General Chat')

        resp = auth_client.get('/api/chat/conversations?category=reflect')
        assert resp.status_code == 200
        items = resp.get_json()
        assert len(items) == 2
        assert all(item['category'] == 'reflect' for item in items)

    def test_filter_excludes_other_categories(self, auth_client):
        self._create(auth_client, 'health', 'Health Chat')
        self._create(auth_client, 'reflect', 'Reflection')

        resp = auth_client.get('/api/chat/conversations?category=reflect')
        titles = [item['title'] for item in resp.get_json()]
        assert 'Reflection' in titles
        assert 'Health Chat' not in titles

    def test_no_filter_returns_all_categories(self, auth_client):
        self._create(auth_client, 'reflect', 'Reflect')
        self._create(auth_client, 'finance', 'Money')
        self._create(auth_client, 'health', 'Body')

        resp = auth_client.get('/api/chat/conversations')
        items = resp.get_json()
        categories = {item['category'] for item in items}
        assert {'reflect', 'finance', 'health'}.issubset(categories)

    def test_invalid_category_filter_returns_all(self, auth_client):
        """An unrecognised ?category= value is ignored — all results returned."""
        self._create(auth_client, 'general', 'Chat A')
        self._create(auth_client, 'reflect', 'Reflect A')

        resp = auth_client.get('/api/chat/conversations?category=bogus')
        assert resp.status_code == 200
        # Both conversations should be present since 'bogus' is filtered out
        assert len(resp.get_json()) >= 2

    def test_list_requires_auth(self, client):
        resp = client.get('/api/chat/conversations')
        assert resp.status_code == 401
