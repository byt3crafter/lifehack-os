"""Integration routes (Vikunja, Firefly).

These endpoints preserve the original API contracts consumed by the existing
frontend while delegating all state management to the plugin registry.

Original contract:
    GET  /api/integrations             -> dict of integration statuses
    POST /api/integrations/vikunja     -> enable/disable vikunja
    POST /api/integrations/vikunja/test
    POST /api/integrations/google_calendar  -> returns 410 (removed)
    POST /api/integrations/firefly
"""
import logging

from flask import Blueprint, jsonify, request

from .decorators import login_required
from src.infrastructure.plugins import plugin_registry

logger = logging.getLogger(__name__)

integrations_bp = Blueprint("integrations", __name__, url_prefix="/api/integrations")


# ---------------------------------------------------------------------------
# Internal helpers — bridge to the plugin registry
# ---------------------------------------------------------------------------

def _plugin_enabled(plugin_id: str) -> bool:
    stored = plugin_registry.get_config(plugin_id)
    return bool(stored.get("enabled", False))


def _plugin_config(plugin_id: str) -> dict:
    stored = plugin_registry.get_config(plugin_id)
    return stored.get("config", {})


def _plugin_connected(plugin_id: str) -> bool:
    if not _plugin_enabled(plugin_id):
        return False
    try:
        plugin = plugin_registry.get(plugin_id)
        return plugin.test_connection(_plugin_config(plugin_id))
    except Exception:
        logger.debug("Connection test failed for '%s'", plugin_id, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@integrations_bp.route("", methods=["GET"])
@login_required
def get_integrations():
    """Return status of all known integrations.

    Preserved response shape::

        {
            "vikunja":         {"enabled": bool, "connected": bool, "api_url": str, "description": str},
            "google_calendar": {"enabled": bool, "connected": bool, "account":  str, "description": str},
            "firefly":         {"enabled": bool, "connected": bool,                   "description": str},
        }
    """
    # Vikunja
    vikunja_cfg     = _plugin_config("vikunja")
    vikunja_enabled = _plugin_enabled("vikunja")
    vikunja_connected = _plugin_connected("vikunja") if vikunja_enabled else False

    # Firefly
    firefly_enabled   = _plugin_enabled("firefly")
    firefly_connected = _plugin_connected("firefly") if firefly_enabled else False

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


# ---------------------------------------------------------------------------
# Vikunja
# ---------------------------------------------------------------------------

@integrations_bp.route("/vikunja", methods=["POST"])
@login_required
def configure_vikunja():
    """Enable or disable the Vikunja integration.

    Request body variants::

        {"enabled": false}                         # disable
        {"api_url": "...", "username": "...", "password": "..."}  # enable
    """
    data = request.get_json(silent=True) or {}

    if data.get("enabled") is False:
        plugin_registry.disable("vikunja")
        return jsonify({"success": True, "enabled": False})

    api_url  = data.get("api_url", "")
    username = data.get("username", "")
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    config = {"api_url": api_url, "username": username, "password": password}
    ok = plugin_registry.enable("vikunja", config)
    if ok:
        return jsonify({"success": True, "enabled": True, "connected": True})
    return jsonify({"error": "Connection test failed"}), 400


@integrations_bp.route("/vikunja/test", methods=["POST"])
@login_required
def test_vikunja():
    """Test Vikunja credentials without saving them."""
    data = request.get_json(silent=True) or {}

    config = {
        "api_url":  data.get("api_url", ""),
        "username": data.get("username", ""),
        "password": data.get("password", ""),
    }
    plugin    = plugin_registry.get("vikunja")
    connected = plugin.test_connection(config)
    return jsonify({"connected": connected})


# ---------------------------------------------------------------------------
# Google Calendar
# ---------------------------------------------------------------------------

@integrations_bp.route("/google_calendar", methods=["POST"])
@login_required
def configure_google_calendar():
    """Google Calendar integration has been removed."""
    return jsonify({"error": "Google Calendar integration is no longer supported"}), 410


# ---------------------------------------------------------------------------
# Firefly III
# ---------------------------------------------------------------------------

@integrations_bp.route("/firefly", methods=["POST"])
@login_required
def configure_firefly():
    """Enable or disable the Firefly III integration."""
    data = request.get_json(silent=True) or {}

    if data.get("enabled") is False:
        plugin_registry.disable("firefly")
        return jsonify({"success": True, "enabled": False})

    helper_path = data.get("helper_path", "")
    account_id  = data.get("account_id", "")
    config = {"helper_path": helper_path, "account_id": account_id}
    ok = plugin_registry.enable("firefly", config)
    if ok:
        return jsonify({"success": True, "enabled": True, "connected": True})
    return jsonify({"error": "Connection test failed"}), 400


# ---------------------------------------------------------------------------
# Calendar and Finance routes are in misc.py (for /api/* paths)
# ---------------------------------------------------------------------------
