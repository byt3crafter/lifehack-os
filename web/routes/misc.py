"""Misc routes (stats, insights, categories, daily, replacements, fasting, wishlist, deepwork)."""
from flask import Blueprint, jsonify, request
from datetime import date, datetime, timedelta

from .decorators import login_required, current_user_id
from src.domain.entities import ReplacementLog
from src.infrastructure.database import get_connection
from src.infrastructure.database.repositories import (
    HabitRepository, CheckinRepository, ReplacementRepository, StatsRepository
)
from src.infrastructure.config import load_config
from src.infrastructure.providers import get_firefly_provider

misc_bp = Blueprint('misc', __name__, url_prefix='/api')

config = load_config()


# ============== STATS ==============
@misc_bp.route('/stats')
@login_required
def get_stats():
    uid = current_user_id()
    conn = get_connection()

    row = conn.execute(
        "SELECT total_xp, level FROM user_stats WHERE user_id = ?", (uid,)
    ).fetchone()
    total_xp = row['total_xp'] if row else 0
    level = row['level'] if row else 1

    # Sobriety streak scoped to this user
    rows = conn.execute(
        """SELECT date, avoided_alcohol FROM daily_checkins
           WHERE user_id = ? ORDER BY date DESC LIMIT 365""",
        (uid,)
    ).fetchall()
    sobriety = 0
    for r in rows:
        if r['avoided_alcohol']:
            sobriety += 1
        else:
            break

    from src.domain.entities import UserStats
    stats = UserStats(id=uid, total_xp=total_xp, level=level)

    return jsonify({
        'total_xp': total_xp,
        'level': level,
        'level_name': config.get_level_name(level),
        'xp_for_next': stats.xp_for_next_level(config.levels.xp_per_level),
        'sobriety_days': sobriety
    })


# ============== INSIGHTS ==============
@misc_bp.route('/insights')
@login_required
def get_insights():
    uid = current_user_id()
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM ai_insights
           WHERE dismissed = 0 AND user_id = ?
           ORDER BY priority DESC, created_at DESC LIMIT 5""",
        (uid,)
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
    uid = current_user_id()
    conn = get_connection()
    conn.execute(
        'UPDATE ai_insights SET dismissed = 1 WHERE id = ? AND user_id = ?',
        (insight_id, uid)
    )
    conn.commit()
    return jsonify({'success': True})


def _get_todays_insight(conn, uid: int):
    """Return today's daily_briefing insight row for the user, or None."""
    return conn.execute(
        """SELECT id, insight_type, title, content, created_at
           FROM ai_insights
           WHERE user_id = ? AND insight_type = 'daily_briefing'
             AND date(created_at) = date('now')
           ORDER BY created_at DESC LIMIT 1""",
        (uid,),
    ).fetchone()


