"""Seed built-in habit templates into the database on first startup."""
import json
from .connection import get_connection

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
                    "Set clothes out night before",
                    "Put them on within 5 min of waking",
                ],
            },
            {
                "phase": 2,
                "name": "Light Movement",
                "description": "5 min stretching in gym clothes",
                "days": 14,
                "micro_tasks": [
                    "5 basic stretches",
                    "Hold each for 30 seconds",
                ],
            },
            {
                "phase": 3,
                "name": "Build Intensity",
                "description": "15 min workout",
                "days": 28,
                "micro_tasks": [
                    "10 pushups",
                    "10 squats",
                    "1 min plank",
                    "5 min cardio",
                ],
            },
            {
                "phase": 4,
                "name": "Full Routine",
                "description": "30+ min exercise session",
                "days": 0,
                "micro_tasks": [
                    "Warm up 5 min",
                    "Main workout 20 min",
                    "Cool down 5 min",
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
                "micro_tasks": ["Put book on pillow", "Read 1 page"],
            },
            {
                "phase": 2,
                "name": "5 Minutes",
                "description": "Read for 5 minutes",
                "days": 14,
                "micro_tasks": ["Set 5 min timer", "Read until timer ends"],
            },
            {
                "phase": 3,
                "name": "15 Minutes",
                "description": "Read 15 minutes daily",
                "days": 14,
                "micro_tasks": [
                    "Find quiet spot",
                    "Read 15 min",
                    "Note one takeaway",
                ],
            },
            {
                "phase": 4,
                "name": "30 Minutes",
                "description": "Full reading session",
                "days": 0,
                "micro_tasks": [
                    "30 min focused reading",
                    "Write 1 sentence summary",
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
                    "Log every urge",
                    "Rate urge 1-5",
                    "Note what triggered it",
                ],
            },
            {
                "phase": 2,
                "name": "Replacement",
                "description": "Replace each urge with an action",
                "days": 21,
                "micro_tasks": [
                    "Walk when urge hits",
                    "Call someone",
                    "Drink water instead",
                ],
            },
            {
                "phase": 3,
                "name": "Routine Building",
                "description": "Build alcohol-free routines",
                "days": 28,
                "micro_tasks": [
                    "Sober social activity weekly",
                    "Evening routine without alcohol",
                    "Celebrate milestones",
                ],
            },
            {
                "phase": 4,
                "name": "Maintenance",
                "description": "Sustain and protect your sobriety",
                "days": 0,
                "micro_tasks": [
                    "Daily check-in",
                    "Weekly reflection",
                    "Help someone else",
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
                    "Find a quiet spot",
                    "Set 1 min timer",
                    "Close eyes and breathe",
                ],
            },
            {
                "phase": 2,
                "name": "5 Minutes",
                "description": "5 minute guided meditation",
                "days": 14,
                "micro_tasks": [
                    "Use a meditation app or timer",
                    "Focus on breath",
                    "Note distractions without judgment",
                ],
            },
            {
                "phase": 3,
                "name": "10 Minutes",
                "description": "10 min daily meditation",
                "days": 21,
                "micro_tasks": [
                    "Morning meditation before phone",
                    "Body scan technique",
                    "Gratitude reflection",
                ],
            },
            {
                "phase": 4,
                "name": "20 Minutes",
                "description": "Full meditation session",
                "days": 0,
                "micro_tasks": [
                    "20 min unguided meditation",
                    "Mindfulness throughout day",
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
                "micro_tasks": ["Log every meal", "No judgment, just awareness"],
            },
            {
                "phase": 2,
                "name": "Add Vegetables",
                "description": "Add one serving of vegetables to each meal",
                "days": 14,
                "micro_tasks": ["Vegetables at lunch", "Vegetables at dinner"],
            },
            {
                "phase": 3,
                "name": "Reduce Junk",
                "description": "Replace one junk food per day with a whole food",
                "days": 21,
                "micro_tasks": [
                    "Swap one snack",
                    "Drink water instead of soda",
                    "Cook one meal at home",
                ],
            },
            {
                "phase": 4,
                "name": "Clean Eating",
                "description": "80% whole foods diet",
                "days": 0,
                "micro_tasks": [
                    "Meal prep weekly",
                    "Read nutrition labels",
                    "Mindful eating",
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
                "micro_tasks": ["Note bedtime", "Note wake time"],
            },
            {
                "phase": 2,
                "name": "Set Alarm",
                "description": "Same wake time every day",
                "days": 14,
                "micro_tasks": ["Wake at same time daily", "No snooze button"],
            },
            {
                "phase": 3,
                "name": "Wind Down",
                "description": "30 min screen-free time before bed",
                "days": 14,
                "micro_tasks": [
                    "Screens off 30 min before bed",
                    "Read or stretch",
                    "Dim lights",
                ],
            },
            {
                "phase": 4,
                "name": "Full Routine",
                "description": "Complete sleep hygiene",
                "days": 0,
                "micro_tasks": [
                    "Same bedtime +/-30 min",
                    "Cool dark room",
                    "No caffeine after 2pm",
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
