"""Habits routes — supports simple habits, strength meter, phases, miss tracking,
habit stacks, and template-based habit creation."""
import json
from datetime import date, datetime, timedelta
from flask import Blueprint, jsonify, request

from .decorators import login_required
from src.domain.entities import Habit, HabitCompletion, CompletionStatus, Frequency
from src.domain.services import (
    calculate_strength_change,
    get_strength_label,
    should_unlock_next_phase,
)
from src.infrastructure.database import get_connection
from src.infrastructure.database.repositories import HabitRepository, StatsRepository
from src.infrastructure.config import load_config

habits_bp = Blueprint('habits', __name__, url_prefix='/api/habits')

habit_repo = HabitRepository()
stats_repo = StatsRepository()
config = load_config()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_or_create_strength(conn, habit_id: int) -> dict:
    """Return the habit_strength row for a habit, creating it if absent."""
    row = conn.execute(
        "SELECT * FROM habit_strength WHERE habit_id = ?", (habit_id,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO habit_strength (habit_id) VALUES (?)", (habit_id,)
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM habit_strength WHERE habit_id = ?", (habit_id,)
        ).fetchone()
    return dict(row)


def _update_strength(conn, habit_id: int, completed: bool) -> dict:
    """Apply strength change and return updated strength data."""
    s = _get_or_create_strength(conn, habit_id)
    new_strength = calculate_strength_change(s["strength"], completed)
    peak = max(s["peak_strength"], new_strength)
    now_iso = datetime.now().isoformat()

    if completed:
        conn.execute(
            """UPDATE habit_strength
               SET strength = ?, peak_strength = ?,
                   last_completed = ?, total_completions = total_completions + 1
               WHERE habit_id = ?""",
            (new_strength, peak, now_iso, habit_id),
        )
    else:
        conn.execute(
            """UPDATE habit_strength
               SET strength = ?, last_missed = ?,
                   total_misses = total_misses + 1
               WHERE habit_id = ?""",
            (new_strength, now_iso, habit_id),
        )
    conn.commit()
    return {
        "strength": round(new_strength, 2),
        "peak_strength": round(peak, 2),
        "strength_label": get_strength_label(new_strength),
    }


def _get_current_phase(conn, habit_id: int) -> dict | None:
    """Return the currently active phase for a habit, or None."""
    row = conn.execute(
        """SELECT * FROM habit_phases
           WHERE habit_id = ? AND is_current = 1
           ORDER BY phase_number ASC LIMIT 1""",
        (habit_id,),
    ).fetchone()
    return dict(row) if row else None


def _check_and_advance_phase(conn, habit_id: int, strength: float) -> dict | None:
    """Advance to the next phase if conditions are met. Returns new phase or None."""
    current = _get_current_phase(conn, habit_id)
    if not current:
        return None

    # Count days the habit has been in the current phase
    phase_start = current["created_at"][:10]  # date portion only
    days_in_phase = (date.today() - date.fromisoformat(phase_start)).days

    if not should_unlock_next_phase(strength, days_in_phase):
        return None

    # Mark current phase complete
    conn.execute(
        """UPDATE habit_phases SET is_current = 0, completed_at = ?
           WHERE id = ?""",
        (datetime.now().isoformat(), current["id"]),
    )

    # Activate the next phase
    next_phase = conn.execute(
        """SELECT * FROM habit_phases
           WHERE habit_id = ? AND phase_number = ?""",
        (habit_id, current["phase_number"] + 1),
    ).fetchone()

    if next_phase:
        conn.execute(
            "UPDATE habit_phases SET is_current = 1, created_at = ? WHERE id = ?",
            (datetime.now().isoformat(), next_phase["id"]),
        )
        conn.commit()
        return dict(next_phase)

    conn.commit()
    return None


def _get_phases_with_tasks(conn, habit_id: int) -> list:
    """Return all phases for a habit, each with its micro-tasks."""
    phase_rows = conn.execute(
        "SELECT * FROM habit_phases WHERE habit_id = ? ORDER BY phase_number",
        (habit_id,),
    ).fetchall()

    phases = []
    for phase in phase_rows:
        task_rows = conn.execute(
            "SELECT * FROM habit_micro_tasks WHERE phase_id = ? ORDER BY sort_order",
            (phase["id"],),
        ).fetchall()
        phases.append({
            "id": phase["id"],
            "phase_number": phase["phase_number"],
            "name": phase["name"],
            "description": phase["description"],
            "unlock_after_days": phase["unlock_after_days"],
            "is_current": bool(phase["is_current"]),
            "completed_at": phase["completed_at"],
            "micro_tasks": [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "description": t["description"],
                    "sort_order": t["sort_order"],
                }
                for t in task_rows
            ],
        })
    return phases


