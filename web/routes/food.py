"""Food/nutrition routes."""
import base64
import json
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from flask import Blueprint, jsonify, request

from .decorators import login_required, current_user_id
from src.infrastructure.database import get_connection
from src.infrastructure.database.user_scope import get_user_setting

food_bp = Blueprint('food', __name__, url_prefix='/api/food')

# Directory where uploaded food photos are stored — inside the persistent data volume.
_UPLOAD_DIR = Path(__file__).parent.parent.parent / 'data' / 'uploads'

_ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}


def _ensure_upload_dir() -> None:
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _format_logged_at(raw: str) -> str:
    """Return a human-readable timestamp from a SQLite datetime string."""
    if not raw:
        return ''
    try:
        dt = datetime.fromisoformat(raw)
        return dt.strftime('%b %d, %Y %I:%M %p')
    except ValueError:
        return raw


def _ensure_utc_suffix(ts: str) -> str:
    """Append 'Z' to a SQLite UTC timestamp so JavaScript interprets it as UTC."""
    if not ts:
        return ts
    ts = ts.strip()
    if not ts.endswith('Z') and '+' not in ts and ts[-1].isdigit():
        return ts + 'Z'
    return ts


def _serialize_log(r) -> dict:
    """Serialize a food_logs row to a dict."""
    images = []
    try:
        images = json.loads(r['images_json'] or '[]')
    except (json.JSONDecodeError, TypeError, KeyError):
        pass
    # Fallback to single image_path if images_json is empty
    if not images:
        try:
            ip = r['image_path']
            if ip:
                images = [ip]
        except (KeyError, IndexError):
            pass

    return {
        'id': r['id'],
        'logged_at': _ensure_utc_suffix(r['logged_at']),
        'logged_at_display': _format_logged_at(r['logged_at']),
        'meal_type': r['meal_type'],
        'description': r['description'],
        'calories': r['calories'],
        'protein_g': r['protein_g'],
        'carbs_g': r['carbs_g'],
        'fat_g': r['fat_g'],
        'images': images,
        'image_path': images[0] if images else (r['image_path'] if 'image_path' in r.keys() else None),
        'ai_analysis': r['ai_analysis'],
        'notes': r['notes'] if 'notes' in r.keys() else '',
        'rating': r['rating'] if 'rating' in r.keys() else None,
        'mood_after': r['mood_after'] if 'mood_after' in r.keys() else None,
    }


@food_bp.route('')
@login_required
def get_food_logs():
    """Return food logs.

    Query parameters:
        date — ISO date string (YYYY-MM-DD), omit for today, or "all" for last 7 days.

    Response always includes ``daily_goal`` and ``today_calories`` for the
    requested date (or today when date=all).
    """
    uid = current_user_id()
    date_param = request.args.get('date', '').strip()
    conn = get_connection()

    if date_param == 'all':
        # Legacy behaviour: last 7 days.
        rows = conn.execute(
            """SELECT * FROM food_logs
               WHERE date(logged_at) >= date('now', '-7 days') AND user_id = ?
               ORDER BY logged_at DESC""",
            (uid,)
        ).fetchall()
        cal_date = 'now'
    elif date_param:
        # Specific date requested.
        rows = conn.execute(
            """SELECT * FROM food_logs
               WHERE date(logged_at) = date(?) AND user_id = ?
               ORDER BY logged_at DESC""",
            (date_param, uid)
        ).fetchall()
        cal_date = date_param
    else:
        # Default: today only.
        rows = conn.execute(
            """SELECT * FROM food_logs
               WHERE date(logged_at) = date('now') AND user_id = ?
               ORDER BY logged_at DESC""",
            (uid,)
        ).fetchall()
        cal_date = 'now'

    # Calorie total for the target date.
    if cal_date == 'now':
        today_cals = conn.execute(
            """SELECT SUM(calories) as total FROM food_logs
               WHERE date(logged_at) = date('now') AND user_id = ?""",
            (uid,)
        ).fetchone()
    else:
        today_cals = conn.execute(
            """SELECT SUM(calories) as total FROM food_logs
               WHERE date(logged_at) = date(?) AND user_id = ?""",
            (cal_date, uid)
        ).fetchone()

    goal = get_user_setting(conn, uid, 'calorie_goal', '2000')

    return jsonify({
        'logs': [_serialize_log(r) for r in rows],
        'today_calories': today_cals['total'] or 0,
        'daily_goal': int(goal),
    })


