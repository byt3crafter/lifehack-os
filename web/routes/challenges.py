"""Challenges / Streak Tracker routes."""
from flask import Blueprint, jsonify, request
from datetime import datetime, date, timedelta

from .decorators import login_required, current_user_id
from src.infrastructure.database import get_connection

challenges_bp = Blueprint('challenges', __name__, url_prefix='/api/challenges')


def init_challenges_table():
    """Create challenges table if not exists."""
    conn = get_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS challenges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT DEFAULT 'general',
        target_days INTEGER,
        start_date TEXT NOT NULL,
        end_date TEXT,
        status TEXT DEFAULT 'active',
        check_in_frequency TEXT DEFAULT 'daily',
        last_check_in TEXT,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS challenge_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        challenge_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        note TEXT,
        logged_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (challenge_id) REFERENCES challenges(id)
    )''')
    conn.commit()


def get_challenge_stats(challenge):
    """Calculate streak and progress for a challenge."""
    start = datetime.fromisoformat(challenge['start_date']).date()
    today = date.today()
    streak_days = (today - start).days

    target = challenge['target_days']
    if target:
        progress = min(100, int((streak_days / target) * 100))
        remaining = max(0, target - streak_days)
    else:
        progress = None
        remaining = None

    # Check if check-in is needed
    last_checkin = challenge['last_check_in']
    needs_checkin = False
    if last_checkin:
        last_dt = datetime.fromisoformat(last_checkin).date()
        if challenge['check_in_frequency'] == 'daily':
            needs_checkin = last_dt < today
        elif challenge['check_in_frequency'] == 'weekly':
            needs_checkin = (today - last_dt).days >= 7
    else:
        needs_checkin = True

    return {
        'streak_days': streak_days,
        'progress': progress,
        'remaining_days': remaining,
        'needs_checkin': needs_checkin
    }


@challenges_bp.route('')
@login_required
def get_challenges():
    """Get all challenges with stats."""
    uid = current_user_id()
    init_challenges_table()
    conn = get_connection()

    rows = conn.execute(
        "SELECT * FROM challenges WHERE user_id = ? ORDER BY status ASC, start_date DESC",
        (uid,),
    ).fetchall()

    result = []
    for r in rows:
        challenge = dict(r)
        if challenge['status'] == 'active':
            stats = get_challenge_stats(challenge)
            challenge.update(stats)
        result.append(challenge)

    return jsonify(result)


@challenges_bp.route('/active')
@login_required
def get_active_challenges():
    """Get only active challenges with stats."""
    uid = current_user_id()
    init_challenges_table()
    conn = get_connection()

    rows = conn.execute(
        "SELECT * FROM challenges WHERE status = 'active' AND user_id = ? ORDER BY start_date ASC",
        (uid,),
    ).fetchall()

    result = []
    for r in rows:
        challenge = dict(r)
        stats = get_challenge_stats(challenge)
        challenge.update(stats)
        result.append(challenge)

    return jsonify(result)


@challenges_bp.route('', methods=['POST'])
@login_required
def create_challenge():
    """Create a new challenge."""
    uid = current_user_id()
    init_challenges_table()
    data = request.json
    conn = get_connection()

    cursor = conn.execute(
        """INSERT INTO challenges
           (user_id, name, category, target_days, start_date, check_in_frequency, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (uid,
         data['name'],
         data.get('category', 'general'),
         data.get('target_days'),
         data.get('start_date', date.today().isoformat()),
         data.get('check_in_frequency', 'daily'),
         data.get('notes', ''))
    )

    # Log creation
    conn.execute(
        "INSERT INTO challenge_logs (challenge_id, action, note) VALUES (?, ?, ?)",
        (cursor.lastrowid, 'created', f"Started: {data['name']}")
    )
    conn.commit()

    return jsonify({'success': True, 'id': cursor.lastrowid})


@challenges_bp.route('/<int:challenge_id>', methods=['PUT'])
@login_required
def update_challenge(challenge_id):
    """Update a challenge."""
    uid = current_user_id()
    data = request.json
    conn = get_connection()

    fields = ['name = ?', 'category = ?', 'target_days = ?', 'check_in_frequency = ?', 'notes = ?']
    values = [data.get('name'), data.get('category'), data.get('target_days'),
              data.get('check_in_frequency'), data.get('notes')]

    if data.get('start_date'):
        fields.append('start_date = ?')
        values.append(data['start_date'])

    values.extend([challenge_id, uid])
    conn.execute(
        f"UPDATE challenges SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
        values
    )
    conn.commit()

    return jsonify({'success': True})


@challenges_bp.route('/<int:challenge_id>/checkin', methods=['POST'])
@login_required
def checkin_challenge(challenge_id):
    """Check in to a challenge (confirm still going)."""
    uid = current_user_id()
    data = request.json or {}
    conn = get_connection()

    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE challenges SET last_check_in = ? WHERE id = ? AND user_id = ?",
        (now, challenge_id, uid)
    )

    conn.execute(
        "INSERT INTO challenge_logs (challenge_id, user_id, action, note, logged_at) VALUES (?, ?, ?, ?, ?)",
        (challenge_id, uid, 'checkin', data.get('note', 'Still going strong!'), now)
    )

    # Auto-backfill missed days since challenge start
    challenge = conn.execute(
        "SELECT start_date FROM challenges WHERE id = ? AND user_id = ?", (challenge_id, uid)
    ).fetchone()
    if challenge and challenge['start_date']:
        from datetime import timedelta
        start = date.fromisoformat(challenge['start_date'])
        today = date.today()
        existing = conn.execute(
            "SELECT DISTINCT date(logged_at) as d FROM challenge_logs WHERE challenge_id = ? AND user_id = ? AND action = 'checkin'",
            (challenge_id, uid)
        ).fetchall()
        existing_dates = {r['d'] for r in existing}
        d = start
        while d < today:
            ds = d.isoformat()
            if ds not in existing_dates:
                conn.execute(
                    "INSERT INTO challenge_logs (challenge_id, user_id, action, note, logged_at) VALUES (?, ?, 'checkin', 'Auto-filled', ?)",
                    (challenge_id, uid, ds + ' 12:00:00')
                )
            d += timedelta(days=1)

    conn.commit()

    return jsonify({'success': True, 'checked_in_at': now})


@challenges_bp.route('/<int:challenge_id>/fail', methods=['POST'])
@login_required
def fail_challenge(challenge_id):
    """Mark a challenge as failed."""
    uid = current_user_id()
    data = request.json or {}
    conn = get_connection()

    # Get current challenge for stats
    challenge = conn.execute(
        "SELECT * FROM challenges WHERE id = ? AND user_id = ?", (challenge_id, uid)
    ).fetchone()

    if challenge:
        stats = get_challenge_stats(dict(challenge))
        streak = stats['streak_days']

        conn.execute(
            "UPDATE challenges SET status = 'failed', end_date = ? WHERE id = ? AND user_id = ?",
            (date.today().isoformat(), challenge_id, uid)
        )

        conn.execute(
            "INSERT INTO challenge_logs (challenge_id, action, note) VALUES (?, ?, ?)",
            (challenge_id, 'failed', f"Ended after {streak} days. {data.get('reason', '')}")
        )
        conn.commit()

        return jsonify({'success': True, 'streak_days': streak})

    return jsonify({'error': 'Challenge not found'}), 404


@challenges_bp.route('/<int:challenge_id>/restart', methods=['POST'])
@login_required
def restart_challenge(challenge_id):
    """Restart a failed challenge."""
    uid = current_user_id()
    conn = get_connection()

    conn.execute(
        """UPDATE challenges
           SET status = 'active', start_date = ?, end_date = NULL, last_check_in = NULL
           WHERE id = ? AND user_id = ?""",
        (date.today().isoformat(), challenge_id, uid)
    )

    conn.execute(
        "INSERT INTO challenge_logs (challenge_id, action, note) VALUES (?, ?, ?)",
        (challenge_id, 'restarted', 'Back on track!')
    )
    conn.commit()

    return jsonify({'success': True})


@challenges_bp.route('/<int:challenge_id>/complete', methods=['POST'])
@login_required
def complete_challenge(challenge_id):
    """Mark a challenge as completed (reached target)."""
    uid = current_user_id()
    conn = get_connection()

    challenge = conn.execute(
        "SELECT * FROM challenges WHERE id = ? AND user_id = ?", (challenge_id, uid)
    ).fetchone()

    if challenge:
        stats = get_challenge_stats(dict(challenge))

        conn.execute(
            "UPDATE challenges SET status = 'completed', end_date = ? WHERE id = ? AND user_id = ?",
            (date.today().isoformat(), challenge_id, uid)
        )

        conn.execute(
            "INSERT INTO challenge_logs (challenge_id, action, note) VALUES (?, ?, ?)",
            (challenge_id, 'completed', f"Completed after {stats['streak_days']} days! 🎉")
        )
        conn.commit()

        return jsonify({'success': True, 'streak_days': stats['streak_days']})

    return jsonify({'error': 'Challenge not found'}), 404


@challenges_bp.route('/<int:challenge_id>/logs')
@login_required
def get_challenge_logs(challenge_id):
    """Get logs for a specific challenge."""
    uid = current_user_id()
    conn = get_connection()

    # Verify ownership before returning logs
    row = conn.execute(
        "SELECT id FROM challenges WHERE id = ? AND user_id = ?", (challenge_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Challenge not found'}), 404

    rows = conn.execute(
        "SELECT * FROM challenge_logs WHERE challenge_id = ? ORDER BY logged_at DESC LIMIT 50",
        (challenge_id,)
    ).fetchall()

    return jsonify([dict(r) for r in rows])


@challenges_bp.route('/<int:challenge_id>', methods=['DELETE'])
@login_required
def delete_challenge(challenge_id):
    """Delete a challenge and its logs."""
    uid = current_user_id()
    conn = get_connection()

    row = conn.execute(
        "SELECT id FROM challenges WHERE id = ? AND user_id = ?", (challenge_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Challenge not found'}), 404

    conn.execute("DELETE FROM challenge_logs WHERE challenge_id = ?", (challenge_id,))
    conn.execute("DELETE FROM challenges WHERE id = ? AND user_id = ?", (challenge_id, uid))
    conn.commit()
    return jsonify({'success': True})
