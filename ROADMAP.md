# LifeHack OS — Roadmap

**Created by:** Ludovic Micinthe (dovik)

---

## Current State

LifeHack OS is a fully functional self-hosted personal operating system with 12 independent modules, 145 API endpoints, 56 database tables, 27 AI tools, and support for 6 AI providers.

### Modules

| Module | Status | What it does |
|---|---|---|
| **Habits** | Stable | Habit tracking with progressive phases, micro-tasks, strength meter, miss logging, habit stacks, template library |
| **Food** | Stable | Calorie and macro logging, AI photo analysis, drink tracking, multi-image meals, receipt scanning |
| **Fasting** | Stable | Intermittent fasting with body stage timeline, hydration tips, deletable history |
| **Wellness** | Stable | Water intake (glass counter), sleep tracking, composite wellness score |
| **Deep Work** | Stable | Focus sessions linked to color-coded projects, cumulative hours per project |
| **Challenges** | Stable | Streak-based commitments, heatmap visualization, flexible target days |
| **Finance** | Stable | Firefly III integration, local spending log, budgets, savings goals, subscriptions, income entries, AI insights, anomaly detection, spending digest |
| **Journal** | Stable | Structured daily entries (gratitude, wins, lessons), on-this-day lookback, tags |
| **Books** | Stable | Book library, timed reading sessions, yearly challenge, ratings and reviews |
| **Notes** | Stable | Quick-capture markdown notes, folder organization, full-text search, random discovery |
| **Contacts CRM** | Stable | Personal relationship manager, reach-out frequency reminders, birthdays, gift ideas, interaction history |
| **Discover** | Stable | Bucket list with categories, completion tracking |

### Platform features

- Multi-user with full data isolation and per-user settings
- Invite-based registration with code expiry and use limits
- Per-user API keys with expiry (`key_id:key_secret` Bearer token scheme)
- Per-user AI provider configuration (different providers per task type)
- User profiles with body metrics and Gravatar support
- Per-module JSON data export
- Global search across all modules
- PWA (installable, service worker)
- AI Chat Mode with 27 tool integrations
- Proactive daily AI insights on dashboard
- Application event and error log
- AI token usage and cost tracking

---

## Recently Completed

These features shipped and are currently live:

- **Finance Stage 2** — subscriptions tracker, income entries, AI budget insights, spending digest, anomaly detection
- **Multi-user architecture** — full `user_id` isolation on all tables, per-user settings and integrations
- **Invite-based registration** — admin-controlled invite codes with use limits and expiry
- **Chat Mode** — full-screen AI assistant with tool execution, image upload, and conversation history
- **Wellness module** — water intake, sleep tracking, wellness score
- **Books module** — reading sessions, yearly challenge, ratings
- **Journal module** — structured daily entries, on-this-day, tags
- **Notes module** — markdown notes, folders, full-text search
- **Contacts CRM** — reach-out reminders, birthdays, gift ideas, interaction history
- **Global search** — cross-module search from one input
- **Data export** — per-module JSON download
- **Per-user API keys** — programmatic access with `key_id:key_secret` Bearer tokens
- **Firefly III timezone fix** — fasting start time correctly displays local timezone

---

## Next Up

These are ideas for future development. Nothing is scheduled; contributions are welcome.

### Notification system
Push notifications for habit reminders, upcoming birthdays, reach-out nudges (contacts past their frequency), and subscription renewals. Would require a notification backend (Web Push API) and per-user notification preferences.

### Calendar view
A weekly and monthly calendar that aggregates events across all modules — habit completions, deep work sessions, journal entries, fasting windows, book reading sessions. A single place to see how a day or week was spent.

### Mobile app
A React Native wrapper or significantly improved PWA (better touch targets, bottom nav, offline queue for logging). The API already supports everything needed; the gap is the native experience.

### Advanced analytics
Cross-module insight reports — correlation between sleep quality and habit completion, deep work hours vs. mood, food macros vs. energy levels. Trend charts over 30/90/365-day windows.

### Import from other apps
CSV and JSON import per module for migrating data from MyFitnessPal (food), Goodreads (books), Notion (notes), and similar apps. Each module would define its own import schema.

### Theme customization
Light mode toggle, accent color picker, font size preference. The dark theme is hard-coded today; extracting it to CSS custom properties at the user level would make this straightforward.

---

## Won't Build

Some features are intentionally out of scope.

**Menstrual cycle tracker** — this is a specialized health domain with its own privacy considerations and UX requirements. Dedicated apps (Clue, Flo, Natural Cycles) do this well. LifeHack OS will not try to compete with them.

**Medication tracker** — medication management involves safety-critical reminders and interactions. It belongs in a dedicated medical app, not a general life OS. Referring users to purpose-built tools is the right call.

**Social / sharing features** — LifeHack OS is intentionally a private, self-hosted tool. There are no plans for public profiles, friend feeds, or leaderboards. The value is in personal data ownership, not social comparison.

---

## Contributing a New Module

If you want to add a module, follow this pattern:

1. **Route file** — create `web/routes/your_module.py` as a Flask Blueprint with `url_prefix='/api/your_module'`. Add `@login_required` on every route and call `uid = current_user_id()` at the top of each handler.

2. **Tables** — add `CREATE TABLE IF NOT EXISTS` statements to `src/infrastructure/database/connection.py`. Include `user_id INTEGER REFERENCES users(id)` on every user-data table. Then add a migration entry in `src/infrastructure/database/migrations.py` for any tables added after the initial schema.

3. **Register the blueprint** — import and register it in `web/app.py`.

4. **Add to MODULE_DEFS** — add an entry in `web/routes/modules.py` with a name, description, and `default` value (use `False` for modules that are off by default).

5. **Frontend** — add a JS file to `web/static/js/` and load it from `web/templates/index.html`. Wire up the nav item conditionally on the module being enabled.

6. **Export** — add the module's tables to `_MODULE_TABLES` in `web/routes/export.py`.

7. **AI tools (optional)** — if the module should be controllable from Chat Mode, add tool definitions to `src/domain/services/chat_tools.py` and implement the execution logic in `src/domain/services/chat_tool_executor.py`.

The most important rule: **never query a user-data table without a `WHERE user_id = ?` clause**. This is what keeps one user's data from appearing in another user's account.
