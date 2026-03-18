# LifeHack OS

**A personal operating system for discipline, habit tracking, project execution, and life rebuilding.**

Created by **Ludovic Micinthe** (dovik@micinthe.com) | Vibe Coder

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/byt3crafter/lifehack-os/actions/workflows/ci.yml/badge.svg)](https://github.com/byt3crafter/lifehack-os/actions)

---

## What Is This?

LifeHack OS is a self-hosted, local-first personal dashboard that helps you build discipline through gamified habit tracking, daily check-ins, movement logging, nutrition tracking, and project management. It treats you like an adult — no childish animations, no subscription fees, no cloud lock-in.

**Who it's for:** Anyone rebuilding their life, building better habits, tracking sobriety, or wanting a serious personal operating system that runs on your own machine.

### Modular Features

Enable only what you need. All modules are toggleable from Settings:

| Module | Description | Default |
|---|---|---|
| **Habits** | Daily/weekly tracking with streaks and multipliers | ON |
| **Check-in** | Daily reflection — mood, energy, sobriety | ON |
| **Analytics** | XP breakdown, point ledger, stats | ON |
| **Projects** | Project management with milestones | OFF |
| **Movement** | Walk & exercise logging with mood tracking | OFF |
| **Food** | Nutrition & meal tracking with AI estimation | OFF |
| **Fasting** | Timer-based fasting tracker | OFF |
| **Deep Work** | Focused work session tracking | OFF |
| **Challenges** | Custom streak challenges (30-day, 90-day, etc.) | OFF |
| **Redirect** | Sobriety replacement actions with urge tracking | OFF |
| **Wishlist** | Places to visit, things to do | OFF |
| **AI Agent** | OpenClaw external AI agent API | OFF |

### Gamification (Not Childish)

- **XP Points** for all actions — habits, check-ins, walks, deep work, fasting
- **Levels**: Initiate → Apprentice → Practitioner → Adept → Master → Grandmaster → Legend
- **Streak multipliers** — 7+ day streaks earn 1.5x points
- **Sobriety bonuses** — Daily XP for staying on track
- **Point ledger** — Full audit trail of every XP earned
- No fake achievements. Real progress only.

### AI Integration (Optional)

LifeHack OS works **perfectly without AI**. When you want AI features:

| Provider | Cost | Setup |
|---|---|---|
| **Standalone** | Free | Default — no AI needed |
| **Ollama** | Free | Local LLM, private, zero cost |
| **OpenAI-compatible** | Paid | Works with OpenAI, Groq, Together, etc. |
| **OpenClaw** | Free | External AI agents push data via API |

### REST API

Full REST API for all features. Discover all endpoints at `GET /api`. Connect external tools, build automations, or integrate with AI agents via the [OpenClaw API](docs/openclaw-api.md).

---

## Quick Start

### Option A: Make (recommended)

```bash
git clone https://github.com/byt3crafter/lifehack-os.git
cd lifehack-os
make setup    # creates venv, installs deps, copies .env
# Edit .env with your username/password
make run      # starts the app at http://localhost:8420
```

### Option B: Docker

```bash
git clone https://github.com/byt3crafter/lifehack-os.git
cd lifehack-os
cp .env.example .env
# Edit .env with your username/password
make docker   # builds and starts at http://localhost:8420
```

### Option C: Manual

```bash
git clone https://github.com/byt3crafter/lifehack-os.git
cd lifehack-os
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your username/password
cd web && python app.py
```

### Demo Data

Want to see the app with sample data?

```bash
cd web && python seed_demo.py
```

---

## Configuration

At minimum, set these in `.env`:

```
LIFEHACK_SECRET_KEY=your-random-secret-here
LIFEHACK_USERNAME=your-username
LIFEHACK_PASSWORD=your-password
```

See [docs/configuration.md](docs/configuration.md) for the complete reference of all environment variables, scoring rules, and category settings.

---

## Documentation

| Doc | Description |
|---|---|
| [Getting Started](docs/getting-started.md) | Installation, first run, .env setup |
| [Modules](docs/modules.md) | Complete guide to all 12 modules |
| [AI Providers](docs/ai-providers.md) | Standalone, Ollama, OpenAI setup |
| [OpenClaw API](docs/openclaw-api.md) | Full API reference with curl examples |
| [Integrations](docs/integrations.md) | Vikunja, Google Calendar, Firefly III |
| [Configuration](docs/configuration.md) | Every .env var, rules.toml, categories.toml |

---

## Architecture

```
lifehack-os/
├── web/                           # Flask web application
│   ├── app.py                     # Application factory
│   ├── routes/                    # API blueprints (14 modules)
│   │   ├── habits.py              # Habit CRUD + completion
│   │   ├── modules.py             # Module toggle system
│   │   ├── ai.py                  # AI provider endpoints
│   │   ├── openclaw.py            # External AI agent API
│   │   └── ...                    # checkins, food, walks, etc.
│   ├── templates/                 # HTML templates
│   ├── static/                    # PWA manifest, service worker
│   └── seed_demo.py               # Demo data seeder
├── src/
│   ├── domain/entities/           # Pure business logic (dataclasses)
│   ├── infrastructure/
│   │   ├── database/              # SQLite connection & repositories
│   │   ├── config/                # TOML config loader
│   │   ├── ai/                    # AI provider abstraction
│   │   │   ├── null.py            # Standalone (no AI)
│   │   │   ├── ollama.py          # Local Ollama LLM
│   │   │   └── openai_provider.py # OpenAI-compatible
│   │   └── providers/             # Vikunja, Google Calendar, Firefly
├── config/                        # TOML configuration files
├── docs/                          # Comprehensive documentation
├── data/                          # SQLite database (auto-created)
├── Dockerfile                     # Container deployment
├── docker-compose.yml             # Docker Compose with optional Ollama
├── Makefile                       # setup, run, lint, docker, clean
├── .env.example                   # Configuration template
└── .github/workflows/ci.yml      # CI: lint + smoke test
```

## Tech Stack

- **Python 3.11+** with Flask
- **SQLite** — Local-first, zero-config database
- **Vanilla JavaScript** — No framework dependencies
- **TOML** — Human-readable configuration
- **Docker** — One-command deployment

## Design Principles

1. **Local-first** — Your data stays on your machine
2. **AI-optional** — Works fully without any AI provider
3. **Modular** — Enable only the features you need
4. **Configurable** — Rules in TOML, secrets in `.env`
5. **Honest** — No fake achievements, real progress only
6. **Free forever** — MIT licensed, self-hosted, no subscriptions

---

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

```bash
make setup    # set up dev environment
make lint     # run linter
make test     # run tests (when they exist)
```

## License

[MIT](LICENSE) — Copyright (c) 2026 Ludovic Micinthe

---

Built for serious use. Not a toy.
