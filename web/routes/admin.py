"""Admin panel routes for LifeHack OS."""
import os
import secrets
import sys
import platform
from datetime import datetime, timezone
from pathlib import Path

import flask
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
)
from werkzeug.security import check_password_hash, generate_password_hash

from src.infrastructure.database import get_connection
from src.infrastructure.ai.usage import PLAN_LIMITS

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Module-level server start time for uptime calculation
_SERVER_START = datetime.now(timezone.utc)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_admin() -> bool:
    return bool(session.get('is_admin') and session.get('user'))


def _require_admin():
    """Return a redirect response if not admin, else None."""
    if not _is_admin():
        return redirect(url_for('admin.admin_login'))
    return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _db_path() -> Path:
    return Path(__file__).parent.parent.parent / 'data' / 'lifehack.db'


def _db_size_mb() -> float:
    try:
        return round(_db_path().stat().st_size / (1024 * 1024), 3)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    # Already logged in as admin — go straight to dashboard
    if _is_admin():
        return redirect(url_for('admin.admin_dashboard'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')

        conn = get_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user and user['is_admin']:
            stored = user['password_hash']
            # Support both legacy SHA-256 and werkzeug hashes
            import hashlib
            if len(stored) == 64 and all(c in '0123456789abcdef' for c in stored):
                valid = hashlib.sha256(password.encode()).hexdigest() == stored
            else:
                valid = check_password_hash(stored, password)

            if valid:
                conn.execute(
                    "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                    (user['id'],),
                )
                conn.commit()
                session['user'] = user['username']
                session['user_id'] = user['id']
                session['is_admin'] = True
                session.permanent = True
                return redirect(url_for('admin.admin_dashboard'))

        error = 'Invalid credentials or insufficient privileges'

    return render_template('admin_login.html', error=error)


@admin_bp.route('/logout', methods=['POST'])
def admin_logout():
    session.clear()
    return redirect(url_for('admin.admin_login'))


# ---------------------------------------------------------------------------
# Dashboard (HTML page)
# ---------------------------------------------------------------------------

@admin_bp.route('/')
def admin_dashboard():
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()

    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    today = _now_utc().date().isoformat()
    active_today = conn.execute(
        "SELECT COUNT(*) FROM users WHERE DATE(last_login) = ?", (today,)
    ).fetchone()[0]

    def _count(table: str) -> int:
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except Exception:
            return 0

    total_habits = _count('habits')
    total_food_logs = _count('food_logs')
    total_journal_entries = _count('journal_entries')
    total_notes = _count('notes')

    db_size = _db_size_mb()

    try:
        recent_errors = conn.execute(
            "SELECT id, timestamp, source, message FROM app_log WHERE level = 'error' "
            "ORDER BY timestamp DESC LIMIT 10"
        ).fetchall()
        recent_errors = [dict(r) for r in recent_errors]
    except Exception:
        recent_errors = []

    return render_template(
        'admin.html',
        total_users=total_users,
        active_today=active_today,
        total_habits=total_habits,
        total_food_logs=total_food_logs,
        total_journal_entries=total_journal_entries,
        total_notes=total_notes,
        db_size=db_size,
        recent_errors=recent_errors,
    )


# ---------------------------------------------------------------------------
# Users API
# ---------------------------------------------------------------------------

@admin_bp.route('/users')
def admin_list_users():
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()
    rows = conn.execute(
        """SELECT
               u.id, u.username, u.display_name, u.is_admin,
               COALESCE(u.byok_enabled, 0) as byok_enabled,
               u.created_at, u.last_login,
               p.email,
               s.total_xp as xp, s.level
           FROM users u
           LEFT JOIN user_profiles p ON p.user_id = u.id
           LEFT JOIN user_stats s ON s.user_id = u.id
           ORDER BY u.id"""
    ).fetchall()

    users = []
    for r in rows:
        try:
            users.append(dict(r))
        except Exception:
            users.append({'id': r[0], 'username': r[1], 'display_name': r[2], 'is_admin': r[3], 'created_at': r[4], 'last_login': r[5]})
    return jsonify(users)


@admin_bp.route('/users/<int:user_id>/toggle-admin', methods=['POST'])
def admin_toggle_admin(user_id: int):
    guard = _require_admin()
    if guard:
        return guard

    if user_id == session.get('user_id'):
        return jsonify({'error': 'Cannot change your own admin status'}), 400

    conn = get_connection()
    user = conn.execute("SELECT id, is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    new_flag = 0 if user['is_admin'] else 1
    conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_flag, user_id))
    conn.commit()
    return jsonify({'id': user_id, 'is_admin': bool(new_flag)})


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
def admin_reset_password(user_id: int):
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()
    user = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    token = secrets.token_urlsafe(32)
    expires_at = (_now_utc().replace(microsecond=0).isoformat())

    # expires 24 h from now
    from datetime import timedelta
    expires_at = (_now_utc() + timedelta(hours=24)).isoformat()

    admin_uid = session.get('user_id')
    conn.execute(
        """INSERT INTO password_reset_tokens (user_id, token, expires_at, created_by)
           VALUES (?, ?, ?, ?)""",
        (user_id, token, expires_at, admin_uid),
    )
    conn.commit()

    base_url = request.host_url.rstrip('/')
    reset_url = f"{base_url}/reset-password?token={token}"
    return jsonify({'token': token, 'url': reset_url, 'expires_at': expires_at})


@admin_bp.route('/users/<int:user_id>/disable', methods=['POST'])
def admin_disable_user(user_id: int):
    """Disable = delete the user for now."""
    guard = _require_admin()
    if guard:
        return guard

    if user_id == session.get('user_id'):
        return jsonify({'error': 'Cannot delete your own account'}), 400

    conn = get_connection()
    user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    return jsonify({'status': 'deleted', 'id': user_id})


@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
def admin_delete_user(user_id: int):
    guard = _require_admin()
    if guard:
        return guard

    if user_id == session.get('user_id'):
        return jsonify({'error': 'Cannot delete your own account'}), 400

    conn = get_connection()
    user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    return '', 204


# ---------------------------------------------------------------------------
# Invites API
# ---------------------------------------------------------------------------

@admin_bp.route('/invites')
def admin_list_invites():
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()
    rows = conn.execute(
        """SELECT
               i.id, i.code, i.max_uses, i.use_count, i.expires_at, i.created_at,
               u.username AS creator_username
           FROM invite_codes i
           LEFT JOIN users u ON u.id = i.created_by
           ORDER BY i.created_at DESC"""
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@admin_bp.route('/invites/<int:invite_id>', methods=['DELETE'])
def admin_delete_invite(invite_id: int):
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()
    invite = conn.execute("SELECT id FROM invite_codes WHERE id = ?", (invite_id,)).fetchone()
    if not invite:
        return jsonify({'error': 'Invite not found'}), 404

    conn.execute("DELETE FROM invite_codes WHERE id = ?", (invite_id,))
    conn.commit()
    return '', 204


# ---------------------------------------------------------------------------
# API Keys API
# ---------------------------------------------------------------------------

@admin_bp.route('/api-keys')
def admin_list_api_keys():
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()
    rows = conn.execute(
        """SELECT
               k.id, k.key_id, k.name, k.scopes, k.last_used_at, k.created_at,
               k.expires_at, k.active,
               u.username AS owner_username
           FROM user_api_keys k
           LEFT JOIN users u ON u.id = k.user_id
           ORDER BY k.created_at DESC"""
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@admin_bp.route('/api-keys/<int:key_id>', methods=['DELETE'])
def admin_revoke_api_key(key_id: int):
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()
    key = conn.execute("SELECT id FROM user_api_keys WHERE id = ?", (key_id,)).fetchone()
    if not key:
        return jsonify({'error': 'API key not found'}), 404

    conn.execute("DELETE FROM user_api_keys WHERE id = ?", (key_id,))
    conn.commit()
    return '', 204


# ---------------------------------------------------------------------------
# Logs API
# ---------------------------------------------------------------------------

@admin_bp.route('/logs')
def admin_logs():
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, timestamp, level, source, message, detail, request_path, request_method "
            "FROM app_log ORDER BY timestamp DESC LIMIT 50"
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# System API
# ---------------------------------------------------------------------------

@admin_bp.route('/system')
def admin_system():
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()

    try:
        total_tables = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
    except Exception:
        total_tables = 0

    uptime_seconds = int((_now_utc() - _SERVER_START).total_seconds())
    uptime_str = _format_uptime(uptime_seconds)

    disk_usage = None
    try:
        import shutil
        du = shutil.disk_usage('/')
        disk_usage = {
            'total_gb': round(du.total / (1024 ** 3), 2),
            'used_gb': round(du.used / (1024 ** 3), 2),
            'free_gb': round(du.free / (1024 ** 3), 2),
            'percent_used': round(du.used / du.total * 100, 1),
        }
    except Exception:
        pass

    return jsonify({
        'python_version': sys.version.split(' ')[0],
        'flask_version': flask.__version__,
        'db_size_mb': _db_size_mb(),
        'total_tables': total_tables,
        'uptime': uptime_str,
        'server_start': _SERVER_START.isoformat(),
        'disk_usage': disk_usage,
        'platform': platform.system(),
    })


# ---------------------------------------------------------------------------
# Tier 2: Module Usage, AI Usage, Storage
# ---------------------------------------------------------------------------

@admin_bp.route('/module-usage')
def admin_module_usage():
    """Per-module usage stats across all users."""
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()
    modules = {}
    try:
        tables = {
            'habits': 'habits', 'food': 'food_logs', 'fasting': 'fasting_logs',
            'journal': 'journal_entries', 'books': 'books', 'notes': 'notes',
            'challenges': 'challenges', 'contacts': 'contacts', 'finance': 'finance_log',
            'wellness_water': 'water_logs', 'wellness_sleep': 'sleep_logs',
            'deep_work': 'deep_work_sessions', 'discover': 'wishlist',
            'subscriptions': 'subscriptions', 'income': 'income_entries',
        }
        for name, table in tables.items():
            try:
                row = conn.execute(f"SELECT COUNT(*) as cnt, COUNT(DISTINCT user_id) as users FROM {table}").fetchone()
                modules[name] = {'entries': row['cnt'], 'users': row['users']}
            except Exception:
                modules[name] = {'entries': 0, 'users': 0}
    except Exception:
        pass

    return jsonify(modules)


@admin_bp.route('/ai-usage')
def admin_ai_usage():
    """AI provider usage stats — tokens, costs, calls per provider."""
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()
    try:
        # Per-provider stats
        providers = conn.execute(
            """SELECT provider, model,
                      COUNT(*) as calls,
                      SUM(total_tokens) as tokens,
                      SUM(cost_usd) as cost,
                      SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures,
                      AVG(duration_ms) as avg_ms
               FROM ai_usage_log
               GROUP BY provider, model
               ORDER BY calls DESC"""
        ).fetchall()

        # Recent calls
        recent = conn.execute(
            """SELECT timestamp, provider, model, action, total_tokens, cost_usd, success, duration_ms
               FROM ai_usage_log
               ORDER BY timestamp DESC LIMIT 20"""
        ).fetchall()

        # Daily totals (last 7 days)
        daily = conn.execute(
            """SELECT date(timestamp) as day, COUNT(*) as calls, SUM(total_tokens) as tokens, SUM(cost_usd) as cost
               FROM ai_usage_log
               WHERE timestamp >= date('now', '-7 days')
               GROUP BY day ORDER BY day"""
        ).fetchall()

        return jsonify({
            'providers': [dict(r) for r in providers],
            'recent': [dict(r) for r in recent],
            'daily': [dict(r) for r in daily],
        })
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@admin_bp.route('/storage')
def admin_storage():
    """Storage usage — uploads per directory, total size."""
    guard = _require_admin()
    if guard:
        return guard

    import os
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'uploads')
    dirs = {}
    total_size = 0
    total_files = 0

    if os.path.exists(upload_dir):
        for dirpath, dirnames, filenames in os.walk(upload_dir):
            rel = os.path.relpath(dirpath, upload_dir)
            if rel == '.':
                rel = 'root'
            dir_size = sum(os.path.getsize(os.path.join(dirpath, f)) for f in filenames)
            dirs[rel] = {'files': len(filenames), 'size_mb': round(dir_size / (1024 * 1024), 2)}
            total_size += dir_size
            total_files += len(filenames)

    return jsonify({
        'total_files': total_files,
        'total_size_mb': round(total_size / (1024 * 1024), 2),
        'directories': dirs,
    })


# ---------------------------------------------------------------------------
# Tier 3: Announcements, Backup
# ---------------------------------------------------------------------------

@admin_bp.route('/announcements', methods=['GET'])
def admin_get_announcements():
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT key, value FROM app_settings WHERE key LIKE 'announcement_%' ORDER BY key DESC"
        ).fetchall()
        announcements = []
        for r in rows:
            announcements.append({'key': r['key'], 'message': r['value']})
        return jsonify(announcements)
    except Exception:
        return jsonify([])


@admin_bp.route('/announcements', methods=['POST'])
def admin_post_announcement():
    guard = _require_admin()
    if guard:
        return guard

    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'Message required'}), 400

    conn = get_connection()
    key = f"announcement_{_now_utc().strftime('%Y%m%d%H%M%S')}"
    conn.execute(
        """INSERT INTO app_settings (key, value, updated_at)
           VALUES (?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
        (key, message),
    )
    conn.commit()
    return jsonify({'success': True, 'key': key})


@admin_bp.route('/announcements/<key>', methods=['DELETE'])
def admin_delete_announcement(key: str):
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()
    conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
    conn.commit()
    return '', 204


# ---------------------------------------------------------------------------
# AI Configuration (global provider setup)
# ---------------------------------------------------------------------------

# All AI-related app_settings keys
_AI_SETTINGS_KEYS = [
    'ai_provider', 'ai_provider_default', 'ai_provider_food', 'ai_provider_habits',
    'ai_provider_insights', 'ai_provider_reports',
    'ai_openai_key', 'ai_openai_url', 'ai_openai_model',
    'ai_anthropic_key', 'ai_anthropic_model',
    'ai_minimax_key', 'ai_minimax_model',
    'ai_ollama_url', 'ai_ollama_model',
    'ai_chatgpt_model', 'openai_oauth_token',
]

_SENSITIVE_AI_KEYS = {'ai_openai_key', 'ai_anthropic_key', 'ai_minimax_key', 'openai_oauth_token'}


@admin_bp.route('/ai-config')
def admin_get_ai_config():
    """Get all global AI provider settings."""
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()
    config = {}
    for key in _AI_SETTINGS_KEYS:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        val = row['value'] if row else ''
        # Mask sensitive values
        if key in _SENSITIVE_AI_KEYS and val:
            config[key] = val[:8] + '••••••••' if len(val) > 8 else '••••••••'
            config[key + '_set'] = True
        else:
            config[key] = val
    return jsonify(config)


@admin_bp.route('/ai-config', methods=['POST'])
def admin_save_ai_config():
    """Save global AI provider settings."""
    guard = _require_admin()
    if guard:
        return guard

    data = request.get_json(silent=True) or {}
    conn = get_connection()

    for key in _AI_SETTINGS_KEYS:
        if key in data:
            val = data[key]
            # Don't overwrite with masked value
            if key in _SENSITIVE_AI_KEYS and '••••' in str(val):
                continue
            if val:
                conn.execute(
                    """INSERT INTO app_settings (key, value, updated_at)
                       VALUES (?, ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                    (key, str(val)),
                )
            else:
                conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
    conn.commit()
    return jsonify({'success': True})


@admin_bp.route('/ai-config/test', methods=['POST'])
def admin_test_ai():
    """Test the current AI configuration."""
    guard = _require_admin()
    if guard:
        return guard

    try:
        from src.infrastructure.ai import get_ai_provider
        provider = get_ai_provider('default')
        available = provider.is_available()
        provider_name = type(provider).__name__.replace('Provider', '')
        model = getattr(provider, 'model', 'unknown')
        return jsonify({
            'success': True,
            'available': available,
            'provider': provider_name,
            'model': model,
        })
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)})


