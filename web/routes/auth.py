"""Authentication routes."""
import hashlib
import os

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify

from src.infrastructure.database import get_connection

auth_bp = Blueprint('auth', __name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _get_user_by_username(username: str):
    """Return a Row for the given username or None."""
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM users WHERE username = ?", (username.lower(),)
    ).fetchone()


def _get_user_by_id(user_id: int):
    """Return a Row for the given id or None."""
    conn = get_connection()
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def ensure_admin_user() -> None:
    """Create the admin user from env vars if no users exist yet (first-run bootstrap)."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        username = os.environ.get('LIFEHACK_USERNAME', 'admin').strip().lower()
        password = os.environ.get('LIFEHACK_PASSWORD', 'changeme')
        display_name = username.capitalize()
        cursor = conn.execute(
            """INSERT INTO users (username, password_hash, display_name, is_admin)
               VALUES (?, ?, ?, 1)""",
            (username, _hash_password(password), display_name),
        )
        conn.commit()
        # Initialise user_stats row for the admin user
        admin_id = cursor.lastrowid
        conn.execute("INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)", (admin_id,))
        conn.commit()
        print(f"  Created admin user: {username}")


# ---------------------------------------------------------------------------
# Login / Logout / Index
# ---------------------------------------------------------------------------

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        user = _get_user_by_username(username)
        if user and user['password_hash'] == _hash_password(password):
            session['user'] = user['username']
            session['user_id'] = user['id']
            session['is_admin'] = bool(user['is_admin'])
            session.permanent = True
            # Update last_login timestamp
            conn = get_connection()
            conn.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                (user['id'],),
            )
            conn.commit()
            return redirect(url_for('auth.index'))
        error = 'Invalid credentials'
    return render_template('login.html', error=error)


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


from .decorators import login_required, admin_required  # noqa: E402


@auth_bp.route('/')
@login_required
def index():
    return render_template('index.html')


# ---------------------------------------------------------------------------
# User management API (admin-only for most operations)
# ---------------------------------------------------------------------------

@auth_bp.route('/api/users', methods=['GET'])
@admin_required
def list_users():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, username, display_name, is_admin, created_at, last_login FROM users ORDER BY id"
    ).fetchall()
    users = [dict(row) for row in rows]
    return jsonify(users)


@auth_bp.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip().lower()
    password = data.get('password') or ''
    display_name = (data.get('display_name') or username).strip()
    is_admin = int(bool(data.get('is_admin', False)))

    if not username:
        return jsonify({'error': 'username is required'}), 400
    if not password:
        return jsonify({'error': 'password is required'}), 400

    conn = get_connection()
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        return jsonify({'error': 'Username already exists'}), 409

    cursor = conn.execute(
        """INSERT INTO users (username, password_hash, display_name, is_admin)
           VALUES (?, ?, ?, ?)""",
        (username, _hash_password(password), display_name, is_admin),
    )
    conn.commit()
    new_id = cursor.lastrowid

    # Initialise per-user tables for the new user
    conn.execute("INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)", (new_id,))
    conn.commit()

    row = conn.execute(
        "SELECT id, username, display_name, is_admin, created_at FROM users WHERE id = ?",
        (new_id,),
    ).fetchone()
    return jsonify(dict(row)), 201


@auth_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id: int):
    if user_id == session.get('user_id'):
        return jsonify({'error': 'Cannot delete your own account'}), 400

    conn = get_connection()
    user = _get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    return '', 204


@auth_bp.route('/api/users/<int:user_id>/password', methods=['PUT'])
@login_required
def change_password(user_id: int):
    """Allow a user to change their own password, or an admin to change anyone's."""
    current_user_id = session.get('user_id')
    is_admin = session.get('is_admin', False)

    if user_id != current_user_id and not is_admin:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json(silent=True) or {}
    new_password = data.get('new_password') or ''
    if not new_password:
        return jsonify({'error': 'new_password is required'}), 400

    conn = get_connection()
    user = _get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (_hash_password(new_password), user_id),
    )
    conn.commit()
    return jsonify({'status': 'ok'})
