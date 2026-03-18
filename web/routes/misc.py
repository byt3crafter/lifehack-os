"""Misc routes (stats, insights, categories, daily, replacements, fasting, wishlist, deepwork)."""
from flask import Blueprint, jsonify, request
from datetime import date, datetime, timedelta

from .decorators import login_required
from src.domain.entities import ReplacementLog
from src.infrastructure.database import get_connection
from src.infrastructure.database.repositories import (
    HabitRepository, CheckinRepository, ReplacementRepository, StatsRepository
)
from src.infrastructure.config import load_config
from src.infrastructure.providers import get_calendar_provider, get_firefly_provider

misc_bp = Blueprint('misc', __name__, url_prefix='/api')

habit_repo = HabitRepository()
checkin_repo = CheckinRepository()
replacement_repo = ReplacementRepository()
stats_repo = StatsRepository()
config = load_config()


# ============== STATS ==============
@misc_bp.route('/stats')
@login_required
def get_stats():
    stats = stats_repo.get_stats()
    sobriety = checkin_repo.get_sobriety_streak()
    return jsonify({
        'total_xp': stats.total_xp,
        'level': stats.level,
        'level_name': config.get_level_name(stats.level),
        'xp_for_next': stats.xp_for_next_level(config.levels.xp_per_level),
        'sobriety_days': sobriety
    })


# ============== INSIGHTS ==============
@misc_bp.route('/insights')
@login_required
def get_insights():
    conn = get_connection()
    rows = conn.execute(
        'SELECT * FROM ai_insights WHERE dismissed = 0 ORDER BY priority DESC, created_at DESC LIMIT 5'
    ).fetchall()
    return jsonify([{
        'id': r['id'],
        'type': r['insight_type'],
        'title': r['title'],
        'content': r['content'],
        'created_at': r['created_at']
    } for r in rows])


@misc_bp.route('/insights/<int:insight_id>/dismiss', methods=['POST'])
@login_required
def dismiss_insight(insight_id):
    conn = get_connection()
    conn.execute('UPDATE ai_insights SET dismissed = 1 WHERE id = ?', (insight_id,))
    conn.commit()
    return jsonify({'success': True})


# ============== CATEGORIES ==============
@misc_bp.route('/categories')
@login_required
def get_categories():
    return jsonify({k: {'name': v.name, 'color': v.color, 'icon': v.icon} for k, v in config.categories.items()})


# ============== DAILY TRACKING ==============
@misc_bp.route('/daily')
@login_required
def get_daily_summary():
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    
    conn = get_connection()
    
    def get_day_stats(d):
        habits = habit_repo.get_all()
        completions = conn.execute(
            "SELECT habit_id FROM habit_completions WHERE date(completed_at) = ?", (d,)
        ).fetchall()
        completed_ids = {r['habit_id'] for r in completions}
        
        checkin = conn.execute(
            "SELECT * FROM daily_checkins WHERE date = ?", (d,)
        ).fetchone()
        
        food_count = conn.execute(
            "SELECT COUNT(*) as c FROM food_logs WHERE date(logged_at) = ?", (d,)
        ).fetchone()['c']
        
        walks = conn.execute(
            "SELECT COUNT(*) as c, SUM(distance_km) as km FROM walk_logs WHERE date(logged_at) = ?", (d,)
        ).fetchone()
        
        points = conn.execute(
            "SELECT SUM(points) as p FROM point_ledger WHERE date(timestamp) = ?", (d,)
        ).fetchone()
        
        habits_pct = (len(completed_ids) / len(habits) * 100) if habits else 0
        checkin_done = 1 if checkin else 0
        food_done = 1 if food_count >= 2 else 0
        movement_done = 1 if walks['c'] >= 1 else 0
        score = int((habits_pct * 0.4) + (checkin_done * 20) + (food_done * 20) + (movement_done * 20))
        
        return {
            'date': d,
            'habits_completed': len(completed_ids),
            'habits_total': len(habits),
            'habits_pct': int(habits_pct),
            'checkin_done': checkin_done,
            'mood': checkin['mood'] if checkin else None,
            'energy': checkin['energy'] if checkin else None,
            'avoided_alcohol': checkin['avoided_alcohol'] if checkin else None,
            'food_logged': food_count,
            'walks': walks['c'] or 0,
            'walk_km': walks['km'] or 0,
            'points': points['p'] or 0,
            'score': min(100, score)
        }
    
    today_stats = get_day_stats(today)
    yesterday_stats = get_day_stats(yesterday)
    
    deltas = {
        'habits': today_stats['habits_completed'] - yesterday_stats['habits_completed'],
        'score': today_stats['score'] - yesterday_stats['score'],
        'points': today_stats['points'] - yesterday_stats['points']
    }
    
    tips = []
    if today_stats['habits_pct'] < 50:
        pending = today_stats['habits_total'] - today_stats['habits_completed']
        tips.append(f"💪 {pending} habits left today — pick one to knock out now")
    if not today_stats['checkin_done']:
        tips.append("📝 Don't forget your daily check-in")
    if today_stats['food_logged'] == 0:
        tips.append("🍽️ Log your meals to track nutrition")
    if today_stats['score'] < yesterday_stats['score']:
        tips.append("📈 Yesterday was better — time to step up!")
    
    return jsonify({
        'today': today_stats,
        'yesterday': yesterday_stats,
        'deltas': deltas,
        'tips': tips
    })


