"""Tests for OpenClaw API endpoints — /api/openclaw/*."""


VALID_KEY = "test-key"
INVALID_KEY = "wrong-key"
API_HEADERS = {"X-API-Key": VALID_KEY, "Content-Type": "application/json"}
BAD_HEADERS = {"X-API-Key": INVALID_KEY, "Content-Type": "application/json"}


class TestOpenClawSchema:
    """GET /api/openclaw/schema — no auth required."""

    def test_schema_returns_200_without_auth(self, auth_client):
        assert auth_client.get("/api/openclaw/schema").status_code == 200

    def test_schema_returns_valid_json(self, auth_client):
        assert auth_client.get("/api/openclaw/schema").get_json() is not None

    def test_schema_has_name_field(self, auth_client):
        data = auth_client.get("/api/openclaw/schema").get_json()
        assert "name" in data

    def test_schema_has_endpoints_list(self, auth_client):
        data = auth_client.get("/api/openclaw/schema").get_json()
        assert "endpoints" in data
        assert len(data["endpoints"]) > 0

    def test_schema_has_auth_info(self, auth_client):
        data = auth_client.get("/api/openclaw/schema").get_json()
        assert "auth" in data

    def test_schema_endpoints_have_path_and_method(self, auth_client):
        for ep in auth_client.get("/api/openclaw/schema").get_json()["endpoints"]:
            assert "path" in ep
            assert "method" in ep


class TestOpenClawStatus:
    """GET /api/openclaw/status — requires API key."""

    def test_status_valid_key_returns_200(self, auth_client):
        assert auth_client.get("/api/openclaw/status", headers=API_HEADERS).status_code == 200

    def test_status_response_has_stats(self, auth_client):
        data = auth_client.get("/api/openclaw/status", headers=API_HEADERS).get_json()
        assert "stats" in data
        assert "total_xp" in data["stats"]

    def test_status_response_has_today(self, auth_client):
        data = auth_client.get("/api/openclaw/status", headers=API_HEADERS).get_json()
        assert "today" in data
        assert "habits_total" in data["today"]

    def test_status_response_has_patterns(self, auth_client):
        data = auth_client.get("/api/openclaw/status", headers=API_HEADERS).get_json()
        assert "patterns" in data

    def test_status_response_has_pending_actions(self, auth_client):
        data = auth_client.get("/api/openclaw/status", headers=API_HEADERS).get_json()
        assert isinstance(data["pending_actions"], list)


class TestOpenClawCompleteHabit:
    """POST /api/openclaw/habit/complete — requires API key."""

    def test_complete_habit_by_name(self, auth_client):
        auth_client.post("/api/habits", json={"name": "Yoga Practice"})
        resp = auth_client.post("/api/openclaw/habit/complete",
                                json={"habit_name": "yoga"}, headers=API_HEADERS)
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_complete_habit_returns_points(self, auth_client):
        auth_client.post("/api/habits", json={"name": "Meditation"})
        resp = auth_client.post("/api/openclaw/habit/complete",
                                json={"habit_name": "meditation"}, headers=API_HEADERS)
        assert resp.get_json()["points"] > 0

    def test_complete_nonexistent_habit_returns_404(self, auth_client):
        resp = auth_client.post("/api/openclaw/habit/complete",
                                json={"habit_name": "nonexistent"}, headers=API_HEADERS)
        assert resp.status_code == 404

    def test_complete_habit_awards_xp(self, auth_client):
        auth_client.post("/api/habits", json={"name": "Cold Shower"})
        before = auth_client.get("/api/openclaw/status", headers=API_HEADERS).get_json()["stats"]["total_xp"]
        auth_client.post("/api/openclaw/habit/complete",
                         json={"habit_name": "cold shower"}, headers=API_HEADERS)
        after = auth_client.get("/api/openclaw/status", headers=API_HEADERS).get_json()["stats"]["total_xp"]
        assert after > before


class TestOpenClawPushInsight:
    """POST /api/openclaw/insight — requires API key."""

    def test_push_insight_returns_success(self, auth_client):
        resp = auth_client.post("/api/openclaw/insight",
                                json={"title": "Great!", "content": "Keep going.", "type": "celebration"},
                                headers=API_HEADERS)
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_push_insight_appears_in_insights(self, auth_client):
        auth_client.post("/api/openclaw/insight",
                         json={"title": "Unique Title", "content": "Body", "type": "advice"},
                         headers=API_HEADERS)
        insights = auth_client.get("/api/insights").get_json()
        assert any(i["title"] == "Unique Title" for i in insights)


class TestOpenClawAuth:
    """API key validation across endpoints."""

    def test_status_no_key_returns_401(self, auth_client):
        assert auth_client.get("/api/openclaw/status").status_code == 401

    def test_status_bad_key_returns_401(self, auth_client):
        assert auth_client.get("/api/openclaw/status", headers=BAD_HEADERS).status_code == 401

    def test_complete_bad_key_returns_401(self, auth_client):
        resp = auth_client.post("/api/openclaw/habit/complete",
                                json={"habit_name": "x"}, headers=BAD_HEADERS)
        assert resp.status_code == 401

    def test_insight_bad_key_returns_401(self, auth_client):
        resp = auth_client.post("/api/openclaw/insight",
                                json={"title": "X", "content": "Y"}, headers=BAD_HEADERS)
        assert resp.status_code == 401

    def test_query_param_api_key_accepted(self, auth_client):
        assert auth_client.get(f"/api/openclaw/status?api_key={VALID_KEY}").status_code == 200

    def test_query_param_wrong_key_rejected(self, auth_client):
        assert auth_client.get(f"/api/openclaw/status?api_key={INVALID_KEY}").status_code == 401