@food_bp.route('', methods=['POST'])
@login_required
def log_food():
    uid = current_user_id()
    data = request.json
    conn = get_connection()

    cursor = conn.execute(
        """INSERT INTO food_logs
           (user_id, meal_type, description, calories, protein_g, carbs_g, fat_g, notes, image_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (uid,
         data.get('meal_type', 'meal'),
         data.get('description', ''),
         data.get('calories'),
         data.get('protein_g'),
         data.get('carbs_g'),
         data.get('fat_g'),
         data.get('notes', ''),
         data.get('image_path'))
    )
    conn.commit()

    return jsonify({'success': True, 'id': cursor.lastrowid})


@food_bp.route('/<int:food_id>', methods=['DELETE'])
@login_required
def delete_food(food_id):
    uid = current_user_id()
    conn = get_connection()
    conn.execute("DELETE FROM food_logs WHERE id = ? AND user_id = ?", (food_id, uid))
    conn.commit()
    return jsonify({'success': True})


@food_bp.route('/<int:food_id>', methods=['PUT'])
@login_required
def update_food(food_id):
    """Update a food log entry (including optional image_path)."""
    uid = current_user_id()
    data = request.json
    conn = get_connection()

    # Build dynamic UPDATE — only set fields that are provided
    fields = []
    values = []
    for col, key in [
        ('meal_type', 'meal_type'), ('description', 'description'),
        ('calories', 'calories'), ('protein_g', 'protein_g'),
        ('carbs_g', 'carbs_g'), ('fat_g', 'fat_g'),
        ('notes', 'notes'), ('rating', 'rating'), ('mood_after', 'mood_after'),
    ]:
        if key in data:
            fields.append(f'{col} = ?')
            values.append(data[key])
    # Only update image_path if explicitly sent (not None/undefined)
    if 'image_path' in data and data['image_path']:
        fields.append('image_path = ?')
        values.append(data['image_path'])

    if fields:
        values.extend([food_id, uid])
        conn.execute(
            f"UPDATE food_logs SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values
        )
        conn.commit()

    return jsonify({'success': True})


@food_bp.route('/<int:food_id>/upload-image', methods=['POST'])
@login_required
def upload_food_image(food_id):
    """Upload a new image for an existing food log entry.

    Accepts multipart/form-data with an ``image`` file field.
    Saves the file to static/uploads/ and appends to images_json.

    Returns:
        {"success": true, "image_path": "/uploads/<filename>", "images": [...]}
    """
    uid = current_user_id()
    _ensure_upload_dir()

    conn = get_connection()
    row = conn.execute(
        "SELECT id, images_json FROM food_logs WHERE id = ? AND user_id = ?", (food_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'success': False, 'error': 'Food entry not found'}), 404

    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'No image file provided'}), 400

    file = request.files['image']
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'Empty file'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in _ALLOWED_EXTENSIONS:
        return jsonify({'success': False, 'error': 'Unsupported file type'}), 400

    # Compress + create thumbnail
    from src.infrastructure.services.image_service import process_upload
    base_name = uuid.uuid4().hex
    results = process_upload(
        file, str(_UPLOAD_DIR.parent), 'food', base_name,
        sizes=['full', 'thumb'], quality=75
    )

    if results.get('thumb'):
        image_url = f"/uploads/{results['thumb']}"
        full_url = f"/uploads/{results.get('full', results['thumb'])}"
    else:
        # Fallback if Pillow not available
        filename = f"{base_name}.{ext}"
        save_path = _UPLOAD_DIR / filename
        file.seek(0)
        file.save(str(save_path))
        image_url = f"/uploads/{filename}"
        full_url = image_url

    # Append to images_json; keep image_path as the first image (backward compat)
    existing = []
    try:
        existing = json.loads(row['images_json'] or '[]')
    except (json.JSONDecodeError, TypeError):
        pass
    existing.append(image_url)

    conn.execute(
        "UPDATE food_logs SET image_path = ?, images_json = ? WHERE id = ? AND user_id = ?",
        (existing[0], json.dumps(existing), food_id, uid)
    )
    conn.commit()

    from .app_log import log_event
    log_event('info', 'food', f'Image updated for food #{food_id}', image_url)

    return jsonify({'success': True, 'image_path': image_url, 'full_path': full_url, 'images': existing})


@food_bp.route('/<int:food_id>/add-image', methods=['POST'])
@login_required
def add_food_image(food_id):
    """Add an additional image to an existing food log entry (does not replace existing images)."""
    uid = current_user_id()
    _ensure_upload_dir()

    conn = get_connection()
    row = conn.execute(
        "SELECT id, images_json FROM food_logs WHERE id = ? AND user_id = ?", (food_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    if 'image' not in request.files:
        return jsonify({'error': 'No image file'}), 400

    file = request.files['image']
    if not file or not file.filename:
        return jsonify({'error': 'Empty file'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in _ALLOWED_EXTENSIONS:
        return jsonify({'error': 'Unsupported file type'}), 400

    # Process with image service (compress + thumbnail)
    from src.infrastructure.services.image_service import process_upload
    base_name = uuid.uuid4().hex
    results = process_upload(file, str(_UPLOAD_DIR.parent), 'food', base_name, sizes=['full', 'thumb'], quality=75)

    if results.get('thumb'):
        new_url = f"/uploads/{results['thumb']}"
    else:
        # Fallback if Pillow not available
        filename = f"{base_name}.{ext}"
        file.seek(0)
        (_UPLOAD_DIR / filename).parent.mkdir(parents=True, exist_ok=True)
        file.save(str(_UPLOAD_DIR / filename))
        new_url = f"/uploads/{filename}"

    # Append to images_json
    existing = []
    try:
        existing = json.loads(row['images_json'] or '[]')
    except (json.JSONDecodeError, TypeError):
        pass
    existing.append(new_url)

    conn.execute(
        "UPDATE food_logs SET images_json = ?, image_path = ? WHERE id = ? AND user_id = ?",
        (json.dumps(existing), existing[0], food_id, uid)
    )
    conn.commit()

    return jsonify({'success': True, 'images': existing})


@food_bp.route('/identify', methods=['POST'])
@login_required
def identify_food():
    """Identify food from a description or image — returns description only.

    This is step 1 of the two-step analysis flow:
    1. POST /api/food/identify  → get a plain-language food description
    2. User reviews / edits the description
    3. POST /api/food/upload    → get calorie/macro estimates

    Request body (JSON):
        description   — optional text hint
        image_base64  — optional base64-encoded image

    Returns:
        {"description": "Avocado toast with fried egg", "confidence": "high"}
    """
    data = request.get_json(silent=True) or {}
    description = data.get('description', '')
    image_base64 = data.get('image_base64')

    if not description and not image_base64:
        return jsonify({'success': False, 'error': 'Provide description or image_base64'}), 400

    try:
        from src.infrastructure.ai.factory import get_ai_provider
        provider = get_ai_provider('food')

        if not provider.is_available():
            return jsonify({'success': False, 'error': 'AI provider not configured'}), 503

        result = provider.identify_food(description=description, image_base64=image_base64)

        if not result.available:
            return jsonify({'success': False, 'error': 'AI could not identify the food'}), 422

        return jsonify({
            'description': result.description,
            'confidence': result.confidence,
        })

    except Exception as exc:
        from .app_log import log_event
        log_event('error', 'ai', f'Food identify failed: {exc}', traceback.format_exc())
        return jsonify({'success': False, 'error': 'AI identification failed'}), 500


@food_bp.route('/analyze', methods=['POST'])
@login_required
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
            "image_path": "/uploads/<filename>",
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

    image_url = f"/uploads/{filename}"

    from .app_log import log_event
    log_event('info', 'food', 'Photo uploaded', image_url)

    # Attempt AI analysis if a provider is configured.
    description = request.form.get('description', '')
    analysis_dict = None
    ai_error = None

    provider_info = {'name': 'none', 'model': ''}
    try:
        from src.infrastructure.ai.factory import get_ai_provider
        provider = get_ai_provider('food')
        provider_info = {
            'name': type(provider).__name__.replace('Provider', '').lower(),
            'model': getattr(provider, 'model', ''),
        }
        if not provider.is_available():
            ai_error = 'AI provider not configured'
        else:
            image_bytes = save_path.read_bytes()
            image_b64 = base64.b64encode(image_bytes).decode('ascii')

            # If no description, try to identify the food from the image
            if not description:
                try:
                    ident = provider.identify_food(description='', image_base64=image_b64)
                    if ident.available and ident.description:
                        description = ident.description
                except Exception:
                    pass

            # If still no description (provider can't see images), return
            # the image path but ask the user to describe the food
            if not description:
                ai_error = 'This AI provider cannot analyze images. Please describe the food and try again.'
                # Return early with just the image saved
                response = {
                    'success': True,
                    'image_path': image_url,
                    'analysis': None,
                    'provider': provider_info,
                    'ai_error': ai_error,
                    'needs_description': True,
                }
                return jsonify(response)

            result = provider.analyze_food(description, image_base64=None)
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
        ai_error = str(exc)
        log_event('error', 'ai', f'Food analysis failed: {ai_error}', traceback.format_exc())

    response = {
        'success': True,
        'image_path': image_url,
        'analysis': analysis_dict,
        'provider': provider_info,
    }
    if ai_error:
        response['ai_error'] = ai_error
    return jsonify(response)
