# LifeHack OS — Project Roadmap

**Owner:** Dovik  
**Developer:** Enki  
**Created:** 2026-03-15  
**Status:** Active Development

---

## 🎯 Vision

LifeHack OS is a **daily-focused personal operating system** that tracks everything in one place:
- Habits, health, food, movement, projects, goals
- AI-powered insights and recommendations
- Daily scoring and progress comparison
- Everything feeds into one unified view

**Core Principle:** Track everything daily. Compare. Improve. Repeat.

---

## 📊 Current State (2026-03-15)

### What Exists

| Feature | Status | Notes |
|---------|--------|-------|
| Habits | ✅ Working | 9 habits, complete/uncomplete/skip |
| Check-in | ✅ Working | Daily mood, energy, sobriety |
| Food Log | ✅ Basic | Just added, needs AI analysis |
| Projects | ⚠️ Partial | Vikunja integration works, UI needs work |
| Movement/Walks | ⚠️ Empty | Table exists, no data |
| Redirect (urges) | ⚠️ Empty | Table exists, not used |
| Settings | ✅ Working | Integration toggles |
| XP/Levels | ✅ Working | Points system functional |
| Sobriety Tracker | ✅ Working | 4-day streak |

### Database Tables
- `habits` (9) — habit definitions
- `habit_completions` (5) — completion logs
- `daily_checkins` (4) — daily check-ins
- `food_logs` (1) — food entries
- `goals` (1) — user goals
- `point_ledger` (12) — XP transactions
- `user_stats` (1) — XP, level
- `walk_logs` (0) — empty
- `replacement_logs` (0) — empty
- `deep_work_sessions` (0) — empty
- `daily_scores` (0) — just created

### UI Views
1. Dashboard
2. Habits
3. Projects
4. Check-in
5. Movement
6. Redirect
7. Food
8. Settings

---

## 🚀 Phase 1: Daily Focus (Priority)

**Goal:** Make the dashboard a proper DAILY TRACKER

### 1.1 Daily View Redesign ✅
- [x] Today's date prominently displayed
- [x] Daily score (0-100%) calculated from:
  - Habits completed (50%)
  - Check-in done (25%)
  - Food logged (25%)
- [x] Visual progress ring/circle (animated SVG)
- [x] "Yesterday" comparison panel
- [x] Delta indicators (↑↓) showing improvement
- [x] Daily tips based on what's missing

### 1.2 Daily History ✅
- [x] Calendar view showing daily scores (last 7 days)
- [x] Color-coded days (gray/warning/accent/success)
- [x] Week averages displayed
- [ ] Click day to see details (future)

### 1.3 Daily Tips
- [ ] AI-generated tips based on:
  - What's not done today
  - Patterns from past days
  - Upcoming events (if calendar connected)
- [ ] "Focus for today" suggestions

### 1.4 Daily Summary
- [ ] End-of-day summary generation
- [ ] What was accomplished
- [ ] What was missed
- [ ] Streaks updated

---

## 🍽️ Phase 2: Food & Nutrition ✅

### 2.1 Enhanced Food Logging
- [x] Quick-add common meals
- [x] Macro tracking (P/C/F)
- [ ] Meal templates (save favorites)
- [x] AI analysis integration (backend ready)

### 🗺️ Phase 9: Wishlist & Exploration ✅
- [x] Places to visit wishlist
- [x] Location and description tracking

### ⏱️ Phase 10: Fasting Tracker ✅
- [x] Advanced live timer
- [x] Progress visualization
- [x] Target hour presets (16h, 18h, etc.)
- [x] Fasting history and XP awards

### 2.4 Nutrition Dashboard
- [ ] Daily calorie goal progress
- [ ] Macro breakdown (P/C/F)
- [ ] Weekly nutrition trends

---

## 💪 Phase 3: Habits Enhancement

