"""Seed built-in habit templates into the database on first startup."""
import json
from .connection import get_connection

# Shorthand helpers for verification rules
_MANUAL = {"type": "manual"}
_FOOD_LOG = {"type": "auto", "check": "food_log_count", "operator": ">=", "value": 2}
_CHECKIN = {"type": "auto", "check": "checkin_done"}
_NO_ALCOHOL = {"type": "auto", "check": "no_alcohol"}
_WALK = {"type": "auto", "check": "walk_count", "operator": ">=", "value": 1}
_CALORIES = {"type": "auto", "check": "calories_under_goal"}
_REPLACEMENT = {"type": "auto", "check": "replacement_count", "operator": ">=", "value": 1}


def _task(name: str, rule: dict = None) -> dict:
    """Build a micro-task dict with a verification rule."""
    return {"name": name, "verification_rule": rule or _MANUAL}


BUILTIN_TEMPLATES = [
    {
        "name": "Morning Exercise Routine",
        "description": "Build a consistent exercise habit from zero to a full morning routine",
        "category": "fitness",
        "difficulty": "beginner",
        "duration_weeks": 9,
        "icon": "💪",
        "is_featured": True,
        "phases": [
            {
                "phase": 1,
                "name": "Just Show Up",
                "description": "Put on gym clothes every morning",
                "days": 14,
                "micro_tasks": [
                    _task("Set clothes out night before"),
                    _task("Put them on within 5 min of waking"),
                ],
            },
            {
                "phase": 2,
                "name": "Light Movement",
                "description": "5 min stretching in gym clothes",
                "days": 14,
                "micro_tasks": [
                    _task("5 basic stretches"),
                    _task("Hold each for 30 seconds"),
                    _task("Log a walk or exercise", _WALK),
                ],
            },
            {
                "phase": 3,
                "name": "Build Intensity",
                "description": "15 min workout",
                "days": 28,
                "micro_tasks": [
                    _task("10 pushups"),
                    _task("10 squats"),
                    _task("1 min plank"),
                    _task("Log exercise session", _WALK),
                ],
            },
            {
                "phase": 4,
                "name": "Full Routine",
                "description": "30+ min exercise session",
                "days": 0,
                "micro_tasks": [
                    _task("Warm up 5 min"),
                    _task("Main workout 20 min"),
                    _task("Cool down 5 min"),
                    _task("Log a walk or exercise", _WALK),
                ],
            },
        ],
    },
    {
        "name": "Daily Reading",
        "description": "Go from not reading at all to reading 30 minutes daily",
        "category": "learning",
        "difficulty": "beginner",
        "duration_weeks": 6,
        "icon": "📚",
        "is_featured": True,
        "phases": [
            {
                "phase": 1,
                "name": "One Page",
                "description": "Read just 1 page before bed",
                "days": 14,
                "micro_tasks": [
                    _task("Put book on pillow"),
                    _task("Read 1 page"),
                    _task("Log mood today", _CHECKIN),
                ],
            },
            {
                "phase": 2,
                "name": "5 Minutes",
                "description": "Read for 5 minutes",
                "days": 14,
                "micro_tasks": [
                    _task("Set 5 min timer"),
                    _task("Read until timer ends"),
                    _task("Log mood today", _CHECKIN),
                ],
            },
            {
                "phase": 3,
                "name": "15 Minutes",
                "description": "Read 15 minutes daily",
                "days": 14,
                "micro_tasks": [
                    _task("Find quiet spot"),
                    _task("Read 15 min"),
                    _task("Note one takeaway"),
                    _task("Log mood today", _CHECKIN),
                ],
            },
            {
                "phase": 4,
                "name": "30 Minutes",
                "description": "Full reading session",
                "days": 0,
                "micro_tasks": [
                    _task("30 min focused reading"),
                    _task("Write 1 sentence summary"),
                    _task("Log mood today", _CHECKIN),
                ],
            },
        ],
    },
    {
        "name": "Sobriety Journey",
        "description": "Build a sober lifestyle with progressive replacement behaviors",
        "category": "sobriety",
        "difficulty": "intermediate",
        "duration_weeks": 12,
        "icon": "🛡️",
        "is_featured": True,
        "phases": [
            {
                "phase": 1,
                "name": "Awareness",
                "description": "Track urges without judgment",
                "days": 14,
                "micro_tasks": [
                    _task("Log every urge"),
                    _task("Rate urge 1-5"),
                    _task("Note what triggered it"),
                    _task("Avoided alcohol today", _NO_ALCOHOL),
                ],
            },
            {
                "phase": 2,
                "name": "Replacement",
                "description": "Replace each urge with an action",
                "days": 21,
                "micro_tasks": [
                    _task("Use a replacement action", _REPLACEMENT),
                    _task("Log a walk or exercise", _WALK),
                    _task("Avoided alcohol today", _NO_ALCOHOL),
                ],
            },
            {
                "phase": 3,
                "name": "Routine Building",
                "description": "Build alcohol-free routines",
                "days": 28,
                "micro_tasks": [
                    _task("Sober social activity weekly"),
                    _task("Evening routine without alcohol"),
                    _task("Avoided alcohol today", _NO_ALCOHOL),
                    _task("Use a replacement action", _REPLACEMENT),
                ],
            },
            {
                "phase": 4,
                "name": "Maintenance",
                "description": "Sustain and protect your sobriety",
                "days": 0,
                "micro_tasks": [
                    _task("Log mood today", _CHECKIN),
                    _task("Avoided alcohol today", _NO_ALCOHOL),
                    _task("Weekly reflection"),
                    _task("Help someone else"),
                ],
            },
        ],
    },
    {
        "name": "Meditation Practice",
        "description": "Build a daily meditation practice from 1 minute to 20 minutes",
        "category": "mindset",
        "difficulty": "beginner",
        "duration_weeks": 8,
        "icon": "🧘",
        "is_featured": True,
        "phases": [
            {
                "phase": 1,
                "name": "Just Sit",
                "description": "Sit quietly for 1 minute",
                "days": 14,
                "micro_tasks": [
                    _task("Find a quiet spot"),
                    _task("Set 1 min timer"),
                    _task("Close eyes and breathe"),
                    _task("Log mood today", _CHECKIN),
                ],
            },
            {
                "phase": 2,
                "name": "5 Minutes",
                "description": "5 minute guided meditation",
                "days": 14,
                "micro_tasks": [
                    _task("Use a meditation app or timer"),
                    _task("Focus on breath"),
                    _task("Note distractions without judgment"),
                    _task("Log mood today", _CHECKIN),
                ],
            },
            {
                "phase": 3,
                "name": "10 Minutes",
                "description": "10 min daily meditation",
                "days": 21,
                "micro_tasks": [
                    _task("Morning meditation before phone"),
                    _task("Body scan technique"),
                    _task("Gratitude reflection"),
                    _task("Log mood today", _CHECKIN),
                ],
            },
            {
                "phase": 4,
                "name": "20 Minutes",
                "description": "Full meditation session",
                "days": 0,
                "micro_tasks": [
                    _task("20 min unguided meditation"),
                    _task("Mindfulness throughout day"),
                    _task("Log mood today", _CHECKIN),
                ],
            },
        ],
    },
    {
        "name": "Healthy Eating",
        "description": "Transform your diet step by step without extreme restrictions",
        "category": "health",
        "difficulty": "beginner",
        "duration_weeks": 8,
        "icon": "🥗",
        "is_featured": True,
        "phases": [
            {
                "phase": 1,
                "name": "Track Everything",
                "description": "Just log what you eat, no changes",
                "days": 14,
                "micro_tasks": [
                    _task("Log every meal", _FOOD_LOG),
                    _task("No judgment, just awareness"),
                    _task("Log mood today", _CHECKIN),
                ],
            },
            {
                "phase": 2,
                "name": "Add Vegetables",
                "description": "Add one serving of vegetables to each meal",
                "days": 14,
                "micro_tasks": [
                    _task("Log every meal", _FOOD_LOG),
                    _task("Vegetables at lunch"),
                    _task("Vegetables at dinner"),
                    _task("Stay under calorie goal", _CALORIES),
                ],
            },
            {
                "phase": 3,
                "name": "Reduce Junk",
                "description": "Replace one junk food per day with a whole food",
                "days": 21,
                "micro_tasks": [
                    _task("Log every meal", _FOOD_LOG),
                    _task("Swap one snack"),
                    _task("Drink water instead of soda"),
                    _task("Stay under calorie goal", _CALORIES),
                ],
            },
            {
                "phase": 4,
                "name": "Clean Eating",
                "description": "80% whole foods diet",
                "days": 0,
                "micro_tasks": [
                    _task("Log every meal", _FOOD_LOG),
                    _task("Stay under calorie goal", _CALORIES),
                    _task("Meal prep weekly"),
                    _task("Read nutrition labels"),
                ],
            },
        ],
    },
    {
        "name": "Consistent Sleep",
        "description": "Fix your sleep schedule and build a bedtime routine",
        "category": "health",
        "difficulty": "beginner",
        "duration_weeks": 6,
        "icon": "😴",
        "is_featured": True,
        "phases": [
            {
                "phase": 1,
                "name": "Track Sleep",
                "description": "Log when you go to bed and wake up",
                "days": 7,
                "micro_tasks": [
                    _task("Note bedtime"),
                    _task("Note wake time"),
                    _task("Log mood today", _CHECKIN),
                ],
            },
            {
                "phase": 2,
                "name": "Set Alarm",
                "description": "Same wake time every day",
                "days": 14,
                "micro_tasks": [
                    _task("Wake at same time daily"),
                    _task("No snooze button"),
                    _task("Log mood today", _CHECKIN),
                ],
            },
            {
                "phase": 3,
                "name": "Wind Down",
                "description": "30 min screen-free time before bed",
                "days": 14,
                "micro_tasks": [
                    _task("Screens off 30 min before bed"),
                    _task("Read or stretch"),
                    _task("Dim lights"),
                    _task("Log mood today", _CHECKIN),
                ],
            },
            {
                "phase": 4,
                "name": "Full Routine",
                "description": "Complete sleep hygiene",
                "days": 0,
                "micro_tasks": [
                    _task("Same bedtime +/-30 min"),
                    _task("Cool dark room"),
                    _task("No caffeine after 2pm"),
                    _task("Log mood today", _CHECKIN),
                ],
            },
        ],
    },
]


