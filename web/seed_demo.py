#!/usr/bin/env python3
"""
LifeHack OS — Demo Seed Script
================================
Populates the database with realistic sample data so new users can see the app
working with real content.

Usage (from the web/ directory):
    python seed_demo.py

The script is idempotent: if data already exists it will report that and exit
without creating duplicates.
"""
import sys
import random
from pathlib import Path
from datetime import date, datetime, timedelta

# Make sure the project root is on the path so src.* imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.database import init_database, get_connection


# ─── Helpers ────────────────────────────────────────────────────────────────

def days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def dt_days_ago(n: int, hour: int = 8, minute: int = 0) -> str:
    dt = datetime.now() - timedelta(days=n)
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()


# ─── Guard: don't seed if data already exists ───────────────────────────────

def already_seeded(conn) -> bool:
    count = conn.execute("SELECT COUNT(*) as c FROM habits").fetchone()["c"]
    return count > 0


# ─── 1. Habits ───────────────────────────────────────────────────────────────

HABITS = [
    # (name, category, frequency, difficulty, points)
    ("Morning meditation",          "mindfulness", "daily",  2, 15),
    ("Cold shower",                 "health",      "daily",  3, 20),
    ("Read 20 pages",               "learning",    "daily",  1, 10),
    ("No alcohol",                  "sobriety",    "daily",  3, 25),
    ("Gym workout",                 "fitness",     "daily",  3, 30),
    ("Drink 2L water",              "health",      "daily",  1, 10),
    ("Journal entry",               "mindfulness", "daily",  1, 10),
    ("Deep work block (2 hrs)",     "work",        "daily",  2, 20),
    ("Evening walk",                "fitness",     "daily",  2, 15),
    ("Vitamins & supplements",      "health",      "daily",  1,  5),
]


def seed_habits(conn) -> list:
    """Insert habits and return list of inserted IDs."""
    ids = []
    for name, category, freq, diff, pts in HABITS:
        cur = conn.execute(
            """INSERT INTO habits (name, category, frequency, difficulty, points, active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (name, category, freq, diff, pts)
        )
        ids.append(cur.lastrowid)
    conn.commit()
    print(f"  Created {len(ids)} habits")
    return ids


# ─── 2. Habit completions (14 days) ─────────────────────────────────────────

# Probability each habit is completed on a given day (simulates realistic imperfection)
HABIT_COMPLETION_RATES = [0.9, 0.7, 0.85, 0.95, 0.6, 0.9, 0.75, 0.65, 0.80, 0.95]


def seed_completions(conn, habit_ids: list) -> None:
    total = 0
    for day in range(14):
        for i, habit_id in enumerate(habit_ids):
            rate = HABIT_COMPLETION_RATES[i % len(HABIT_COMPLETION_RATES)]
            if random.random() < rate:
                completed_at = dt_days_ago(day, hour=random.randint(7, 22))
                points = HABITS[i][4]
                conn.execute(
                    """INSERT INTO habit_completions (habit_id, completed_at, status, points_earned)
                       VALUES (?, ?, 'complete', ?)""",
                    (habit_id, completed_at, points)
                )
                total += 1
    conn.commit()
    print(f"  Created {total} habit completions over 14 days")


# ─── 3. Daily check-ins (7 days) ─────────────────────────────────────────────

CHECKIN_ENTRIES = [
    # (days_ago, mood, energy, avoided_alcohol, worked_on_future, completed_today, note)
    (0, 4, 4, True,  True,  "Finished the API refactor, meditated, gym done",     "Keep building momentum"),
    (1, 3, 3, True,  True,  "Good deep work session, meal prepped for the week",   "Sleep earlier tonight"),
    (2, 4, 5, True,  True,  "PB on deadlifts, shipped a feature, cold shower",     "Ride this energy"),
    (3, 2, 2, True,  False, "Tired day, only basics done",                          "Rest was needed"),
    (4, 4, 4, True,  True,  "Long walk, journaled, studied Spanish for 30 mins",   "Good balance today"),
    (5, 3, 3, True,  True,  "Solid work day, 3 deep work blocks",                  "Could read more"),
    (6, 5, 5, True,  True,  "Amazing day — flow state all morning, yoga evening",  "Recreate this routine"),
]


def seed_checkins(conn) -> None:
    for days, mood, energy, no_alc, future, completed, note in CHECKIN_ENTRIES:
        d = days_ago(days)
        pts = 20 + (10 if no_alc else 0) + (5 if future else 0)
        conn.execute(
            """INSERT OR IGNORE INTO daily_checkins
               (date, mood, energy, avoided_alcohol, worked_on_future,
                completed_today, improvement_note, points_earned)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (d, mood, energy, int(no_alc), int(future), completed, note, pts)
        )
    conn.commit()
    print(f"  Created {len(CHECKIN_ENTRIES)} daily check-ins")


