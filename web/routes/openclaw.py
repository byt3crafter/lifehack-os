"""OpenClaw API routes (AI agent integration endpoints).

OpenClaw is an external AI agent that connects to LifeHack OS via these endpoints.
Any OpenClaw-compatible AI agent can use these to monitor, report, and push data.
Authenticate with X-API-Key header.

All data operations target the first admin user's data.
"""
from flask import Blueprint, jsonify, request
from datetime import date, datetime

from .decorators import api_key_required
from src.domain.entities import Habit, HabitCompletion, CompletionStatus, Frequency, DailyCheckin
from src.infrastructure.database import get_connection
from src.infrastructure.database.repositories import HabitRepository, CheckinRepository, StatsRepository
from src.infrastructure.config import load_config

openclaw_bp = Blueprint('openclaw', __name__, url_prefix='/api/openclaw')

config = load_config()


def _get_admin_uid(conn) -> int:
    """Return the ID of the first admin user."""
    row = conn.execute(
        "SELECT id FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    if not row:
        raise RuntimeError("No admin user found")
    return row['id']


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
    conn = get_connection()
    uid = _get_admin_uid(conn)

    stats_row = conn.execute(
        "SELECT total_xp, level FROM user_stats WHERE user_id = ?", (uid,)
    ).fetchone()
    total_xp = stats_row['total_xp'] if stats_row else 0
    level = stats_row['level'] if stats_row else 1

    habit_rows = conn.execute(
        "SELECT * FROM habits WHERE user_id = ? AND active = 1 ORDER BY category, name", (uid,)
    ).fetchall()

    completion_rows = conn.execute(
        "SELECT habit_id FROM habit_completions WHERE user_id = ? AND date(completed_at) = date('now')",
        (uid,)
    ).fetchall()
    completed_ids = {r['habit_id'] for r in completion_rows}

    checkin = conn.execute(
        "SELECT mood, energy, avoided_alcohol FROM daily_checkins WHERE user_id = ? AND date = date('now')",
        (uid,)
    ).fetchone()

    # Sobriety streak
    checkin_rows = conn.execute(
        """SELECT date, avoided_alcohol FROM daily_checkins
           WHERE user_id = ? ORDER BY date DESC LIMIT 365""",
        (uid,)
    ).fetchall()
    sobriety = 0
    for r in checkin_rows:
        if r['avoided_alcohol']:
            sobriety += 1
        else:
            break

    weak_habits = []
    strong_habits = []
    for h in habit_rows:
        streak_rows = conn.execute(
            """SELECT DISTINCT date(completed_at) as d FROM habit_completions
               WHERE user_id = ? AND habit_id = ? AND status = 'complete'
               ORDER BY d DESC LIMIT 365""",
            (uid, h['id'])
        ).fetchall()
        streak = 0
        expected = date.today()
        for row in streak_rows:
            cd = date.fromisoformat(row['d'])
            if cd == expected:
                streak += 1
                expected = date.fromordinal(expected.toordinal() - 1)
            elif cd < expected:
                break

        if streak >= 7:
            strong_habits.append({'name': h['name'], 'streak': streak})
        elif streak == 0 and h['id'] not in completed_ids:
            weak_habits.append({'name': h['name'], 'category': h['category']})

    _log_openclaw_action('status_check')

    return jsonify({
        'timestamp': datetime.now().isoformat(),
        'stats': {
            'total_xp': total_xp,
            'level': level,
            'level_name': config.get_level_name(level),
            'sobriety_days': sobriety
        },
        'today': {
            'habits_total': len(habit_rows),
            'habits_completed': len(completed_ids),
            'habits_pending': len(habit_rows) - len(completed_ids),
            'checkin_done': checkin is not None,
            'mood': checkin['mood'] if checkin else None,
            'energy': checkin['energy'] if checkin else None,
            'avoided_alcohol': checkin['avoided_alcohol'] if checkin else None
        },
        'patterns': {
            'strong_habits': strong_habits,
            'weak_habits': weak_habits,
            'needs_attention': len(weak_habits) > len(strong_habits)
        },
        'pending_actions': [h['name'] for h in habit_rows if h['id'] not in completed_ids]
    })


@openclaw_bp.route('/insight', methods=['POST'])
@api_key_required
def openclaw_push_insight():
    """OpenClaw pushes an insight/advice to display on dashboard."""
    data = request.json
    conn = get_connection()
    uid = _get_admin_uid(conn)
    conn.execute(
        'INSERT INTO ai_insights (user_id, insight_type, title, content, priority) VALUES (?, ?, ?, ?, ?)',
        (uid, data.get('type', 'advice'), data['title'], data['content'], data.get('priority', 0))
    )
    conn.commit()
    _log_openclaw_action('push_insight', data.get('title', ''))
    return jsonify({'success': True})


@openclaw_bp.route('/checkin', methods=['POST'])
@api_key_required
def openclaw_do_checkin():
    """OpenClaw can submit a check-in on behalf of user."""
    data = request.json
    conn = get_connection()
    uid = _get_admin_uid(conn)

    today = date.today().isoformat()
    existing = conn.execute(
        "SELECT id FROM daily_checkins WHERE user_id = ? AND date = ?", (uid, today)
    ).fetchone()
    is_new = existing is None

    avoided_alcohol = data.get('avoided_alcohol', True)
    worked_on_future = data.get('worked_on_future', False)
    mood = data.get('mood', 3)
    energy = data.get('energy', 3)
    completed_today = data.get('completed_today', '')
    improvement_note = data.get('improvement_note', '')

    points = config.checkin.completion_points
    if avoided_alcohol:
        points += config.checkin.sobriety_bonus
    if worked_on_future:
        points += config.checkin.future_work_bonus

    if existing:
        conn.execute(
            """UPDATE daily_checkins
               SET completed_today=?, avoided_alcohol=?, worked_on_future=?,
                   mood=?, energy=?, improvement_note=?, points_earned=?
               WHERE user_id = ? AND date = ?""",
            (completed_today, avoided_alcohol, worked_on_future,
             mood, energy, improvement_note, points, uid, today)
        )
        checkin_id = existing['id']
    else:
        cursor = conn.execute(
            """INSERT INTO daily_checkins
               (user_id, date, completed_today, avoided_alcohol, worked_on_future,
                mood, energy, improvement_note, points_earned)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, today, completed_today, avoided_alcohol, worked_on_future,
             mood, energy, improvement_note, points)
        )
        checkin_id = cursor.lastrowid

    if is_new:
        conn.execute(
            "UPDATE user_stats SET total_xp = total_xp + ? WHERE user_id = ?", (points, uid)
        )
        conn.execute(
            """INSERT INTO point_ledger (user_id, source_type, source_id, points, reason)
               VALUES (?, 'checkin', ?, ?, 'Check-in via OpenClaw')""",
            (uid, checkin_id, points)
        )

    conn.commit()
    _log_openclaw_action('checkin', f"{points} pts")
    return jsonify({'success': True, 'points': points})


@openclaw_bp.route('/habit/complete', methods=['POST'])
@api_key_required
def openclaw_complete_habit():
    """OpenClaw can mark a habit complete by name."""
    data = request.json
    habit_name = data.get('habit_name', '').lower()

    conn = get_connection()
    uid = _get_admin_uid(conn)

    habit_rows = conn.execute(
        "SELECT * FROM habits WHERE user_id = ? AND active = 1", (uid,)
    ).fetchall()

    for h in habit_rows:
        if habit_name in h['name'].lower():
            # Calculate streak
            streak_rows = conn.execute(
                """SELECT DISTINCT date(completed_at) as d FROM habit_completions
                   WHERE user_id = ? AND habit_id = ? AND status = 'complete'
                   ORDER BY d DESC LIMIT 365""",
                (uid, h['id'])
            ).fetchall()
            streak = 0
            expected = date.today()
            for row in streak_rows:
                cd = date.fromisoformat(row['d'])
                if cd == expected:
                    streak += 1
                    expected = date.fromordinal(expected.toordinal() - 1)
                elif cd < expected:
                    break

            base_points = h['points']
            if streak >= config.scoring.streak_multiplier_threshold:
                points = int(base_points * config.scoring.streak_multiplier)
            else:
                points = base_points

            cursor = conn.execute(
                """INSERT INTO habit_completions (user_id, habit_id, completed_at, status, points_earned, notes)
                   VALUES (?, ?, ?, 'complete', ?, '')""",
                (uid, h['id'], datetime.now().isoformat(), points)
            )
            conn.execute(
                "UPDATE user_stats SET total_xp = total_xp + ? WHERE user_id = ?", (points, uid)
            )
            conn.execute(
                """INSERT INTO point_ledger (user_id, source_type, source_id, points, reason)
                   VALUES (?, 'habit', ?, ?, ?)""",
                (uid, h['id'], points, f"Completed via OpenClaw: {h['name']}")
            )
            conn.commit()
            _log_openclaw_action('habit_complete', h['name'])
            return jsonify({'success': True, 'habit': h['name'], 'points': points})

    return jsonify({'error': 'Habit not found'}), 404


@openclaw_bp.route('/habit/create', methods=['POST'])
@api_key_required
def openclaw_create_habit():
    """OpenClaw can create a new habit."""
    data = request.json
    conn = get_connection()
    uid = _get_admin_uid(conn)

    cursor = conn.execute(
        """INSERT INTO habits (user_id, name, category, frequency, difficulty, points, active)
           VALUES (?, ?, ?, ?, ?, ?, 1)""",
        (uid, data['name'], data.get('category', 'health'),
         data.get('frequency', 'daily'), data.get('difficulty', 1),
         config.scoring.base_habit_points)
    )
    conn.commit()
    habit_id = cursor.lastrowid
    _log_openclaw_action('habit_create', data['name'])
    return jsonify({'success': True, 'id': habit_id, 'name': data['name']})


@openclaw_bp.route('/habits', methods=['GET'])
@api_key_required
def openclaw_list_habits():
    """OpenClaw can list all habits."""
    conn = get_connection()
    uid = _get_admin_uid(conn)

    habit_rows = conn.execute(
        "SELECT * FROM habits WHERE user_id = ? AND active = 1 ORDER BY category, name", (uid,)
    ).fetchall()

    completion_rows = conn.execute(
        "SELECT habit_id FROM habit_completions WHERE user_id = ? AND date(completed_at) = date('now')",
        (uid,)
    ).fetchall()
    completed_ids = {r['habit_id'] for r in completion_rows}

    result = []
    for h in habit_rows:
        streak_rows = conn.execute(
            """SELECT DISTINCT date(completed_at) as d FROM habit_completions
               WHERE user_id = ? AND habit_id = ? AND status = 'complete'
               ORDER BY d DESC LIMIT 365""",
            (uid, h['id'])
        ).fetchall()
        streak = 0
        expected = date.today()
        for row in streak_rows:
            cd = date.fromisoformat(row['d'])
            if cd == expected:
                streak += 1
                expected = date.fromordinal(expected.toordinal() - 1)
            elif cd < expected:
                break

        result.append({
            'id': h['id'],
            'name': h['name'],
            'category': h['category'],
            'frequency': h['frequency'],
            'streak': streak,
            'completed_today': h['id'] in completed_ids
        })

    return jsonify(result)


@openclaw_bp.route('/food/log', methods=['POST'])
@api_key_required
def openclaw_log_food():
    """OpenClaw can log food with AI-estimated nutrition."""
    data = request.json
    conn = get_connection()
    uid = _get_admin_uid(conn)

    cursor = conn.execute(
        """INSERT INTO food_logs
           (user_id, meal_type, description, calories, protein_g, carbs_g, fat_g, ai_analysis, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (uid,
         data.get('meal_type', 'meal'),
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