### 3.1 Habit Management ✅
- [x] Edit habit (name, category, difficulty)
- [x] Delete/archive habit (soft delete)
- [ ] Disable habit for specific days (weekends off)
- [ ] Habit scheduling (daily/weekly/specific days)

### 3.2 Habit Insights
- [ ] Streak visualization
- [ ] Best day of week for each habit
- [ ] Completion rate over time
- [ ] Habit correlation (which habits done together)

### 3.3 Habit Categories
- [ ] Custom categories
- [ ] Category-based views
- [ ] Category daily goals

---

## 📋 Phase 4: Projects & Tasks

### 4.1 Vikunja Full Integration
- [ ] View all projects with tasks
- [ ] Create/edit/delete tasks
- [ ] Due dates and priorities
- [ ] Task completion syncs both ways

### 4.2 Daily Tasks View
- [ ] "Due Today" section on dashboard
- [ ] Overdue tasks highlighted
- [ ] Quick-add task

### 4.3 Project Progress
- [ ] Milestone tracking
- [ ] Project completion percentage
- [ ] Time spent on projects (via deep work)

---

## 🚶 Phase 5: Movement & Health

### 5.1 Walk/Exercise Logging
- [ ] Quick log walk (distance, duration)
- [ ] GPS integration (optional)
- [ ] Exercise types (walk, run, gym, etc.)

### 5.2 Health Metrics
- [ ] Weight tracking
- [ ] Sleep logging (or integration)
- [ ] Symptom tracking
- [ ] Correlations (food → symptoms)

---

## 📅 Phase 6: Calendar & Events ✅

### 6.1 Google Calendar Integration
- [x] Show today's events on dashboard
- [x] Upcoming events (next 24h)
- [ ] Event reminders (future)

---

## 💰 Phase 7: Finance (Optional)

### 7.1 Firefly III Integration
- [ ] Daily spending summary
- [ ] Budget status
- [ ] Quick expense logging

---

## 🤖 Phase 8: AI Enhancement

### 8.1 Daily AI Companion
- [ ] Morning briefing (via Telegram)
- [ ] Evening summary
- [ ] Proactive suggestions

### 8.2 Pattern Recognition
- [ ] Identify trends
- [ ] Predict habit completion
- [ ] Personalized coaching

---

## 📱 Technical Improvements

### Infrastructure
- [ ] Mobile-responsive improvements
- [ ] PWA (installable app)
- [ ] Offline support
- [ ] Push notifications

### Performance
- [ ] API caching
- [ ] Lazy loading
- [ ] Image optimization

### Code Quality
- [ ] Unit tests
- [ ] Error handling
- [ ] Logging

---

## 📅 Implementation Order

### Week 1 (Current)
1. ✅ Vikunja integration
2. ✅ Food logging basic
3. ✅ Habit undo/skip
4. 🔄 Daily view redesign
5. 🔄 Daily scoring

### Week 2
1. Daily history calendar
2. Food image upload
3. AI food analysis
4. Habit management (edit/delete)

### Week 3
1. Movement logging
2. Projects tasks view
3. Daily tips AI
4. End-of-day summary

### Week 4
1. Calendar integration
2. Deep work tracking
3. Weekly reports
4. Mobile PWA

---

## 📝 Notes

- All changes deploy to PRODUCTION (77.237.233.253)
- Database: SQLite at /opt/lifehack-os/data/lifehack.db
- Web: Flask on port 8420
- URL: lifehack.micinthe.com

---

## ✅ Completed Today (2026-03-15)

1. ✅ Vikunja integration (projects/tasks from Vikunja)
2. ✅ Settings page with integration toggles
3. ✅ Habit undo (click again to uncomplete)
4. ✅ Habit skip for today
5. ✅ Food logging section added
6. ✅ Sobriety backfill (4 days logged)
7. ✅ Projects showing on dashboard
8. ✅ XP progress bar

---

*Last updated: 2026-03-15 11:05 MU*
