# LifeHack OS — Architecture

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Web framework | Flask 3.x with Flask-CORS |
| Database | SQLite (single file, `data/lifehack.db`) |
| Frontend | Vanilla JavaScript, no framework |
| Styles | Inline CSS, DM Sans font, dark theme |
| Image processing | Pillow (compression, thumbnails, EXIF rotation) |
| Auth | werkzeug PBKDF2 password hashing, session cookies, Bearer API keys |
| Containerization | Docker + Docker Compose |
| Config | python-dotenv, TOML (category/rule configs) |

The web server (`web/`) is the primary application. The `src/` directory in the project root contains a legacy desktop app (customtkinter) that is not part of the web stack and not included in the Docker image.

---

## Directory Structure

```
lifehack-os/
├── web/                        # Flask web application
│   ├── app.py                  # Application factory (create_app)
│   ├── routes/                 # One blueprint file per module
│   │   ├── decorators.py       # @login_required, current_user_id(), @admin_required
│   │   ├── auth.py             # Login, logout, registration, user management
│   │   ├── habits.py           # Habits, phases, strength, templates
│   │   ├── food.py             # Food logs, AI analysis, drinks
│   │   ├── fasting.py          # (via checkins.py) Fasting sessions
│   │   ├── finance.py          # Firefly III, local log, budgets, subscriptions, income
│   │   ├── journal.py          # Journal entries, tags, on-this-day
│   │   ├── books.py            # Book library, reading sessions
│   │   ├── notes.py            # Notes with folders and search
│   │   ├── wellness.py         # Water logs, sleep logs, wellness score
│   │   ├── contacts.py         # Personal CRM, interactions, gift ideas
│   │   ├── discover.py         # Bucket list
│   │   ├── challenges.py       # Streak challenges and heatmap
│   │   ├── deepwork.py         # Deep work sessions and projects
│   │   ├── chat.py             # Universal AI chat, tool execution
│   │   ├── ai.py               # AI insights, food analysis, habit plans
│   │   ├── settings.py         # Per-user and global settings API
│   │   ├── modules.py          # Module enable/disable per user
│   │   ├── export.py           # Per-module JSON data export
│   │   ├── integrations.py     # Firefly III + Vikunja config
│   │   ├── ai_models.py        # Available model listing per provider
│   │   ├── api_docs.py         # Interactive API documentation route
│   │   ├── app_log.py          # Application event/error log
│   │   ├── plugins.py          # Plugin registry
│   │   └── ...
│   ├── templates/              # Jinja2 HTML templates
│   │   ├── index.html          # Main SPA shell (loads all JS modules)
│   │   ├── login.html
│   │   ├── register.html
│   │   └── ...
│   └── static/                 # Static assets
│       ├── js/                 # Per-module JavaScript files
│       ├── manifest.json       # PWA manifest
│       ├── sw.js               # Service worker
│       └── icon.svg / icon-*.png
│
├── src/                        # Shared backend code
│   ├── domain/
│   │   ├── entities/           # Data classes (Habit, Project, etc.)
│   │   └── services/           # Business logic
│   │       ├── chat_tools.py       # TOOL_DEFINITIONS — 27 AI tool specs
│   │       ├── chat_tool_executor.py  # Tool dispatch and execution
│   │       ├── chat_context.py     # Context assembly for AI prompts
│   │       ├── habit_strength.py   # Strength calculation algorithm
│   │       └── ...
│   └── infrastructure/
│       ├── ai/                 # AI provider abstraction
│       │   ├── base.py             # AIProvider ABC + shared types
│       │   ├── factory.py          # get_ai_provider() — provider resolution
│       │   ├── openai_provider.py
│       │   ├── anthropic_provider.py
│       │   ├── ollama.py
│       │   ├── minimax_provider.py
│       │   ├── chatgpt_oauth_provider.py
│       │   └── null.py             # No-op provider when AI is disabled
│       ├── database/
│       │   ├── connection.py       # SQLite connection, init_database(), all CREATE TABLE
│       │   ├── migrations.py       # Versioned schema migrations (24 migrations)
│       │   ├── repositories.py     # Repository classes (Habit, Project, etc.)
│       │   ├── user_scope.py       # get_user_setting(), set_user_setting(), user integration helpers
│       │   └── habit_templates_seed.py
│       ├── services/
│       │   ├── firefly_service.py  # Firefly III API client
│       │   └── image_service.py    # Pillow image processing
│       ├── config/             # Config loading (TOML)
│       └── plugins/            # Plugin registry and built-in plugins
│
├── config/
│   ├── categories.toml         # Finance/food category definitions
│   └── rules.toml              # Scoring and replacement rules
│
├── data/                       # Runtime data (gitignored)
│   ├── lifehack.db             # SQLite database
│   └── uploads/                # User-uploaded images
│
├── tests/                      # pytest test suite
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── main.py                     # Desktop app entry point (not used by Docker)
```

---

## Database

**Engine:** SQLite (`data/lifehack.db`). A single persistent file — straightforward to back up, zero configuration.

**Scale:** 56 tables across all modules.

