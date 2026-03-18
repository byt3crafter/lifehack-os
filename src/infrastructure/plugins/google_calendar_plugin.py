"""Google Calendar plugin — wraps the existing GoogleCalendarProvider."""
import logging

from .base import Plugin

logger = logging.getLogger(__name__)


class GoogleCalendarPlugin(Plugin):
    """Upcoming events from Google Calendar via the 'gog' CLI."""

    id          = "google_calendar"
    name        = "Google Calendar"
    description = "Pull upcoming events from Google Calendar using the gog CLI."
    category    = "calendar"
    icon        = "G"

    def get_config_fields(self) -> list[dict]:
        return [
            {
                "id":          "account",
                "label":       "Google Account Email",
                "type":        "text",
                "required":    True,
                "placeholder": "you@gmail.com",
            },
        ]

    def test_connection(self, config: dict) -> bool:
        """Verify that the gog CLI can list calendars for the given account."""
        from src.infrastructure.providers.google_calendar import (
            GoogleCalendarProvider,
            GoogleCalendarConfig,
        )

        try:
            provider = GoogleCalendarProvider(
                GoogleCalendarConfig(
                    enabled=True,
                    account=config.get("account", ""),
                )
            )
            return provider.test_connection()
        except Exception:
            logger.debug("Google Calendar connection test failed", exc_info=True)
            return False

    def get_status(self, config: dict) -> dict:
        """Return connected state and a short status message."""
        connected = self.test_connection(config)
        account = config.get("account", "")
        return {
            "connected": connected,
            "detail": (
                f"Connected as {account}" if connected
                else "gog CLI unavailable or not authenticated"
            ),
        }

    def get_provider(self, config: dict):
        """Return a ready-to-use GoogleCalendarProvider."""
        from src.infrastructure.providers.google_calendar import (
            GoogleCalendarProvider,
            GoogleCalendarConfig,
        )

        return GoogleCalendarProvider(
            GoogleCalendarConfig(
                enabled=True,
                account=config.get("account", ""),
            )
        )
