"""Integration routes (Vikunja, Google Calendar, Firefly)."""
from flask import Blueprint, jsonify, request

from .decorators import login_required
from src.infrastructure.providers import (
    get_integration_status,
    enable_vikunja, disable_vikunja,
    enable_google_calendar, disable_google_calendar, get_calendar_provider,
    enable_firefly, disable_firefly, get_firefly_provider
)

integrations_bp = Blueprint('integrations', __name__, url_prefix='/api/integrations')


@integrations_bp.route('')
@login_required
def get_integrations():
    return jsonify(get_integration_status())


@integrations_bp.route('/vikunja', methods=['POST'])
@login_required
def configure_vikunja():
    data = request.json
    
    if data.get('enabled') is False:
        disable_vikunja()
        return jsonify({'success': True, 'enabled': False})
    
    api_url = data.get('api_url', '')
    username = data.get('username', '')
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    if enable_vikunja(api_url, username, password):
        return jsonify({'success': True, 'enabled': True, 'connected': True})
    else:
        return jsonify({'error': 'Connection test failed'}), 400


@integrations_bp.route('/vikunja/test', methods=['POST'])
@login_required
def test_vikunja():
    data = request.json
    from src.infrastructure.providers.vikunja import VikunjaTaskProvider, VikunjaConfig
    
    config = VikunjaConfig(
        api_url=data.get('api_url', ''),
        username=data.get('username', ''),
        password=data.get('password', '')
    )
    provider = VikunjaTaskProvider(config)
    connected = provider.test_connection()
    
    return jsonify({'connected': connected})


@integrations_bp.route('/google_calendar', methods=['POST'])
@login_required
def configure_google_calendar():
    data = request.json
    
    if data.get('enabled') is False:
        disable_google_calendar()
        return jsonify({'success': True, 'enabled': False})
    
    account = data.get('account', '')
    if enable_google_calendar(account):
        return jsonify({'success': True, 'enabled': True, 'connected': True})
    else:
        return jsonify({'error': 'Connection test failed'}), 400


@integrations_bp.route('/firefly', methods=['POST'])
@login_required
def configure_firefly():
    data = request.json
    
    if data.get('enabled') is False:
        disable_firefly()
        return jsonify({'success': True, 'enabled': False})
    
    if enable_firefly():
        return jsonify({'success': True, 'enabled': True, 'connected': True})
    else:
        return jsonify({'error': 'Connection test failed'}), 400


# Calendar and Finance routes moved to misc.py for correct /api/* paths
