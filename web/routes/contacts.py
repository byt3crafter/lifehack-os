"""Contacts routes — personal CRM for nurturing relationships intentionally."""
from datetime import date, datetime, timedelta
from flask import Blueprint, jsonify, request

from .decorators import login_required, current_user_id
from src.infrastructure.database import get_connection

contacts_bp = Blueprint('contacts', __name__, url_prefix='/api/contacts')

# Frequency thresholds in days
FREQUENCY_DAYS = {
    'weekly': 7,
    'biweekly': 14,
    'monthly': 30,
    'quarterly': 90,
    'yearly': 365,
}


def _compute_days_since(last_contact_date: str | None) -> int | None:
    """Return days since last_contact_date, or None if not set."""
    if not last_contact_date:
        return None
    try:
        last = date.fromisoformat(last_contact_date[:10])
        return (date.today() - last).days
    except (ValueError, TypeError):
        return None


def _is_overdue(days_since: int | None, frequency: str) -> bool:
    """Return True if contact is overdue based on frequency threshold."""
    if days_since is None:
        return True
    threshold = FREQUENCY_DAYS.get(frequency, 30)
    return days_since > threshold


def _serialize_contact(r) -> dict:
    """Serialize a contacts row to a dict with computed fields."""
    days_since = _compute_days_since(r['last_contact_date'])
    return {
        'id': r['id'],
        'user_id': r['user_id'],
        'name': r['name'],
        'relationship': r['relationship'],
        'birthday': r['birthday'],
        'email': r['email'],
        'phone': r['phone'],
        'photo_url': r['photo_url'],
        'notes': r['notes'],
        'reach_out_frequency': r['reach_out_frequency'],
        'last_contact_date': r['last_contact_date'],
        'group_name': r['group_name'],
        'created_at': r['created_at'],
        'days_since_contact': days_since,
        'overdue': _is_overdue(days_since, r['reach_out_frequency']),
    }


def _serialize_interaction(r) -> dict:
    return {
        'id': r['id'],
        'user_id': r['user_id'],
        'contact_id': r['contact_id'],
        'type': r['type'],
        'notes': r['notes'],
        'date': r['date'],
        'created_at': r['created_at'],
    }


def _serialize_gift(r) -> dict:
    return {
        'id': r['id'],
        'user_id': r['user_id'],
        'contact_id': r['contact_id'],
        'idea': r['idea'],
        'link': r['link'],
        'price': r['price'],
        'purchased': bool(r['purchased']),
        'created_at': r['created_at'],
    }


# ---------------------------------------------------------------------------
# GET /api/contacts
# ---------------------------------------------------------------------------

@contacts_bp.route('')
@login_required
def list_contacts():
    """List contacts ordered by longest-since-contact first.

    Query parameters:
        group  — filter by group_name.
        search — substring search across name, relationship, email, phone, notes.
    """
    uid = current_user_id()
    group = request.args.get('group', '').strip()
    search = request.args.get('search', '').strip()

    conn = get_connection()
    query = "SELECT * FROM contacts WHERE user_id = ?"
    params = [uid]

    if group:
        query += " AND group_name = ?"
        params.append(group)

    if search:
        pattern = f"%{search}%"
        query += (
            " AND (name LIKE ? OR relationship LIKE ?"
            " OR email LIKE ? OR phone LIKE ? OR notes LIKE ?)"
        )
        params.extend([pattern, pattern, pattern, pattern, pattern])

    # Order by last_contact_date ASC — NULLs first (most overdue at top)
    query += " ORDER BY last_contact_date ASC NULLS FIRST"

    rows = conn.execute(query, params).fetchall()
    return jsonify([_serialize_contact(r) for r in rows])


# ---------------------------------------------------------------------------
# GET /api/contacts/dashboard
# ---------------------------------------------------------------------------