def _apply_daily_decay(conn) -> None:
    """Apply -1% strength decay for each active habit not completed today.

    Called from the daily summary endpoint so it runs at most once per day.
    """
    today = date.today().isoformat()
    # Find habits that have a strength row but were NOT completed today
    rows = conn.execute(
        """SELECT hs.habit_id, hs.strength, hs.peak_strength
           FROM habit_strength hs
           WHERE (hs.last_completed IS NULL OR date(hs.last_completed) < ?)""",
        (today,),
    ).fetchall()

    for row in rows:
        new_strength = max(0.0, row["strength"] - 1.0)
        conn.execute(
            "UPDATE habit_strength SET strength = ? WHERE habit_id = ?",
            (new_strength, row["habit_id"]),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Existing endpoints (backwards compatible)
# ---------------------------------------------------------------------------

@habits_bp.route('')
@login_required
def get_habits():
    """List all active habits with strength, current phase, and phase progress."""
    conn = get_connection()
    habits = habit_repo.get_all()
    completions = habit_repo.get_completions_for_date(date.today())
    completed_ids = {c.habit_id for c in completions}

    result = []
    for h in habits:
        streak = habit_repo.get_streak(h.id)
        cat_info = config.categories.get(h.category, None)

        # Strength data
        s_row = conn.execute(
            "SELECT * FROM habit_strength WHERE habit_id = ?", (h.id,)
        ).fetchone()
        strength = round(s_row["strength"], 2) if s_row else 0.0
        strength_label = get_strength_label(strength)

        # Current phase
        current_phase = _get_current_phase(conn, h.id)

        # Phase progress: how many phases total vs completed
        phase_counts = conn.execute(
            """SELECT
                   COUNT(*) as total,
                   SUM(CASE WHEN completed_at IS NOT NULL THEN 1 ELSE 0 END) as done
               FROM habit_phases WHERE habit_id = ?""",
            (h.id,),
        ).fetchone()

        result.append({
            'id': h.id,
            'name': h.name,
            'category': h.category,
            'category_name': cat_info.name if cat_info else h.category,
            'category_color': cat_info.color if cat_info else '#6B7280',
            'frequency': h.frequency.value,
            'difficulty': h.difficulty,
            'points': h.points,
            'streak': streak,
            'completed': h.id in completed_ids,
            'strength': strength,
            'strength_label': strength_label,
            'current_phase': {
                'phase_number': current_phase['phase_number'],
                'name': current_phase['name'],
            } if current_phase else None,
            'phase_progress': {
                'total': phase_counts['total'] or 0,
                'completed': phase_counts['done'] or 0,
            },
        })
    return jsonify(result)


@habits_bp.route('', methods=['POST'])
@login_required
def create_habit():
    """Create a simple habit (phases are optional)."""
    data = request.json
    habit = Habit(
        name=data['name'],
        category=data.get('category', 'health'),
        frequency=Frequency(data.get('frequency', 'daily')),
        difficulty=data.get('difficulty', 1),
        points=config.scoring.base_habit_points,
    )
    habit = habit_repo.create(habit)

    # Initialise strength row immediately so queries never miss
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO habit_strength (habit_id) VALUES (?)", (habit.id,)
    )
    conn.commit()

    return jsonify({'id': habit.id, 'success': True}), 201


@habits_bp.route('/<int:habit_id>/complete', methods=['POST'])
@login_required
def complete_habit(habit_id):
    """Complete a habit, update strength, and check phase unlock."""
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404

    conn = get_connection()
    streak = habit_repo.get_streak(habit_id)
    points = habit.calculate_points(
        streak,
        config.scoring.streak_multiplier_threshold,
        config.scoring.streak_multiplier,
    )
    completion = HabitCompletion(
        habit_id=habit_id,
        status=CompletionStatus.COMPLETE,
        points_earned=points,
    )
    habit_repo.log_completion(completion)
    stats_repo.add_points('habit', points, f"Completed: {habit.name}", habit_id)

    # Strength update
    strength_data = _update_strength(conn, habit_id, completed=True)

    # Phase advance check
    unlocked_phase = _check_and_advance_phase(
        conn, habit_id, strength_data["strength"]
    )

    response = {
        'success': True,
        'points': points,
        **strength_data,
    }
    if unlocked_phase:
        response['phase_unlocked'] = {
            'phase_number': unlocked_phase['phase_number'],
            'name': unlocked_phase['name'],
        }
    return jsonify(response)


