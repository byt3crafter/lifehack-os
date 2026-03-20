"""Wellness routes — water intake, sleep logging, and wellness score."""
from datetime import date, datetime, timedelta
from flask import Blueprint, jsonify, request

from .decorators import login_required, current_user_id
from src.infrastructure.database import get_connection
from src.infrastructure.database.user_scope import get_user_setting, set_user_setting

wellness_bp = Blueprint('wellness', __name__, url_prefix='/api/wellness')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _calc_hours(bedtime: str, wake_time: str) -> float | None:
    """Calculate sleep hours from HH:MM strings. Handles midnight crossover."""
    if not bedtime or not wake_time:
        return None
    try:
        bed = datetime.strptime(bedtime, '%H:%M')
        wake = datetime.strptime(wake_time, '%H:%M')
        delta = wake - bed
        if delta.total_seconds() < 0:
            # Crossed midnight
            delta += timedelta(days=1)
        hours = delta.total_seconds() / 3600
        return round(hours, 2)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Water endpoints
# ---------------------------------------------------------------------------

@wellness_bp.route('/water', methods=['POST'])
@login_required
def log_water():
    """Log water intake. Body: {glasses: 1}."""
    uid = current_user_id()
    data = request.get_json(silent=True) or {}
    glasses = int(data.get('glasses', 1))
    if glasses < 1:
        return jsonify({'error': 'glasses must be at least 1'}), 400

    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO water_logs (user_id, glasses) VALUES (?, ?)",
        (uid, glasses),
    )
    conn.commit()

    total_row = conn.execute(
        "SELECT COALESCE(SUM(glasses), 0) as total FROM water_logs WHERE user_id = ? AND date(logged_at) = date('now')",
        (uid,),
    ).fetchone()

    return jsonify({
        'success': True,
        'id': cursor.lastrowid,
        'glasses': glasses,
        'total_today': total_row['total'],
    }), 201


@wellness_bp.route('/water/today')
@login_required
def get_water_today():
    """Return {total_glasses, goal} for today."""
    uid = current_user_id()
    conn = get_connection()

    total_row = conn.execute(
        "SELECT COALESCE(SUM(glasses), 0) as total FROM water_logs WHERE user_id = ? AND date(logged_at) = date('now')",
        (uid,),
    ).fetchone()

    logs = conn.execute(
        "SELECT id, glasses, logged_at FROM water_logs WHERE user_id = ? AND date(logged_at) = date('now') ORDER BY logged_at",
        (uid,),
    ).fetchall()

    goal = int(get_user_setting(conn, uid, 'water_goal', '8'))

    return jsonify({
        'total_glasses': total_row['total'],
        'goal': goal,
        'logs': [{'id': r['id'], 'glasses': r['glasses'], 'logged_at': r['logged_at']} for r in logs],
    })


@wellness_bp.route('/water/goal', methods=['PUT'])
@login_required
def set_water_goal():
    """Set daily water goal. Body: {goal: 8}."""
    uid = current_user_id()
    data = request.get_json(silent=True) or {}
    goal = int(data.get('goal', 8))
    if goal < 1:
        return jsonify({'error': 'goal must be at least 1'}), 400

    conn = get_connection()
    set_user_setting(conn, uid, 'water_goal', str(goal))

    return jsonify({'success': True, 'goal': goal})


@wellness_bp.route('/water/<int:log_id>', methods=['DELETE'])
@login_required
def delete_water(log_id):
    """Delete a water log entry."""
    uid = current_user_id()
    conn = get_connection()
    result = conn.execute(
        "DELETE FROM water_logs WHERE id = ? AND user_id = ?",
        (log_id, uid),
    )
    conn.commit()
    if result.rowcount == 0:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Sleep endpoints
# ---------------------------------------------------------------------------

@wellness_bp.route('/sleep', methods=['POST'])
@login_required
def log_sleep():
    """Log sleep. Body: {date, bedtime, wake_time, quality, notes}."""
    uid = current_user_id()
    data = request.get_json(silent=True) or {}

    sleep_date = (data.get('date') or date.today().isoformat()).strip()
    bedtime = (data.get('bedtime') or '').strip() or None
    wake_time = (data.get('wake_time') or '').strip() or None
    notes = (data.get('notes') or '').strip()

    try:
        quality = int(data.get('quality', 3))
        quality = max(1, min(5, quality))
    except (TypeError, ValueError):
        quality = 3

    hours = _calc_hours(bedtime, wake_time)

    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM sleep_logs WHERE user_id = ? AND date = ?",
        (uid, sleep_date),
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE sleep_logs
               SET bedtime = ?, wake_time = ?, hours = ?, quality = ?, notes = ?
               WHERE id = ? AND user_id = ?""",
            (bedtime, wake_time, hours, quality, notes, existing['id'], uid),
        )
        log_id = existing['id']
    else:
        cursor = conn.execute(
            """INSERT INTO sleep_logs (user_id, date, bedtime, wake_time, hours, quality, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (uid, sleep_date, bedtime, wake_time, hours, quality, notes),
        )
        log_id = cursor.lastrowid

    conn.commit()

    return jsonify({
        'success': True,
        'id': log_id,
        'date': sleep_date,
        'hours': hours,
        'quality': quality,
    }), 201


