"""Tool definitions for the AI chat system.

Each tool describes an action the AI can take on behalf of the user.
The AI produces [TOOL: name] {"param": "value"} syntax; chat.py parses
and dispatches to chat_tool_executor.py.
"""

TOOL_DEFINITIONS = [
    # ── Habits ──────────────────────────────────────────────────────────────
    {
        "name": "create_habit",
        "description": "Create a simple habit WITHOUT phases or micro-tasks. Use generate_and_create_habit instead for better habits with progressive phases.",
        "parameters": {
            "name": "string (required)",
            "category": "string — e.g. health, fitness, mindfulness (default: health)",
            "difficulty": "integer 1-5 (default: 1)",
        },
    },
    {
        "name": "generate_and_create_habit",
        "description": (
            "PREFERRED way to create habits. Generates a progressive phased plan with micro-tasks "
            "from a goal description. Always use this unless the user explicitly wants a bare habit."
        ),
        "parameters": {
            "goal": "string (required) — describe what the user wants to achieve",
        },
    },
    {
        "name": "complete_habit",
        "description": "Mark a habit as completed for today",
        "parameters": {
            "habit_id": "integer (required)",
        },
    },
    {
        "name": "delete_habit",
        "description": "Deactivate (soft-delete) a habit so it no longer appears",
        "parameters": {
            "habit_id": "integer (required)",
        },
    },
    # ── Food ────────────────────────────────────────────────────────────────
    {
        "name": "log_food",
        "description": "Log a meal or drink with nutrition info",
        "parameters": {
            "description": "string (required) — what you ate or drank",
            "meal_type": "string — breakfast/lunch/dinner/snack/drink/coffee/smoothie/tea/alcohol/juice/water/meal (default: meal)",
            "calories": "number (optional)",
            "protein_g": "number (optional)",
            "carbs_g": "number (optional)",
            "fat_g": "number (optional)",
        },
    },
    {
        "name": "set_calorie_goal",
        "description": "Set the user's daily calorie goal",
        "parameters": {
            "goal": "number (required) — target calories per day",
        },
    },
    # ── Fasting ─────────────────────────────────────────────────────────────
    {
        "name": "start_fast",
        "description": "Start a new intermittent fast (cancels any active fast first)",
        "parameters": {
            "target_hours": "number — target fasting duration in hours (default: 16)",
            "mood": "integer 1-5 — starting mood (default: 3)",
        },
    },
    {
        "name": "end_fast",
        "description": "End the currently active fast and record its duration",
        "parameters": {
            "mood": "integer 1-5 — ending mood (optional, default: 3)",
        },
    },
    # ── Finance ─────────────────────────────────────────────────────────────
    {
        "name": "log_transaction",
        "description": "Log a financial transaction (spending or income) to the local finance log",
        "parameters": {
            "amount": "number (required)",
            "description": "string (required)",
            "category": "string (optional) — e.g. food, transport, entertainment",
            "type": "string — withdrawal/deposit/transfer (default: withdrawal)",
        },
    },
    {
        "name": "add_budget_rule",
        "description": "Add or update a monthly budget limit for a spending category",
        "parameters": {
            "category": "string (required)",
            "monthly_limit": "number (required) — max spend per month in the user's currency",
        },
    },
    # ── Challenges ──────────────────────────────────────────────────────────
    {
        "name": "create_challenge",
        "description": "Create a new streak/challenge to track",
        "parameters": {
            "name": "string (required)",
            "target_days": "number (optional) — leave blank for open-ended",
            "category": "string (optional, default: general)",
            "start_date": "string YYYY-MM-DD (optional, defaults to today)",
        },
    },
    # ── Discover / Bucket list ───────────────────────────────────────────────
    {
        "name": "add_discovery",
        "description": "Add an item to the bucket list / Discover list",
        "parameters": {
            "title": "string (required)",
            "category": "string — places/skills/experiences/food/creative (default: place)",
            "description": "string (optional)",
            "location": "string (optional)",
        },
    },
    # ── Deep Work ───────────────────────────────────────────────────────────
    {
        "name": "create_dw_project",
        "description": "Create a new local deep work project",
        "parameters": {
            "name": "string (required)",
            "description": "string (optional)",
            "color": "hex color (optional, e.g. #4f80ff)",
        },
    },
    {
        "name": "delete_dw_project",
        "description": "Delete a local deep work project",
        "parameters": {
            "project_id": "integer (required)",
        },
    },
    {
        "name": "list_dw_projects",
        "description": "List all deep work projects with total hours",
        "parameters": {},
    },
    {
        "name": "start_deep_work",
        "description": "Start a deep-work / focus session",
        "parameters": {
            "project_name": "string (optional) — name of the project to work on",
            "project_id": "integer (optional) — ID of existing project",
            "notes": "string (optional) — what you're working on",
        },
    },
    {
        "name": "end_deep_work",
        "description": "End the current deep-work session and record its duration",
        "parameters": {},
    },
    # ── Vikunja (Task Management Integration) ─────────────────────────────
    {
        "name": "list_vikunja_projects",
        "description": "List all projects from the connected Vikunja task manager",
        "parameters": {},
    },
    {
        "name": "list_vikunja_tasks",
        "description": "List tasks from a Vikunja project",
        "parameters": {
            "project_id": "string (required) — Vikunja project ID",
        },
    },
    {
        "name": "create_vikunja_task",
        "description": "Create a new task in Vikunja",
        "parameters": {
            "project_id": "string (required) — Vikunja project ID",
            "title": "string (required) — task title",
            "description": "string (optional) — task details",
            "priority": "integer 0-4 (optional, 0=none, 1=low, 2=medium, 3=high, 4=urgent)",
            "due_date": "string (optional) — ISO date e.g. 2026-03-25",
        },
    },
    {
        "name": "complete_vikunja_task",
        "description": "Mark a Vikunja task as done",
        "parameters": {
            "task_id": "string (required) — Vikunja task ID",
        },
    },
    # ── Mood / Check-in ─────────────────────────────────────────────────────
    {
        "name": "log_mood",
        "description": "Log today's mood and energy level (daily check-in)",
        "parameters": {
            "mood": "integer 1-5 (required)",
            "energy": "integer 1-5 (required)",
            "note": "string (optional)",
        },
    },
    # ── Journal ─────────────────────────────────────────────────────────────
    {
        "name": "log_journal",
        "description": "Create or update a journal entry for a given date",
        "parameters": {
            "date": "YYYY-MM-DD (defaults to today)",
            "mood": "integer 1-5",
            "energy": "integer 1-5",
            "gratitude": "list of up to 3 strings",
            "wins": "list of strings",
            "lessons": "string",
            "content": "freeform text",
            "tags": "list of tag strings",
        },
    },
    # ── Books ────────────────────────────────────────────────────────────────
    {
        "name": "log_book",
        "description": "Add a book or update its status",
        "parameters": {
            "title": "string (required)",
            "author": "string",
            "genre": "string",
            "page_count": "integer",
            "status": "to-read/reading/finished/abandoned",
            "rating": "integer 1-5 (for finished books)",
            "review": "string",
        },
    },
    # ── Wellness ─────────────────────────────────────────────────────────────
    {
        "name": "log_water",
        "description": "Log or remove water intake (glasses). Use negative number to remove.",
        "parameters": {"glasses": "integer (default 1, use -1 to remove a glass)"},
    },
    {
        "name": "log_sleep",
        "description": "Log sleep data",
        "parameters": {
            "date": "YYYY-MM-DD (defaults to today)",
            "bedtime": "HH:MM (e.g. 23:00)",
            "wake_time": "HH:MM (e.g. 07:00)",
            "quality": "integer 1-5",
        },
    },
    # ── Finance — subscriptions & income ────────────────────────────────────
    {
        "name": "add_subscription",
        "description": "Track a recurring subscription (Netflix, Spotify, SaaS tools, etc.)",
        "parameters": {
            "name": "string (required) — name of the service or product",
            "cost": "number (required) — cost per billing period",
            "billing_cycle": "string — monthly/weekly/yearly (default: monthly)",
            "category": "string (optional) — e.g. entertainment, software, fitness",
            "currency": "string (optional, default: USD)",
            "worth_it": "integer 1-5 (optional, default: 3) — subjective value rating",
            "next_billing": "YYYY-MM-DD (optional) — next billing date",
        },
    },
    {
        "name": "log_income",
        "description": "Log income received (salary, freelance, dividends, etc.)",
        "parameters": {
            "source": "string (required) — where the income came from",
            "amount": "number (required) — amount received",
            "date": "YYYY-MM-DD (optional, defaults to today)",
            "recurring": "boolean (optional, default: false) — is this recurring income?",
        },
    },
    # ── Notes ────────────────────────────────────────────────────────────────
    {
        "name": "create_note",
        "description": "Create a quick capture note",
        "parameters": {
            "title": "string (required)",
            "body": "markdown text",
            "tags": "list of strings",
            "folder": "string",
        },
    },
    # ── Contacts CRM ─────────────────────────────────────────────────────────
    {
        "name": "add_contact",
        "description": "Add a contact to your personal CRM",
        "parameters": {
            "name": "string (required)",
            "relationship": "family/friend/colleague/mentor/acquaintance",
            "phone": "string",
            "email": "string",
            "birthday": "YYYY-MM-DD",
            "reach_out_frequency": "weekly/biweekly/monthly/quarterly/yearly",
        },
    },
    {
        "name": "log_interaction",
        "description": "Log that you contacted someone",
        "parameters": {
            "contact_name": "string (required, partial match)",
            "type": "call/text/meeting/coffee/email/other",
            "notes": "string",
        },
    },
]

__all__ = ["TOOL_DEFINITIONS"]