@habits_bp.route('/<int:habit_id>/uncomplete', methods=['POST'])
@login_required
def uncomplete_habit(habit_id):
    """Remove today's completion and decay strength slightly."""
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404

    conn = get_connection()
    result = conn.execute(
        """DELETE FROM habit_completions
           WHERE habit_id = ? AND date(completed_at) = date('now')""",
        (habit_id,),
    )
    conn.commit()

    if result.rowcount > 0:
        stats_repo.add_points('habit', -10, f"Undone: {habit.name}", habit_id)
        strength_data = _update_strength(conn, habit_id, completed=False)
        return jsonify({'success': True, 'undone': True, **strength_data})

    return jsonify({'success': False, 'message': 'No completion found for today'})


@habits_bp.route('/<int:habit_id>/skip', methods=['POST'])
@login_required
def skip_habit(habit_id):
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404

    completion = HabitCompletion(
        habit_id=habit_id,
        status=CompletionStatus.SKIPPED,
        points_earned=0,
    )
    habit_repo.log_completion(completion)
    return jsonify({'success': True, 'skipped': True})


@habits_bp.route('/<int:habit_id>', methods=['PUT'])
@login_required
def update_habit(habit_id):
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


@habits_bp.route('/<int:habit_id>', methods=['DELETE'])
@login_required
def delete_habit(habit_id):
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404

    habit.active = False
    habit_repo.update(habit)
    return jsonify({'success': True, 'deactivated': True})


# ---------------------------------------------------------------------------
# New endpoints
# ---------------------------------------------------------------------------

@habits_bp.route('/<int:habit_id>/detail')
@login_required
def get_habit_detail(habit_id):
    """Full habit detail: phases, micro-tasks, strength, stacks, miss log."""
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404

    conn = get_connection()
    streak = habit_repo.get_streak(habit_id)

    s_row = conn.execute(
        "SELECT * FROM habit_strength WHERE habit_id = ?", (habit_id,)
    ).fetchone()
    strength_data = dict(s_row) if s_row else {
        "strength": 0.0, "peak_strength": 0.0,
        "last_completed": None, "last_missed": None,
        "total_completions": 0, "total_misses": 0,
    }

    phases = _get_phases_with_tasks(conn, habit_id)

    stacks = conn.execute(
        "SELECT * FROM habit_stacks WHERE habit_id = ? ORDER BY id",
        (habit_id,),
    ).fetchall()

    miss_logs = conn.execute(
        """SELECT * FROM habit_miss_log WHERE habit_id = ?
           ORDER BY date DESC LIMIT 20""",
        (habit_id,),
    ).fetchall()

    cat_info = config.categories.get(habit.category, None)

    return jsonify({
        'id': habit.id,
        'name': habit.name,
        'category': habit.category,
        'category_name': cat_info.name if cat_info else habit.category,
        'category_color': cat_info.color if cat_info else '#6B7280',
        'frequency': habit.frequency.value,
        'difficulty': habit.difficulty,
        'points': habit.points,
        'active': habit.active,
        'created_at': habit.created_at.isoformat(),
        'streak': streak,
        'strength': round(float(strength_data['strength']), 2),
        'peak_strength': round(float(strength_data['peak_strength']), 2),
        'strength_label': get_strength_label(float(strength_data['strength'])),
        'last_completed': strength_data['last_completed'],
        'last_missed': strength_data['last_missed'],
        'total_completions': strength_data['total_completions'],
        'total_misses': strength_data['total_misses'],
        'phases': phases,
        'stacks': [
            {'id': s['id'], 'trigger': s['trigger_text']}
            for s in stacks
        ],
        'miss_log': [
            {
                'id': m['id'],
                'date': m['date'],
                'reason': m['reason'],
                'blocker': m['blocker'],
                'logged_at': m['logged_at'],
            }
            for m in miss_logs
        ],
    })


@habits_bp.route('/<int:habit_id>/miss', methods=['POST'])
@login_required
def log_habit_miss(habit_id):
    """Log a missed day with optional reason and blocker text."""
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    reason = data.get('reason', '')
    blocker = data.get('blocker', '')
    miss_date = data.get('date', date.today().isoformat())

    conn = get_connection()

    # Prevent duplicate miss log for the same date
    existing = conn.execute(
        "SELECT id FROM habit_miss_log WHERE habit_id = ? AND date = ?",
        (habit_id, miss_date),
    ).fetchone()
    if existing:
        return jsonify({'error': 'Miss already logged for this date'}), 409

    conn.execute(
        """INSERT INTO habit_miss_log (habit_id, date, reason, blocker)
           VALUES (?, ?, ?, ?)""",
        (habit_id, miss_date, reason, blocker),
    )
    conn.commit()

    # Apply strength decay for the miss
    strength_data = _update_strength(conn, habit_id, completed=False)

    return jsonify({'success': True, **strength_data}), 201


