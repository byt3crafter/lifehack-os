"""Module management routes — enable/disable features."""
import json
from flask import Blueprint, jsonify, request

from .decorators import login_required
from src.infrastructure.database import get_connection

modules_bp = Blueprint('modules', __name__, url_prefix='/api/modules')

# Module definitions: id -> {name, description, default}
MODULE_DEFS = {
    'habits':     {'name': 'Habits',         'description': 'Daily/weekly habit tracking with streaks',   'default': True},
    'checkin':    {'name': 'Check-in',       'description': 'Daily reflection, mood & energy',            'default': True},
    'analytics':  {'name': 'Analytics',      'description': 'XP breakdown, point ledger, stats',          'default': True},
    'projects':   {'name': 'Projects',       'description': 'Project management with milestones',         'default': False},
    'walks':      {'name': 'Movement',       'description': 'Walk & exercise logging',                    'default': False},
    'food':       {'name': 'Food',           'description': 'Nutrition & meal tracking',                  'default': False},
    'fasting':    {'name': 'Fasting',        'description': 'Fasting timer & history',                    'default': False},
    'deepwork':   {'name': 'Deep Work',      'description': 'Focused work session tracking',              'default': False},
    'challenges': {'name': 'Challenges',     'description': 'Custom streak challenges',                   'default': False},
    'replace':    {'name': 'Redirect',       'description': 'Sobriety replacement actions',               'default': False},
    'wishlist':   {'name': 'Wishlist',       'description': 'Places & things to do',                      'default': False},
    'openclaw':   {'name': 'AI Agent (OpenClaw)', 'description': 'External AI agent API access',          'default': False},
}


def get_enabled_modules() -> dict:
    """Get module enabled/disabled state. Returns {module_id: bool}."""
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = 'enabled_modules'"
    ).fetchone()

    if row:
        saved = json.loads(row['value'])
        # Merge with defaults for any new modules
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
    enabled = get_enabled_modules()
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
    """Update module enabled/disabled state."""
    data = request.json  # {module_id: bool, ...}
    current = get_enabled_modules()

    for mod_id, enabled in data.items():
        if mod_id in MODULE_DEFS:
            current[mod_id] = bool(enabled)

    conn = get_connection()
    conn.execute(
        """INSERT INTO app_settings (key, value, updated_at)
           VALUES ('enabled_modules', ?, CURRENT_TIMESTAMP)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
        (json.dumps(current),)
    )
    conn.commit()
    return jsonify({'success': True, 'modules': current})
