"""AI feature routes — food analysis, insights, reports."""
from flask import Blueprint, jsonify, request

from .decorators import login_required, current_user_id
from src.infrastructure.ai import get_ai_provider
from src.infrastructure.ai.factory import _get_setting, _make_provider
from src.infrastructure.database import get_connection
from src.infrastructure.config import load_config
from datetime import date
import os

ai_bp = Blueprint('ai', __name__, url_prefix='/api/ai')

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

    Non-admin users only see their own usage (filtered by user_id).
    Admins see all usage across the installation.

    Query parameters:
        limit  — number of recent entries to return (default 100)
    """
    limit = request.args.get('limit', 100, type=int)
    uid = current_user_id()
    conn = get_connection()

    # Non-admin users only see their own usage
    user = conn.execute(
        "SELECT is_admin FROM users WHERE id = ?", (uid,)
    ).fetchone()
    is_admin = user and user['is_admin']

    if is_admin:
        where_clause = ""
        params = (limit,)
        totals_where = ""
        totals_params = ()
    else:
        where_clause = "WHERE user_id = ?"
        params = (uid, limit)
        totals_where = "WHERE user_id = ?"
        totals_params = (uid,)

    rows = conn.execute(
        f"""SELECT timestamp, provider, model, action,
                  input_tokens, output_tokens, total_tokens,
                  cost_usd, success, error_message, duration_ms
           FROM ai_usage_log
           {where_clause}
           ORDER BY timestamp DESC
           LIMIT ?""",
        params,
    ).fetchall()

    totals_row = conn.execute(
        f"""SELECT
               COUNT(*) AS total_calls,
               SUM(total_tokens) AS total_tokens,
               SUM(cost_usd) AS total_cost_usd,
               SUM(success) AS success_count
           FROM ai_usage_log
           {totals_where}""",
        totals_params,
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
    uid = current_user_id()
    provider = get_ai_provider('insights')
    if not provider.is_available():
        return jsonify({'error': 'AI not configured'}), 200

    conn = get_connection()

    # Fetch user-scoped stats
    stats_row = conn.execute(
        "SELECT total_xp, level FROM user_stats WHERE user_id = ?", (uid,)
    ).fetchone()
    total_xp = stats_row['total_xp'] if stats_row else 0
    level = stats_row['level'] if stats_row else 1

    # Fetch user-scoped habits
    habit_rows = conn.execute(
        "SELECT id FROM habits WHERE user_id = ? AND active = 1", (uid,)
    ).fetchall()
    habit_ids = [r['id'] for r in habit_rows]

    # Completions for today
    completion_rows = conn.execute(
        "SELECT habit_id FROM habit_completions WHERE user_id = ? AND date(completed_at) = date('now')",
        (uid,)
    ).fetchall()
    completed_ids = {r['habit_id'] for r in completion_rows}

    # Today's check-in
    checkin = conn.execute(
        "SELECT mood, energy FROM daily_checkins WHERE user_id = ? AND date = date('now')", (uid,)
    ).fetchone()

    # Best streak across all habits
    best_streak = 0
    for hid in habit_ids:
        rows = conn.execute(
            """SELECT DISTINCT date(completed_at) as d FROM habit_completions
               WHERE user_id = ? AND habit_id = ? AND status = 'complete'
               ORDER BY d DESC LIMIT 365""",
            (uid, hid)
        ).fetchall()
        streak = 0
        from datetime import date as _date
        expected = _date.today()
        for row in rows:
            cd = _date.fromisoformat(row['d'])
            if cd == expected:
                streak += 1
                expected = _date.fromordinal(expected.toordinal() - 1)
            elif cd < expected:
                break
        if streak > best_streak:
            best_streak = streak

    user_state = {
        'total_xp': total_xp,
        'level': level,
        'habits_completed': len(completed_ids),
        'habits_total': len(habit_ids),
        'best_streak': best_streak,
        'mood': checkin['mood'] if checkin else None,
        'energy': checkin['energy'] if checkin else None,
    }

    try:
        insight = provider.generate_insight(user_state)
    except Exception as exc:
        return jsonify({'generated': False, 'ai_error': str(exc)})

    if not insight:
        return jsonify({'generated': False, 'ai_error': 'AI returned no insight'})

    # Save to database scoped to this user
    conn.execute(
        'INSERT INTO ai_insights (user_id, insight_type, title, content, priority) VALUES (?, ?, ?, ?, ?)',
        (uid, insight.insight_type, insight.title, insight.content, insight.priority)
    )
    conn.commit()

    return jsonify({
        'generated': True,
        'title': insight.title,
        'content': insight.content,
        'type': insight.insight_type,
    })
