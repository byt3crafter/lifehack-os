"""AI provider test and model-discovery endpoints."""
import requests
from flask import Blueprint, jsonify, request

from .decorators import login_required
from src.infrastructure.database import get_connection

ai_models_bp = Blueprint('ai_models', __name__, url_prefix='/api/ai')

# Hardcoded model lists for providers that do not expose a /models endpoint
_ANTHROPIC_MODELS = [
    'claude-opus-4-20250514',
    'claude-sonnet-4-20250514',
    'claude-haiku-4-5-20251001',
]
_CHATGPT_OAUTH_MODELS = [
    'gpt-4o',
    'gpt-4o-mini',
    'o1',
    'o1-mini',
    'o3-mini',
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _bearer_headers(api_key: str) -> dict:
    return {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }


def _test_openai_compatible(base_url: str, api_key: str) -> tuple[bool, str]:
    """Test an OpenAI-compatible endpoint by fetching /models."""
    try:
        resp = requests.get(
            f"{base_url.rstrip('/')}/models",
            headers=_bearer_headers(api_key),
            timeout=10,
        )
        if resp.status_code == 200:
            return True, ''
        return False, f"HTTP {resp.status_code}"
    except requests.exceptions.ConnectionError:
        return False, 'Connection refused — is the server running?'
    except requests.exceptions.Timeout:
        return False, 'Request timed out'
    except Exception as exc:
        return False, str(exc)


def _test_anthropic(api_key: str) -> tuple[bool, str]:
    """Test Anthropic by sending a minimal messages request."""
    try:
        resp = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'claude-haiku-4-5-20251001',
                'max_tokens': 1,
                'messages': [{'role': 'user', 'content': 'hi'}],
            },
            timeout=15,
        )
        # 200 means success; 401/403 means bad key
        if resp.status_code in (200, 400):
            # 400 can happen for bad params but that means auth worked
            return True, ''
        return False, f"HTTP {resp.status_code}"
    except requests.exceptions.Timeout:
        return False, 'Request timed out'
    except Exception as exc:
        return False, str(exc)


def _test_ollama(base_url: str) -> tuple[bool, str]:
    """Test Ollama by hitting /api/tags."""
    try:
        resp = requests.get(
            f"{base_url.rstrip('/')}/api/tags",
            timeout=5,
        )
        if resp.status_code == 200:
            return True, ''
        return False, f"HTTP {resp.status_code}"
    except requests.exceptions.ConnectionError:
        return False, 'Connection refused — is Ollama running?'
    except requests.exceptions.Timeout:
        return False, 'Request timed out'
    except Exception as exc:
        return False, str(exc)


def _test_chatgpt_oauth() -> tuple[bool, str]:
    """Check if the OAuth token exists and is present."""
    token = _get_setting('openai_oauth_token')
    if token:
        return True, ''
    return False, 'No OAuth token found — connect via ChatGPT OAuth first'


def _fetch_openai_compatible_models(base_url: str, api_key: str) -> list[str]:
    """Return model IDs from an OpenAI-compatible /models endpoint."""
    try:
        resp = requests.get(
            f"{base_url.rstrip('/')}/models",
            headers=_bearer_headers(api_key),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        models = [m.get('id', '') for m in data.get('data', []) if m.get('id')]
        return sorted(models)
    except Exception:
        return []


def _fetch_ollama_models(base_url: str) -> list[str]:
    """Return model names from the Ollama /api/tags endpoint."""
    try:
        resp = requests.get(
            f"{base_url.rstrip('/')}/api/tags",
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        models = [m.get('name', '') for m in data.get('models', []) if m.get('name')]
        return sorted(models)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@ai_models_bp.route('/test', methods=['POST'])
@login_required
def test_provider():
    """Test connectivity for a given AI provider configuration.

    Request body:
        {
            "provider": "openai",          # required
            "api_key":  "sk-...",          # required for openai/anthropic/minimax
            "base_url": "https://..."      # required for openai/ollama/minimax
        }

    Response:
        {"valid": true, "error": ""}
        {"valid": false, "error": "Connection refused"}
    """
    data = request.get_json(silent=True) or {}
    provider = (data.get('provider') or '').strip().lower()
    api_key = (data.get('api_key') or '').strip()
    base_url = (data.get('base_url') or '').strip()

    if not provider:
        return jsonify({'valid': False, 'error': 'provider is required'}), 400

    if provider in ('openai', 'minimax'):
        if not api_key:
            return jsonify({'valid': False, 'error': 'api_key is required'})
        if not base_url:
            base_url = (
                'https://api.openai.com/v1' if provider == 'openai'
                else 'https://api.minimaxi.chat/v1'
            )
        valid, error = _test_openai_compatible(base_url, api_key)

    elif provider == 'anthropic':
        if not api_key:
            return jsonify({'valid': False, 'error': 'api_key is required'})
        valid, error = _test_anthropic(api_key)

    elif provider == 'ollama':
        if not base_url:
            base_url = 'http://localhost:11434'
        valid, error = _test_ollama(base_url)

    elif provider == 'chatgpt_oauth':
        valid, error = _test_chatgpt_oauth()

    else:
        return jsonify({'valid': False, 'error': f"Unknown provider: {provider}"}), 400

    return jsonify({'valid': valid, 'error': error})


@ai_models_bp.route('/models', methods=['GET'])
@login_required
def list_models():
    """Return available models for a given provider.

    Query parameters:
        provider  — provider name
        api_key   — API key (where applicable)
        base_url  — base URL (where applicable)

    Response:
        {"models": ["gpt-4o", "gpt-4o-mini", ...]}
    """
    provider = (request.args.get('provider') or '').strip().lower()
    api_key = (request.args.get('api_key') or '').strip()
    base_url = (request.args.get('base_url') or '').strip()

    if not provider:
        return jsonify({'error': 'provider is required'}), 400

    if provider in ('openai', 'minimax'):
        if not base_url:
            base_url = (
                'https://api.openai.com/v1' if provider == 'openai'
                else 'https://api.minimaxi.chat/v1'
            )
        models = _fetch_openai_compatible_models(base_url, api_key)

    elif provider == 'anthropic':
        models = list(_ANTHROPIC_MODELS)

    elif provider == 'ollama':
        if not base_url:
            base_url = 'http://localhost:11434'
        models = _fetch_ollama_models(base_url)

    elif provider == 'chatgpt_oauth':
        models = list(_CHATGPT_OAUTH_MODELS)

    else:
        return jsonify({'error': f"Unknown provider: {provider}"}), 400

    return jsonify({'models': models})
