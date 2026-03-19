"""Chat context assembly — dumps relevant data from ALL tables for AI reasoning."""
import json
from datetime import date, datetime, timedelta


def _rows_to_dicts(rows) -> list:
    """Convert sqlite3.Row objects to plain dicts."""
    return [dict(r) for r in rows] if rows else []


def _safe_query(conn, sql, params=()) -> list:
    """Run a query and return list of dicts, empty list on error."""
    try:
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    except Exception:
        return []


def assemble_context(conn) -> dict:
    """Dump relevant data from ALL modules so the AI can reason about anything."""

    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    context = {}

    # User stats
    context['user_stats'] = _safe_query(conn, "SELECT * FROM user_stats WHERE id = 1")

    # Today's mood/energy
    context['mood_today'] = _safe_query(conn, "SELECT mood, energy, improvement_note FROM daily_checkins WHERE date = ?", (today,))

    # Habits (ALL — active and inactive, AI needs full history)
    context['habits'] = _safe_query(conn, """
        SELECT h.id, h.name, h.category, h.difficulty, h.active,
               hs.strength, hs.peak_strength, hs.total_completions, hs.total_misses,
               hp.name as current_phase, hp.phase_number
        FROM habits h
        LEFT JOIN habit_strength hs ON hs.habit_id = h.id
        LEFT JOIN habit_phases hp ON hp.habit_id = h.id AND hp.is_current = 1
        ORDER BY h.active DESC, h.name
    """)

    # Today's habit completions
    context['habit_completions_today'] = _safe_query(conn,
        "SELECT hc.habit_id, h.name, h.active FROM habit_completions hc JOIN habits h ON h.id = hc.habit_id WHERE date(hc.completed_at) = ?",
        (today,))

    # Food today (full details)
    context['food_today'] = _safe_query(conn,
        "SELECT meal_type, description, calories, protein_g, carbs_g, fat_g, logged_at FROM food_logs WHERE date(logged_at) = ? ORDER BY logged_at",
        (today,))

    # Calorie goal
    goal = _safe_query(conn, "SELECT value FROM app_settings WHERE key = 'daily_calorie_goal'")
    context['calorie_goal'] = int(goal[0]['value']) if goal else 2000

    # Fasting
    context['active_fast'] = _safe_query(conn,
        "SELECT start_at, target_hours, status FROM fasting_logs WHERE status = 'active' ORDER BY start_at DESC LIMIT 1")

    # Recent fasting history
    context['fasting_history'] = _safe_query(conn,
        "SELECT start_at, end_at, target_hours, status FROM fasting_logs WHERE status = 'completed' ORDER BY end_at DESC LIMIT 5")

    # Challenges
    context['active_challenges'] = _safe_query(conn,
        "SELECT name, category, target_days, start_date, check_in_frequency FROM challenges WHERE status = 'active'")

    # Deep work today
    context['deep_work_today'] = _safe_query(conn,
        "SELECT dw.duration_minutes, dw.notes, p.name as project FROM deep_work_sessions dw LEFT JOIN projects p ON p.id = dw.project_id WHERE date(dw.started_at) = ?",
        (today,))

    # Finance — budget rules
    context['budget_rules'] = _safe_query(conn,
        "SELECT category, monthly_limit, description FROM finance_rules WHERE active = 1")

    # Finance — this month's spending (local log)
    context['spending_this_month'] = _safe_query(conn,
        "SELECT category, SUM(amount) as total FROM finance_log WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now') GROUP BY category")

    # Finance — recent transactions (local log)
    context['recent_transactions'] = _safe_query(conn,
        "SELECT date, amount, description, category, type FROM finance_log ORDER BY date DESC LIMIT 15")

    # Discover items
    context['discover_items'] = _safe_query(conn,
        "SELECT title, category, status, location, rating, completed_at FROM wishlist ORDER BY created_at DESC LIMIT 10")

    # Recent AI insights
    context['ai_insights'] = _safe_query(conn,
        "SELECT title, content, insight_type FROM ai_insights WHERE dismissed = 0 ORDER BY created_at DESC LIMIT 3")

    # Walk/movement this week
    context['walks_this_week'] = _safe_query(conn,
        "SELECT logged_at, distance_km, duration_minutes, mood_before, mood_after FROM walk_logs WHERE date(logged_at) >= ? ORDER BY logged_at DESC",
        (week_ago,))

    # Replacement/redirect actions (sobriety)
    context['replacement_actions_today'] = _safe_query(conn,
        "SELECT ra.name, rl.urge_level, rl.notes FROM replacement_logs rl JOIN replacement_actions ra ON ra.id = rl.action_id WHERE date(rl.logged_at) = ?",
        (today,))

    # Firefly III data (if connected)
    try:
        from src.infrastructure.plugins import plugin_registry
        ff_stored = plugin_registry.get_config('firefly')
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


def build_system_prompt(context: dict) -> str:
    """Build the AI system prompt with full module data."""
    return f"""You are the user's personal life advisor inside LifeHack OS. You have FULL access to ALL their data.

## Your Personality
- Direct and honest. No fluff.
- Strict with finances — challenge unnecessary spending.
- Encouraging with habits — celebrate progress, push through dips.
- Data-driven — cite actual numbers from the data below.
- Proactive — suggest actions, don't just answer.
- Keep responses concise (2-4 sentences) unless asked for detail.

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
"""
