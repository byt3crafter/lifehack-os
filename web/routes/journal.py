"""Journal routes — daily reflections, mood tracking, and gratitude logs."""
import json
from datetime import date, datetime
from flask import Blueprint, jsonify, request

from .decorators import login_required, current_user_id
from src.infrastructure.database import get_connection

journal_bp = Blueprint('journal', __name__, url_prefix='/api/journal')


def _serialize(r) -> dict:
    """Serialize a journal_entries row to a dict, expanding JSON fields."""
    def _load_json_list(val):
        if not val:
            return []
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            return []

    return {
        'id': r['id'],
        'user_id': r['user_id'],
        'date': r['date'],
        'mood': r['mood'],
        'energy': r['energy'],
        'gratitude': _load_json_list(r['gratitude_json']),
        'wins': _load_json_list(r['wins_json']),
        'lessons': r['lessons'],
        'content': r['content'],
        'tags': _load_json_list(r['tags_json']),
        'created_at': r['created_at'],
    }


# ---------------------------------------------------------------------------
# GET /api/journal
# ---------------------------------------------------------------------------

@journal_bp.route('')
@login_required
def list_entries():
    """List journal entries.

    Query parameters:
        date   — ISO date string (YYYY-MM-DD), filter to a single day.
        search — substring search across content, gratitude, wins, lessons, tags.
        limit  — max rows to return (default 30).
    """
    uid = current_user_id()
    date_param = request.args.get('date', '').strip()
    search = request.args.get('search', '').strip()
    try:
        limit = int(request.args.get('limit', 30))
    except (TypeError, ValueError):
        limit = 30

    conn = get_connection()
    query = "SELECT * FROM journal_entries WHERE user_id = ?"
    params = [uid]

    if date_param:
        query += " AND date = ?"
        params.append(date_param)

    if search:
        pattern = f"%{search}%"
        query += (
            " AND (content LIKE ? OR gratitude_json LIKE ?"
            " OR wins_json LIKE ? OR lessons LIKE ? OR tags_json LIKE ?)"
        )
        params.extend([pattern, pattern, pattern, pattern, pattern])

    query += " ORDER BY date DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return jsonify([_serialize(r) for r in rows])


# ---------------------------------------------------------------------------
# GET /api/journal/on-this-day
# ---------------------------------------------------------------------------

@journal_bp.route('/on-this-day')
@login_required
def on_this_day():
    """Return entries from the same month/day in all previous years."""
    uid = current_user_id()
    today = date.today()
    month_day = today.strftime('%m-%d')

    conn = get_connection()
    # Match rows where date ends with the same MM-DD but year is earlier
    rows = conn.execute(
        """SELECT * FROM journal_entries
           WHERE user_id = ?
             AND strftime('%m-%d', date) = ?
             AND date < date('now')
           ORDER BY date DESC""",
        (uid, month_day),
    ).fetchall()
    return jsonify([_serialize(r) for r in rows])


# ---------------------------------------------------------------------------
# GET /api/journal/search
# ---------------------------------------------------------------------------

@journal_bp.route('/search')
@login_required
def search_entries():
    """Full-text search across all text fields.

    Query parameters:
        q — search term (required).
    """
    uid = current_user_id()
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'error': 'q parameter is required'}), 400

    pattern = f"%{q}%"
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM journal_entries
           WHERE user_id = ?
             AND (content LIKE ? OR gratitude_json LIKE ?
                  OR wins_json LIKE ? OR lessons LIKE ? OR tags_json LIKE ?)
           ORDER BY date DESC""",
        (uid, pattern, pattern, pattern, pattern, pattern),
    ).fetchall()
    return jsonify([_serialize(r) for r in rows])


# ---------------------------------------------------------------------------
# GET /api/journal/<id>
# ---------------------------------------------------------------------------

@journal_bp.route('/<int:entry_id>')
@login_required
def get_entry(entry_id: int):
    """Return a single journal entry."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM journal_entries WHERE id = ? AND user_id = ?",
        (entry_id, uid),
    ).fetchone()
    if not row:
        return jsonify({'error': 'Entry not found'}), 404
    return jsonify(_serialize(row))


# ---------------------------------------------------------------------------
# POST /api/journal
# ---------------------------------------------------------------------------

