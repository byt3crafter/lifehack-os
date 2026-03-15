"""Reports and analytics routes."""
from flask import Blueprint, jsonify, request
from datetime import date, timedelta

from .decorators import login_required
from src.infrastructure.database import get_connection
from src.infrastructure.database.repositories import HabitRepository, CheckinRepository

reports_bp = Blueprint('reports', __name__, url_prefix='/api/reports')

habit_repo = HabitRepository()
checkin_repo = CheckinRepository()


@reports_bp.route('/weekly')
@login_required
def weekly_report():
    """Get weekly summary report."""
    conn = get_connection()
    
    # Calculate date range
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    # Habits completed this week
    habits_completed = conn.execute(
        """SELECT COUNT(*) as count FROM habit_completions 
           WHERE date(completed_at) >= ? AND date(completed_at) <= ?""",
        (week_start.isoformat(), week_end.isoformat())
    ).fetchone()['count']
    
    # Check-ins done this week
    checkins_done = conn.execute(
        """SELECT COUNT(*) as count FROM daily_checkins 
           WHERE date >= ? AND date <= ?""",
        (week_start.isoformat(), week_end.isoformat())
    ).fetchone()['count']
    
    # Points earned this week
    points_earned = conn.execute(
        """SELECT SUM(points) as total FROM point_ledger 
           WHERE date(timestamp) >= ? AND date(timestamp) <= ?""",
        (week_start.isoformat(), week_end.isoformat())
    ).fetchone()['total'] or 0
    
    # Sobriety days
    sobriety = checkin_repo.get_sobriety_streak()
    
    # Walks this week
    walks = conn.execute(
        """SELECT COUNT(*) as count, SUM(distance_km) as km FROM walk_logs 
           WHERE date(logged_at) >= ? AND date(logged_at) <= ?""",
        (week_start.isoformat(), week_end.isoformat())
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
    habits = habit_repo.get_all()
    streaks = []
    
    for h in habits:
        streak = habit_repo.get_streak(h.id)
        if streak > 0:
            streaks.append({
                'habit_id': h.id,
                'habit_name': h.name,
                'category': h.category,
                'streak': streak
            })
    
    # Sort by streak descending
    streaks.sort(key=lambda x: x['streak'], reverse=True)
    
    return jsonify(streaks)


@reports_bp.route('/points/history')
@login_required
def points_history():
    """Get points history."""
    days = int(request.args.get('days', 30))
    
    conn = get_connection()
    rows = conn.execute(
        """SELECT date(timestamp) as date, SUM(points) as total, category
           FROM point_ledger 
           WHERE date(timestamp) >= date('now', ?)
           GROUP BY date(timestamp), category
           ORDER BY date(timestamp) DESC""",
        (f'-{days} days',)
    ).fetchall()
    
    return jsonify([{
        'date': r['date'],
        'points': r['total'],
        'category': r['category']
    } for r in rows])
