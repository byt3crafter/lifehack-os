"""Data export routes — download any module's data as JSON."""
from flask import Blueprint, jsonify
from datetime import datetime, date

from .decorators import login_required, current_user_id
from src.infrastructure.database import get_connection

export_bp = Blueprint('export', __name__, url_prefix='/api/export')

# Map of module name → list of (table, user_id_column).
# Every entry uses user_id as the scoping column unless noted.
_MODULE_TABLES: dict[str, list[str]] = {
    'habits':     ['habits', 'habit_completions', 'habit_strength'],
    'food':       ['food_logs'],
    'fasting':    ['fasting_logs'],
    'finance':    ['finance_log', 'finance_rules', 'savings_goals', 'subscriptions', 'income_entries'],
    'journal':    ['journal_entries'],
    'books':      ['books', 'reading_sessions'],
    'notes':      ['notes'],
    'challenges': ['challenges', 'challenge_logs'],
    'contacts':   ['contacts', 'contact_interactions', 'gift_ideas'],
    'wellness':   ['water_logs', 'sleep_logs'],
    'checkins':   ['daily_checkins'],
    'walks':      ['walk_logs'],
}


def _rows_for_table(conn, table: str, uid: int) -> list[dict]:
    """Return all rows for a table scoped to uid, converting to plain dicts.

    Falls back to an unscoped query if the table has no user_id column, and
    returns an empty list if the table does not exist at all.
    """
    try:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE user_id = ?", (uid,)
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        # Table might not exist or might not have user_id — return empty
        return []


def _export_module(conn, module: str, uid: int) -> dict:
    """Return a dict of {table_name: [rows]} for a single module."""
    tables = _MODULE_TABLES[module]
    data: dict[str, list[dict]] = {}
    for table in tables:
        data[table] = _rows_for_table(conn, table, uid)
    return data


def _build_response(module: str, data: dict):
    """Wrap data in the standard envelope and attach download headers."""
    today = date.today().isoformat()
    response = jsonify({
        'module': module,
        'exported_at': datetime.utcnow().isoformat(),
        'data': data,
    })
    response.headers['Content-Disposition'] = (
        f'attachment; filename=lifehack_{module}_{today}.json'
    )
    return response


# ── Single module export ────────────────────────────────────────────────────

@export_bp.route('/<module>')
@login_required
def export_module(module: str):
    """Export one module's data as a downloadable JSON file.

    Supported modules: habits, food, fasting, finance, journal, books, notes,
    challenges, contacts, wellness, checkins, walks.
    """
    if module not in _MODULE_TABLES:
        return jsonify({
            'error': f"Unknown module '{module}'.",
            'available': sorted(_MODULE_TABLES.keys()),
        }), 404

    uid = current_user_id()
    conn = get_connection()
    data = _export_module(conn, module, uid)
    return _build_response(module, data)


# ── All-modules export ──────────────────────────────────────────────────────

@export_bp.route('/all')
@login_required
def export_all():
    """Export every module's data as a single downloadable JSON file."""
    uid = current_user_id()
    conn = get_connection()

    all_data: dict[str, dict] = {}
    for module in _MODULE_TABLES:
        all_data[module] = _export_module(conn, module, uid)

    today = date.today().isoformat()
    response = jsonify({
        'module': 'all',
        'exported_at': datetime.utcnow().isoformat(),
        'data': all_data,
    })
    response.headers['Content-Disposition'] = (
        f'attachment; filename=lifehack_all_{today}.json'
    )
    return response
