"""Route decorators for authentication and user scoping.

Every authenticated route should call ``current_user_id()`` to obtain the
logged-in user's ID and pass it to all database queries so that user data
is fully isolated.
"""
import os
from functools import wraps
from flask import g, session, request, redirect, url_for, jsonify
from werkzeug.security import check_password_hash


def _validate_user_api_key(key_id: str, key_secret: str) -> int | None:
    """Validate a user API key pair.

    Returns the user_id if valid and active, None otherwise.
    Also updates last_used_at on success.
    """
    try:
        from src.infrastructure.database import get_connection
        from datetime import datetime, timezone
        conn = get_connection()
        row = conn.execute(
            """SELECT id, user_id, key_secret_hash, active, expires_at
               FROM user_api_keys
               WHERE key_id = ?""",
            (key_id,),
        ).fetchone()

        if not row:
            return None
        if not row['active']:
            return None

        # Check expiry
        if row['expires_at']:
            expires_at = datetime.fromisoformat(row['expires_at'])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                return None

        # Constant-time hash comparison via werkzeug
        if not check_password_hash(row['key_secret_hash'], key_secret):
            return None

        # Update last_used_at (best-effort, do not block on failure)
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE user_api_keys SET last_used_at = ? WHERE id = ?",
                (now, row['id']),
            )
            conn.commit()
        except Exception:
            pass

        return int(row['user_id'])
    except Exception:
        return None


def current_user_id() -> int:
    """Return the authenticated user's database ID.

    Checks API key auth (g.api_user_id) first, then falls back to session.
    Must only be called inside a ``@login_required`` route.
    """
    # API key auth takes priority
    api_uid = getattr(g, 'api_user_id', None)
    if api_uid is not None:
        return int(api_uid)
    # Session auth
    uid = session.get('user_id')
    if uid is None:
        raise RuntimeError('current_user_id() called outside authenticated context')
    return int(uid)


def _get_api_key() -> str:
    """Return the configured OpenClaw API key.

    Resolution order:
    1. ``openclaw_api_key`` row in the app_settings table (set via the UI).
    2. ``LIFEHACK_API_KEY`` environment variable (legacy / Docker fallback).
    """
    try:
        from src.infrastructure.database import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'openclaw_api_key'"
        ).fetchone()
        if row and row['value']:
            return row['value']
    except Exception:
        pass
    return os.environ.get('LIFEHACK_API_KEY', '')


def login_required(f):
    """Require user to be logged in via session OR a valid user API key.

    Accepts:
    - Session cookie (existing browser auth)
    - Authorization: Bearer <key_id>:<key_secret> header
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # --- Check for user API key in Authorization header ---
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            if ':' in token:
                key_id, key_secret = token.split(':', 1)
                user_id = _validate_user_api_key(key_id, key_secret)
                if user_id is not None:
                    g.api_user_id = user_id
                    return f(*args, **kwargs)
                # Key was provided but invalid — reject immediately, do not
                # fall through to session so a bad key never silently succeeds.
                return jsonify({'error': 'Invalid or expired API key'}), 401

        # --- Fall back to session auth ---
        if 'user' not in session and not getattr(g, 'api_user_id', None):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Require user to be logged in AND have admin privileges."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('auth.login'))
        if not session.get('is_admin'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Forbidden'}), 403
            return redirect(url_for('auth.index'))
        return f(*args, **kwargs)
    return decorated


def api_key_required(f):
    """Require valid API key for OpenClaw endpoints.

    The expected key is resolved at request time so that changes made through
    the Settings UI take effect without a server restart.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key') or request.args.get('api_key')
        expected = _get_api_key()
        if not expected or key != expected:
            return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated
