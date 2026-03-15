#!/usr/bin/env python3
"""Life Hack OS - AI-Native Personal Operating System."""
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from flask_cors import CORS
from functools import wraps
from datetime import date, datetime, timedelta
import hashlib
import secrets
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.database import init_database, get_connection
from src.infrastructure.database.repositories import (
    HabitRepository, ProjectRepository, CheckinRepository,
    WalkRepository, ReplacementRepository, StatsRepository
)
from src.infrastructure.config import load_config
from src.infrastructure.providers import (
    get_task_provider, get_integration_status,
    enable_vikunja, disable_vikunja,
    enable_google_calendar, disable_google_calendar, get_calendar_provider,
    enable_firefly, disable_firefly, get_firefly_provider
)
from src.domain.entities import (
    Habit, HabitCompletion, CompletionStatus, Frequency,
    Project, Milestone, ProjectStatus,
    DailyCheckin, WalkLog, ReplacementLog
)

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = 'lifehack-persistent-secret-2026' # secrets.token_hex(32)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400 * 30  # 30 days
CORS(app)

# Auth
USERS = {'dovik': hashlib.sha256('LifeHack2026!'.encode()).hexdigest()}
API_KEY = 'lifehack_openclaw_2026'  # For OpenClaw API access

# Initialize
init_database()
config = load_config()

# Create insights table
conn = get_connection()
conn.execute('''CREATE TABLE IF NOT EXISTS ai_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    insight_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    dismissed INTEGER DEFAULT 0
)''')
conn.commit()

# Repositories
habit_repo = HabitRepository()
project_repo = ProjectRepository()
checkin_repo = CheckinRepository()
walk_repo = WalkRepository()
replacement_repo = ReplacementRepository()
stats_repo = StatsRepository()

def seed_defaults():
    actions = replacement_repo.get_all_actions()
    if not actions:
        from src.domain.entities import ReplacementAction
        for cat_id, cat_info in config.replacement_categories.items():
            action = ReplacementAction(name=cat_info['name'], category=cat_id, points=cat_info['points'])
            replacement_repo.create_action(action)
seed_defaults()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if key != API_KEY:
            return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated

# ============== AUTH ==============
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        if username in USERS and USERS[username] == hashlib.sha256(password.encode()).hexdigest():
            session['user'] = username
            session.permanent = True
            return redirect(url_for('index'))
        error = 'Invalid credentials'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

# ============== OPENCLAW API ==============
@app.route('/api/openclaw/status', methods=['GET'])
@api_key_required
def openclaw_status():
    """Full status dump for OpenClaw to understand current state."""
    stats = stats_repo.get_stats()
    habits = habit_repo.get_all()
    completions = habit_repo.get_completions_for_date(date.today())
    completed_ids = {c.habit_id for c in completions}
    checkin = checkin_repo.get_for_date(date.today())
    sobriety = checkin_repo.get_sobriety_streak()
    
    # Analyze patterns
    weak_habits = []
    strong_habits = []
    for h in habits:
        streak = habit_repo.get_streak(h.id)
        if streak >= 7:
            strong_habits.append({'name': h.name, 'streak': streak})
        elif streak == 0 and h.id not in completed_ids:
            weak_habits.append({'name': h.name, 'category': h.category})
    
    return jsonify({
        'timestamp': datetime.now().isoformat(),
        'stats': {
            'total_xp': stats.total_xp,
            'level': stats.level,
            'level_name': config.get_level_name(stats.level),
            'sobriety_days': sobriety
        },
        'today': {
            'habits_total': len(habits),
            'habits_completed': len(completed_ids),
            'habits_pending': len(habits) - len(completed_ids),
            'checkin_done': checkin is not None,
            'mood': checkin.mood if checkin else None,
            'energy': checkin.energy if checkin else None,
            'avoided_alcohol': checkin.avoided_alcohol if checkin else None
        },
        'patterns': {
            'strong_habits': strong_habits,
            'weak_habits': weak_habits,
            'needs_attention': len(weak_habits) > len(strong_habits)
        },
        'pending_actions': [h.name for h in habits if h.id not in completed_ids]
    })

@app.route('/api/openclaw/insight', methods=['POST'])
@api_key_required
def openclaw_push_insight():
    """OpenClaw pushes an insight/advice to display on dashboard."""
    data = request.json
    conn = get_connection()
    conn.execute(
        'INSERT INTO ai_insights (insight_type, title, content, priority) VALUES (?, ?, ?, ?)',
        (data.get('type', 'advice'), data['title'], data['content'], data.get('priority', 0))
    )
    conn.commit()
    return jsonify({'success': True})