@misc_bp.route('/daily/history')
@login_required  
def get_daily_history():
    days = int(request.args.get('days', 7))
    history = []
    
    conn = get_connection()
    habits = habit_repo.get_all()
    
    for i in range(days):
        d = (date.today() - timedelta(days=i)).isoformat()
        
        completions = conn.execute(
            "SELECT COUNT(*) as c FROM habit_completions WHERE date(completed_at) = ?", (d,)
        ).fetchone()['c']
        
        checkin = conn.execute(
            "SELECT id FROM daily_checkins WHERE date = ?", (d,)
        ).fetchone()
        
        habits_pct = (completions / len(habits) * 100) if habits else 0
        score = int((habits_pct * 0.5) + (25 if checkin else 0) + 25)
        
        history.append({
            'date': d,
            'habits': completions,
            'checkin': 1 if checkin else 0,
            'score': min(100, score)
        })
    
    return jsonify(history)


# ============== REPLACEMENTS ==============
@misc_bp.route('/replacements')
@login_required
def get_replacements():
    actions = replacement_repo.get_all_actions()
    logs = replacement_repo.get_recent_logs(10)
    return jsonify({
        'actions': [{'id': a.id, 'name': a.name, 'category': a.category, 'points': a.points} for a in actions],
        'logs': [{'id': l.id, 'action_name': l.action_name, 'urge_level': l.urge_level,
                  'points': l.points_earned, 'date': l.logged_at.isoformat()} for l in logs]
    })


@misc_bp.route('/replacements', methods=['POST'])
@login_required
def log_replacement():
    data = request.json
    urge_level = data.get('urge_level', 3)
    points = config.replacements.urge_redirect_base + (config.replacements.high_urge_bonus if urge_level >= 4 else 0)
    log = ReplacementLog(action_id=data['action_id'], urge_level=urge_level, points_earned=points, notes=data.get('notes', ''))
    replacement_repo.log_replacement(log)
    stats_repo.add_points('replacement', points, f"Urge redirected (level {urge_level})", log.id)
    return jsonify({'success': True, 'points': points})


# ============== FASTING ==============
@misc_bp.route('/fasting/status')
@login_required
def get_fasting_status():
    conn = get_connection()
    active = conn.execute(
        "SELECT * FROM fasting_logs WHERE status = 'active' ORDER BY start_at DESC LIMIT 1"
    ).fetchone()
    
    last_completed = conn.execute(
        "SELECT * FROM fasting_logs WHERE status = 'completed' ORDER BY end_at DESC LIMIT 5"
    ).fetchall()
    
    return jsonify({
        'active': dict(active) if active else None,
        'history': [dict(r) for r in last_completed]
    })


