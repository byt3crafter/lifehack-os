"""Unit tests for the notifications system.

Coverage:
- GET /api/notifications
- GET /api/notifications/count
- POST /api/notifications/<id>/read
- POST /api/notifications/read-all
- POST /api/notifications/<id>/dismiss
- POST /api/notifications/generate  (cron + admin auth)
- JSON serialization contract
"""
import os
import json
import pytest
from datetime import datetime, timedelta


# ── Helpers ──────────────────────────────────────────────────────────────────

def _insert_notification(conn, user_id, *, title="Test", body="Body",
                          notif_type="test_type", icon="bell", link="/",
                          read=0, dismissed=0, expires_at=None):
    """Insert a notification row and return its id."""
    cur = conn.execute(
        "INSERT INTO notifications (user_id, type, title, body, icon, link, read, dismissed, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, notif_type, title, body, icon, link, read, dismissed, expires_at),
    )
    conn.commit()
    return cur.lastrowid


def _get_user_id(conn):
    """Return the id of the first (admin) user created by bootstrap."""
    row = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
    return row["id"]


# ── API Tests ─────────────────────────────────────────────────────────────────

class TestGetNotificationsEmpty:
    def test_returns_empty_list_and_zero_unread(self, auth_client):
        resp = auth_client.get("/api/notifications")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["notifications"] == []
        assert data["unread_count"] == 0


class TestGetCountEmpty:
    def test_returns_zero_unread(self, auth_client):
        resp = auth_client.get("/api/notifications/count")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["unread"] == 0


class TestCreateAndGetNotification:
    def test_inserted_notification_appears_in_list(self, auth_client, test_conn):
        user_id = _get_user_id(test_conn)
        notif_id = _insert_notification(test_conn, user_id, title="Hello", body="World")

        resp = auth_client.get("/api/notifications")
        assert resp.status_code == 200
        data = resp.get_json()

        assert len(data["notifications"]) == 1
        n = data["notifications"][0]
        assert n["id"] == notif_id
        assert n["title"] == "Hello"
        assert n["body"] == "World"
        assert data["unread_count"] == 1


class TestMarkRead:
    def test_mark_read_sets_read_flag(self, auth_client, test_conn):
        user_id = _get_user_id(test_conn)
        notif_id = _insert_notification(test_conn, user_id, title="Unread")

        resp = auth_client.post(f"/api/notifications/{notif_id}/read")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

        # Verify the DB row is now read=1
        row = test_conn.execute(
            "SELECT read FROM notifications WHERE id=?", (notif_id,)
        ).fetchone()
        assert row["read"] == 1

    def test_unread_count_is_zero_after_mark_read(self, auth_client, test_conn):
        user_id = _get_user_id(test_conn)
        _insert_notification(test_conn, user_id)

        auth_client.post(f"/api/notifications/1/read")

        resp = auth_client.get("/api/notifications/count")
        data = resp.get_json()
        assert data["unread"] == 0


class TestMarkAllRead:
    def test_three_notifications_all_marked_read(self, auth_client, test_conn):
        user_id = _get_user_id(test_conn)
        ids = [
            _insert_notification(test_conn, user_id, title=f"N{i}", notif_type=f"t{i}")
            for i in range(3)
        ]

        resp = auth_client.post("/api/notifications/read-all")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

        for notif_id in ids:
            row = test_conn.execute(
                "SELECT read FROM notifications WHERE id=?", (notif_id,)
            ).fetchone()
            assert row["read"] == 1, f"Notification {notif_id} was not marked read"

    def test_unread_count_is_zero_after_mark_all_read(self, auth_client, test_conn):
        user_id = _get_user_id(test_conn)
        for i in range(3):
            _insert_notification(test_conn, user_id, notif_type=f"t{i}")

        auth_client.post("/api/notifications/read-all")

        resp = auth_client.get("/api/notifications/count")
        assert resp.get_json()["unread"] == 0


class TestDismiss:
    def test_dismiss_removes_from_list(self, auth_client, test_conn):
        user_id = _get_user_id(test_conn)
        notif_id = _insert_notification(test_conn, user_id, title="Dismiss me")

        resp = auth_client.post(f"/api/notifications/{notif_id}/dismiss")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

        resp = auth_client.get("/api/notifications")
        data = resp.get_json()
        assert data["notifications"] == []

    def test_dismissed_not_in_list(self, auth_client, test_conn):
        user_id = _get_user_id(test_conn)
        # One dismissed, one active
        _insert_notification(test_conn, user_id, title="Dismissed", dismissed=1, notif_type="t1")
        active_id = _insert_notification(test_conn, user_id, title="Active", notif_type="t2")

        resp = auth_client.get("/api/notifications")
        data = resp.get_json()

        assert len(data["notifications"]) == 1
        assert data["notifications"][0]["id"] == active_id