**User isolation convention:** Every table that stores user-specific data includes a `user_id INTEGER REFERENCES users(id)` column. All `SELECT`, `INSERT`, and `UPDATE` queries must include the `user_id` predicate. Global/system tables exempt from this rule: `users`, `schema_version`, `app_settings`, `habit_templates`, `app_log`, `ai_usage_log`.

**Migration system:** `src/infrastructure/database/migrations.py` contains a list of `(version, description, sql)` tuples. `run_migrations()` runs each migration exactly once, recording applied versions in the `schema_version` table. There are currently 24 migrations. Base schema (tables present from the first run) is created in `connection.py`; all subsequent schema changes go through migrations.

**Connection:** A single module-level `sqlite3.Connection` is reused for the lifetime of the process (`check_same_thread=False`). `PRAGMA foreign_keys = ON` is set at connection time. The `row_factory = sqlite3.Row` setting means rows are accessible by column name.

**Key tables:**

| Table | Purpose |
|---|---|
| `users` | User accounts with bcrypt-hashed passwords, admin flag |
| `user_settings` | Per-user key/value settings (AI provider, API keys, goals) |
| `user_integrations` | Per-user integration configs (Firefly III URL + token, Vikunja) |
| `user_profiles` | Body metrics, display preferences, Gravatar email |
| `user_api_keys` | Bearer API keys — `key_id`, `key_secret_hash`, expiry, last used |
| `invite_codes` | Registration invite codes with use count and expiry |
| `app_settings` | Global admin-controlled settings (fallback for user settings) |
| `habits` + `habit_completions` | Habit definitions and daily completion records |
| `habit_phases` + `habit_micro_tasks` | Progressive phase system per habit |
| `habit_strength` | Decaying strength score per habit (built on completions, eroded by misses) |
| `food_logs` | Meal and drink entries with macros |
| `fasting_logs` | Fasting session start/end times and mood |
| `finance_log` + `finance_rules` | Local spending log and monthly budget limits |
| `savings_goals` + `subscriptions` + `income_entries` | Finance stage 2 tables |
| `chat_messages` | AI chat history |
| `journal_entries` | Daily journal with structured fields and tags |
| `books` + `reading_sessions` | Book library and timed reading sessions |
| `notes` | Markdown notes with folder and tag support |
| `contacts` + `contact_interactions` + `gift_ideas` | Personal CRM |
| `water_logs` + `sleep_logs` | Wellness tracking |
| `ai_insights` | Cached proactive AI insights |
| `ai_usage_log` | Token usage and cost tracking per AI call |
| `app_log` | Application errors and events |

---

## Authentication

**Session-based (browser):** On login, `session['user_id']` and `session['user']` are set. Sessions are permanent (30-day cookie). Passwords are hashed with werkzeug's PBKDF2 implementation. Legacy SHA-256 hashes are transparently migrated to PBKDF2 on next successful login.

**API key-based (programmatic):** Each user can generate named API keys. A key consists of a `key_id` (plain) and a `key_secret` (stored as a werkzeug hash). Clients send `Authorization: Bearer <key_id>:<key_secret>`. The `@login_required` decorator checks this header first; if valid, it sets `g.api_user_id` and skips session auth.

**`current_user_id()`:** A helper in `decorators.py` that returns the authenticated user's database ID. Checks `g.api_user_id` first (API key path), then falls back to `session['user_id']`. Every route that accesses user data calls this function and passes the result to all queries.

**Admin routes:** The `@admin_required` decorator checks `session['is_admin']`. Admin users can manage other users, create invite codes, and view the app log.

**Registration:** New users register with an invite code. Invite codes have a max-use count and optional expiry. The admin creates codes from the user management panel.

---

## Module System

The 12 modules are defined in `web/routes/modules.py` as `MODULE_DEFS`:

```
habits, food, fasting, deepwork, finance, challenges,
discover, journal, books, notes, wellness, contacts
```

Each entry has a `default` boolean (habits and food default to `True`; all others default to `False`).

**Per-user state:** Module enabled/disabled state is stored as a JSON blob in `user_settings` under the key `enabled_modules`. Each user independently controls which modules appear in their nav.

**Data is never deleted** when a module is disabled. Disabling a module hides it from the nav and stops the frontend from rendering it. The underlying data remains intact and is restored if the module is re-enabled.

**Nav visibility:** The frontend reads the module state on load and only renders nav items and dashboard widgets for enabled modules.

---

## AI System

### Provider Factory

`src/infrastructure/ai/factory.py` exports `get_ai_provider(task, user_id)`. Resolution order:

1. `user_settings.ai_provider_{task}` for the requesting user
2. `user_settings.ai_provider_default` for the requesting user
3. `app_settings.ai_provider_{task}` (global per-task)
4. `app_settings.ai_provider_default` (global default)
5. `app_settings.ai_provider` (backwards compat)
6. `LIFEHACK_AI_PROVIDER` environment variable

If no provider resolves, `NullAIProvider` is returned, which returns empty/no-op responses without raising exceptions.

### Provider Interface