@admin_bp.route('/backup')
def admin_backup():
    """Download the entire SQLite database as a backup."""
    guard = _require_admin()
    if guard:
        return guard

    from flask import send_file
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'lifehack.db')
    if not os.path.exists(db_path):
        return jsonify({'error': 'Database not found'}), 404

    return send_file(
        db_path,
        as_attachment=True,
        download_name=f"lifehack_backup_{_now_utc().strftime('%Y%m%d_%H%M%S')}.db",
        mimetype='application/x-sqlite3',
    )


# ---------------------------------------------------------------------------
# Plan management & per-user AI cost breakdown
# ---------------------------------------------------------------------------

@admin_bp.route('/users/<int:user_id>/plan', methods=['POST'])
def admin_set_plan(user_id: int):
    """Set a user's plan (free / personal / pro / unlimited)."""
    guard = _require_admin()
    if guard:
        return guard

    data = request.get_json(silent=True) or {}
    plan = data.get('plan', 'free')
    if plan not in PLAN_LIMITS:
        return jsonify({'error': f"Invalid plan '{plan}'. Valid: {list(PLAN_LIMITS)}"}), 400

    conn = get_connection()
    user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    conn.execute("UPDATE users SET plan = ? WHERE id = ?", (plan, user_id))
    conn.commit()
    return jsonify({'success': True, 'user_id': user_id, 'plan': plan})


