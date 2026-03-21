"""Chat context assembly — dumps relevant data from ALL tables for AI reasoning."""
import json
from datetime import date, datetime, timedelta

from src.infrastructure.database.user_scope import get_user_setting


def _rows_to_dicts(rows) -> list:
    """Convert sqlite3.Row objects to plain dicts."""
    return [dict(r) for r in rows] if rows else []


def _safe_query(conn, sql, params=()) -> list:
    """Run a query and return list of dicts, empty list on error."""
    try:
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    except Exception:
        return []


def assemble_context(conn, user_id: int) -> dict:
    """Dump relevant data from ALL modules so the AI can reason about anything."""

    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    context = {}

    # User profile (for AI personalization)
    context['user_profile'] = _safe_query(
        conn,
        """SELECT u.display_name, up.bio, up.age, up.timezone,
                  up.health_goals, up.fitness_level, up.dietary_preferences,
                  up.work_type, up.work_hours,
                  up.height_cm, up.weight_kg, up.gender,
                  up.target_weight_kg, up.preferred_name
           FROM users u
           LEFT JOIN user_profiles up ON up.user_id = u.id
           WHERE u.id = ?""",
        (user_id,),
    )

    # User stats
    context['user_stats'] = _safe_query(
        conn, "SELECT * FROM user_stats WHERE user_id = ?", (user_id,)
    )

    # Today's mood/energy
    context['mood_today'] = _safe_query(
        conn,
        "SELECT mood, energy, improvement_note FROM daily_checkins WHERE user_id = ? AND date = ?",
        (user_id, today),
    )

    # Habits (ALL — active and inactive, AI needs full history)
    context['habits'] = _safe_query(conn, """
        SELECT h.id, h.name, h.category, h.difficulty, h.active,
               hs.strength, hs.peak_strength, hs.total_completions, hs.total_misses,
               hp.name as current_phase, hp.phase_number
        FROM habits h
        LEFT JOIN habit_strength hs ON hs.habit_id = h.id
        LEFT JOIN habit_phases hp ON hp.habit_id = h.id AND hp.is_current = 1
        WHERE h.user_id = ?
        ORDER BY h.active DESC, h.name
    """, (user_id,))

    # Today's habit completions
    context['habit_completions_today'] = _safe_query(
        conn,
        """SELECT hc.habit_id, h.name, h.active
           FROM habit_completions hc
           JOIN habits h ON h.id = hc.habit_id
           WHERE hc.user_id = ? AND date(hc.completed_at) = ?""",
        (user_id, today),
    )

    # Food today (full details)
    context['food_today'] = _safe_query(
        conn,
        """SELECT meal_type, description, calories, protein_g, carbs_g, fat_g,
                  notes, rating, mood_after, logged_at
           FROM food_logs
           WHERE user_id = ? AND date(logged_at) = ?
           ORDER BY logged_at""",
        (user_id, today),
    )

    # Calorie goal — user_settings first, then app_settings fallback
    context['calorie_goal'] = int(get_user_setting(conn, user_id, 'daily_calorie_goal', '2000'))

    # Fasting
    context['active_fast'] = _safe_query(
        conn,
        "SELECT start_at, target_hours, status FROM fasting_logs WHERE user_id = ? AND status = 'active' ORDER BY start_at DESC LIMIT 1",
        (user_id,),
    )

    # Recent fasting history
    context['fasting_history'] = _safe_query(
        conn,
        "SELECT start_at, end_at, target_hours, status FROM fasting_logs WHERE user_id = ? AND status = 'completed' ORDER BY end_at DESC LIMIT 5",
        (user_id,),
    )

    # Challenges
    context['active_challenges'] = _safe_query(
        conn,
        "SELECT name, category, target_days, start_date, check_in_frequency FROM challenges WHERE user_id = ? AND status = 'active'",
        (user_id,),
    )

    # Deep work today
    context['deep_work_today'] = _safe_query(
        conn,
        """SELECT dw.duration_minutes, dw.notes, p.name as project
           FROM deep_work_sessions dw
           LEFT JOIN projects p ON p.id = dw.project_id
           WHERE dw.user_id = ? AND date(dw.started_at) = ?""",
        (user_id, today),
    )

    # Vikunja integration — projects and recent tasks
    try:
        from src.infrastructure.plugins import plugin_registry
        stored = plugin_registry.get_config("vikunja", user_id)
        if stored.get("enabled"):
            plugin = plugin_registry.get("vikunja")
            provider = plugin.get_provider(stored.get("config", {}))
            vk_projects = provider.get_projects()
            context['vikunja_projects'] = [
                {"id": p.id, "title": p.title, "task_count": p.task_count}
                for p in vk_projects
            ]
    except Exception:
        pass

    # Finance — subscriptions (active)
    context['subscriptions'] = _safe_query(conn,
        "SELECT name, cost, billing_cycle, category, worth_it FROM subscriptions WHERE user_id = ? AND active = 1",
        (user_id,))

    # Finance — income this month
    context['income_this_month'] = _safe_query(conn,
        "SELECT source, amount, date FROM income_entries WHERE user_id = ? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')",
        (user_id,))

    # Finance — budget rules
    context['budget_rules'] = _safe_query(
        conn,
        "SELECT category, monthly_limit, description FROM finance_rules WHERE user_id = ? AND active = 1",
        (user_id,),
    )

    # Finance — this month's spending (local log)
    context['spending_this_month'] = _safe_query(
        conn,
        """SELECT category, SUM(amount) as total
           FROM finance_log
           WHERE user_id = ? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
           GROUP BY category""",
        (user_id,),
    )

    # Finance — recent transactions (local log)
    context['recent_transactions'] = _safe_query(
        conn,
        """SELECT date, amount, description, category, type
           FROM finance_log
           WHERE user_id = ?
           ORDER BY date DESC LIMIT 15""",
        (user_id,),
    )

    # Water intake today
    context['water_today'] = _safe_query(conn,
        "SELECT COALESCE(SUM(glasses), 0) as total FROM water_logs WHERE user_id = ? AND date(logged_at) = ?",
        (user_id, today))

    # Sleep last night
    context['sleep_last'] = _safe_query(conn,
        "SELECT date, bedtime, wake_time, hours, quality FROM sleep_logs WHERE user_id = ? ORDER BY date DESC LIMIT 1",
        (user_id,))

    # Discover items
    context['discover_items'] = _safe_query(
        conn,
        "SELECT title, category, status, location, rating, completed_at FROM wishlist WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (user_id,),
    )

    # Recent AI insights
    context['ai_insights'] = _safe_query(
        conn,
        "SELECT title, content, insight_type FROM ai_insights WHERE user_id = ? AND dismissed = 0 ORDER BY created_at DESC LIMIT 3",
        (user_id,),
    )

    # Walk/movement this week
    context['walks_this_week'] = _safe_query(
        conn,
        """SELECT logged_at, distance_km, duration_minutes, mood_before, mood_after
           FROM walk_logs
           WHERE user_id = ? AND date(logged_at) >= ?
           ORDER BY logged_at DESC""",
        (user_id, week_ago),
    )

    # Replacement/redirect actions (sobriety)
    context['replacement_actions_today'] = _safe_query(
        conn,
        """SELECT ra.name, rl.urge_level, rl.notes
           FROM replacement_logs rl
           JOIN replacement_actions ra ON ra.id = rl.action_id
           WHERE rl.user_id = ? AND date(rl.logged_at) = ?""",
        (user_id, today),
    )

    # Journal — today and recent
    context['journal_today'] = _safe_query(conn,
        "SELECT date, mood, energy, gratitude_json, wins_json, lessons, content FROM journal_entries WHERE user_id = ? AND date = ?",
        (user_id, today))

    context['journal_recent'] = _safe_query(conn,
        "SELECT date, mood, energy, gratitude_json, wins_json, tags_json FROM journal_entries WHERE user_id = ? ORDER BY date DESC LIMIT 7",
        (user_id,))

    # Books currently reading
    context['books_reading'] = _safe_query(conn,
        "SELECT title, author, current_page, page_count, genre FROM books WHERE user_id = ? AND status = 'reading'",
        (user_id,))

    context['books_finished_recent'] = _safe_query(conn,
        "SELECT title, author, rating, finished_at FROM books WHERE user_id = ? AND status = 'finished' ORDER BY finished_at DESC LIMIT 5",
        (user_id,))

    # Pinned notes
    context['pinned_notes'] = _safe_query(conn,
        "SELECT title, body, tags_json, folder FROM notes WHERE user_id = ? AND pinned = 1 AND archived = 0 LIMIT 10",
        (user_id,))

    # Contacts CRM — overdue contacts and upcoming birthdays
    context['contacts_overdue'] = _safe_query(conn,
        """SELECT name, relationship, last_contact_date, reach_out_frequency
           FROM contacts WHERE user_id = ? AND last_contact_date IS NOT NULL
           ORDER BY last_contact_date ASC LIMIT 5""",
        (user_id,))

    context['upcoming_birthdays'] = _safe_query(conn,
        """SELECT name, birthday FROM contacts
           WHERE user_id = ? AND birthday IS NOT NULL
           AND (CAST(strftime('%j', birthday) AS INTEGER) - CAST(strftime('%j', 'now') AS INTEGER) + 366) % 366 <= 30
           ORDER BY (CAST(strftime('%j', birthday) AS INTEGER) - CAST(strftime('%j', 'now') AS INTEGER) + 366) % 366
           LIMIT 5""",
        (user_id,))

    # Firefly III data (if connected)
    try:
        from src.infrastructure.plugins import plugin_registry
        ff_stored = plugin_registry.get_config('firefly', user_id)
        if ff_stored.get('enabled'):
            ff_config = ff_stored.get('config', {})
            ff_plugin = plugin_registry.get('firefly')
            base_url = ff_plugin._base_url(ff_config.get('api_url', ''))
            token = ff_config.get('api_token', '')
            if base_url and token:
                import requests
                headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
                # Accounts
                try:
                    r = requests.get(f'{base_url}/api/v1/accounts?type=asset', headers=headers, timeout=8)
                    if r.status_code == 200:
                        context['firefly_accounts'] = [
                            {'name': a['attributes']['name'],
                             'balance': a['attributes'].get('current_balance'),
                             'currency': a['attributes'].get('currency_code', '')}
                            for a in r.json().get('data', [])
                        ]
                except Exception:
                    pass
                # Recent transactions
                try:
                    r = requests.get(f'{base_url}/api/v1/transactions?limit=20', headers=headers, timeout=8)
                    if r.status_code == 200:
                        txns = []
                        for t in r.json().get('data', [])[:20]:
                            tx = t.get('attributes', {}).get('transactions', [{}])[0]
                            txns.append({
                                'date': (tx.get('date') or '')[:10],
                                'description': tx.get('description', ''),
                                'amount': tx.get('amount'),
                                'type': tx.get('type', ''),
                                'category': tx.get('category_name', ''),
                                'source': tx.get('source_name', ''),
                                'destination': tx.get('destination_name', ''),
                            })
                        context['firefly_transactions'] = txns
                except Exception:
                    pass
                # Budgets
                try:
                    r = requests.get(f'{base_url}/api/v1/budgets', headers=headers, timeout=8)
                    if r.status_code == 200:
                        context['firefly_budgets'] = [
                            {'name': b['attributes']['name']}
                            for b in r.json().get('data', [])
                        ]
                except Exception:
                    pass
    except Exception:
        pass

    return context