@wellness_bp.route('/sleep/today')
@login_required
def get_sleep_today():
    """Return today's sleep entry or null."""
    uid = current_user_id()
    conn = get_connection()
    today = date.today().isoformat()

    row = conn.execute(
        "SELECT id, date, bedtime, wake_time, hours, quality, notes FROM sleep_logs WHERE user_id = ? AND date = ?",
        (uid, today),
    ).fetchone()

    return jsonify(dict(row) if row else None)


@wellness_bp.route('/sleep')
@login_required
def get_sleep_history():
    """Return sleep entries for last N days (default 7). Query param: days."""
    uid = current_user_id()
    days = max(1, int(request.args.get('days', 7)))
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()

    conn = get_connection()
    rows = conn.execute(
        """SELECT id, date, bedtime, wake_time, hours, quality, notes
           FROM sleep_logs
           WHERE user_id = ? AND date >= ?
           ORDER BY date DESC""",
        (uid, cutoff),
    ).fetchall()

    return jsonify([dict(r) for r in rows])


@wellness_bp.route('/sleep/<int:log_id>', methods=['DELETE'])
@login_required
def delete_sleep(log_id):
    """Delete a sleep log entry."""
    uid = current_user_id()
    conn = get_connection()
    result = conn.execute(
        "DELETE FROM sleep_logs WHERE id = ? AND user_id = ?",
        (log_id, uid),
    )
    conn.commit()
    if result.rowcount == 0:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Wellness score
# ---------------------------------------------------------------------------

@wellness_bp.route('/score')
@login_required
def get_wellness_score():
    """Calculate today's wellness score (0-100) with a 7-day trend."""
    uid = current_user_id()
    conn = get_connection()
    today = date.today().isoformat()

    def _score_for_day(d: str) -> dict:
        # -- Habits (25 pts) --
        total_habits = conn.execute(
            "SELECT COUNT(*) as c FROM habits WHERE user_id = ? AND active = 1",
            (uid,),
        ).fetchone()['c']
        completed_habits = conn.execute(
            "SELECT COUNT(*) as c FROM habit_completions WHERE user_id = ? AND date(completed_at) = ?",
            (uid, d),
        ).fetchone()['c']
        habits_pts = (completed_habits / total_habits * 25) if total_habits else 0

        # -- Water (25 pts) --
        water_total = conn.execute(
            "SELECT COALESCE(SUM(glasses), 0) as total FROM water_logs WHERE user_id = ? AND date(logged_at) = ?",
            (uid, d),
        ).fetchone()['total']
        water_goal = int(get_user_setting(conn, uid, 'water_goal', '8'))
        water_pts = min(water_total / water_goal, 1.0) * 25 if water_goal else 0

        # -- Sleep quality (25 pts) --
        sleep_row = conn.execute(
            "SELECT quality FROM sleep_logs WHERE user_id = ? AND date = ?",
            (uid, d),
        ).fetchone()
        sleep_pts = (sleep_row['quality'] / 5 * 25) if sleep_row else 0

        # -- Food (25 pts) --
        meals_logged = conn.execute(
            "SELECT COUNT(*) as c FROM food_logs WHERE user_id = ? AND date(logged_at) = ?",
            (uid, d),
        ).fetchone()['c']
        food_pts = min(meals_logged, 3) / 3 * 25

        score = round(habits_pts + water_pts + sleep_pts + food_pts)
        return {
            'date': d,
            'score': min(100, score),
            'habits': round(habits_pts, 1),
            'water': round(water_pts, 1),
            'sleep': round(sleep_pts, 1),
            'food': round(food_pts, 1),
        }

    # Today's full breakdown
    today_data = _score_for_day(today)

    # 7-day trend (today + 6 prior days, oldest first)
    trend = []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        day_data = _score_for_day(d) if d != today else today_data
        trend.append({'date': day_data['date'], 'score': day_data['score']})

    return jsonify({
        'score': today_data['score'],
        'breakdown': {
            'habits': today_data['habits'],
            'water': today_data['water'],
            'sleep': today_data['sleep'],
            'food': today_data['food'],
        },
        'trend': trend,
    })
