"""Tool executor for the AI chat system.

Each handler receives:
  args: dict  — parsed from the AI's JSON argument block
  conn        — live SQLite connection (already open, row_factory set)
  user_id     — integer user ID for data isolation

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

def execute_tool(tool_name: str, args: dict, conn, user_id: int) -> dict:
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
        "log_journal": _log_journal,
        "log_book": _log_book,
        "create_note": _create_note,
        "log_water": _log_water,
        "log_sleep": _log_sleep,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return handler(args, conn, user_id)
    except Exception as exc:
        logger.error("Tool '%s' raised an exception: %s", tool_name, exc, exc_info=True)
        return {"error": f"Tool execution failed: {exc}"}


# ---------------------------------------------------------------------------
# Habits
# ---------------------------------------------------------------------------

def _create_habit(args: dict, conn, user_id: int) -> dict:
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
        "INSERT INTO habits (name, category, difficulty, points, user_id) VALUES (?, ?, ?, 10, ?)",
        (name, category, difficulty, user_id),
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


def _generate_and_create_habit(args: dict, conn, user_id: int) -> dict:
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
        "INSERT INTO habits (name, category, frequency, difficulty, points, user_id) VALUES (?, ?, 'daily', ?, 10, ?)",
        (plan.name, plan.category, 1, user_id),
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


def _complete_habit(args: dict, conn, user_id: int) -> dict:
    habit_id = args.get("habit_id")
    if habit_id is None:
        return {"error": "habit_id is required"}

    try:
        habit_id = int(habit_id)
    except (TypeError, ValueError):
        return {"error": "habit_id must be an integer"}

    # Verify the habit exists, is active, and belongs to this user
    row = conn.execute(
        "SELECT id, name FROM habits WHERE id = ? AND user_id = ? AND active = 1",
        (habit_id, user_id),
    ).fetchone()
    if not row:
        return {"error": f"No active habit with id {habit_id}"}

    habit_name = row["name"]

    # Prevent double-completion on the same day
    already = conn.execute(
        "SELECT id FROM habit_completions WHERE habit_id = ? AND user_id = ? AND date(completed_at) = date('now')",
        (habit_id, user_id),
    ).fetchone()
    if already:
        return {
            "success": True,
            "message": f'"{habit_name}" was already completed today',
        }

    # Insert completion
    conn.execute(
        "INSERT INTO habit_completions (habit_id, status, points_earned, user_id) VALUES (?, 'complete', 10, ?)",
        (habit_id, user_id),
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

        StatsRepository(user_id).add_points("habit", 10, f"Completed: {habit_name}", habit_id)
    except Exception as exc:
        logger.warning("Stats points update skipped: %s", exc)

    conn.commit()

    return {
        "success": True,
        "habit_id": habit_id,
        "message": f'"{habit_name}" marked complete for today',
    }


def _delete_habit(args: dict, conn, user_id: int) -> dict:
    habit_id = args.get("habit_id")
    if habit_id is None:
        return {"error": "habit_id is required"}

    try:
        habit_id = int(habit_id)
    except (TypeError, ValueError):
        return {"error": "habit_id must be an integer"}

    row = conn.execute(
        "SELECT name FROM habits WHERE id = ? AND user_id = ?", (habit_id, user_id)
    ).fetchone()
    if not row:
        return {"error": f"No habit found with id {habit_id}"}

    habit_name = row["name"]
    conn.execute("UPDATE habits SET active = 0 WHERE id = ? AND user_id = ?", (habit_id, user_id))
    conn.commit()

    return {
        "success": True,
        "message": f'Habit "{habit_name}" has been deactivated',
    }


# ---------------------------------------------------------------------------
# Food
# ---------------------------------------------------------------------------

def _log_food(args: dict, conn, user_id: int) -> dict:
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
        """INSERT INTO food_logs (meal_type, description, calories, protein_g, carbs_g, fat_g, user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (meal_type, description, _num(calories), _num(protein_g), _num(carbs_g), _num(fat_g), user_id),
    )
    conn.commit()

    cal_text = f" ({int(calories)} kcal)" if calories is not None else ""
    return {
        "success": True,
        "food_id": cursor.lastrowid,
        "message": f'Logged {meal_type}: {description}{cal_text}',
    }


