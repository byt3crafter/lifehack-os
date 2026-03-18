"""OpenClaw API routes (AI agent integration endpoints).

OpenClaw is an external AI agent that connects to LifeHack OS via these endpoints.
Any OpenClaw-compatible AI agent can use these to monitor, report, and push data.
Authenticate with X-API-Key header.
"""
from flask import Blueprint, jsonify, request
from datetime import date, datetime

from .decorators import api_key_required
from src.domain.entities import Habit, HabitCompletion, CompletionStatus, Frequency, DailyCheckin
from src.infrastructure.database import get_connection
from src.infrastructure.database.repositories import (
    HabitRepository, CheckinRepository, StatsRepository
)
from src.infrastructure.config import load_config

openclaw_bp = Blueprint('openclaw', __name__, url_prefix='/api/openclaw')

habit_repo = HabitRepository()
checkin_repo = CheckinRepository()
stats_repo = StatsRepository()
config = load_config()


def _log_openclaw_action(action: str, detail: str = ''):
    """Log an OpenClaw action for the connection log."""
    try:
        conn = get_connection()
        ip = request.remote_addr or ''
        conn.execute(
            "INSERT INTO openclaw_log (action, detail, ip_address) VALUES (?, ?, ?)",
            (action, detail, ip)
        )
        conn.commit()
    except Exception:
        pass


@openclaw_bp.route('/status', methods=['GET'])
@api_key_required
def openclaw_status():
    """Full status dump for OpenClaw to understand current state."""
    stats = stats_repo.get_stats()
    habits = habit_repo.get_all()
    completions = habit_repo.get_completions_for_date(date.today())
    completed_ids = {c.habit_id for c in completions}
    checkin = checkin_repo.get_for_date(date.today())
    sobriety = checkin_repo.get_sobriety_streak()
    
    weak_habits = []
    strong_habits = []
    for h in habits:
        streak = habit_repo.get_streak(h.id)
        if streak >= 7:
            strong_habits.append({'name': h.name, 'streak': streak})
        elif streak == 0 and h.id not in completed_ids:
            weak_habits.append({'name': h.name, 'category': h.category})
    
    return jsonify({
        'timestamp': datetime.now().isoformat(),
        'stats': {
            'total_xp': stats.total_xp,
            'level': stats.level,
            'level_name': config.get_level_name(stats.level),
            'sobriety_days': sobriety
        },
        'today': {
            'habits_total': len(habits),
            'habits_completed': len(completed_ids),
            'habits_pending': len(habits) - len(completed_ids),
            'checkin_done': checkin is not None,
            'mood': checkin.mood if checkin else None,
            'energy': checkin.energy if checkin else None,
            'avoided_alcohol': checkin.avoided_alcohol if checkin else None
        },
        'patterns': {
            'strong_habits': strong_habits,
            'weak_habits': weak_habits,
            'needs_attention': len(weak_habits) > len(strong_habits)
        },
        'pending_actions': [h.name for h in habits if h.id not in completed_ids]
    })
    _log_openclaw_action('status_check')


@openclaw_bp.route('/insight', methods=['POST'])
@api_key_required
def openclaw_push_insight():
    """OpenClaw pushes an insight/advice to display on dashboard."""
    data = request.json
    conn = get_connection()
    conn.execute(
        'INSERT INTO ai_insights (insight_type, title, content, priority) VALUES (?, ?, ?, ?)',
        (data.get('type', 'advice'), data['title'], data['content'], data.get('priority', 0))
    )
    conn.commit()
    _log_openclaw_action('push_insight', data.get('title', ''))
    return jsonify({'success': True})


@openclaw_bp.route('/checkin', methods=['POST'])
@api_key_required
def openclaw_do_checkin():
    """OpenClaw can submit a check-in on behalf of user."""
    data = request.json
    existing = checkin_repo.get_for_date(date.today())
    is_new = existing is None
    
    checkin = DailyCheckin(
        date=date.today(),
        completed_today=data.get('completed_today', ''),
        avoided_alcohol=data.get('avoided_alcohol', True),
        worked_on_future=data.get('worked_on_future', False),
        mood=data.get('mood', 3),
        energy=data.get('energy', 3),
        improvement_note=data.get('improvement_note', '')
    )
    points = checkin.calculate_points(
        config.checkin.completion_points,
        config.checkin.sobriety_bonus,
        config.checkin.future_work_bonus
    )
    checkin.points_earned = points
    checkin_repo.save(checkin)
    
    if is_new:
        stats_repo.add_points('checkin', points, "Check-in via OpenClaw", checkin.id)
    
    _log_openclaw_action('checkin', f"{points} pts")
    return jsonify({'success': True, 'points': points})


@openclaw_bp.route('/habit/complete', methods=['POST'])
@api_key_required
def openclaw_complete_habit():
    """OpenClaw can mark a habit complete by name."""
    data = request.json
    habit_name = data.get('habit_name', '').lower()
    
    habits = habit_repo.get_all()
    for h in habits:
        if habit_name in h.name.lower():
            streak = habit_repo.get_streak(h.id)
            points = h.calculate_points(
                streak,
                config.scoring.streak_multiplier_threshold,
                config.scoring.streak_multiplier
            )
            completion = HabitCompletion(
                habit_id=h.id,
                status=CompletionStatus.COMPLETE,
                points_earned=points
            )
            habit_repo.log_completion(completion)
            stats_repo.add_points('habit', points, f"Completed via OpenClaw: {h.name}", h.id)
            _log_openclaw_action('habit_complete', h.name)
            return jsonify({'success': True, 'habit': h.name, 'points': points})
    
    return jsonify({'error': 'Habit not found'}), 404