def _build_insight_context(conn, uid: int) -> str:
    """Gather key data points and return a concise context string for the AI."""
    today = date.today().isoformat()

    # Habit completions today vs total
    total_habits = conn.execute(
        "SELECT COUNT(*) as c FROM habits WHERE user_id = ? AND active = 1", (uid,)
    ).fetchone()['c']
    completed_habits = conn.execute(
        "SELECT COUNT(*) as c FROM habit_completions WHERE user_id = ? AND date(completed_at) = ?",
        (uid, today),
    ).fetchone()['c']

    # Top streaks
    streaks_rows = conn.execute(
        """SELECT hs.strength, hs.total_completions, h.name
           FROM habit_strength hs
           JOIN habits h ON h.id = hs.habit_id
           WHERE h.user_id = ? AND h.active = 1
           ORDER BY hs.strength DESC LIMIT 3""",
        (uid,),
    ).fetchall()
    streaks_info = "; ".join(
        f"{r['name']} ({r['strength']:.0f}% strength, {r['total_completions']} completions)"
        for r in streaks_rows
    ) if streaks_rows else "no habit data"

    # Calorie total today
    cal_row = conn.execute(
        "SELECT SUM(calories) as total FROM food_logs WHERE user_id = ? AND date(logged_at) = ?",
        (uid, today),
    ).fetchone()
    calories_today = int(cal_row['total'] or 0)

    # Active fast
    active_fast = conn.execute(
        "SELECT start_at, target_hours FROM fasting_logs WHERE user_id = ? AND status = 'active' ORDER BY start_at DESC LIMIT 1",
        (uid,),
    ).fetchone()
    fast_info = (
        f"active fast started {active_fast['start_at'][:16]}, target {active_fast['target_hours']}h"
        if active_fast else "no active fast"
    )

    # Budget over-spend (local finance_log vs finance_rules)
    over_budget = conn.execute(
        """SELECT fr.category, fr.monthly_limit, SUM(fl.amount) as spent
           FROM finance_rules fr
           LEFT JOIN finance_log fl
             ON fl.category = fr.category
            AND fl.user_id = fr.user_id
            AND strftime('%Y-%m', fl.date) = strftime('%Y-%m', 'now')
           WHERE fr.user_id = ? AND fr.active = 1
           GROUP BY fr.category, fr.monthly_limit
           HAVING spent > fr.monthly_limit""",
        (uid,),
    ).fetchall()
    budget_info = (
        "; ".join(f"{r['category']} over by {r['spent'] - r['monthly_limit']:.2f}" for r in over_budget)
        if over_budget else "all budgets on track"
    )

    # Recent mood trend (last 3 check-ins)
    mood_rows = conn.execute(
        "SELECT mood, energy, date FROM daily_checkins WHERE user_id = ? ORDER BY date DESC LIMIT 3",
        (uid,),
    ).fetchall()
    mood_info = "; ".join(
        f"{r['date']}: mood={r['mood']}, energy={r['energy']}"
        for r in mood_rows
    ) if mood_rows else "no mood data"

    return (
        f"Habits today: {completed_habits}/{total_habits} completed. "
        f"Top habits: {streaks_info}. "
        f"Calories today: {calories_today} kcal. "
        f"Fasting: {fast_info}. "
        f"Budget: {budget_info}. "
        f"Recent mood: {mood_info}."
    )


@misc_bp.route('/insights/generate', methods=['POST'])
@login_required
def generate_insight():
    """Generate a daily AI briefing insight if one hasn't been created today."""
    uid = current_user_id()
    conn = get_connection()

    # Return existing insight if already generated today
    existing = _get_todays_insight(conn, uid)
    if existing:
        return jsonify({
            'id': existing['id'],
            'type': existing['insight_type'],
            'title': existing['title'],
            'content': existing['content'],
            'created_at': existing['created_at'],
            'generated': False,
        })

    # Gather context and call AI
    context_str = _build_insight_context(conn, uid)

    try:
        from src.infrastructure.ai import get_ai_provider
        provider = get_ai_provider('insights', user_id=uid)
    except Exception:
        return jsonify({'error': 'AI provider not available'}), 503

    if not provider or not provider.is_available():
        return jsonify({'error': 'AI provider not configured'}), 503

    try:
        insight = provider.generate_insight({'summary': context_str, 'type': 'daily_briefing'})
    except Exception as exc:
        return jsonify({'error': f'AI generation failed: {exc}'}), 500

    if not insight:
        return jsonify({'error': 'AI returned no insight'}), 500

    cursor = conn.execute(
        """INSERT INTO ai_insights (user_id, insight_type, title, content, priority)
           VALUES (?, 'daily_briefing', ?, ?, 1)""",
        (uid, insight.title, insight.content),
    )
    conn.commit()
    insight_id = cursor.lastrowid

    return jsonify({
        'id': insight_id,
        'type': 'daily_briefing',
        'title': insight.title,
        'content': insight.content,
        'created_at': datetime.utcnow().isoformat(),
        'generated': True,
    }), 201


@misc_bp.route('/insights/today', methods=['GET'])
@login_required
def get_todays_insight():
    """Return today's daily briefing, generating it on the fly if absent."""
    uid = current_user_id()
    conn = get_connection()

    existing = _get_todays_insight(conn, uid)
    if existing:
        return jsonify({
            'id': existing['id'],
            'type': existing['insight_type'],
            'title': existing['title'],
            'content': existing['content'],
            'created_at': existing['created_at'],
            'generated': False,
        })

    # No insight yet today — trigger generation
    return generate_insight()


