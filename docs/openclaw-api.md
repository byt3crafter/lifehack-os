# OpenClaw API Reference

OpenClaw is the external AI agent integration layer for LifeHack OS. Any AI agent, automation script, or external system can use these endpoints to read your status, complete habits, push insights, log food, and manage challenges.

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Base URL](#base-url)
4. [Self-Discovery: Schema Endpoint](#self-discovery-schema-endpoint)
5. [Core Endpoints](#core-endpoints)
   - [GET /api/openclaw/status](#get-apiopenclaw-status)
   - [GET /api/openclaw/habits](#get-apiopenclawhabits)
   - [POST /api/openclaw/habit/complete](#post-apiopenclawhabitcomplete)
   - [POST /api/openclaw/habit/create](#post-apiopenclawhabitcreate)
   - [POST /api/openclaw/checkin](#post-apiopenclaw-checkin)
   - [POST /api/openclaw/insight](#post-apiopenclawinsight)
   - [POST /api/openclaw/food/log](#post-apiopenclawfoodlog)
   - [GET /api/openclaw/log](#get-apiopenclawlog)
6. [Challenge Endpoints](#challenge-endpoints)
   - [GET /api/challenges/openclaw/status](#get-apichallengesopenclaw-status)
   - [POST /api/challenges/openclaw/checkin](#post-apichallengesopenclaw-checkin)
   - [POST /api/challenges/openclaw/fail](#post-apichallengesopenclaw-fail)
7. [Error Responses](#error-responses)
8. [Example Agent Workflow](#example-agent-workflow)

---

## Overview

OpenClaw endpoints allow an external agent to:

- Read the user's current state (XP, habits, check-in, patterns)
- Take actions on behalf of the user (complete habits, submit check-ins, log food)
- Push information to the dashboard (insights, advice, warnings)
- Monitor and manage challenges

These endpoints are designed to be consumed by an AI agent running on a schedule (e.g., a nightly or morning summary agent), or integrated into a larger automation system.

### Enabling OpenClaw

1. Set `LIFEHACK_API_KEY` in your `.env` file to a random secret string
2. Enable the **AI Agent (OpenClaw)** module in Settings

```bash
# Generate a key
python3 -c "import secrets; print(secrets.token_hex(32))"
```

```dotenv
LIFEHACK_API_KEY=your-generated-key-here
```

---

## Authentication

All OpenClaw endpoints (except `/api/openclaw/schema`) require authentication via the `X-API-Key` header:

```
X-API-Key: your-api-key-here
```

The API key can also be passed as a query parameter:

```
GET /api/openclaw/status?api_key=your-api-key-here
```

Requests with a missing or incorrect key receive a `401` response:

```json
{"error": "Invalid API key"}
```

**Important:** The API key is checked against `LIFEHACK_API_KEY` from the environment. If this variable is not set (empty string), all requests with any key will be rejected. Set the variable before using these endpoints.

---

## Base URL

All endpoints are relative to the server root. With default settings:

```
http://localhost:8420
```

---

## Self-Discovery: Schema Endpoint

`GET /api/openclaw/schema`

Returns a machine-readable description of all available endpoints. This endpoint does not require authentication — an agent can call it to discover the API before authenticating.

**Request:**

```bash
curl http://localhost:8420/api/openclaw/schema
```

**Response:**

```json
{
  "name": "LifeHack OS OpenClaw API",
  "version": "1.0",
  "auth": {
    "type": "api_key",
    "header": "X-API-Key",
    "description": "Set your API key in .env as LIFEHACK_API_KEY"
  },
  "endpoints": [
    {
      "path": "/api/openclaw/status",
      "method": "GET",
      "description": "Full status dump — XP, habits, check-in, patterns, pending actions",
      "auth": true
    },
    ...
  ]
}
```

---

## Core Endpoints

---

### GET /api/openclaw/status

Returns a comprehensive snapshot of the user's current state. This is the primary endpoint for an agent to understand what is happening today.

**Request:**

```bash
curl http://localhost:8420/api/openclaw/status \
  -H "X-API-Key: your-key"
```

**Response:**

```json
{
  "timestamp": "2026-03-18T08:45:00.123456",
  "stats": {
    "total_xp": 2450,
    "level": 5,
    "level_name": "Master",
    "sobriety_days": 45
  },
  "today": {
    "habits_total": 6,
    "habits_completed": 2,
    "habits_pending": 4,
    "checkin_done": false,
    "mood": null,
    "energy": null,
    "avoided_alcohol": null
  },
  "patterns": {
    "strong_habits": [
      {"name": "Morning workout", "streak": 12},
      {"name": "Read 30 minutes", "streak": 9}
    ],
    "weak_habits": [
      {"name": "Cold shower", "category": "fitness"},
      {"name": "Meditate", "category": "mindset"}
    ],
    "needs_attention": true
  },
  "pending_actions": ["Cold shower", "Meditate", "Journal", "Evening walk"]
}
```

**Fields:**

| Field | Description |
|---|---|
| `stats.total_xp` | All-time XP total |
| `stats.level` | Current numeric level (1-7) |
| `stats.level_name` | Level display name |
| `stats.sobriety_days` | Current sobriety streak from check-ins |
| `today.habits_total` | Total active habits |
| `today.habits_completed` | Completed today |
| `today.habits_pending` | Not yet completed today |
| `today.checkin_done` | Whether today's check-in has been submitted |
| `today.mood` | Check-in mood (1-5) or null |
| `today.energy` | Check-in energy (1-5) or null |
| `patterns.strong_habits` | Habits with streak >= 7 days |
| `patterns.weak_habits` | Habits with streak = 0 and not done today |
| `patterns.needs_attention` | True if weak habits outnumber strong habits |
| `pending_actions` | Names of habits not yet completed today |

---

### GET /api/openclaw/habits

Returns all active habits with today's completion status and current streak for each.

**Request:**

```bash
curl http://localhost:8420/api/openclaw/habits \
  -H "X-API-Key: your-key"
```

**Response:**

```json
[
  {
    "id": 1,
    "name": "Morning workout",
    "category": "fitness",
    "frequency": "daily",
    "streak": 12,
    "completed_today": true
  },
  {
    "id": 2,
    "name": "Read 30 minutes",
    "category": "learning",
    "frequency": "daily",
    "streak": 9,
    "completed_today": false
  }
]
```

**Fields:**

| Field | Type | Description |
|---|---|---|
| `id` | integer | Habit's database ID |
| `name` | string | Habit name |
| `category` | string | Category key (e.g., `fitness`, `health`) |
| `frequency` | string | `daily` or `weekly` |
| `streak` | integer | Current consecutive completion streak |
| `completed_today` | boolean | Whether completed today |

---

### POST /api/openclaw/habit/complete

Marks a habit as complete by name. Uses partial, case-insensitive matching — so `"workout"` matches `"Morning workout"`.

**Request:**

```bash
curl -X POST http://localhost:8420/api/openclaw/habit/complete \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"habit_name": "workout"}'
```

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `habit_name` | string | Yes | Partial name to match (case-insensitive) |

**Response (success):**

```json
{
  "success": true,
  "habit": "Morning workout",
  "points": 15
}
```

The `points` value reflects the streak multiplier if the habit has a streak of 7 or more days.

**Response (not found):**

```json
{"error": "Habit not found"}
```

HTTP status: `404`

---

### POST /api/openclaw/habit/create

Creates a new habit.

**Request:**

```bash
curl -X POST http://localhost:8420/api/openclaw/habit/create \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Evening stretch",
    "category": "fitness",
    "frequency": "daily",
    "difficulty": 2
  }'
```

**Request Body:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | Yes | — | Habit name |
| `category` | string | No | `health` | Category key |
| `frequency` | string | No | `daily` | `daily` or `weekly` |
| `difficulty` | integer | No | `1` | 1 to 5 |

**Response:**

```json
{
  "success": true,
  "id": 7,
  "name": "Evening stretch"
}
```

---

### POST /api/openclaw/checkin

Submits today's daily check-in. If a check-in already exists for today, it is updated but no additional XP is awarded.

**Request:**

```bash
curl -X POST http://localhost:8420/api/openclaw/checkin \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "completed_today": "Finished the project proposal and went for a walk",
    "avoided_alcohol": true,
    "worked_on_future": true,
    "mood": 4,
    "energy": 3,
    "improvement_note": "Need to sleep earlier"
  }'
```

**Request Body:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `completed_today` | string | No | `""` | What was accomplished today |
| `avoided_alcohol` | boolean | No | `true` | Whether alcohol was avoided |
| `worked_on_future` | boolean | No | `false` | Whether future-building work was done |
| `mood` | integer | No | `3` | Mood rating 1-5 |
| `energy` | integer | No | `3` | Energy rating 1-5 |
| `improvement_note` | string | No | `""` | One thing to improve |

**Response:**

```json
{
  "success": true,
  "points": 50
}
```

The `points` field shows XP awarded. It is `0` if the check-in already existed for today.

---

### POST /api/openclaw/insight

Pushes an insight to the user's dashboard. Insights appear in the dashboard's insight panel and can be dismissed by the user.

**Request:**

```bash
curl -X POST http://localhost:8420/api/openclaw/insight \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Streak at risk",
    "content": "Your meditation habit has not been completed in 2 days. A 15-minute session now will protect your streak.",
    "type": "warning",
    "priority": 8
  }'
```

**Request Body:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `title` | string | Yes | — | Short title shown in the card header |
| `content` | string | Yes | — | Insight text (1-3 sentences recommended) |
| `type` | string | No | `advice` | `advice`, `warning`, `celebration`, or `tip` |
| `priority` | integer | No | `0` | 0-10, higher priority shown first |

**Response:**

```json
{"success": true}
```

Insights are displayed in order of `priority DESC, created_at DESC`. The dashboard shows up to 5 undismissed insights at a time.

---

### POST /api/openclaw/food/log

Logs a food entry with nutritional data. Intended for agents that have already estimated nutrition (e.g., using an AI) and want to push the result directly to the food log.

**Request:**

```bash
curl -X POST http://localhost:8420/api/openclaw/food/log \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "meal_type": "lunch",
    "description": "Grilled chicken salad with olive oil dressing",
    "calories": 420,
    "protein_g": 38,
    "carbs_g": 12,
    "fat_g": 22,
    "ai_analysis": "Estimated via GPT-4o based on description",
    "notes": ""
  }'
```

**Request Body:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `meal_type` | string | No | `meal` | `breakfast`, `lunch`, `dinner`, `snack`, or `meal` |
| `description` | string | No | `""` | Food description |
| `calories` | number | No | null | Total calories |
| `protein_g` | number | No | null | Protein in grams |
| `carbs_g` | number | No | null | Carbohydrates in grams |
| `fat_g` | number | No | null | Fat in grams |
| `ai_analysis` | string | No | `""` | Note about how values were estimated |
| `notes` | string | No | `""` | Additional notes |

**Response:**

```json
{
  "success": true,
  "id": 23
}
```

The `id` is the database ID of the newly created food log entry.

---

### GET /api/openclaw/log

Returns the 50 most recent OpenClaw actions. Useful for auditing agent activity.

**Request:**

```bash
curl http://localhost:8420/api/openclaw/log \
  -H "X-API-Key: your-key"
```

**Response:**

```json
[
  {
    "id": 145,
    "action": "status_check",
    "detail": "",
    "ip": "127.0.0.1",
    "timestamp": "2026-03-18T08:45:00"
  },
  {
    "id": 144,
    "action": "habit_complete",
    "detail": "Morning workout",
    "ip": "127.0.0.1",
    "timestamp": "2026-03-18T07:30:00"
  },
  {
    "id": 143,
    "action": "push_insight",
    "detail": "Streak at risk",
    "ip": "127.0.0.1",
    "timestamp": "2026-03-18T07:00:00"
  }
]
```

**Action types logged:**

| Action | Trigger |
|---|---|
| `status_check` | `GET /api/openclaw/status` |
| `habit_complete` | `POST /api/openclaw/habit/complete` |
| `habit_create` | `POST /api/openclaw/habit/create` |
| `checkin` | `POST /api/openclaw/checkin` |
| `push_insight` | `POST /api/openclaw/insight` |
| `food_log` | `POST /api/openclaw/food/log` |
| `view_log` | `GET /api/openclaw/log` |

---

## Challenge Endpoints

These endpoints use a different URL prefix (`/api/challenges/openclaw/`) because they are part of the Challenges module, but they are authenticated with the same `X-API-Key` header.

---

### GET /api/challenges/openclaw/status

Returns active challenges with stats, a list of challenges needing check-in today, and any milestone days reached today.

**Request:**

```bash
curl http://localhost:8420/api/challenges/openclaw/status \
  -H "X-API-Key: your-key"
```

**Response:**

```json
{
  "active_challenges": [
    {
      "id": 1,
      "name": "90 days alcohol-free",
      "category": "sobriety",
      "streak_days": 45,
      "target_days": 90,
      "progress": 50
    },
    {
      "id": 2,
      "name": "Daily gym",
      "category": "fitness",
      "streak_days": 7,
      "target_days": 30,
      "progress": 23
    }
  ],
  "needs_checkin": ["Daily gym"],
  "milestones_today": [
    {
      "name": "Daily gym",
      "days": 7
    }
  ]
}
```

**Fields:**

| Field | Description |
|---|---|
| `active_challenges` | All currently active challenges |
| `streak_days` | Days since challenge start date |
| `target_days` | Target day count (null if open-ended) |
| `progress` | Percentage towards target (null if no target) |
| `needs_checkin` | Names of challenges awaiting check-in today |
| `milestones_today` | Challenges that hit a milestone day (7, 14, 21, 30, 60, 90, 100, 180, 365) today |

---

### POST /api/challenges/openclaw/checkin

Checks in to a challenge by name. Uses partial, case-insensitive matching.

**Request:**

```bash
curl -X POST http://localhost:8420/api/challenges/openclaw/checkin \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "challenge_name": "alcohol-free",
    "note": "Day 46. Feeling strong."
  }'
```

**Request Body:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `challenge_name` | string | Yes | — | Partial name to match (case-insensitive) |
| `note` | string | No | `"Checked in via OpenClaw"` | Optional check-in note |

**Response (success):**

```json
{
  "success": true,
  "challenge": "90 days alcohol-free"
}
```

**Response (not found):**

```json
{"error": "Challenge not found"}
```

HTTP status: `404`

---

### POST /api/challenges/openclaw/fail

Marks an active challenge as failed by name. Records the streak count at the time of failure.

**Request:**

```bash
curl -X POST http://localhost:8420/api/challenges/openclaw/fail \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "challenge_name": "alcohol-free",
    "reason": "Drank at the wedding"
  }'
```

**Request Body:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `challenge_name` | string | Yes | — | Partial name to match (case-insensitive) |
| `reason` | string | No | `""` | Reason for failure, logged in challenge history |

**Response (success):**

```json
{
  "success": true,
  "challenge": "90 days alcohol-free",
  "streak_days": 45
}
```

**Response (not found):**

```json
{"error": "Challenge not found"}
```

HTTP status: `404`

---

## Error Responses

All endpoints return JSON error responses:

| HTTP Status | Response Body | Cause |
|---|---|---|
| `401` | `{"error": "Invalid API key"}` | Missing or incorrect `X-API-Key` |
| `404` | `{"error": "Habit not found"}` | Habit name matched nothing |
| `404` | `{"error": "Challenge not found"}` | Challenge name matched nothing |
| `400` | `{"error": "No active session"}` | Deep work or fasting end with no active session |

---

## Example Agent Workflow

A typical morning agent workflow:

```bash
#!/bin/bash
BASE="http://localhost:8420"
KEY="your-api-key-here"

# 1. Get current status
STATUS=$(curl -s "$BASE/api/openclaw/status" -H "X-API-Key: $KEY")

# 2. Check if check-in is done
CHECKIN_DONE=$(echo $STATUS | python3 -c "import sys,json; print(json.load(sys.stdin)['today']['checkin_done'])")

# 3. Get challenge status
CHALLENGES=$(curl -s "$BASE/api/challenges/openclaw/status" -H "X-API-Key: $KEY")

# 4. Push a morning briefing insight
PENDING=$(echo $STATUS | python3 -c "import sys,json; d=json.load(sys.stdin); print(', '.join(d['pending_actions'][:3]))")

curl -s -X POST "$BASE/api/openclaw/insight" \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"title\": \"Morning briefing\",
    \"content\": \"Good morning. You have ${PENDING} pending. Let's go.\",
    \"type\": \"tip\",
    \"priority\": 5
  }"
```

For a Python agent:

```python
import requests

BASE = "http://localhost:8420"
HEADERS = {"X-API-Key": "your-api-key-here"}

# Get full status
status = requests.get(f"{BASE}/api/openclaw/status", headers=HEADERS).json()

# Complete a habit
requests.post(
    f"{BASE}/api/openclaw/habit/complete",
    headers=HEADERS,
    json={"habit_name": "morning workout"}
)

# Push an insight
requests.post(
    f"{BASE}/api/openclaw/insight",
    headers=HEADERS,
    json={
        "title": "Well done",
        "content": f"You've completed {status['today']['habits_completed']} habits today. Keep going.",
        "type": "celebration",
        "priority": 3
    }
)
```