def seed_habit_templates() -> None:
    """Seed built-in templates if the table is empty."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM habit_templates").fetchone()[0]
    if count > 0:
        return

    for tpl in BUILTIN_TEMPLATES:
        phases = tpl.pop("phases")
        conn.execute(
            """INSERT INTO habit_templates
               (name, description, category, difficulty, duration_weeks, icon,
                phases_json, created_by, is_featured)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'system', ?)""",
            (
                tpl["name"],
                tpl["description"],
                tpl["category"],
                tpl["difficulty"],
                tpl["duration_weeks"],
                tpl["icon"],
                json.dumps(phases),
                1 if tpl.get("is_featured") else 0,
            ),
        )
        # Restore phases so the list is not mutated for subsequent calls
        tpl["phases"] = phases

    conn.commit()
    print(f"  Seeded {len(BUILTIN_TEMPLATES)} built-in habit templates.")


def reseed_habit_templates() -> None:
    """Re-seed all built-in templates, updating existing rows by name.

    This is useful after verification_rule data has been added to the seed
    definitions. It updates phases_json for existing system templates without
    removing user-created ones.
    """
    conn = get_connection()
    updated = 0
    for tpl in BUILTIN_TEMPLATES:
        phases = tpl.get("phases", [])
        conn.execute(
            """UPDATE habit_templates
               SET phases_json = ?, description = ?, duration_weeks = ?
               WHERE name = ? AND created_by = 'system'""",
            (
                json.dumps(phases),
                tpl["description"],
                tpl["duration_weeks"],
                tpl["name"],
            ),
        )
        if conn.execute("SELECT changes()").fetchone()[0] > 0:
            updated += 1
    conn.commit()
    if updated:
        print(f"  Updated {updated} built-in habit templates with verification rules.")