@contacts_bp.route('/dashboard')
@login_required
def dashboard():
    """Return overdue contacts, upcoming birthdays, and total count."""
    uid = current_user_id()
    conn = get_connection()

    all_contacts = conn.execute(
        "SELECT * FROM contacts WHERE user_id = ? ORDER BY last_contact_date ASC NULLS FIRST",
        (uid,),
    ).fetchall()

    total_contacts = len(all_contacts)

    overdue_contacts = []
    for row in all_contacts:
        days_since = _compute_days_since(row['last_contact_date'])
        if _is_overdue(days_since, row['reach_out_frequency']):
            overdue_contacts.append(_serialize_contact(row))

    # Upcoming birthdays in the next 30 days
    upcoming_birthdays = []
    today = date.today()
    for row in all_contacts:
        birthday = row['birthday']
        if not birthday:
            continue
        try:
            bday = date.fromisoformat(birthday[:10])
            # Replace year with current year; if already passed, use next year
            next_bday = bday.replace(year=today.year)
            if next_bday < today:
                next_bday = bday.replace(year=today.year + 1)
            days_until = (next_bday - today).days
            if 0 <= days_until <= 30:
                c = _serialize_contact(row)
                c['days_until_birthday'] = days_until
                c['next_birthday'] = next_bday.isoformat()
                upcoming_birthdays.append(c)
        except (ValueError, TypeError):
            continue

    upcoming_birthdays.sort(key=lambda c: c['days_until_birthday'])

    return jsonify({
        'overdue_contacts': overdue_contacts,
        'upcoming_birthdays': upcoming_birthdays,
        'total_contacts': total_contacts,
    })


# ---------------------------------------------------------------------------
# GET /api/contacts/<id>
# ---------------------------------------------------------------------------

@contacts_bp.route('/<int:contact_id>')
@login_required
def get_contact(contact_id: int):
    """Return a single contact with recent interactions and gift ideas."""
    uid = current_user_id()
    conn = get_connection()

    row = conn.execute(
        "SELECT * FROM contacts WHERE id = ? AND user_id = ?",
        (contact_id, uid),
    ).fetchone()
    if not row:
        return jsonify({'error': 'Contact not found'}), 404

    interactions = conn.execute(
        "SELECT * FROM contact_interactions WHERE contact_id = ? ORDER BY date DESC LIMIT 20",
        (contact_id,),
    ).fetchall()

    gifts = conn.execute(
        "SELECT * FROM gift_ideas WHERE contact_id = ? ORDER BY created_at DESC",
        (contact_id,),
    ).fetchall()

    contact = _serialize_contact(row)
    contact['recent_interactions'] = [_serialize_interaction(i) for i in interactions]
    contact['gift_ideas'] = [_serialize_gift(g) for g in gifts]
    return jsonify(contact)


# ---------------------------------------------------------------------------
# POST /api/contacts
# ---------------------------------------------------------------------------

