"""Integration routes (Vikunja, Firefly).

These endpoints preserve the original API contracts consumed by the existing
frontend while delegating all state management to the plugin registry.

All integration configs are per-user via user_integrations table.
"""
import logging

from flask import Blueprint, jsonify, request

from .decorators import login_required, current_user_id
from src.infrastructure.plugins import plugin_registry

logger = logging.getLogger(__name__)

integrations_bp = Blueprint("integrations", __name__, url_prefix="/api/integrations")


# ---------------------------------------------------------------------------
# Internal helpers — bridge to the plugin registry
# ---------------------------------------------------------------------------

def _plugin_enabled(plugin_id: str, uid: int) -> bool:
    stored = plugin_registry.get_config(plugin_id, uid)
    return bool(stored.get("enabled", False))


def _plugin_config(plugin_id: str, uid: int) -> dict:
    stored = plugin_registry.get_config(plugin_id, uid)
    return stored.get("config", {})


def _plugin_connected(plugin_id: str, uid: int) -> bool:
    if not _plugin_enabled(plugin_id, uid):
        return False
    try:
        plugin = plugin_registry.get(plugin_id)
        return plugin.test_connection(_plugin_config(plugin_id, uid))
    except Exception:
        logger.debug("Connection test failed for '%s'", plugin_id, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@integrations_bp.route("", methods=["GET"])
@login_required
def get_integrations():
    uid = current_user_id()

    vikunja_cfg       = _plugin_config("vikunja", uid)
    vikunja_enabled   = _plugin_enabled("vikunja", uid)
    vikunja_connected = _plugin_connected("vikunja", uid) if vikunja_enabled else False

    firefly_enabled   = _plugin_enabled("firefly", uid)
    firefly_connected = _plugin_connected("firefly", uid) if firefly_enabled else False

    return jsonify({
        "vikunja": {
            "enabled":     vikunja_enabled,
            "connected":   vikunja_connected,
            "api_url":     vikunja_cfg.get("api_url", ""),
            "description": "Task management via Vikunja",
        },
        "google_calendar": {
            "enabled":     False,
            "connected":   False,
            "account":     "",
            "description": "Google Calendar integration removed",
        },
        "firefly": {
            "enabled":     firefly_enabled,
            "connected":   firefly_connected,
            "description": "Personal finance via Firefly III",
        },
    })


@integrations_bp.route("/vikunja", methods=["POST"])
@login_required
def configure_vikunja():
    uid = current_user_id()
    data = request.get_json(silent=True) or {}

    if data.get("enabled") is False:
        plugin_registry.disable("vikunja", uid)
        return jsonify({"success": True, "enabled": False})

    api_url   = data.get("api_url", "")
    api_token = data.get("api_token", "")

    if not api_token:
        return jsonify({"error": "API token required"}), 400

    config = {"api_url": api_url, "api_token": api_token}
    ok = plugin_registry.enable("vikunja", config, uid)
    if ok:
        return jsonify({"success": True, "enabled": True, "connected": True})
    return jsonify({"error": "Connection test failed"}), 400


@integrations_bp.route("/vikunja/test", methods=["POST"])
@login_required
def test_vikunja():
    data = request.get_json(silent=True) or {}
    config = {
        "api_url":   data.get("api_url", ""),
        "api_token": data.get("api_token", ""),
    }
    plugin    = plugin_registry.get("vikunja")
    connected = plugin.test_connection(config)
    return jsonify({"connected": connected})


@integrations_bp.route("/google_calendar", methods=["POST"])
@login_required
def configure_google_calendar():
    return jsonify({"error": "Google Calendar integration is no longer supported"}), 410


@integrations_bp.route("/firefly", methods=["POST"])
@login_required
def configure_firefly():
    uid = current_user_id()
    data = request.get_json(silent=True) or {}

    if data.get("enabled") is False:
        plugin_registry.disable("firefly", uid)
        return jsonify({"success": True, "enabled": False})

    api_url    = data.get("api_url", "")
    api_token  = data.get("api_token", "")
    account_id = data.get("default_account_id", data.get("account_id", ""))
    if not api_token:
        return jsonify({"error": "API token required"}), 400
    config = {"api_url": api_url, "api_token": api_token, "default_account_id": account_id}
    ok = plugin_registry.enable("firefly", config, uid)
    if ok:
        return jsonify({"success": True, "enabled": True, "connected": True})
    return jsonify({"error": "Connection test failed"}), 400
