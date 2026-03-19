"""Tool executor for the AI chat system.

Each handler receives:
  args: dict  — parsed from the AI's JSON argument block
  conn        — live SQLite connection (already open, row_factory set)

Handlers operate DIRECTLY on the database — no HTTP calls to self.
Every handler returns a dict with at minimum one of:
  {'success': True, 'message': '...'}   on success
  {'error': '...'}                       on failure
"""

import json
import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public dispatch entry-point
# ---------------------------------------------------------------------------

def execute_tool(tool_name: str, args: dict, conn) -> dict:
    """Dispatch tool_name to the appropriate handler and return its result.

    Never raises — all exceptions are caught and returned as error dicts.
    """
    handlers = {
        "create_habit": _create_habit,
        "generate_and_create_habit": _generate_and_create_habit,
        "complete_habit": _complete_habit,
        "delete_habit": _delete_habit,
        "log_food": _log_food,
        "set_calorie_goal": _set_calorie_goal,
        "start_fast": _start_fast,
        "end_fast": _end_fast,
        "log_transaction": _log_transaction,
        "add_budget_rule": _add_budget_rule,
        "create_challenge": _create_challenge,
        "add_discovery": _add_discovery,
        "create_dw_project": _create_dw_project,
        "delete_dw_project": _delete_dw_project,
        "list_dw_projects": _list_dw_projects,
        "start_deep_work": _start_deep_work,
        "end_deep_work": _end_deep_work,
        "log_mood": _log_mood,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return handler(args, conn)
    except Exception as exc:
        logger.error("Tool '%s' raised an exception: %s", tool_name, exc, exc_info=True)
        return {"error": f"Tool execution failed: {exc}"}


# ---------------------------------------------------------------------------
# Habits
# ---------------------------------------------------------------------------

def _create_habit(args: dict, conn) -> dict:
    name = (args.get("name") or "").strip()
    if not name:
        return {"error": "name is required"}

    category = (args.get("category") or "health").strip()

    try:
        difficulty = int(args.get("difficulty", 1))
        difficulty = max(1, min(5, difficulty))
    except (TypeError, ValueError):
        difficulty = 1

    cursor = conn.execute(
        "INSERT INTO habits (name, category, difficulty, points) VALUES (?, ?, ?, 10)",
        (name, category, difficulty),
    )
    habit_id = cursor.lastrowid

    # Initialise strength row so queries never miss
    conn.execute(
        "INSERT OR IGNORE INTO habit_strength (habit_id, strength) VALUES (?, 0)",
        (habit_id,),
    )
    conn.commit()

    return {
        "success": True,
        "habit_id": habit_id,
        "message": f'Created habit "{name}" in category "{category}"',
    }


def _generate_and_create_habit(args: dict, conn) -> dict:
    goal = (args.get("goal") or "").strip()
    if not goal:
        return {"error": "goal is required"}

    try:
        from src.infrastructure.ai.factory import get_ai_provider

        provider = get_ai_provider("habits")
        if not provider.is_available():
            return {"error": "No AI provider configured for habits"}

        plan = provider.generate_habit_plan(goal)
        if not plan:
            return {"error": "AI could not generate a habit plan for that goal"}

    except Exception as exc:
        logger.error("generate_habit_plan failed: %s", exc, exc_info=True)
        return {"error": f"AI habit generation failed: {exc}"}

    # Persist the habit
    cursor = conn.execute(
        "INSERT INTO habits (name, category, frequency, difficulty, points) VALUES (?, ?, 'daily', ?, 10)",
        (plan.name, plan.category, 1),
    )
    habit_id = cursor.lastrowid

    conn.execute(
        "INSERT OR IGNORE INTO habit_strength (habit_id, strength) VALUES (?, 0)",
        (habit_id,),
    )

    # Persist phases and micro-tasks
    for i, phase in enumerate(plan.phases):
        phase_cursor = conn.execute(
            """INSERT INTO habit_phases
               (habit_id, phase_number, name, description, unlock_after_days, is_current)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                habit_id,
                phase.phase,
                phase.name,
                phase.description,
                phase.days or 14,
                1 if i == 0 else 0,
            ),
        )
        phase_id = phase_cursor.lastrowid

        for j, task in enumerate(phase.micro_tasks):
            if isinstance(task, dict):
                task_name = task.get("name", "")
                vr = task.get("verification_rule", {"type": "manual"})
                vr_json = json.dumps(vr) if isinstance(vr, dict) else (vr or '{"type":"manual"}')
            else:
                task_name = str(task)
                vr_json = '{"type":"manual"}'

            if task_name:
                conn.execute(
                    """INSERT INTO habit_micro_tasks
                       (phase_id, name, verification_rule, sort_order)
                       VALUES (?, ?, ?, ?)""",
                    (phase_id, task_name, vr_json, j),
                )

    conn.commit()

    return {
        "success": True,
        "habit_id": habit_id,
        "name": plan.name,
        "phases": len(plan.phases),
        "message": f'Created habit "{plan.name}" with {len(plan.phases)} phase(s)',
    }


def _complete_habit(args: dict, conn) -> dict:
    habit_id = args.get("habit_id")
    if habit_id is None:
        return {"error": "habit_id is required"}

    try:
        habit_id = int(habit_id)
    except (TypeError, ValueError):
        return {"error": "habit_id must be an integer"}

    # Verify the habit exists and is active
    row = conn.execute(
        "SELECT id, name FROM habits WHERE id = ? AND active = 1", (habit_id,)
    ).fetchone()
    if not row:
        return {"error": f"No active habit with id {habit_id}"}

    habit_name = row["name"]

    # Prevent double-completion on the same day
    already = conn.execute(
        "SELECT id FROM habit_completions WHERE habit_id = ? AND date(completed_at) = date('now')",
        (habit_id,),
    ).fetchone()
    if already:
        return {
            "success": True,
            "message": f'"{habit_name}" was already completed today',
        }

    # Insert completion
    conn.execute(
        "INSERT INTO habit_completions (habit_id, status, points_earned) VALUES (?, 'complete', 10)",
        (habit_id,),
    )

    # Update strength meter
    s_row = conn.execute(
        "SELECT strength, peak_strength FROM habit_strength WHERE habit_id = ?",
        (habit_id,),
    ).fetchone()

    if s_row:
        try:
            from src.domain.services.habit_strength import calculate_strength_change

            new_strength = calculate_strength_change(s_row["strength"], True)
            peak = max(s_row["peak_strength"] or 0, new_strength)
            conn.execute(
                """UPDATE habit_strength
                   SET strength = ?, peak_strength = ?,
                       last_completed = ?, total_completions = total_completions + 1
                   WHERE habit_id = ?""",
                (new_strength, peak, datetime.now().isoformat(), habit_id),
            )
        except Exception as exc:
            logger.warning("Strength update skipped: %s", exc)
    else:
        conn.execute(
            """INSERT OR IGNORE INTO habit_strength
               (habit_id, strength, peak_strength, last_completed, total_completions)
               VALUES (?, 10, 10, ?, 1)""",
            (habit_id, datetime.now().isoformat()),
        )

    # Award XP points
    try:
        from src.infrastructure.database.repositories import StatsRepository

        StatsRepository().add_points("habit", 10, f"Completed: {habit_name}", habit_id)
    except Exception as exc:
        logger.warning("Stats points update skipped: %s", exc)

    conn.commit()

    return {
        "success": True,
        "habit_id": habit_id,
        "message": f'"{habit_name}" marked complete for today',
    }


def _delete_habit(args: dict, conn) -> dict:
    habit_id = args.get("habit_id")
    if habit_id is None:
        return {"error": "habit_id is required"}

    try:
        habit_id = int(habit_id)
    except (TypeError, ValueError):
        return {"error": "habit_id must be an integer"}

    row = conn.execute("SELECT name FROM habits WHERE id = ?", (habit_id,)).fetchone()
    if not row:
        return {"error": f"No habit found with id {habit_id}"}

    habit_name = row["name"]
    conn.execute("UPDATE habits SET active = 0 WHERE id = ?", (habit_id,))
    conn.commit()

    return {
        "success": True,
        "message": f'Habit "{habit_name}" has been deactivated',
    }


# ---------------------------------------------------------------------------
# Food
# ---------------------------------------------------------------------------

def _log_food(args: dict, conn) -> dict:
    description = (args.get("description") or "").strip()
    if not description:
        return {"error": "description is required"}

    meal_type = (args.get("meal_type") or "meal").strip()
    calories = args.get("calories")
    protein_g = args.get("protein_g")
    carbs_g = args.get("carbs_g")
    fat_g = args.get("fat_g")

    # Coerce numeric fields safely
    def _num(v):
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    cursor = conn.execute(
        """INSERT INTO food_logs (meal_type, description, calories, protein_g, carbs_g, fat_g)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (meal_type, description, _num(calories), _num(protein_g), _num(carbs_g), _num(fat_g)),
    )
    conn.commit()

    cal_text = f" ({int(calories)} kcal)" if calories is not None else ""
    return {
        "success": True,
        "food_id": cursor.lastrowid,
        "message": f'Logged {meal_type}: {description}{cal_text}',
    }


def _set_calorie_goal(args: dict, conn) -> dict:
    goal = args.get("goal")
    if goal is None:
        return {"error": "goal is required"}

    try:
        goal = int(float(goal))
        if goal <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return {"error": "goal must be a positive number"}

    conn.execute(
        """INSERT INTO app_settings (key, value) VALUES ('daily_calorie_goal', ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
        (str(goal),),
    )
    conn.commit()

    return {
        "success": True,
        "message": f"Daily calorie goal set to {goal} kcal",
    }


# ---------------------------------------------------------------------------
# Fasting
# ---------------------------------------------------------------------------

def _start_fast(args: dict, conn) -> dict:
    try:
        target_hours = int(float(args.get("target_hours", 16)))
    except (TypeError, ValueError):
        target_hours = 16

    try:
        mood = int(args.get("mood", 3))
        mood = max(1, min(5, mood))
    except (TypeError, ValueError):
        mood = 3

    # Cancel any active fast first
    conn.execute(
        "UPDATE fasting_logs SET status = 'cancelled', end_at = ? WHERE status = 'active'",
        (datetime.now().isoformat(),),
    )

    cursor = conn.execute(
        "INSERT INTO fasting_logs (start_at, target_hours, mood_start) VALUES (?, ?, ?)",
        (datetime.now().isoformat(), target_hours, mood),
    )
    conn.commit()

    return {
        "success": True,
        "fast_id": cursor.lastrowid,
        "message": f"Started a {target_hours}-hour fast",
    }


def _end_fast(args: dict, conn) -> dict:
    active = conn.execute(
        "SELECT id, start_at FROM fasting_logs WHERE status = 'active' ORDER BY start_at DESC LIMIT 1"
    ).fetchone()

    if not active:
        return {"error": "No active fast to end"}

    try:
        mood = int(args.get("mood", 3))
        mood = max(1, min(5, mood))
    except (TypeError, ValueError):
        mood = 3

    end_at = datetime.now()
    try:
        start_at = datetime.fromisoformat(active["start_at"])
    except (ValueError, TypeError):
        start_at = end_at

    duration_hours = (end_at - start_at).total_seconds() / 3600

    conn.execute(
        """UPDATE fasting_logs
           SET end_at = ?, status = 'completed', mood_end = ?
           WHERE id = ?""",
        (end_at.isoformat(), mood, active["id"]),
    )

    # Award points: 10 pts per hour fasted
    points = int(duration_hours * 10)
    try:
        from src.infrastructure.database.repositories import StatsRepository

        StatsRepository().add_points(
            "fasting", points, f"Completed {duration_hours:.1f}h fast"
        )
    except Exception as exc:
        logger.warning("Stats points update skipped: %s", exc)

    conn.commit()

    return {
        "success": True,
        "hours": round(duration_hours, 1),
        "points": points,
        "message": f"Fast completed: {round(duration_hours, 1)} hours",
    }


# ---------------------------------------------------------------------------
# Finance
# ---------------------------------------------------------------------------

def _log_transaction(args: dict, conn) -> dict:
    amount = args.get("amount")
    description = (args.get("description") or "").strip()

    if amount is None:
        return {"error": "amount is required"}
    if not description:
        return {"error": "description is required"}

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"error": "amount must be a number"}

    tx_type = (args.get("type") or "withdrawal").strip().lower()
    if tx_type not in ("withdrawal", "deposit", "transfer"):
        tx_type = "withdrawal"

    category = (args.get("category") or "").strip()
    tx_date = date.today().isoformat()

    cursor = conn.execute(
        """INSERT INTO finance_log (date, amount, description, category, type, source)
           VALUES (?, ?, ?, ?, ?, 'chat')""",
        (tx_date, amount, description, category, tx_type),
    )
    conn.commit()

    sign = "+" if tx_type == "deposit" else "-"
    return {
        "success": True,
        "transaction_id": cursor.lastrowid,
        "message": f"Logged {tx_type}: {sign}{amount:.2f} — {description}",
    }


def _add_budget_rule(args: dict, conn) -> dict:
    category = (args.get("category") or "").strip()
    monthly_limit = args.get("monthly_limit")

    if not category:
        return {"error": "category is required"}
    if monthly_limit is None:
        return {"error": "monthly_limit is required"}

    try:
        monthly_limit = float(monthly_limit)
        if monthly_limit <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return {"error": "monthly_limit must be a positive number"}

    existing = conn.execute(
        "SELECT id FROM finance_rules WHERE category = ?", (category,)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE finance_rules SET monthly_limit = ?, active = 1 WHERE category = ?",
            (monthly_limit, category),
        )
        action = "Updated"
    else:
        conn.execute(
            "INSERT INTO finance_rules (category, monthly_limit) VALUES (?, ?)",
            (category, monthly_limit),
        )
        action = "Created"

    conn.commit()

    return {
        "success": True,
        "message": f"{action} budget rule: {category} = {monthly_limit:.2f}/month",
    }


# ---------------------------------------------------------------------------
# Challenges
# ---------------------------------------------------------------------------

def _create_challenge(args: dict, conn) -> dict:
    name = (args.get("name") or "").strip()
    if not name:
        return {"error": "name is required"}

    category = (args.get("category") or "general").strip()
    start_date = (args.get("start_date") or date.today().isoformat()).strip()

    # Validate/normalise start_date
    try:
        datetime.fromisoformat(start_date)
    except (ValueError, TypeError):
        start_date = date.today().isoformat()

    target_days = args.get("target_days")
    if target_days is not None:
        try:
            target_days = int(target_days)
            if target_days <= 0:
                target_days = None
        except (TypeError, ValueError):
            target_days = None

    # Ensure table exists (idempotent)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            target_days INTEGER,
            start_date TEXT NOT NULL,
            end_date TEXT,
            status TEXT DEFAULT 'active',
            check_in_frequency TEXT DEFAULT 'daily',
            last_check_in TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS challenge_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            note TEXT,
            logged_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (challenge_id) REFERENCES challenges(id)
        )"""
    )

    cursor = conn.execute(
        """INSERT INTO challenges (name, category, target_days, start_date, check_in_frequency)
           VALUES (?, ?, ?, ?, 'daily')""",
        (name, category, target_days, start_date),
    )
    challenge_id = cursor.lastrowid

    conn.execute(
        "INSERT INTO challenge_logs (challenge_id, action, note) VALUES (?, 'created', ?)",
        (challenge_id, f"Started: {name}"),
    )
    conn.commit()

    target_text = f" ({target_days} days)" if target_days else " (open-ended)"
    return {
        "success": True,
        "challenge_id": challenge_id,
        "message": f'Challenge "{name}"{target_text} started from {start_date}',
    }


# ---------------------------------------------------------------------------
# Discover / Bucket list
# ---------------------------------------------------------------------------

def _add_discovery(args: dict, conn) -> dict:
    title = (args.get("title") or "").strip()
    if not title:
        return {"error": "title is required"}

    category = (args.get("category") or "place").strip()
    description = (args.get("description") or "").strip()
    location = (args.get("location") or "").strip()

    cursor = conn.execute(
        """INSERT INTO wishlist (title, description, category, location, status)
           VALUES (?, ?, ?, ?, 'want')""",
        (title, description, category, location),
    )
    conn.commit()

    return {
        "success": True,
        "item_id": cursor.lastrowid,
        "message": f'Added to bucket list: "{title}"',
    }


# ---------------------------------------------------------------------------
# Deep Work — Projects
# ---------------------------------------------------------------------------


def _create_dw_project(args: dict, conn) -> dict:
    name = (args.get("name") or "").strip()
    if not name:
        return {"error": "name is required"}
    color = args.get("color", "#4f80ff")
    desc = args.get("description", "")
    cursor = conn.execute(
        "INSERT INTO deep_work_projects (name, description, color) VALUES (?, ?, ?)",
        (name, desc, color),
    )
    conn.commit()
    return {"success": True, "project_id": cursor.lastrowid, "message": f'Created project "{name}"'}


def _delete_dw_project(args: dict, conn) -> dict:
    pid = args.get("project_id")
    if not pid:
        return {"error": "project_id is required"}
    conn.execute("UPDATE deep_work_projects SET active = 0 WHERE id = ?", (int(pid),))
    conn.commit()
    return {"success": True, "message": "Project deleted"}


def _list_dw_projects(args: dict, conn) -> dict:
    rows = conn.execute(
        "SELECT id, name, color, total_minutes FROM deep_work_projects WHERE active = 1 ORDER BY name"
    ).fetchall()
    projects = []
    for r in rows:
        hours = round(r["total_minutes"] / 60, 1) if r["total_minutes"] else 0
        projects.append({"id": r["id"], "name": r["name"], "hours": hours})
    return {"success": True, "projects": projects, "message": f"{len(projects)} projects"}


# ---------------------------------------------------------------------------
# Deep Work — Sessions
# ---------------------------------------------------------------------------

def _start_deep_work(args: dict, conn) -> dict:
    project_id = args.get("project_id")
    notes = (args.get("notes") or "").strip()

    if project_id is not None:
        try:
            project_id = int(project_id)
        except (TypeError, ValueError):
            project_id = None

    # End any active session first
    conn.execute(
        "UPDATE deep_work_sessions SET ended_at = CURRENT_TIMESTAMP WHERE ended_at IS NULL"
    )

    cursor = conn.execute(
        "INSERT INTO deep_work_sessions (project_id, notes) VALUES (?, ?)",
        (project_id, notes),
    )
    conn.commit()

    notes_text = f': "{notes}"' if notes else ""
    return {
        "success": True,
        "session_id": cursor.lastrowid,
        "message": f"Deep work session started{notes_text}",
    }


def _end_deep_work(args: dict, conn) -> dict:
    active = conn.execute(
        "SELECT id, started_at FROM deep_work_sessions WHERE ended_at IS NULL"
    ).fetchone()

    if not active:
        return {"error": "No active deep work session to end"}

    end_at = datetime.now()
    try:
        raw = active["started_at"].replace(" ", "T")
        start_at = datetime.fromisoformat(raw)
    except (ValueError, TypeError, AttributeError):
        start_at = end_at

    duration_minutes = int((end_at - start_at).total_seconds() / 60)
    points = int(duration_minutes / 10) * 5  # 5 pts per 10-minute block

    conn.execute(
        """UPDATE deep_work_sessions
           SET ended_at = ?, duration_minutes = ?, points_earned = ?
           WHERE id = ?""",
        (end_at.isoformat(), duration_minutes, points, active["id"]),
    )

    try:
        from src.infrastructure.database.repositories import StatsRepository

        StatsRepository().add_points(
            "deepwork", points, f"Deep Work: {duration_minutes} mins"
        )
    except Exception as exc:
        logger.warning("Stats points update skipped: %s", exc)

    conn.commit()

    return {
        "success": True,
        "duration_minutes": duration_minutes,
        "points": points,
        "message": f"Deep work session ended: {duration_minutes} minutes ({points} pts)",
    }


# ---------------------------------------------------------------------------
# Mood / Daily check-in
# ---------------------------------------------------------------------------

def _log_mood(args: dict, conn) -> dict:
    mood = args.get("mood")
    energy = args.get("energy")

    if mood is None:
        return {"error": "mood is required"}
    if energy is None:
        return {"error": "energy is required"}

    try:
        mood = int(mood)
        mood = max(1, min(5, mood))
    except (TypeError, ValueError):
        return {"error": "mood must be an integer 1-5"}

    try:
        energy = int(energy)
        energy = max(1, min(5, energy))
    except (TypeError, ValueError):
        return {"error": "energy must be an integer 1-5"}

    note = (args.get("note") or "").strip()
    today = date.today().isoformat()

    # Upsert — only one check-in per day
    existing = conn.execute(
        "SELECT id FROM daily_checkins WHERE date = ?", (today,)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE daily_checkins SET mood = ?, energy = ?, improvement_note = ? WHERE date = ?",
            (mood, energy, note, today),
        )
        action = "Updated"
    else:
        conn.execute(
            """INSERT INTO daily_checkins (date, mood, energy, improvement_note)
               VALUES (?, ?, ?, ?)""",
            (today, mood, energy, note),
        )
        action = "Logged"

    conn.commit()

    return {
        "success": True,
        "message": f"{action} mood: {mood}/5, energy: {energy}/5",
    }


__all__ = ["execute_tool"]