def _set_calorie_goal(args: dict, conn, user_id: int) -> dict:
    goal = args.get("goal")
    if goal is None:
        return {"error": "goal is required"}

    try:
        goal = int(float(goal))
        if goal <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return {"error": "goal must be a positive number"}

    from src.infrastructure.database.user_scope import set_user_setting
    set_user_setting(conn, user_id, 'daily_calorie_goal', str(goal))

    return {
        "success": True,
        "message": f"Daily calorie goal set to {goal} kcal",
    }


# ---------------------------------------------------------------------------
# Fasting
# ---------------------------------------------------------------------------

def _start_fast(args: dict, conn, user_id: int) -> dict:
    try:
        target_hours = int(float(args.get("target_hours", 16)))
    except (TypeError, ValueError):
        target_hours = 16

    try:
        mood = int(args.get("mood", 3))
        mood = max(1, min(5, mood))
    except (TypeError, ValueError):
        mood = 3

    # Cancel any active fast for this user first
    conn.execute(
        "UPDATE fasting_logs SET status = 'cancelled', end_at = ? WHERE user_id = ? AND status = 'active'",
        (datetime.now().isoformat(), user_id),
    )

    cursor = conn.execute(
        "INSERT INTO fasting_logs (start_at, target_hours, mood_start, user_id) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), target_hours, mood, user_id),
    )
    conn.commit()

    return {
        "success": True,
        "fast_id": cursor.lastrowid,
        "message": f"Started a {target_hours}-hour fast",
    }


