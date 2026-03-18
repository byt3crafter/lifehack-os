"""Abstract base class for all LifeHack OS plugins."""
from abc import ABC, abstractmethod
from typing import Optional


class Plugin(ABC):
    """Base class for all LifeHack OS plugins.

    Every plugin must declare its identity attributes as class-level strings and
    implement the three abstract methods below.
    """

    # -- Identity (must be overridden as class attributes) --
    id: str           # Unique snake_case identifier, e.g. "vikunja"
    name: str         # Human-readable display name, e.g. "Vikunja"
    description: str  # One-sentence description shown in the UI
    category: str     # One of: "tasks" | "calendar" | "finance" | "health" | "notifications"
    icon: str         # SVG markup or a single emoji

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def get_config_fields(self) -> list[dict]:
        """Return the list of configuration fields this plugin requires.

        Each entry is a dict with the following keys:
            id          str   — field identifier used as the key in config dicts
            label       str   — human-readable label shown in the UI
            type        str   — one of "text" | "password" | "url" | "toggle"
            required    bool  — whether the field must be non-empty to enable the plugin
            placeholder str   — hint text shown in the input (optional, default "")
        """
        ...

    @abstractmethod
    def test_connection(self, config: dict) -> bool:
        """Test connectivity using the supplied config.

        Args:
            config: dict mapping field ids to their string values.

        Returns:
            True if the plugin can successfully reach its backend; False otherwise.
            Must never raise — return False on any exception.
        """
        ...

    @abstractmethod
    def get_status(self, config: dict) -> dict:
        """Return the current connection status of the plugin.

        Args:
            config: dict mapping field ids to their string values.

        Returns:
            {
                "connected": bool,
                "detail":    str   # short human-readable status message
            }
        """
        ...

    # ------------------------------------------------------------------
    # Helpers available to all plugins
    # ------------------------------------------------------------------

    def to_dict(self, enabled: bool = False, config: Optional[dict] = None) -> dict:
        """Serialize plugin metadata to a JSON-serialisable dict.

        The ``config`` dict passed in here should already have sensitive
        (password-type) fields scrubbed before calling this method.
        """
        return {
            "id":           self.id,
            "name":         self.name,
            "description":  self.description,
            "category":     self.category,
            "icon":         self.icon,
            "config_fields": self.get_config_fields(),
            "enabled":      enabled,
            "config":       config or {},
        }
