# Life Operating System — 2030 Architecture

## Vision
A unified AI-native personal operating system that tracks, coaches, and optimizes human performance. Single AI identity (ECHO), single data layer (LifeHack), running locally on axiom.

**IMPORTANT:** LifeHack is PRIVATE. Only ECHO on axiom has access. OpenClaw (Linode) does NOT access LifeHack.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│                            ┌─────────────┐                                  │
│                            │    DOVIK    │                                  │
│                            │   (Human)   │                                  │
│                            └──────┬──────┘                                  │
│                                   │                                         │
│                    ┌──────────────┼──────────────┐                          │
│                    │              │              │                          │
│                    ▼              ▼              ▼                          │
│             ┌──────────┐   ┌──────────┐   ┌──────────┐                      │
│             │ Telegram │   │   Web    │   │  Voice   │  ← Input Channels   │
│             │   3CH0   │   │Dashboard │   │ (Future) │                      │
│             └────┬─────┘   └────┬─────┘   └────┬─────┘                      │
│                  │              │              │                            │
│                  └──────────────┼──────────────┘                            │
│                                 │                                           │
│                                 ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                              ECHO                                    │   │
│  │                       (axiom - LOCAL)                                │   │
│  │                         @d0v1k_bot                                   │   │
│  │                                                                      │   │
│  │   ┌────────────────────────────────────────────────────────────┐     │   │
│  │   │                     CAPABILITIES                           │     │   │
│  │   │                                                            │     │   │
│  │   │  • Claude Opus 4.5         • Habit Logging                 │     │   │
│  │   │  • Personal Assistant      • Goal Analysis                 │     │   │
│  │   │  • Trading Operations      • Pattern Detection             │     │   │
│  │   │  • Email/Calendar          • Strict Coaching               │     │   │
│  │   │  • Check-in Reminders      • Dynamic Habit Creation        │     │   │
│  │   │                                                            │     │   │
│  │   └────────────────────────────────────────────────────────────┘     │   │
│  │                                 │                                    │   │
│  │                                 ▼                                    │   │
│  │                    ┌────────────────────────┐                        │   │
│  │                    │      LIFEHACK API      │                        │   │
│  │                    │   (LOCAL - axiom)      │                        │   │
│  │                    │   lifehack.micinthe.com│                        │   │
│  │                    └────────────────────────┘                        │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         LIFEHACK DATABASE                            │   │
│  │                           (SQLite)                                   │   │
│  │                                                                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │   │
│  │  │   HABITS    │  │   GOALS     │  │  CHECK-INS  │  │  INSIGHTS   │  │   │
│  │  │             │  │             │  │             │  │             │  │   │
│  │  │ • Daily     │  │ • Targets   │  │ • Mood      │  │ • Warnings  │  │   │
│  │  │ • Streaks   │  │ • Progress  │  │ • Energy    │  │ • Advice    │  │   │
│  │  │ • XP        │  │ • Habits    │  │ • Sobriety  │  │ • Patterns  │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │   │
│  │                                                                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                   │   │
│  │  │  MOVEMENT   │  │  REDIRECT   │  │   STATS     │                   │   │
│  │  │             │  │             │  │             │                   │   │
│  │  │ • Walks     │  │ • Urge logs │  │ • Level     │                   │   │
│  │  │ • Distance  │  │ • Alts used │  │ • XP total  │                   │   │
│  │  │ • Duration  │  │ • Success   │  │ • Sobriety  │                   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                   │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ════════════════════════════════════════════════════════════════════════   │
│                          SEPARATE SYSTEM (BUSINESS)                         │
│  ════════════════════════════════════════════════════════════════════════   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        OPENCLAW (Linode)                             │   │
│  │                      172.236.221.66                                  │   │
│  │                                                                      │   │
│  │   • ERPNext Operations (6 sites, 40 companies)                       │   │
│  │   • Infrastructure Monitoring (Zabbix)                               │   │
│  │   • Business AI Agents (r00tkit, daniel, etc.)                       │   │
│  │                                                                      │   │
│  │   ⛔ NO ACCESS TO LIFEHACK (PRIVATE)                                 │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### ECHO (axiom - LOCAL)