@contacts_bp.route('', methods=['POST'])
@login_required
def create_contact():
    """Create a new contact."""
    uid = current_user_id()
    data = request.json or {}

    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400

    relationship = (data.get('relationship') or '').strip()
    birthday = (data.get('birthday') or '').strip() or None
    email = (data.get('email') or '').strip()
    phone = (data.get('phone') or '').strip()
    photo_url = (data.get('photo_url') or '').strip()
    notes = (data.get('notes') or '').strip()
    reach_out_frequency = (data.get('reach_out_frequency') or 'monthly').strip()
    last_contact_date = (data.get('last_contact_date') or '').strip() or None
    group_name = (data.get('group_name') or '').strip()

    if reach_out_frequency not in FREQUENCY_DAYS:
        reach_out_frequency = 'monthly'

    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO contacts
               (user_id, name, relationship, birthday, email, phone, photo_url,
                notes, reach_out_frequency, last_contact_date, group_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (uid, name, relationship, birthday, email, phone, photo_url,
         notes, reach_out_frequency, last_contact_date, group_name),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM contacts WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return jsonify(_serialize_contact(row)), 201


# ---------------------------------------------------------------------------
# PUT /api/contacts/<id>
# ---------------------------------------------------------------------------

@contacts_bp.route('/<int:contact_id>', methods=['PUT'])
@login_required
def update_contact(contact_id: int):
    """Update an existing contact."""
    uid = current_user_id()
    conn = get_connection()

    row = conn.execute(
        "SELECT * FROM contacts WHERE id = ? AND user_id = ?",
        (contact_id, uid),
    ).fetchone()
    if not row:
        return jsonify({'error': 'Contact not found'}), 404

    data = request.json or {}
    fields = []
    values = []

    for col in [
        'name', 'relationship', 'birthday', 'email', 'phone',
        'photo_url', 'notes', 'last_contact_date', 'group_name',
    ]:
        if col in data:
            fields.append(f'{col} = ?')
            values.append((data[col] or '').strip() or None if col in ('birthday', 'last_contact_date') else (data[col] or '').strip())

    if 'reach_out_frequency' in data:
        freq = (data['reach_out_frequency'] or 'monthly').strip()
        if freq not in FREQUENCY_DAYS:
            freq = 'monthly'
        fields.append('reach_out_frequency = ?')
        values.append(freq)

    if fields:
        values.extend([contact_id, uid])
        conn.execute(
            f"UPDATE contacts SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values,
        )
        conn.commit()

    row = conn.execute(
        "SELECT * FROM contacts WHERE id = ?", (contact_id,)
    ).fetchone()
    return jsonify(_serialize_contact(row))


# ---------------------------------------------------------------------------
# DELETE /api/contacts/<id>
# ---------------------------------------------------------------------------

@contacts_bp.route('/<int:contact_id>', methods=['DELETE'])
@login_required
def delete_contact(contact_id: int):
    """Delete a contact and cascade to interactions and gift ideas."""
    uid = current_user_id()
    conn = get_connection()

    row = conn.execute(
        "SELECT id FROM contacts WHERE id = ? AND user_id = ?",
        (contact_id, uid),
    ).fetchone()
    if not row:
        return jsonify({'error': 'Contact not found'}), 404

    conn.execute(
        "DELETE FROM contacts WHERE id = ? AND user_id = ?",
        (contact_id, uid),
    )
    conn.commit()
    return '', 204


# ---------------------------------------------------------------------------
# POST /api/contacts/<id>/interactions — log an interaction
# ---------------------------------------------------------------------------

@contacts_bp.route('/<int:contact_id>/interactions', methods=['POST'])
@login_required
def log_interaction(contact_id: int):
    """Log an interaction and auto-update last_contact_date."""
    uid = current_user_id()
    conn = get_connection()

    contact = conn.execute(
        "SELECT id FROM contacts WHERE id = ? AND user_id = ?",
        (contact_id, uid),
    ).fetchone()
    if not contact:
        return jsonify({'error': 'Contact not found'}), 404

    data = request.json or {}
    interaction_type = (data.get('type') or 'other').strip()
    valid_types = {'call', 'text', 'meeting', 'coffee', 'email', 'other'}
    if interaction_type not in valid_types:
        interaction_type = 'other'

    notes = (data.get('notes') or '').strip()
    interaction_date = (data.get('date') or date.today().isoformat()).strip()

    cursor = conn.execute(
        """INSERT INTO contact_interactions
               (user_id, contact_id, type, notes, date)
           VALUES (?, ?, ?, ?, ?)""",
        (uid, contact_id, interaction_type, notes, interaction_date),
    )

    # Update last_contact_date if this interaction is more recent
    conn.execute(
        """UPDATE contacts
           SET last_contact_date = ?
           WHERE id = ? AND user_id = ?
             AND (last_contact_date IS NULL OR last_contact_date < ?)""",
        (interaction_date, contact_id, uid, interaction_date),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM contact_interactions WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return jsonify(_serialize_interaction(row)), 201


# ---------------------------------------------------------------------------
# GET /api/contacts/<id>/interactions
# ---------------------------------------------------------------------------

@contacts_bp.route('/<int:contact_id>/interactions')
@login_required
def list_interactions(contact_id: int):
    """List all interactions for a contact."""
    uid = current_user_id()
    conn = get_connection()

    contact = conn.execute(
        "SELECT id FROM contacts WHERE id = ? AND user_id = ?",
        (contact_id, uid),
    ).fetchone()
    if not contact:
        return jsonify({'error': 'Contact not found'}), 404

    rows = conn.execute(
        "SELECT * FROM contact_interactions WHERE contact_id = ? ORDER BY date DESC",
        (contact_id,),
    ).fetchall()
    return jsonify([_serialize_interaction(r) for r in rows])


# ---------------------------------------------------------------------------
# POST /api/contacts/<id>/gifts — add a gift idea
# ---------------------------------------------------------------------------

@contacts_bp.route('/<int:contact_id>/gifts', methods=['POST'])
@login_required
def add_gift(contact_id: int):
    """Add a gift idea for a contact."""
    uid = current_user_id()
    conn = get_connection()

    contact = conn.execute(
        "SELECT id FROM contacts WHERE id = ? AND user_id = ?",
        (contact_id, uid),
    ).fetchone()
    if not contact:
        return jsonify({'error': 'Contact not found'}), 404

    data = request.json or {}
    idea = (data.get('idea') or '').strip()
    if not idea:
        return jsonify({'error': 'idea is required'}), 400

    link = (data.get('link') or '').strip()
    price = data.get('price')
    if price is not None:
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = None

    cursor = conn.execute(
        """INSERT INTO gift_ideas (user_id, contact_id, idea, link, price)
           VALUES (?, ?, ?, ?, ?)""",
        (uid, contact_id, idea, link, price),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM gift_ideas WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return jsonify(_serialize_gift(row)), 201


# ---------------------------------------------------------------------------
# PUT /api/contacts/gifts/<gift_id>
# ---------------------------------------------------------------------------

@contacts_bp.route('/gifts/<int:gift_id>', methods=['PUT'])
@login_required
def update_gift(gift_id: int):
    """Update a gift idea (e.g. mark purchased)."""
    uid = current_user_id()
    conn = get_connection()

    row = conn.execute(
        "SELECT * FROM gift_ideas WHERE id = ? AND user_id = ?",
        (gift_id, uid),
    ).fetchone()
    if not row:
        return jsonify({'error': 'Gift idea not found'}), 404

    data = request.json or {}
    fields = []
    values = []

    for col in ('idea', 'link'):
        if col in data:
            fields.append(f'{col} = ?')
            values.append((data[col] or '').strip())

    if 'price' in data:
        try:
            price = float(data['price']) if data['price'] is not None else None
        except (TypeError, ValueError):
            price = None
        fields.append('price = ?')
        values.append(price)

    if 'purchased' in data:
        fields.append('purchased = ?')
        values.append(1 if data['purchased'] else 0)

    if fields:
        values.extend([gift_id, uid])
        conn.execute(
            f"UPDATE gift_ideas SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values,
        )
        conn.commit()

    row = conn.execute(
        "SELECT * FROM gift_ideas WHERE id = ?", (gift_id,)
    ).fetchone()
    return jsonify(_serialize_gift(row))


# ---------------------------------------------------------------------------
# DELETE /api/contacts/gifts/<gift_id>
# ---------------------------------------------------------------------------

@contacts_bp.route('/gifts/<int:gift_id>', methods=['DELETE'])
@login_required
def delete_gift(gift_id: int):
    """Delete a gift idea."""
    uid = current_user_id()
    conn = get_connection()

    row = conn.execute(
        "SELECT id FROM gift_ideas WHERE id = ? AND user_id = ?",
        (gift_id, uid),
    ).fetchone()
    if not row:
        return jsonify({'error': 'Gift idea not found'}), 404

    conn.execute(
        "DELETE FROM gift_ideas WHERE id = ? AND user_id = ?",
        (gift_id, uid),
    )
    conn.commit()
    return '', 204
