"""Books routes — reading tracker, sessions, stats, and yearly challenge."""
import json
from collections import defaultdict
from datetime import date, datetime
from flask import Blueprint, jsonify, request

from .decorators import login_required, current_user_id
from src.infrastructure.database import get_connection

books_bp = Blueprint('books', __name__, url_prefix='/api/books')

# Status ordering: reading → to-read → finished → everything else
_STATUS_ORDER = {'reading': 0, 'to-read': 1, 'finished': 2}


def _serialize_book(r) -> dict:
    return {
        'id': r['id'],
        'user_id': r['user_id'],
        'title': r['title'],
        'author': r['author'],
        'genre': r['genre'],
        'page_count': r['page_count'],
        'current_page': r['current_page'],
        'status': r['status'],
        'rating': r['rating'],
        'review': r['review'],
        'cover_url': r['cover_url'],
        'format': r['format'],
        'started_at': r['started_at'],
        'finished_at': r['finished_at'],
        'created_at': r['created_at'],
    }


def _serialize_session(r) -> dict:
    return {
        'id': r['id'],
        'user_id': r['user_id'],
        'book_id': r['book_id'],
        'pages_read': r['pages_read'],
        'date': r['date'],
        'created_at': r['created_at'],
    }


# ---------------------------------------------------------------------------
# GET /api/books
# ---------------------------------------------------------------------------

@books_bp.route('')
@login_required
def list_books():
    """List books, optionally filtered by status.

    Ordering: reading first, then to-read, then finished, then other.

    Query parameters:
        status — filter by status string.
    """
    uid = current_user_id()
    status_filter = request.args.get('status', '').strip()

    conn = get_connection()
    query = "SELECT * FROM books WHERE user_id = ?"
    params = [uid]

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)

    rows = conn.execute(query, params).fetchall()

    # Sort in Python to apply custom status ordering
    books = [_serialize_book(r) for r in rows]
    books.sort(key=lambda b: (_STATUS_ORDER.get(b['status'], 99), b['created_at'] or ''))
    return jsonify(books)


# ---------------------------------------------------------------------------
# GET /api/books/stats
# ---------------------------------------------------------------------------

@books_bp.route('/stats')
@login_required
def get_stats():
    """Return reading statistics.

    Response:
        books_this_year   — count of books finished in the current calendar year.
        books_per_month   — list of {month, count} for the last 12 months.
        genre_breakdown   — list of {genre, count} across all books.
        total_pages_read  — sum of pages_read across all reading sessions.
        reading_streak    — current consecutive-day streak of reading sessions.
    """
    uid = current_user_id()
    conn = get_connection()
    this_year = date.today().year

    # Books finished this year
    books_this_year = conn.execute(
        """SELECT COUNT(*) AS cnt FROM books
           WHERE user_id = ? AND status = 'finished'
             AND strftime('%Y', finished_at) = ?""",
        (uid, str(this_year)),
    ).fetchone()['cnt']

    # Books finished per month (last 12 months based on finished_at)
    monthly_rows = conn.execute(
        """SELECT strftime('%Y-%m', finished_at) AS month, COUNT(*) AS cnt
           FROM books
           WHERE user_id = ? AND status = 'finished'
             AND finished_at >= date('now', '-12 months')
           GROUP BY month
           ORDER BY month""",
        (uid,),
    ).fetchall()
    books_per_month = [{'month': r['month'], 'count': r['cnt']} for r in monthly_rows]

    # Genre breakdown
    genre_rows = conn.execute(
        """SELECT genre, COUNT(*) AS cnt FROM books
           WHERE user_id = ? AND genre IS NOT NULL AND genre != ''
           GROUP BY genre
           ORDER BY cnt DESC""",
        (uid,),
    ).fetchall()
    genre_breakdown = [{'genre': r['genre'], 'count': r['cnt']} for r in genre_rows]

    # Total pages read from all sessions
    total_pages = conn.execute(
        "SELECT SUM(pages_read) AS total FROM reading_sessions WHERE user_id = ?",
        (uid,),
    ).fetchone()['total'] or 0

    # Reading streak: consecutive days (ending today or yesterday) with at least one session
    session_dates = conn.execute(
        """SELECT DISTINCT date FROM reading_sessions
           WHERE user_id = ?
           ORDER BY date DESC""",
        (uid,),
    ).fetchall()

    streak = 0
    if session_dates:
        dates = [r['date'] for r in session_dates]
        today_str = date.today().isoformat()
        yesterday_str = date.fromordinal(date.today().toordinal() - 1).isoformat()

        # Streak only counts if the most recent session was today or yesterday
        if dates[0] in (today_str, yesterday_str):
            streak = 1
            prev = date.fromisoformat(dates[0])
            for d_str in dates[1:]:
                d = date.fromisoformat(d_str)
                if (prev - d).days == 1:
                    streak += 1
                    prev = d
                else:
                    break

    return jsonify({
        'books_this_year': books_this_year,
        'books_per_month': books_per_month,
        'genre_breakdown': genre_breakdown,
        'total_pages_read': total_pages,
        'reading_streak': streak,
    })


