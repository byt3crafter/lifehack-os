"""Plugin registry — discovers, stores, and manages all available plugins."""
import logging
from typing import Optional

from .base import Plugin
from src.infrastructure.database.user_scope import get_user_integration, set_user_integration

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Centralised store for all registered plugins.

    Usage::

        from src.infrastructure.plugins import plugin_registry

        # At application startup
        plugin_registry.register(VikunjaPlugin())

        # In route handlers (user_id is required for all config operations)
        plugins = plugin_registry.get_all()
        plugin  = plugin_registry.get("vikunja")
        config  = plugin_registry.get_config("vikunja", user_id)
        ok      = plugin_registry.enable("vikunja", {"api_url": "...", ...}, user_id)
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
    # Persistence helpers (user_integrations table)
    # ------------------------------------------------------------------

    def get_config(self, plugin_id: str, user_id: int) -> dict:
        """Load plugin config from the user_integrations table.

        Returns ``{}`` if nothing has been saved yet.
        The returned dict has the shape::

            {"enabled": bool, "config": {field_id: value, ...}}
        """
        from src.infrastructure.database import get_connection

        try:
            conn = get_connection()
            result = get_user_integration(conn, user_id, plugin_id)
            if result is not None:
                return result
        except Exception:
            logger.exception("Failed to load config for plugin '%s'", plugin_id)
        return {}

    def save_config(self, plugin_id: str, data: dict, user_id: int) -> None:
        """Persist plugin config to the user_integrations table.

        ``data`` must be a dict with shape ``{"enabled": bool, "config": {...}}``.
        """
        from src.infrastructure.database import get_connection

        try:
            conn = get_connection()
            enabled = bool(data.get('enabled', False))
            config = data.get('config', {})
            set_user_integration(conn, user_id, plugin_id, enabled, config)
        except Exception:
            logger.exception("Failed to save config for plugin '%s'", plugin_id)
            raise

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    def is_enabled(self, plugin_id: str, user_id: int) -> bool:
        """Return True if the plugin is enabled for this user."""
        stored = self.get_config(plugin_id, user_id)
        return bool(stored.get("enabled", False))

    def enable(self, plugin_id: str, config: dict, user_id: int) -> bool:
        """Enable a plugin after a successful connection test.

        Args:
            plugin_id: The plugin's unique id.
            config:    Dict mapping field ids to their values.
            user_id:   The user enabling the plugin.

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

        stored = self.get_config(plugin_id, user_id)
        stored["enabled"] = True
        stored["config"] = config
        self.save_config(plugin_id, stored, user_id)
        return True

    def disable(self, plugin_id: str, user_id: int) -> None:
        """Disable a plugin (keeps its config so re-enabling is frictionless)."""
        stored = self.get_config(plugin_id, user_id)
        stored["enabled"] = False
        self.save_config(plugin_id, stored, user_id)

    # ------------------------------------------------------------------
    # Convenience: scrub sensitive fields before sending to the client
    # ------------------------------------------------------------------

    def safe_config(self, plugin_id: str, user_id: int) -> dict:
        """Return the stored config dict with password fields masked."""
        plugin = self.get(plugin_id)
        stored = self.get_config(plugin_id, user_id)
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
