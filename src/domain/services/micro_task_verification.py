"""Micro-task verification engine.

Supports auto-verified checks against live database tables and manual
tick-box completions stored in micro_task_completions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from src.infrastructure.database.user_scope import get_user_setting


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    """Result of verifying a single micro-task for a given date."""
    verified: bool
    current_value: Optional[float] = None
    target_value: Optional[float] = None
    check_type: str = 'manual'
    message: str = ''


# ---------------------------------------------------------------------------
# Individual check implementations
# ---------------------------------------------------------------------------

def _check_food_log_count(conn, user_id: int, target_date: str, rule: dict) -> VerificationResult:
    """COUNT rows in food_logs for the given date."""
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM food_logs WHERE user_id = ? AND date(logged_at) = ?",
        (user_id, target_date),
    ).fetchone()
    count = float(row['cnt'] or 0)
    threshold = float(rule.get('value', 1))
    op = rule.get('operator', '>=')
    verified = _apply_operator(count, op, threshold)
    return VerificationResult(
        verified=verified,
        current_value=count,
        target_value=threshold,
        check_type='food_log_count',
        message=f'{int(count)} meal(s) logged (need {op} {int(threshold)})',
    )


def _check_walk_count(conn, user_id: int, target_date: str, rule: dict) -> VerificationResult:
    """COUNT walk/exercise entries for the given date."""
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM walk_logs WHERE user_id = ? AND date(logged_at) = ?",
        (user_id, target_date),
    ).fetchone()
    count = float(row['cnt'] or 0)
    threshold = float(rule.get('value', 1))
    op = rule.get('operator', '>=')
    verified = _apply_operator(count, op, threshold)
    return VerificationResult(
        verified=verified,
        current_value=count,
        target_value=threshold,
        check_type='walk_count',
        message=f'{int(count)} walk(s) logged (need {op} {int(threshold)})',
    )


def _check_walk_km(conn, user_id: int, target_date: str, rule: dict) -> VerificationResult:
    """SUM distance_km from walk_logs for the given date."""
    row = conn.execute(
        "SELECT COALESCE(SUM(distance_km), 0) as total FROM walk_logs WHERE user_id = ? AND date(logged_at) = ?",
        (user_id, target_date),
    ).fetchone()
    total_km = float(row['total'] or 0)
    threshold = float(rule.get('value', 1))
    op = rule.get('operator', '>=')
    verified = _apply_operator(total_km, op, threshold)
    return VerificationResult(
        verified=verified,
        current_value=total_km,
        target_value=threshold,
        check_type='walk_km',
        message=f'{total_km:.1f} km walked (need {op} {threshold} km)',
    )


def _check_checkin_done(conn, user_id: int, target_date: str, rule: dict) -> VerificationResult:
    """EXISTS check for a daily_checkins row on the given date."""
    row = conn.execute(
        "SELECT id FROM daily_checkins WHERE user_id = ? AND date = ?",
        (user_id, target_date),
    ).fetchone()
    verified = row is not None
    return VerificationResult(
        verified=verified,
        check_type='checkin_done',
        message='Mood logged today' if verified else 'Log your mood on the Dashboard',
    )


def _check_deep_work_minutes(conn, user_id: int, target_date: str, rule: dict) -> VerificationResult:
    """SUM duration_minutes from deep_work_sessions for the given date."""
    row = conn.execute(
        """SELECT COALESCE(SUM(duration_minutes), 0) as total
           FROM deep_work_sessions
           WHERE user_id = ? AND date(started_at) = ? AND ended_at IS NOT NULL""",
        (user_id, target_date),
    ).fetchone()
    total = float(row['total'] or 0)
    threshold = float(rule.get('value', 25))
    op = rule.get('operator', '>=')
    verified = _apply_operator(total, op, threshold)
    return VerificationResult(
        verified=verified,
        current_value=total,
        target_value=threshold,
        check_type='deep_work_minutes',
        message=f'{int(total)} min deep work (need {op} {int(threshold)} min)',
    )


def _check_calories_under_goal(conn, user_id: int, target_date: str, rule: dict) -> VerificationResult:
    """SUM calories from food_logs < daily_calorie_goal from user_settings (with app_settings fallback)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(calories), 0) as total FROM food_logs WHERE user_id = ? AND date(logged_at) = ?",
        (user_id, target_date),
    ).fetchone()
    total_cal = float(row['total'] or 0)

    # Read calorie goal — user_settings first, fall back to app_settings, then hard default
    goal = float(get_user_setting(conn, user_id, 'daily_calorie_goal', '2000'))

    verified = total_cal > 0 and total_cal < goal
    return VerificationResult(
        verified=verified,
        current_value=total_cal,
        target_value=goal,
        check_type='calories_under_goal',
        message=f'{int(total_cal)} kcal logged (goal < {int(goal)} kcal)',
    )