class TestUnreadCountDecrements:
    def test_count_decrements_after_read(self, auth_client, test_conn):
        user_id = _get_user_id(test_conn)
        id1 = _insert_notification(test_conn, user_id, notif_type="t1")
        _insert_notification(test_conn, user_id, notif_type="t2")

        # Two unread
        resp = auth_client.get("/api/notifications/count")
        assert resp.get_json()["unread"] == 2

        auth_client.post(f"/api/notifications/{id1}/read")

        resp = auth_client.get("/api/notifications/count")
        assert resp.get_json()["unread"] == 1


class TestAuthRequired:
    def test_get_notifications_requires_auth(self, client):
        resp = client.get("/api/notifications")
        assert resp.status_code == 401

    def test_get_count_requires_auth(self, client):
        resp = client.get("/api/notifications/count")
        assert resp.status_code == 401

    def test_mark_read_requires_auth(self, client):
        resp = client.post("/api/notifications/1/read")
        assert resp.status_code == 401

    def test_mark_all_read_requires_auth(self, client):
        resp = client.post("/api/notifications/read-all")
        assert resp.status_code == 401

    def test_dismiss_requires_auth(self, client):
        resp = client.post("/api/notifications/1/dismiss")
        assert resp.status_code == 401


# ── Generate Endpoint Tests ───────────────────────────────────────────────────

class TestGenerateRequiresAuth:
    def test_no_auth_returns_401(self, client):
        resp = client.post("/api/notifications/generate")
        assert resp.status_code == 401

    def test_wrong_secret_returns_401(self, client):
        resp = client.post(
            "/api/notifications/generate",
            headers={"X-Cron-Secret": "wrong-secret"},
        )
        assert resp.status_code == 401


class TestGenerateWithCronSecret:
    def test_valid_cron_secret_returns_ok(self, client, monkeypatch):
        monkeypatch.setenv("LIFEHACK_CRON_SECRET", "supersecret")
        resp = client.post(
            "/api/notifications/generate",
            headers={"X-Cron-Secret": "supersecret"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "generated" in data


class TestGenerateWithAdmin:
    def test_admin_auth_client_can_trigger_generate(self, auth_client):
        # auth_client is logged in as the admin bootstrap user (is_admin=1)
        resp = auth_client.post("/api/notifications/generate")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True


class TestGenerateCreatesOverdueHabitNotification:
    def test_overdue_habit_creates_notification(self, auth_client, test_conn, monkeypatch):
        user_id = _get_user_id(test_conn)

        # Insert a habit scheduled at 08:00, no completion today
        test_conn.execute(
            "INSERT INTO habits (user_id, name, active, scheduled_time) VALUES (?, ?, 1, '08:00')",
            (user_id, "Morning Run"),
        )
        test_conn.commit()

        # Freeze _user_now to return 11:00 today so the habit is overdue
        fake_now = datetime.now().replace(hour=11, minute=0, second=0, microsecond=0)
        monkeypatch.setattr(
            "web.routes.notifications._generate_for_user",
            _make_overdue_generator(fake_now),
        )

        resp = auth_client.post("/api/notifications/generate")
        assert resp.status_code == 200

    def test_overdue_habit_notification_appears_in_list(self, auth_client, test_conn, monkeypatch):
        user_id = _get_user_id(test_conn)

        # Insert a habit with a past scheduled_time
        cur = test_conn.execute(
            "INSERT INTO habits (user_id, name, active, scheduled_time) VALUES (?, ?, 1, '08:00')",
            (user_id, "Morning Run"),
        )
        habit_id = cur.lastrowid
        test_conn.commit()

        # Patch _user_now at the chat_context level to return 11:00
        fake_now = datetime.now().replace(hour=11, minute=0, second=0, microsecond=0)
        monkeypatch.setattr(
            "src.domain.services.chat_context._user_now",
            lambda conn, uid: fake_now,
        )

        auth_client.post("/api/notifications/generate")

        resp = auth_client.get("/api/notifications")
        data = resp.get_json()

        notif_types = [n["type"] for n in data["notifications"]]
        assert f"habit_overdue_{habit_id}" in notif_types


class TestGenerateDedup:
    def test_calling_generate_twice_does_not_duplicate(self, auth_client, test_conn, monkeypatch):
        user_id = _get_user_id(test_conn)

        test_conn.execute(
            "INSERT INTO habits (user_id, name, active, scheduled_time) VALUES (?, ?, 1, '08:00')",
            (user_id, "Morning Run"),
        )
        test_conn.commit()

        fake_now = datetime.now().replace(hour=11, minute=0, second=0, microsecond=0)
        monkeypatch.setattr(
            "src.domain.services.chat_context._user_now",
            lambda conn, uid: fake_now,
        )

        auth_client.post("/api/notifications/generate")
        auth_client.post("/api/notifications/generate")

        rows = test_conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND type LIKE 'habit_overdue_%'",
            (user_id,),
        ).fetchone()
        assert rows[0] == 1, "generate should not insert duplicate notifications on the same day"


class TestGenerateNoNotificationForCompletedHabit:
    def test_completed_habit_does_not_trigger_overdue(self, auth_client, test_conn, monkeypatch):
        user_id = _get_user_id(test_conn)
        today_str = datetime.now().date().isoformat()

        cur = test_conn.execute(
            "INSERT INTO habits (user_id, name, active, scheduled_time) VALUES (?, ?, 1, '08:00')",
            (user_id, "Morning Run"),
        )
        habit_id = cur.lastrowid
        test_conn.commit()

        # Mark as completed today
        test_conn.execute(
            "INSERT INTO habit_completions (user_id, habit_id, completed_at) VALUES (?, ?, ?)",
            (user_id, habit_id, f"{today_str}T09:00:00"),
        )
        test_conn.commit()

        fake_now = datetime.now().replace(hour=11, minute=0, second=0, microsecond=0)
        monkeypatch.setattr(
            "src.domain.services.chat_context._user_now",
            lambda conn, uid: fake_now,
        )

        auth_client.post("/api/notifications/generate")

        rows = test_conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND type=?",
            (user_id, f"habit_overdue_{habit_id}"),
        ).fetchone()
        assert rows[0] == 0, "completed habit should not generate an overdue notification"