@app.route('/api/openclaw/checkin', methods=['POST'])
@api_key_required
def openclaw_do_checkin():
    """OpenClaw can submit a check-in on behalf of user (from conversation)."""
    data = request.json
    existing = checkin_repo.get_for_date(date.today())
    is_new = existing is None
    
    checkin = DailyCheckin(
        date=date.today(),
        completed_today=data.get('completed_today', ''),
        avoided_alcohol=data.get('avoided_alcohol', True),
        worked_on_future=data.get('worked_on_future', False),
        mood=data.get('mood', 3),
        energy=data.get('energy', 3),
        improvement_note=data.get('improvement_note', '')
    )
    points = checkin.calculate_points(config.checkin.completion_points, config.checkin.sobriety_bonus, config.checkin.future_work_bonus)
    checkin.points_earned = points
    checkin_repo.save(checkin)
    
    if is_new:
        stats_repo.add_points('checkin', points, "Check-in via OpenClaw", checkin.id)
    
    return jsonify({'success': True, 'points': points})

@app.route('/api/openclaw/habit/complete', methods=['POST'])
@api_key_required
def openclaw_complete_habit():
    """OpenClaw can mark a habit complete by name."""
    data = request.json
    habit_name = data.get('habit_name', '').lower()
    
    habits = habit_repo.get_all()
    for h in habits:
        if habit_name in h.name.lower():
            streak = habit_repo.get_streak(h.id)
            points = h.calculate_points(streak, config.scoring.streak_multiplier_threshold, config.scoring.streak_multiplier)
            completion = HabitCompletion(habit_id=h.id, status=CompletionStatus.COMPLETE, points_earned=points)
            habit_repo.log_completion(completion)
            stats_repo.add_points('habit', points, f"Completed via OpenClaw: {h.name}", h.id)
            return jsonify({'success': True, 'habit': h.name, 'points': points})
    
    return jsonify({'error': 'Habit not found'}), 404

@app.route('/api/openclaw/habit/create', methods=['POST'])
@api_key_required
def openclaw_create_habit():
    """OpenClaw can create a new habit."""
    data = request.json
    habit = Habit(
        name=data['name'],
        category=data.get('category', 'health'),
        frequency=Frequency(data.get('frequency', 'daily')),
        difficulty=data.get('difficulty', 1),
        points=config.scoring.base_habit_points
    )
    habit = habit_repo.create(habit)
    return jsonify({'success': True, 'id': habit.id, 'name': habit.name})

@app.route('/api/openclaw/habits', methods=['GET'])
@api_key_required
def openclaw_list_habits():
    """OpenClaw can list all habits."""
    habits = habit_repo.get_all()
    completions = habit_repo.get_completions_for_date(date.today())
    completed_ids = {c.habit_id for c in completions}
    
    return jsonify([{
        'id': h.id,
        'name': h.name,
        'category': h.category,
        'frequency': h.frequency.value,
        'streak': habit_repo.get_streak(h.id),
        'completed_today': h.id in completed_ids
    } for h in habits])

# ============== USER API ==============
@app.route('/api/stats')
@login_required
def get_stats():
    stats = stats_repo.get_stats()
    sobriety = checkin_repo.get_sobriety_streak()
    return jsonify({
        'total_xp': stats.total_xp,
        'level': stats.level,
        'level_name': config.get_level_name(stats.level),
        'xp_for_next': stats.xp_for_next_level(config.levels.xp_per_level),
        'sobriety_days': sobriety
    })

@app.route('/api/insights')
@login_required
def get_insights():
    conn = get_connection()
    rows = conn.execute(
        'SELECT * FROM ai_insights WHERE dismissed = 0 ORDER BY priority DESC, created_at DESC LIMIT 5'
    ).fetchall()
    return jsonify([{
        'id': r['id'],
        'type': r['insight_type'],
        'title': r['title'],
        'content': r['content'],
        'created_at': r['created_at']
    } for r in rows])

@app.route('/api/insights/<int:insight_id>/dismiss', methods=['POST'])
@login_required
def dismiss_insight(insight_id):
    conn = get_connection()
    conn.execute('UPDATE ai_insights SET dismissed = 1 WHERE id = ?', (insight_id,))
    conn.commit()
    return jsonify({'success': True})

@app.route('/api/habits')
@login_required
def get_habits():
    habits = habit_repo.get_all()
    completions = habit_repo.get_completions_for_date(date.today())
    completed_ids = {c.habit_id for c in completions}
    
    result = []
    for h in habits:
        streak = habit_repo.get_streak(h.id)
        cat_info = config.categories.get(h.category, None)
        result.append({
            'id': h.id, 'name': h.name, 'category': h.category,
            'category_name': cat_info.name if cat_info else h.category,
            'category_color': cat_info.color if cat_info else '#6B7280',
            'frequency': h.frequency.value, 'difficulty': h.difficulty,
            'points': h.points, 'streak': streak,
            'completed': h.id in completed_ids
        })
    return jsonify(result)

