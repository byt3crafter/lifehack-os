"""Plugin registry — discovers, stores, and manages all available plugins."""
import json
import logging
from typing import Optional

from .base import Plugin

logger = logging.getLogger(__name__)

# app_settings key template
_SETTINGS_KEY = "plugin_config_{plugin_id}"


class PluginRegistry:
    """Centralised store for all registered plugins.

    Usage::

        from src.infrastructure.plugins import plugin_registry

        # At application startup
        plugin_registry.register(VikunjaPlugin())

        # In route handlers
        plugins = plugin_registry.get_all()
        plugin  = plugin_registry.get("vikunja")
        config  = plugin_registry.get_config("vikunja")
        ok      = plugin_registry.enable("vikunja", {"api_url": "...", ...})
    """

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, plugin: Plugin) -> None:
        """Register a plugin instance. Raises ValueError on duplicate id."""
        if plugin.id in self._plugins:
            raise ValueError(f"Plugin '{plugin.id}' is already registered.")
        self._plugins[plugin.id] = plugin
        logger.debug("Registered plugin: %s", plugin.id)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_all(self) -> list[Plugin]:
        """Return all registered plugin instances, in registration order."""
        return list(self._plugins.values())

    def get(self, plugin_id: str) -> Plugin:
        """Return a single plugin by id. Raises KeyError if not found."""
        if plugin_id not in self._plugins:
            raise KeyError(f"Plugin '{plugin_id}' is not registered.")
        return self._plugins[plugin_id]

    def has(self, plugin_id: str) -> bool:
        """Return True if a plugin with the given id is registered."""
        return plugin_id in self._plugins

    # ------------------------------------------------------------------
    # Persistence helpers (app_settings table)
    # ------------------------------------------------------------------

    @staticmethod
    def _settings_key(plugin_id: str) -> str:
        return _SETTINGS_KEY.format(plugin_id=plugin_id)

    def get_config(self, plugin_id: str) -> dict:
        """Load plugin config from the app_settings table.

        Returns ``{}`` if nothing has been saved yet.
        The returned dict has the shape::

            {"enabled": bool, "config": {field_id: value, ...}}
        """
        from src.infrastructure.database import get_connection

        try:
            conn = get_connection()
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (self._settings_key(plugin_id),),
            ).fetchone()
            if row:
                return json.loads(row["value"])
        except Exception:
            logger.exception("Failed to load config for plugin '%s'", plugin_id)
        return {}

    def save_config(self, plugin_id: str, data: dict) -> None:
        """Persist plugin config to the app_settings table.

        ``data`` must be a dict with shape ``{"enabled": bool, "config": {...}}``.
        """
        from src.infrastructure.database import get_connection

        try:
            conn = get_connection()
            conn.execute(
                """INSERT INTO app_settings (key, value, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE
                   SET value = excluded.value,
                       updated_at = excluded.updated_at""",
                (self._settings_key(plugin_id), json.dumps(data)),
            )
            conn.commit()
        except Exception:
            logger.exception("Failed to save config for plugin '%s'", plugin_id)
            raise

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    def is_enabled(self, plugin_id: str) -> bool:
        """Return True if the plugin is enabled in the database."""
        stored = self.get_config(plugin_id)
        return bool(stored.get("enabled", False))

    def enable(self, plugin_id: str, config: dict) -> bool:
        """Enable a plugin after a successful connection test.

        Args:
            plugin_id: The plugin's unique id.
            config:    Dict mapping field ids to their values.

        Returns:
            True if the connection test passed and the plugin was persisted as
            enabled; False if the test failed.
        """
        plugin = self.get(plugin_id)

        try:
            connected = plugin.test_connection(config)
        except Exception:
            logger.exception("test_connection raised for plugin '%s'", plugin_id)
            connected = False

        if not connected:
            return False

        stored = self.get_config(plugin_id)
        stored["enabled"] = True
        stored["config"] = config
        self.save_config(plugin_id, stored)
        return True

    def disable(self, plugin_id: str) -> None:
        """Disable a plugin (keeps its config so re-enabling is frictionless)."""
        stored = self.get_config(plugin_id)
        stored["enabled"] = False
        self.save_config(plugin_id, stored)

    # ------------------------------------------------------------------
    # Convenience: scrub sensitive fields before sending to the client
    # ------------------------------------------------------------------

    def safe_config(self, plugin_id: str) -> dict:
        """Return the stored config dict with password fields masked."""
        plugin = self.get(plugin_id)
        stored = self.get_config(plugin_id)
        raw_config: dict = stored.get("config", {})

        password_fields = {
            f["id"]
            for f in plugin.get_config_fields()
            if f.get("type") == "password"
        }

        return {
            k: ("********" if k in password_fields and v else v)
            for k, v in raw_config.items()
        }


# Module-level singleton used throughout the application
plugin_registry = PluginRegistry()
