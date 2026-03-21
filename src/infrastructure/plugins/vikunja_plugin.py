"""Vikunja plugin — wraps the existing VikunjaTaskProvider."""
import logging

from .base import Plugin

logger = logging.getLogger(__name__)


class VikunjaPlugin(Plugin):
    """Task management via a self-hosted Vikunja instance."""

    id          = "vikunja"
    name        = "Vikunja"
    description = "Sync tasks and projects with a self-hosted Vikunja instance."
    category    = "tasks"
    icon        = "V"

    def get_config_fields(self) -> list[dict]:
        return [
            {
                "id":          "api_url",
                "label":       "API URL",
                "type":        "url",
                "required":    True,
                "placeholder": "https://vikunja.example.com/api/v1",
            },
            {
                "id":          "api_token",
                "label":       "API Token",
                "type":        "password",
                "required":    True,
                "placeholder": "Your Vikunja API token",
            },
        ]

    def test_connection(self, config: dict) -> bool:
        """Test connection using the API token."""
        from src.infrastructure.providers.vikunja import VikunjaTaskProvider, VikunjaConfig

        api_url = self._normalize_url(config.get("api_url", ""))

        try:
            provider = VikunjaTaskProvider(
                VikunjaConfig(
                    api_url=api_url,
                    token=config.get("api_token", ""),
                )
            )
            return provider.test_connection()
        except Exception:
            logger.warning("Vikunja connection test failed for %s", api_url, exc_info=True)
            return False

    @staticmethod
    def _normalize_url(url: str) -> str:
        url = (url or "").rstrip("/")
        if url and not url.endswith("/api/v1"):
            url = url + "/api/v1"
        return url

    def get_status(self, config: dict) -> dict:
        connected = self.test_connection(config)
        return {
            "connected": connected,
            "detail":    "Connected to Vikunja" if connected else "Unable to reach Vikunja API",
        }

    def get_provider(self, config: dict):
        """Return a ready-to-use VikunjaTaskProvider."""
        from src.infrastructure.providers.vikunja import VikunjaTaskProvider, VikunjaConfig

        return VikunjaTaskProvider(
            VikunjaConfig(
                api_url=self._normalize_url(config.get("api_url", "")),
                token=config.get("api_token", ""),
            )
        )
