"""Module management routes — enable/disable features."""
import json
from flask import Blueprint, jsonify, request

from .decorators import login_required, current_user_id
from src.infrastructure.database import get_connection
from src.infrastructure.database.user_scope import get_user_setting, set_user_setting

modules_bp = Blueprint('modules', __name__, url_prefix='/api/modules')

# Module definitions: id -> {name, description, default}
MODULE_DEFS = {
    'habits':     {'name': 'Habits',      'description': 'Smart habit tracking with phases and micro-tasks', 'default': True},
    'food':       {'name': 'Food',        'description': 'Nutrition tracking with AI photo analysis',       'default': True},
    'fasting':    {'name': 'Fasting',     'description': 'Intermittent fasting lifestyle tracker',           'default': False},
    'deepwork':   {'name': 'Deep Work',   'description': 'Project-based work logging',                      'default': False},
    'finance':    {'name': 'Finance',     'description': 'Personal finance with AI budget advice',           'default': False},
    'challenges': {'name': 'Challenges',  'description': 'Spontaneous one-off commitments',                  'default': False},
    'discover':   {'name': 'Discover',    'description': 'Bucket list of experiences and places',            'default': False},
    'openclaw':   {'name': 'AI Agent',    'description': 'External AI agent API access',                     'default': False},
    'journal':    {'name': 'Journal',     'description': 'Daily journaling with gratitude, wins, and reflections', 'default': False},
    'books':      {'name': 'Books',       'description': 'Book tracker with reading sessions and yearly challenge', 'default': False},
    'notes':      {'name': 'Notes',       'description': 'Quick capture notes with folders and search',            'default': False},
    'wellness':   {'name': 'Wellness',    'description': 'Water intake, sleep tracking, and wellness score',        'default': False},
}

_SETTING_KEY = 'enabled_modules'


def get_enabled_modules(uid: int = None) -> dict:
    """Get module enabled/disabled state for a user. Returns {module_id: bool}.

    Falls back to app_settings for backwards compatibility when uid is None.
    """
    conn = get_connection()

    if uid is not None:
        raw = get_user_setting(conn, uid, _SETTING_KEY, '')
    else:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (_SETTING_KEY,)
        ).fetchone()
        raw = row['value'] if row else ''

    if raw:
        try:
            saved = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            saved = {}
        result = {}
        for mod_id, mod_def in MODULE_DEFS.items():
            result[mod_id] = saved.get(mod_id, mod_def['default'])
        return result
    else:
        # First run — use defaults
        return {mod_id: mod_def['default'] for mod_id, mod_def in MODULE_DEFS.items()}


@modules_bp.route('')
@login_required
def list_modules():
    """List all modules with their enabled state."""
    uid = current_user_id()
    enabled = get_enabled_modules(uid)
    modules = []
    for mod_id, mod_def in MODULE_DEFS.items():
        modules.append({
            'id': mod_id,
            'name': mod_def['name'],
            'description': mod_def['description'],
            'enabled': enabled.get(mod_id, mod_def['default']),
            'default': mod_def['default'],
        })
    return jsonify(modules)


@modules_bp.route('', methods=['POST'])
@login_required
def update_modules():
    """Update module enabled/disabled state for the current user."""
    uid = current_user_id()
    data = request.json  # {module_id: bool, ...}
    current = get_enabled_modules(uid)

    for mod_id, enabled in data.items():
        if mod_id in MODULE_DEFS:
            current[mod_id] = bool(enabled)

    conn = get_connection()
    set_user_setting(conn, uid, _SETTING_KEY, json.dumps(current))
    return jsonify({'success': True, 'modules': current})