@app.route('/api/habits', methods=['POST'])
@login_required
def create_habit():
    data = request.json
    habit = Habit(name=data['name'], category=data.get('category', 'health'),
                  frequency=Frequency(data.get('frequency', 'daily')),
                  difficulty=data.get('difficulty', 1), points=config.scoring.base_habit_points)
    habit = habit_repo.create(habit)
    return jsonify({'id': habit.id, 'success': True})

@app.route('/api/habits/<int:habit_id>/complete', methods=['POST'])
@login_required
def complete_habit(habit_id):
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404
    
    streak = habit_repo.get_streak(habit_id)
    points = habit.calculate_points(streak, config.scoring.streak_multiplier_threshold, config.scoring.streak_multiplier)
    completion = HabitCompletion(habit_id=habit_id, status=CompletionStatus.COMPLETE, points_earned=points)
    habit_repo.log_completion(completion)
    stats_repo.add_points('habit', points, f"Completed: {habit.name}", habit_id)
    return jsonify({'success': True, 'points': points})


@app.route('/api/habits/<int:habit_id>/uncomplete', methods=['POST'])
@login_required
def uncomplete_habit(habit_id):
    """Undo a habit completion for today."""
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404
    
    # Find and delete today's completion
    conn = get_connection()
    result = conn.execute(
        """DELETE FROM habit_completions 
           WHERE habit_id = ? AND date(completed_at) = date('now')""",
        (habit_id,)
    )
    conn.commit()
    
    if result.rowcount > 0:
        # Deduct points
        stats_repo.add_points('habit', -10, f"Undone: {habit.name}", habit_id)
        return jsonify({'success': True, 'undone': True})
    
    return jsonify({'success': False, 'message': 'No completion found for today'})


@app.route('/api/habits/<int:habit_id>/skip', methods=['POST'])
@login_required
def skip_habit(habit_id):
    """Skip a habit for today (no points, no streak break)."""
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404
    
    # Log as skipped (different status)
    completion = HabitCompletion(habit_id=habit_id, status=CompletionStatus.SKIPPED, points_earned=0)
    habit_repo.log_completion(completion)
    return jsonify({'success': True, 'skipped': True})


@app.route('/api/habits/<int:habit_id>', methods=['PUT'])
@login_required
def update_habit(habit_id):
    """Update a habit."""
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404
    
    data = request.json
    if 'name' in data:
        habit.name = data['name']
    if 'category' in data:
        habit.category = data['category']
    if 'difficulty' in data:
        habit.difficulty = data['difficulty']
    if 'active' in data:
        habit.active = data['active']
    
    habit_repo.update(habit)
    return jsonify({'success': True})


@app.route('/api/habits/<int:habit_id>', methods=['DELETE'])
@login_required
def delete_habit(habit_id):
    """Delete (deactivate) a habit."""
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404
    
    # Soft delete - just deactivate
    habit.active = False
    habit_repo.update(habit)
    return jsonify({'success': True, 'deactivated': True})

@app.route('/api/projects')
@login_required
def get_projects():
    """Get projects from configured provider (Vikunja if enabled, else native)."""
    provider = get_task_provider()
    projects = provider.get_projects()
    return jsonify([{
        'id': p.id, 'title': p.title, 'name': p.title,  # 'name' for backwards compat
        'description': p.description,
        'task_count': p.task_count, 'completed_count': p.completed_count,
        'progress': p.progress, 'provider': p.provider
    } for p in projects])


@app.route('/api/tasks')
@login_required
def get_tasks():
    """Get tasks from configured provider."""
    provider = get_task_provider()
    project_id = request.args.get('project_id')
    tasks = provider.get_tasks(project_id)
    return jsonify([{
        'id': t.id, 'title': t.title, 'done': t.done,
        'project_id': t.project_id, 'project_name': t.project_name,
        'due_date': t.due_date.isoformat() if t.due_date else None,
        'priority': t.priority, 'provider': t.provider
    } for t in tasks])


@app.route('/api/tasks', methods=['POST'])
@login_required
def create_task():
    """Create a new task via provider."""
    data = request.json
    provider = get_task_provider()
    task = provider.create_task(
        project_id=data['project_id'],
        title=data['title'],
        description=data.get('description', ''),
        priority=data.get('priority', 0)
    )
    return jsonify({'success': True, 'id': task.id, 'provider': task.provider})


