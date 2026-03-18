"""AI feature routes — food analysis, insights, reports."""
from flask import Blueprint, jsonify, request

from .decorators import login_required
from src.infrastructure.ai import get_ai_provider
from src.infrastructure.database import get_connection
from src.infrastructure.database.repositories import (
    HabitRepository, CheckinRepository, StatsRepository
)
from src.infrastructure.config import load_config
from datetime import date

ai_bp = Blueprint('ai', __name__, url_prefix='/api/ai')

habit_repo = HabitRepository()
checkin_repo = CheckinRepository()
stats_repo = StatsRepository()
config = load_config()


@ai_bp.route('/status')
@login_required
def ai_status():
    """Check if AI provider is configured and available."""
    import os
    provider_name = os.environ.get('LIFEHACK_AI_PROVIDER', 'none')
    provider = get_ai_provider()
    return jsonify({
        'provider': provider_name,
        'available': provider.is_available(),
        'provider_class': type(provider).__name__
    })


@ai_bp.route('/analyze-food', methods=['POST'])
@login_required
def analyze_food():
    """Use AI to estimate nutrition from a food description."""
    data = request.json
    description = data.get('description', '')

    if not description:
        return jsonify({'error': 'Description required'}), 400

    provider = get_ai_provider()
    if not provider.is_available():
        return jsonify({'error': 'AI not configured', 'estimated': False}), 200

    result = provider.analyze_food(description)
    return jsonify({
        'estimated': result.estimated,
        'calories': result.calories,
        'protein_g': result.protein_g,
        'carbs_g': result.carbs_g,
        'fat_g': result.fat_g,
        'description': result.description
    })


@ai_bp.route('/insight', methods=['POST'])
@login_required
def generate_insight():
    """Generate a personalized AI insight based on current user state."""
    provider = get_ai_provider()
    if not provider.is_available():
        return jsonify({'error': 'AI not configured'}), 200

    stats = stats_repo.get_stats()
    habits = habit_repo.get_all()
    completions = habit_repo.get_completions_for_date(date.today())
    checkin = checkin_repo.get_for_date(date.today())

    # Find best streak
    best_streak = 0
    for h in habits:
        s = habit_repo.get_streak(h.id)
        if s > best_streak:
            best_streak = s

    user_state = {
        'total_xp': stats.total_xp,
        'level': stats.level,
        'habits_completed': len(completions),
        'habits_total': len(habits),
        'best_streak': best_streak,
        'mood': checkin.mood if checkin else None,
        'energy': checkin.energy if checkin else None,
    }

    insight = provider.generate_insight(user_state)
    if not insight:
        return jsonify({'generated': False})

    # Save to database so it shows on dashboard
    conn = get_connection()
    conn.execute(
        'INSERT INTO ai_insights (insight_type, title, content, priority) VALUES (?, ?, ?, ?)',
        (insight.insight_type, insight.title, insight.content, insight.priority)
    )
    conn.commit()

    return jsonify({
        'generated': True,
        'title': insight.title,
        'content': insight.content,
        'type': insight.insight_type
    })
