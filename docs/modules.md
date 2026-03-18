# Modules

LifeHack OS is built around a module system. Each feature is an independent module that you can enable or disable from the Settings page. This keeps the interface clean — you only see what you actually use.

---

## Table of Contents

1. [Module System Overview](#module-system-overview)
2. [Habits](#habits)
3. [Check-in](#check-in)
4. [Analytics](#analytics)
5. [Projects](#projects)
6. [Movement](#movement)
7. [Food](#food)
8. [Fasting](#fasting)
9. [Deep Work](#deepwork)
10. [Challenges](#challenges)
11. [Redirect](#redirect)
12. [Wishlist](#wishlist)
13. [AI Agent (OpenClaw)](#ai-agent-openclaw)

---

## Module System Overview

### Default States

| Module | ID | Default |
|---|---|---|
| Habits | `habits` | Enabled |
| Check-in | `checkin` | Enabled |
| Analytics | `analytics` | Enabled |
| Projects | `projects` | Disabled |
| Movement | `walks` | Disabled |
| Food | `food` | Disabled |
| Fasting | `fasting` | Disabled |
| Deep Work | `deepwork` | Disabled |
| Challenges | `challenges` | Disabled |
| Redirect | `replace` | Disabled |
| Wishlist | `wishlist` | Disabled |
| AI Agent (OpenClaw) | `openclaw` | Disabled |

### Enabling and Disabling Modules

1. Click **Settings** in the left navigation
2. Toggle any module on or off
3. Changes take effect immediately — the navigation updates without a page reload

Module state is stored in the database (the `app_settings` table), not in a file. Disabling a module hides it from the navigation and UI, but does not delete its data.

---

## Habits

**What it does:** The core of LifeHack OS. Track daily and weekly habits with streak counting and XP rewards. Habits are the main source of daily XP and the primary driver of consistency.

### How to Enable

Habits are enabled by default.

### Creating a Habit

1. Go to **Habits**
2. Click **Add Habit**
3. Fill in:
   - **Name** — what you want to track (e.g., "Morning workout", "Read 30 minutes")
   - **Category** — assigns a color and icon (see [categories](configuration.md#categoriesToml))
   - **Frequency** — `daily` or `weekly`
   - **Difficulty** — 1 to 5 (affects XP earned)

### Completing Habits

Click the checkbox next to a habit to mark it complete. The XP is added immediately. You can also:

- **Undo** a completion by clicking the checkbox again (removes the completion and subtracts the XP)
- **Skip** a habit (marks it skipped without affecting the streak)

### Streak Multiplier

After 7 consecutive days of completing a habit, all XP from that habit is multiplied by **1.5x**. The threshold and multiplier are configurable in `config/rules.toml`.

### XP Calculation

```
Base XP = base_habit_points (default: 10)
With streak ≥ 7 days: Base XP × streak_multiplier (default: 1.5)
```

### Tips

- Start with three to five habits. Adding too many at once leads to failure.
- Use categories to group habits visually — fitness habits in amber, health in green, etc.
- The weekly frequency is useful for things like "deep clean the house" or "review finances" that you genuinely can't or shouldn't do every day.
- Soft-deleting a habit (using the delete button) sets it to inactive but preserves all historical data and XP.

---

## Check-in

**What it does:** A daily reflection prompt. You record what you accomplished, your mood (1-5), energy level (1-5), whether you avoided alcohol, whether you worked on your future, and one improvement note. Completing the check-in awards XP.

### How to Enable

Check-in is enabled by default.

### Completing a Check-in

1. Go to **Check-in**
2. Fill in the form:
   - **What did you complete today?** — free text, describe what you did
   - **Avoided alcohol?** — yes/no toggle
   - **Worked on future?** — yes/no toggle (did you do something that builds your future?)
   - **Mood** — 1 (very bad) to 5 (excellent)
   - **Energy** — 1 (exhausted) to 5 (highly energized)
   - **One thing to improve** — free text
3. Submit — XP is awarded

Only one check-in per day is counted for XP. If you submit again the same day, the entry is updated but no additional XP is awarded.

### XP Calculation

| Action | Points |
|---|---|
| Completing the check-in | 15 |
| Avoided alcohol bonus | +25 |
| Worked on future bonus | +10 |
| **Maximum per day** | **50** |

These values are configurable in `config/rules.toml` under `[checkin]`.

### Sobriety Streak

The check-in module tracks a sobriety streak based on the "avoided alcohol" field. This streak is displayed in the dashboard header and reported in the OpenClaw status endpoint.

### Tips

- Make the check-in the last thing you do each day, as a proper close-of-day ritual.
- The "worked on future" toggle is intentionally binary — it forces a yes/no answer about whether you did something that matters long-term.
- The mood and energy fields build historical data. Over time, the Analytics module shows patterns.

---

## Analytics

**What it does:** Shows your XP breakdown, point ledger, habit completion rates, streak stats, and weekly summary. This is your read-only view of progress over time.

### How to Enable

Analytics is enabled by default.

### What is Shown

- **XP total and level** — current level name and XP to next level
- **Point ledger** — a full audit trail of every XP transaction with source type, reason, and timestamp
- **Weekly report** — habits completed, check-ins done, points earned, walks logged, sobriety days
- **Streak leaderboard** — all habits with active streaks, sorted by streak length
- **Points history** — XP earned per day, broken down by category (habit, checkin, walk, etc.)

### Level Progression

| Level | Name | XP Required |
|---|---|---|
| 1 | Initiate | 0 |
| 2 | Apprentice | 500 |
| 3 | Practitioner | 1,000 |
| 4 | Adept | 1,500 |
| 5 | Master | 2,000 |
| 6 | Grandmaster | 2,500 |
| 7 | Legend | 3,000 |

XP per level and level names are configurable in `config/rules.toml` under `[levels]`.

### Tips

- Use the points history to identify your most productive days and what drove them.
- The point ledger is useful for verifying that XP was awarded correctly after completing actions.

---

## Projects

**What it does:** Project management with milestone and task tracking. Supports both a built-in native provider and an external Vikunja instance. Completing tasks and milestones awards XP.

### How to Enable

Go to **Settings** and enable the **Projects** module.

### Native vs. Vikunja

By default, Projects uses the native SQLite-backed provider. If you have Vikunja configured (see [integrations.md](integrations.md)), the project list pulls from Vikunja instead.

### Creating a Project

1. Go to **Projects**
2. Click **New Project**
3. Enter a name and optional description
4. Starting a project awards 25 XP immediately

### Tasks

Tasks are managed through the configured provider. With the native provider:

- Tasks belong to a project
- Completing a task awards 10 XP
- Completing a milestone awards 50 XP

With Vikunja, tasks are synced from your Vikunja lists.

### Tips

- Use Projects for goals that have a defined endpoint (build a website, learn a skill, move apartments). For ongoing behaviors, use Habits.
- The Deep Work module integrates with Projects — you can associate a deep work session with a specific project.

---

## Movement

**What it does:** Logs walks and exercise sessions with distance, duration, mood before/after, location, and movement type. Calculates XP based on distance and mood improvement.

### How to Enable

Go to **Settings** and enable the **Movement** module.

### Logging a Session

1. Go to **Movement**
2. Click **Log Session**
3. Fill in:
   - **Distance (km)** — how far you went
   - **Duration (minutes)** — how long it took
   - **Mood before** — 1 to 5
   - **Mood after** — 1 to 5
   - **Location** — optional label (e.g., "Seaside road")
   - **Movement type** — defaults to `exercise`
   - **Notes** — anything else worth recording
4. Submit — XP is calculated and awarded

### XP Calculation

```
XP = base_points + (distance_km × km_bonus) + mood_improvement_bonus
```

With default settings:
- Base: 20 XP
- Per km: +5 XP
- Mood improved (after > before): +10 XP

A 5 km walk where your mood improved earns: `20 + (5 × 5) + 10 = 55 XP`

These values are configurable in `config/rules.toml` under `[walks]`.

### Weekly Stats

The module shows a weekly summary of total sessions, total distance, and total XP earned from movement.

### Tips

- Even a 10-minute walk counts. Log it. Consistency beats intensity.
- The mood before/after fields generate interesting data over time — many users find that their mood after is almost always higher than before.

---

## Food

**What it does:** Meal logging with calories and macronutrient tracking (protein, carbs, fat). Supports manual entry and optional AI-assisted nutrition estimation.

### How to Enable

Go to **Settings** and enable the **Food** module.

### Logging a Meal

1. Go to **Food**
2. Click **Log Meal**
3. Fill in:
   - **Meal type** — breakfast, lunch, dinner, snack, or meal
   - **Description** — what you ate
   - **Calories** — optional
   - **Protein (g)**, **Carbs (g)**, **Fat (g)** — optional
   - **Notes** — optional
4. Save

### AI-Assisted Nutrition Estimation

If you have an AI provider configured (Ollama or OpenAI), you can type a food description and request an AI estimate of its nutritional content. The AI returns calories and macros as a best-effort estimate — not a medical-grade analysis.

See [ai-providers.md](ai-providers.md) for how to configure AI.

### Today's Calorie Total

The Food module displays a running total of today's calories at the top of the page. It pulls only from entries logged on the current date.

### Editing and Deleting Entries

All food log entries can be edited or deleted from the log list. The last 7 days of entries are shown by default.

### Tips

- You do not need to be precise to get value from food logging. Even rough estimates reveal patterns.
- If you use AI estimation, treat the numbers as approximate guidance, not exact measurements.

---

## Fasting

**What it does:** A fasting timer that tracks when you started a fast, your target duration, and your mood at start and end. Completing a fast awards XP proportional to its duration.

### How to Enable

Go to **Settings** and enable the **Fasting** module.

### Starting a Fast

1. Go to **Fasting**
2. Click **Start Fast**
3. Set your target hours (default: 16)
4. Set your current mood (1-5)
5. Click start — the timer begins

Only one active fast is tracked at a time. Starting a new fast cancels any active one.

### Ending a Fast

Click **End Fast** to stop the timer. Enter your end mood and any notes. XP is calculated immediately.

### XP Calculation

```
XP = floor(duration_hours × 10)
```

A 16-hour fast earns 160 XP. A 24-hour fast earns 240 XP.

### History

The module shows the five most recently completed fasts with their duration and timestamps.

### Tips

- Use the mood fields honestly. If fasting worsens your mental state, that data is worth knowing.
- The fasting timer persists across browser sessions — you can close and reopen the page without losing your active fast.

---

## Deep Work

**What it does:** Tracks focused work sessions with a live timer. Sessions can be associated with a project. XP is awarded based on total session duration.

### How to Enable

Go to **Settings** and enable the **Deep Work** module.

### Starting a Session

1. Go to **Deep Work**
2. Click **Start Session**
3. Optionally select a project to associate the session with
4. Add a focus note (what you are working on)
5. Click start — the timer runs

Only one session is active at a time. Starting a new one closes the current one automatically.

### Ending a Session

Click **End Session**. The duration is calculated and XP is awarded.

### XP Calculation

```
XP = floor(duration_minutes / 10) × 5
```

A 25-minute session earns `floor(25/10) × 5 = 10 XP`.
A 60-minute session earns `floor(60/10) × 5 = 30 XP`.
A 90-minute session earns `floor(90/10) × 5 = 45 XP`.

### History

The module shows the five most recently completed sessions with duration, project association, and XP earned.

### Tips

- The minimum useful session is 25 minutes (one Pomodoro). Sessions shorter than this rarely reflect real deep work.
- Associate sessions with projects to track where your focused time goes.

---

## Challenges

**What it does:** Custom streak challenges with a defined target (e.g., "30 days no sugar", "90 days gym every day"). Track multiple simultaneous challenges. Check in daily or weekly to keep the streak alive.

### How to Enable

Go to **Settings** and enable the **Challenges** module.

### Creating a Challenge

1. Go to **Challenges**
2. Click **New Challenge**
3. Fill in:
   - **Name** — the challenge (e.g., "30 days alcohol-free")
   - **Category** — general, sobriety, fitness, health, etc.
   - **Target days** — leave blank for an open-ended challenge
   - **Start date** — defaults to today
   - **Check-in frequency** — daily or weekly
   - **Notes** — any context you want to capture

### Check-in

Each day (or week) you need to check in to a challenge to confirm you are still on track. A challenge that has not been checked in to shows a reminder.

### Challenge States

| State | Description |
|---|---|
| `active` | Running, streak counting |
| `completed` | Reached target days |
| `failed` | Marked as failed or restarted |

### Failing and Restarting

If you break a challenge, mark it as failed. The streak count at the time of failure is logged. You can then restart the challenge, which resets the start date to today.

### Milestone Days

The system tracks milestone days automatically: 7, 14, 21, 30, 60, 90, 100, 180, and 365. When a challenge hits one of these, the OpenClaw API (if enabled) reports it as a milestone.

### Tips

- Name challenges specifically. "Sobriety" is vague. "30 days no alcohol starting March 1" is a commitment.
- Set a target if you have one. An open-ended challenge can drift. A 90-day target creates urgency.

---

## Redirect

**What it does:** Sobriety replacement action tracking. When you feel the urge to drink or use, you log that you redirected the urge into a constructive action (gym, long drive, creative work, etc.). Higher urge levels earn more XP — the system rewards you more for resisting a strong urge.

### How to Enable

Go to **Settings** and enable the **Redirect** module.

### Logging a Redirect

1. Go to **Redirect**
2. Select the replacement action you took
3. Set the urge level (1-5, where 5 is the most intense)
4. Add any notes
5. Submit

### XP Calculation

```
XP = urge_redirect_base + (high_urge_bonus if urge_level >= 4 else 0)
```

With default settings:
- Normal urge (1-3): 30 XP
- High urge (4-5): 50 XP

These values are configurable in `config/rules.toml` under `[replacements]`.

### Default Replacement Actions

These are seeded from `config/categories.toml` on first run:

| Action | Points |
|---|---|
| Long Drive | 35 |
| Gym Session | 40 |
| Long Walk | 30 |
| Sober Social | 25 |
| Creative Work | 30 |
| Cook at Home | 20 |
| Documentary Night | 15 |
| Family Time | 25 |
| Project Work | 35 |
| Beach Trip | 30 |

### Tips

- The urge level field is private data. Be honest — it makes the XP system reflect real effort.
- If your go-to replacements are not in the default list, you can add custom categories by editing `config/categories.toml` and restarting the server.

---

## Wishlist

**What it does:** A simple list of places to visit and things to do. Captures title, location, description, and category. Useful as a motivational reference — things you are working towards.

### How to Enable

Go to **Settings** and enable the **Wishlist** module.

### Adding an Item

1. Go to **Wishlist**
2. Click **Add Item**
3. Fill in:
   - **Title** — what it is
   - **Location** — where (for places)
   - **Description** — any notes
   - **Category** — place, activity, etc.

### Tips

- Use this as a "things worth staying healthy for" list. Places you want to travel to when you're in better shape. Experiences you're building towards.
- It does not award XP — it is purely informational and motivational.

---

## AI Agent (OpenClaw)

**What it does:** Enables the OpenClaw API — a set of authenticated REST endpoints that an external AI agent can use to read your status, complete habits, push insights, log food, and check in to challenges on your behalf.

### How to Enable

Go to **Settings** and enable the **AI Agent (OpenClaw)** module. You also need `LIFEHACK_API_KEY` set in your `.env` file.

### What OpenClaw Can Do

- Read your current XP, level, habits, and check-in status
- Mark habits as complete by name
- Create new habits
- Submit a daily check-in
- Push insights to your dashboard
- Log food entries with nutrition data
- View and manage challenges

### Security

All OpenClaw endpoints require the `X-API-Key` header. If `LIFEHACK_API_KEY` is empty or not set, the API key check will reject all requests.

For the complete API reference, see [openclaw-api.md](openclaw-api.md).

### Tips

- The OpenClaw module logs every API action (action type, detail, IP address, timestamp) in the database. View this log at `GET /api/openclaw/log`.
- You do not need this module enabled if you only want AI-assisted food analysis or insights — those features use the internal AI provider and do not require the API key.