@habits_bp.route('/<int:habit_id>/phases', methods=['POST'])
@login_required
def add_habit_phase(habit_id):
    """Add a custom phase (with optional micro-tasks) to an existing habit."""
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    if not data.get('name'):
        return jsonify({'error': 'name is required'}), 400

    conn = get_connection()

    # Determine next phase number
    row = conn.execute(
        "SELECT COALESCE(MAX(phase_number), 0) as max_num FROM habit_phases WHERE habit_id = ?",
        (habit_id,),
    ).fetchone()
    next_num = (row['max_num'] or 0) + 1

    # If this is the first phase, mark it as current
    is_first = next_num == 1
    cursor = conn.execute(
        """INSERT INTO habit_phases
               (habit_id, phase_number, name, description, unlock_after_days, is_current)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            habit_id,
            next_num,
            data['name'],
            data.get('description', ''),
            data.get('unlock_after_days', 14),
            1 if is_first else 0,
        ),
    )
    phase_id = cursor.lastrowid

    # Insert micro-tasks if provided
    micro_tasks = data.get('micro_tasks', [])
    for i, task_name in enumerate(micro_tasks):
        if isinstance(task_name, str):
            task_name = task_name.strip()
            if task_name:
                conn.execute(
                    """INSERT INTO habit_micro_tasks (phase_id, name, sort_order)
                       VALUES (?, ?, ?)""",
                    (phase_id, task_name, i),
                )

    conn.commit()
    return jsonify({'success': True, 'phase_id': phase_id, 'phase_number': next_num}), 201


@habits_bp.route('/templates')
@login_required
def get_templates():
    """List all habit templates, featured first."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM habit_templates
           ORDER BY is_featured DESC, name ASC"""
    ).fetchall()

    templates = []
    for row in rows:
        try:
            phases = json.loads(row['phases_json'])
        except (json.JSONDecodeError, TypeError):
            phases = []
        templates.append({
            'id': row['id'],
            'name': row['name'],
            'description': row['description'],
            'category': row['category'],
            'difficulty': row['difficulty'],
            'duration_weeks': row['duration_weeks'],
            'icon': row['icon'],
            'is_featured': bool(row['is_featured']),
            'phase_count': len(phases),
            'created_at': row['created_at'],
        })
    return jsonify(templates)


@habits_bp.route('/templates/<int:template_id>/start', methods=['POST'])
@login_required
def start_from_template(template_id):
    """Create a habit (with all phases and micro-tasks) from a template."""
    conn = get_connection()
    tpl_row = conn.execute(
        "SELECT * FROM habit_templates WHERE id = ?", (template_id,)
    ).fetchone()
    if not tpl_row:
        return jsonify({'error': 'Template not found'}), 404

    data = request.get_json(silent=True) or {}

    # Allow caller to override habit name
    habit_name = data.get('name', tpl_row['name'])

    habit = Habit(
        name=habit_name,
        category=tpl_row['category'],
        frequency=Frequency.DAILY,
        difficulty=1,
        points=config.scoring.base_habit_points,
    )
    habit = habit_repo.create(habit)

    # Seed strength row
    conn.execute(
        "INSERT OR IGNORE INTO habit_strength (habit_id) VALUES (?)", (habit.id,)
    )

    # Create phases and micro-tasks from template JSON
    try:
        phases = json.loads(tpl_row['phases_json'])
    except (json.JSONDecodeError, TypeError):
        phases = []

    for i, phase_def in enumerate(phases):
        is_current = 1 if i == 0 else 0
        cursor = conn.execute(
            """INSERT INTO habit_phases
                   (habit_id, phase_number, name, description,
                    unlock_after_days, is_current)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                habit.id,
                phase_def.get('phase', i + 1),
                phase_def.get('name', f'Phase {i + 1}'),
                phase_def.get('description', ''),
                phase_def.get('days', 14) or 14,
                is_current,
            ),
        )
        phase_id = cursor.lastrowid

        for j, task_name in enumerate(phase_def.get('micro_tasks', [])):
            if task_name and task_name.strip():
                conn.execute(
                    """INSERT INTO habit_micro_tasks (phase_id, name, sort_order)
                       VALUES (?, ?, ?)""",
                    (phase_id, task_name.strip(), j),
                )

    conn.commit()

    return jsonify({
        'success': True,
        'habit_id': habit.id,
        'name': habit.name,
        'phases_created': len(phases),
    }), 201


