# Configuration Reference

LifeHack OS has three configuration layers:

1. **`.env`** — secrets, credentials, server settings, AI provider selection
2. **`config/rules.toml`** — all scoring values, level progression, penalties
3. **`config/categories.toml`** — habit categories and replacement action definitions

None of these files are created for you (except `.env.example`). The application uses built-in defaults if a file is missing or a key is absent.

---

## Table of Contents

1. [.env Variables](#env-variables)
2. [config/rules.toml](#configrulestoml)
3. [config/categories.toml](#configcategoriestoml)

---

## .env Variables

Copy `.env.example` to `.env` and edit the values. The application loads this file automatically on startup from the project root.

```bash
cp .env.example .env
```

### Required Variables

These must be set before the application is useful. The defaults in `.env.example` are insecure placeholders.

| Variable | Default | Description |
|---|---|---|
| `LIFEHACK_SECRET_KEY` | `change-me-to-a-random-string` | Flask session signing key. Generate with: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `LIFEHACK_USERNAME` | `admin` | Login username |
| `LIFEHACK_PASSWORD` | `change-me-to-a-strong-password` | Login password |

### API Key

| Variable | Default | Description |
|---|---|---|
| `LIFEHACK_API_KEY` | `change-me-to-a-random-string` | API key for OpenClaw endpoints and the food `/analyze` endpoint. Required if you use either feature. Leave blank to disable API key authentication (all API key checks will fail). Generate with: `python3 -c "import secrets; print(secrets.token_hex(32))"` |

### AI Provider

| Variable | Default | Description |
|---|---|---|
| `LIFEHACK_AI_PROVIDER` | `none` | Which AI provider to use. Options: `none`, `ollama`, `openai`. `none` disables AI features entirely. |

**Ollama settings** (only relevant when `LIFEHACK_AI_PROVIDER=ollama`):

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | URL of the running Ollama server |
| `OLLAMA_MODEL` | `llama3` | Model name to use for generation. Must match a model installed via `ollama pull`. |

**OpenAI-compatible settings** (only relevant when `LIFEHACK_AI_PROVIDER=openai`):

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | _(empty)_ | API key. Required for the OpenAI provider. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL for any OpenAI-compatible API. Override for Groq, Together AI, Azure, etc. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name. Must be available at the configured endpoint. |

### Integrations

These pre-configure integrations. The integration also needs to be enabled through the Settings UI (or `config/integrations.json`) to be active.

| Variable | Default | Description |
|---|---|---|
| `VIKUNJA_API_URL` | _(empty)_ | Vikunja API base URL, ending in `/api/v1` |
| `VIKUNJA_USERNAME` | _(empty)_ | Vikunja login username |
| `VIKUNJA_PASSWORD` | _(empty)_ | Vikunja login password |
| `GCAL_ACCOUNT` | _(empty)_ | Google account email for Calendar integration via `gog` CLI |
| `FIREFLY_HELPER_PATH` | _(empty)_ | Absolute path to the `firefly.sh` helper script |
| `FIREFLY_ACCOUNT_ID` | _(empty)_ | Default Firefly III account ID for balance/transaction operations |

### Server

| Variable | Default | Description |
|---|---|---|
| `LIFEHACK_HOST` | `0.0.0.0` | Host address to bind to. Use `127.0.0.1` to restrict to localhost only. |
| `LIFEHACK_PORT` | `8420` | Port to listen on. |

### Complete .env.example

```dotenv
# LifeHack OS Configuration
# Copy this file to .env and customize your values
# cp .env.example .env

# === REQUIRED ===
# Flask secret key (generate a random one: python3 -c "import secrets; print(secrets.token_hex(32))")
LIFEHACK_SECRET_KEY=change-me-to-a-random-string

# Login credentials
LIFEHACK_USERNAME=admin
LIFEHACK_PASSWORD=change-me-to-a-strong-password

# API key for AI/OpenClaw integration (generate a random one or leave blank to disable)
LIFEHACK_API_KEY=change-me-to-a-random-string

# === OPTIONAL: AI Provider ===
# Options: none, ollama, openai
# "none" = app works fully without AI (default)
# "ollama" = free local LLM (requires Ollama running locally)
# "openai" = OpenAI-compatible API
LIFEHACK_AI_PROVIDER=none

# Only needed if AI_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# Only needed if AI_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3

# === OPTIONAL: Integrations ===
# Vikunja task management
VIKUNJA_API_URL=
VIKUNJA_USERNAME=
VIKUNJA_PASSWORD=

# Google Calendar (requires 'gog' CLI tool)
GCAL_ACCOUNT=

# Firefly III personal finance
FIREFLY_HELPER_PATH=
FIREFLY_ACCOUNT_ID=

# === SERVER ===
LIFEHACK_HOST=0.0.0.0
LIFEHACK_PORT=8420
```

---

## config/rules.toml

This file controls all point values, level progression, and penalties. Edit it to adjust the economics of your personal operating system. The application re-reads this file on startup — restart the server after changes.

If this file does not exist, all built-in defaults (shown below) are used.

### [scoring]

Controls how habit XP is calculated and when streak bonuses apply.

```toml
[scoring]
base_habit_points = 10
streak_multiplier_threshold = 7
streak_multiplier = 1.5
weekly_consistency_bonus = 50
sobriety_daily_bonus = 25
```

| Key | Default | Description |
|---|---|---|
| `base_habit_points` | `10` | Base XP earned for completing any habit |
| `streak_multiplier_threshold` | `7` | Consecutive days of completion before the streak multiplier activates |
| `streak_multiplier` | `1.5` | Multiplier applied to habit XP when streak exceeds threshold. `1.5` means 15 XP instead of 10. |
| `weekly_consistency_bonus` | `50` | XP bonus awarded when all daily habits are completed for 7 consecutive days (not currently auto-awarded — reserved for future use) |
| `sobriety_daily_bonus` | `25` | XP bonus per day of sobriety (referenced in architecture documentation; applied via check-in sobriety bonus in practice) |

**XP formula for a completed habit:**

```
if streak >= streak_multiplier_threshold:
    xp = base_habit_points × streak_multiplier
else:
    xp = base_habit_points
```

### [levels]

Defines the XP cost per level and the display names for each level tier.

```toml
[levels]
xp_per_level = 500
level_names = [
    "Initiate",
    "Apprentice",
    "Practitioner",
    "Adept",
    "Master",
    "Grandmaster",
    "Legend"
]
```

| Key | Default | Description |
|---|---|---|
| `xp_per_level` | `500` | XP required to advance one level. Level 2 requires 500 total XP, level 3 requires 1000, etc. |
| `level_names` | `["Initiate", ...]` | Display names for levels 1 through 7. The list can be shorter or longer — names beyond the list length display the last name. |

**Level thresholds with default settings:**

| Level | Name | Total XP Required |
|---|---|---|
| 1 | Initiate | 0 |
| 2 | Apprentice | 500 |
| 3 | Practitioner | 1,000 |
| 4 | Adept | 1,500 |
| 5 | Master | 2,000 |
| 6 | Grandmaster | 2,500 |
| 7 | Legend | 3,000 |

### [penalties]

Controls optional XP penalties for missed habits and sobriety breaks.

```toml
[penalties]
missed_habit = -5
broken_sobriety = -100
missed_checkin = -10
enable_penalties = true
```

| Key | Default | Description |
|---|---|---|
| `missed_habit` | `-5` | XP penalty for a missed daily habit (negative value). Referenced in the rules engine; automatic application is a future feature. |
| `broken_sobriety` | `-100` | XP penalty for a broken sobriety streak. Referenced in architecture; not currently auto-applied. |
| `missed_checkin` | `-10` | XP penalty for missing a daily check-in. Not currently auto-applied. |
| `enable_penalties` | `true` | Master switch for penalties. Set to `false` to disable all penalties. |

### [deep_work]

Controls XP earned from focused work sessions.

```toml
[deep_work]
points_per_30min = 15
max_daily_sessions = 4
minimum_session_minutes = 25
```

| Key | Default | Description |
|---|---|---|
| `points_per_30min` | `15` | XP per 30-minute block of deep work (informational reference; actual calculation uses `floor(minutes/10) × 5`) |
| `max_daily_sessions` | `4` | Maximum number of sessions that earn XP per day (not currently enforced — tracked for future use) |
| `minimum_session_minutes` | `25` | Minimum session length in minutes (not currently enforced as a hard limit) |

**Actual XP formula (from code):**

```
xp = floor(duration_minutes / 10) × 5
```

| Duration | XP |
|---|---|
| 25 min | 10 |
| 30 min | 15 |
| 45 min | 20 |
| 60 min | 30 |
| 90 min | 45 |
| 120 min | 60 |

### [walks]

Controls XP earned from movement sessions.

```toml
[walks]
base_points = 20
km_bonus = 5
mood_improvement_bonus = 10
```

| Key | Default | Description |
|---|---|---|
| `base_points` | `20` | Base XP for any logged movement session regardless of distance |
| `km_bonus` | `5` | Additional XP per kilometre logged |
| `mood_improvement_bonus` | `10` | Additional XP when mood_after > mood_before |

**XP formula:**

```
xp = base_points + (distance_km × km_bonus) + (mood_improvement_bonus if mood_after > mood_before else 0)
```

### [replacements]

Controls XP earned from the Redirect (sobriety replacement) module.

```toml
[replacements]
urge_redirect_base = 30
high_urge_bonus = 20
```

| Key | Default | Description |
|---|---|---|
| `urge_redirect_base` | `30` | Base XP for any logged replacement action |
| `high_urge_bonus` | `20` | Additional XP when the urge level is 4 or 5 |

**XP formula:**

```
xp = urge_redirect_base + (high_urge_bonus if urge_level >= 4 else 0)
```

### [checkin]

Controls XP earned from the daily check-in.

```toml
[checkin]
completion_points = 15
sobriety_bonus = 25
future_work_bonus = 10
```

| Key | Default | Description |
|---|---|---|
| `completion_points` | `15` | Base XP for completing the daily check-in |
| `sobriety_bonus` | `25` | Additional XP when `avoided_alcohol = true` in the check-in |
| `future_work_bonus` | `10` | Additional XP when `worked_on_future = true` in the check-in |

Maximum daily check-in XP: `15 + 25 + 10 = 50`

---

## config/categories.toml

This file defines the habit categories and the replacement action options for the Redirect module. Edit it to add, rename, or recolor categories. Restart the server after changes.

### [categories]

Each entry defines a habit category. The key (e.g., `health`, `fitness`) is the value stored in the database. The `name`, `color`, and `icon` are display properties.

```toml
[categories]
health    = { name = "Health",   color = "#10B981", icon = "🏥" }
fitness   = { name = "Fitness",  color = "#F59E0B", icon = "💪" }
work      = { name = "Work",     color = "#3B82F6", icon = "💼" }
finance   = { name = "Finance",  color = "#8B5CF6", icon = "💰" }
family    = { name = "Family",   color = "#EC4899", icon = "👨‍👩‍👧" }
sobriety  = { name = "Sobriety", color = "#14B8A6", icon = "🛡️" }
mindset   = { name = "Mindset",  color = "#6366F1", icon = "🧠" }
house     = { name = "House",    color = "#78716C", icon = "🏠" }
learning  = { name = "Learning", color = "#0EA5E9", icon = "📚" }
creative  = { name = "Creative", color = "#F472B6", icon = "🎨" }
```

**Default categories:**

| Key | Name | Color | Icon |
|---|---|---|---|
| `health` | Health | `#10B981` (green) | 🏥 |
| `fitness` | Fitness | `#F59E0B` (amber) | 💪 |
| `work` | Work | `#3B82F6` (blue) | 💼 |
| `finance` | Finance | `#8B5CF6` (purple) | 💰 |
| `family` | Family | `#EC4899` (pink) | 👨‍👩‍👧 |
| `sobriety` | Sobriety | `#14B8A6` (teal) | 🛡️ |
| `mindset` | Mindset | `#6366F1` (indigo) | 🧠 |
| `house` | House | `#78716C` (stone) | 🏠 |
| `learning` | Learning | `#0EA5E9` (sky) | 📚 |
| `creative` | Creative | `#F472B6` (rose) | 🎨 |

**Adding a custom category:**

```toml
[categories]
# ... existing categories ...
language = { name = "Language", color = "#F97316", icon = "🗣️" }
```

After saving, restart the server. The new category appears in the habit creation dropdown.

**Changing colors:**

Colors are hex codes. Use any valid hex color. The color is applied as a badge background in the habits list.

### [replacement_categories]

Defines the replacement actions available in the Redirect module. These are seeded into the database on first run. Changing this file after first run requires either manually updating the database or resetting the replacement actions table.

```toml
[replacement_categories]
drive         = { name = "Long Drive",          points = 35 }
gym           = { name = "Gym Session",         points = 40 }
walk          = { name = "Long Walk",           points = 30 }
social        = { name = "Sober Social",        points = 25 }
creative      = { name = "Creative Work",       points = 30 }
cooking       = { name = "Cook at Home",        points = 20 }
documentary   = { name = "Documentary Night",   points = 15 }
family        = { name = "Family Time",         points = 25 }
project       = { name = "Project Work",        points = 35 }
beach         = { name = "Beach Trip",          points = 30 }
```

**Default replacement actions:**

| Key | Name | Points |
|---|---|---|
| `drive` | Long Drive | 35 |
| `gym` | Gym Session | 40 |
| `walk` | Long Walk | 30 |
| `social` | Sober Social | 25 |
| `creative` | Creative Work | 30 |
| `cooking` | Cook at Home | 20 |
| `documentary` | Documentary Night | 15 |
| `family` | Family Time | 25 |
| `project` | Project Work | 35 |
| `beach` | Beach Trip | 30 |

The `points` value here is the base action value before the urge-level bonus from `config/rules.toml` is applied. The `urge_redirect_base` and `high_urge_bonus` in `rules.toml` override these per-action values in the current scoring implementation — the per-action `points` field in `categories.toml` is used as the initial seeded value in the database but does not affect runtime XP calculation.

To add a new replacement action after the server has already run (and the defaults are seeded), add it directly to the `replacement_actions` table in the SQLite database, or modify the database seeding code in `web/app.py`.
