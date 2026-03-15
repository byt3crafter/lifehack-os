#!/usr/bin/env python3
"""Life Hack OS - AI-Native Personal Operating System (Modular)."""
from flask import Flask
from flask_cors import CORS
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.database import init_database, get_connection
from src.infrastructure.config import load_config
from src.infrastructure.database.repositories import ReplacementRepository

# Import all blueprints
from routes import (
    auth_bp, habits_bp, food_bp, checkins_bp, walks_bp,
    patterns_bp, reports_bp, projects_bp, integrations_bp,
    misc_bp, openclaw_bp
)


def create_app():
    """Application factory."""
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.secret_key = 'lifehack-persistent-secret-2026'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400 * 30  # 30 days
    CORS(app)
    
    # Initialize database
    init_database()
    config = load_config()
    
    # Create insights table
    conn = get_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS ai_insights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        insight_type TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        priority INTEGER DEFAULT 0,
        dismissed INTEGER DEFAULT 0
    )''')
    conn.commit()
    
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
    
    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8420, debug=False)