@app.route('/api/tasks/<task_id>/complete', methods=['POST'])
@login_required
def complete_task(task_id):
    """Mark a task as complete via provider."""
    provider = get_task_provider()
    task = provider.complete_task(task_id)
    if task:
        stats_repo.add_points('task', 10, f"Completed: {task.title}")
        return jsonify({'success': True, 'points': 10})
    return jsonify({'error': 'Task not found'}), 404


@app.route('/api/tasks/<task_id>/uncomplete', methods=['POST'])
@login_required
def uncomplete_task(task_id):
    """Mark a task as incomplete via provider."""
    provider = get_task_provider()
    task = provider.uncomplete_task(task_id)
    return jsonify({'success': True}) if task else (jsonify({'error': 'Not found'}), 404)

@app.route('/api/projects', methods=['POST'])
@login_required
def create_project():
    data = request.json
    project = Project(name=data['name'], description=data.get('description', ''))
    project = project_repo.create(project)
    stats_repo.add_points('project', project.points_start, f"Started: {project.name}", project.id)
    return jsonify({'id': project.id, 'success': True})

@app.route('/api/milestones/<int:milestone_id>/complete', methods=['POST'])
@login_required
def complete_milestone(milestone_id):
    project_repo.complete_milestone(milestone_id)
    stats_repo.add_points('milestone', 50, f"Milestone completed", milestone_id)
    return jsonify({'success': True})

@app.route('/api/checkin')
@login_required
def get_checkin():
    checkin = checkin_repo.get_for_date(date.today())
    if not checkin:
        return jsonify(None)
    return jsonify({
        'completed_today': checkin.completed_today, 'avoided_alcohol': checkin.avoided_alcohol,
        'worked_on_future': checkin.worked_on_future, 'mood': checkin.mood,
        'energy': checkin.energy, 'improvement_note': checkin.improvement_note
    })

@app.route('/api/checkin', methods=['POST'])
@login_required
def save_checkin():
    data = request.json
    existing = checkin_repo.get_for_date(date.today())
    is_new = existing is None
    
    checkin = DailyCheckin(
        date=date.today(), completed_today=data.get('completed_today', ''),
        avoided_alcohol=data.get('avoided_alcohol', True), worked_on_future=data.get('worked_on_future', False),
        mood=data.get('mood', 3), energy=data.get('energy', 3), improvement_note=data.get('improvement_note', '')
    )
    points = checkin.calculate_points(config.checkin.completion_points, config.checkin.sobriety_bonus, config.checkin.future_work_bonus)
    checkin.points_earned = points
    checkin_repo.save(checkin)
    
    if is_new:
        stats_repo.add_points('checkin', points, "Daily check-in", checkin.id)
    return jsonify({'success': True, 'points': points})

@app.route('/api/walks')
@login_required
def get_walks():
    walks = walk_repo.get_recent(20)
    stats = walk_repo.get_weekly_stats()
    
    # Custom query for enhanced fields
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM walk_logs ORDER BY logged_at DESC LIMIT 20"
    ).fetchall()
    
    return jsonify({
        'stats': stats,
        'walks': [{
            'id': r['id'], 
            'date': r['logged_at'], 
            'distance_km': r['distance_km'],
            'duration_minutes': r['duration_minutes'], 
            'mood_before': r['mood_before'],
            'mood_after': r['mood_after'], 
            'points': r['points_earned'],
            'location': r['location'],
            'movement_type': r['movement_type']
        } for r in rows]
    })

@app.route('/api/walks', methods=['POST'])
@login_required
def log_walk():
    data = request.json
    distance_km = float(data.get('distance_km', 0))
    duration_minutes = int(data.get('duration_minutes', 0))
    
    # Use repo for basic logic but manual SQL for enhanced fields
    walk = WalkLog(
        distance_km=distance_km, 
        duration_minutes=duration_minutes,
        mood_before=data.get('mood_before', 3), 
        mood_after=data.get('mood_after', 3), 
        notes=data.get('notes', '')
    )
    points = walk.calculate_points(config.walks.base_points, config.walks.km_bonus, config.walks.mood_improvement_bonus)
    
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO walk_logs 
           (logged_at, distance_km, duration_minutes, mood_before, mood_after, points_earned, notes, location, movement_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (datetime.now().isoformat(), distance_km, duration_minutes,
         walk.mood_before, walk.mood_after, points, walk.notes,
         data.get('location', ''), data.get('movement_type', 'exercise'))
    )
    conn.commit()
    
    stats_repo.add_points('walk', points, f"Movement: {data.get('location', 'Walk')}", cursor.lastrowid)
    return jsonify({'success': True, 'points': points})

