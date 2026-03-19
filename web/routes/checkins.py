"""Check-in routes — includes /api/mood quick-log endpoints."""
from flask import Blueprint, jsonify, request
from datetime import date

from .decorators import login_required
from src.domain.entities import DailyCheckin
from src.infrastructure.database.repositories import CheckinRepository, StatsRepository
from src.infrastructure.database import get_connection
from src.infrastructure.config import load_config

checkins_bp = Blueprint('checkins', __name__, url_prefix='/api/checkin')

checkin_repo = CheckinRepository()
stats_repo = StatsRepository()
config = load_config()


@checkins_bp.route('')
@login_required
def get_checkin():
    checkin = checkin_repo.get_for_date(date.today())
    if not checkin:
        return jsonify(None)
    return jsonify({
        'completed_today': checkin.completed_today,
        'avoided_alcohol': checkin.avoided_alcohol,
        'worked_on_future': checkin.worked_on_future,
        'mood': checkin.mood,
        'energy': checkin.energy,
        'improvement_note': checkin.improvement_note
    })


@checkins_bp.route('', methods=['POST'])
@login_required
def save_checkin():
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
        "SELECT id FROM daily_checkins WHERE date = ?", (today,)
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE daily_checkins
               SET mood = ?, energy = ?, improvement_note = CASE WHEN ? != '' THEN ? ELSE improvement_note END
               WHERE date = ?""",
            (mood, energy, note, note, today),
        )
    else:
        conn.execute(
            """INSERT INTO daily_checkins (date, mood, energy, improvement_note)
               VALUES (?, ?, ?, ?)""",
            (today, mood, energy, note),
        )

    conn.commit()
    return jsonify({'success': True})


@mood_bp.route('/today')
@login_required
def get_mood_today():
    """Return today's mood and energy, or null if not logged yet."""
    conn = get_connection()
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT mood, energy, improvement_note FROM daily_checkins WHERE date = ?",
        (today,),
    ).fetchone()

    if not row:
        return jsonify(None)

    return jsonify({
        'mood': row['mood'],
        'energy': row['energy'],
        'note': row['improvement_note'],
        'date': today,
    })