@openclaw_bp.route('/habit/create', methods=['POST'])
@api_key_required
def openclaw_create_habit():
    """OpenClaw can create a new habit."""
    data = request.json
    habit = Habit(
        name=data['name'],
        category=data.get('category', 'health'),
        frequency=Frequency(data.get('frequency', 'daily')),
        difficulty=data.get('difficulty', 1),
        points=config.scoring.base_habit_points
    )
    habit = habit_repo.create(habit)
    _log_openclaw_action('habit_create', habit.name)
    return jsonify({'success': True, 'id': habit.id, 'name': habit.name})


@openclaw_bp.route('/habits', methods=['GET'])
@api_key_required
def openclaw_list_habits():
    """OpenClaw can list all habits."""
    habits = habit_repo.get_all()
    completions = habit_repo.get_completions_for_date(date.today())
    completed_ids = {c.habit_id for c in completions}
    
    return jsonify([{
        'id': h.id,
        'name': h.name,
        'category': h.category,
        'frequency': h.frequency.value,
        'streak': habit_repo.get_streak(h.id),
        'completed_today': h.id in completed_ids
    } for h in habits])


@openclaw_bp.route('/food/log', methods=['POST'])
@api_key_required
def openclaw_log_food():
    """OpenClaw can log food with AI-estimated nutrition."""
    data = request.json
    conn = get_connection()
    
    cursor = conn.execute(
        """INSERT INTO food_logs 
           (meal_type, description, calories, protein_g, carbs_g, fat_g, ai_analysis, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (data.get('meal_type', 'meal'),
         data.get('description', ''),
         data.get('calories'),
         data.get('protein_g'),
         data.get('carbs_g'),
         data.get('fat_g'),
         data.get('ai_analysis', ''),
         data.get('notes', ''))
    )
    conn.commit()
    
    _log_openclaw_action('food_log', data.get('description', ''))
    return jsonify({'success': True, 'id': cursor.lastrowid})


@openclaw_bp.route('/schema', methods=['GET'])
def openclaw_schema():
    """Self-documenting API schema. No auth required — lets OpenClaw discover endpoints."""
    return jsonify({
        'name': 'LifeHack OS OpenClaw API',
        'version': '1.0',
        'auth': {
            'type': 'api_key',
            'header': 'X-API-Key',
            'description': 'Set your API key in .env as LIFEHACK_API_KEY'
        },
        'endpoints': [
            {
                'path': '/api/openclaw/status',
                'method': 'GET',
                'description': 'Full status dump — XP, habits, check-in, patterns, pending actions',
                'auth': True
            },
            {
                'path': '/api/openclaw/habits',
                'method': 'GET',
                'description': 'List all habits with streaks and today completion status',
                'auth': True
            },
            {
                'path': '/api/openclaw/habit/complete',
                'method': 'POST',
                'description': 'Mark a habit complete by name',
                'body': {'habit_name': 'string (partial match)'},
                'auth': True
            },
            {
                'path': '/api/openclaw/habit/create',
                'method': 'POST',
                'description': 'Create a new habit',
                'body': {'name': 'string', 'category': 'string (optional)', 'frequency': 'daily|weekly', 'difficulty': '1-5'},
                'auth': True
            },
            {
                'path': '/api/openclaw/checkin',
                'method': 'POST',
                'description': 'Submit a daily check-in',
                'body': {'completed_today': 'string', 'avoided_alcohol': 'bool', 'mood': '1-5', 'energy': '1-5', 'improvement_note': 'string'},
                'auth': True
            },
            {
                'path': '/api/openclaw/insight',
                'method': 'POST',
                'description': 'Push an insight to the dashboard',
                'body': {'title': 'string', 'content': 'string', 'type': 'advice|warning|celebration|tip', 'priority': '0-10'},
                'auth': True
            },
            {
                'path': '/api/openclaw/food/log',
                'method': 'POST',
                'description': 'Log food with nutrition data',
                'body': {'meal_type': 'string', 'description': 'string', 'calories': 'number', 'protein_g': 'number', 'carbs_g': 'number', 'fat_g': 'number'},
                'auth': True
            },
            {
                'path': '/api/openclaw/log',
                'method': 'GET',
                'description': 'View recent connection activity log',
                'auth': True
            },
            {
                'path': '/api/openclaw/schema',
                'method': 'GET',
                'description': 'This endpoint — API documentation',
                'auth': False
            }
        ]
    })


@openclaw_bp.route('/log', methods=['GET'])
@api_key_required
def openclaw_connection_log():
    """View recent OpenClaw activity."""
    _log_openclaw_action('view_log')
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM openclaw_log ORDER BY logged_at DESC LIMIT 50"
    ).fetchall()
    return jsonify([{
        'id': r['id'],
        'action': r['action'],
        'detail': r['detail'],
        'ip': r['ip_address'],
        'timestamp': r['logged_at']
    } for r in rows])
