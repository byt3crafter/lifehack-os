"""Discover module routes — bucket list of experiences and places."""
import json
import traceback
import uuid
from datetime import date, datetime
from pathlib import Path
from flask import Blueprint, jsonify, request

from .decorators import login_required, current_user_id
from src.infrastructure.database import get_connection

discover_bp = Blueprint('discover', __name__, url_prefix='/api/discover')

_UPLOAD_DIR = Path(__file__).parent.parent.parent / 'data' / 'uploads'
_ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}


def _ensure_upload_dir() -> None:
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _serialize(r) -> dict:
    photos = r['photos_json']
    try:
        photos = json.loads(photos) if photos else []
    except (TypeError, ValueError):
        photos = []

    return {
        'id': r['id'],
        'title': r['title'],
        'location': r['location'],
        'description': r['description'],
        'category': r['category'],
        'status': r['status'],
        'completed': bool(r['completed']),
        'rating': r['rating'],
        'completed_at': r['completed_at'],
        'photos': photos,
        'notes': r['notes'],
        'created_at': r['created_at'],
    }


# ---------------------------------------------------------------------------
# GET /api/discover
# ---------------------------------------------------------------------------

@discover_bp.route('')
@login_required
def list_items():
    """List all discover items, optionally filtered by status and category."""
    uid = current_user_id()
    status = request.args.get('status')
    category = request.args.get('category')

    conn = get_connection()
    query = "SELECT * FROM wishlist WHERE user_id = ?"
    params = [uid]

    if status:
        query += " AND status = ?"
        params.append(status)
    if category:
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    return jsonify([_serialize(r) for r in rows])


# ---------------------------------------------------------------------------
# POST /api/discover
# ---------------------------------------------------------------------------

@discover_bp.route('', methods=['POST'])
@login_required
def create_item():
    """Add a new discover item."""
    uid = current_user_id()
    data = request.json or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'title is required'}), 400

    description = (data.get('description') or '').strip()
    category = (data.get('category') or 'place').strip()
    location = (data.get('location') or '').strip()

    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO wishlist (user_id, title, description, category, location, status)
           VALUES (?, ?, ?, ?, ?, 'want')""",
        (uid, title, description, category, location),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM wishlist WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return jsonify(_serialize(row)), 201


# ---------------------------------------------------------------------------
# PUT /api/discover/<id>
# ---------------------------------------------------------------------------

@discover_bp.route('/<int:item_id>', methods=['PUT'])
@login_required
def update_item(item_id: int):
    """Update a discover item's fields."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM wishlist WHERE id = ? AND user_id = ?", (item_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Item not found'}), 404

    data = request.json or {}
    title = (data.get('title') or row['title']).strip()
    description = (data.get('description') if 'description' in data else row['description'])
    category = (data.get('category') or row['category']).strip()
    location = (data.get('location') if 'location' in data else row['location'])
    status = (data.get('status') or row['status']).strip()
    notes = (data.get('notes') if 'notes' in data else row['notes'])

    conn.execute(
        """UPDATE wishlist
           SET title = ?, description = ?, category = ?, location = ?, status = ?, notes = ?
           WHERE id = ? AND user_id = ?""",
        (title, description, category, location, status, notes, item_id, uid),
    )
    conn.commit()

    row = conn.execute("SELECT * FROM wishlist WHERE id = ?", (item_id,)).fetchone()
    return jsonify(_serialize(row))


# ---------------------------------------------------------------------------
# DELETE /api/discover/<id>
# ---------------------------------------------------------------------------

