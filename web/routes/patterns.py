"""Check-in patterns routes (learned patterns for AI smart check-ins)."""
from flask import Blueprint, jsonify, request
from datetime import datetime

from .decorators import login_required, api_key_required
from src.infrastructure.database import get_connection

patterns_bp = Blueprint('patterns', __name__, url_prefix='/api/patterns')


def ensure_table():
    """Ensure checkin_patterns table exists."""
    conn = get_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS checkin_patterns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity TEXT NOT NULL,
        time_pattern TEXT,
        occurrences INTEGER DEFAULT 1,
        last_seen TEXT,
        suggested INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()


@patterns_bp.route('')
@login_required
def get_patterns():
    """Get all learned check-in patterns."""
    ensure_table()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM checkin_patterns ORDER BY occurrences DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@patterns_bp.route('/log', methods=['POST'])
@api_key_required
def log_pattern():
    """Log a check-in activity to learn patterns."""
    ensure_table()
    data = request.json
    activity = data.get('activity', '')
    time = data.get('time', datetime.now().strftime('%H:%M'))
    
    conn = get_connection()
    
    # Check if pattern exists
    existing = conn.execute(
        "SELECT id, occurrences FROM checkin_patterns WHERE activity = ?",
        (activity,)
    ).fetchone()
    
    if existing:
        conn.execute(
            "UPDATE checkin_patterns SET occurrences = occurrences + 1, last_seen = ?, time_pattern = ? WHERE id = ?",
            (datetime.now().isoformat(), time, existing['id'])
        )
    else:
        conn.execute(
            "INSERT INTO checkin_patterns (activity, time_pattern, last_seen) VALUES (?, ?, ?)",
            (activity, time, datetime.now().isoformat())
        )
    
    conn.commit()
    return jsonify({'success': True})


@patterns_bp.route('/reset', methods=['POST'])
@login_required
def reset_patterns():
    """Reset all learned patterns."""
    ensure_table()
    conn = get_connection()
    conn.execute("DELETE FROM checkin_patterns")
    conn.commit()
    return jsonify({'success': True})