@misc_bp.route('/fasting/start', methods=['POST'])
@login_required
def start_fast():
    data = request.json
    conn = get_connection()
    conn.execute("UPDATE fasting_logs SET status = 'cancelled' WHERE status = 'active'")
    
    cursor = conn.execute(
        "INSERT INTO fasting_logs (start_at, target_hours, mood_start) VALUES (?, ?, ?)",
        (datetime.now().isoformat(), data.get('target', 16), data.get('mood', 3))
    )
    conn.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid})


@misc_bp.route('/fasting/end', methods=['POST'])
@login_required
def end_fast():
    data = request.json
    conn = get_connection()
    active = conn.execute("SELECT id, start_at FROM fasting_logs WHERE status = 'active'").fetchone()
    if not active:
        return jsonify({'error': 'No active fast'}), 400
        
    end_at = datetime.now()
    start_at = datetime.fromisoformat(active['start_at'])
    duration = (end_at - start_at).total_seconds() / 3600
    
    conn.execute(
        "UPDATE fasting_logs SET end_at = ?, status = 'completed', mood_end = ?, notes = ? WHERE id = ?",
        (end_at.isoformat(), data.get('mood', 3), data.get('notes', ''), active['id'])
    )
    
    points = int(duration * 10)
    stats_repo.add_points('fasting', points, f"Completed {duration:.1f}h fast")
    conn.commit()
    return jsonify({'success': True, 'points': points, 'hours': round(duration, 1)})


@misc_bp.route('/fasting/cancel', methods=['POST'])
@login_required
def cancel_fast():
    """Cancel the active fast without awarding points."""
    conn = get_connection()
    result = conn.execute(
        "UPDATE fasting_logs SET status = 'cancelled', end_at = ? WHERE status = 'active'",
        (datetime.now().isoformat(),)
    )
    conn.commit()
    if result.rowcount == 0:
        return jsonify({'error': 'No active fast'}), 400
    return jsonify({'success': True})


# ============== WISHLIST ==============
@misc_bp.route('/wishlist')
@login_required
def get_wishlist():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM wishlist ORDER BY created_at DESC").fetchall()
    return jsonify([dict(r) for r in rows])


@misc_bp.route('/wishlist', methods=['POST'])
@login_required
def add_to_wishlist():
    data = request.json
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO wishlist (title, location, description, category) VALUES (?, ?, ?, ?)",
        (data['title'], data.get('location', ''), data.get('description', ''), data.get('category', 'place'))
    )
    conn.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid})


@misc_bp.route('/wishlist/<int:item_id>', methods=['PUT'])
@login_required
def update_wishlist_item(item_id):
    """Edit a wishlist item."""
    data = request.json
    conn = get_connection()
    row = conn.execute("SELECT id FROM wishlist WHERE id = ?", (item_id,)).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    conn.execute(
        """UPDATE wishlist SET title = ?, location = ?, description = ?, category = ?
           WHERE id = ?""",
        (data.get('title'), data.get('location', ''), data.get('description', ''),
         data.get('category', 'place'), item_id)
    )
    conn.commit()
    return jsonify({'success': True})


@misc_bp.route('/wishlist/<int:item_id>', methods=['DELETE'])
@login_required
def delete_wishlist_item(item_id):
    """Delete a wishlist item."""
    conn = get_connection()
    result = conn.execute("DELETE FROM wishlist WHERE id = ?", (item_id,))
    conn.commit()
    if result.rowcount == 0:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'success': True})


@misc_bp.route('/wishlist/<int:item_id>/complete', methods=['POST'])
@login_required
def complete_wishlist_item(item_id):
    """Mark a wishlist item as visited/completed."""
    conn = get_connection()
    row = conn.execute("SELECT id FROM wishlist WHERE id = ?", (item_id,)).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    conn.execute("UPDATE wishlist SET completed = 1 WHERE id = ?", (item_id,))
    conn.commit()
    return jsonify({'success': True})