@app.route('/api/replacements')
@login_required
def get_replacements():
    actions = replacement_repo.get_all_actions()
    logs = replacement_repo.get_recent_logs(10)
    return jsonify({
        'actions': [{'id': a.id, 'name': a.name, 'category': a.category, 'points': a.points} for a in actions],
        'logs': [{'id': l.id, 'action_name': l.action_name, 'urge_level': l.urge_level,
                  'points': l.points_earned, 'date': l.logged_at.isoformat()} for l in logs]
    })

@app.route('/api/replacements', methods=['POST'])
@login_required
def log_replacement():
    data = request.json
    urge_level = data.get('urge_level', 3)
    points = config.replacements.urge_redirect_base + (config.replacements.high_urge_bonus if urge_level >= 4 else 0)
    log = ReplacementLog(action_id=data['action_id'], urge_level=urge_level, points_earned=points, notes=data.get('notes', ''))
    replacement_repo.log_replacement(log)
    stats_repo.add_points('replacement', points, f"Urge redirected (level {urge_level})", log.id)
    return jsonify({'success': True, 'points': points})

@app.route('/api/categories')
@login_required
def get_categories():
    return jsonify({k: {'name': v.name, 'color': v.color, 'icon': v.icon} for k, v in config.categories.items()})


# ============== INTEGRATIONS ==============
@app.route('/api/integrations')
@login_required
def get_integrations():
    """Get status of all integrations."""
    return jsonify(get_integration_status())


@app.route('/api/integrations/vikunja', methods=['POST'])
@login_required
def configure_vikunja():
    """Enable/configure Vikunja integration."""
    data = request.json
    
    if data.get('enabled') is False:
        disable_vikunja()
        return jsonify({'success': True, 'enabled': False})
    
    # Enable with credentials
    api_url = data.get('api_url', 'https://tasks.micinthe.com/api/v1')
    username = data.get('username', '')
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    if enable_vikunja(api_url, username, password):
        return jsonify({'success': True, 'enabled': True, 'connected': True})
    else:
        return jsonify({'error': 'Connection test failed'}), 400


@app.route('/api/integrations/vikunja/test', methods=['POST'])
@login_required
def test_vikunja():
    """Test Vikunja connection without saving."""
    data = request.json
    from src.infrastructure.providers.vikunja import VikunjaTaskProvider, VikunjaConfig
    
    config = VikunjaConfig(
        api_url=data.get('api_url', 'https://tasks.micinthe.com/api/v1'),
        username=data.get('username', ''),
        password=data.get('password', '')
    )
    provider = VikunjaTaskProvider(config)
    connected = provider.test_connection()
    
    return jsonify({'connected': connected})


@app.route('/api/integrations/google_calendar', methods=['POST'])
@login_required
def configure_google_calendar():
    """Enable/disable Google Calendar integration."""
    data = request.json
    
    if data.get('enabled') is False:
        disable_google_calendar()
        return jsonify({'success': True, 'enabled': False})
    
    account = data.get('account', 'dovik@micinthe.com')
    if enable_google_calendar(account):
        return jsonify({'success': True, 'enabled': True, 'connected': True})
    else:
        return jsonify({'error': 'Connection test failed - is gog CLI configured?'}), 400


@app.route('/api/integrations/firefly', methods=['POST'])
@login_required
def configure_firefly():
    """Enable/disable Firefly III integration."""
    data = request.json
    
    if data.get('enabled') is False:
        disable_firefly()
        return jsonify({'success': True, 'enabled': False})
    
    if enable_firefly():
        return jsonify({'success': True, 'enabled': True, 'connected': True})
    else:
        return jsonify({'error': 'Connection test failed - is firefly.sh configured?'}), 400


# ============== CALENDAR API ==============
@app.route('/api/calendar/events')
@login_required
def get_calendar_events():
    """Get upcoming calendar events."""
    provider = get_calendar_provider()
    if not provider:
        return jsonify({'enabled': False, 'events': []})
    
    days = int(request.args.get('days', 7))
    events = provider.get_events(days_ahead=days)
    
    return jsonify({
        'enabled': True,
        'events': [{
            'id': e.id,
            'title': e.title,
            'start': e.start.isoformat(),
            'end': e.end.isoformat(),
            'location': e.location,
            'all_day': e.all_day
        } for e in events]
    })


