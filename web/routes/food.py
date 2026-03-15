"""Food/nutrition routes."""
from flask import Blueprint, jsonify, request
from datetime import datetime

from .decorators import login_required, api_key_required
from src.infrastructure.database import get_connection

food_bp = Blueprint('food', __name__, url_prefix='/api/food')


@food_bp.route('')
@login_required
def get_food_logs():
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM food_logs 
           WHERE date(logged_at) >= date('now', '-7 days')
           ORDER BY logged_at DESC"""
    ).fetchall()
    
    today_cals = conn.execute(
        """SELECT SUM(calories) as total FROM food_logs 
           WHERE date(logged_at) = date('now')"""
    ).fetchone()
    
    return jsonify({
        'logs': [{
            'id': r['id'],
            'logged_at': r['logged_at'],
            'meal_type': r['meal_type'],
            'description': r['description'],
            'calories': r['calories'],
            'protein_g': r['protein_g'],
            'carbs_g': r['carbs_g'],
            'fat_g': r['fat_g'],
            'image_path': r['image_path'],
            'ai_analysis': r['ai_analysis']
        } for r in rows],
        'today_calories': today_cals['total'] or 0
    })


@food_bp.route('', methods=['POST'])
@login_required
def log_food():
    data = request.json
    conn = get_connection()
    
    cursor = conn.execute(
        """INSERT INTO food_logs 
           (meal_type, description, calories, protein_g, carbs_g, fat_g, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (data.get('meal_type', 'meal'),
         data.get('description', ''),
         data.get('calories'),
         data.get('protein_g'),
         data.get('carbs_g'),
         data.get('fat_g'),
         data.get('notes', ''))
    )
    conn.commit()
    
    return jsonify({'success': True, 'id': cursor.lastrowid})


@food_bp.route('/<int:food_id>', methods=['DELETE'])
@login_required
def delete_food(food_id):
    conn = get_connection()
    conn.execute("DELETE FROM food_logs WHERE id = ?", (food_id,))
    conn.commit()
    return jsonify({'success': True})


@food_bp.route('/<int:food_id>', methods=['PUT'])
@login_required
def update_food(food_id):
    """Update a food log entry."""
    data = request.json
    conn = get_connection()
    
    conn.execute(
        """UPDATE food_logs 
           SET meal_type = ?, description = ?, calories = ?, protein_g = ?, carbs_g = ?, fat_g = ?
           WHERE id = ?""",
        (data.get('meal_type'),
         data.get('description'),
         data.get('calories'),
         data.get('protein_g'),
         data.get('carbs_g'),
         data.get('fat_g'),
         food_id)
    )
    conn.commit()
    
    return jsonify({'success': True})


@food_bp.route('/analyze', methods=['POST'])
@api_key_required
def analyze_food():
    data = request.json
    
    if data.get('food_id'):
        conn = get_connection()
        conn.execute(
            "UPDATE food_logs SET ai_analysis = ?, calories = ?, protein_g = ?, carbs_g = ?, fat_g = ? WHERE id = ?",
            (data.get('ai_analysis'), data.get('calories'), data.get('protein_g'), 
             data.get('carbs_g'), data.get('fat_g'), data.get('food_id'))
        )
        conn.commit()
    
    return jsonify({'success': True})
