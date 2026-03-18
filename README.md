# LifeHack OS

**A personal operating system for discipline, habit tracking, project execution, and life rebuilding.**

Created by **Ludovic Micinthe** (dovik@micinthe.com) | Vibe Coder

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

---

## What Is This?

LifeHack OS is a self-hosted, local-first personal dashboard that helps you build discipline through gamified habit tracking, daily check-ins, movement logging, nutrition tracking, and project management. It treats you like an adult — no childish animations, no subscription fees, no cloud lock-in.

**Who it's for:** Anyone rebuilding their life, building better habits, tracking sobriety, or just wanting a serious personal operating system that runs on your own machine.

### Features

- **Habits** — Daily/weekly tracking with streak multipliers, categories, difficulty levels
- **Daily Check-ins** — Reflection on mood, energy, sobriety, future work
- **Movement** — Walk/exercise logging with mood tracking
- **Food & Nutrition** — Meal logging with calorie and macro tracking
- **Fasting** — Timer-based fasting tracker with history
- **Projects** — Project management with milestones and task breakdown
- **Deep Work** — Focused work session tracking with XP rewards
- **Challenges** — Custom challenge streaks (30-day, 90-day, etc.)
- **Sobriety Module** — Replacement action tracking with urge-level XP bonuses
- **Wishlist** — Places to visit, things to do
- **Analytics** — XP breakdown, point ledger, completion rates, streak stats

### Gamification (Not Childish)

- **XP Points** for all actions — habits, check-ins, walks, deep work, fasting
- **Levels**: Initiate → Apprentice → Practitioner → Adept → Master → Grandmaster → Legend
- **Streak multipliers** — 7+ day streaks earn 1.5x points
- **Sobriety bonuses** — Daily XP for staying on track
- **Point ledger** — Full audit trail of every XP earned
- No fake achievements. Real progress only.

### AI Integration (Optional)

LifeHack OS works **perfectly without AI**. But if you want AI-powered features:

- **Standalone** — Full functionality, no AI needed
- **Ollama** — Free, local LLM. Private, zero cost
- **OpenAI-compatible** — Works with any OpenAI-compatible API
- **OpenClaw/Push API** — External AI agents can push insights via API

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/lifehack-os.git
cd lifehack-os
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your preferred username/password and a random secret key
```

At minimum, set these in `.env`:
```
LIFEHACK_SECRET_KEY=your-random-secret-here
LIFEHACK_USERNAME=your-username
LIFEHACK_PASSWORD=your-password
```

### 3. Run

```bash
cd web
python app.py
```

Open `http://localhost:8420` in your browser. That's it.

---

## Configuration

### Gamification Rules

Edit `config/rules.toml` to customize:
- Point values for habits, check-ins, walks, deep work
- Streak multiplier thresholds
- Level XP requirements
- Penalty amounts (optional)

### Habit Categories

Edit `config/categories.toml` to customize:
- Category names, colors, and icons
- Replacement action definitions and point values

### Optional Integrations

Configure in the Settings page or via `.env`:
- **Vikunja** — External task management
- **Google Calendar** — Event display (requires `gog` CLI)
- **Firefly III** — Personal finance tracking

---

## Architecture

```
lifehack-os/
├── web/                        # Flask web application
│   ├── app.py                  # Application factory
│   ├── routes/                 # API blueprints (12 modules)
│   ├── templates/              # HTML templates
│   └── static/                 # CSS, JS, assets
├── src/
│   ├── domain/entities/        # Pure business logic (dataclasses)
│   ├── infrastructure/
│   │   ├── database/           # SQLite connection & repositories
│   │   ├── config/             # TOML config loader
│   │   └── providers/          # Vikunja, Google Calendar, Firefly
├── config/                     # TOML configuration files
├── data/                       # SQLite database (auto-created)
├── .env.example                # Configuration template
└── requirements.txt            # Python dependencies
```

## Tech Stack

- **Python 3.11+** with Flask
- **SQLite** — Local-first, zero-config database
- **Tailwind CSS** — Responsive web UI
- **Vanilla JavaScript** — No framework dependencies
- **TOML** — Human-readable configuration

## Design Principles

1. **Local-first** — Your data stays on your machine
2. **AI-optional** — Works fully without any AI provider
3. **Configurable** — Rules in TOML, secrets in `.env`
4. **Honest** — No fake achievements, real progress only
5. **Free forever** — MIT licensed, self-hosted, no subscriptions

---

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

## License

[MIT](LICENSE) — Copyright (c) 2026 Ludovic Micinthe

---

Built for serious use. Not a toy.
