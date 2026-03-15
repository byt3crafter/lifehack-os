"""Routes package - Flask Blueprints for LifeHack OS."""
import sys
from pathlib import Path

# Add parent to path for src imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .auth import auth_bp
from .habits import habits_bp
from .food import food_bp
from .checkins import checkins_bp
from .walks import walks_bp
from .patterns import patterns_bp
from .reports import reports_bp
from .projects import projects_bp
from .integrations import integrations_bp
from .misc import misc_bp
from .openclaw import openclaw_bp
from .challenges import challenges_bp

__all__ = [
    'auth_bp',
    'habits_bp', 
    'food_bp',
    'checkins_bp',
    'walks_bp',
    'patterns_bp',
    'reports_bp',
    'projects_bp',
    'integrations_bp',
    'misc_bp',
    'openclaw_bp',
    'challenges_bp'
]
