"""Notifications — in-app nudges, alerts, and cron-driven habit reminders."""
from flask import Blueprint, jsonify, request, session
from .decorators import login_required, current_user_id
from src.infrastructure.database import get_connection
import os

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')


# ── Helpers ─────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    d = dict(row)
    d['read'] = bool(d.get('read'))
    d['dismissed'] = bool(d.get('dismissed'))
    return d


def _already_generated_today(conn, user_id: int, notif_type: str, today_str: str) -> bool:
    """Return True if a notification of this type was already inserted today for the user."""
    row = conn.execute(
        "SELECT id FROM notifications WHERE user_id=? AND type=? AND date(created_at)=?",
        (user_id, notif_type, today_str),
    ).fetchone()
    return row is not None


# ── GET /api/notifications ───────────────────────────────────────────────────

@notifications_bp.route('', methods=['GET'])
@login_required
def list_notifications():
    user_id = current_user_id()
    conn = get_connection()

    rows = conn.execute(
        """SELECT * FROM notifications
           WHERE user_id=? AND dismissed=0
             AND (expires_at IS NULL OR expires_at > datetime('now'))
           ORDER BY created_at DESC
           LIMIT 20""",
        (user_id,),
    ).fetchall()

    unread_row = conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0 AND dismissed=0",
        (user_id,),
    ).fetchone()

    return jsonify({
        'notifications': [_row_to_dict(r) for r in rows],
        'unread_count': unread_row[0] if unread_row else 0,
    })


# ── GET /api/notifications/count ────────────────────────────────────────────

@notifications_bp.route('/count', methods=['GET'])
@login_required
def notification_count():
    user_id = current_user_id()
    conn = get_connection()

    row = conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0 AND dismissed=0",
        (user_id,),
    ).fetchone()

    return jsonify({'unread': row[0] if row else 0})


# ── POST /api/notifications/<id>/read ───────────────────────────────────────