@discover_bp.route('/<int:item_id>', methods=['DELETE'])
@login_required
def delete_item(item_id: int):
    """Delete a discover item."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM wishlist WHERE id = ? AND user_id = ?", (item_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Item not found'}), 404

    conn.execute("DELETE FROM wishlist WHERE id = ? AND user_id = ?", (item_id, uid))
    conn.commit()
    return '', 204


# ---------------------------------------------------------------------------
# POST /api/discover/<id>/complete
# ---------------------------------------------------------------------------

@discover_bp.route('/<int:item_id>/complete', methods=['POST'])
@login_required
def complete_item(item_id: int):
    """Mark a discover item as done. Body: {rating, notes, photos_json}."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM wishlist WHERE id = ? AND user_id = ?", (item_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Item not found'}), 404

    data = request.json or {}
    rating = data.get('rating')
    notes = (data.get('notes') or '').strip()
    photos = data.get('photos_json', [])

    if rating is not None:
        try:
            rating = int(rating)
            if not (1 <= rating <= 5):
                return jsonify({'error': 'rating must be 1–5'}), 400
        except (TypeError, ValueError):
            return jsonify({'error': 'rating must be an integer 1–5'}), 400

    photos_json = json.dumps(photos) if isinstance(photos, list) else photos

    conn.execute(
        """UPDATE wishlist
           SET status = 'done', completed = 1, completed_at = ?,
               rating = ?, notes = ?, photos_json = ?
           WHERE id = ? AND user_id = ?""",
        (date.today().isoformat(), rating, notes, photos_json, item_id, uid),
    )
    conn.commit()

    row = conn.execute("SELECT * FROM wishlist WHERE id = ?", (item_id,)).fetchone()
    return jsonify(_serialize(row))


# ---------------------------------------------------------------------------
# POST /api/discover/<id>/upload-photo
# ---------------------------------------------------------------------------

@discover_bp.route('/<int:item_id>/upload-photo', methods=['POST'])
@login_required
def upload_photo(item_id: int):
    """Upload a completion photo and append its path to photos_json."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM wishlist WHERE id = ? AND user_id = ?", (item_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Item not found'}), 404

    if 'photo' not in request.files:
        return jsonify({'error': 'photo file is required'}), 400

    file = request.files['photo']
    if not file.filename:
        return jsonify({'error': 'empty filename'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return jsonify({'error': f'unsupported file type: {ext}'}), 400

    _ensure_upload_dir()
    filename = f"discover_{item_id}_{uuid.uuid4().hex}.{ext}"
    file.save(str(_UPLOAD_DIR / filename))
    photo_url = f"/uploads/{filename}"

    existing = row['photos_json']
    try:
        photos = json.loads(existing) if existing else []
    except (TypeError, ValueError):
        photos = []

    photos.append(photo_url)
    conn.execute(
        "UPDATE wishlist SET photos_json = ? WHERE id = ? AND user_id = ?",
        (json.dumps(photos), item_id, uid),
    )
    conn.commit()

    return jsonify({'photo_url': photo_url, 'photos': photos}), 201


# ---------------------------------------------------------------------------
# POST /api/discover/<id>/start-habit  — create a habit from a discovery
# ---------------------------------------------------------------------------

@discover_bp.route('/<int:item_id>/start-habit', methods=['POST'])
@login_required
def start_habit_from_discover(item_id: int):
    """Use AI to generate a habit plan inspired by this discover item."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM wishlist WHERE id = ? AND user_id = ?", (item_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Item not found'}), 404

    data = request.json or {}
    goal_override = (data.get('goal') or '').strip()
    goal = goal_override or f"Pursue and achieve: {row['title']}. {row['description']}"

    try:
        from src.infrastructure.ai import get_ai_provider

        provider = get_ai_provider('habits')
        if not provider.is_available():
            return jsonify({'error': 'AI provider not configured'}), 503

        plan = provider.generate_habit_plan(goal)
        if not plan:
            return jsonify({'error': 'AI could not generate a habit plan'}), 502

        # Persist the habit using the same logic as the habits blueprint
        habit_conn = get_connection()
        cursor = habit_conn.execute(
            """INSERT INTO habits (user_id, name, category, frequency, difficulty, points)
               VALUES (?, ?, ?, 'daily', ?, ?)""",
            (uid, plan.name, plan.category, 1, 10),
        )
        habit_id = cursor.lastrowid

        for phase in plan.phases:
            pc = habit_conn.execute(
                """INSERT INTO habit_phases
                   (habit_id, phase_number, name, description, unlock_after_days, is_current)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (habit_id, phase.phase, phase.name, phase.description,
                 phase.days, 1 if phase.phase == 1 else 0),
            )
            phase_id = pc.lastrowid
            for idx, task in enumerate(phase.micro_tasks):
                vr = json.dumps(task.get('verification_rule', {'type': 'manual'}))
                habit_conn.execute(
                    """INSERT INTO habit_micro_tasks
                       (phase_id, name, description, sort_order, verification_rule)
                       VALUES (?, ?, ?, ?, ?)""",
                    (phase_id, task['name'], task.get('description', ''), idx, vr),
                )

        habit_conn.commit()
        return jsonify({'success': True, 'habit_id': habit_id, 'habit_name': plan.name}), 201

    except Exception as exc:
        return jsonify({'error': 'Failed to create habit', 'detail': str(exc)}), 500


# ---------------------------------------------------------------------------
# POST /api/discover/<id>/start-challenge  — create a challenge from a discovery
# ---------------------------------------------------------------------------

@discover_bp.route('/<int:item_id>/start-challenge', methods=['POST'])
@login_required
def start_challenge_from_discover(item_id: int):
    """Create a challenge directly linked to this discover item."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM wishlist WHERE id = ? AND user_id = ?", (item_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Item not found'}), 404

    data = request.json or {}
    name = (data.get('name') or row['title']).strip()
    target_days = data.get('target_days', 30)
    notes = (data.get('notes') or f"Challenge created from discover item: {row['title']}").strip()

    try:
        target_days = int(target_days)
    except (TypeError, ValueError):
        return jsonify({'error': 'target_days must be an integer'}), 400

    start_date = date.today().isoformat()

    cursor = conn.execute(
        """INSERT INTO challenges
           (user_id, name, category, target_days, start_date, status, notes)
           VALUES (?, ?, ?, ?, ?, 'active', ?)""",
        (uid, name, row['category'] or 'general', target_days, start_date, notes),
    )
    conn.commit()

    return jsonify({
        'success': True,
        'challenge_id': cursor.lastrowid,
        'challenge_name': name,
    }), 201