# ============== CATEGORIES ==============
@misc_bp.route('/categories')
@login_required
def get_categories():
    return jsonify({k: {'name': v.name, 'color': v.color, 'icon': v.icon} for k, v in config.categories.items()})


# ============== DAILY TRACKING ==============
@misc_bp.route('/daily')
@login_required
def get_daily_summary():
    uid = current_user_id()
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    conn = get_connection()

    # Trigger habit strength decay for uncompleted habits
    try:
        from web.routes.habits import _apply_daily_decay
        _apply_daily_decay(conn)
    except Exception:
        pass

    def get_day_stats(d):
        habits = conn.execute(
            "SELECT id FROM habits WHERE user_id = ? AND active = 1", (uid,)
        ).fetchall()
        habit_ids = [h['id'] for h in habits]

        completions = conn.execute(
            "SELECT habit_id FROM habit_completions WHERE user_id = ? AND date(completed_at) = ?",
            (uid, d)
        ).fetchall()
        completed_ids = {r['habit_id'] for r in completions}

        checkin = conn.execute(
            "SELECT * FROM daily_checkins WHERE user_id = ? AND date = ?", (uid, d)
        ).fetchone()

        food_count = conn.execute(
            "SELECT COUNT(*) as c FROM food_logs WHERE user_id = ? AND date(logged_at) = ?",
            (uid, d)
        ).fetchone()['c']

        walks = conn.execute(
            "SELECT COUNT(*) as c, SUM(distance_km) as km FROM walk_logs WHERE user_id = ? AND date(logged_at) = ?",
            (uid, d)
        ).fetchone()

        points = conn.execute(
            "SELECT SUM(points) as p FROM point_ledger WHERE user_id = ? AND date(timestamp) = ?",
            (uid, d)
        ).fetchone()

        habits_pct = (len(completed_ids) / len(habit_ids) * 100) if habit_ids else 0
        checkin_done = 1 if checkin else 0
        food_done = 1 if food_count >= 2 else 0
        movement_done = 1 if walks['c'] >= 1 else 0
        score = int((habits_pct * 0.4) + (checkin_done * 20) + (food_done * 20) + (movement_done * 20))

        return {
            'date': d,
            'habits_completed': len(completed_ids),
            'habits_total': len(habit_ids),
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
    uid = current_user_id()
    days = int(request.args.get('days', 7))
    history = []

    conn = get_connection()
    habit_ids = [
        r['id'] for r in conn.execute(
            "SELECT id FROM habits WHERE user_id = ? AND active = 1", (uid,)
        ).fetchall()
    ]

    for i in range(days):
        d = (date.today() - timedelta(days=i)).isoformat()

        completions = conn.execute(
            "SELECT COUNT(*) as c FROM habit_completions WHERE user_id = ? AND date(completed_at) = ?",
            (uid, d)
        ).fetchone()['c']

        checkin = conn.execute(
            "SELECT id FROM daily_checkins WHERE user_id = ? AND date = ?", (uid, d)
        ).fetchone()

        habits_pct = (completions / len(habit_ids) * 100) if habit_ids else 0
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
    uid = current_user_id()
    conn = get_connection()

    action_rows = conn.execute(
        "SELECT * FROM replacement_actions WHERE user_id = ? AND active = 1 ORDER BY category, name",
        (uid,)
    ).fetchall()

    log_rows = conn.execute(
        """SELECT rl.*, ra.name as action_name
           FROM replacement_logs rl
           JOIN replacement_actions ra ON rl.action_id = ra.id
           WHERE rl.user_id = ?
           ORDER BY rl.logged_at DESC LIMIT 10""",
        (uid,)
    ).fetchall()

    return jsonify({
        'actions': [{'id': r['id'], 'name': r['name'], 'category': r['category'], 'points': r['points']}
                    for r in action_rows],
        'logs': [{'id': r['id'], 'action_name': r['action_name'], 'urge_level': r['urge_level'],
                  'points': r['points_earned'], 'date': r['logged_at']} for r in log_rows]
    })


@misc_bp.route('/replacements', methods=['POST'])
@login_required
def log_replacement():
    uid = current_user_id()
    data = request.json
    urge_level = data.get('urge_level', 3)
    points = config.replacements.urge_redirect_base + (config.replacements.high_urge_bonus if urge_level >= 4 else 0)

    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO replacement_logs (user_id, action_id, urge_level, points_earned, notes)
           VALUES (?, ?, ?, ?, ?)""",
        (uid, data['action_id'], urge_level, points, data.get('notes', ''))
    )
    log_id = cursor.lastrowid
    conn.execute(
        "UPDATE user_stats SET total_xp = total_xp + ? WHERE user_id = ?", (points, uid)
    )
    conn.execute(
        """INSERT INTO point_ledger (user_id, source_type, source_id, points, reason)
           VALUES (?, 'replacement', ?, ?, ?)""",
        (uid, log_id, points, f"Urge redirected (level {urge_level})")
    )
    conn.commit()
    return jsonify({'success': True, 'points': points})


# ============== FASTING ==============
@misc_bp.route('/fasting/status')
@login_required
def get_fasting_status():
    uid = current_user_id()
    conn = get_connection()
    active = conn.execute(
        "SELECT * FROM fasting_logs WHERE user_id = ? AND status = 'active' ORDER BY start_at DESC LIMIT 1",
        (uid,)
    ).fetchone()

    last_completed = conn.execute(
        """SELECT * FROM fasting_logs
           WHERE user_id = ? AND status IN ('completed','cancelled')
           ORDER BY end_at DESC LIMIT 30""",
        (uid,)
    ).fetchall()

    return jsonify({
        'active': dict(active) if active else None,
        'history': [dict(r) for r in last_completed]
    })


@misc_bp.route('/fasting/start', methods=['POST'])
@login_required
def start_fast():
    uid = current_user_id()
    data = request.json
    conn = get_connection()
    conn.execute(
        "UPDATE fasting_logs SET status = 'cancelled' WHERE user_id = ? AND status = 'active'",
        (uid,)
    )
    cursor = conn.execute(
        "INSERT INTO fasting_logs (user_id, start_at, target_hours, mood_start) VALUES (?, ?, ?, ?)",
        (uid, datetime.now().isoformat(), data.get('target', 16), data.get('mood', 3))
    )
    conn.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid})


@misc_bp.route('/fasting/end', methods=['POST'])
@login_required
def end_fast():
    uid = current_user_id()
    data = request.json
    conn = get_connection()
    active = conn.execute(
        "SELECT id, start_at FROM fasting_logs WHERE user_id = ? AND status = 'active'",
        (uid,)
    ).fetchone()
    if not active:
        return jsonify({'error': 'No active fast'}), 400

    end_at = datetime.now()
    start_at = datetime.fromisoformat(active['start_at'])
    duration = (end_at - start_at).total_seconds() / 3600

    conn.execute(
        "UPDATE fasting_logs SET end_at = ?, status = 'completed', mood_end = ?, notes = ? WHERE id = ? AND user_id = ?",
        (end_at.isoformat(), data.get('mood', 3), data.get('notes', ''), active['id'], uid)
    )

    points = int(duration * 10)
    conn.execute(
        "UPDATE user_stats SET total_xp = total_xp + ? WHERE user_id = ?", (points, uid)
    )
    conn.execute(
        """INSERT INTO point_ledger (user_id, source_type, source_id, points, reason)
           VALUES (?, 'fasting', ?, ?, ?)""",
        (uid, active['id'], points, f"Completed {duration:.1f}h fast")
    )
    conn.commit()
    return jsonify({'success': True, 'points': points, 'hours': round(duration, 1)})


@misc_bp.route('/fasting/cancel', methods=['POST'])
@login_required
def cancel_fast():
    """Cancel the active fast without awarding points."""
    uid = current_user_id()
    conn = get_connection()
    result = conn.execute(
        "UPDATE fasting_logs SET status = 'cancelled', end_at = ? WHERE user_id = ? AND status = 'active'",
        (datetime.now().isoformat(), uid)
    )
    conn.commit()
    if result.rowcount == 0:
        return jsonify({'error': 'No active fast'}), 400
    return jsonify({'success': True})


@misc_bp.route('/fasting/<int:fast_id>', methods=['DELETE'])
@login_required
def delete_fast(fast_id):
    """Delete a fasting history entry (completed or cancelled only)."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT id, status FROM fasting_logs WHERE id = ? AND user_id = ?", (fast_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    if row['status'] == 'active':
        return jsonify({'error': 'Cannot delete an active fast — cancel it first'}), 400
    conn.execute("DELETE FROM fasting_logs WHERE id = ? AND user_id = ?", (fast_id, uid))
    conn.commit()
    return jsonify({'success': True})


@misc_bp.route('/fasting/clear-history', methods=['POST'])
@login_required
def clear_fasting_history():
    """Delete all completed/cancelled fasting logs (keeps active)."""
    uid = current_user_id()
    conn = get_connection()
    conn.execute(
        "DELETE FROM fasting_logs WHERE user_id = ? AND status != 'active'", (uid,)
    )
    conn.commit()
    return jsonify({'success': True})


# ============== WISHLIST ==============
@misc_bp.route('/wishlist')
@login_required
def get_wishlist():
    uid = current_user_id()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM wishlist WHERE user_id = ? ORDER BY created_at DESC", (uid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@misc_bp.route('/wishlist', methods=['POST'])
@login_required
def add_to_wishlist():
    uid = current_user_id()
    data = request.json
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO wishlist (user_id, title, location, description, category) VALUES (?, ?, ?, ?, ?)",
        (uid, data['title'], data.get('location', ''), data.get('description', ''), data.get('category', 'place'))
    )
    conn.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid})