@admin_bp.route('/users/<int:user_id>/byok', methods=['POST'])
def admin_toggle_byok(user_id: int):
    """Toggle BYOK (bring-your-own-key) for a user."""
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()
    user = conn.execute(
        "SELECT id, byok_enabled FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    new_val = 0 if user['byok_enabled'] else 1
    conn.execute("UPDATE users SET byok_enabled = ? WHERE id = ?", (new_val, user_id))
    conn.commit()
    return jsonify({'success': True, 'user_id': user_id, 'byok_enabled': bool(new_val)})


@admin_bp.route('/user-costs')
def admin_user_costs():
    """Per-user AI cost and usage breakdown."""
    guard = _require_admin()
    if guard:
        return guard

    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT
                u.id, u.username, u.display_name,
                COALESCE(u.plan, 'free') as plan,
                COALESCE(u.byok_enabled, 0) as byok_enabled,
                COUNT(a.id) as total_calls,
                COALESCE(SUM(a.total_tokens), 0) as total_tokens,
                COALESCE(SUM(a.cost_usd), 0) as total_cost,
                COUNT(CASE WHEN date(a.timestamp) = date('now') THEN 1 END) as today_calls
            FROM users u
            LEFT JOIN ai_usage_log a ON a.user_id = u.id
            GROUP BY u.id
            ORDER BY total_cost DESC
        """).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


def _format_uptime(seconds: int) -> str:
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return ' '.join(parts)