@habits_bp.route('/<int:habit_id>/stack', methods=['POST'])
@login_required
def add_habit_stack(habit_id):
    """Add a cue/trigger to stack this habit after an existing behaviour."""
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    trigger = (data.get('trigger') or '').strip()
    if not trigger:
        return jsonify({'error': 'trigger text is required'}), 400

    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO habit_stacks (trigger_text, habit_id) VALUES (?, ?)",
        (trigger, habit_id),
    )
    conn.commit()
    return jsonify({'success': True, 'stack_id': cursor.lastrowid}), 201


@habits_bp.route('/<int:habit_id>/strength-history')
@login_required
def get_strength_history(habit_id):
    """Return strength changes over the last N days, derived from completions and miss log."""
    habit = habit_repo.get_by_id(habit_id)
    if not habit:
        return jsonify({'error': 'Not found'}), 404

    days = min(int(request.args.get('days', 30)), 365)
    conn = get_connection()

    # Build a daily map: date -> 'complete' | 'miss' | None
    start_date = date.today() - timedelta(days=days - 1)

    completion_dates = {
        row['d']
        for row in conn.execute(
            """SELECT DISTINCT date(completed_at) as d FROM habit_completions
               WHERE habit_id = ? AND status = 'complete'
                 AND date(completed_at) >= ?""",
            (habit_id, start_date.isoformat()),
        ).fetchall()
    }

    miss_dates = {
        row['date']
        for row in conn.execute(
            "SELECT date FROM habit_miss_log WHERE habit_id = ? AND date >= ?",
            (habit_id, start_date.isoformat()),
        ).fetchall()
    }

    # Replay strength from the beginning to reconstruct history
    # Start from what we know as the current strength and work backwards is
    # inaccurate, so we replay forward from habit creation with a simplified model.
    # We use the existing habit_strength row as ground truth for "current" and
    # only reconstruct relative daily changes for the requested window.
    s_row = conn.execute(
        "SELECT strength FROM habit_strength WHERE habit_id = ?", (habit_id,)
    ).fetchone()
    current_strength = float(s_row['strength']) if s_row else 0.0

    # Reconstruct by replaying the window in reverse to find the starting point
    # then replay forward for the response.
    simulated = current_strength
    daily_events = []
    for offset in range(days - 1, -1, -1):
        d = date.today() - timedelta(days=offset)
        d_str = d.isoformat()
        if d_str in completion_dates:
            event = 'complete'
        elif d_str in miss_dates:
            event = 'miss'
        else:
            event = None
        daily_events.append((d_str, event))

    # Walk forward and record strength at each step
    history = []
    replay_strength = max(0.0, current_strength)

    # Estimate starting strength by un-applying events in reverse
    temp = current_strength
    for d_str, event in reversed(daily_events):
        # Rough inverse: undo the last event
        if event == 'complete':
            gain = max(2.0, 5.0 - (max(0.0, temp - 5.0) / 25.0))
            temp = max(0.0, temp - gain)
        elif event == 'miss':
            loss = min(8.0, 3.0 + (min(100.0, temp + 8.0) / 33.0))
            temp = min(100.0, temp + loss)
    replay_strength = max(0.0, temp)

    for d_str, event in daily_events:
        if event == 'complete':
            replay_strength = calculate_strength_change(replay_strength, True)
        elif event == 'miss':
            replay_strength = calculate_strength_change(replay_strength, False)
        # No event = passive day (no change in history replay)

        history.append({
            'date': d_str,
            'strength': round(replay_strength, 2),
            'event': event,
            'strength_label': get_strength_label(replay_strength),
        })

    return jsonify({
        'habit_id': habit_id,
        'days': days,
        'current_strength': round(current_strength, 2),
        'strength_label': get_strength_label(current_strength),
        'history': history,
    })


@habits_bp.route('/daily-decay', methods=['POST'])
@login_required
def trigger_daily_decay():
    """Apply passive strength decay for habits not completed today.

    This is called by the daily summary endpoint so it runs at most once
    per day. It replaces the old 'streak reset to 0' model.
    """
    conn = get_connection()
    _apply_daily_decay(conn)
    return jsonify({'success': True, 'message': 'Daily decay applied'})
