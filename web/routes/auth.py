"""Authentication routes."""
from flask import Blueprint, render_template, request, redirect, url_for, session
import hashlib

auth_bp = Blueprint('auth', __name__)

# User credentials
USERS = {'dovik': hashlib.sha256('LifeHack2026!'.encode()).hexdigest()}


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        if username in USERS and USERS[username] == hashlib.sha256(password.encode()).hexdigest():
            session['user'] = username
            session.permanent = True
            return redirect(url_for('auth.index'))
        error = 'Invalid credentials'
    return render_template('login.html', error=error)


@auth_bp.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('auth.login'))


from .decorators import login_required

@auth_bp.route('/')
@login_required
def index():
    return render_template('index.html')
