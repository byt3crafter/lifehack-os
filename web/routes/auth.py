"""Authentication routes."""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
)
from werkzeug.security import generate_password_hash, check_password_hash

from src.infrastructure.database import get_connection

auth_bp = Blueprint('auth', __name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SHA256_HEX_LEN = 64  # length of a sha256 hexdigest string


def _hash_password(password: str) -> str:
    """Hash a password using werkzeug (bcrypt-compatible pbkdf2)."""
    return generate_password_hash(password)


def _verify_password(stored_hash: str, password: str) -> bool:
    """Verify password against stored hash.

    Transparently handles legacy SHA-256 hashes (64 hex chars): verifies with
    hashlib and — if correct — re-hashes with werkzeug so the account is
    migrated on first successful login.  Returns (is_valid, needs_rehash).
    """
    if len(stored_hash) == _SHA256_HEX_LEN and all(c in '0123456789abcdef' for c in stored_hash):
        # Legacy SHA-256 path
        sha256_hash = hashlib.sha256(password.encode()).hexdigest()
        return sha256_hash == stored_hash, True
    # Modern werkzeug hash
    return check_password_hash(stored_hash, password), False


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


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


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
        admin_id = cursor.lastrowid
        conn.execute("INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)", (admin_id,))
        conn.execute(
            "INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (admin_id,)
        )
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
        if user:
            is_valid, needs_rehash = _verify_password(user['password_hash'], password)
            if is_valid:
                conn = get_connection()
                if needs_rehash:
                    conn.execute(
                        "UPDATE users SET password_hash = ? WHERE id = ?",
                        (_hash_password(password), user['id']),
                    )
                conn.execute(
                    "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                    (user['id'],),
                )
                conn.commit()
                session['user'] = user['username']
                session['user_id'] = user['id']
                session['is_admin'] = bool(user['is_admin'])
                session.permanent = True
                return redirect(url_for('auth.index'))
        error = 'Invalid credentials'
    return render_template('login.html', error=error)


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


from .decorators import login_required, admin_required, current_user_id  # noqa: E402


@auth_bp.route('/')
@login_required
def index():
    return render_template('index.html')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@auth_bp.route('/register', methods=['GET'])
def register():
    code = request.args.get('code', '')
    return render_template('register.html', code=code)


@auth_bp.route('/register', methods=['POST'])
def register_post():
    username = (request.form.get('username') or '').strip().lower()
    password = request.form.get('password') or ''
    display_name = (request.form.get('display_name') or username).strip()
    code_value = (request.form.get('code') or '').strip()

    # --- Input validation ---
    if not username:
        return render_template('register.html', error='Username is required', code=code_value)
    if len(username) < 3:
        return render_template('register.html', error='Username must be at least 3 characters', code=code_value)
    if not password:
        return render_template('register.html', error='Password is required', code=code_value)
    if len(password) < 8:
        return render_template('register.html', error='Password must be at least 8 characters', code=code_value)
    if not code_value:
        return render_template('register.html', error='Invite code is required', code=code_value)

    conn = get_connection()

    # --- Validate invite code ---
    invite = conn.execute(
        "SELECT * FROM invite_codes WHERE code = ?", (code_value,)
    ).fetchone()
    if not invite:
        return render_template('register.html', error='Invalid invite code', code=code_value)
    if invite['use_count'] >= invite['max_uses']:
        return render_template('register.html', error='Invite code has reached its maximum uses', code=code_value)
    if invite['expires_at'] and datetime.fromisoformat(invite['expires_at']) < _now_utc():
        return render_template('register.html', error='Invite code has expired', code=code_value)

    # --- Check username availability ---
    existing = conn.execute(
        "SELECT id FROM users WHERE username = ?", (username,)
    ).fetchone()
    if existing:
        return render_template('register.html', error='Username already taken', code=code_value)

    # --- Create user ---
    cursor = conn.execute(
        """INSERT INTO users (username, password_hash, display_name, is_admin)
           VALUES (?, ?, ?, 0)""",
        (username, _hash_password(password), display_name),
    )
    conn.commit()
    new_id = cursor.lastrowid

    # --- Increment invite use_count and record used_by ---
    conn.execute(
        "UPDATE invite_codes SET use_count = use_count + 1, used_by = ? WHERE id = ?",
        (new_id, invite['id']),
    )

    # --- Initialise per-user rows ---
    conn.execute("INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)", (new_id,))
    conn.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (new_id,))
    conn.commit()

    # --- Auto-login ---
    session['user'] = username
    session['user_id'] = new_id
    session['is_admin'] = False
    session.permanent = True

    return redirect(url_for('auth.index'))


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

    conn.execute("INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)", (new_id,))
    conn.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (new_id,))
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
    uid = current_user_id()
    is_admin = session.get('is_admin', False)

    if user_id != uid and not is_admin:
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


