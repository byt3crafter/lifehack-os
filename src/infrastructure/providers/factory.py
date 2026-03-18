"""Provider factory - returns appropriate provider based on settings."""
import json
from typing import Optional
from pathlib import Path

from .base import TaskProvider
from .native import NativeTaskProvider
from .vikunja import VikunjaTaskProvider, VikunjaConfig
from .google_calendar import GoogleCalendarProvider, GoogleCalendarConfig
from .firefly import FireflyProvider, FireflyConfig


# Default config path
CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "config"
INTEGRATIONS_FILE = CONFIG_DIR / "integrations.json"


def load_integrations() -> dict:
    """Load integration settings from config file."""
    if not INTEGRATIONS_FILE.exists():
        return {"vikunja": {"enabled": False}}
    
    try:
        with open(INTEGRATIONS_FILE) as f:
            return json.load(f)
    except Exception:
        return {"vikunja": {"enabled": False}}


def save_integrations(config: dict) -> None:
    """Save integration settings to config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(INTEGRATIONS_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_vikunja_config() -> Optional[VikunjaConfig]:
    """Get Vikunja config from integrations file."""
    integrations = load_integrations()
    vikunja = integrations.get("vikunja", {})
    
    if not vikunja.get("enabled"):
        return None
    
    return VikunjaConfig(
        api_url=vikunja.get("api_url", ""),
        username=vikunja.get("username", ""),
        password=vikunja.get("password", ""),
        token=vikunja.get("token", "")
    )


def get_task_provider(prefer_native: bool = False) -> TaskProvider:
    """
    Get the appropriate task provider based on settings.
    
    Args:
        prefer_native: If True, always return native provider (for fallback scenarios)
    
    Returns:
        TaskProvider instance (Vikunja if enabled and connected, else Native)
    """
    if prefer_native:
        return NativeTaskProvider()
    
    vikunja_config = get_vikunja_config()
    
    if vikunja_config:
        try:
            provider = VikunjaTaskProvider(vikunja_config)
            if provider.test_connection():
                return provider
        except Exception:
            pass  # Fall through to native
    
    return NativeTaskProvider()


def enable_vikunja(api_url: str, username: str, password: str) -> bool:
    """
    Enable Vikunja integration.
    
    Returns True if connection test passes.
    """
    config = VikunjaConfig(
        api_url=api_url,
        username=username,
        password=password
    )
    
    provider = VikunjaTaskProvider(config)
    if not provider.test_connection():
        return False
    
    integrations = load_integrations()
    integrations["vikunja"] = {
        "enabled": True,
        "api_url": api_url,
        "username": username,
        "password": password
    }
    save_integrations(integrations)
    return True


def disable_vikunja() -> None:
    """Disable Vikunja integration."""
    integrations = load_integrations()
    if "vikunja" in integrations:
        integrations["vikunja"]["enabled"] = False
    save_integrations(integrations)


def get_integration_status() -> dict:
    """Get status of all integrations."""
    integrations = load_integrations()
    status = {}
    
    # Vikunja
    vikunja = integrations.get("vikunja", {})
    vikunja_status = {
        "enabled": vikunja.get("enabled", False),
        "connected": False,
        "api_url": vikunja.get("api_url", ""),
        "description": "Task management via Vikunja"
    }
    
    if vikunja_status["enabled"]:
        config = get_vikunja_config()
        if config:
            try:
                provider = VikunjaTaskProvider(config)
                vikunja_status["connected"] = provider.test_connection()
            except Exception:
                pass
    
    status["vikunja"] = vikunja_status
    
    # Google Calendar
    gcal = integrations.get("google_calendar", {})
    gcal_status = {
        "enabled": gcal.get("enabled", False),
        "connected": False,
        "account": gcal.get("account", ""),
        "description": "Events from Google Calendar"
    }
    
    if gcal_status["enabled"]:
        try:
            config = GoogleCalendarConfig(
                enabled=True,
                account=gcal.get("account", "")
            )
            provider = GoogleCalendarProvider(config)
            gcal_status["connected"] = provider.test_connection()
        except Exception:
            pass
    
    status["google_calendar"] = gcal_status
    
    # Firefly III
    firefly = integrations.get("firefly", {})
    firefly_status = {
        "enabled": firefly.get("enabled", False),
        "connected": False,
        "description": "Personal finance via Firefly III"
    }
    
    if firefly_status["enabled"]:
        try:
            provider = FireflyProvider(FireflyConfig(enabled=True))
            firefly_status["connected"] = provider.test_connection()
        except Exception:
            pass
    
    status["firefly"] = firefly_status
    
    return status


# ============== Google Calendar ==============

def enable_google_calendar(account: str = "") -> bool:
    """Enable Google Calendar integration."""
    config = GoogleCalendarConfig(enabled=True, account=account)
    provider = GoogleCalendarProvider(config)
    
    if not provider.test_connection():
        return False
    
    integrations = load_integrations()
    integrations["google_calendar"] = {
        "enabled": True,
        "account": account
    }
    save_integrations(integrations)
    return True


def disable_google_calendar() -> None:
    """Disable Google Calendar integration."""
    integrations = load_integrations()
    if "google_calendar" in integrations:
        integrations["google_calendar"]["enabled"] = False
    save_integrations(integrations)


def get_calendar_provider() -> Optional[GoogleCalendarProvider]:
    """Get Google Calendar provider if enabled."""
    integrations = load_integrations()
    gcal = integrations.get("google_calendar", {})
    
    if not gcal.get("enabled"):
        return None
    
    config = GoogleCalendarConfig(
        enabled=True,
        account=gcal.get("account", "")
    )
    return GoogleCalendarProvider(config)


# ============== Firefly III ==============

def enable_firefly() -> bool:
    """Enable Firefly III integration."""
    provider = FireflyProvider(FireflyConfig(enabled=True))
    
    if not provider.test_connection():
        return False
    
    integrations = load_integrations()
    integrations["firefly"] = {"enabled": True}
    save_integrations(integrations)
    return True


def disable_firefly() -> None:
    """Disable Firefly III integration."""
    integrations = load_integrations()
    if "firefly" in integrations:
        integrations["firefly"]["enabled"] = False
    save_integrations(integrations)


def get_firefly_provider() -> Optional[FireflyProvider]:
    """Get Firefly provider if enabled."""
    integrations = load_integrations()
    firefly = integrations.get("firefly", {})
    
    if not firefly.get("enabled"):
        return None
    
    return FireflyProvider(FireflyConfig(enabled=True))