def build_system_prompt(context: dict, tools: list | None = None) -> str:
    """Build the AI system prompt with full module data and optional tool list."""

    # --- Resolve user name for personalised addressing ---
    user_name = None
    profile_list = context.get('user_profile')
    if profile_list:
        profile = profile_list[0] if isinstance(profile_list, list) else profile_list
        user_name = (profile.get('preferred_name') or '').strip() or \
                    (profile.get('display_name') or '').strip() or None

    name_directive = ""
    if user_name:
        name_directive = f'- Address the user as \'{user_name}\'. Use their name naturally.'

    # --- Build a concise user profile summary ---
    profile_summary_lines = []
    if profile_list:
        profile = profile_list[0] if isinstance(profile_list, list) else profile_list
        if profile.get('age'):
            profile_summary_lines.append(f"Age: {profile['age']}")
        if profile.get('gender'):
            profile_summary_lines.append(f"Gender: {profile['gender']}")
        if profile.get('height_cm'):
            profile_summary_lines.append(f"Height: {profile['height_cm']} cm")
        if profile.get('weight_kg'):
            profile_summary_lines.append(f"Weight: {profile['weight_kg']} kg")
            if profile.get('height_cm') and profile['height_cm'] > 0:
                bmi = round(profile['weight_kg'] / (profile['height_cm'] / 100) ** 2, 1)
                profile_summary_lines.append(f"BMI: {bmi}")
        if profile.get('target_weight_kg'):
            profile_summary_lines.append(f"Target weight: {profile['target_weight_kg']} kg")
        if profile.get('fitness_level'):
            profile_summary_lines.append(f"Fitness level: {profile['fitness_level']}")
        if profile.get('health_goals'):
            profile_summary_lines.append(f"Health goals: {profile['health_goals']}")
        if profile.get('dietary_preferences'):
            profile_summary_lines.append(f"Dietary preferences: {profile['dietary_preferences']}")
        if profile.get('work_type'):
            profile_summary_lines.append(f"Work type: {profile['work_type']}")
        if profile.get('timezone'):
            profile_summary_lines.append(f"Timezone: {profile['timezone']}")

    profile_summary_section = ""
    if profile_summary_lines:
        profile_summary_section = "\n## User Profile Summary\n" + "\n".join(
            f"- {line}" for line in profile_summary_lines
        ) + "\n"

    tools_section = ""
    if tools:
        tool_lines = []
        for t in tools:
            param_keys = ", ".join(t.get("parameters", {}).keys())
            tool_lines.append(f"- {t['name']}({param_keys}) — {t['description']}")
        tools_text = "\n".join(tool_lines)
        tools_section = f"""

## Tools You Can Use
When the user asks you to DO something (create, log, start, add, delete, set), respond with
a tool call on its own line using this exact format:

[TOOL: tool_name] {{"param": "value"}}

Available tools:
{tools_text}

Rules for tool use:
- Only call a tool when the user explicitly asks you to take an action.
- For questions, advice, or analysis — just answer; do NOT call tools.
- You may call multiple tools in one response — put each on its own line.
- After the tool results are fed back to you, summarise what happened in 1-2 sentences.
- Never invent habit_id or challenge_id values. Look them up in the context data above.
- If a required parameter is missing, ask the user before calling the tool.
"""

    return f"""You are the user's personal life advisor inside LifeHack OS. You have FULL access to ALL their data.

## Your Personality
- Direct and honest. No fluff.
- Strict with finances — challenge unnecessary spending.
- Encouraging with habits — celebrate progress, push through dips.
- Data-driven — cite actual numbers from the data below.
- Proactive — suggest actions, don't just answer.
- Keep responses concise (2-4 sentences) unless asked for detail.
{name_directive}
{profile_summary_section}
## The User's Complete Data (live from database)
{json.dumps(context, indent=2, default=str)}

## Rules
- NEVER make up data. Only reference what's in the data above.
- For finance: always check actual balances and budgets before advising.
- For food: reference actual meals logged, not generic advice.
- For habits: reference actual strength percentages and phase progress.
- If data is empty for a module, say "I don't see any data for that yet."
- Use the user's actual currency from Firefly (look at the accounts).
- Be a strict but caring advisor — like a friend who won't let you waste money or skip workouts.

## Rich Visual Formatting
When presenting data, use these special blocks to render visual elements in the chat. Don't use them for simple answers — only when showing data, stats, or trends.

### Markdown Tables
Use for lists of items (meals logged, transactions, tasks, habits, contacts):
| Meal | Calories | Protein |
|------|----------|---------|
| Breakfast | 450 | 32g |
| Lunch | 680 | 45g |

### Metric Cards
Use ```metrics blocks for summary dashboards and key numbers. Format: `Label: Value (delta)` — one per line:
```metrics
Calories: 1,847 (+12%)
Protein: 142g
Water: 6/8 glasses
Streak: 12 days
```

### Progress Bars
Use ```progress blocks for goal tracking. Format: `Label: current/total` or `Label: percentage`:
```progress
Habits completed: 5/8
Calorie goal: 1847/2200
Water intake: 6/8
Fasting: 14/16
```

### Charts
Use ```chart blocks with Chart.js config JSON for trends and comparisons. Use dark theme colors (background #141416, text #f0f0f2, muted #9898a6, accent #4f80ff, purple #8b5cf6, green #22c55e, red #ef4444, yellow #eab308, grid #2a2a2e):
```chart
{{"type":"bar","data":{{"labels":["Mon","Tue","Wed","Thu","Fri"],"datasets":[{{"label":"Calories","data":[2100,1800,1950,2200,1750],"backgroundColor":"rgba(79,128,255,0.6)","borderColor":"#4f80ff","borderWidth":1}}]}},"options":{{"plugins":{{"legend":{{"labels":{{"color":"#f0f0f2"}}}}}},"scales":{{"y":{{"ticks":{{"color":"#9898a6"}},"grid":{{"color":"#2a2a2e"}}}},"x":{{"ticks":{{"color":"#9898a6"}},"grid":{{"color":"#2a2a2e"}}}}}}}}}}
```

### When to use each:
- **Tables**: Lists of items with multiple columns
- **Metrics**: Daily overview, quick stats, key numbers at a glance
- **Progress**: Goal completion, streaks, anything with a target
- **Charts**: Trends over days/weeks (calories, sleep, spending, habits)
- Combine formats in one response (e.g., metrics + chart + table)
- For simple questions, just answer in plain text
- Chart config must be valid JSON — double-check brackets
{tools_section}"""