# ---------------------------------------------------------------------------
# Invite code API
# ---------------------------------------------------------------------------

@auth_bp.route('/api/invite-codes', methods=['POST'])
@login_required
def create_invite_code():
    uid = current_user_id()
    data = request.get_json(silent=True) or {}

    max_uses = int(data.get('max_uses', 1))
    expires_in_days = data.get('expires_in_days')

    if max_uses < 1:
        return jsonify({'error': 'max_uses must be at least 1'}), 400

    code = secrets.token_urlsafe(6)
    expires_at = None
    if expires_in_days is not None:
        expires_at = (_now_utc() + timedelta(days=int(expires_in_days))).isoformat()

    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO invite_codes (code, created_by, max_uses, use_count, expires_at)
           VALUES (?, ?, ?, 0, ?)""",
        (code, uid, max_uses, expires_at),
    )
    conn.commit()
    invite_id = cursor.lastrowid

    base_url = request.host_url.rstrip('/')
    register_url = f"{base_url}/register?code={code}"

    return jsonify({
        'id': invite_id,
        'code': code,
        'url': register_url,
        'max_uses': max_uses,
        'expires_at': expires_at,
    }), 201


@auth_bp.route('/api/invite-codes', methods=['GET'])
@login_required
def list_invite_codes():
    uid = current_user_id()
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, code, max_uses, use_count, used_by, expires_at, created_at
           FROM invite_codes
           WHERE created_by = ?
           ORDER BY created_at DESC""",
        (uid,),
    ).fetchall()
    base_url = request.host_url.rstrip('/')
    codes = []
    for row in rows:
        entry = dict(row)
        entry['url'] = f"{base_url}/register?code={entry['code']}"
        codes.append(entry)
    return jsonify(codes)


@auth_bp.route('/api/invite-codes/<int:invite_id>', methods=['DELETE'])
@login_required
def delete_invite_code(invite_id: int):
    uid = current_user_id()
    is_admin = session.get('is_admin', False)

    conn = get_connection()
    invite = conn.execute(
        "SELECT * FROM invite_codes WHERE id = ?", (invite_id,)
    ).fetchone()
    if not invite:
        return jsonify({'error': 'Invite code not found'}), 404
    if invite['created_by'] != uid and not is_admin:
        return jsonify({'error': 'Forbidden'}), 403

    conn.execute("DELETE FROM invite_codes WHERE id = ?", (invite_id,))
    conn.commit()
    return '', 204


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

@auth_bp.route('/api/password-reset-tokens', methods=['POST'])
@login_required
def create_password_reset_token():
    uid = current_user_id()
    is_admin = session.get('is_admin', False)

    data = request.get_json(silent=True) or {}
    target_user_id = data.get('user_id')

    if target_user_id is not None:
        target_user_id = int(target_user_id)
        if target_user_id != uid and not is_admin:
            return jsonify({'error': 'Forbidden'}), 403
    else:
        target_user_id = uid

    conn = get_connection()
    target_user = _get_user_by_id(target_user_id)
    if not target_user:
        return jsonify({'error': 'User not found'}), 404

    token = secrets.token_urlsafe(32)
    expires_at = (_now_utc() + timedelta(hours=24)).isoformat()

    conn.execute(
        """INSERT INTO password_reset_tokens (user_id, token, expires_at, created_by)
           VALUES (?, ?, ?, ?)""",
        (target_user_id, token, expires_at, uid),
    )
    conn.commit()

    base_url = request.host_url.rstrip('/')
    reset_url = f"{base_url}/reset-password?token={token}"

    return jsonify({
        'token': token,
        'url': reset_url,
        'expires_at': expires_at,
        'user_id': target_user_id,
    }), 201


