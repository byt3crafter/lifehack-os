"""API discovery endpoint — returns a summary of all available REST endpoints."""
from flask import Blueprint, jsonify

from .decorators import login_required

api_docs_bp = Blueprint('api_docs', __name__, url_prefix='/api')


@api_docs_bp.route('')
@login_required
def api_index():
    """GET /api — returns a structured list of all available API endpoints."""
    endpoints = {
        "version": "1.0",
        "base_url": "/api",
        "auth": "Session cookie (login via /auth/login) or X-API-Key header for AI endpoints",
        "groups": {
            "habits": {
                "description": "Daily habit tracking with streaks and points",
                "endpoints": [
                    {"method": "GET",    "path": "/api/habits",                    "description": "List all active habits with today's completion status and streaks"},
                    {"method": "POST",   "path": "/api/habits",                    "description": "Create a new habit", "body": {"name": "string", "category": "string", "frequency": "daily|weekly", "difficulty": "1-3"}},
                    {"method": "PUT",    "path": "/api/habits/:id",                "description": "Update habit name, category, difficulty, or active status"},
                    {"method": "DELETE", "path": "/api/habits/:id",                "description": "Soft-delete (deactivate) a habit"},
                    {"method": "POST",   "path": "/api/habits/:id/complete",       "description": "Mark a habit complete for today, awards points"},
                    {"method": "POST",   "path": "/api/habits/:id/uncomplete",     "description": "Undo today's completion for a habit"},
                    {"method": "POST",   "path": "/api/habits/:id/skip",           "description": "Skip a habit for today without breaking the streak"},
                ]
            },
            "food": {
                "description": "Nutrition and meal logging",
                "endpoints": [
                    {"method": "GET",    "path": "/api/food",                      "description": "List food logs for the last 7 days plus today's calorie total"},
                    {"method": "POST",   "path": "/api/food",                      "description": "Log a meal", "body": {"meal_type": "string", "description": "string", "calories": "number", "protein_g": "number", "carbs_g": "number", "fat_g": "number"}},
                    {"method": "PUT",    "path": "/api/food/:id",                  "description": "Edit a food log entry"},
                    {"method": "DELETE", "path": "/api/food/:id",                  "description": "Delete a food log entry"},
                    {"method": "POST",   "path": "/api/food/analyze",              "description": "Store AI-generated nutritional analysis (requires X-API-Key)", "body": {"food_id": "int", "ai_analysis": "string", "calories": "number"}},
                ]
            },
            "walks": {
                "description": "Movement and exercise logging",
                "endpoints": [
                    {"method": "GET",    "path": "/api/walks",                     "description": "List recent walks (up to 20) with weekly stats"},
                    {"method": "POST",   "path": "/api/walks",                     "description": "Log a walk or exercise session", "body": {"distance_km": "number", "duration_minutes": "number", "mood_before": "1-5", "mood_after": "1-5", "location": "string", "movement_type": "string", "notes": "string"}},
                    {"method": "PUT",    "path": "/api/walks/:id",                 "description": "Edit a walk log entry"},
                    {"method": "DELETE", "path": "/api/walks/:id",                 "description": "Delete a walk log entry"},
                ]
            },
            "checkin": {
                "description": "Daily mental health and sobriety check-ins",
                "endpoints": [
                    {"method": "GET",    "path": "/api/checkin",                   "description": "Get today's check-in (null if not done yet)"},
                    {"method": "POST",   "path": "/api/checkin",                   "description": "Save today's check-in (upsert)", "body": {"mood": "1-5", "energy": "1-5", "avoided_alcohol": "bool", "worked_on_future": "bool", "completed_today": "string", "improvement_note": "string"}},
                ]
            },
            "challenges": {
                "description": "Long-term streak challenges and habit goals",
                "endpoints": [
                    {"method": "GET",    "path": "/api/challenges",                "description": "List all challenges with streak stats"},
                    {"method": "GET",    "path": "/api/challenges/active",         "description": "List only active challenges"},
                    {"method": "POST",   "path": "/api/challenges",                "description": "Create a new challenge", "body": {"name": "string", "category": "string", "target_days": "int", "start_date": "YYYY-MM-DD", "check_in_frequency": "daily|weekly"}},
                    {"method": "PUT",    "path": "/api/challenges/:id",            "description": "Edit a challenge"},
                    {"method": "DELETE", "path": "/api/challenges/:id",            "description": "Delete a challenge and its logs"},
                    {"method": "POST",   "path": "/api/challenges/:id/checkin",    "description": "Check in to confirm you're still on track"},
                    {"method": "POST",   "path": "/api/challenges/:id/fail",       "description": "Mark a challenge as failed"},
                    {"method": "POST",   "path": "/api/challenges/:id/restart",    "description": "Restart a failed challenge from today"},
                    {"method": "POST",   "path": "/api/challenges/:id/complete",   "description": "Mark a challenge as successfully completed"},
                    {"method": "GET",    "path": "/api/challenges/:id/logs",       "description": "Get activity log for a specific challenge"},
                ]
            },
            "projects": {
                "description": "Project and task management",
                "endpoints": [
                    {"method": "GET",    "path": "/api/projects",                  "description": "List all projects with progress"},
                    {"method": "POST",   "path": "/api/projects",                  "description": "Create a new project", "body": {"name": "string", "description": "string"}},
                    {"method": "PUT",    "path": "/api/projects/:id",              "description": "Update a project"},
                    {"method": "DELETE", "path": "/api/projects/:id",              "description": "Delete a project"},
                    {"method": "GET",    "path": "/api/tasks",                     "description": "List tasks (optional ?project_id= filter)"},
                    {"method": "POST",   "path": "/api/tasks",                     "description": "Create a task", "body": {"project_id": "int", "title": "string", "priority": "0-3"}},
                    {"method": "PUT",    "path": "/api/tasks/:id",                 "description": "Edit a task"},
                    {"method": "DELETE", "path": "/api/tasks/:id",                 "description": "Delete a task"},
                    {"method": "POST",   "path": "/api/tasks/:id/complete",        "description": "Mark a task as done, awards 10 points"},
                    {"method": "POST",   "path": "/api/tasks/:id/uncomplete",      "description": "Mark a task as not done"},
                    {"method": "POST",   "path": "/api/milestones/:id/complete",   "description": "Mark a milestone as complete, awards 50 points"},
                ]
            },
            "fasting": {
                "description": "Intermittent fasting timer and logs",
                "endpoints": [
                    {"method": "GET",    "path": "/api/fasting/status",            "description": "Get current active fast and recent history"},
                    {"method": "POST",   "path": "/api/fasting/start",             "description": "Start a new fast (cancels any active fast)", "body": {"target": "hours_int", "mood": "1-5"}},
                    {"method": "POST",   "path": "/api/fasting/end",               "description": "End the active fast, awards points proportional to duration", "body": {"mood": "1-5", "notes": "string"}},
                    {"method": "POST",   "path": "/api/fasting/cancel",            "description": "Cancel the active fast without awarding points"},
                ]
            },
            "wishlist": {
                "description": "Places and experiences wishlist",
                "endpoints": [
                    {"method": "GET",    "path": "/api/wishlist",                  "description": "List all wishlist items"},
                    {"method": "POST",   "path": "/api/wishlist",                  "description": "Add an item to the wishlist", "body": {"title": "string", "location": "string", "description": "string", "category": "place|experience|food|activity"}},
                    {"method": "PUT",    "path": "/api/wishlist/:id",              "description": "Edit a wishlist item"},
                    {"method": "DELETE", "path": "/api/wishlist/:id",              "description": "Delete a wishlist item"},
                    {"method": "POST",   "path": "/api/wishlist/:id/complete",     "description": "Mark a wishlist item as visited/done"},
                ]
            },
            "deepwork": {
                "description": "Focused work session timer",
                "endpoints": [
                    {"method": "GET",    "path": "/api/deepwork/status",           "description": "Get current active session and recent history"},
                    {"method": "POST",   "path": "/api/deepwork/start",            "description": "Start a deep work session", "body": {"project_id": "int|null", "notes": "string"}},
                    {"method": "POST",   "path": "/api/deepwork/end",              "description": "End the active session, awards points per 10 minutes"},
                ]
            },
            "replacements": {
                "description": "Urge replacement actions for sobriety support",
                "endpoints": [
                    {"method": "GET",    "path": "/api/replacements",              "description": "List replacement actions and recent logs"},
                    {"method": "POST",   "path": "/api/replacements",              "description": "Log a replacement action (urge redirect)", "body": {"action_id": "int", "urge_level": "1-5", "notes": "string"}},
                ]
            },
            "daily": {
                "description": "Daily summary dashboard data",
                "endpoints": [
                    {"method": "GET",    "path": "/api/daily",                     "description": "Today and yesterday summary with score, tips, and deltas"},
                    {"method": "GET",    "path": "/api/daily/history",             "description": "Historical daily scores (default 7 days, use ?days=N)"},
                ]
            },
            "stats": {
                "description": "User XP, level, and stats",
                "endpoints": [
                    {"method": "GET",    "path": "/api/stats",                     "description": "Current XP, level, level name, and sobriety streak"},
                    {"method": "GET",    "path": "/api/categories",                "description": "List habit categories with colors and icons"},
                ]
            },
            "reports": {
                "description": "Analytics and progress reports",
                "endpoints": [
                    {"method": "GET",    "path": "/api/reports/weekly",            "description": "Weekly summary: habits, check-ins, points, walks"},
                    {"method": "GET",    "path": "/api/reports/streaks",           "description": "Current streaks for all habits (non-zero only)"},
                    {"method": "GET",    "path": "/api/reports/points/history",    "description": "Points history by date and category (use ?days=N, default 30)"},
                ]
            },
            "insights": {
                "description": "AI-generated insights and recommendations",
                "endpoints": [
                    {"method": "GET",    "path": "/api/insights",                  "description": "List up to 5 active (non-dismissed) AI insights"},
                    {"method": "POST",   "path": "/api/insights/:id/dismiss",      "description": "Dismiss an insight"},
                ]
            },
            "calendar": {
                "description": "Calendar integration (requires provider configuration)",
                "endpoints": [
                    {"method": "GET",    "path": "/api/calendar/events",           "description": "Upcoming events (use ?days=N, default 7). Returns enabled:false if not configured"},
                ]
            },
            "finance": {
                "description": "Finance integration via Firefly III (requires provider configuration)",
                "endpoints": [
                    {"method": "GET",    "path": "/api/finance/summary",           "description": "Account balance and recent transactions. Returns enabled:false if not configured"},
                    {"method": "POST",   "path": "/api/finance/transaction",       "description": "Add a transaction", "body": {"type": "withdrawal|deposit", "amount": "number", "description": "string", "category": "string"}},
                ]
            },
            "patterns": {
                "description": "AI-learned check-in patterns",
                "endpoints": [
                    {"method": "GET",    "path": "/api/patterns",                  "description": "List all learned activity patterns"},
                    {"method": "POST",   "path": "/api/patterns/log",              "description": "Log a pattern observation (requires X-API-Key)"},
                    {"method": "POST",   "path": "/api/patterns/reset",            "description": "Reset all learned patterns"},
                ]
            },
        }
    }
    return jsonify(endpoints)
