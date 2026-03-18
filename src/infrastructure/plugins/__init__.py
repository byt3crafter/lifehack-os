"""Plugin system for LifeHack OS.

Public API::

    from src.infrastructure.plugins import (
        Plugin,
        PluginRegistry,
        plugin_registry,        # module-level singleton
        VikunjaPlugin,
        GoogleCalendarPlugin,
        FireflyPlugin,
        register_builtin_plugins,
    )

Call ``register_builtin_plugins()`` once at application startup to load all
first-party plugins into the singleton registry.
"""
from .base import Plugin
from .registry import PluginRegistry, plugin_registry
from .vikunja_plugin import VikunjaPlugin
from .google_calendar_plugin import GoogleCalendarPlugin
from .firefly_plugin import FireflyPlugin


def register_builtin_plugins() -> None:
    """Register all first-party plugins into the singleton registry.

    Safe to call multiple times — subsequent calls are no-ops if the
    plugins are already registered.
    """
    for plugin in (VikunjaPlugin(), GoogleCalendarPlugin(), FireflyPlugin()):
        if not plugin_registry.has(plugin.id):
            plugin_registry.register(plugin)


__all__ = [
    "Plugin",
    "PluginRegistry",
    "plugin_registry",
    "VikunjaPlugin",
    "GoogleCalendarPlugin",
    "FireflyPlugin",
    "register_builtin_plugins",
]
