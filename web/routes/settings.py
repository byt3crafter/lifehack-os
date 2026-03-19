"""App settings routes — configure API keys and global preferences from the UI."""
from flask import Blueprint, jsonify, request

from .decorators import login_required, admin_required, current_user_id
from src.infrastructure.database import get_connection
from src.infrastructure.database.user_scope import get_user_setting, set_user_setting

settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')

# Keys that hold sensitive values and should be masked in GET responses
_SENSITIVE_KEYS = {'openclaw_api_key', 'ai_openai_key', 'ai_anthropic_key', 'ai_minimax_key'}

# Per-user setting keys (stored in user_settings, not app_settings)
_USER_SETTING_KEYS = {
    'ai_provider',
    'ai_provider_food',
    'ai_provider_habits',
    'ai_provider_insights',
    'ai_provider_reports',
    'ai_provider_default',
    'ai_openai_key',
    'ai_openai_url',
    'ai_openai_model',
    'ai_ollama_url',
    'ai_ollama_model',
    'ai_anthropic_key',
    'ai_anthropic_model',
    'ai_minimax_key',
    'ai_minimax_model',
    'ai_chatgpt_model',
    'daily_calorie_goal',
}

# Truly global keys (admin-managed, stored in app_settings)
_GLOBAL_SETTING_KEYS = {
    'openclaw_api_key',
}

# All recognised setting keys
_SETTING_KEYS = _USER_SETTING_KEYS | _GLOBAL_SETTING_KEYS

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
    'chat_messages',
]


def _get_global_setting(conn, key: str) -> str:
    """Read a global (app_settings) value."""
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    return row['value'] if row else ''


def _upsert_global_setting(conn, key: str, value: str) -> None:
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
    """Return current settings. Per-user settings come from user_settings; global from app_settings."""
    uid = current_user_id()
    conn = get_connection()

    result = {}
    for key in _SETTING_KEYS:
        if key in _GLOBAL_SETTING_KEYS:
            value = _get_global_setting(conn, key)
        else:
            value = get_user_setting(conn, uid, key, '')

        if key in _SENSITIVE_KEYS and value:
            result[key] = value[:4] + '****' if len(value) > 4 else '****'
        else:
            result[key] = value

    return jsonify(result)


@settings_bp.route('', methods=['POST'])
@login_required
def save_settings():
    """Save settings. Per-user keys go to user_settings; global keys go to app_settings."""
    uid = current_user_id()
    data = request.json or {}
    conn = get_connection()

    saved = []
    for key in _SETTING_KEYS:
        if key not in data:
            continue
        value = str(data[key]).strip()
        # For sensitive fields: if the client sends back a masked value
        # (ending with ****), skip the update to preserve the real value
        if key in _SENSITIVE_KEYS and value.endswith('****'):
            continue

        if key in _GLOBAL_SETTING_KEYS:
            _upsert_global_setting(conn, key, value)
        else:
            set_user_setting(conn, uid, key, value)
        saved.append(key)

    conn.commit()
    return jsonify({'success': True, 'saved': saved})


@settings_bp.route('/reset', methods=['POST'])
@admin_required
def reset_all_data():
    """Delete the current user's data. Does NOT remove users or global app_settings."""
    uid = current_user_id()
    from .app_log import log_event
    log_event('warning', 'settings', f'Data reset by user {uid}')

    conn = get_connection()

    for table in _RESET_TABLES:
        try:
            conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (uid,))
        except Exception:
            # Table may not have user_id column or may not exist yet
            try:
                conn.execute(f"DELETE FROM {table}")
            except Exception:
                pass

    # Reset this user's stats to baseline
    try:
        conn.execute(
            "UPDATE user_stats SET total_xp = 0, level = 1 WHERE user_id = ?", (uid,)
        )
    except Exception:
        pass

    # Clear streaks for this user
    try:
        conn.execute("DELETE FROM streaks WHERE user_id = ?", (uid,))
    except Exception:
        pass

    conn.commit()
    return jsonify({'success': True, 'message': 'All data has been reset'})
