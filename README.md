# LifeHack OS

**Your personal life operating system — self-hosted, AI-powered, open source.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](docker-compose.yml)

---

## What is LifeHack OS?

LifeHack OS is a modular personal operating system for your life — habits, food, fasting, finance, journaling, books, contacts, and more, all in one self-hosted web app. Every module is optional and toggleable per user. The AI layer is also optional: the entire system works without any API keys, and you can plug in any of six supported providers when you want AI features. Built to be cloned, owned, and extended.

![Dashboard](docs/screenshot.png)

---

## Features

### Health
- **Habits** — Progressive phases with micro-tasks, strength meter (builds and decays over time), miss logging with blocker notes, habit stacks, template library, scheduled reminders
- **Food** — Calorie and macro tracking, AI food photo analysis (single or multi-image), drink logging, daily goal, receipt scanning
- **Fasting** — Intermittent fasting tracker with body stage timeline (ketosis, autophagy), hydration tips, deletable history
- **Wellness** — Daily water intake (glass counter), sleep tracking, composite wellness score

### Productivity
- **Deep Work** — Focus sessions linked to color-coded projects, cumulative hour tracking per project
- **Challenges** — Streak-based one-off commitments with heatmap visualization and flexible target days
- **Notes** — Quick-capture markdown notes, folder organization, full-text search, random note discovery

### Life
- **Finance** — Firefly III integration (live accounts, transactions, budgets), local spending log, savings goals, subscriptions tracker, income entries, AI budget insights, anomaly detection, spending digest
- **Journal** — Daily entries with structured gratitude, wins, and lessons fields, on-this-day lookback, tag system
- **Books** — Reading log, session tracking, yearly reading challenge, ratings and reviews
- **Contacts CRM** — Personal relationship manager with reach-out frequency reminders, birthday tracking, gift ideas, and interaction history
- **Discover** — Bucket list organized by category (places, skills, experiences, food, creative) with completion tracking

### AI
- **Chat Mode** — Full-screen AI assistant with markdown rendering, image upload, and persistent conversation history
- **27 AI tools** — The assistant can create habits, log food, start a fast, add journal entries, create notes, manage contacts, log transactions, set budgets, and more — all from natural language
- **Proactive daily insights** — AI-generated daily summary surfaced on the dashboard
- **Food photo analysis** — Photograph or describe a meal for instant macro estimates
- **Receipt scanner** — Photograph a receipt to log transactions automatically

### Platform
- **Multi-user** — Full data isolation per user; each user has independent module settings, AI provider settings, and data
- **Invite-based registration** — Admin creates invite codes; new users register with a valid code
- **Per-user API keys** — Generate `key_id:key_secret` pairs for programmatic access to any endpoint
- **Profile** — Display name, body metrics (height, weight, age), Gravatar support
- **Data export** — Download any module's data as JSON at any time
- **PWA** — Installable as a progressive web app
- **Global search** — Search across habits, food logs, notes, journal entries, books, contacts, and more from one input

---

## Quick Start

### Docker (recommended)

```bash
cp .env.example .env        # edit LIFEHACK_USERNAME and LIFEHACK_PASSWORD at minimum
docker compose up --build -d
open http://localhost:8420
```

The database is persisted in the `lifehack_data` named volume. Rebuilding the container does not lose data.

### Manual

```bash
git clone https://github.com/dovik/lifehack-os.git
cd lifehack-os
pip install -r requirements.txt
cp .env.example .env        # edit as needed
python -m web.app
```

The app starts on `http://localhost:8420`.

---

## Configuration

All configuration is done via environment variables (or a `.env` file in the project root).

| Variable | Default | Description |
|---|---|---|
| `LIFEHACK_USERNAME` | `admin` | Admin account username created on first run |
| `LIFEHACK_PASSWORD` | `changeme` | Admin account password — change this |
| `LIFEHACK_SECRET_KEY` | random | Flask session secret key — set a fixed value in production |
| `LIFEHACK_AI_PROVIDER` | `none` | Default AI provider: `openai`, `anthropic`, `ollama`, `minimax`, `chatgpt_oauth`, or `none` |
| `LIFEHACK_HOST` | `0.0.0.0` | Host to bind the Flask server |
| `LIFEHACK_PORT` | `8420` | Port to listen on |

After first run, AI provider settings (API keys, models, per-task overrides) can also be configured per-user from the Settings page in the UI. Those values are stored in the database and take priority over the environment variable.

---

## AI Providers

All providers are optional. The app runs fully without any AI configuration.

| Provider | Setting value | Notes |
|---|---|---|
| OpenAI | `openai` | Requires an OpenAI API key. Supports vision for food photo analysis. |
| Anthropic Claude | `anthropic` | Requires an Anthropic API key. Full tool and vision support. |
| Ollama | `ollama` | Local LLM, no API key needed. Set `OLLAMA_URL` (default: `http://localhost:11434`). See `docker-compose.yml` for the optional sidecar service. |
| MiniMax | `minimax` | Requires a MiniMax API key. Reasoning `<think>` blocks are stripped automatically. |
| ChatGPT OAuth | `chatgpt_oauth` | Uses OpenAI's OAuth flow — no manual API key management. |
| None | `none` | Disables all AI features. All other functionality works normally. |

Each user can override the global provider from their own Settings page, including setting different providers per task (food analysis, insights, reports, chat).

---

## API

LifeHack OS exposes 145 REST API endpoints across all modules. Every endpoint that returns user data requires authentication.

**Authentication** — pass a `Bearer` token in the `Authorization` header:

```bash
curl http://localhost:8420/api/habits \
  -H "Authorization: Bearer <key_id>:<key_secret>"
```

Generate API keys from **Settings > API Keys** in the UI. Keys are scoped to the generating user and cannot access another user's data.

For interactive API documentation, visit `/api/docs` while the app is running.

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for a full technical walkthrough covering the directory structure, database schema and migrations, module system, AI provider factory, multi-user isolation patterns, image processing pipeline, and frontend design.

---

## Contributing

1. Fork the repository and create a feature branch
2. Follow the existing module pattern — Flask blueprint, `user_id` on all DB queries, `@login_required` on every authenticated route
3. Run `ruff check .` before submitting a pull request
4. See [ROADMAP.md](ROADMAP.md) for ideas on what to build next

Bug reports and pull requests are welcome.

---

## License

MIT — see [LICENSE](LICENSE). Created by [Ludovic Micinthe](https://github.com/dovik).
