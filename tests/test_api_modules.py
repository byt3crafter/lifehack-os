"""Tests for module management endpoints — /api/modules."""


class TestListModules:
    def test_returns_list_when_authenticated(self, auth_client):
        resp = auth_client.get("/api/modules")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_returns_401_when_unauthenticated(self, client):
        resp = client.get("/api/modules")
        assert resp.status_code == 401

    def test_returns_8_modules(self, auth_client):
        resp = auth_client.get("/api/modules")
        data = resp.get_json()
        assert len(data) == 8

    def test_each_module_has_required_fields(self, auth_client):
        modules = auth_client.get("/api/modules").get_json()
        for mod in modules:
            assert "id" in mod
            assert "name" in mod
            assert "enabled" in mod
            assert "default" in mod

    def test_habits_module_enabled_by_default(self, auth_client):
        modules = auth_client.get("/api/modules").get_json()
        habits_mod = next(m for m in modules if m["id"] == "habits")
        assert habits_mod["enabled"] is True

    def test_food_module_enabled_by_default(self, auth_client):
        modules = auth_client.get("/api/modules").get_json()
        food_mod = next(m for m in modules if m["id"] == "food")
        assert food_mod["enabled"] is True

    def test_fasting_module_disabled_by_default(self, auth_client):
        modules = auth_client.get("/api/modules").get_json()
        mod = next(m for m in modules if m["id"] == "fasting")
        assert mod["enabled"] is False

    def test_finance_module_disabled_by_default(self, auth_client):
        modules = auth_client.get("/api/modules").get_json()
        mod = next(m for m in modules if m["id"] == "finance")
        assert mod["enabled"] is False



class TestUpdateModules:
    def test_toggle_module_on(self, auth_client):
        resp = auth_client.post("/api/modules", json={"food": True})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["modules"]["food"] is True

    def test_toggle_module_off(self, auth_client):
        resp = auth_client.post("/api/modules", json={"habits": False})
        assert resp.status_code == 200
        assert resp.get_json()["modules"]["habits"] is False

    def test_toggle_persists_across_requests(self, auth_client):
        auth_client.post("/api/modules", json={"fasting": True})
        modules = auth_client.get("/api/modules").get_json()
        mod = next(m for m in modules if m["id"] == "fasting")
        assert mod["enabled"] is True

    def test_unknown_module_id_ignored(self, auth_client):
        resp = auth_client.post("/api/modules", json={"nonexistent_module": True})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "nonexistent_module" not in data["modules"]

    def test_toggle_multiple_modules_at_once(self, auth_client):
        resp = auth_client.post(
            "/api/modules", json={"food": True, "fasting": True, "deepwork": True}
        )
        assert resp.status_code == 200
        modules_state = resp.get_json()["modules"]
        assert modules_state["food"] is True
        assert modules_state["fasting"] is True
        assert modules_state["deepwork"] is True

    def test_update_unauthorized(self, client):
        resp = client.post("/api/modules", json={"food": True})
        assert resp.status_code == 401
