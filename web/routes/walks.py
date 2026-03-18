"""Movement/walks routes."""
from flask import Blueprint, jsonify, request
from datetime import datetime

from .decorators import login_required
from src.domain.entities import WalkLog
from src.infrastructure.database import get_connection
from src.infrastructure.database.repositories import WalkRepository, StatsRepository
from src.infrastructure.config import load_config

walks_bp = Blueprint('walks', __name__, url_prefix='/api/walks')

walk_repo = WalkRepository()
stats_repo = StatsRepository()
config = load_config()


@walks_bp.route('')
@login_required
def get_walks():
    stats = walk_repo.get_weekly_stats()
    
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM walk_logs ORDER BY logged_at DESC LIMIT 20"
    ).fetchall()
    
    return jsonify({
        'stats': stats,
        'walks': [{
            'id': r['id'], 
            'date': r['logged_at'], 
            'distance_km': r['distance_km'],
            'duration_minutes': r['duration_minutes'], 
            'mood_before': r['mood_before'],
            'mood_after': r['mood_after'], 
            'points': r['points_earned'],
            'location': r['location'],
            'movement_type': r['movement_type']
        } for r in rows]
    })


@walks_bp.route('', methods=['POST'])
@login_required
def log_walk():
    data = request.json
    distance_km = float(data.get('distance_km', 0))
    duration_minutes = int(data.get('duration_minutes', 0))
    
    walk = WalkLog(
        distance_km=distance_km, 
        duration_minutes=duration_minutes,
        mood_before=data.get('mood_before', 3), 
        mood_after=data.get('mood_after', 3), 
        notes=data.get('notes', '')
    )
    points = walk.calculate_points(
        config.walks.base_points,
        config.walks.km_bonus,
        config.walks.mood_improvement_bonus
    )
    
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO walk_logs 
           (logged_at, distance_km, duration_minutes, mood_before, mood_after, points_earned, notes, location, movement_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (datetime.now().isoformat(), distance_km, duration_minutes,
         walk.mood_before, walk.mood_after, points, walk.notes,
         data.get('location', ''), data.get('movement_type', 'exercise'))
    )
    conn.commit()
    
    stats_repo.add_points('walk', points, f"Movement: {data.get('location', 'Walk')}", cursor.lastrowid)
    return jsonify({'success': True, 'points': points, 'id': cursor.lastrowid})


@walks_bp.route('/<int:walk_id>', methods=['PUT'])
@login_required
def update_walk(walk_id):
    """Edit an existing walk log entry."""
    data = request.json
    conn = get_connection()

    row = conn.execute("SELECT id FROM walk_logs WHERE id = ?", (walk_id,)).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    conn.execute(
        """UPDATE walk_logs
           SET distance_km = ?, duration_minutes = ?, mood_before = ?, mood_after = ?,
               notes = ?, location = ?, movement_type = ?
           WHERE id = ?""",
        (
            data.get('distance_km'),
            data.get('duration_minutes'),
            data.get('mood_before'),
            data.get('mood_after'),
            data.get('notes', ''),
            data.get('location', ''),
            data.get('movement_type', 'exercise'),
            walk_id,
        )
    )
    conn.commit()
    return jsonify({'success': True})


@walks_bp.route('/<int:walk_id>', methods=['DELETE'])
@login_required
def delete_walk(walk_id):
    """Delete a walk log entry."""
    conn = get_connection()
    result = conn.execute("DELETE FROM walk_logs WHERE id = ?", (walk_id,))
    conn.commit()
    if result.rowcount == 0:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'success': True})
