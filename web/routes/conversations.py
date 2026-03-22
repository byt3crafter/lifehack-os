"""Chat conversations — threaded, categorized, pinnable chat threads.

Each conversation belongs to a user and has a category (health, finance,
productivity, life, general).  Messages are linked via conversation_id.
"""
from flask import Blueprint, jsonify, request

from .decorators import login_required, current_user_id
from src.infrastructure.database import get_connection

conversations_bp = Blueprint('conversations', __name__, url_prefix='/api/chat/conversations')

VALID_CATEGORIES = {'health', 'finance', 'productivity', 'life', 'general'}

CATEGORY_META = {
    'health':       {'icon': '💚', 'label': 'Health',       'color': '#22c55e'},
    'finance':      {'icon': '💰', 'label': 'Finance',      'color': '#eab308'},
    'productivity': {'icon': '⚡', 'label': 'Productivity', 'color': '#4f80ff'},
    'life':         {'icon': '🌱', 'label': 'Life',         'color': '#a855f7'},
    'general':      {'icon': '💬', 'label': 'General',      'color': '#9898a6'},
}


def _serialize(row) -> dict:
    d = dict(row)
    meta = CATEGORY_META.get(d.get('category', 'general'), CATEGORY_META['general'])
    d['category_icon'] = meta['icon']
    d['category_label'] = meta['label']
    d['category_color'] = meta['color']
    d['pinned'] = bool(d.get('pinned'))
    d['bookmarked'] = bool(d.get('bookmarked'))
    d['archived'] = bool(d.get('archived'))
    return d


# ── List conversations ──────────────────────────────────────────────────────

@conversations_bp.route('', methods=['GET'])
@login_required
def list_conversations():
    """List user's conversations, optionally filtered by category.

    Query params:
        category — filter by category (optional)
        archived — include archived (default: 0)
    """
    uid = current_user_id()
    conn = get_connection()
    category = request.args.get('category', '').strip().lower()
    show_archived = request.args.get('archived', '0') == '1'

    query = """SELECT c.*, COUNT(m.id) as message_count
               FROM chat_conversations c
               LEFT JOIN chat_messages m ON m.conversation_id = c.id
               WHERE c.user_id = ?"""
    params = [uid]

    if not show_archived:
        query += " AND c.archived = 0"
    if category and category in VALID_CATEGORIES:
        query += " AND c.category = ?"
        params.append(category)

    query += " GROUP BY c.id ORDER BY c.pinned DESC, c.last_message_at DESC"

    rows = conn.execute(query, params).fetchall()
    return jsonify([_serialize(r) for r in rows])


# ── Create conversation ─────────────────────────────────────────────────────

@conversations_bp.route('', methods=['POST'])
@login_required
def create_conversation():
    uid = current_user_id()
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or 'New Chat').strip()
    category = (data.get('category') or 'general').strip().lower()
    if category not in VALID_CATEGORIES:
        category = 'general'

    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO chat_conversations (user_id, title, category)
           VALUES (?, ?, ?)""",
        (uid, title, category),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM chat_conversations WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return jsonify(_serialize(row)), 201


# ── Get single conversation ─────────────────────────────────────────────────

@conversations_bp.route('/<int:conv_id>', methods=['GET'])
@login_required
def get_conversation(conv_id):
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM chat_conversations WHERE id = ? AND user_id = ?",
        (conv_id, uid),
    ).fetchone()
    if not row:
        return jsonify({'error': 'Conversation not found'}), 404
    return jsonify(_serialize(row))


# ── Update conversation ─────────────────────────────────────────────────────

@conversations_bp.route('/<int:conv_id>', methods=['PUT'])
@login_required
def update_conversation(conv_id):
    uid = current_user_id()
    data = request.get_json(silent=True) or {}
    conn = get_connection()

    row = conn.execute(
        "SELECT id FROM chat_conversations WHERE id = ? AND user_id = ?",
        (conv_id, uid),
    ).fetchone()
    if not row:
        return jsonify({'error': 'Conversation not found'}), 404

    updates = []
    params = []
    for field in ('title',):
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])
    for field in ('pinned', 'bookmarked', 'archived'):
        if field in data:
            updates.append(f"{field} = ?")
            params.append(1 if data[field] else 0)
    if 'category' in data:
        cat = data['category'].strip().lower()
        if cat in VALID_CATEGORIES:
            updates.append("category = ?")
            params.append(cat)

    if not updates:
        return jsonify({'error': 'No valid fields to update'}), 400

    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.extend([conv_id, uid])
    conn.execute(
        f"UPDATE chat_conversations SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
        params,
    )
    conn.commit()

    updated = conn.execute(
        "SELECT * FROM chat_conversations WHERE id = ?", (conv_id,)
    ).fetchone()
    return jsonify(_serialize(updated))


# ── Delete conversation ─────────────────────────────────────────────────────

@conversations_bp.route('/<int:conv_id>', methods=['DELETE'])
@login_required
def delete_conversation(conv_id):
    uid = current_user_id()
    conn = get_connection()

    row = conn.execute(
        "SELECT id FROM chat_conversations WHERE id = ? AND user_id = ?",
        (conv_id, uid),
    ).fetchone()
    if not row:
        return jsonify({'error': 'Conversation not found'}), 404

    conn.execute("DELETE FROM chat_messages WHERE conversation_id = ? AND user_id = ?", (conv_id, uid))
    conn.execute("DELETE FROM chat_conversations WHERE id = ? AND user_id = ?", (conv_id, uid))
    conn.commit()
    return '', 204


# ── Get messages for a conversation ─────────────────────────────────────────

@conversations_bp.route('/<int:conv_id>/messages', methods=['GET'])
@login_required
def get_messages(conv_id):
    uid = current_user_id()
    conn = get_connection()

    # Verify ownership
    row = conn.execute(
        "SELECT id FROM chat_conversations WHERE id = ? AND user_id = ?",
        (conv_id, uid),
    ).fetchone()
    if not row:
        return jsonify({'error': 'Conversation not found'}), 404

    limit = min(int(request.args.get('limit', 100)), 500)
    rows = conn.execute(
        """SELECT * FROM (
               SELECT id, role, content, provider, model, created_at
               FROM chat_messages
               WHERE conversation_id = ? AND user_id = ?
               ORDER BY created_at DESC, id DESC
               LIMIT ?
           ) ORDER BY created_at ASC, id ASC""",
        (conv_id, uid, limit),
    ).fetchall()

    return jsonify({'messages': [dict(r) for r in rows]})


# ── Delete messages in a conversation ───────────────────────────────────────

@conversations_bp.route('/<int:conv_id>/messages', methods=['DELETE'])
@login_required
def clear_messages(conv_id):
    uid = current_user_id()
    conn = get_connection()
    conn.execute(
        "DELETE FROM chat_messages WHERE conversation_id = ? AND user_id = ?",
        (conv_id, uid),
    )
    conn.commit()
    return jsonify({'success': True})
