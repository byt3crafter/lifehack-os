"""Check-in routes — includes /api/mood quick-log endpoints."""
from flask import Blueprint, jsonify, request
from datetime import date

from .decorators import login_required, current_user_id
from src.domain.entities import DailyCheckin
from src.infrastructure.database import get_connection
from src.infrastructure.config import load_config

checkins_bp = Blueprint('checkins', __name__, url_prefix='/api/checkin')

config = load_config()


@checkins_bp.route('')
@login_required
def get_checkin():
    uid = current_user_id()
    conn = get_connection()
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT * FROM daily_checkins WHERE date = ? AND user_id = ?",
        (today, uid),
    ).fetchone()
    if not row:
        return jsonify(None)
    return jsonify({
        'completed_today': row['completed_today'],
        'avoided_alcohol': bool(row['avoided_alcohol']),
        'worked_on_future': bool(row['worked_on_future']),
        'mood': row['mood'],
        'energy': row['energy'],
        'improvement_note': row['improvement_note'],
    })


@checkins_bp.route('', methods=['POST'])
@login_required
def save_checkin():
    uid = current_user_id()
    data = request.json
    conn = get_connection()
    today = date.today().isoformat()

    existing = conn.execute(
        "SELECT id FROM daily_checkins WHERE date = ? AND user_id = ?",
        (today, uid),
    ).fetchone()
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

    if is_new:
        cursor = conn.execute(
            """INSERT INTO daily_checkins
               (date, user_id, completed_today, avoided_alcohol, worked_on_future,
                mood, energy, improvement_note, points_earned)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (today, uid, checkin.completed_today, checkin.avoided_alcohol,
             checkin.worked_on_future, checkin.mood, checkin.energy,
             checkin.improvement_note, points),
        )
        checkin.id = cursor.lastrowid
    else:
        conn.execute(
            """UPDATE daily_checkins
               SET completed_today = ?, avoided_alcohol = ?, worked_on_future = ?,
                   mood = ?, energy = ?, improvement_note = ?, points_earned = ?
               WHERE date = ? AND user_id = ?""",
            (checkin.completed_today, checkin.avoided_alcohol, checkin.worked_on_future,
             checkin.mood, checkin.energy, checkin.improvement_note, points,
             today, uid),
        )
    conn.commit()

    if is_new:
        from src.infrastructure.database.repositories import StatsRepository
        stats_repo = StatsRepository(uid)
        stats_repo.add_points('checkin', points, "Daily check-in", checkin.id)

    return jsonify({'success': True, 'points': points})


# ---------------------------------------------------------------------------
# Dashboard mood/energy quick-log — replaces the standalone check-in module.
# Stored in the existing daily_checkins table so habit auto-verification
# (checkin_done, no_alcohol) keeps working unchanged.
# ---------------------------------------------------------------------------

mood_bp = Blueprint('mood', __name__, url_prefix='/api/mood')


@mood_bp.route('', methods=['POST'])
@login_required
def log_mood():
    """Quick mood log: {mood: 1-5, energy: 1-5, note: optional}.

    Creates a new daily_checkins row for today or updates mood/energy on an
    existing one.  All other checkin fields are left at their defaults so that
    a POST /api/mood never clobbers a full check-in submitted through the
    normal flow.
    """
    uid = current_user_id()
    data = request.json or {}
    mood = data.get('mood', 3)
    energy = data.get('energy', 3)
    note = (data.get('note') or '').strip()

    try:
        mood = int(mood)
        energy = int(energy)
    except (TypeError, ValueError):
        return jsonify({'error': 'mood and energy must be integers 1–5'}), 400

    if not (1 <= mood <= 5) or not (1 <= energy <= 5):
        return jsonify({'error': 'mood and energy must be between 1 and 5'}), 400

    conn = get_connection()
    today = date.today().isoformat()

    existing = conn.execute(
        "SELECT id FROM daily_checkins WHERE date = ? AND user_id = ?",
        (today, uid),
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE daily_checkins
               SET mood = ?, energy = ?, improvement_note = CASE WHEN ? != '' THEN ? ELSE improvement_note END
               WHERE date = ? AND user_id = ?""",
            (mood, energy, note, note, today, uid),
        )
    else:
        conn.execute(
            """INSERT INTO daily_checkins (date, user_id, mood, energy, improvement_note)
               VALUES (?, ?, ?, ?, ?)""",
            (today, uid, mood, energy, note),
        )

    conn.commit()
    return jsonify({'success': True})


@mood_bp.route('/today')
@login_required
def get_mood_today():
    """Return today's mood and energy, or null if not logged yet."""
    uid = current_user_id()
    conn = get_connection()
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT mood, energy, improvement_note FROM daily_checkins WHERE date = ? AND user_id = ?",
        (today, uid),
    ).fetchone()

    if not row:
        return jsonify(None)

    return jsonify({
        'mood': row['mood'],
        'energy': row['energy'],
        'note': row['improvement_note'],
        'date': today,
    })