def _end_fast(args: dict, conn, user_id: int) -> dict:
    active = conn.execute(
        "SELECT id, start_at FROM fasting_logs WHERE user_id = ? AND status = 'active' ORDER BY start_at DESC LIMIT 1",
        (user_id,),
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
           WHERE id = ? AND user_id = ?""",
        (end_at.isoformat(), mood, active["id"], user_id),
    )

    # Award points: 10 pts per hour fasted
    points = int(duration_hours * 10)
    try:
        from src.infrastructure.database.repositories import StatsRepository

        StatsRepository(user_id).add_points(
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

def _log_transaction(args: dict, conn, user_id: int) -> dict:
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
        """INSERT INTO finance_log (date, amount, description, category, type, source, user_id)
           VALUES (?, ?, ?, ?, ?, 'chat', ?)""",
        (tx_date, amount, description, category, tx_type, user_id),
    )
    conn.commit()

    sign = "+" if tx_type == "deposit" else "-"
    return {
        "success": True,
        "transaction_id": cursor.lastrowid,
        "message": f"Logged {tx_type}: {sign}{amount:.2f} — {description}",
    }


def _add_budget_rule(args: dict, conn, user_id: int) -> dict:
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
        "SELECT id FROM finance_rules WHERE user_id = ? AND category = ?", (user_id, category)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE finance_rules SET monthly_limit = ?, active = 1 WHERE user_id = ? AND category = ?",
            (monthly_limit, user_id, category),
        )
        action = "Updated"
    else:
        conn.execute(
            "INSERT INTO finance_rules (category, monthly_limit, user_id) VALUES (?, ?, ?)",
            (category, monthly_limit, user_id),
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

def _create_challenge(args: dict, conn, user_id: int) -> dict:
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
            user_id INTEGER,
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
        """INSERT INTO challenges (name, category, target_days, start_date, check_in_frequency, user_id)
           VALUES (?, ?, ?, ?, 'daily', ?)""",
        (name, category, target_days, start_date, user_id),
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

def _add_discovery(args: dict, conn, user_id: int) -> dict:
    title = (args.get("title") or "").strip()
    if not title:
        return {"error": "title is required"}

    category = (args.get("category") or "place").strip()
    description = (args.get("description") or "").strip()
    location = (args.get("location") or "").strip()

    cursor = conn.execute(
        """INSERT INTO wishlist (title, description, category, location, status, user_id)
           VALUES (?, ?, ?, ?, 'want', ?)""",
        (title, description, category, location, user_id),
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


def _create_dw_project(args: dict, conn, user_id: int) -> dict:
    name = (args.get("name") or "").strip()
    if not name:
        return {"error": "name is required"}
    color = args.get("color", "#4f80ff")
    desc = args.get("description", "")
    cursor = conn.execute(
        "INSERT INTO deep_work_projects (name, description, color, user_id) VALUES (?, ?, ?, ?)",
        (name, desc, color, user_id),
    )
    conn.commit()
    return {"success": True, "project_id": cursor.lastrowid, "message": f'Created project "{name}"'}


def _delete_dw_project(args: dict, conn, user_id: int) -> dict:
    pid = args.get("project_id")
    if not pid:
        return {"error": "project_id is required"}
    conn.execute(
        "UPDATE deep_work_projects SET active = 0 WHERE id = ? AND user_id = ?",
        (int(pid), user_id),
    )
    conn.commit()
    return {"success": True, "message": "Project deleted"}


def _list_dw_projects(args: dict, conn, user_id: int) -> dict:
    rows = conn.execute(
        "SELECT id, name, color, total_minutes FROM deep_work_projects WHERE user_id = ? AND active = 1 ORDER BY name",
        (user_id,),
    ).fetchall()
    projects = []
    for r in rows:
        hours = round(r["total_minutes"] / 60, 1) if r["total_minutes"] else 0
        projects.append({"id": r["id"], "name": r["name"], "hours": hours})
    return {"success": True, "projects": projects, "message": f"{len(projects)} projects"}


# ---------------------------------------------------------------------------
# Deep Work — Sessions
# ---------------------------------------------------------------------------

def _start_deep_work(args: dict, conn, user_id: int) -> dict:
    project_id = args.get("project_id")
    notes = (args.get("notes") or "").strip()

    if project_id is not None:
        try:
            project_id = int(project_id)
        except (TypeError, ValueError):
            project_id = None

    # End any active session for this user first
    conn.execute(
        "UPDATE deep_work_sessions SET ended_at = CURRENT_TIMESTAMP WHERE user_id = ? AND ended_at IS NULL",
        (user_id,),
    )

    cursor = conn.execute(
        "INSERT INTO deep_work_sessions (project_id, notes, user_id) VALUES (?, ?, ?)",
        (project_id, notes, user_id),
    )
    conn.commit()

    notes_text = f': "{notes}"' if notes else ""
    return {
        "success": True,
        "session_id": cursor.lastrowid,
        "message": f"Deep work session started{notes_text}",
    }


def _end_deep_work(args: dict, conn, user_id: int) -> dict:
    active = conn.execute(
        "SELECT id, started_at FROM deep_work_sessions WHERE user_id = ? AND ended_at IS NULL",
        (user_id,),
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
           WHERE id = ? AND user_id = ?""",
        (end_at.isoformat(), duration_minutes, points, active["id"], user_id),
    )

    try:
        from src.infrastructure.database.repositories import StatsRepository

        StatsRepository(user_id).add_points(
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

def _log_mood(args: dict, conn, user_id: int) -> dict:
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

    # Upsert — only one check-in per day per user
    existing = conn.execute(
        "SELECT id FROM daily_checkins WHERE user_id = ? AND date = ?", (user_id, today)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE daily_checkins SET mood = ?, energy = ?, improvement_note = ? WHERE user_id = ? AND date = ?",
            (mood, energy, note, user_id, today),
        )
        action = "Updated"
    else:
        conn.execute(
            """INSERT INTO daily_checkins (date, mood, energy, improvement_note, user_id)
               VALUES (?, ?, ?, ?, ?)""",
            (today, mood, energy, note, user_id),
        )
        action = "Logged"

    conn.commit()

    return {
        "success": True,
        "message": f"{action} mood: {mood}/5, energy: {energy}/5",
    }


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

def _log_journal(args: dict, conn, user_id: int) -> dict:
    entry_date = (args.get("date") or date.today().isoformat()).strip()

    # Validate / normalise date
    try:
        datetime.fromisoformat(entry_date)
    except (ValueError, TypeError):
        entry_date = date.today().isoformat()

    # Coerce integer fields
    def _int_clamp(v, lo=1, hi=5):
        if v is None:
            return None
        try:
            return max(lo, min(hi, int(v)))
        except (TypeError, ValueError):
            return None

    mood = _int_clamp(args.get("mood"))
    energy = _int_clamp(args.get("energy"))
    lessons = (args.get("lessons") or "").strip() or None
    content = (args.get("content") or "").strip() or None

    # JSON array fields — accept list or leave None
    def _json_list(v):
        if v is None:
            return None
        if isinstance(v, list):
            return json.dumps(v)
        return None

    gratitude_json = _json_list(args.get("gratitude"))
    wins_json = _json_list(args.get("wins"))
    tags_json = _json_list(args.get("tags"))

    existing = conn.execute(
        "SELECT id FROM journal_entries WHERE user_id = ? AND date = ?",
        (user_id, entry_date),
    ).fetchone()

    if existing:
        # Build UPDATE — only set fields that are non-None in this call
        updates = []
        params = []
        for col, val in [
            ("mood", mood),
            ("energy", energy),
            ("lessons", lessons),
            ("content", content),
            ("gratitude_json", gratitude_json),
            ("wins_json", wins_json),
            ("tags_json", tags_json),
        ]:
            if val is not None:
                updates.append(f"{col} = ?")
                params.append(val)

        if updates:
            params.extend([user_id, entry_date])
            conn.execute(
                f"UPDATE journal_entries SET {', '.join(updates)} WHERE user_id = ? AND date = ?",
                params,
            )
        action = "updated"
    else:
        conn.execute(
            """INSERT INTO journal_entries
               (date, mood, energy, lessons, content, gratitude_json, wins_json, tags_json, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (entry_date, mood, energy, lessons, content, gratitude_json, wins_json, tags_json, user_id),
        )
        action = "created"

    conn.commit()

    return {"status": "ok", "date": entry_date, "action": action}


# ---------------------------------------------------------------------------
# Books
# ---------------------------------------------------------------------------

def _log_book(args: dict, conn, user_id: int) -> dict:
    title = (args.get("title") or "").strip()
    if not title:
        return {"error": "title is required"}

    author = (args.get("author") or "").strip() or None
    genre = (args.get("genre") or "").strip() or None
    review = (args.get("review") or "").strip() or None
    status = (args.get("status") or "").strip().lower() or None

    valid_statuses = {"to-read", "reading", "finished", "abandoned"}
    if status and status not in valid_statuses:
        status = None

    page_count = args.get("page_count")
    if page_count is not None:
        try:
            page_count = int(page_count)
            if page_count <= 0:
                page_count = None
        except (TypeError, ValueError):
            page_count = None

    rating = args.get("rating")
    if rating is not None:
        try:
            rating = max(1, min(5, int(rating)))
        except (TypeError, ValueError):
            rating = None

    now_iso = datetime.now().isoformat()

    existing = conn.execute(
        "SELECT id, started_at FROM books WHERE user_id = ? AND title = ?",
        (user_id, title),
    ).fetchone()

    if existing:
        book_id = existing["id"]
        updates = []
        params = []

        for col, val in [
            ("author", author),
            ("genre", genre),
            ("page_count", page_count),
            ("status", status),
            ("rating", rating),
            ("review", review),
        ]:
            if val is not None:
                updates.append(f"{col} = ?")
                params.append(val)

        # started_at / finished_at side-effects
        if status == "reading" and existing["started_at"] is None:
            updates.append("started_at = ?")
            params.append(now_iso)
        if status == "finished":
            updates.append("finished_at = ?")
            params.append(now_iso)

        if updates:
            params.extend([user_id, title])
            conn.execute(
                f"UPDATE books SET {', '.join(updates)} WHERE user_id = ? AND title = ?",
                params,
            )
    else:
        started_at = now_iso if status == "reading" else None
        finished_at = now_iso if status == "finished" else None

        cursor = conn.execute(
            """INSERT INTO books
               (title, author, genre, page_count, status, rating, review, started_at, finished_at, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, author, genre, page_count, status, rating, review, started_at, finished_at, user_id),
        )
        book_id = cursor.lastrowid

    conn.commit()

    return {"status": "ok", "book_id": book_id, "title": title}


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

def _create_note(args: dict, conn, user_id: int) -> dict:
    title = (args.get("title") or "").strip()
    if not title:
        return {"error": "title is required"}

    body = (args.get("body") or "").strip() or None
    folder = (args.get("folder") or "").strip() or None

    tags = args.get("tags")
    tags_json = json.dumps(tags) if isinstance(tags, list) else None

    cursor = conn.execute(
        """INSERT INTO notes (title, body, tags_json, folder, user_id)
           VALUES (?, ?, ?, ?, ?)""",
        (title, body, tags_json, folder, user_id),
    )
    conn.commit()

    return {"status": "ok", "note_id": cursor.lastrowid, "title": title}


# ---------------------------------------------------------------------------
# Wellness — Water
# ---------------------------------------------------------------------------

def _log_water(args: dict, conn, user_id: int) -> dict:
    try:
        glasses = int(args.get("glasses", 1))
    except (TypeError, ValueError):
        glasses = 1
    glasses = max(1, glasses)

    conn.execute(
        "INSERT INTO water_logs (user_id, glasses) VALUES (?, ?)",
        (user_id, glasses),
    )
    conn.commit()

    total_row = conn.execute(
        "SELECT COALESCE(SUM(glasses), 0) as total FROM water_logs WHERE user_id = ? AND date(logged_at) = date('now')",
        (user_id,),
    ).fetchone()

    return {
        "status": "ok",
        "glasses": glasses,
        "total_today": total_row["total"],
        "message": f"Logged {glasses} glass(es) of water. Total today: {total_row['total']}",
    }


# ---------------------------------------------------------------------------
# Wellness — Sleep
# ---------------------------------------------------------------------------

def _log_sleep(args: dict, conn, user_id: int) -> dict:
    from datetime import date as _date, datetime as _datetime, timedelta as _timedelta

    sleep_date = (args.get("date") or _date.today().isoformat()).strip()
    bedtime = (args.get("bedtime") or "").strip() or None
    wake_time = (args.get("wake_time") or "").strip() or None

    try:
        quality = int(args.get("quality", 3))
        quality = max(1, min(5, quality))
    except (TypeError, ValueError):
        quality = 3

    # Calculate hours if both times provided
    hours = None
    if bedtime and wake_time:
        try:
            bed = _datetime.strptime(bedtime, "%H:%M")
            wake = _datetime.strptime(wake_time, "%H:%M")
            delta = wake - bed
            if delta.total_seconds() < 0:
                delta += _timedelta(days=1)
            hours = round(delta.total_seconds() / 3600, 2)
        except ValueError:
            pass

    existing = conn.execute(
        "SELECT id FROM sleep_logs WHERE user_id = ? AND date = ?",
        (user_id, sleep_date),
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE sleep_logs
               SET bedtime = ?, wake_time = ?, hours = ?, quality = ?
               WHERE id = ? AND user_id = ?""",
            (bedtime, wake_time, hours, quality, existing["id"], user_id),
        )
        log_id = existing["id"]
    else:
        cursor = conn.execute(
            """INSERT INTO sleep_logs (user_id, date, bedtime, wake_time, hours, quality)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, sleep_date, bedtime, wake_time, hours, quality),
        )
        log_id = cursor.lastrowid

    conn.commit()

    msg_parts = [f"Sleep logged for {sleep_date}"]
    if hours is not None:
        msg_parts.append(f"{hours}h sleep")
    msg_parts.append(f"quality {quality}/5")

    return {
        "status": "ok",
        "log_id": log_id,
        "date": sleep_date,
        "hours": hours,
        "quality": quality,
        "message": ", ".join(msg_parts),
    }

__all__ = ["execute_tool"]
