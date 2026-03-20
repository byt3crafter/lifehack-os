"""Routes package - Flask Blueprints for LifeHack OS."""
import sys
from pathlib import Path

# Add parent to path for src imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .auth import auth_bp
from .habits import habits_bp
from .food import food_bp
from .checkins import checkins_bp, mood_bp
from .walks import walks_bp
from .patterns import patterns_bp
from .reports import reports_bp
from .projects import projects_bp
from .integrations import integrations_bp
from .misc import misc_bp
from .openclaw import openclaw_bp
from .challenges import challenges_bp
from .modules import modules_bp
from .ai import ai_bp
from .api_docs import api_docs_bp
from .plugins import plugins_bp
from .settings import settings_bp
from .openai_oauth import openai_oauth_bp
from .ai_models import ai_models_bp
from .app_log import app_log_bp
from .finance import finance_bp
from .discover import discover_bp
from .chat import chat_bp
from .deepwork import deepwork_bp
from .journal import journal_bp
from .books import books_bp
from .notes import notes_bp
from .wellness import wellness_bp

__all__ = [
    'auth_bp',
    'habits_bp',
    'food_bp',
    'checkins_bp',
    'mood_bp',
    'walks_bp',
    'patterns_bp',
    'reports_bp',
    'projects_bp',
    'integrations_bp',
    'misc_bp',
    'openclaw_bp',
    'challenges_bp',
    'modules_bp',
    'ai_bp',
    'api_docs_bp',
    'plugins_bp',
    'settings_bp',
    'openai_oauth_bp',
    'ai_models_bp',
    'app_log_bp',
    'finance_bp',
    'discover_bp',
    'chat_bp',
    'deepwork_bp',
    'journal_bp',
    'books_bp',
    'notes_bp',
    'wellness_bp',
]
