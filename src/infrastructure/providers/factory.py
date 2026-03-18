"""Provider factory — returns the appropriate provider based on plugin registry settings.

All state is now stored in the app_settings table via the plugin registry.
The legacy JSON config file (config/integrations.json) is no longer used; it is
kept for reference only.

Legacy public API is preserved so that callers outside web/routes/ keep working
without modification.
"""
import logging
from typing import Optional

from .base import TaskProvider
from .native import NativeTaskProvider
from .vikunja import VikunjaTaskProvider, VikunjaConfig
from .google_calendar import GoogleCalendarProvider, GoogleCalendarConfig
from .firefly import FireflyProvider, FireflyConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers — thin wrappers around the plugin registry
# ---------------------------------------------------------------------------

def _registry():
    """Lazy import to avoid circular dependencies at module load time."""
    from src.infrastructure.plugins import plugin_registry
    return plugin_registry


def _get_plugin_config(plugin_id: str) -> dict:
    try:
        stored = _registry().get_config(plugin_id)
        return stored.get("config", {}) if stored.get("enabled") else {}
    except Exception:
        return {}


def _is_enabled(plugin_id: str) -> bool:
    try:
        return _registry().is_enabled(plugin_id)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Task provider
# ---------------------------------------------------------------------------

def get_task_provider(prefer_native: bool = False) -> TaskProvider:
    """Return the best available task provider.

    Falls back to NativeTaskProvider if Vikunja is not enabled or the
    connection test fails.
    """
    if prefer_native:
        return NativeTaskProvider()

    if _is_enabled("vikunja"):
        cfg = _get_plugin_config("vikunja")
        if cfg:
            try:
                provider = VikunjaTaskProvider(
                    VikunjaConfig(
                        api_url=cfg.get("api_url", ""),
                        username=cfg.get("username", ""),
                        password=cfg.get("password", ""),
                    )
                )
                if provider.test_connection():
                    return provider
            except Exception:
                logger.debug("Vikunja provider unavailable, falling back to native", exc_info=True)

    return NativeTaskProvider()


# ---------------------------------------------------------------------------
# Integration status (legacy shape)
# ---------------------------------------------------------------------------

def get_integration_status() -> dict:
    """Return status dict for all integrations in the legacy response shape."""
    # Vikunja
    vikunja_enabled = _is_enabled("vikunja")
    vikunja_cfg     = _get_plugin_config("vikunja")
    vikunja_connected = False
    if vikunja_enabled and vikunja_cfg:
        try:
            provider = VikunjaTaskProvider(
                VikunjaConfig(
                    api_url=vikunja_cfg.get("api_url", ""),
                    username=vikunja_cfg.get("username", ""),
                    password=vikunja_cfg.get("password", ""),
                )
            )
            vikunja_connected = provider.test_connection()
        except Exception:
            pass

    # Google Calendar
    gcal_enabled = _is_enabled("google_calendar")
    gcal_cfg     = _get_plugin_config("google_calendar")
    gcal_connected = False
    if gcal_enabled and gcal_cfg:
        try:
            provider = GoogleCalendarProvider(
                GoogleCalendarConfig(enabled=True, account=gcal_cfg.get("account", ""))
            )
            gcal_connected = provider.test_connection()
        except Exception:
            pass

    # Firefly
    firefly_enabled = _is_enabled("firefly")
    firefly_cfg     = _get_plugin_config("firefly")
    firefly_connected = False
    if firefly_enabled and firefly_cfg:
        try:
            provider = FireflyProvider(
                FireflyConfig(
                    enabled=True,
                    helper_path=firefly_cfg.get("helper_path", ""),
                    default_account_id=firefly_cfg.get("account_id", ""),
                )
            )
            firefly_connected = provider.test_connection()
        except Exception:
            pass

    return {
        "vikunja": {
            "enabled":     vikunja_enabled,
            "connected":   vikunja_connected,
            "api_url":     vikunja_cfg.get("api_url", ""),
            "description": "Task management via Vikunja",
        },
        "google_calendar": {
            "enabled":     gcal_enabled,
            "connected":   gcal_connected,
            "account":     gcal_cfg.get("account", ""),
            "description": "Events from Google Calendar",
        },
        "firefly": {
            "enabled":     firefly_enabled,
            "connected":   firefly_connected,
            "description": "Personal finance via Firefly III",
        },
    }


# ---------------------------------------------------------------------------
# Vikunja — legacy helpers
# ---------------------------------------------------------------------------

def enable_vikunja(api_url: str, username: str, password: str) -> bool:
    """Enable Vikunja via the plugin registry. Returns True on success."""
    config = {"api_url": api_url, "username": username, "password": password}
    return _registry().enable("vikunja", config)


def disable_vikunja() -> None:
    """Disable the Vikunja plugin."""
    _registry().disable("vikunja")


def get_vikunja_config() -> Optional[VikunjaConfig]:
    """Return VikunjaConfig if the plugin is enabled, else None."""
    if not _is_enabled("vikunja"):
        return None
    cfg = _get_plugin_config("vikunja")
    if not cfg:
        return None
    return VikunjaConfig(
        api_url=cfg.get("api_url", ""),
        username=cfg.get("username", ""),
        password=cfg.get("password", ""),
    )


# ---------------------------------------------------------------------------
# Google Calendar — legacy helpers
# ---------------------------------------------------------------------------

def enable_google_calendar(account: str = "") -> bool:
    """Enable Google Calendar via the plugin registry."""
    return _registry().enable("google_calendar", {"account": account})


def disable_google_calendar() -> None:
    """Disable the Google Calendar plugin."""
    _registry().disable("google_calendar")


def get_calendar_provider() -> Optional[GoogleCalendarProvider]:
    """Return GoogleCalendarProvider if the plugin is enabled, else None."""
    if not _is_enabled("google_calendar"):
        return None
    cfg = _get_plugin_config("google_calendar")
    return GoogleCalendarProvider(
        GoogleCalendarConfig(enabled=True, account=cfg.get("account", ""))
    )


# ---------------------------------------------------------------------------
# Firefly — legacy helpers
# ---------------------------------------------------------------------------

def enable_firefly(helper_path: str = "", account_id: str = "") -> bool:
    """Enable Firefly via the plugin registry."""
    return _registry().enable("firefly", {"helper_path": helper_path, "account_id": account_id})


def disable_firefly() -> None:
    """Disable the Firefly plugin."""
    _registry().disable("firefly")


def get_firefly_provider() -> Optional[FireflyProvider]:
    """Return FireflyProvider if the plugin is enabled, else None."""
    if not _is_enabled("firefly"):
        return None
    cfg = _get_plugin_config("firefly")
    return FireflyProvider(
        FireflyConfig(
            enabled=True,
            helper_path=cfg.get("helper_path", ""),
            default_account_id=cfg.get("account_id", ""),
        )
    )