```
┌─────────────────────────────────────────────────────────────┐
│  ECHO - Personal AI Assistant                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Location:     /home/d0v1k/clawd (axiom)                    │
│  Model:        Claude Opus 4.5                              │
│  Telegram:     @d0v1k_bot (3CH0)                            │
│  Gateway:      port 18789                                   │
│                                                             │
│  RESPONSIBILITIES:                                          │
│  ├── Personal Assistant (primary)                           │
│  ├── LifeHack integration (EXCLUSIVE)                       │
│  │   ├── Habit logging from chat                            │
│  │   ├── Goal analysis & habit creation                     │
│  │   ├── Check-in reminders                                 │
│  │   ├── Pattern detection                                  │
│  │   └── Strict coaching insights                           │
│  ├── Trading operations                                     │
│  ├── Email monitoring                                       │
│  ├── Calendar management                                    │
│  └── Task management (Vikunja)                              │
│                                                             │
│  LIFEHACK ACCESS:                                           │
│  ├── API Key: lifehack_openclaw_2026                        │
│  ├── URL: http://lifehack.micinthe.com                      │
│  └── Full read/write access                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### LifeHack OS (LOCAL)

```
┌─────────────────────────────────────────────────────────────┐
│  LIFEHACK OS - Personal Operating System                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Location:     axiom (77.237.233.253 proxy)                 │
│  URL:          http://lifehack.micinthe.com                 │
│  Port:         8420                                         │
│  Database:     SQLite                                       │
│  Auth:         Session (web) + API Key (ECHO only)          │
│                                                             │
│  FEATURES:                                                  │
│  ├── Dashboard          (visual overview)                   │
│  ├── Habits             (daily/weekly tracking)             │
│  ├── Goals              (auto-generates habits)             │
│  ├── Projects           (long-term milestones)              │
│  ├── Check-in           (mood, energy, sobriety)            │
│  ├── Movement           (walks, exercise)                   │
│  └── Redirect           (urge management)                   │
│                                                             │
│  API ENDPOINTS:                                             │
│  ├── GET  /api/openclaw/status                              │
│  ├── GET  /api/openclaw/habits                              │
│  ├── GET  /api/openclaw/goals                               │
│  ├── POST /api/openclaw/habit/create                        │
│  ├── POST /api/openclaw/habit/complete                      │
│  ├── POST /api/openclaw/goal/create                         │
│  ├── POST /api/openclaw/goal/{id}/link-habit                │
│  ├── POST /api/openclaw/checkin                             │
│  └── POST /api/openclaw/insight                             │
│                                                             │
│  🔒 PRIVATE - ECHO ONLY - NO EXTERNAL ACCESS                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Dynamic Goal → Habit Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        GOAL → HABITS AUTOMATION                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   YOU: "I want to lose 10kg by June"                                        │
│          │                                                                  │
│          ▼                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  ECHO analyzes goal:                                                │   │
│   │  • What's the target? (lose 10kg)                                   │   │
│   │  • What's the deadline? (June 2026)                                 │   │
│   │  • What daily/weekly actions achieve this?                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│          │                                                                  │
│          ▼                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  AUTO-GENERATED HABITS:                                             │   │
│   │  ┌─────────────────┬────────────┬────────────┐                      │   │
│   │  │ Habit           │ Frequency  │ Difficulty │                      │   │
│   │  ├─────────────────┼────────────┼────────────┤                      │   │
│   │  │ 30min Cardio    │ Daily      │ ★★☆        │                      │   │
│   │  │ Track Calories  │ Daily      │ ★☆☆        │                      │   │
│   │  │ No Junk Food    │ Daily      │ ★★☆        │                      │   │
│   │  │ Weekly Weigh-in │ Weekly     │ ★☆☆        │                      │   │
│   │  └─────────────────┴────────────┴────────────┘                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│          │                                                                  │
│          ▼                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  LINKED TO GOAL:                                                    │   │
│   │  Goal ID 1 ──────► Habit 6, 7, 8, 9                                 │   │
│   │  Progress tracked automatically                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│          │                                                                  │
│          ▼                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  DASHBOARD UPDATED:                                                 │   │
│   │  • New habits appear                                                │   │
│   │  • Goal progress visible                                            │   │
│   │  • AI insight pushed: "4 habits created. Start tomorrow."           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Daily Automation (Cron Jobs)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ TIME    │ JOB                    │ ACTION                               │
├─────────┼────────────────────────┼──────────────────────────────────────┤
│ 07:00   │ tech-pulse-digest      │ Tech news → Telegram                 │
│ 07:30   │ vikunja-daily-tasks    │ Task list → Telegram                 │
│ 09:00   │ lifehack-sobriety-track│ "Yesterday — clean or slip?"         │
│ 14:00   │ vikunja-afternoon      │ Task follow-up                       │
│ 20:00   │ vikunja-evening        │ End of day review                    │
│ 21:00   │ lifehack-checkin       │ Check-in reminder (if not done)      │
└─────────┴────────────────────────┴──────────────────────────────────────┘
```

---

## Chat-to-Action Mapping

```
┌─────────────────────────────────────────────────────────────────┐
│ YOU SAY                      │ ECHO DOES                        │
├──────────────────────────────┼──────────────────────────────────┤
│ "I walked 40 mins"           │ → Complete "Morning Walk" habit  │
│ "Did my workout"             │ → Complete "Workout" habit       │
│ "Stayed sober tonight"       │ → Complete "No Alcohol" habit    │
│ "2 hours of deep work"       │ → Complete "Deep Work 2h" habit  │
│ "Had a beer"                 │ → Log slip, offer redirect       │
│ "Feeling tired, mood 2"      │ → Update check-in                │
│ "Goal: run a marathon"       │ → Create goal + generate habits  │
│ "Add habit: meditate"        │ → Create new habit               │
└──────────────────────────────┴──────────────────────────────────┘
```

---

## Security Model

```
┌─────────────────────────────────────────────────────────────────┐
│                    ACCESS CONTROL                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LIFEHACK ACCESS:                                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  ✅ ECHO (axiom)     → Full read/write                  │    │
│  │  ✅ Web UI (dovik)   → Full read/write                  │    │
│  │  ⛔ OpenClaw (Linode)→ NO ACCESS                        │    │
│  │  ⛔ External         → NO ACCESS                        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  CURRENT AUTH:                                                  │
│  ├── API Key: lifehack_openclaw_2026                            │
│  └── Web: dovik / LifeHack2026!                                 │
│                                                                 │
│  FUTURE (Q2 2026):                                              │
│  ├── JWT tokens (short-lived)                                   │
│  ├── IP allowlist (axiom only)                                  │
│  ├── Rate limiting                                              │
│  └── Audit logging                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Infrastructure

