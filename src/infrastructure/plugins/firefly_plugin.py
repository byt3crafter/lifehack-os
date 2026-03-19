"""Firefly III plugin — connects directly to the Firefly III REST API."""
import logging

import requests

from .base import Plugin

logger = logging.getLogger(__name__)


class FireflyPlugin(Plugin):
    """Personal finance data via the Firefly III REST API."""

    id          = "firefly"
    name        = "Firefly III"
    description = "Access accounts, transactions, and budgets via the Firefly III REST API."
    category    = "finance"
    icon        = "F"

    def get_config_fields(self) -> list[dict]:
        return [
            {
                "id":          "api_url",
                "label":       "Firefly III API URL",
                "type":        "url",
                "required":    True,
                "placeholder": "https://firefly.example.com (without /api/v1)",
            },
            {
                "id":          "api_token",
                "label":       "Personal Access Token",
                "type":        "password",
                "required":    True,
                "placeholder": "eyJ0eXAiOiJKV1QiLC...",
            },
            {
                "id":          "default_account_id",
                "label":       "Default Account ID",
                "type":        "text",
                "required":    False,
                "placeholder": "1",
            },
        ]

    @staticmethod
    def _base_url(api_url: str) -> str:
        """Normalize the URL — strip trailing /api/v1 if user included it."""
        url = api_url.rstrip("/")
        if url.endswith("/api/v1"):
            url = url[:-7]
        if url.endswith("/api"):
            url = url[:-4]
        return url

    def test_connection(self, config: dict) -> bool:
        """Verify the API URL and token are valid by calling /api/v1/about."""
        api_url = self._base_url(config.get("api_url", ""))
        api_token = config.get("api_token", "")
        if not api_url or not api_token:
            return False
        try:
            resp = requests.get(
                f"{api_url}/api/v1/about",
                headers={"Authorization": f"Bearer {api_token}", "Accept": "application/json"},
                timeout=10,
            )
            return resp.status_code == 200
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
                else "Could not reach Firefly III — check the API URL and token"
            ),
        }

    def get_provider(self, config: dict):
        """Return a ready-to-use FireflyProvider (legacy helper-script wrapper).

        Falls back to the existing helper-based provider so that existing
        integrations continue to work while the REST-native provider is built.
        """
        from src.infrastructure.providers.firefly import FireflyProvider, FireflyConfig

        return FireflyProvider(
            FireflyConfig(
                enabled=True,
                helper_path=config.get("helper_path", ""),
                default_account_id=config.get("default_account_id", ""),
            )
        )
