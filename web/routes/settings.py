"""App settings routes — configure API keys and global preferences from the UI."""
from flask import Blueprint, jsonify, request

from .decorators import login_required, admin_required
from src.infrastructure.database import get_connection

settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')

# Keys that hold sensitive values and should be masked in GET responses
_SENSITIVE_KEYS = {'openclaw_api_key', 'ai_openai_key', 'ai_anthropic_key', 'ai_minimax_key'}

# All recognised setting keys and their defaults
_SETTING_KEYS = {
    'openclaw_api_key',
    # Legacy single-provider key — kept for backwards compatibility.
    # New per-task keys take precedence over this.
    'ai_provider',
    # Per-task provider assignments
    'ai_provider_food',
    'ai_provider_insights',
    'ai_provider_reports',
    'ai_provider_default',
    # Provider credentials / config
    'ai_openai_key',
    'ai_openai_url',
    'ai_openai_model',
    'ai_ollama_url',
    'ai_ollama_model',
    'ai_anthropic_key',
    'ai_anthropic_model',
    'ai_minimax_key',
    'ai_minimax_model',
    'daily_calorie_goal',
}

# Tables to truncate on reset (order matters for FK constraints)
_RESET_TABLES = [
    'habit_completions',
    'habits',
    'tasks',
    'milestones',
    'projects',
    'daily_checkins',
    'walk_logs',
    'food_logs',
    'fasting_logs',
    'wishlist',
    'challenge_logs',
    'challenges',
    'deep_work_sessions',
    'replacement_actions',
    'replacement_logs',
    'ai_insights',
    'openclaw_log',
    'point_ledger',
]


def _get_all_settings(conn) -> dict:
    """Return all app settings as a flat dict (raw, unmasked)."""
    rows = conn.execute(
        "SELECT key, value FROM app_settings WHERE key IN ({})".format(
            ','.join('?' * len(_SETTING_KEYS))
        ),
        list(_SETTING_KEYS),
    ).fetchall()
    return {row['key']: row['value'] for row in rows}


def _upsert_setting(conn, key: str, value: str) -> None:
    conn.execute(
        """INSERT INTO app_settings (key, value, updated_at)
           VALUES (?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                          updated_at = excluded.updated_at""",
        (key, value),
    )


@settings_bp.route('', methods=['GET'])
@login_required
def get_settings():
    """Return current app settings. Sensitive values are masked."""
    conn = get_connection()
    raw = _get_all_settings(conn)

    result = {}
    for key in _SETTING_KEYS:
        value = raw.get(key, '')
        if key in _SENSITIVE_KEYS and value:
            # Show only a hint: first 4 chars + asterisks
            result[key] = value[:4] + '****' if len(value) > 4 else '****'
        else:
            result[key] = value

    return jsonify(result)


@settings_bp.route('', methods=['POST'])
@login_required
def save_settings():
    """Save app settings to the app_settings table."""
    data = request.json or {}
    conn = get_connection()

    saved = []
    for key in _SETTING_KEYS:
        if key in data:
            value = str(data[key]).strip()
            # For sensitive fields: if the client sends back a masked value
            # (ending with ****), skip the update to preserve the real value
            if key in _SENSITIVE_KEYS and value.endswith('****'):
                continue
            _upsert_setting(conn, key, value)
            saved.append(key)

    conn.commit()
    return jsonify({'success': True, 'saved': saved})


@settings_bp.route('/reset', methods=['POST'])
@admin_required
def reset_all_data():
    """Delete all user data. Does NOT remove users or app_settings."""
    from .app_log import log_event
    log_event('warning', 'settings', 'All data reset by admin')

    conn = get_connection()

    for table in _RESET_TABLES:
        try:
            conn.execute(f"DELETE FROM {table}")
        except Exception:
            # Table may not exist yet (e.g. fasting_logs on older installs)
            pass

    # Reset user stats to baseline
    conn.execute(
        "UPDATE user_stats SET total_xp = 0, level = 1 WHERE id = 1"
    )
    # Also clear streaks table
    try:
        conn.execute("DELETE FROM streaks")
    except Exception:
        pass

    conn.commit()
    return jsonify({'success': True, 'message': 'All data has been reset'})
