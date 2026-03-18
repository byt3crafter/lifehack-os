"""Plugin management API routes.

Endpoints
---------
GET  /api/plugins                — list all plugins with config fields, enabled state, status
POST /api/plugins/<id>/enable    — enable a plugin; body: {"config": {field_id: value}}
POST /api/plugins/<id>/disable   — disable a plugin
POST /api/plugins/<id>/test      — test connection without saving; body: {"config": {...}}
GET  /api/plugins/<id>/status    — get current connection status for a plugin
"""
import logging

from flask import Blueprint, jsonify, request

from .decorators import login_required
from src.infrastructure.plugins import plugin_registry

logger = logging.getLogger(__name__)

plugins_bp = Blueprint("plugins", __name__, url_prefix="/api/plugins")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plugin_response(plugin_id: str, include_status: bool = False) -> dict:
    """Serialize a single plugin to a dict safe to return to the client."""
    plugin  = plugin_registry.get(plugin_id)
    stored  = plugin_registry.get_config(plugin_id)
    enabled = bool(stored.get("enabled", False))
    safe_cfg = plugin_registry.safe_config(plugin_id)

    data = plugin.to_dict(enabled=enabled, config=safe_cfg)

    if include_status and enabled:
        raw_config = stored.get("config", {})
        try:
            data["status"] = plugin.get_status(raw_config)
        except Exception:
            logger.exception("get_status raised for plugin '%s'", plugin_id)
            data["status"] = {"connected": False, "detail": "Status check failed"}
    elif include_status:
        data["status"] = {"connected": False, "detail": "Plugin is disabled"}

    return data


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@plugins_bp.route("", methods=["GET"])
@login_required
def list_plugins():
    """List all registered plugins with their metadata and current status."""
    result = []
    for plugin in plugin_registry.get_all():
        try:
            result.append(_plugin_response(plugin.id, include_status=True))
        except Exception:
            logger.exception("Failed to build response for plugin '%s'", plugin.id)
    return jsonify(result)


@plugins_bp.route("/<plugin_id>/enable", methods=["POST"])
@login_required
def enable_plugin(plugin_id: str):
    """Enable a plugin with the provided config.

    Request body::

        {"config": {"field_id": "value", ...}}

    Returns 404 if the plugin is unknown, 400 if the connection test fails,
    200 with the updated plugin object on success.
    """
    if not plugin_registry.has(plugin_id):
        return jsonify({"error": f"Plugin '{plugin_id}' not found"}), 404

    body   = request.get_json(silent=True) or {}
    config = body.get("config", {})

    if not isinstance(config, dict):
        return jsonify({"error": "'config' must be a JSON object"}), 400

    # Validate required fields
    plugin = plugin_registry.get(plugin_id)
    missing = [
        f["label"]
        for f in plugin.get_config_fields()
        if f.get("required") and not config.get(f["id"])
    ]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    ok = plugin_registry.enable(plugin_id, config)
    if not ok:
        return jsonify({"error": "Connection test failed — check your configuration"}), 400

    return jsonify(_plugin_response(plugin_id, include_status=True))


@plugins_bp.route("/<plugin_id>/disable", methods=["POST"])
@login_required
def disable_plugin(plugin_id: str):
    """Disable a plugin (config is retained for easy re-enabling)."""
    if not plugin_registry.has(plugin_id):
        return jsonify({"error": f"Plugin '{plugin_id}' not found"}), 404

    plugin_registry.disable(plugin_id)
    return jsonify(_plugin_response(plugin_id, include_status=False))


@plugins_bp.route("/<plugin_id>/test", methods=["POST"])
@login_required
def test_plugin(plugin_id: str):
    """Test a plugin connection without persisting the config.

    Request body::

        {"config": {"field_id": "value", ...}}

    Returns::

        {"connected": bool, "detail": str}
    """
    if not plugin_registry.has(plugin_id):
        return jsonify({"error": f"Plugin '{plugin_id}' not found"}), 404

    body   = request.get_json(silent=True) or {}
    config = body.get("config", {})

    if not isinstance(config, dict):
        return jsonify({"error": "'config' must be a JSON object"}), 400

    plugin = plugin_registry.get(plugin_id)
    try:
        status = plugin.get_status(config)
    except Exception:
        logger.exception("get_status raised during /test for plugin '%s'", plugin_id)
        status = {"connected": False, "detail": "Status check raised an error"}

    return jsonify(status)


@plugins_bp.route("/<plugin_id>/status", methods=["GET"])
@login_required
def plugin_status(plugin_id: str):
    """Return the live connection status of an enabled plugin.

    Returns::

        {"connected": bool, "detail": str}
    """
    if not plugin_registry.has(plugin_id):
        return jsonify({"error": f"Plugin '{plugin_id}' not found"}), 404

    stored  = plugin_registry.get_config(plugin_id)
    enabled = bool(stored.get("enabled", False))

    if not enabled:
        return jsonify({"connected": False, "detail": "Plugin is disabled"})

    plugin     = plugin_registry.get(plugin_id)
    raw_config = stored.get("config", {})

    try:
        status = plugin.get_status(raw_config)
    except Exception:
        logger.exception("get_status raised for plugin '%s'", plugin_id)
        status = {"connected": False, "detail": "Status check failed"}

    return jsonify(status)