# ============== FINANCE API ==============
@app.route('/api/finance/summary')
@login_required
def get_finance_summary():
    """Get financial summary."""
    provider = get_firefly_provider()
    if not provider:
        return jsonify({'enabled': False})
    
    balance = provider.get_balance()
    transactions = provider.get_recent_transactions(5)
    
    return jsonify({
        'enabled': True,
        'balance': balance,
        'recent_transactions': [{
            'id': t.id,
            'description': t.description,
            'amount': t.amount,
            'type': t.type,
            'date': t.date.isoformat(),
            'category': t.category
        } for t in transactions]
    })


@app.route('/api/finance/transaction', methods=['POST'])
@login_required
def add_transaction():
    """Add a financial transaction."""
    provider = get_firefly_provider()
    if not provider:
        return jsonify({'error': 'Firefly not enabled'}), 400
    
    data = request.json
    tx_type = data.get('type', 'withdrawal')
    amount = float(data.get('amount', 0))
    description = data.get('description', '')
    category = data.get('category')
    
    if tx_type == 'deposit':
        success = provider.add_deposit(amount, description)
    else:
        success = provider.add_withdrawal(amount, description, category=category)
    
    if success:
        return jsonify({'success': True})
    return jsonify({'error': 'Failed to add transaction'}), 400


# ============== DAILY TRACKING ==============
@app.route('/api/daily')
@login_required
def get_daily_summary():
    """Get today's summary with yesterday comparison."""
    from datetime import date as dt_date, timedelta
    
    today = dt_date.today().isoformat()
    yesterday = (dt_date.today() - timedelta(days=1)).isoformat()
    
    conn = get_connection()
    
    def get_day_stats(d):
        # Habits
        habits = habit_repo.get_all()
        completions = conn.execute(
            "SELECT habit_id FROM habit_completions WHERE date(completed_at) = ?", (d,)
        ).fetchall()
        completed_ids = {r['habit_id'] for r in completions}
        
        # Check-in
        checkin = conn.execute(
            "SELECT * FROM daily_checkins WHERE date = ?", (d,)
        ).fetchone()
        
        # Food
        food_count = conn.execute(
            "SELECT COUNT(*) as c FROM food_logs WHERE date(logged_at) = ?", (d,)
        ).fetchone()['c']
        
        # Walks
        walks = conn.execute(
            "SELECT COUNT(*) as c, SUM(distance_km) as km FROM walk_logs WHERE date(logged_at) = ?", (d,)
        ).fetchone()
        
        # Points earned today
        points = conn.execute(
            "SELECT SUM(points) as p FROM point_ledger WHERE date(timestamp) = ?", (d,)
        ).fetchone()
        
        # Calculate score
        habits_pct = (len(completed_ids) / len(habits) * 100) if habits else 0
        checkin_done = 1 if checkin else 0
        food_done = 1 if food_count >= 2 else 0  # At least 2 meals
        
        # Score = weighted average
        # Habits (40%), Check-in (20%), Food (20%), Movement (20%)
        movement_done = 1 if walks['c'] >= 1 else 0
        score = int((habits_pct * 0.4) + (checkin_done * 20) + (food_done * 20) + (movement_done * 20))
        
        return {
            'date': d,
            'habits_completed': len(completed_ids),
            'habits_total': len(habits),
            'habits_pct': int(habits_pct),
            'checkin_done': checkin_done,
            'mood': checkin['mood'] if checkin else None,
            'energy': checkin['energy'] if checkin else None,
            'avoided_alcohol': checkin['avoided_alcohol'] if checkin else None,
            'food_logged': food_count,
            'walks': walks['c'] or 0,
            'walk_km': walks['km'] or 0,
            'points': points['p'] or 0,
            'score': min(100, score)
        }
    
    today_stats = get_day_stats(today)
    yesterday_stats = get_day_stats(yesterday)
    
    # Calculate deltas
    deltas = {
        'habits': today_stats['habits_completed'] - yesterday_stats['habits_completed'],
        'score': today_stats['score'] - yesterday_stats['score'],
        'points': today_stats['points'] - yesterday_stats['points']
    }
    
    # Generate tips
    tips = []
    if today_stats['habits_pct'] < 50:
        pending = today_stats['habits_total'] - today_stats['habits_completed']
        tips.append(f"💪 {pending} habits left today — pick one to knock out now")
    if not today_stats['checkin_done']:
        tips.append("📝 Don't forget your daily check-in")
    if today_stats['food_logged'] == 0:
        tips.append("🍽️ Log your meals to track nutrition")
    if today_stats['score'] < yesterday_stats['score']:
        tips.append("📈 Yesterday was better — time to step up!")
    
    return jsonify({
        'today': today_stats,
        'yesterday': yesterday_stats,
        'deltas': deltas,
        'tips': tips
    })