# ---------------------------------------------------------------------------
# GET /api/books/challenge
# ---------------------------------------------------------------------------

@books_bp.route('/challenge')
@login_required
def get_challenge():
    """Return the yearly reading challenge target and current progress."""
    uid = current_user_id()
    conn = get_connection()
    this_year = date.today().year

    row = conn.execute(
        "SELECT value FROM user_settings WHERE user_id = ? AND key = 'reading_challenge_target'",
        (uid,),
    ).fetchone()
    target = int(row['value']) if row and row['value'] else 0

    finished = conn.execute(
        """SELECT COUNT(*) AS cnt FROM books
           WHERE user_id = ? AND status = 'finished'
             AND strftime('%Y', finished_at) = ?""",
        (uid, str(this_year)),
    ).fetchone()['cnt']

    return jsonify({
        'year': this_year,
        'target': target,
        'finished': finished,
        'remaining': max(0, target - finished),
        'completed': target > 0 and finished >= target,
    })


# ---------------------------------------------------------------------------
# PUT /api/books/challenge
# ---------------------------------------------------------------------------

@books_bp.route('/challenge', methods=['PUT'])
@login_required
def set_challenge():
    """Set the yearly reading challenge target in user_settings."""
    uid = current_user_id()
    data = request.json or {}
    try:
        target = int(data.get('target', 0))
        if target < 0:
            return jsonify({'error': 'target must be a non-negative integer'}), 400
    except (TypeError, ValueError):
        return jsonify({'error': 'target must be an integer'}), 400

    conn = get_connection()
    conn.execute(
        """INSERT INTO user_settings (user_id, key, value)
           VALUES (?, 'reading_challenge_target', ?)
           ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value""",
        (uid, str(target)),
    )
    conn.commit()
    return jsonify({'success': True, 'target': target})


# ---------------------------------------------------------------------------
# GET /api/books/<id>
# ---------------------------------------------------------------------------

