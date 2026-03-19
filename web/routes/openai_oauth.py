"""ChatGPT OAuth PKCE flow routes.

The redirect_uri is hardcoded to http://localhost:1455/auth/callback because
that URI is hardcoded in OpenAI's Codex CLI client and is the only URI
accepted by the app registration.

Flow:
  1. GET  /auth/openai/start      → generate PKCE + state, return auth URL as JSON
  2. POST /auth/openai/exchange   → frontend sends {code, state, redirect_uri},
                                    server exchanges code for tokens
  3. GET  /auth/openai/status     → check connection status
  4. POST /auth/openai/disconnect → remove tokens
  5. POST /auth/openai/refresh    → refresh expired access token
"""
import base64
import hashlib
import os
import secrets

import requests
from flask import Blueprint, jsonify, request, session

from .decorators import login_required
from src.infrastructure.database import get_connection

openai_oauth_bp = Blueprint('openai_oauth', __name__, url_prefix='/auth/openai')

_CLIENT_ID = 'app_EMoamEEZ73f0CkXaXp7hrann'
_TOKEN_URL = 'https://auth.openai.com/oauth/token'
_AUTH_URL = 'https://auth.openai.com/oauth/authorize'

# This URI is hardcoded in OpenAI's Codex CLI client — do not change.
_REDIRECT_URI = 'http://localhost:1455/auth/callback'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _b64url(data: bytes) -> str:
    """Base64url-encode bytes with NO padding (RFC 7636 §4.1)."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _make_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256.

    code_verifier  : 64 random bytes → base64url (no padding)
    code_challenge : SHA-256(verifier) → base64url (no padding)
    """
    verifier = _b64url(os.urandom(64))
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    challenge = _b64url(digest)
    return verifier, challenge


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


def _decode_jwt_payload(token: str) -> dict:
    """Decode the payload section of a JWT without verifying the signature."""
    try:
        parts = token.split('.')
        if len(parts) < 2:
            return {}
        # Add padding back before decoding (JWT strips it)
        payload_b64 = parts[1] + '=='
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        import json
        return json.loads(payload_bytes)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@openai_oauth_bp.route('/start')
@login_required
def start():
    """Generate PKCE values and return the OpenAI authorization URL as JSON.

    The frontend is responsible for opening the URL (e.g. in a new tab).
    The redirect_uri is always http://localhost:1455/auth/callback.

    Response:
        {
            "auth_url": "https://auth.openai.com/oauth/authorize?..."
        }
    """
    verifier, challenge = _make_pkce_pair()
    state = _b64url(secrets.token_bytes(32))

    session['openai_oauth_verifier'] = verifier
    session['openai_oauth_state'] = state

    params = '&'.join([
        f"response_type=code",
        f"client_id={_CLIENT_ID}",
        f"redirect_uri={requests.utils.quote(_REDIRECT_URI, safe='')}",
        f"scope={requests.utils.quote('openid profile email offline_access', safe='')}",
        f"code_challenge={challenge}",
        f"code_challenge_method=S256",
        f"state={state}",
        f"codex_cli_simplified_flow=true",
        f"originator=codex_cli_rs",
    ])

    auth_url = f"{_AUTH_URL}?{params}"
    return jsonify({'auth_url': auth_url})