# ── Model / Serialization Tests ───────────────────────────────────────────────

class TestNotificationSerialization:
    def test_response_has_all_expected_fields(self, auth_client, test_conn):
        user_id = _get_user_id(test_conn)
        _insert_notification(
            test_conn, user_id,
            title="Serialization Test",
            body="Check fields",
            notif_type="test_serial",
            icon="bell",
            link="/dashboard",
        )

        resp = auth_client.get("/api/notifications")
        assert resp.status_code == 200
        notifications = resp.get_json()["notifications"]
        assert len(notifications) == 1
        n = notifications[0]

        required_fields = {"id", "type", "title", "body", "icon", "link", "read", "created_at"}
        missing = required_fields - set(n.keys())
        assert not missing, f"Response is missing fields: {missing}"

    def test_read_field_is_boolean(self, auth_client, test_conn):
        user_id = _get_user_id(test_conn)
        _insert_notification(test_conn, user_id)

        resp = auth_client.get("/api/notifications")
        n = resp.get_json()["notifications"][0]
        assert isinstance(n["read"], bool)

    def test_unread_notification_has_read_false(self, auth_client, test_conn):
        user_id = _get_user_id(test_conn)
        _insert_notification(test_conn, user_id, read=0)

        resp = auth_client.get("/api/notifications")
        n = resp.get_json()["notifications"][0]
        assert n["read"] is False

    def test_field_values_match_inserted_data(self, auth_client, test_conn):
        user_id = _get_user_id(test_conn)
        _insert_notification(
            test_conn, user_id,
            title="My Title",
            body="My Body",
            notif_type="my_type",
            icon="star",
            link="/habits",
        )

        resp = auth_client.get("/api/notifications")
        n = resp.get_json()["notifications"][0]
        assert n["title"] == "My Title"
        assert n["body"] == "My Body"
        assert n["type"] == "my_type"
        assert n["icon"] == "star"
        assert n["link"] == "/habits"


# ── Internal helper used by monkeypatching tests ─────────────────────────────

def _make_overdue_generator(fake_now):
    """Return a replacement for _generate_for_user that uses a controlled time."""
    from web.routes.notifications import _generate_for_user as _orig

    def _patched(conn, user_id):
        import src.domain.services.chat_context as _ctx
        original = _ctx._user_now
        _ctx._user_now = lambda c, u: fake_now
        try:
            return _orig(conn, user_id)
        finally:
            _ctx._user_now = original

    return _patched
