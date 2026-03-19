"""Application-wide error and event logging routes."""
from flask import Blueprint, jsonify, request

from .decorators import login_required, admin_required
from src.infrastructure.database import get_connection

app_log_bp = Blueprint('app_log', __name__, url_prefix='/api/logs')


def log_event(level: str, source: str, message: str, detail: str = '') -> None:
    """Log an event to the app_log table.

    Safe to call from anywhere — failures are silently swallowed so that
    a logging error never interrupts the normal request flow.
    """
    try:
        from flask import request as req
        path = req.path if req else ''
        method = req.method if req else ''
    except Exception:
        path = method = ''
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO app_log (level, source, message, detail, request_path, request_method) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (level, source, message, detail[:5000], path, method),
        )
        conn.commit()
    except Exception:
        pass


@app_log_bp.route('')
@login_required
def get_logs():
    """Return recent application logs, optionally filtered by level."""
    level = request.args.get('level', '')
    limit = request.args.get('limit', 100, type=int)
    conn = get_connection()

    if level:
        rows = conn.execute(
            "SELECT * FROM app_log WHERE level = ? ORDER BY timestamp DESC LIMIT ?",
            (level, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM app_log ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return jsonify([{
        'id': r['id'],
        'timestamp': r['timestamp'],
        'level': r['level'],
        'source': r['source'],
        'message': r['message'],
        'detail': r['detail'],
        'path': r['request_path'],
        'method': r['request_method'],
    } for r in rows])


@app_log_bp.route('/clear', methods=['POST'])
@admin_required
def clear_logs():
    """Delete all application logs (admin only)."""
    conn = get_connection()
    conn.execute("DELETE FROM app_log")
    conn.commit()
    return jsonify({'success': True})