@notifications_bp.route('/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_read(notif_id: int):
    user_id = current_user_id()
    conn = get_connection()

    conn.execute(
        "UPDATE notifications SET read=1 WHERE id=? AND user_id=?",
        (notif_id, user_id),
    )
    conn.commit()
    return jsonify({'ok': True})


# ── POST /api/notifications/read-all ────────────────────────────────────────

@notifications_bp.route('/read-all', methods=['POST'])
@login_required
def mark_all_read():
    user_id = current_user_id()
    conn = get_connection()

    conn.execute(
        "UPDATE notifications SET read=1 WHERE user_id=? AND read=0",
        (user_id,),
    )
    conn.commit()
    return jsonify({'ok': True})


# ── POST /api/notifications/<id>/dismiss ────────────────────────────────────

@notifications_bp.route('/<int:notif_id>/dismiss', methods=['POST'])
@login_required
def dismiss_notification(notif_id: int):
    user_id = current_user_id()
    conn = get_connection()

    conn.execute(
        "UPDATE notifications SET dismissed=1 WHERE id=? AND user_id=?",
        (notif_id, user_id),
    )
    conn.commit()
    return jsonify({'ok': True})


# ── POST /api/notifications/generate ────────────────────────────────────────

@notifications_bp.route('/generate', methods=['POST'])
def generate_nudges():
    """Cron endpoint — generates nudge notifications for all active users.

    Authenticated via X-Cron-Secret header matching LIFEHACK_CRON_SECRET env
    var.  Also accessible to logged-in admin users (for manual testing).
    """
    cron_secret = os.environ.get('LIFEHACK_CRON_SECRET', '')
    request_secret = request.headers.get('X-Cron-Secret', '')

    is_cron = cron_secret and request_secret == cron_secret
    is_admin = bool(session.get('is_admin') and session.get('user'))

    if not is_cron and not is_admin:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_connection()

    # Clean up notifications older than 30 days
    conn.execute("DELETE FROM notifications WHERE created_at < date('now', '-30 days')")
    conn.commit()

    # Process all active users
    users = conn.execute("SELECT id FROM users").fetchall()
    generated = 0

    for user_row in users:
        user_id = user_row['id']
        try:
            generated += _generate_for_user(conn, user_id)
        except Exception as exc:
            # Log but continue processing other users
            try:
                from web.routes.app_log import log_event
                log_event('error', 'notifications', f'nudge generation failed for user {user_id}: {exc}')
            except Exception:
                pass

    conn.commit()
    return jsonify({'ok': True, 'generated': generated})


def _generate_for_user(conn, user_id: int) -> int:
    """Run all nudge checks for one user. Returns count of notifications inserted."""
    from src.domain.services.chat_context import _user_now

    user_now = _user_now(conn, user_id)
    user_hour = user_now.hour
    today_str = user_now.date().isoformat()
    expires_at = today_str + 'T23:59:59'

    count = 0

    # ------------------------------------------------------------------
    # 1. Overdue habits (check at 10:00+)
    # ------------------------------------------------------------------
    if user_hour >= 10:
        overdue_habits = conn.execute(
            """SELECT h.id, h.name, h.scheduled_time FROM habits h
               WHERE h.user_id=? AND h.active=1 AND h.scheduled_time != ''
                 AND h.id NOT IN (
                     SELECT habit_id FROM habit_completions
                     WHERE user_id=? AND date(completed_at)=?
                 )
                 AND h.id NOT IN (
                     SELECT habit_id FROM habit_miss_log
                     WHERE user_id=? AND date=?
                 )""",
            (user_id, user_id, today_str, user_id, today_str),
        ).fetchall()

        for habit in overdue_habits:
            scheduled_time = habit['scheduled_time'] or ''
            # Parse the hour from the scheduled_time (HH:MM or H:MM format)
            try:
                sched_hour = int(scheduled_time.split(':')[0])
            except (ValueError, IndexError):
                continue

            if sched_hour >= user_hour:
                # Not yet overdue
                continue

            notif_type = f'habit_overdue_{habit["id"]}'
            if _already_generated_today(conn, user_id, notif_type, today_str):
                continue

            conn.execute(
                "INSERT INTO notifications (user_id, type, title, body, icon, link, expires_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    user_id,
                    notif_type,
                    f'Overdue habit: {habit["name"]}',
                    f'Your habit "{habit["name"]}" was scheduled at {scheduled_time} and is not done yet.',
                    'clock',
                    '/habits',
                    expires_at,
                ),
            )
            count += 1

    # ------------------------------------------------------------------
    # 2. Low water intake (check at 14:00+)
    # ------------------------------------------------------------------
    if user_hour >= 14:
        notif_type = 'low_water'
        if not _already_generated_today(conn, user_id, notif_type, today_str):
            water_row = conn.execute(
                "SELECT COALESCE(SUM(glasses), 0) FROM water_logs WHERE user_id=? AND date(logged_at)=?",
                (user_id, today_str),
            ).fetchone()
            glasses = water_row[0] if water_row else 0

            if glasses < 4:
                conn.execute(
                    "INSERT INTO notifications (user_id, type, title, body, icon, link, expires_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (
                        user_id,
                        notif_type,
                        'Low water intake',
                        f"You've only logged {int(glasses)} glass(es) of water today. Aim for at least 8.",
                        'droplet',
                        '/wellness',
                        expires_at,
                    ),
                )
                count += 1

    # ------------------------------------------------------------------
    # 3. No food logged (check at 12:00+)
    # ------------------------------------------------------------------
    if user_hour >= 12:
        notif_type = 'no_food_logged'
        if not _already_generated_today(conn, user_id, notif_type, today_str):
            food_row = conn.execute(
                "SELECT COUNT(*) FROM food_logs WHERE user_id=? AND date(logged_at)=?",
                (user_id, today_str),
            ).fetchone()
            food_count = food_row[0] if food_row else 0

            if food_count == 0:
                conn.execute(
                    "INSERT INTO notifications (user_id, type, title, body, icon, link, expires_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (
                        user_id,
                        notif_type,
                        'No meals logged today',
                        "You haven't logged any food yet today. Track your nutrition to stay on top of your goals.",
                        'utensils',
                        '/food',
                        expires_at,
                    ),
                )
                count += 1

    # ------------------------------------------------------------------
    # 4. Fasting near target (>= 90 % of target hours elapsed)
    # ------------------------------------------------------------------
    notif_type = 'fasting_near_target'
    if not _already_generated_today(conn, user_id, notif_type, today_str):
        fasting_rows = conn.execute(
            "SELECT id, start_at, target_hours FROM fasting_logs WHERE user_id=? AND end_at IS NULL",
            (user_id,),
        ).fetchall()

        for fast in fasting_rows:
            try:
                from datetime import datetime
                start_at = datetime.fromisoformat(fast['start_at'])
                elapsed_hours = (user_now.replace(tzinfo=None) - start_at.replace(tzinfo=None)).total_seconds() / 3600
                target_hours = float(fast['target_hours'] or 16)

                if elapsed_hours >= target_hours * 0.9:
                    pct = int((elapsed_hours / target_hours) * 100)
                    conn.execute(
                        "INSERT INTO notifications (user_id, type, title, body, icon, link, expires_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (
                            user_id,
                            notif_type,
                            'Fasting goal almost reached',
                            f"You are {pct}% through your {int(target_hours)}-hour fast. "
                            f"You've fasted {elapsed_hours:.1f} hours so far.",
                            'zap',
                            '/wellness',
                            expires_at,
                        ),
                    )
                    count += 1
                    break  # One fasting notification per user per day is enough
            except Exception:
                continue

    # ------------------------------------------------------------------
    # 5. Habit miss streak (2+ consecutive misses)
    # ------------------------------------------------------------------
    streak_habits = conn.execute(
        """SELECT hml.habit_id, h.name, hml.consecutive_misses
           FROM habit_miss_log hml
           JOIN habits h ON h.id = hml.habit_id
           WHERE hml.user_id=? AND hml.date=? AND hml.consecutive_misses >= 2""",
        (user_id, today_str),
    ).fetchall()

    for sh in streak_habits:
        notif_type = f'habit_miss_streak_{sh["habit_id"]}'
        if _already_generated_today(conn, user_id, notif_type, today_str):
            continue

        misses = sh['consecutive_misses']
        conn.execute(
            "INSERT INTO notifications (user_id, type, title, body, icon, link, expires_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                user_id,
                notif_type,
                f'Habit slipping: {sh["name"]}',
                f'You have missed "{sh["name"]}" {misses} days in a row. Get back on track today!',
                'alert-triangle',
                '/habits',
                expires_at,
            ),
        )
        count += 1

    return count