@books_bp.route('/<int:book_id>')
@login_required
def get_book(book_id: int):
    """Return a single book with its reading sessions."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM books WHERE id = ? AND user_id = ?", (book_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Book not found'}), 404

    sessions = conn.execute(
        "SELECT * FROM reading_sessions WHERE book_id = ? AND user_id = ? ORDER BY date DESC",
        (book_id, uid),
    ).fetchall()

    book = _serialize_book(row)
    book['sessions'] = [_serialize_session(s) for s in sessions]
    return jsonify(book)


# ---------------------------------------------------------------------------
# POST /api/books
# ---------------------------------------------------------------------------

@books_bp.route('', methods=['POST'])
@login_required
def add_book():
    """Add a new book."""
    uid = current_user_id()
    data = request.json or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'title is required'}), 400

    author = (data.get('author') or '').strip()
    genre = (data.get('genre') or '').strip()
    page_count = data.get('page_count')
    current_page = data.get('current_page', 0)
    status = (data.get('status') or 'to-read').strip()
    rating = data.get('rating')
    review = (data.get('review') or '').strip()
    cover_url = (data.get('cover_url') or '').strip()
    book_format = (data.get('format') or 'physical').strip()

    started_at = None
    finished_at = None
    if status == 'reading':
        started_at = date.today().isoformat()
    elif status == 'finished':
        started_at = data.get('started_at') or date.today().isoformat()
        finished_at = data.get('finished_at') or date.today().isoformat()

    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO books
               (user_id, title, author, genre, page_count, current_page,
                status, rating, review, cover_url, format, started_at, finished_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (uid, title, author, genre, page_count, current_page,
         status, rating, review, cover_url, book_format, started_at, finished_at),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM books WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return jsonify(_serialize_book(row)), 201


# ---------------------------------------------------------------------------
# PUT /api/books/<id>
# ---------------------------------------------------------------------------

@books_bp.route('/<int:book_id>', methods=['PUT'])
@login_required
def update_book(book_id: int):
    """Update a book.

    If status changes to 'reading', started_at is set to today (if not already set).
    If status changes to 'finished', finished_at is set to today (if not already set).
    """
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM books WHERE id = ? AND user_id = ?", (book_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Book not found'}), 404

    data = request.json or {}

    fields = []
    values = []

    for col, key in [
        ('title', 'title'), ('author', 'author'), ('genre', 'genre'),
        ('page_count', 'page_count'), ('current_page', 'current_page'),
        ('rating', 'rating'), ('review', 'review'),
        ('cover_url', 'cover_url'), ('format', 'format'),
        ('started_at', 'started_at'), ('finished_at', 'finished_at'),
    ]:
        if key in data:
            fields.append(f'{col} = ?')
            values.append(data[key])

    if 'status' in data:
        new_status = data['status']
        fields.append('status = ?')
        values.append(new_status)

        # Auto-set dates on status transitions
        if new_status == 'reading' and not row['started_at'] and 'started_at' not in data:
            fields.append('started_at = ?')
            values.append(date.today().isoformat())

        if new_status == 'finished' and not row['finished_at'] and 'finished_at' not in data:
            fields.append('finished_at = ?')
            values.append(date.today().isoformat())

    if fields:
        values.extend([book_id, uid])
        conn.execute(
            f"UPDATE books SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values,
        )
        conn.commit()

    row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    return jsonify(_serialize_book(row))


# ---------------------------------------------------------------------------
# DELETE /api/books/<id>
# ---------------------------------------------------------------------------

@books_bp.route('/<int:book_id>', methods=['DELETE'])
@login_required
def delete_book(book_id: int):
    """Delete a book and cascade-delete its reading sessions."""
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM books WHERE id = ? AND user_id = ?", (book_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Book not found'}), 404

    conn.execute("DELETE FROM reading_sessions WHERE book_id = ? AND user_id = ?", (book_id, uid))
    conn.execute("DELETE FROM books WHERE id = ? AND user_id = ?", (book_id, uid))
    conn.commit()
    return '', 204


# ---------------------------------------------------------------------------
# POST /api/books/<id>/sessions
# ---------------------------------------------------------------------------

@books_bp.route('/<int:book_id>/sessions', methods=['POST'])
@login_required
def log_session(book_id: int):
    """Log a reading session and update the book's current_page.

    Body fields:
        pages_read — integer (required).
        date       — ISO date string (default: today).
    """
    uid = current_user_id()
    conn = get_connection()
    book = conn.execute(
        "SELECT * FROM books WHERE id = ? AND user_id = ?", (book_id, uid)
    ).fetchone()
    if not book:
        return jsonify({'error': 'Book not found'}), 404

    data = request.json or {}
    try:
        pages_read = int(data.get('pages_read', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'pages_read must be an integer'}), 400

    if pages_read <= 0:
        return jsonify({'error': 'pages_read must be a positive integer'}), 400

    session_date = (data.get('date') or date.today().isoformat()).strip()

    cursor = conn.execute(
        """INSERT INTO reading_sessions (user_id, book_id, pages_read, date)
           VALUES (?, ?, ?, ?)""",
        (uid, book_id, pages_read, session_date),
    )

    # Advance current_page (capped at page_count if set)
    new_page = (book['current_page'] or 0) + pages_read
    if book['page_count']:
        new_page = min(new_page, book['page_count'])

    conn.execute(
        "UPDATE books SET current_page = ? WHERE id = ? AND user_id = ?",
        (new_page, book_id, uid),
    )
    conn.commit()

    session_row = conn.execute(
        "SELECT * FROM reading_sessions WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return jsonify(_serialize_session(session_row)), 201