@auth_bp.route('/reset-password', methods=['GET'])
def reset_password_page():
    token_value = request.args.get('token', '').strip()
    error = None

    if not token_value:
        error = 'Missing reset token'
        return render_template('reset_password.html', error=error, token=token_value)

    conn = get_connection()
    token_row = conn.execute(
        "SELECT * FROM password_reset_tokens WHERE token = ?", (token_value,)
    ).fetchone()

    if not token_row:
        error = 'Invalid reset token'
    elif token_row['used_at']:
        error = 'This reset link has already been used'
    elif datetime.fromisoformat(token_row['expires_at']) < _now_utc():
        error = 'This reset link has expired'

    return render_template('reset_password.html', error=error, token=token_value)


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password_post():
    token_value = (request.form.get('token') or '').strip()
    new_password = request.form.get('new_password') or ''

    if not token_value:
        return render_template('reset_password.html', error='Missing reset token', token=token_value)
    if len(new_password) < 8:
        return render_template('reset_password.html', error='Password must be at least 8 characters', token=token_value)

    conn = get_connection()
    token_row = conn.execute(
        "SELECT * FROM password_reset_tokens WHERE token = ?", (token_value,)
    ).fetchone()

    if not token_row:
        return render_template('reset_password.html', error='Invalid reset token', token=token_value)
    if token_row['used_at']:
        return render_template('reset_password.html', error='This reset link has already been used', token=token_value)
    if datetime.fromisoformat(token_row['expires_at']) < _now_utc():
        return render_template('reset_password.html', error='This reset link has expired', token=token_value)

    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (_hash_password(new_password), token_row['user_id']),
    )
    conn.execute(
        "UPDATE password_reset_tokens SET used_at = ? WHERE id = ?",
        (_now_utc().isoformat(), token_row['id']),
    )
    conn.commit()

    return redirect(url_for('auth.login'))


# ---------------------------------------------------------------------------
# Profile API
# ---------------------------------------------------------------------------

_UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'data', 'uploads', 'profiles',
)
_ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def _allowed_image(filename: str) -> bool:
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in _ALLOWED_IMAGE_EXTENSIONS
    )


def _gravatar_url(email_or_username: str, size: int = 200) -> str:
    """Return a Gravatar URL for the given email or username@lifehack.local."""
    identifier = email_or_username.strip().lower()
    md5_hash = hashlib.md5(identifier.encode()).hexdigest()  # noqa: S324
    return f"https://www.gravatar.com/avatar/{md5_hash}?d=identicon&s={size}"


@auth_bp.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    uid = current_user_id()
    conn = get_connection()
    row = conn.execute(
        """SELECT
               u.id, u.username, u.display_name, u.is_admin, u.created_at, u.last_login,
               p.bio, p.age, p.timezone, p.health_goals, p.fitness_level,
               p.dietary_preferences, p.work_type, p.work_hours, p.photo_path,
               p.height_cm, p.weight_kg, p.gender, p.target_weight_kg, p.preferred_name,
               p.email, p.use_gravatar,
               p.updated_at
           FROM users u
           LEFT JOIN user_profiles p ON p.user_id = u.id
           WHERE u.id = ?""",
        (uid,),
    ).fetchone()

    if not row:
        return jsonify({'error': 'User not found'}), 404

    result = dict(row)

    # Compute BMI if both height and weight are present
    height_cm = result.get('height_cm')
    weight_kg = result.get('weight_kg')
    if height_cm and weight_kg and height_cm > 0:
        result['bmi'] = round(weight_kg / (height_cm / 100) ** 2, 1)
    else:
        result['bmi'] = None

    # Compute photo_url: uploaded photo > gravatar > null
    photo_path = result.get('photo_path') or ''
    use_gravatar = bool(result.get('use_gravatar', 0))
    email = (result.get('email') or '').strip()
    username = result.get('username', '')

    if photo_path:
        result['photo_url'] = f"/uploads/{photo_path}"
    elif use_gravatar:
        gravatar_input = email if email else f"{username}@lifehack.local"
        result['photo_url'] = _gravatar_url(gravatar_input)
    else:
        result['photo_url'] = None

    return jsonify(result)