def _check_no_alcohol(conn, user_id: int, target_date: str, rule: dict) -> VerificationResult:
    """avoided_alcohol = 1 in daily_checkins for the given date."""
    row = conn.execute(
        "SELECT avoided_alcohol FROM daily_checkins WHERE user_id = ? AND date = ?",
        (user_id, target_date),
    ).fetchone()
    if row is None:
        # No check-in yet — cannot confirm
        return VerificationResult(
            verified=False,
            check_type='no_alcohol',
            message='Log mood first to verify sobriety',
        )
    verified = bool(row['avoided_alcohol'])
    return VerificationResult(
        verified=verified,
        check_type='no_alcohol',
        message='Alcohol avoided today' if verified else 'Alcohol not marked as avoided',
    )


def _check_replacement_count(conn, user_id: int, target_date: str, rule: dict) -> VerificationResult:
    """COUNT replacement_logs rows for the given date."""
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM replacement_logs WHERE user_id = ? AND date(logged_at) = ?",
        (user_id, target_date),
    ).fetchone()
    count = float(row['cnt'] or 0)
    threshold = float(rule.get('value', 1))
    op = rule.get('operator', '>=')
    verified = _apply_operator(count, op, threshold)
    return VerificationResult(
        verified=verified,
        current_value=count,
        target_value=threshold,
        check_type='replacement_count',
        message=f'{int(count)} replacement action(s) (need {op} {int(threshold)})',
    )


def _check_fasting_hours(conn, user_id: int, target_date: str, rule: dict) -> VerificationResult:
    """Check completed fasting duration for the given date."""
    row = conn.execute(
        """SELECT start_at, end_at, target_hours
           FROM fasting_logs
           WHERE user_id = ? AND date(start_at) = ? AND status = 'completed'
           ORDER BY id DESC LIMIT 1""",
        (user_id, target_date),
    ).fetchone()
    if row is None:
        return VerificationResult(
            verified=False,
            check_type='fasting_hours',
            message='No completed fast found for today',
        )

    from datetime import datetime
    try:
        start = datetime.fromisoformat(row['start_at'])
        end = datetime.fromisoformat(row['end_at'])
        hours = (end - start).total_seconds() / 3600.0
    except Exception:
        hours = 0.0

    threshold = float(rule.get('value', row['target_hours'] or 16))
    op = rule.get('operator', '>=')
    verified = _apply_operator(hours, op, threshold)
    return VerificationResult(
        verified=verified,
        current_value=round(hours, 1),
        target_value=threshold,
        check_type='fasting_hours',
        message=f'{hours:.1f}h fasted (need {op} {threshold}h)',
    )


def _check_manual(conn, task_id: int, target_date: str) -> VerificationResult:
    """Check the micro_task_completions table for a manual tick."""
    row = conn.execute(
        "SELECT id FROM micro_task_completions WHERE micro_task_id = ? AND date = ?",
        (task_id, target_date),
    ).fetchone()
    verified = row is not None
    return VerificationResult(
        verified=verified,
        check_type='manual',
        message='Marked complete' if verified else 'Not yet marked complete',
    )


# ---------------------------------------------------------------------------
# Operator helper
# ---------------------------------------------------------------------------