@app.route('/api/daily/history')
@login_required  
def get_daily_history():
    """Get daily scores for the last N days."""
    from datetime import date as dt_date, timedelta
    
    days = int(request.args.get('days', 7))
    history = []
    
    conn = get_connection()
    habits = habit_repo.get_all()
    
    for i in range(days):
        d = (dt_date.today() - timedelta(days=i)).isoformat()
        
        completions = conn.execute(
            "SELECT COUNT(*) as c FROM habit_completions WHERE date(completed_at) = ?", (d,)
        ).fetchone()['c']
        
        checkin = conn.execute(
            "SELECT id FROM daily_checkins WHERE date = ?", (d,)
        ).fetchone()
        
        habits_pct = (completions / len(habits) * 100) if habits else 0
        score = int((habits_pct * 0.5) + (25 if checkin else 0) + 25)  # Simplified
        
        history.append({
            'date': d,
            'habits': completions,
            'checkin': 1 if checkin else 0,
            'score': min(100, score)
        })
    
    return jsonify(history)


# ============== FOOD/NUTRITION ==============
@app.route('/api/food')
@login_required
def get_food_logs():
    """Get recent food logs."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM food_logs 
           WHERE date(logged_at) >= date('now', '-7 days')
           ORDER BY logged_at DESC"""
    ).fetchall()
    
    today_cals = conn.execute(
        """SELECT SUM(calories) as total FROM food_logs 
           WHERE date(logged_at) = date('now')"""
    ).fetchone()
    
    return jsonify({
        'logs': [{
            'id': r['id'],
            'logged_at': r['logged_at'],
            'meal_type': r['meal_type'],
            'description': r['description'],
            'calories': r['calories'],
            'protein_g': r['protein_g'],
            'carbs_g': r['carbs_g'],
            'fat_g': r['fat_g'],
            'image_path': r['image_path'],
            'ai_analysis': r['ai_analysis']
        } for r in rows],
        'today_calories': today_cals['total'] or 0
    })


@app.route('/api/food', methods=['POST'])
@login_required
def log_food():
    """Log a meal."""
    data = request.json
    conn = get_connection()
    
    cursor = conn.execute(
        """INSERT INTO food_logs 
           (meal_type, description, calories, protein_g, carbs_g, fat_g, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (data.get('meal_type', 'meal'),
         data.get('description', ''),
         data.get('calories'),
         data.get('protein_g'),
         data.get('carbs_g'),
         data.get('fat_g'),
         data.get('notes', ''))
    )
    conn.commit()
    
    return jsonify({'success': True, 'id': cursor.lastrowid})


@app.route('/api/food/<int:food_id>', methods=['DELETE'])
@login_required
def delete_food(food_id):
    """Delete a food log entry."""
    conn = get_connection()
    conn.execute("DELETE FROM food_logs WHERE id = ?", (food_id,))
    conn.commit()
    return jsonify({'success': True})


@app.route('/api/food/analyze', methods=['POST'])
@api_key_required
def analyze_food():
    """AI analyzes food description and estimates nutrition."""
    data = request.json
    description = data.get('description', '')
    
    # This would be called by OpenClaw with AI analysis
    # For now, store the analysis
    if data.get('food_id'):
        conn = get_connection()
        conn.execute(
            "UPDATE food_logs SET ai_analysis = ?, calories = ?, protein_g = ?, carbs_g = ?, fat_g = ? WHERE id = ?",
            (data.get('ai_analysis'), data.get('calories'), data.get('protein_g'), 
             data.get('carbs_g'), data.get('fat_g'), data.get('food_id'))
        )
        conn.commit()
    
    return jsonify({'success': True})


@app.route('/api/openclaw/food/log', methods=['POST'])
@api_key_required
def openclaw_log_food():
    """OpenClaw can log food with AI-estimated nutrition."""
    data = request.json
    conn = get_connection()
    
    cursor = conn.execute(
        """INSERT INTO food_logs 
           (meal_type, description, calories, protein_g, carbs_g, fat_g, ai_analysis, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (data.get('meal_type', 'meal'),
         data.get('description', ''),
         data.get('calories'),
         data.get('protein_g'),
         data.get('carbs_g'),
         data.get('fat_g'),
         data.get('ai_analysis', ''),
         data.get('notes', ''))
    )
    conn.commit()
    
    return jsonify({'success': True, 'id': cursor.lastrowid})


# ============== FASTING ==============
@app.route('/api/fasting/status')
@login_required
def get_fasting_status():
    conn = get_connection()
    active = conn.execute(
        "SELECT * FROM fasting_logs WHERE status = 'active' ORDER BY start_at DESC LIMIT 1"
    ).fetchone()
    
    last_completed = conn.execute(
        "SELECT * FROM fasting_logs WHERE status = 'completed' ORDER BY end_at DESC LIMIT 5"
    ).fetchall()
    
    return jsonify({
        'active': dict(active) if active else None,
        'history': [dict(r) for r in last_completed]
    })

@app.route('/api/fasting/start', methods=['POST'])
@login_required
def start_fast():
    data = request.json
    conn = get_connection()
    # Close any existing active fasts
    conn.execute("UPDATE fasting_logs SET status = 'cancelled' WHERE status = 'active'")
    
    cursor = conn.execute(
        "INSERT INTO fasting_logs (start_at, target_hours, mood_start) VALUES (?, ?, ?)",
        (datetime.now().isoformat(), data.get('target', 16), data.get('mood', 3))
    )
    conn.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid})