# ─── 4. Walk logs (5 entries) ────────────────────────────────────────────────

WALKS = [
    # (days_ago, distance_km, duration_min, mood_before, mood_after, location, type)
    (0, 5.2,  52, 3, 5, "Riverfront Park",    "walk"),
    (2, 3.1,  35, 2, 4, "Neighbourhood loop", "walk"),
    (4, 8.0,  85, 4, 5, "Forest trail",       "hike"),
    (6, 4.5,  45, 3, 4, "City centre",        "walk"),
    (9, 6.3,  60, 3, 5, "Canal path",         "run"),
]


def seed_walks(conn) -> None:
    for day, dist, dur, mb, ma, loc, mtype in WALKS:
        base_pts = 15 + int(dist * 5) + (5 if ma > mb else 0)
        conn.execute(
            """INSERT INTO walk_logs
               (logged_at, distance_km, duration_minutes, mood_before, mood_after,
                points_earned, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (dt_days_ago(day, 18, 0), dist, dur, mb, ma, base_pts,
             f"{mtype.capitalize()} at {loc}")
        )
    conn.commit()
    print(f"  Created {len(WALKS)} walk logs")


# ─── 5. Food logs (3 entries) ────────────────────────────────────────────────

FOOD = [
    # (days_ago, hour, meal_type, description, cal, protein, carbs, fat)
    (0, 8,  "breakfast", "Overnight oats with banana and almond butter", 480, 18, 65, 14),
    (0, 13, "lunch",     "Grilled chicken salad with avocado and feta",  520, 42, 22, 28),
    (1, 19, "dinner",    "Salmon fillet, roasted sweet potato, broccoli", 680, 48, 55, 22),
]


def seed_food(conn) -> None:
    for day, hour, mtype, desc, cal, prot, carbs, fat in FOOD:
        conn.execute(
            """INSERT INTO food_logs
               (logged_at, meal_type, description, calories, protein_g, carbs_g, fat_g)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (dt_days_ago(day, hour, 0), mtype, desc, cal, prot, carbs, fat)
        )
    conn.commit()
    print(f"  Created {len(FOOD)} food log entries")


# ─── 6. Projects (2) with milestones ────────────────────────────────────────

def seed_projects(conn) -> None:
    # Project 1: active
    cur = conn.execute(
        """INSERT INTO projects (name, description, status, points_start, points_complete)
           VALUES (?, ?, 'active', 25, 100)""",
        ("Launch Personal Website", "Portfolio site showcasing projects and writing")
    )
    p1_id = cur.lastrowid

    milestones_p1 = [
        ("Design mockup",        50, True),
        ("Build with HTML/CSS",  50, True),
        ("Add blog section",     50, False),
        ("Deploy to production", 75, False),
    ]
    for i, (name, pts, done) in enumerate(milestones_p1):
        completed_at = dt_days_ago(7 - i) if done else None
        conn.execute(
            "INSERT INTO milestones (project_id, name, points, sort_order, completed_at) VALUES (?, ?, ?, ?, ?)",
            (p1_id, name, pts, i, completed_at)
        )

    # Project 2: active
    cur = conn.execute(
        """INSERT INTO projects (name, description, status, points_start, points_complete)
           VALUES (?, ?, 'active', 25, 100)""",
        ("Learn Spanish B2", "Reach conversational fluency by end of year")
    )
    p2_id = cur.lastrowid

    milestones_p2 = [
        ("Complete A1 Duolingo course",  50, True),
        ("Finish A2 vocabulary deck",    50, True),
        ("Watch 10 Spanish films",       50, False),
        ("B1 grammar workbook done",     50, False),
        ("First conversation with native speaker", 100, False),
    ]
    for i, (name, pts, done) in enumerate(milestones_p2):
        completed_at = dt_days_ago(14 - i * 2) if done else None
        conn.execute(
            "INSERT INTO milestones (project_id, name, points, sort_order, completed_at) VALUES (?, ?, ?, ?, ?)",
            (p2_id, name, pts, i, completed_at)
        )

    conn.commit()
    print("  Created 2 projects with milestones")


# ─── 7. Challenge (21-day streak, active) ────────────────────────────────────

