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
    return jsonify({'success': True, 'points': points})
