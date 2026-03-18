"""Tests for habit API endpoints — /api/habits/*."""
import json


class TestGetHabits:
    def test_returns_list_when_authenticated(self, auth_client):
        resp = auth_client.get("/api/habits")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_returns_401_when_unauthenticated(self, client):
        resp = client.get("/api/habits")
        assert resp.status_code == 401

    def test_returns_empty_list_when_no_habits(self, auth_client):
        resp = auth_client.get("/api/habits")
        data = resp.get_json()
        assert data == []

    def test_created_habit_appears_in_list(self, auth_client):
        auth_client.post(
            "/api/habits",
            json={"name": "Meditate", "category": "health", "difficulty": 1},
        )
        resp = auth_client.get("/api/habits")
        names = [h["name"] for h in resp.get_json()]
        assert "Meditate" in names

    def test_habit_list_includes_streak_and_completed_fields(self, auth_client):
        auth_client.post("/api/habits", json={"name": "Run"})
        habits = auth_client.get("/api/habits").get_json()
        habit = habits[0]
        assert "streak" in habit
        assert "completed" in habit
        assert "id" in habit


class TestCreateHabit:
    def test_create_habit_returns_id(self, auth_client):
        resp = auth_client.post(
            "/api/habits",
            json={"name": "Journal", "category": "mind", "difficulty": 2},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert isinstance(data["id"], int)

    def test_create_habit_unauthorized(self, client):
        resp = client.post("/api/habits", json={"name": "Journal"})
        assert resp.status_code == 401

    def test_create_multiple_habits(self, auth_client):
        for name in ("A", "B", "C"):
            auth_client.post("/api/habits", json={"name": name})
        habits = auth_client.get("/api/habits").get_json()
        assert len(habits) == 3


class TestCompleteHabit:
    def _create_habit(self, auth_client, name="Run"):
        r = auth_client.post("/api/habits", json={"name": name, "difficulty": 1})
        return r.get_json()["id"]

    def test_complete_habit_returns_points(self, auth_client):
        habit_id = self._create_habit(auth_client)
        resp = auth_client.post(f"/api/habits/{habit_id}/complete")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["points"] > 0

    def test_complete_habit_marks_as_completed(self, auth_client):
        habit_id = self._create_habit(auth_client)
        auth_client.post(f"/api/habits/{habit_id}/complete")
        habits = auth_client.get("/api/habits").get_json()
        habit = next(h for h in habits if h["id"] == habit_id)
        assert habit["completed"] is True

    def test_complete_nonexistent_habit_returns_404(self, auth_client):
        resp = auth_client.post("/api/habits/99999/complete")
        assert resp.status_code == 404

    def test_complete_habit_awards_xp(self, auth_client):
        habit_id = self._create_habit(auth_client)
        stats_before = auth_client.get("/api/stats").get_json()
        auth_client.post(f"/api/habits/{habit_id}/complete")
        stats_after = auth_client.get("/api/stats").get_json()
        assert stats_after["total_xp"] > stats_before["total_xp"]

    def test_complete_unauthorized(self, client):
        resp = client.post("/api/habits/1/complete")
        assert resp.status_code == 401


class TestUncompleteHabit:
    def _create_and_complete(self, auth_client, name="Walk"):
        r = auth_client.post("/api/habits", json={"name": name})
        habit_id = r.get_json()["id"]
        auth_client.post(f"/api/habits/{habit_id}/complete")
        return habit_id

    def test_uncomplete_removes_completion(self, auth_client):
        habit_id = self._create_and_complete(auth_client)
        resp = auth_client.post(f"/api/habits/{habit_id}/uncomplete")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["undone"] is True

    def test_uncomplete_habit_no_longer_marked_completed(self, auth_client):
        habit_id = self._create_and_complete(auth_client)
        auth_client.post(f"/api/habits/{habit_id}/uncomplete")
        habits = auth_client.get("/api/habits").get_json()
        habit = next(h for h in habits if h["id"] == habit_id)
        assert habit["completed"] is False

    def test_uncomplete_when_not_completed_returns_false(self, auth_client):
        r = auth_client.post("/api/habits", json={"name": "NewHabit"})
        habit_id = r.get_json()["id"]
        resp = auth_client.post(f"/api/habits/{habit_id}/uncomplete")
        data = resp.get_json()
        assert data["success"] is False

    def test_uncomplete_nonexistent_returns_404(self, auth_client):
        resp = auth_client.post("/api/habits/99999/uncomplete")
        assert resp.status_code == 404

    def test_uncomplete_unauthorized(self, client):
        resp = client.post("/api/habits/1/uncomplete")
        assert resp.status_code == 401


class TestUpdateHabit:
    def test_update_habit_name(self, auth_client):
        r = auth_client.post("/api/habits", json={"name": "OldName"})
        habit_id = r.get_json()["id"]
        resp = auth_client.put(f"/api/habits/{habit_id}", json={"name": "NewName"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_update_reflects_in_list(self, auth_client):
        r = auth_client.post("/api/habits", json={"name": "OldName"})
        habit_id = r.get_json()["id"]
        auth_client.put(f"/api/habits/{habit_id}", json={"name": "UpdatedName"})
        habits = auth_client.get("/api/habits").get_json()
        names = [h["name"] for h in habits]
        assert "UpdatedName" in names
        assert "OldName" not in names

    def test_update_nonexistent_returns_404(self, auth_client):
        resp = auth_client.put("/api/habits/99999", json={"name": "X"})
        assert resp.status_code == 404

    def test_update_unauthorized(self, client):
        resp = client.put("/api/habits/1", json={"name": "X"})
        assert resp.status_code == 401


class TestDeleteHabit:
    def test_delete_habit_soft_deletes(self, auth_client):
        r = auth_client.post("/api/habits", json={"name": "ToDelete"})
        habit_id = r.get_json()["id"]
        resp = auth_client.delete(f"/api/habits/{habit_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["deactivated"] is True

    def test_deleted_habit_not_in_active_list(self, auth_client):
        r = auth_client.post("/api/habits", json={"name": "ToDelete"})
        habit_id = r.get_json()["id"]
        auth_client.delete(f"/api/habits/{habit_id}")
        habits = auth_client.get("/api/habits").get_json()
        ids = [h["id"] for h in habits]
        assert habit_id not in ids

    def test_delete_nonexistent_returns_404(self, auth_client):
        resp = auth_client.delete("/api/habits/99999")
        assert resp.status_code == 404

    def test_delete_unauthorized(self, client):
        resp = client.delete("/api/habits/1")
        assert resp.status_code == 401
