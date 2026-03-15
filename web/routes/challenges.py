"""Challenges / Streak Tracker routes."""
from flask import Blueprint, jsonify, request
from datetime import datetime, date, timedelta

from .decorators import login_required, api_key_required
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
    init_challenges_table()
    conn = get_connection()
    
    rows = conn.execute(
        "SELECT * FROM challenges ORDER BY status ASC, start_date DESC"
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
    init_challenges_table()
    conn = get_connection()
    
    rows = conn.execute(
        "SELECT * FROM challenges WHERE status = 'active' ORDER BY start_date ASC"
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
    init_challenges_table()
    data = request.json
    conn = get_connection()
    
    cursor = conn.execute(
        """INSERT INTO challenges 
           (name, category, target_days, start_date, check_in_frequency, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (data['name'],
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
    data = request.json
    conn = get_connection()
    
    conn.execute(
        """UPDATE challenges 
           SET name = ?, category = ?, target_days = ?, check_in_frequency = ?, notes = ?
           WHERE id = ?""",
        (data.get('name'),
         data.get('category'),
         data.get('target_days'),
         data.get('check_in_frequency'),
         data.get('notes'),
         challenge_id)
    )
    conn.commit()
    
    return jsonify({'success': True})


@challenges_bp.route('/<int:challenge_id>/checkin', methods=['POST'])
@login_required
def checkin_challenge(challenge_id):
    """Check in to a challenge (confirm still going)."""
    data = request.json or {}
    conn = get_connection()
    
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE challenges SET last_check_in = ? WHERE id = ?",
        (now, challenge_id)
    )
    
    conn.execute(
        "INSERT INTO challenge_logs (challenge_id, action, note) VALUES (?, ?, ?)",
        (challenge_id, 'checkin', data.get('note', 'Still going strong!'))
    )
    conn.commit()
    
    return jsonify({'success': True, 'checked_in_at': now})


@challenges_bp.route('/<int:challenge_id>/fail', methods=['POST'])
@login_required
def fail_challenge(challenge_id):
    """Mark a challenge as failed."""
    data = request.json or {}
    conn = get_connection()
    
    # Get current challenge for stats
    challenge = conn.execute(
        "SELECT * FROM challenges WHERE id = ?", (challenge_id,)
    ).fetchone()
    
    if challenge:
        stats = get_challenge_stats(dict(challenge))
        streak = stats['streak_days']
        
        conn.execute(
            "UPDATE challenges SET status = 'failed', end_date = ? WHERE id = ?",
            (date.today().isoformat(), challenge_id)
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
    conn = get_connection()
    
    conn.execute(
        """UPDATE challenges 
           SET status = 'active', start_date = ?, end_date = NULL, last_check_in = NULL
           WHERE id = ?""",
        (date.today().isoformat(), challenge_id)
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
    conn = get_connection()
    
    challenge = conn.execute(
        "SELECT * FROM challenges WHERE id = ?", (challenge_id,)
    ).fetchone()
    
    if challenge:
        stats = get_challenge_stats(dict(challenge))
        
        conn.execute(
            "UPDATE challenges SET status = 'completed', end_date = ? WHERE id = ?",
            (date.today().isoformat(), challenge_id)
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
    conn = get_connection()
    
    rows = conn.execute(
        "SELECT * FROM challenge_logs WHERE challenge_id = ? ORDER BY logged_at DESC LIMIT 50",
        (challenge_id,)
    ).fetchall()
    
    return jsonify([dict(r) for r in rows])


@challenges_bp.route('/<int:challenge_id>', methods=['DELETE'])
@login_required
def delete_challenge(challenge_id):
    """Delete a challenge and its logs."""
    conn = get_connection()
    conn.execute("DELETE FROM challenge_logs WHERE challenge_id = ?", (challenge_id,))
    conn.execute("DELETE FROM challenges WHERE id = ?", (challenge_id,))
    conn.commit()
    return jsonify({'success': True})


# ============== OPENCLAW INTEGRATION ==============

@challenges_bp.route('/openclaw/status', methods=['GET'])
@api_key_required
def openclaw_challenges_status():
    """Get challenges status for OpenClaw AI."""
    init_challenges_table()
    conn = get_connection()
    
    active = conn.execute(
        "SELECT * FROM challenges WHERE status = 'active'"
    ).fetchall()
    
    result = {
        'active_challenges': [],
        'needs_checkin': [],
        'milestones_today': []
    }
    
    milestone_days = [7, 14, 21, 30, 60, 90, 100, 180, 365]
    
    for r in active:
        challenge = dict(r)
        stats = get_challenge_stats(challenge)
        challenge.update(stats)
        result['active_challenges'].append({
            'id': challenge['id'],
            'name': challenge['name'],
            'category': challenge['category'],
            'streak_days': stats['streak_days'],
            'target_days': challenge['target_days'],
            'progress': stats['progress']
        })
        
        if stats['needs_checkin']:
            result['needs_checkin'].append(challenge['name'])
        
        if stats['streak_days'] in milestone_days:
            result['milestones_today'].append({
                'name': challenge['name'],
                'days': stats['streak_days']
            })
    
    return jsonify(result)


@challenges_bp.route('/openclaw/checkin', methods=['POST'])
@api_key_required
def openclaw_checkin():
    """AI can check in to a challenge by name."""
    data = request.json
    challenge_name = data.get('challenge_name', '').lower()
    
    conn = get_connection()
    challenge = conn.execute(
        "SELECT id, name FROM challenges WHERE status = 'active' AND LOWER(name) LIKE ?",
        (f'%{challenge_name}%',)
    ).fetchone()
    
    if challenge:
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE challenges SET last_check_in = ? WHERE id = ?",
            (now, challenge['id'])
        )
        conn.execute(
            "INSERT INTO challenge_logs (challenge_id, action, note) VALUES (?, ?, ?)",
            (challenge['id'], 'checkin', data.get('note', 'Checked in via OpenClaw'))
        )
        conn.commit()
        
        return jsonify({'success': True, 'challenge': challenge['name']})
    
    return jsonify({'error': 'Challenge not found'}), 404


@challenges_bp.route('/openclaw/fail', methods=['POST'])
@api_key_required
def openclaw_fail():
    """AI can mark a challenge as failed by name."""
    data = request.json
    challenge_name = data.get('challenge_name', '').lower()
    reason = data.get('reason', '')
    
    conn = get_connection()
    challenge = conn.execute(
        "SELECT * FROM challenges WHERE status = 'active' AND LOWER(name) LIKE ?",
        (f'%{challenge_name}%',)
    ).fetchone()
    
    if challenge:
        stats = get_challenge_stats(dict(challenge))
        
        conn.execute(
            "UPDATE challenges SET status = 'failed', end_date = ? WHERE id = ?",
            (date.today().isoformat(), challenge['id'])
        )
        conn.execute(
            "INSERT INTO challenge_logs (challenge_id, action, note) VALUES (?, ?, ?)",
            (challenge['id'], 'failed', f"Ended after {stats['streak_days']} days. {reason}")
        )
        conn.commit()
        
        return jsonify({
            'success': True,
            'challenge': challenge['name'],
            'streak_days': stats['streak_days']
        })
    
    return jsonify({'error': 'Challenge not found'}), 404
