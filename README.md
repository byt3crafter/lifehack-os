# Life Hack OS

A personal operating system for discipline, habit tracking, project execution, and life rebuilding.

## Quick Start

```bash
cd /home/d0v1k/clawd/projects/lifehack-os

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

## Features

### Core
- **Dashboard** — Today view with XP, streaks, habits, projects
- **Habits** — Daily/weekly habits with streak tracking and category filters
- **Projects** — Project management with milestones and completion bonuses
- **Check-in** — Daily reflection (sobriety, mood, energy, future work)
- **Movement** — Walk logging with mood tracking
- **Analytics** — XP breakdown, point sources, activity ledger

### Gamification (Not Childish)
- XP points for all actions
- Level system with meaningful progression
- Streak multipliers (7+ days = 1.5x)
- Sobriety bonuses
- No fake achievements — real progress only

### Alcohol Replacement Module
- Define replacement behaviors (gym, walk, project work, etc.)
- Track urge levels (1-5)
- Bonus XP for redirecting high urges
- Build positive habits while breaking destructive ones

## Configuration

Edit `config/rules.toml` to customize:
- Point values
- Streak multipliers
- Level thresholds
- Penalty amounts

Edit `config/categories.toml` to customize:
- Habit categories and colors
- Replacement action definitions

## Architecture

```
lifehack-os/
├── src/
│   ├── domain/entities/    # Pure business logic
│   ├── infrastructure/     # Database, config
│   └── ui/                 # CustomTkinter views
├── config/                 # TOML configuration
├── data/                   # SQLite database
└── main.py                 # Entry point
```

## Stack
- Python 3.11+
- CustomTkinter (modern UI)
- SQLite (local-first)
- TOML (configuration)

## Design Principles
1. **Execution over aesthetics** — Function first
2. **Local-first** — Your data stays on your machine
3. **Configurable** — Rules in TOML, not hardcoded
4. **Honest** — No fake achievements
5. **Fast** — Sub-second response

---

Built for serious use. Not a toy.