def _apply_operator(value: float, op: str, threshold: float) -> bool:
    """Apply a comparison operator between value and threshold."""
    if op == '>=':
        return value >= threshold
    elif op == '>':
        return value > threshold
    elif op == '<=':
        return value <= threshold
    elif op == '<':
        return value < threshold
    elif op == '==':
        return value == threshold
    else:
        return value >= threshold


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_CHECK_DISPATCH = {
    'food_log_count': _check_food_log_count,
    'walk_count': _check_walk_count,
    'walk_km': _check_walk_km,
    'checkin_done': _check_checkin_done,
    'deep_work_minutes': _check_deep_work_minutes,
    'calories_under_goal': _check_calories_under_goal,
    'no_alcohol': _check_no_alcohol,
    'replacement_count': _check_replacement_count,
    'fasting_hours': _check_fasting_hours,
}


def verify_micro_task(
    task_id: int,
    rule: dict,
    conn,
    user_id: int,
    target_date: str = None,
) -> VerificationResult:
    """Verify a single micro-task against the live database.

    Args:
        task_id:     Primary key of the habit_micro_tasks row.
        rule:        Parsed verification_rule JSON dict.
        conn:        Active SQLite connection.
        user_id:     The user performing the check (for data isolation).
        target_date: ISO date string (defaults to today).

    Returns:
        VerificationResult with verified flag and contextual values.
    """
    if target_date is None:
        target_date = date.today().isoformat()

    rule_type = rule.get('type', 'manual')

    if rule_type == 'manual':
        return _check_manual(conn, task_id, target_date)

    if rule_type == 'auto':
        check = rule.get('check', '')
        handler = _CHECK_DISPATCH.get(check)
        if handler is None:
            # Unknown check — treat as unverified manual
            return VerificationResult(
                verified=False,
                check_type=check,
                message=f'Unknown check type: {check}',
            )
        try:
            return handler(conn, user_id, target_date, rule)
        except Exception as exc:
            return VerificationResult(
                verified=False,
                check_type=check,
                message=f'Verification error: {exc}',
            )

    # Fallback for unknown rule types
    return VerificationResult(
        verified=False,
        check_type=rule_type,
        message=f'Unknown rule type: {rule_type}',
    )


def verify_phase_tasks(
    phase_id: int,
    conn,
    user_id: int,
    target_date: str = None,
) -> list[dict]:
    """Return all micro-tasks for a phase with live verification status.

    Args:
        phase_id:    Primary key of the habit_phases row.
        conn:        Active SQLite connection.
        user_id:     The user performing the check (for data isolation).
        target_date: ISO date string (defaults to today).

    Returns:
        List of dicts with keys: id, name, description, sort_order,
        verification_type, verified, current_value, target_value, message.
    """
    if target_date is None:
        target_date = date.today().isoformat()

    task_rows = conn.execute(
        """SELECT id, name, description, sort_order, verification_rule
           FROM habit_micro_tasks
           WHERE phase_id = ?
           ORDER BY sort_order""",
        (phase_id,),
    ).fetchall()

    results = []
    for task in task_rows:
        task_id = task['id']
        try:
            rule = json.loads(task['verification_rule'] or '{"type": "manual"}')
        except (json.JSONDecodeError, TypeError):
            rule = {'type': 'manual'}

        result = verify_micro_task(task_id, rule, conn, user_id, target_date)

        results.append({
            'id': task_id,
            'name': task['name'],
            'description': task['description'],
            'sort_order': task['sort_order'],
            'verification_type': rule.get('type', 'manual'),
            'verified': result.verified,
            'current_value': result.current_value,
            'target_value': result.target_value,
            'message': result.message,
        })

    return results


def are_all_tasks_complete(
    phase_id: int,
    conn,
    user_id: int,
    target_date: str = None,
) -> bool:
    """Return True if every micro-task in the phase is verified for the date.

    If the phase has no micro-tasks, returns True (nothing to block).
    """
    tasks = verify_phase_tasks(phase_id, conn, user_id, target_date)
    if not tasks:
        return True
    return all(t['verified'] for t in tasks)