@journal_bp.route('', methods=['POST'])
@login_required
def create_entry():
    """Create or upsert a journal entry.

    If an entry already exists for the given date + user, it is updated
    in place (upsert). Otherwise a new row is inserted.

    Body fields:
        date       — ISO date string (default: today).
        mood       — integer 1–10.
        energy     — integer 1–10.
        gratitude  — list of strings (stored as JSON).
        wins       — list of strings (stored as JSON).
        lessons    — string.
        content    — string.
        tags       — list of strings (stored as JSON).
    """
    uid = current_user_id()
    data = request.json or {}

    entry_date = (data.get('date') or date.today().isoformat()).strip()
    mood = data.get('mood')
    energy = data.get('energy')
    gratitude_json = json.dumps(data['gratitude']) if isinstance(data.get('gratitude'), list) else data.get('gratitude_json', '[]')
    wins_json = json.dumps(data['wins']) if isinstance(data.get('wins'), list) else data.get('wins_json', '[]')
    lessons = (data.get('lessons') or '').strip()
    content = (data.get('content') or '').strip()
    tags_json = json.dumps(data['tags']) if isinstance(data.get('tags'), list) else data.get('tags_json', '[]')

    conn = get_connection()

    # Check for existing entry on this date
    existing = conn.execute(
        "SELECT id FROM journal_entries WHERE user_id = ? AND date = ?",
        (uid, entry_date),
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE journal_entries
               SET mood = ?, energy = ?, gratitude_json = ?, wins_json = ?,
                   lessons = ?, content = ?, tags_json = ?
               WHERE id = ? AND user_id = ?""",
            (mood, energy, gratitude_json, wins_json,
             lessons, content, tags_json, existing['id'], uid),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM journal_entries WHERE id = ?", (existing['id'],)
        ).fetchone()
        return jsonify(_serialize(row))

    cursor = conn.execute(
        """INSERT INTO journal_entries
               (user_id, date, mood, energy, gratitude_json, wins_json,
                lessons, content, tags_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (uid, entry_date, mood, energy, gratitude_json, wins_json,
         lessons, content, tags_json),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM journal_entries WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return jsonify(_serialize(row)), 201


# ---------------------------------------------------------------------------
# PUT /api/journal/<id>
# ---------------------------------------------------------------------------

@journal_bp.route('/<int:entry_id>', methods=['PUT'])
@login_required
def update_entry(entry_id: int):
    """Update an existing journal entry."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM journal_entries WHERE id = ? AND user_id = ?",
        (entry_id, uid),
    ).fetchone()
    if not row:
        return jsonify({'error': 'Entry not found'}), 404

    data = request.json or {}

    fields = []
    values = []

    for col, key in [
        ('date', 'date'), ('mood', 'mood'), ('energy', 'energy'),
        ('lessons', 'lessons'), ('content', 'content'),
    ]:
        if key in data:
            fields.append(f'{col} = ?')
            values.append(data[key])

    for json_col, list_key in [
        ('gratitude_json', 'gratitude'),
        ('wins_json', 'wins'),
        ('tags_json', 'tags'),
    ]:
        if list_key in data:
            fields.append(f'{json_col} = ?')
            values.append(json.dumps(data[list_key]) if isinstance(data[list_key], list) else data[list_key])

    if fields:
        values.extend([entry_id, uid])
        conn.execute(
            f"UPDATE journal_entries SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values,
        )
        conn.commit()

    row = conn.execute(
        "SELECT * FROM journal_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    return jsonify(_serialize(row))


# ---------------------------------------------------------------------------
# DELETE /api/journal/<id>
# ---------------------------------------------------------------------------

@journal_bp.route('/<int:entry_id>', methods=['DELETE'])
@login_required
def delete_entry(entry_id: int):
    """Delete a journal entry."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM journal_entries WHERE id = ? AND user_id = ?",
        (entry_id, uid),
    ).fetchone()
    if not row:
        return jsonify({'error': 'Entry not found'}), 404

    conn.execute(
        "DELETE FROM journal_entries WHERE id = ? AND user_id = ?",
        (entry_id, uid),
    )
    conn.commit()
    return '', 204
