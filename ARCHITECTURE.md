# Life Hack OS — Architecture

## Overview
A personal operating system for discipline, habit tracking, project execution, and life rebuilding. Built for serious use, not gamification theater.

## Tech Stack
- **Language:** Python 3.11+
- **UI Framework:** CustomTkinter (modern, clean, native feel)
- **Database:** SQLite (local-first, portable)
- **Config:** TOML for rules engine
- **Architecture:** Clean Architecture (Domain → Application → Infrastructure → UI)

## Directory Structure
```
lifehack-os/
├── src/
│   ├── domain/           # Pure business logic, no dependencies
│   │   ├── entities/     # Habit, Project, Task, Milestone, CheckIn, etc.
│   │   ├── value_objects/ # Points, Streak, Level, Duration
│   │   └── services/     # Scoring, Streaks, Rules evaluation
│   │
│   ├── application/      # Use cases, orchestration
│   │   ├── habits/       # Habit CRUD, completion, streaks
│   │   ├── projects/     # Project management, milestones
│   │   ├── checkins/     # Daily check-ins
│   │   ├── walks/        # Movement logging
│   │   ├── replacements/ # Alcohol replacement tracking
│   │   └── analytics/    # Reports, trends
│   │
│   ├── infrastructure/   # External concerns
│   │   ├── database/     # SQLite repository implementations
│   │   ├── config/       # TOML config loader
│   │   └── export/       # CSV/JSON export
│   │
│   └── ui/               # CustomTkinter UI
│       ├── app.py        # Main application window
│       ├── theme.py      # Colors, fonts, styling
│       ├── components/   # Reusable UI components
│       └── views/        # Dashboard, Habits, Projects, etc.
│
├── config/
│   ├── rules.toml        # Scoring rules, penalties, multipliers
│   └── categories.toml   # Habit categories
│
├── data/                 # SQLite database lives here
├── tests/
├── main.py
└── requirements.txt
```

## Data Model

### Core Entities

```
┌─────────────────────────────────────────────────────────────────┐
│                           HABITS                                │
├─────────────────────────────────────────────────────────────────┤
│ id, name, category, frequency (daily/weekly), difficulty,       │
│ points, created_at, active                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      HABIT_COMPLETIONS                          │
├─────────────────────────────────────────────────────────────────┤
│ id, habit_id, completed_at, status (complete/partial/missed),   │
│ points_earned, notes                                            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                          PROJECTS                               │
├─────────────────────────────────────────────────────────────────┤
│ id, name, description, status (active/paused/complete),         │
│ points_start, points_complete, created_at, completed_at         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         MILESTONES                              │
├─────────────────────────────────────────────────────────────────┤
│ id, project_id, name, points, order, completed_at               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                           TASKS                                 │
├─────────────────────────────────────────────────────────────────┤
│ id, milestone_id, name, points, completed_at                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      DEEP_WORK_SESSIONS                         │
├─────────────────────────────────────────────────────────────────┤
│ id, project_id, started_at, ended_at, duration_minutes,         │
│ points_earned, notes                                            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    REPLACEMENT_ACTIONS                          │
├─────────────────────────────────────────────────────────────────┤
│ id, name, points, category (drive/gym/walk/social/creative)     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    REPLACEMENT_LOGS                             │
├─────────────────────────────────────────────────────────────────┤
│ id, action_id, logged_at, urge_level (1-5), points_earned,      │
│ notes                                                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         WALK_LOGS                               │
├─────────────────────────────────────────────────────────────────┤
│ id, logged_at, distance_km, duration_minutes, mood_before,      │
│ mood_after, points_earned, notes                                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       DAILY_CHECKINS                            │
├─────────────────────────────────────────────────────────────────┤
│ id, date, completed_today (text), avoided_alcohol (bool),       │
│ worked_on_future (bool), mood (1-5), energy (1-5),              │
│ improvement_note, points_earned                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                          STREAKS                                │
├─────────────────────────────────────────────────────────────────┤
│ id, type (habit/sobriety/checkin/walk), reference_id,           │
│ current_count, best_count, last_date                            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        USER_STATS                               │
├─────────────────────────────────────────────────────────────────┤
│ id, total_xp, level, sobriety_days, created_at                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       POINT_LEDGER                              │
├─────────────────────────────────────────────────────────────────┤
│ id, timestamp, source_type, source_id, points, reason           │
└─────────────────────────────────────────────────────────────────┘
```

## Rules Engine (rules.toml)

```toml
[scoring]
base_habit_points = 10
streak_multiplier_threshold = 7  # Days before multiplier kicks in
streak_multiplier = 1.5
weekly_consistency_bonus = 50    # All habits hit for 7 days
sobriety_daily_bonus = 25

[levels]
xp_per_level = 500
level_names = ["Initiate", "Apprentice", "Practitioner", "Adept", "Master", "Grandmaster"]

[penalties]
missed_habit = -5
broken_sobriety = -100
missed_checkin = -10

[deep_work]
points_per_30min = 15
max_daily_sessions = 4

[walks]
base_points = 20
km_bonus = 5  # per km
mood_improvement_bonus = 10

[replacements]
urge_redirect_base = 30
high_urge_bonus = 20  # urge level 4-5
```

## UI Layout

```
┌────────────────────────────────────────────────────────────────────────────┐
│  LIFE HACK OS                                           [Settings] [Exit]  │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────┐  ┌─────────────────────────────────────────────────────────┐  │
│  │ NAV     │  │                                                         │  │
│  │         │  │  DASHBOARD / HABITS / PROJECTS / WALKS / ANALYTICS      │  │
│  │ ○ Dash  │  │                                                         │  │
│  │ ○ Habit │  │  Content area changes based on nav selection            │  │
│  │ ○ Proj  │  │                                                         │  │
│  │ ○ Walks │  │                                                         │  │
│  │ ○ Check │  │                                                         │  │
│  │ ○ Stats │  │                                                         │  │
│  │         │  │                                                         │  │
│  └─────────┘  └─────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  XP: 2,450  │  Level 5: Adept  │  🔥 Streak: 12 days  │  Sober: 45d  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────┘
```

## MVP Scope

### Phase 1: Core (This Build)
- [x] Architecture & data model
- [ ] Database setup + migrations
- [ ] Habit CRUD + daily completion
- [ ] Basic streak tracking
- [ ] XP/Level system
- [ ] Dashboard view
- [ ] Daily check-in
- [ ] Rules config loading

### Phase 2: Projects
- [ ] Project CRUD
- [ ] Milestones & tasks
- [ ] Deep work session timer
- [ ] Project progress visualization

### Phase 3: Behavioral
- [ ] Replacement actions module
- [ ] Walk logging
- [ ] Enhanced analytics

### Phase 4: Polish
- [ ] Weekly review
- [ ] Data export
- [ ] Backup/restore
- [ ] Mobile companion (future)

## Design Principles

1. **Execution over aesthetics** — Function first, but clean
2. **Local-first** — Your data stays on your machine
3. **Configurable** — Rules in TOML, not hardcoded
4. **Honest** — No fake achievements, real progress only
5. **Fast** — Sub-second response, no bloat
