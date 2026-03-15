"""Habits routes."""
from flask import Blueprint, jsonify, request
from datetime import date

from .decorators import login_required
from src.domain.entities import Habit, HabitCompletion, CompletionStatus, Frequency
from src.infrastructure.database import get_connection
from src.infrastructure.database.repositories import HabitRepository, StatsRepository
from src.infrastructure.config import load_config

habits_bp = Blueprint('habits', __name__, url_prefix='/api/habits')

habit_repo = HabitRepository()
stats_repo = StatsRepository()
config = load_config()


@habits_bp.route('')
@login_required
def get_habits():
    habits = habit_repo.get_all()
    completions = habit_repo.get_completions_for_date(date.today())
    completed_ids = {c.habit_id for c in completions}
    
    result = []
    for h in habits:
        streak = habit_repo.get_streak(h.id)
        cat_info = config.categories.get(h.category, None)
        result.append({
            'id': h.id, 'name': h.name, 'category': h.category,
            'category_name': cat_info.name if cat_info else h.category,
            'category_color': cat_info.color if cat_info else '#6B7280',
            'frequency': h.frequency.value, 'difficulty': h.difficulty,
            'points': h.points, 'streak': streak,
            'completed': h.id in completed_ids
        })
    return jsonify(result)


@habits_bp.route('', methods=['POST'])
@login_required
def create_habit():
    data = request.json
    habit = Habit(
        name=data['name'],
        category=data.get('category', 'health'),
        frequency=Frequency(data.get('frequency', 'daily')),
        difficulty=data.get('difficulty', 1),
        points=config.scoring.base_habit_points
    )
    habit = habit_repo.create(habit)
    return jsonify({'id': habit.id, 'success': True})


@habits_bp.route('/<int:habit_id>/complete', methods=['POST'])
@login_required
def complete_habit(habit_id):
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404
    
    streak = habit_repo.get_streak(habit_id)
    points = habit.calculate_points(streak, config.scoring.streak_multiplier_threshold, config.scoring.streak_multiplier)
    completion = HabitCompletion(habit_id=habit_id, status=CompletionStatus.COMPLETE, points_earned=points)
    habit_repo.log_completion(completion)
    stats_repo.add_points('habit', points, f"Completed: {habit.name}", habit_id)
    return jsonify({'success': True, 'points': points})


@habits_bp.route('/<int:habit_id>/uncomplete', methods=['POST'])
@login_required
def uncomplete_habit(habit_id):
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404
    
    conn = get_connection()
    result = conn.execute(
        """DELETE FROM habit_completions 
           WHERE habit_id = ? AND date(completed_at) = date('now')""",
        (habit_id,)
    )
    conn.commit()
    
    if result.rowcount > 0:
        stats_repo.add_points('habit', -10, f"Undone: {habit.name}", habit_id)
        return jsonify({'success': True, 'undone': True})
    
    return jsonify({'success': False, 'message': 'No completion found for today'})


@habits_bp.route('/<int:habit_id>/skip', methods=['POST'])
@login_required
def skip_habit(habit_id):
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404
    
    completion = HabitCompletion(habit_id=habit_id, status=CompletionStatus.SKIPPED, points_earned=0)
    habit_repo.log_completion(completion)
    return jsonify({'success': True, 'skipped': True})


@habits_bp.route('/<int:habit_id>', methods=['PUT'])
@login_required
def update_habit(habit_id):
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404
    
    data = request.json
    if 'name' in data:
        habit.name = data['name']
    if 'category' in data:
        habit.category = data['category']
    if 'difficulty' in data:
        habit.difficulty = data['difficulty']
    if 'active' in data:
        habit.active = data['active']
    
    habit_repo.update(habit)
    return jsonify({'success': True})


@habits_bp.route('/<int:habit_id>', methods=['DELETE'])
@login_required
def delete_habit(habit_id):
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404
    
    habit.active = False
    habit_repo.update(habit)
    return jsonify({'success': True, 'deactivated': True})
