"""Google Calendar provider for events integration."""
import subprocess
import json
from typing import List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from .base import TaskProvider, TaskItem, ProjectItem


@dataclass
class CalendarEvent:
    """Calendar event representation."""
    id: str
    title: str
    start: datetime
    end: datetime
    location: str = ""
    description: str = ""
    calendar_id: str = "primary"
    all_day: bool = False


@dataclass  
class GoogleCalendarConfig:
    """Google Calendar configuration."""
    enabled: bool = False
    account: str = "dovik@micinthe.com"
    calendars: List[str] = None  # None = all calendars
    
    def __post_init__(self):
        if self.calendars is None:
            self.calendars = ["primary"]


class GoogleCalendarProvider:
    """
    Google Calendar integration via 'gog' CLI.
    
    Note: This is NOT a TaskProvider - calendars don't have tasks.
    This is a separate EventProvider interface.
    """
    
    provider_name = "google_calendar"
    
    def __init__(self, config: Optional[GoogleCalendarConfig] = None):
        self.config = config or GoogleCalendarConfig()
    
    def test_connection(self) -> bool:
        """Test if gog CLI is available and authenticated."""
        try:
            result = subprocess.run(
                ["gog", "calendar", "calendars", "--account", self.config.account],
                capture_output=True, text=True, timeout=15
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def get_events(self, days_ahead: int = 7, calendar_id: str = "primary") -> List[CalendarEvent]:
        """Get upcoming events from Google Calendar."""
        from_date = datetime.now().strftime("%Y-%m-%d")
        to_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        
        try:
            result = subprocess.run(
                ["gog", "calendar", "events", calendar_id,
                 "--from", from_date, "--to", to_date,
                 "--account", self.config.account, "--json"],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode != 0:
                return []
            
            events_data = json.loads(result.stdout) if result.stdout.strip() else []
            return [self._parse_event(e) for e in events_data]
        except Exception:
            return []
    
    def get_today_events(self) -> List[CalendarEvent]:
        """Get today's events."""
        return self.get_events(days_ahead=1)
    
    def create_event(self, title: str, start: datetime, end: datetime,
                    description: str = "", location: str = "",
                    calendar_id: str = "primary") -> Optional[CalendarEvent]:
        """Create a new calendar event."""
        try:
            # gog calendar event create format
            result = subprocess.run(
                ["gog", "calendar", "event", "create",
                 "--calendar", calendar_id,
                 "--title", title,
                 "--start", start.isoformat(),
                 "--end", end.isoformat(),
                 "--description", description,
                 "--location", location,
                 "--account", self.config.account],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                return CalendarEvent(
                    id="new", title=title, start=start, end=end,
                    description=description, location=location
                )
        except Exception:
            pass
        return None
    
    def _parse_event(self, data: dict) -> CalendarEvent:
        """Parse event from gog JSON output."""
        start_str = data.get("start", {}).get("dateTime") or data.get("start", {}).get("date", "")
        end_str = data.get("end", {}).get("dateTime") or data.get("end", {}).get("date", "")
        
        all_day = "date" in data.get("start", {}) and "dateTime" not in data.get("start", {})
        
        try:
            start = datetime.fromisoformat(start_str.replace("Z", "+00:00")) if start_str else datetime.now()
            end = datetime.fromisoformat(end_str.replace("Z", "+00:00")) if end_str else start
        except ValueError:
            start = end = datetime.now()
        
        return CalendarEvent(
            id=data.get("id", ""),
            title=data.get("summary", "Untitled"),
            start=start,
            end=end,
            location=data.get("location", ""),
            description=data.get("description", ""),
            all_day=all_day
        )
