"""Unit and integration tests for the AI report generation system.

Covers:
- REPORT_PROMPTS structure and content
- _get_or_create_reports_conversation idempotency
- _create_weekly_conversation uniqueness
- generate_report with no AI provider (NullAIProvider)
- generate_report idempotency (second call returns None)
- VALID_CATEGORIES and CATEGORY_META
- API endpoint routing with report_type param
- ai_reports table existence (migration 30)
- Row persistence and notification creation after generation

AI calls are always mocked — no network access required.
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CANNED_RESPONSE = "## Morning Briefing\nYour day looks great."


def _make_mock_provider(content: str = CANNED_RESPONSE) -> MagicMock:
    """Return a mock AI provider that returns ``content`` from chat_with_context."""
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.chat_with_context.return_value = content
    return provider


def _ensure_user(conn) -> int:
    """Ensure at least one user exists and return their id.

    The ``test_conn`` fixture creates an empty DB.  Tests that don't go
    through ``create_app()`` / ``ensure_admin_user()`` need to seed a user
    directly so the service layer has someone to generate reports for.
    """
    row = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
    if row is not None:
        return row["id"]

    from werkzeug.security import generate_password_hash

    cursor = conn.execute(
        "INSERT INTO users (username, password_hash, display_name, is_admin) VALUES (?, ?, ?, 1)",
        ("testadmin", generate_password_hash("password"), "Test Admin"),
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.execute("INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)", (user_id,))
    conn.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user_id,))
    conn.commit()
    return user_id


def _get_user_id(conn) -> int:
    """Return a valid user id, creating one if the DB is empty."""
    return _ensure_user(conn)


# ---------------------------------------------------------------------------
# 1. Report prompts exist
# ---------------------------------------------------------------------------

class TestReportPrompts:
    def test_report_prompts_exist(self):
        """REPORT_PROMPTS must have morning, evening, and weekly keys."""
        from src.domain.services.report_generator import REPORT_PROMPTS

        assert "morning" in REPORT_PROMPTS
        assert "evening" in REPORT_PROMPTS
        assert "weekly" in REPORT_PROMPTS

    def test_report_prompts_contain_instructions(self):
        """Each prompt must contain the word 'Structure' (format instructions)."""
        from src.domain.services.report_generator import REPORT_PROMPTS

        for report_type, prompt in REPORT_PROMPTS.items():
            assert "Structure" in prompt, (
                f"Prompt for '{report_type}' is missing format instructions"
            )

    def test_report_prompts_contain_name_placeholder(self):
        """Each prompt must contain {name} so the user's name can be injected."""
        from src.domain.services.report_generator import REPORT_PROMPTS

        for report_type, prompt in REPORT_PROMPTS.items():
            assert "{name}" in prompt, (
                f"Prompt for '{report_type}' is missing {{name}} placeholder"
            )


# ---------------------------------------------------------------------------
# 2. _get_or_create_reports_conversation
# ---------------------------------------------------------------------------

class TestGetOrCreateReportsConversation:
    def test_creates_conversation_on_first_call(self, test_conn):
        """First call creates a new 'AI Reports' conversation and returns its id."""
        from src.domain.services.report_generator import _get_or_create_reports_conversation

        user_id = _get_user_id(test_conn)
        conv_id = _get_or_create_reports_conversation(test_conn, user_id)

        assert isinstance(conv_id, int)
        assert conv_id > 0

    def test_returns_same_id_on_second_call(self, test_conn):
        """Second call returns the same conversation id — no duplicate is created."""
        from src.domain.services.report_generator import _get_or_create_reports_conversation

        user_id = _get_user_id(test_conn)
        first_id = _get_or_create_reports_conversation(test_conn, user_id)
        second_id = _get_or_create_reports_conversation(test_conn, user_id)

        assert first_id == second_id

    def test_conversation_has_reports_category(self, test_conn):
        """Created conversation must be in the 'reports' category and pinned."""
        from src.domain.services.report_generator import _get_or_create_reports_conversation

        user_id = _get_user_id(test_conn)
        conv_id = _get_or_create_reports_conversation(test_conn, user_id)

        row = test_conn.execute(
            "SELECT title, category, pinned FROM chat_conversations WHERE id=?",
            (conv_id,),
        ).fetchone()
        assert row["title"] == "AI Reports"
        assert row["category"] == "reports"
        assert row["pinned"] == 1


# ---------------------------------------------------------------------------
# 3. _create_weekly_conversation
# ---------------------------------------------------------------------------