# ============== DEEP WORK ==============
@misc_bp.route('/deepwork/status')
@login_required
def get_deepwork_status():
    conn = get_connection()
    active = conn.execute(
        """SELECT dw.*, p.name as project_name FROM deep_work_sessions dw 
           LEFT JOIN projects p ON dw.project_id = p.id 
           WHERE dw.ended_at IS NULL ORDER BY dw.started_at DESC LIMIT 1"""
    ).fetchone()
    
    history = conn.execute(
        """SELECT dw.*, p.name as project_name FROM deep_work_sessions dw 
           LEFT JOIN projects p ON dw.project_id = p.id 
           WHERE dw.ended_at IS NOT NULL ORDER BY dw.ended_at DESC LIMIT 5"""
    ).fetchall()
    
    return jsonify({
        'active': dict(active) if active else None,
        'history': [dict(r) for r in history]
    })


@misc_bp.route('/deepwork/start', methods=['POST'])
@login_required
def start_deepwork():
    data = request.json
    conn = get_connection()
    conn.execute("UPDATE deep_work_sessions SET ended_at = CURRENT_TIMESTAMP WHERE ended_at IS NULL")
    
    cursor = conn.execute(
        "INSERT INTO deep_work_sessions (project_id, notes) VALUES (?, ?)",
        (data.get('project_id'), data.get('notes', ''))
    )
    conn.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid})


@misc_bp.route('/deepwork/end', methods=['POST'])
@login_required
def end_deepwork():
    conn = get_connection()
    active = conn.execute("SELECT id, started_at FROM deep_work_sessions WHERE ended_at IS NULL").fetchone()
    if not active:
        return jsonify({'error': 'No active session'}), 400
        
    start_at = datetime.fromisoformat(active['started_at'].replace(' ', 'T'))
    end_at = datetime.now()
    duration = int((end_at - start_at).total_seconds() / 60)
    
    points = int(duration / 10) * 5
    
    conn.execute(
        "UPDATE deep_work_sessions SET ended_at = ?, duration_minutes = ?, points_earned = ? WHERE id = ?",
        (end_at.isoformat(), duration, points, active['id'])
    )
    stats_repo.add_points('deepwork', points, f"Deep Work: {duration} mins")
    conn.commit()
    return jsonify({'success': True, 'duration': duration, 'points': points})


# ============== CALENDAR ==============
@misc_bp.route('/calendar/events')
@login_required
def get_calendar_events():
    provider = get_calendar_provider()
    if not provider:
        return jsonify({'enabled': False, 'events': []})
    
    days = int(request.args.get('days', 7))
    events = provider.get_events(days_ahead=days)
    
    return jsonify({
        'enabled': True,
        'events': [{
            'id': e.id,
            'title': e.title,
            'start': e.start.isoformat(),
            'end': e.end.isoformat(),
            'location': e.location,
            'all_day': e.all_day
        } for e in events]
    })


# ============== FINANCE ==============
@misc_bp.route('/finance/summary')
@login_required
def get_finance_summary():
    provider = get_firefly_provider()
    if not provider:
        return jsonify({'enabled': False})
    
    balance = provider.get_balance()
    transactions = provider.get_recent_transactions(5)
    
    return jsonify({
        'enabled': True,
        'balance': balance,
        'recent_transactions': [{
            'id': t.id,
            'description': t.description,
            'amount': t.amount,
            'type': t.type,
            'date': t.date.isoformat(),
            'category': t.category
        } for t in transactions]
    })


@misc_bp.route('/finance/transaction', methods=['POST'])
@login_required
def add_transaction():
    provider = get_firefly_provider()
    if not provider:
        return jsonify({'error': 'Firefly not enabled'}), 400
    
    data = request.json
    tx_type = data.get('type', 'withdrawal')
    amount = float(data.get('amount', 0))
    description = data.get('description', '')
    category = data.get('category')
    
    if tx_type == 'deposit':
        success = provider.add_deposit(amount, description)
    else:
        success = provider.add_withdrawal(amount, description, category=category)
    
    if success:
        return jsonify({'success': True})
    return jsonify({'error': 'Failed to add transaction'}), 400
