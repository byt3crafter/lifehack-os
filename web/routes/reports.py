"""Reports and analytics routes."""
from flask import Blueprint, jsonify, request
from datetime import date, timedelta

from .decorators import login_required, current_user_id
from src.infrastructure.database import get_connection

reports_bp = Blueprint('reports', __name__, url_prefix='/api/reports')


@reports_bp.route('/weekly')
@login_required
def weekly_report():
    """Get weekly summary report."""
    uid = current_user_id()
    conn = get_connection()

    # Calculate date range
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # Habits completed this week
    habits_completed = conn.execute(
        """SELECT COUNT(*) as count FROM habit_completions
           WHERE user_id = ? AND date(completed_at) >= ? AND date(completed_at) <= ?""",
        (uid, week_start.isoformat(), week_end.isoformat())
    ).fetchone()['count']

    # Check-ins done this week
    checkins_done = conn.execute(
        """SELECT COUNT(*) as count FROM daily_checkins
           WHERE user_id = ? AND date >= ? AND date <= ?""",
        (uid, week_start.isoformat(), week_end.isoformat())
    ).fetchone()['count']

    # Points earned this week
    points_earned = conn.execute(
        """SELECT SUM(points) as total FROM point_ledger
           WHERE user_id = ? AND date(timestamp) >= ? AND date(timestamp) <= ?""",
        (uid, week_start.isoformat(), week_end.isoformat())
    ).fetchone()['total'] or 0

    # Sobriety streak scoped to this user
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

    # Walks this week
    walks = conn.execute(
        """SELECT COUNT(*) as count, SUM(distance_km) as km FROM walk_logs
           WHERE user_id = ? AND date(logged_at) >= ? AND date(logged_at) <= ?""",
        (uid, week_start.isoformat(), week_end.isoformat())
    ).fetchone()

    return jsonify({
        'period': {
            'start': week_start.isoformat(),
            'end': week_end.isoformat()
        },
        'habits_completed': habits_completed,
        'checkins_done': checkins_done,
        'points_earned': int(points_earned),
        'sobriety_days': sobriety,
        'walks': walks['count'] or 0,
        'walk_km': round(walks['km'] or 0, 1)
    })


@reports_bp.route('/streaks')
@login_required
def get_streaks():
    """Get current streaks for all habits."""
    uid = current_user_id()
    conn = get_connection()

    habit_rows = conn.execute(
        "SELECT id, name, category FROM habits WHERE user_id = ? AND active = 1 ORDER BY category, name",
        (uid,)
    ).fetchall()

    streaks = []
    for h in habit_rows:
        # Calculate streak for this user's habit
        rows = conn.execute(
            """SELECT DISTINCT date(completed_at) as d FROM habit_completions
               WHERE user_id = ? AND habit_id = ? AND status = 'complete'
               ORDER BY d DESC LIMIT 365""",
            (uid, h['id'])
        ).fetchall()

        streak = 0
        expected = date.today()
        for row in rows:
            completion_date = date.fromisoformat(row['d'])
            if completion_date == expected:
                streak += 1
                expected = date.fromordinal(expected.toordinal() - 1)
            elif completion_date < expected:
                break

        if streak > 0:
            streaks.append({
                'habit_id': h['id'],
                'habit_name': h['name'],
                'category': h['category'],
                'streak': streak
            })

    # Sort by streak descending
    streaks.sort(key=lambda x: x['streak'], reverse=True)

    return jsonify(streaks)


@reports_bp.route('/points/history')
@login_required
def points_history():
    """Get points history."""
    uid = current_user_id()
    days = int(request.args.get('days', 30))

    conn = get_connection()
    rows = conn.execute(
        """SELECT date(timestamp) as date, SUM(points) as total, category
           FROM point_ledger
           WHERE user_id = ? AND date(timestamp) >= date('now', ?)
           GROUP BY date(timestamp), category
           ORDER BY date(timestamp) DESC""",
        (uid, f'-{days} days')
    ).fetchall()

    return jsonify([{
        'date': r['date'],
        'points': r['total'],
        'category': r['category']
    } for r in rows])
