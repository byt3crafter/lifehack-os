"""Route decorators for authentication."""
from functools import wraps
from flask import session, request, redirect, url_for, jsonify

API_KEY = 'lifehack_openclaw_2026'


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


def api_key_required(f):
    """Require valid API key for OpenClaw endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if key != API_KEY:
            return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated
