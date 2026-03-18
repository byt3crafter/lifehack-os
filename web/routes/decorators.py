"""Route decorators for authentication."""
import os
from functools import wraps
from flask import session, request, redirect, url_for, jsonify


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
    """Require user to be logged in."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
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
