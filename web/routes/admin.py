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
               u.created_at, u.last_login,
               p.email,
               s.xp, s.level
           FROM users u
           LEFT JOIN user_profiles p ON p.user_id = u.id
           LEFT JOIN user_stats s ON s.user_id = u.id
           ORDER BY u.id"""
    ).fetchall()
    return jsonify([dict(r) for r in rows])


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