All providers implement `AIProvider` from `src/infrastructure/ai/base.py`. Key methods:
- `analyze_food(image_data, prompt)` — returns `FoodAnalysis`
- `generate_insights(context)` — returns list of `Insight`
- `generate_habit_plan(goal)` — returns `HabitPlan`
- `chat(messages, system_prompt, tools)` — returns a text response

### AI Tools (Chat Mode)

The 27 tools are defined in `src/domain/services/chat_tools.py` as `TOOL_DEFINITIONS` — a list of dicts describing each tool's name, description, and parameters. This list is injected into the system prompt at chat time so the model knows what actions it can take.

When the model wants to call a tool, it emits `[TOOL: tool_name] {"param": "value"}` inline in its response. `web/routes/chat.py` parses these with a regex and dispatches to `chat_tool_executor.py`, which executes the corresponding database operation on behalf of the user. Tool results are appended to the response sent back to the frontend.

Tools cover: habits (create, complete, delete, generate phased plan), food (log, set goal), fasting (start, end), finance (log transaction, add budget rule, add subscription, log income), challenges (create), deep work (create project, start/end session), mood (log check-in), journal (log entry), books (log book), wellness (log water, log sleep), notes (create), contacts (add, log interaction), discover (add item).

### Context Assembly

`src/domain/services/chat_context.py` assembles a context block that is prepended to every chat request. It pulls today's habits, recent food logs, active fasts, financial summary, and other module data to give the model situational awareness without requiring the user to re-explain their state each time.

---

## Multi-User Isolation

The isolation model is enforced at the query level, not the ORM level. Every route that reads or writes user data:

1. Calls `uid = current_user_id()` from `decorators.py`
2. Passes `uid` to every SQL query as a `WHERE user_id = ?` predicate or `INSERT` value
3. Never reads rows without the user_id filter

The `user_scope.py` module provides `get_user_setting()` and `set_user_setting()` helpers that automatically apply the user predicate and fall back to global `app_settings` for settings that have not been personalized.

User integrations (Firefly III URL and token, Vikunja URL and token) are stored in `user_integrations` and loaded per-request with `get_user_integration()`. This means each user can point to their own Firefly III instance independently.

---

## API Design

**Blueprints:** Each module is a Flask `Blueprint` registered in `web/app.py`. URL prefixes follow `/api/<module>`. The auth blueprint also serves the HTML pages (`/`, `/login`, `/register`).

**Authentication:** Every API route uses `@login_required`. Routes that modify data or access admin features use `@admin_required` where appropriate.

**Response format:** All API routes return JSON. Successful responses return the data directly (no envelope wrapper). Error responses return `{"error": "message"}` with an appropriate HTTP status code (400 for validation errors, 401 for auth failures, 403 for permission errors, 404 for not found, 500 for server errors).

**Error handling:** Two global Flask error handlers in `app.py` catch unhandled `Exception` and `500` responses, log them to the `app_log` table, and return a safe `{"error": "..."}` JSON response.

**File uploads:** Uploaded files (food photos, profile photos, receipts) are saved to `data/uploads/` and served via the `/uploads/<path>` route. All images pass through `image_service.py` for compression and thumbnail generation before storage.

---

## External Integrations

**Firefly III:** A personal finance manager. LifeHack OS connects as an API client using the user's Firefly III URL and a personal access token (configured per-user in `user_integrations`). `src/infrastructure/services/firefly_service.py` wraps the Firefly III API for accounts, transactions, budgets, and categories. The finance module falls back gracefully to local-only mode when Firefly is not configured.

**Vikunja:** A task management app. Integration config is stored per-user in `user_integrations`. Route handling is in `web/routes/integrations.py`.

**Plugin registry:** `src/infrastructure/plugins/` provides a plugin registry for built-in and third-party extensions. Plugins are registered at app startup with `register_builtin_plugins()`.

---

## Image Processing

All uploaded images go through `src/infrastructure/services/image_service.py` before storage.

Three size variants are created:
- `full` — max 1200×1200 px, compressed to ~80% JPEG quality
- `thumb` — max 400×400 px, used in list views and cards
- `micro` — max 80×80 px, used for profile avatars

EXIF orientation data is read and applied before resizing so photos taken on phones are not rotated incorrectly. If Pillow is not installed, the service logs a warning and returns empty paths (the upload still succeeds, just without processing).

---

## Frontend

The frontend is a single-page application served from `web/templates/index.html`. There is no build step, no bundler, and no JavaScript framework.

**Structure:** `index.html` is a shell that loads per-module JavaScript files from `web/static/js/`. Each JS file owns one module's UI (rendering, API calls, state). The nav sidebar and module toggles are rendered from the `/api/modules` response on page load.

**API communication:** All data fetching uses `fetch()` against the `/api/*` endpoints. The session cookie handles auth automatically in the browser. Responses are JSON.

**Theme:** Dark background, DM Sans variable font, a blue/purple accent palette. Styles are written inline in `index.html` and the module JS files using CSS custom properties for the color tokens.

**PWA:** `web/static/manifest.json` and `web/static/sw.js` enable installation as a progressive web app. Icons at 192px and 512px are included.

**Markdown rendering:** Chat Mode and Notes use a lightweight inline markdown renderer for headings, bold, italic, code blocks, and lists.
