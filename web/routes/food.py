"""Food/nutrition routes."""
import base64
import uuid
from pathlib import Path
from flask import Blueprint, jsonify, request

from .decorators import login_required, api_key_required
from src.infrastructure.database import get_connection

food_bp = Blueprint('food', __name__, url_prefix='/api/food')

# Directory where uploaded food photos are stored.
_UPLOAD_DIR = Path(__file__).parent.parent / 'static' / 'uploads'

_ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}


def _ensure_upload_dir() -> None:
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _get_calorie_goal(conn) -> int:
    """Return the daily calorie goal from settings (default 2000)."""
    try:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'daily_calorie_goal'"
        ).fetchone()
        if row and row['value']:
            return int(row['value'])
    except Exception:
        pass
    return 2000


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
        'today_calories': today_cals['total'] or 0,
        'daily_goal': _get_calorie_goal(conn),
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


@food_bp.route('/upload', methods=['POST'])
@login_required
def upload_food_photo():
    """Accept a food photo, optionally run AI analysis, and return the result.

    Expects multipart/form-data with an ``image`` file field.
    Optional form field ``description`` provides a text hint for the AI.

    Returns JSON:
        {
            "success": true,
            "image_path": "/static/uploads/<filename>",
            "analysis": {
                "calories": ..., "protein_g": ..., "carbs_g": ...,
                "fat_g": ..., "description": ..., "estimated": true
            }
        }
    """
    _ensure_upload_dir()

    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'No image file provided'}), 400

    file = request.files['image']
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'Empty file'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in _ALLOWED_EXTENSIONS:
        return jsonify({'success': False, 'error': 'Unsupported file type'}), 400

    filename = f"{uuid.uuid4().hex}.{ext}"
    save_path = _UPLOAD_DIR / filename
    file.save(str(save_path))

    image_url = f"/static/uploads/{filename}"

    # Attempt AI analysis if a provider is configured.
    description = request.form.get('description', '')
    analysis_dict = None
    ai_error = None

    try:
        from src.infrastructure.ai.factory import get_ai_provider
        provider = get_ai_provider()
        if not provider.is_available():
            ai_error = 'AI provider not configured'
        else:
            image_bytes = save_path.read_bytes()
            image_b64 = base64.b64encode(image_bytes).decode('ascii')
            result = provider.analyze_food(description, image_base64=image_b64)
            if result.estimated:
                analysis_dict = {
                    'calories': result.calories,
                    'protein_g': result.protein_g,
                    'carbs_g': result.carbs_g,
                    'fat_g': result.fat_g,
                    'description': result.description or description,
                    'estimated': result.estimated,
                }
            else:
                ai_error = 'AI returned no usable analysis'
    except Exception as exc:
        # AI analysis is best-effort; always return the saved image path.
        ai_error = str(exc)

    response = {
        'success': True,
        'image_path': image_url,
        'analysis': analysis_dict,
    }
    if ai_error:
        response['ai_error'] = ai_error
    return jsonify(response)
