"""View modules."""
from .dashboard import DashboardView
from .habits import HabitsView
from .projects import ProjectsView
from .checkin import CheckinView
from .walks import WalksView
from .analytics import AnalyticsView

__all__ = [
    'DashboardView', 'HabitsView', 'ProjectsView',
    'CheckinView', 'WalksView', 'AnalyticsView'
]
