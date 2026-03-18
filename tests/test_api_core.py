"""Tests for core API endpoints: stats, daily, checkin, food, walks, api discovery, health."""


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_ok_text(self, client):
        resp = client.get("/health")
        assert b"ok" in resp.data.lower()


# ---------------------------------------------------------------------------
# API discovery endpoint  GET /api
# ---------------------------------------------------------------------------

class TestApiDiscovery:
    def test_api_index_returns_200_when_authenticated(self, auth_client):
        resp = auth_client.get("/api")
        assert resp.status_code == 200

    def test_api_index_returns_valid_json(self, auth_client):
        resp = auth_client.get("/api")
        data = resp.get_json()
        assert data is not None

    def test_api_index_has_version_field(self, auth_client):
        resp = auth_client.get("/api")
        data = resp.get_json()
        assert "version" in data

    def test_api_index_has_groups(self, auth_client):
        resp = auth_client.get("/api")
        data = resp.get_json()
        assert "groups" in data
        assert isinstance(data["groups"], dict)

    def test_api_index_unauthorized_returns_401_or_redirect(self, client):
        resp = client.get("/api")
        assert resp.status_code in (401, 302)  # 401 for JSON, 302 redirect for browser


# ---------------------------------------------------------------------------
# Stats   GET /api/stats
# ---------------------------------------------------------------------------

