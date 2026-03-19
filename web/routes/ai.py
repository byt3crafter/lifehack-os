"""AI feature routes — food analysis, insights, reports."""
from flask import Blueprint, jsonify, request

from .decorators import login_required
from src.infrastructure.ai import get_ai_provider
from src.infrastructure.ai.factory import _get_setting, _make_provider
from src.infrastructure.database import get_connection
from src.infrastructure.database.repositories import (
    HabitRepository, CheckinRepository, StatsRepository
)
from src.infrastructure.config import load_config
from datetime import date
import os

ai_bp = Blueprint('ai', __name__, url_prefix='/api/ai')

habit_repo = HabitRepository()
checkin_repo = CheckinRepository()
stats_repo = StatsRepository()
config = load_config()

# Known provider names and the settings keys that indicate they are configured.
_PROVIDER_CREDENTIAL_KEYS = {
    'openai': 'ai_openai_key',
    'anthropic': 'ai_anthropic_key',
    'minimax': 'ai_minimax_key',
    'ollama': 'ai_ollama_url',
    'chatgpt_oauth': 'openai_oauth_token',
}

# Per-task setting keys (must match factory.py resolution order).
_TASK_SETTING_KEYS = {
    'food': 'ai_provider_food',
    'habits': 'ai_provider_habits',
    'insights': 'ai_provider_insights',
    'reports': 'ai_provider_reports',
    'default': 'ai_provider_default',
}


@ai_bp.route('/usage')
@login_required
def ai_usage():
    """Return recent AI usage log with aggregate totals.

    Query parameters:
        limit  — number of recent entries to return (default 100)
    """
    limit = request.args.get('limit', 100, type=int)
    conn = get_connection()

    rows = conn.execute(
        """SELECT timestamp, provider, model, action,
                  input_tokens, output_tokens, total_tokens,
                  cost_usd, success, error_message, duration_ms
           FROM ai_usage_log
           ORDER BY timestamp DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()

    totals_row = conn.execute(
        """SELECT
               COUNT(*) AS total_calls,
               SUM(total_tokens) AS total_tokens,
               SUM(cost_usd) AS total_cost_usd,
               SUM(success) AS success_count
           FROM ai_usage_log"""
    ).fetchone()

    total_calls = totals_row['total_calls'] or 0
    success_count = totals_row['success_count'] or 0
    success_rate = round((success_count / total_calls * 100), 1) if total_calls > 0 else 0.0

    return jsonify({
        'entries': [
            {
                'timestamp': r['timestamp'],
                'provider': r['provider'],
                'model': r['model'],
                'action': r['action'],
                'input_tokens': r['input_tokens'],
                'output_tokens': r['output_tokens'],
                'total_tokens': r['total_tokens'],
                'cost_usd': r['cost_usd'],
                'success': bool(r['success']),
                'error_message': r['error_message'],
                'duration_ms': r['duration_ms'],
            }
            for r in rows
        ],
        'totals': {
            'total_calls': total_calls,
            'total_tokens': totals_row['total_tokens'] or 0,
            'total_cost_usd': round(totals_row['total_cost_usd'] or 0, 6),
            'success_rate': success_rate,
        },
    })


@ai_bp.route('/status')
@login_required
def ai_status():
    """Check if AI provider is configured and available."""
    provider_name = os.environ.get('LIFEHACK_AI_PROVIDER', 'none')
    provider = get_ai_provider()
    return jsonify({
        'provider': provider_name,
        'available': provider.is_available(),
        'provider_class': type(provider).__name__
    })


@ai_bp.route('/providers')
@login_required
def ai_providers():
    """Return all configured providers and their per-task assignments.

    Response shape:
    {
        "providers": {
            "<name>": {"configured": bool, "available": bool},
            ...
        },
        "assignments": {
            "food": "<name>",
            "insights": "<name>",
            "reports": "<name>",
            "default": "<name>"
        }
    }
    """
    providers_info = {}
    for provider_name, cred_key in _PROVIDER_CREDENTIAL_KEYS.items():
        configured = bool(_get_setting(cred_key))
        if configured:
            try:
                instance = _make_provider(provider_name)
                available = instance.is_available()
            except Exception:
                available = False
            model = getattr(instance, 'model', '')
            providers_info[provider_name] = {'configured': True, 'available': available, 'model': model}
        else:
            providers_info[provider_name] = {'configured': False, 'model': ''}

    # Build task assignments by replicating the factory resolution order.
    env_fallback = os.environ.get('LIFEHACK_AI_PROVIDER', 'none')
    default_provider = (
        _get_setting('ai_provider_default')
        or _get_setting('ai_provider')
        or env_fallback
    ).lower()

    assignments = {}
    for task, setting_key in _TASK_SETTING_KEYS.items():
        if task == 'default':
            assignments[task] = default_provider
        else:
            assignments[task] = (
                _get_setting(setting_key)
                or default_provider
            ).lower()

    return jsonify({
        'providers': providers_info,
        'assignments': assignments,
    })


@ai_bp.route('/analyze-food', methods=['POST'])
@login_required
def analyze_food():
    """Use AI to estimate nutrition from a food description."""
    data = request.json
    description = data.get('description', '')

    if not description:
        return jsonify({'error': 'Description required'}), 400

    provider = get_ai_provider('food')
    if not provider.is_available():
        return jsonify({'error': 'AI not configured', 'estimated': False}), 200

    try:
        result = provider.analyze_food(description)
        if not result.estimated:
            return jsonify({
                'estimated': False,
                'ai_error': 'AI returned no usable data',
            })
        return jsonify({
            'estimated': result.estimated,
            'calories': result.calories,
            'protein_g': result.protein_g,
            'carbs_g': result.carbs_g,
            'fat_g': result.fat_g,
            'description': result.description,
        })
    except Exception as exc:
        return jsonify({'estimated': False, 'ai_error': str(exc)})


@ai_bp.route('/insight', methods=['POST'])
@login_required
def generate_insight():
    """Generate a personalized AI insight based on current user state."""
    provider = get_ai_provider('insights')
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

    try:
        insight = provider.generate_insight(user_state)
    except Exception as exc:
        return jsonify({'generated': False, 'ai_error': str(exc)})

    if not insight:
        return jsonify({'generated': False, 'ai_error': 'AI returned no insight'})

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
        'type': insight.insight_type,
    })