def seed_challenges(conn) -> None:
    start = days_ago(21)
    cur = conn.execute(
        """INSERT INTO challenges
           (name, category, target_days, start_date, status, check_in_frequency,
            last_check_in, notes)
           VALUES (?, ?, ?, ?, 'active', 'daily', ?, ?)""",
        (
            "No alcohol — 90 days",
            "sobriety",
            90,
            start,
            datetime.now().isoformat(),
            "Committed to 90 days. No exceptions."
        )
    )
    c_id = cur.lastrowid

    # Log creation + a few check-ins
    conn.execute(
        "INSERT INTO challenge_logs (challenge_id, action, note) VALUES (?, 'created', ?)",
        (c_id, "Challenge started. This time for real.")
    )
    for day in [14, 7, 3, 1, 0]:
        conn.execute(
            "INSERT INTO challenge_logs (challenge_id, action, note, logged_at) VALUES (?, 'checkin', ?, ?)",
            (c_id, "Still going strong.", dt_days_ago(day, 20, 0))
        )
    conn.commit()
    print("  Created 1 active challenge (21-day streak)")


# ─── 8. XP and point ledger ──────────────────────────────────────────────────

LEDGER_ENTRIES = [
    # (days_ago, source_type, points, reason)
    (0,  "habit",       15,  "Completed: Morning meditation"),
    (0,  "habit",       20,  "Completed: Cold shower"),
    (0,  "walk",        40,  "Movement: Riverfront Park"),
    (1,  "checkin",     35,  "Daily check-in"),
    (1,  "habit",       30,  "Completed: Gym workout"),
    (2,  "habit",       15,  "Completed: Read 20 pages"),
    (2,  "walk",        30,  "Movement: Neighbourhood loop"),
    (3,  "checkin",     35,  "Daily check-in"),
    (4,  "milestone",   50,  "Milestone completed: Design mockup"),
    (5,  "habit",       25,  "Completed: No alcohol"),
    (6,  "checkin",     35,  "Daily check-in"),
    (7,  "project",     25,  "Started: Launch Personal Website"),
    (8,  "milestone",   50,  "Milestone completed: Complete A1 Duolingo course"),
    (10, "habit",       30,  "Completed: Gym workout"),
    (12, "walk",        55,  "Movement: Forest trail"),
]


def seed_ledger(conn) -> None:
    total_xp = 0
    for day, source, pts, reason in LEDGER_ENTRIES:
        conn.execute(
            "INSERT INTO point_ledger (timestamp, source_type, points, reason) VALUES (?, ?, ?, ?)",
            (dt_days_ago(day, 12, 0), source, pts, reason)
        )
        total_xp += pts

    # Update user_stats
    conn.execute(
        "UPDATE user_stats SET total_xp = total_xp + ?, level = MAX(1, MIN(10, (total_xp + ?) / 100)) WHERE id = 1",
        (total_xp, total_xp)
    )
    conn.commit()
    print(f"  Created {len(LEDGER_ENTRIES)} point ledger entries (+{total_xp} XP)")


# ─── 9. AI Insights ──────────────────────────────────────────────────────────

INSIGHTS = [
    (
        "streak_risk",
        "Keep Your Streak Alive",
        "Your morning meditation streak is 14 days — your longest ever. "
        "You tend to skip it on days after late nights. Consider a 5-minute fallback "
        "for busy mornings to protect the streak.",
        2,
    ),
    (
        "pattern",
        "Energy Peaks Mid-Morning",
        "Your check-ins show consistently higher energy (4-5) between 9-11am. "
        "Schedule your deepest work and most demanding habits during this window "
        "to leverage your natural rhythm.",
        1,
    ),
]


def seed_insights(conn) -> None:
    for itype, title, content, priority in INSIGHTS:
        conn.execute(
            """INSERT INTO ai_insights (insight_type, title, content, priority, dismissed)
               VALUES (?, ?, ?, ?, 0)""",
            (itype, title, content, priority)
        )
    conn.commit()
    print(f"  Created {len(INSIGHTS)} AI insights")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("LifeHack OS — Demo Seed")
    print("=" * 40)

    init_database()
    conn = get_connection()

    if already_seeded(conn):
        print("Database already has habits — skipping seed to avoid duplicates.")
        print("To re-seed, clear the database first (rm data/lifehack.db).")
        return

    print("Seeding demo data...")
    habit_ids = seed_habits(conn)
    seed_completions(conn, habit_ids)
    seed_checkins(conn)
    seed_walks(conn)
    seed_food(conn)
    seed_projects(conn)
    seed_challenges(conn)
    seed_ledger(conn)
    seed_insights(conn)

    print("=" * 40)
    print("Done! The app is ready to demo.")
    print("Start the server with: python app.py")


if __name__ == "__main__":
    main()