@app.route('/api/fasting/end', methods=['POST'])
@login_required
def end_fast():
    data = request.json
    conn = get_connection()
    active = conn.execute("SELECT id, start_at FROM fasting_logs WHERE status = 'active'").fetchone()
    if not active:
        return jsonify({'error': 'No active fast'}), 400
        
    end_at = datetime.now()
    start_at = datetime.fromisoformat(active['start_at'])
    duration = (end_at - start_at).total_seconds() / 3600
    
    conn.execute(
        "UPDATE fasting_logs SET end_at = ?, status = 'completed', mood_end = ?, notes = ? WHERE id = ?",
        (end_at.isoformat(), data.get('mood', 3), data.get('notes', ''), active['id'])
    )
    
    points = int(duration * 10)
    stats_repo.add_points('fasting', points, f"Completed {duration:.1f}h fast")
    conn.commit()
    return jsonify({'success': True, 'points': points, 'hours': round(duration, 1)})

# ============== WISHLIST ==============
@app.route('/api/wishlist')
@login_required
def get_wishlist():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM wishlist ORDER BY created_at DESC").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/wishlist', methods=['POST'])
@login_required
def add_to_wishlist():
    data = request.json
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO wishlist (title, location, description, category) VALUES (?, ?, ?, ?)",
        (data['title'], data.get('location', ''), data.get('description', ''), data.get('category', 'place'))
    )
    conn.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid})

# ============== DEEP WORK ==============
@app.route('/api/deepwork/status')
@login_required
def get_deepwork_status():
    conn = get_connection()
    active = conn.execute(
        """SELECT dw.*, p.name as project_name FROM deep_work_sessions dw 
           LEFT JOIN projects p ON dw.project_id = p.id 
           WHERE dw.ended_at IS NULL ORDER BY dw.started_at DESC LIMIT 1"""
    ).fetchone()
    
    history = conn.execute(
        """SELECT dw.*, p.name as project_name FROM deep_work_sessions dw 
           LEFT JOIN projects p ON dw.project_id = p.id 
           WHERE dw.ended_at IS NOT NULL ORDER BY dw.ended_at DESC LIMIT 5"""
    ).fetchall()
    
    return jsonify({
        'active': dict(active) if active else None,
        'history': [dict(r) for r in history]
    })

@app.route('/api/deepwork/start', methods=['POST'])
@login_required
def start_deepwork():
    data = request.json
    conn = get_connection()
    # Close existing
    conn.execute("UPDATE deep_work_sessions SET ended_at = CURRENT_TIMESTAMP WHERE ended_at IS NULL")
    
    cursor = conn.execute(
        "INSERT INTO deep_work_sessions (project_id, notes) VALUES (?, ?)",
        (data.get('project_id'), data.get('notes', ''))
    )
    conn.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid})

@app.route('/api/deepwork/end', methods=['POST'])
@login_required
def end_deepwork():
    conn = get_connection()
    active = conn.execute("SELECT id, started_at FROM deep_work_sessions WHERE ended_at IS NULL").fetchone()
    if not active:
        return jsonify({'error': 'No active session'}), 400
        
    start_at = datetime.fromisoformat(active['started_at'].replace(' ', 'T'))
    end_at = datetime.now()
    duration = int((end_at - start_at).total_seconds() / 60)
    
    points = int(duration / 10) * 5 # 5 XP per 10 mins
    
    conn.execute(
        "UPDATE deep_work_sessions SET ended_at = ?, duration_minutes = ?, points_earned = ? WHERE id = ?",
        (end_at.isoformat(), duration, points, active['id'])
    )
    stats_repo.add_points('deepwork', points, f"Deep Work: {duration} mins")
    conn.commit()
    return jsonify({'success': True, 'duration': duration, 'points': points})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8420, debug=False)