@misc_bp.route('/wishlist/<int:item_id>', methods=['PUT'])
@login_required
def update_wishlist_item(item_id):
    """Edit a wishlist item."""
    uid = current_user_id()
    data = request.json
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM wishlist WHERE id = ? AND user_id = ?", (item_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    conn.execute(
        """UPDATE wishlist SET title = ?, location = ?, description = ?, category = ?
           WHERE id = ? AND user_id = ?""",
        (data.get('title'), data.get('location', ''), data.get('description', ''),
         data.get('category', 'place'), item_id, uid)
    )
    conn.commit()
    return jsonify({'success': True})


@misc_bp.route('/wishlist/<int:item_id>', methods=['DELETE'])
@login_required
def delete_wishlist_item(item_id):
    """Delete a wishlist item."""
    uid = current_user_id()
    conn = get_connection()
    result = conn.execute(
        "DELETE FROM wishlist WHERE id = ? AND user_id = ?", (item_id, uid)
    )
    conn.commit()
    if result.rowcount == 0:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'success': True})


@misc_bp.route('/wishlist/<int:item_id>/complete', methods=['POST'])
@login_required
def complete_wishlist_item(item_id):
    """Mark a wishlist item as visited/completed."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM wishlist WHERE id = ? AND user_id = ?", (item_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    conn.execute(
        "UPDATE wishlist SET completed = 1 WHERE id = ? AND user_id = ?", (item_id, uid)
    )
    conn.commit()
    return jsonify({'success': True})


# ============== DEEP WORK (backwards-compat shims) ==============
# These routes are kept so any existing clients that still call /api/deepwork/*
# via the misc blueprint continue to work. They delegate to the canonical
# implementations in web/routes/deepwork.py.

@misc_bp.route('/deepwork/status')
@login_required
def get_deepwork_status():
    from .deepwork import get_status
    return get_status()


@misc_bp.route('/deepwork/start', methods=['POST'])
@login_required
def start_deepwork():
    from .deepwork import start_session
    return start_session()


@misc_bp.route('/deepwork/end', methods=['POST'])
@login_required
def end_deepwork():
    from .deepwork import end_session
    return end_session()


# ============== CALENDAR ==============
@misc_bp.route('/calendar/events')
@login_required
def get_calendar_events():
    # Google Calendar integration has been removed.
    return jsonify({'enabled': False, 'events': []})


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