@openai_oauth_bp.route('/exchange', methods=['POST'])
@login_required
def exchange():
    """Exchange an authorization code for tokens.

    Expects JSON body:
        {
            "code":         "<auth code from redirect>",
            "state":        "<state param from redirect>",
            "redirect_uri": "<must be http://localhost:1455/auth/callback>"
        }

    The redirect_uri field in the body is accepted for forward-compatibility but
    is always overridden with the hardcoded _REDIRECT_URI on the server side.
    """
    data = request.json or {}
    code = data.get('code', '').strip()
    state = data.get('state', '').strip()

    if not code:
        return jsonify({'success': False, 'error': 'Missing authorization code'}), 400

    # Validate state
    expected_state = session.pop('openai_oauth_state', None)
    if expected_state and state != expected_state:
        return jsonify({'success': False, 'error': 'State mismatch — possible CSRF'}), 400

    verifier = session.pop('openai_oauth_verifier', '')
    if not verifier:
        return jsonify({'success': False, 'error': 'Missing PKCE verifier — start the flow again'}), 400

    # Exchange code for tokens.
    # MUST use application/x-www-form-urlencoded, NOT JSON.
    # MUST send code_verifier (the raw verifier), NOT the challenge.
    try:
        resp = requests.post(
            _TOKEN_URL,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': _REDIRECT_URI,
                'client_id': _CLIENT_ID,
                'code_verifier': verifier,
            },
            timeout=15,
        )
        resp.raise_for_status()
        token_data = resp.json()
    except requests.HTTPError as exc:
        try:
            from .app_log import log_event
            log_event('error', 'openai_oauth', f'Token exchange HTTP error: {exc} — {exc.response.text if exc.response else ""}')
        except Exception:
            pass
        return jsonify({'success': False, 'error': 'Token exchange failed'}), 502
    except Exception as exc:
        try:
            from .app_log import log_event
            log_event('error', 'openai_oauth', f'Token exchange failed: {str(exc)}')
        except Exception:
            pass
        return jsonify({'success': False, 'error': 'Token exchange failed'}), 502

    access_token = token_data.get('access_token', '')
    refresh_token = token_data.get('refresh_token', '')

    if not access_token:
        try:
            from .app_log import log_event
            log_event('error', 'openai_oauth', 'Token exchange succeeded but no access_token in response')
        except Exception:
            pass
        return jsonify({'success': False, 'error': 'No access token in response'}), 502

    # Extract chatgpt_account_id from the JWT payload (best-effort).
    payload = _decode_jwt_payload(access_token)
    account_id = payload.get('chatgpt_account_id') or payload.get('sub', '')

    conn = get_connection()
    _upsert_setting(conn, 'openai_oauth_token', access_token)
    if refresh_token:
        _upsert_setting(conn, 'openai_oauth_refresh', refresh_token)
    conn.commit()

    try:
        from .app_log import log_event
        log_event('info', 'openai_oauth', 'OAuth connection established successfully')
    except Exception:
        pass

    return jsonify({
        'success': True,
        'account_id': account_id,
    })


@openai_oauth_bp.route('/status')
@login_required
def status():
    """Return whether the ChatGPT OAuth connection is active."""
    token = _get_setting('openai_oauth_token')
    connected = bool(token)
    return jsonify({'connected': connected, 'has_token': bool(token)})


@openai_oauth_bp.route('/disconnect', methods=['POST'])
@login_required
def disconnect():
    """Remove stored OAuth tokens."""
    conn = get_connection()
    _delete_setting(conn, 'openai_oauth_token')
    _delete_setting(conn, 'openai_oauth_refresh')
    conn.commit()

    try:
        from .app_log import log_event
        log_event('info', 'openai_oauth', 'OAuth tokens removed')
    except Exception:
        pass

    return jsonify({'success': True, 'message': 'ChatGPT OAuth disconnected'})


@openai_oauth_bp.route('/refresh', methods=['POST'])
@login_required
def refresh():
    """Use the stored refresh token to obtain a new access token."""
    refresh_token = _get_setting('openai_oauth_refresh')
    if not refresh_token:
        return jsonify({'success': False, 'error': 'No refresh token stored'}), 400

    try:
        resp = requests.post(
            _TOKEN_URL,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': _CLIENT_ID,
            },
            timeout=15,
        )
        resp.raise_for_status()
        token_data = resp.json()
    except requests.HTTPError as exc:
        try:
            from .app_log import log_event
            log_event('error', 'openai_oauth', f'Token refresh HTTP error: {exc}')
        except Exception:
            pass
        return jsonify({'success': False, 'error': 'Token refresh failed'}), 502
    except Exception as exc:
        try:
            from .app_log import log_event
            log_event('error', 'openai_oauth', f'Token refresh failed: {str(exc)}')
        except Exception:
            pass
        return jsonify({'success': False, 'error': 'Token refresh failed'}), 502

    new_access_token = token_data.get('access_token', '')
    new_refresh_token = token_data.get('refresh_token', '')

    if not new_access_token:
        return jsonify({'success': False, 'error': 'No access token in refresh response'}), 502

    conn = get_connection()
    _upsert_setting(conn, 'openai_oauth_token', new_access_token)
    if new_refresh_token:
        _upsert_setting(conn, 'openai_oauth_refresh', new_refresh_token)
    conn.commit()

    try:
        from .app_log import log_event
        log_event('info', 'openai_oauth', 'OAuth token refreshed successfully')
    except Exception:
        pass

    return jsonify({'success': True})