@auth_bp.route('/api/profile', methods=['PUT'])
@login_required
def update_profile():
    uid = current_user_id()

    # Support both JSON and multipart/form-data (for photo uploads)
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form.to_dict()
    else:
        data = request.get_json(silent=True) or {}

    profile_fields = [
        'bio', 'age', 'timezone', 'health_goals',
        'fitness_level', 'dietary_preferences', 'work_type', 'work_hours',
        'height_cm', 'weight_kg', 'gender', 'target_weight_kg', 'preferred_name',
        'email',
    ]

    conn = get_connection()

    # --- Optional photo upload ---
    photo_path = None
    photo_file = request.files.get('photo')
    if photo_file and photo_file.filename:
        if not _allowed_image(photo_file.filename):
            return jsonify({'error': 'Unsupported image format'}), 400
        from src.infrastructure.services.image_service import process_upload
        from pathlib import Path as P
        upload_base = str(P(_UPLOAD_DIR).parent)
        results = process_upload(
            photo_file, upload_base, 'profiles', str(uid),
            sizes=['thumb', 'micro'], quality=80
        )
        if results.get('thumb'):
            photo_path = results['thumb']
        else:
            os.makedirs(_UPLOAD_DIR, exist_ok=True)
            ext = photo_file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uid}.{ext}"
            save_path = os.path.join(_UPLOAD_DIR, filename)
            photo_file.seek(0)
            photo_file.save(save_path)
            photo_path = f"profiles/{filename}"

    # --- Update display_name on users table if provided ---
    display_name = (data.get('display_name') or '').strip()
    if display_name:
        conn.execute(
            "UPDATE users SET display_name = ? WHERE id = ?",
            (display_name, uid),
        )

    # --- Build user_profiles upsert ---
    updates = {}
    for field in profile_fields:
        if field in data:
            updates[field] = data[field] if data[field] != '' else None
    if photo_path is not None:
        updates['photo_path'] = photo_path
    if 'use_gravatar' in data:
        updates['use_gravatar'] = 1 if data['use_gravatar'] in (True, 'true', '1', 1) else 0
    updates['updated_at'] = _now_utc().isoformat()

    # Ensure profile row exists
    conn.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (uid,))

    if updates:
        set_clause = ', '.join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [uid]
        conn.execute(
            f"UPDATE user_profiles SET {set_clause} WHERE user_id = ?",
            values,
        )

    conn.commit()

    # Return updated profile
    row = conn.execute(
        """SELECT
               u.id, u.username, u.display_name, u.is_admin, u.created_at, u.last_login,
               p.bio, p.age, p.timezone, p.health_goals, p.fitness_level,
               p.dietary_preferences, p.work_type, p.work_hours, p.photo_path,
               p.height_cm, p.weight_kg, p.gender, p.target_weight_kg, p.preferred_name,
               p.email, p.use_gravatar,
               p.updated_at
           FROM users u
           LEFT JOIN user_profiles p ON p.user_id = u.id
           WHERE u.id = ?""",
        (uid,),
    ).fetchone()

    result = dict(row)

    # Compute BMI if both height and weight are present
    height_cm = result.get('height_cm')
    weight_kg = result.get('weight_kg')
    if height_cm and weight_kg and height_cm > 0:
        result['bmi'] = round(weight_kg / (height_cm / 100) ** 2, 1)
    else:
        result['bmi'] = None

    # Compute photo_url: uploaded photo > gravatar > null
    photo_path_val = result.get('photo_path') or ''
    use_gravatar_val = bool(result.get('use_gravatar', 0))
    email_val = (result.get('email') or '').strip()
    username_val = result.get('username', '')

    if photo_path_val:
        result['photo_url'] = f"/uploads/{photo_path_val}"
    elif use_gravatar_val:
        gravatar_input = email_val if email_val else f"{username_val}@lifehack.local"
        result['photo_url'] = _gravatar_url(gravatar_input)
    else:
        result['photo_url'] = None

    return jsonify(result)
