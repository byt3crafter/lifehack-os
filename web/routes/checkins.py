"""Check-in routes."""
from flask import Blueprint, jsonify, request
from datetime import date

from .decorators import login_required
from src.domain.entities import DailyCheckin
from src.infrastructure.database.repositories import CheckinRepository, StatsRepository
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