class TestGetStats:
    def test_stats_returns_200(self, auth_client):
        resp = auth_client.get("/api/stats")
        assert resp.status_code == 200

    def test_stats_contains_required_fields(self, auth_client):
        data = auth_client.get("/api/stats").get_json()
        assert "total_xp" in data
        assert "level" in data
        assert "level_name" in data
        assert "xp_for_next" in data
        assert "sobriety_days" in data

    def test_stats_initial_xp_is_zero(self, auth_client):
        data = auth_client.get("/api/stats").get_json()
        assert data["total_xp"] == 0

    def test_stats_initial_level_is_one(self, auth_client):
        data = auth_client.get("/api/stats").get_json()
        assert data["level"] == 1

    def test_stats_xp_increases_after_habit_completion(self, auth_client):
        auth_client.post("/api/habits", json={"name": "Run"})
        habits = auth_client.get("/api/habits").get_json()
        auth_client.post(f"/api/habits/{habits[0]['id']}/complete")
        data = auth_client.get("/api/stats").get_json()
        assert data["total_xp"] > 0

    def test_stats_unauthorized_returns_401(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Daily summary   GET /api/daily
# ---------------------------------------------------------------------------

class TestGetDaily:
    def test_daily_returns_200(self, auth_client):
        resp = auth_client.get("/api/daily")
        assert resp.status_code == 200

    def test_daily_contains_today_and_yesterday(self, auth_client):
        data = auth_client.get("/api/daily").get_json()
        assert "today" in data
        assert "yesterday" in data

    def test_daily_today_has_required_fields(self, auth_client):
        today = auth_client.get("/api/daily").get_json()["today"]
        assert "habits_completed" in today
        assert "habits_total" in today
        assert "score" in today
        assert "points" in today

    def test_daily_score_between_0_and_100(self, auth_client):
        today = auth_client.get("/api/daily").get_json()["today"]
        assert 0 <= today["score"] <= 100

    def test_daily_has_deltas_and_tips(self, auth_client):
        data = auth_client.get("/api/daily").get_json()
        assert "deltas" in data
        assert "tips" in data

    def test_daily_unauthorized_returns_401(self, client):
        resp = client.get("/api/daily")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Check-in   GET/POST /api/checkin
# ---------------------------------------------------------------------------

class TestCheckin:
    def test_get_checkin_returns_null_when_none(self, auth_client):
        resp = auth_client.get("/api/checkin")
        assert resp.status_code == 200
        # Flask's jsonify(None) returns a JSON null
        assert resp.get_json() is None

    def test_post_checkin_returns_success_and_points(self, auth_client):
        resp = auth_client.post(
            "/api/checkin",
            json={
                "completed_today": "Went to the gym",
                "avoided_alcohol": True,
                "worked_on_future": True,
                "mood": 4,
                "energy": 4,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["points"] > 0

    def test_checkin_awards_sobriety_bonus(self, auth_client):
        # avoided_alcohol=True should earn more than base alone
        resp_sober = auth_client.post(
            "/api/checkin",
            json={"avoided_alcohol": True, "worked_on_future": False},
        )
        points_sober = resp_sober.get_json()["points"]
        # base=15, sobriety_bonus=25 → 40
        assert points_sober == 40

    def test_checkin_future_work_bonus(self, auth_client):
        resp = auth_client.post(
            "/api/checkin",
            json={"avoided_alcohol": False, "worked_on_future": True},
        )
        points = resp.get_json()["points"]
        # base=15, future_bonus=10 → 25
        assert points == 25

    def test_get_checkin_returns_data_after_post(self, auth_client):
        auth_client.post(
            "/api/checkin",
            json={"mood": 5, "energy": 4, "avoided_alcohol": True},
        )
        resp = auth_client.get("/api/checkin")
        data = resp.get_json()
        assert data is not None
        assert data["mood"] == 5

    def test_checkin_is_idempotent_same_day(self, auth_client):
        # Second POST on same day should not award XP again
        auth_client.post("/api/checkin", json={"mood": 3})
        stats_after_first = auth_client.get("/api/stats").get_json()["total_xp"]
        auth_client.post("/api/checkin", json={"mood": 4})
        stats_after_second = auth_client.get("/api/stats").get_json()["total_xp"]
        assert stats_after_first == stats_after_second

    def test_checkin_unauthorized_returns_401(self, client):
        resp = client.post("/api/checkin", json={"mood": 3})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Food   GET/POST /api/food
# ---------------------------------------------------------------------------

class TestFood:
    def test_get_food_returns_200(self, auth_client):
        resp = auth_client.get("/api/food")
        assert resp.status_code == 200

    def test_get_food_has_logs_and_calories(self, auth_client):
        data = auth_client.get("/api/food").get_json()
        assert "logs" in data
        assert "today_calories" in data

    def test_get_food_empty_logs_initially(self, auth_client):
        data = auth_client.get("/api/food").get_json()
        assert data["logs"] == []

    def test_post_food_returns_success(self, auth_client):
        resp = auth_client.post(
            "/api/food",
            json={
                "meal_type": "breakfast",
                "description": "Oats and banana",
                "calories": 350,
                "protein_g": 10,
                "carbs_g": 65,
                "fat_g": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert isinstance(data["id"], int)

    def test_logged_food_appears_in_list(self, auth_client):
        auth_client.post(
            "/api/food",
            json={"meal_type": "lunch", "description": "Chicken salad", "calories": 400},
        )
        logs = auth_client.get("/api/food").get_json()["logs"]
        descriptions = [l["description"] for l in logs]
        assert "Chicken salad" in descriptions

    def test_food_unauthorized_returns_401(self, client):
        resp = client.get("/api/food")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Walks   GET/POST /api/walks
# ---------------------------------------------------------------------------

class TestWalks:
    def test_get_walks_returns_200(self, auth_client):
        resp = auth_client.get("/api/walks")
        assert resp.status_code == 200

    def test_get_walks_has_stats_and_walks_fields(self, auth_client):
        data = auth_client.get("/api/walks").get_json()
        assert "stats" in data
        assert "walks" in data

    def test_get_walks_empty_initially(self, auth_client):
        data = auth_client.get("/api/walks").get_json()
        assert data["walks"] == []

    def test_post_walk_returns_success_and_points(self, auth_client):
        resp = auth_client.post(
            "/api/walks",
            json={
                "distance_km": 3.5,
                "duration_minutes": 40,
                "mood_before": 3,
                "mood_after": 4,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["points"] > 0

    def test_logged_walk_appears_in_list(self, auth_client):
        auth_client.post(
            "/api/walks",
            json={"distance_km": 2.0, "duration_minutes": 25},
        )
        walks = auth_client.get("/api/walks").get_json()["walks"]
        assert len(walks) == 1
        assert walks[0]["distance_km"] == 2.0

    def test_walk_awards_xp(self, auth_client):
        stats_before = auth_client.get("/api/stats").get_json()["total_xp"]
        auth_client.post("/api/walks", json={"distance_km": 1.0, "duration_minutes": 20})
        stats_after = auth_client.get("/api/stats").get_json()["total_xp"]
        assert stats_after > stats_before

    def test_walks_unauthorized_returns_401(self, client):
        resp = client.get("/api/walks")
        assert resp.status_code == 401
