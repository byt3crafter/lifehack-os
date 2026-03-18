"""Firefly III plugin — wraps the existing FireflyProvider."""
import logging

from .base import Plugin

logger = logging.getLogger(__name__)


class FireflyPlugin(Plugin):
    """Personal finance data via a Firefly III helper script."""

    id          = "firefly"
    name        = "Firefly III"
    description = "Access accounts, transactions, and budgets via a Firefly III helper script."
    category    = "finance"
    icon        = "F"

    def get_config_fields(self) -> list[dict]:
        return [
            {
                "id":          "helper_path",
                "label":       "Firefly Helper Script Path",
                "type":        "text",
                "required":    True,
                "placeholder": "/usr/local/bin/firefly.sh",
            },
            {
                "id":          "account_id",
                "label":       "Default Account ID",
                "type":        "text",
                "required":    False,
                "placeholder": "1",
            },
        ]

    def test_connection(self, config: dict) -> bool:
        """Verify the helper script can be executed and returns account data."""
        from src.infrastructure.providers.firefly import FireflyProvider, FireflyConfig

        try:
            provider = FireflyProvider(
                FireflyConfig(
                    enabled=True,
                    helper_path=config.get("helper_path", ""),
                    default_account_id=config.get("account_id", ""),
                )
            )
            return provider.test_connection()
        except Exception:
            logger.debug("Firefly connection test failed", exc_info=True)
            return False

    def get_status(self, config: dict) -> dict:
        """Return connected state and a short status message."""
        connected = self.test_connection(config)
        return {
            "connected": connected,
            "detail": (
                "Connected to Firefly III" if connected
                else "Helper script not found or returned an error"
            ),
        }

    def get_provider(self, config: dict):
        """Return a ready-to-use FireflyProvider."""
        from src.infrastructure.providers.firefly import FireflyProvider, FireflyConfig

        return FireflyProvider(
            FireflyConfig(
                enabled=True,
                helper_path=config.get("helper_path", ""),
                default_account_id=config.get("account_id", ""),
            )
        )