class TestCreateWeeklyConversation:
    def test_creates_unique_conversation_each_call(self, test_conn):
        """Each call creates a brand-new conversation (not idempotent by design)."""
        from src.domain.services.report_generator import _create_weekly_conversation

        user_id = _get_user_id(test_conn)
        now = datetime(2026, 3, 23, 9, 0, 0)

        first_id = _create_weekly_conversation(test_conn, user_id, now)
        second_id = _create_weekly_conversation(test_conn, user_id, now)

        assert first_id != second_id

    def test_title_includes_week_range(self, test_conn):
        """Conversation title must follow the 'Weekly Report · Mon D-D' pattern."""
        from src.domain.services.report_generator import _create_weekly_conversation

        user_id = _get_user_id(test_conn)
        # 2026-03-23 is a Monday; week spans Mar 23-29
        now = datetime(2026, 3, 23, 9, 0, 0)
        conv_id = _create_weekly_conversation(test_conn, user_id, now)

        row = test_conn.execute(
            "SELECT title FROM chat_conversations WHERE id=?", (conv_id,)
        ).fetchone()
        assert "Weekly Report" in row["title"]
        assert "Mar" in row["title"]


# ---------------------------------------------------------------------------
# 4. generate_report — no provider
# ---------------------------------------------------------------------------

class TestGenerateReportNoProvider:
    def test_returns_none_when_provider_not_available(self, test_conn, monkeypatch):
        """generate_report returns None when the AI provider is not available."""
        from src.domain.services import report_generator

        unavailable = MagicMock()
        unavailable.is_available.return_value = False
        monkeypatch.setattr(
            "src.infrastructure.ai.factory.get_ai_provider",
            lambda *a, **kw: unavailable,
        )

        user_id = _get_user_id(test_conn)
        result = report_generator.generate_report(test_conn, user_id, "morning")

        assert result is None


# ---------------------------------------------------------------------------
# 5. generate_report — idempotency
# ---------------------------------------------------------------------------

class TestGenerateReportIdempotent:
    def test_second_call_same_day_returns_none(self, test_conn, monkeypatch):
        """A report already generated today must not be generated a second time."""
        from src.domain.services import report_generator

        monkeypatch.setattr(
            "src.infrastructure.ai.factory.get_ai_provider",
            lambda *a, **kw: _make_mock_provider(),
        )

        user_id = _get_user_id(test_conn)

        first = report_generator.generate_report(test_conn, user_id, "morning")
        assert first is not None, "First call should succeed"

        second = report_generator.generate_report(test_conn, user_id, "morning")
        assert second is None, "Second call same day should be skipped"

    def test_first_call_returns_success_dict(self, test_conn, monkeypatch):
        """First successful call returns a dict with success, report_id, conversation_id."""
        from src.domain.services import report_generator

        monkeypatch.setattr(
            "src.infrastructure.ai.factory.get_ai_provider",
            lambda *a, **kw: _make_mock_provider(),
        )

        user_id = _get_user_id(test_conn)
        result = report_generator.generate_report(test_conn, user_id, "evening")

        assert result is not None
        assert result["success"] is True
        assert isinstance(result["report_id"], int)
        assert isinstance(result["conversation_id"], int)


# ---------------------------------------------------------------------------
# 6. Category tests
# ---------------------------------------------------------------------------

class TestValidCategories:
    def test_reports_category_in_valid(self):
        """'reports' must be present in VALID_CATEGORIES."""
        from web.routes.conversations import VALID_CATEGORIES

        assert "reports" in VALID_CATEGORIES

    def test_reports_category_meta_icon(self):
        """CATEGORY_META['reports'] must exist and use the bar-chart icon."""
        from web.routes.conversations import CATEGORY_META

        assert "reports" in CATEGORY_META
        assert CATEGORY_META["reports"]["icon"] == "📊"

    def test_reports_category_meta_label(self):
        """CATEGORY_META['reports'] must have a human-readable label."""
        from web.routes.conversations import CATEGORY_META

        assert CATEGORY_META["reports"]["label"] == "Reports"


# ---------------------------------------------------------------------------
# 7. API endpoint tests
# ---------------------------------------------------------------------------

