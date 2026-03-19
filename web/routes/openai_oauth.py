"""ChatGPT OAuth PKCE flow routes."""
import base64
import hashlib
import os
import secrets

import requests
from flask import Blueprint, jsonify, redirect, request, session

from .decorators import login_required
from src.infrastructure.database import get_connection

openai_oauth_bp = Blueprint('openai_oauth', __name__, url_prefix='/auth/openai')

_CLIENT_ID = 'app_EMoamEEZ73f0CkXaXp7hrann'
_TOKEN_URL = 'https://auth.openai.com/oauth/token'
_AUTH_URL = 'https://auth.openai.com/oauth/authorize'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _upsert_setting(conn, key: str, value: str) -> None:
    conn.execute(
        """INSERT INTO app_settings (key, value, updated_at)
           VALUES (?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                          updated_at = excluded.updated_at""",
        (key, value),
    )


def _get_setting(key: str) -> str:
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
        if row and row['value']:
            return row['value']
    except Exception:
        pass
    return ''


def _delete_setting(conn, key: str) -> None:
    conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))


def _build_callback_url() -> str:
    """Build the absolute callback URL from the current request context."""
    host_url = request.host_url.rstrip('/')
    return f"{host_url}/auth/openai/callback"


def _make_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    # RFC 7636: verifier must be 43-128 unreserved ASCII chars
    verifier = base64.urlsafe_b64encode(os.urandom(64)).rstrip(b'=').decode('ascii')
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')
    return verifier, challenge


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@openai_oauth_bp.route('/start')
@login_required
def start():
    """Initiate the OAuth PKCE flow — redirect the browser to OpenAI's auth page."""
    verifier, challenge = _make_pkce_pair()
    state = secrets.token_urlsafe(24)

    session['openai_oauth_verifier'] = verifier
    session['openai_oauth_state'] = state

    callback_url = _build_callback_url()

    params = (
        f"client_id={_CLIENT_ID}"
        f"&redirect_uri={requests.utils.quote(callback_url, safe='')}"
        f"&response_type=code"
        f"&scope=openai.chat"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
        f"&state={state}"
    )
    return redirect(f"{_AUTH_URL}?{params}")


@openai_oauth_bp.route('/callback')
@login_required
def callback():
    """Handle the redirect from OpenAI after the user authorises the app."""
    code = request.args.get('code', '')
    state = request.args.get('state', '')

    if not code:
        return redirect('/#settings?error=oauth_no_code')

    # State validation (best-effort — session may have been cleared)
    expected_state = session.pop('openai_oauth_state', None)
    if expected_state and state != expected_state:
        return redirect('/#settings?error=oauth_state_mismatch')

    verifier = session.pop('openai_oauth_verifier', '')
    if not verifier:
        return redirect('/#settings?error=oauth_missing_verifier')

    callback_url = _build_callback_url()

    try:
        resp = requests.post(
            _TOKEN_URL,
            headers={'Content-Type': 'application/json'},
            json={
                'grant_type': 'authorization_code',
                'client_id': _CLIENT_ID,
                'code': code,
                'redirect_uri': callback_url,
                'code_verifier': verifier,
            },
            timeout=15,
        )
        resp.raise_for_status()
        token_data = resp.json()
    except Exception as exc:
        # Log server-side; surface a generic error to the browser
        print(f"[openai_oauth] token exchange failed: {exc}")
        return redirect('/#settings?error=oauth_token_exchange_failed')

    access_token = token_data.get('access_token', '')
    refresh_token = token_data.get('refresh_token', '')

    if not access_token:
        return redirect('/#settings?error=oauth_no_access_token')

    conn = get_connection()
    _upsert_setting(conn, 'openai_oauth_token', access_token)
    if refresh_token:
        _upsert_setting(conn, 'openai_oauth_refresh', refresh_token)
    _upsert_setting(conn, 'ai_provider', 'chatgpt_oauth')
    conn.commit()

    return redirect('/#settings')


@openai_oauth_bp.route('/status')
@login_required
def status():
    """Return whether the ChatGPT OAuth connection is active."""
    token = _get_setting('openai_oauth_token')
    provider = _get_setting('ai_provider')
    connected = bool(token) and provider == 'chatgpt_oauth'
    return jsonify({'connected': connected, 'has_token': bool(token)})


@openai_oauth_bp.route('/disconnect', methods=['POST'])
@login_required
def disconnect():
    """Remove stored OAuth tokens and revert the provider to 'none'."""
    conn = get_connection()
    _delete_setting(conn, 'openai_oauth_token')
    _delete_setting(conn, 'openai_oauth_refresh')
    # If the active provider was chatgpt_oauth, reset it
    provider = _get_setting('ai_provider')
    if provider == 'chatgpt_oauth':
        _upsert_setting(conn, 'ai_provider', 'none')
    conn.commit()
    return jsonify({'success': True, 'message': 'ChatGPT OAuth disconnected'})
