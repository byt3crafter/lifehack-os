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
        "description": "Log a meal or food entry with optional nutrition data",
        "parameters": {
            "description": "string (required) — what was eaten",
            "meal_type": "string — breakfast/lunch/dinner/snack/meal (default: meal)",
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
        "name": "start_deep_work",
        "description": "Start a deep-work / focus session (ends any active session first)",
        "parameters": {
            "project_id": "integer (optional) — link to a project",
            "notes": "string (optional) — what you're working on",
        },
    },
    {
        "name": "end_deep_work",
        "description": "End the current deep-work session and record its duration",
        "parameters": {},
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
]

__all__ = ["TOOL_DEFINITIONS"]
