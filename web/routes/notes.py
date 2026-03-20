"""Notes routes — pinnable, archivable notes organised into folders."""
import json
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request

from .decorators import login_required, current_user_id
from src.infrastructure.database import get_connection

notes_bp = Blueprint('notes', __name__, url_prefix='/api/notes')


def _now_iso() -> str:
    """Return the current UTC datetime as an ISO 8601 string."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def _serialize(r) -> dict:
    tags = r['tags_json']
    try:
        tags = json.loads(tags) if tags else []
    except (TypeError, ValueError):
        tags = []

    return {
        'id': r['id'],
        'user_id': r['user_id'],
        'title': r['title'],
        'body': r['body'],
        'tags': tags,
        'folder': r['folder'],
        'pinned': bool(r['pinned']),
        'archived': bool(r['archived']),
        'created_at': r['created_at'],
        'updated_at': r['updated_at'],
    }


# ---------------------------------------------------------------------------
# GET /api/notes
# ---------------------------------------------------------------------------

@notes_bp.route('')
@login_required
def list_notes():
    """List notes for the current user.

    Query parameters:
        folder   — filter by folder name.
        search   — substring search across title and body.
        archived — '1' to show archived notes; defaults to '0' (active only).

    Ordering: pinned notes first, then by updated_at DESC.
    """
    uid = current_user_id()
    folder = request.args.get('folder', '').strip()
    search = request.args.get('search', '').strip()
    show_archived = request.args.get('archived', '0').strip() == '1'

    conn = get_connection()
    query = "SELECT * FROM notes WHERE user_id = ? AND archived = ?"
    params = [uid, 1 if show_archived else 0]

    if folder:
        query += " AND folder = ?"
        params.append(folder)

    if search:
        pattern = f"%{search}%"
        query += " AND (title LIKE ? OR body LIKE ?)"
        params.extend([pattern, pattern])

    query += " ORDER BY pinned DESC, updated_at DESC"

    rows = conn.execute(query, params).fetchall()
    return jsonify([_serialize(r) for r in rows])


# ---------------------------------------------------------------------------
# GET /api/notes/folders
# ---------------------------------------------------------------------------

@notes_bp.route('/folders')
@login_required
def list_folders():
    """Return distinct non-empty folder names for the current user."""
    uid = current_user_id()
    conn = get_connection()
    rows = conn.execute(
        """SELECT DISTINCT folder FROM notes
           WHERE user_id = ? AND folder IS NOT NULL AND folder != ''
           ORDER BY folder ASC""",
        (uid,),
    ).fetchall()
    return jsonify([r['folder'] for r in rows])


# ---------------------------------------------------------------------------
# GET /api/notes/<id>
# ---------------------------------------------------------------------------

@notes_bp.route('/<int:note_id>')
@login_required
def get_note(note_id: int):
    """Return a single note."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Note not found'}), 404
    return jsonify(_serialize(row))


# ---------------------------------------------------------------------------
# POST /api/notes
# ---------------------------------------------------------------------------

@notes_bp.route('', methods=['POST'])
@login_required
def create_note():
    """Create a new note.

    Body fields:
        title  — string (required).
        body   — string.
        tags   — list of strings (stored as JSON).
        folder — string.
    """
    uid = current_user_id()
    data = request.json or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'title is required'}), 400

    body = (data.get('body') or '').strip()
    tags_json = json.dumps(data['tags']) if isinstance(data.get('tags'), list) else '[]'
    folder = (data.get('folder') or '').strip()
    now = _now_iso()

    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO notes (user_id, title, body, tags_json, folder, pinned, archived, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)""",
        (uid, title, body, tags_json, folder, now, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM notes WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return jsonify(_serialize(row)), 201


# ---------------------------------------------------------------------------
# PUT /api/notes/<id>
# ---------------------------------------------------------------------------

@notes_bp.route('/<int:note_id>', methods=['PUT'])
@login_required
def update_note(note_id: int):
    """Update a note. updated_at is always refreshed."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Note not found'}), 404

    data = request.json or {}

    fields = ['updated_at = ?']
    values = [_now_iso()]

    for col, key in [
        ('title', 'title'), ('body', 'body'), ('folder', 'folder'),
        ('pinned', 'pinned'), ('archived', 'archived'),
    ]:
        if key in data:
            fields.append(f'{col} = ?')
            values.append(data[key])

    if 'tags' in data:
        fields.append('tags_json = ?')
        values.append(json.dumps(data['tags']) if isinstance(data['tags'], list) else data['tags'])

    values.extend([note_id, uid])
    conn.execute(
        f"UPDATE notes SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
        values,
    )
    conn.commit()

    row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    return jsonify(_serialize(row))


# ---------------------------------------------------------------------------
# DELETE /api/notes/<id>
# ---------------------------------------------------------------------------

@notes_bp.route('/<int:note_id>', methods=['DELETE'])
@login_required
def delete_note(note_id: int):
    """Delete a note."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM notes WHERE id = ? AND user_id = ?", (note_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Note not found'}), 404

    conn.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, uid))
    conn.commit()
    return '', 204


# ---------------------------------------------------------------------------
# POST /api/notes/<id>/pin
# ---------------------------------------------------------------------------

@notes_bp.route('/<int:note_id>/pin', methods=['POST'])
@login_required
def toggle_pin(note_id: int):
    """Toggle the pinned state of a note."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Note not found'}), 404

    new_pinned = 0 if row['pinned'] else 1
    conn.execute(
        "UPDATE notes SET pinned = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (new_pinned, _now_iso(), note_id, uid),
    )
    conn.commit()

    row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    return jsonify(_serialize(row))


# ---------------------------------------------------------------------------
# POST /api/notes/<id>/archive
# ---------------------------------------------------------------------------

@notes_bp.route('/<int:note_id>/archive', methods=['POST'])
@login_required
def toggle_archive(note_id: int):
    """Toggle the archived state of a note."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Note not found'}), 404

    new_archived = 0 if row['archived'] else 1
    conn.execute(
        "UPDATE notes SET archived = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (new_archived, _now_iso(), note_id, uid),
    )
    conn.commit()

    row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    return jsonify(_serialize(row))