```
┌─────────────────────────────────────────────────────────────────┐
│                     PERSONAL (PRIVATE)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  AXIOM (Home Server - Mauritius)                                │
│  ├── IP: 192.168.8.113 (LAN) / Tailscale                        │
│  ├── ECHO (Clawdbot) ────────► :18789                           │
│  ├── LifeHack (Flask) ───────► :8420                            │
│  └── Nginx proxy ────────────► lifehack.micinthe.com            │
│                                                                 │
│  RUNSTATE VPS (77.237.233.253)                                  │
│  └── Nginx reverse proxy to axiom for lifehack.micinthe.com     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     BUSINESS (SEPARATE)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  OPENCLAW VPS (172.236.221.66 - Linode)                         │
│  ├── OpenClaw Gateway ───────► :18789                           │
│  ├── ERPNext access (6 sites)                                   │
│  ├── Zabbix monitoring                                          │
│  └── Business AI agents                                         │
│                                                                 │
│  ⛔ NO CONNECTION TO LIFEHACK                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Reference

### ECHO Commands (Chat)
```
"I did [habit]"           → Log habit completion
"Goal: [description]"     → Create goal + auto-habits
"Add habit: [name]"       → Create new habit
"Check-in: mood 4"        → Quick check-in
"How am I doing?"         → Get status summary
```

### API Cheat Sheet
```bash
# Get status
curl -s "http://lifehack.micinthe.com/api/openclaw/status?api_key=lifehack_openclaw_2026"

# List habits
curl -s "http://lifehack.micinthe.com/api/openclaw/habits?api_key=lifehack_openclaw_2026"

# List goals
curl -s "http://lifehack.micinthe.com/api/openclaw/goals?api_key=lifehack_openclaw_2026"

# Complete habit
curl -s -X POST "http://lifehack.micinthe.com/api/openclaw/habit/complete" \
  -H "X-API-Key: lifehack_openclaw_2026" \
  -H "Content-Type: application/json" \
  -d '{"habit_name":"workout"}'

# Create goal
curl -s -X POST "http://lifehack.micinthe.com/api/openclaw/goal/create" \
  -H "X-API-Key: lifehack_openclaw_2026" \
  -H "Content-Type: application/json" \
  -d '{"name":"Lose 10kg","target_date":"2026-06-01"}'
```

---

## Roadmap

### ✅ Phase 1: Core (Complete)
- [x] LifeHack web dashboard
- [x] Habit tracking + streaks
- [x] Goals → auto-habit generation
- [x] ECHO integration
- [x] Daily reminders
- [x] Check-in system
- [x] Movement tracking
- [x] Redirect (urge management)

### 🔄 Phase 2: Intelligence (This Weekend)
- [ ] Pattern detection (weak habits)
- [ ] Strict coaching (auto-insights)
- [ ] Streak break alerts
- [ ] Weekly summary reports

### 📅 Phase 3: Integrations (Q2 2026)
- [ ] Apple Health sync
- [ ] Oura Ring data
- [ ] Strava activities
- [ ] Firefly III (spending patterns)

### 🔮 Phase 4: Scale (2027+)
- [ ] Mobile native app
- [ ] Voice input (Whisper)
- [ ] Predictive ML
- [ ] Family/team support

---

*Architecture v2.1 — 2026-03-14*
*System: ECHO on axiom*
*Privacy: LifeHack is LOCAL and PRIVATE*