class TestGenerateEndpoint:
    """Tests for POST /api/notifications/generate?report_type=..."""

    def test_generate_with_report_type_morning_returns_200(self, auth_client, monkeypatch):
        """report_type=morning should enter the report branch and return 200."""
        monkeypatch.setattr(
            "src.infrastructure.ai.factory.get_ai_provider",
            lambda *a, **kw: _make_mock_provider(),
        )

        resp = auth_client.post("/api/notifications/generate?report_type=morning")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["report_type"] == "morning"

    def test_generate_with_report_type_invalid_falls_through_to_nudges(self, auth_client):
        """report_type=invalid is not a known type; the endpoint falls through to nudge logic."""
        resp = auth_client.post("/api/notifications/generate?report_type=invalid")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        # Nudge branch produces a 'generated' count, not a 'report_type' key
        assert "generated" in data
        assert "report_type" not in data

    def test_generate_without_report_type_runs_nudge_logic(self, auth_client):
        """Missing report_type should run the standard nudge-generation branch."""
        resp = auth_client.post("/api/notifications/generate")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "generated" in data

    def test_generate_unauthenticated_returns_401(self, client):
        """Unauthenticated requests must be rejected with 401."""
        resp = client.post("/api/notifications/generate?report_type=morning")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 8. Integration tests
# ---------------------------------------------------------------------------

class TestAiReportsIntegration:
    def test_ai_reports_table_exists(self, test_conn):
        """Migration 30 must have created the ai_reports table."""
        tables = {
            row[0]
            for row in test_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "ai_reports" in tables

    def test_ai_reports_table_has_required_columns(self, test_conn):
        """ai_reports must have the columns the service writes to."""
        cols = {
            row[1]
            for row in test_conn.execute("PRAGMA table_info(ai_reports)").fetchall()
        }
        required = {"id", "user_id", "type", "content", "conversation_id", "period_start", "period_end"}
        assert required.issubset(cols)

    def test_report_saved_to_ai_reports_table(self, test_conn, monkeypatch):
        """After a successful generation, a row must exist in ai_reports."""
        from src.domain.services import report_generator

        monkeypatch.setattr(
            "src.infrastructure.ai.factory.get_ai_provider",
            lambda *a, **kw: _make_mock_provider(),
        )

        user_id = _get_user_id(test_conn)
        result = report_generator.generate_report(test_conn, user_id, "morning")

        assert result is not None
        row = test_conn.execute(
            "SELECT * FROM ai_reports WHERE id=?", (result["report_id"],)
        ).fetchone()
        assert row is not None
        assert row["user_id"] == user_id
        assert row["type"] == "morning"
        assert CANNED_RESPONSE in row["content"]

    def test_notification_created_for_report(self, test_conn, monkeypatch):
        """After generation, a notification of type ai_report_morning must be inserted."""
        from src.domain.services import report_generator

        monkeypatch.setattr(
            "src.infrastructure.ai.factory.get_ai_provider",
            lambda *a, **kw: _make_mock_provider(),
        )

        user_id = _get_user_id(test_conn)
        report_generator.generate_report(test_conn, user_id, "morning")

        row = test_conn.execute(
            "SELECT * FROM notifications WHERE user_id=? AND type=?",
            (user_id, "ai_report_morning"),
        ).fetchone()
        assert row is not None
        assert "Morning Briefing" in row["title"]

    def test_notification_links_to_conversation(self, test_conn, monkeypatch):
        """The notification link must point to the generated conversation."""
        from src.domain.services import report_generator

        monkeypatch.setattr(
            "src.infrastructure.ai.factory.get_ai_provider",
            lambda *a, **kw: _make_mock_provider(),
        )

        user_id = _get_user_id(test_conn)
        result = report_generator.generate_report(test_conn, user_id, "morning")

        row = test_conn.execute(
            "SELECT link FROM notifications WHERE user_id=? AND type=?",
            (user_id, "ai_report_morning"),
        ).fetchone()
        assert f"/chat?conv={result['conversation_id']}" == row["link"]

    def test_unknown_report_type_returns_none(self, test_conn):
        """generate_report with an unknown type must return None without raising."""
        from src.domain.services import report_generator

        user_id = _get_user_id(test_conn)
        result = report_generator.generate_report(test_conn, user_id, "quarterly")

        assert result is None

    def test_message_inserted_into_conversation(self, test_conn, monkeypatch):
        """The AI response must be stored as an assistant message in the conversation."""
        from src.domain.services import report_generator

        monkeypatch.setattr(
            "src.infrastructure.ai.factory.get_ai_provider",
            lambda *a, **kw: _make_mock_provider(),
        )

        user_id = _get_user_id(test_conn)
        result = report_generator.generate_report(test_conn, user_id, "morning")

        msg = test_conn.execute(
            "SELECT role, content FROM chat_messages WHERE conversation_id=? AND user_id=?",
            (result["conversation_id"], user_id),
        ).fetchone()
        assert msg is not None
        assert msg["role"] == "assistant"
        assert CANNED_RESPONSE in msg["content"]
