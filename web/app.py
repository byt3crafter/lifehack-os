#!/usr/bin/env python3
"""Life Hack OS - AI-Native Personal Operating System (Modular).

Created by Ludovic Micinthe (dovik@micinthe.com) | Vibe Coder
"""
from flask import Flask, jsonify
from flask_cors import CORS
import os
import secrets
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent.parent / '.env')

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.database import init_database, get_connection, seed_habit_templates
from src.infrastructure.config import load_config
from src.infrastructure.database.repositories import ReplacementRepository
from src.infrastructure.plugins import register_builtin_plugins

# Import all blueprints
from routes import (
    auth_bp, habits_bp, food_bp, checkins_bp, walks_bp,
    patterns_bp, reports_bp, projects_bp, integrations_bp,
    misc_bp, openclaw_bp, challenges_bp, modules_bp, ai_bp,
    api_docs_bp, plugins_bp, settings_bp,
    openai_oauth_bp, ai_models_bp, app_log_bp,
)


def create_app():
    """Application factory."""
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.secret_key = os.environ.get('LIFEHACK_SECRET_KEY') or secrets.token_hex(32)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400 * 30  # 30 days
    CORS(app)

    # Initialize database (all tables created in connection.py) and run migrations
    init_database()
    config = load_config()

    # Seed built-in habit templates if the table is empty
    seed_habit_templates()

    # Register built-in plugins into the singleton registry
    register_builtin_plugins()

    # Bootstrap admin user from env vars if no users exist yet
    from routes.auth import ensure_admin_user
    ensure_admin_user()

    # Seed defaults
    replacement_repo = ReplacementRepository()
    actions = replacement_repo.get_all_actions()
    if not actions:
        from src.domain.entities import ReplacementAction
        for cat_id, cat_info in config.replacement_categories.items():
            action = ReplacementAction(name=cat_info['name'], category=cat_id, points=cat_info['points'])
            replacement_repo.create_action(action)

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(habits_bp)
    app.register_blueprint(food_bp)
    app.register_blueprint(checkins_bp)
    app.register_blueprint(walks_bp)
    app.register_blueprint(patterns_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(integrations_bp)
    app.register_blueprint(misc_bp)
    app.register_blueprint(openclaw_bp)
    app.register_blueprint(challenges_bp)
    app.register_blueprint(modules_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(api_docs_bp)
    app.register_blueprint(plugins_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(openai_oauth_bp)
    app.register_blueprint(ai_models_bp)
    app.register_blueprint(app_log_bp)

    # Flask error handlers — log to app_log table and return safe JSON responses

    @app.errorhandler(500)
    def handle_500(e):
        from web.routes.app_log import log_event
        log_event('error', 'flask', f'500 Internal Server Error: {str(e)}', traceback.format_exc())
        return jsonify({'error': 'Internal server error'}), 500

    @app.errorhandler(Exception)
    def handle_exception(e):
        from web.routes.app_log import log_event
        log_event('error', 'flask', str(e), traceback.format_exc())
        return jsonify({'error': str(e)}), 500

    # Health check endpoint (used by Docker HEALTHCHECK)
    @app.route('/health')
    def health():
        return 'ok', 200

    return app


app = create_app()

if __name__ == '__main__':
    host = os.environ.get('LIFEHACK_HOST', '0.0.0.0')
    port = int(os.environ.get('LIFEHACK_PORT', 8420))
    app.run(host=host, port=port, debug=False)
