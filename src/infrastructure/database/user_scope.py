"""User-scoped database helpers.

Provides standardised functions for user-isolated queries so that every
module follows the same pattern and no endpoint can accidentally leak
data across users.

Usage in routes::

    from src.infrastructure.database.user_scope import get_user_setting, set_user_setting
    from web.routes.decorators import current_user_id

    uid = current_user_id()
    goal = get_user_setting(conn, uid, 'calorie_goal', '2000')

Usage convention for new tables:
    Every new table that stores user-specific data MUST include a
    ``user_id INTEGER REFERENCES users(id)`` column.  All SELECT queries
    must include ``WHERE user_id = ?`` and all INSERT queries must supply
    the user_id value.
"""
import json
from typing import Any, Optional


def get_user_setting(conn, user_id: int, key: str, default: str = '') -> str:
    """Get a per-user setting, falling back to the global app_settings default."""
    row = conn.execute(
        "SELECT value FROM user_settings WHERE user_id = ? AND key = ?",
        (user_id, key),
    ).fetchone()
    if row:
        return row['value']
    # Fallback to global
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    return row['value'] if row else default


def set_user_setting(conn, user_id: int, key: str, value: str) -> None:
    """Set a per-user setting (upsert)."""
    conn.execute(
        """INSERT INTO user_settings (user_id, key, value, updated_at)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(user_id, key) DO UPDATE
           SET value = excluded.value, updated_at = excluded.updated_at""",
        (user_id, key, value),
    )
    conn.commit()


def get_user_integration(conn, user_id: int, name: str) -> Optional[dict]:
    """Get a user's integration config. Returns None if not configured."""
    row = conn.execute(
        "SELECT * FROM user_integrations WHERE user_id = ? AND integration_name = ?",
        (user_id, name),
    ).fetchone()
    if not row:
        return None
    try:
        config = json.loads(row['config_json'] or '{}')
    except (json.JSONDecodeError, TypeError):
        config = {}
    return {
        'id': row['id'],
        'enabled': bool(row['enabled']),
        'config': config,
    }


def set_user_integration(conn, user_id: int, name: str, enabled: bool, config: dict) -> None:
    """Upsert a user's integration config."""
    conn.execute(
        """INSERT INTO user_integrations (user_id, integration_name, enabled, config_json, updated_at)
           VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(user_id, integration_name) DO UPDATE
           SET enabled = excluded.enabled, config_json = excluded.config_json,
               updated_at = excluded.updated_at""",
        (user_id, name, 1 if enabled else 0, json.dumps(config)),
    )
    conn.commit()


def ensure_user_stats(conn, user_id: int) -> None:
    """Ensure a user_stats row exists for this user."""
    conn.execute(
        "INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)",
        (user_id,),
    )
    conn.commit()
