"""Chat context assembly — gathers live data from all modules into a single dict."""
import json
from datetime import date, datetime
from typing import Optional


def assemble_context(conn) -> dict:
    """Gather current state from ALL modules into a single context dict."""

    context: dict = {}
    today = date.today().isoformat()

    # 1. Stats & XP
    try:
        stats = conn.execute("SELECT * FROM user_stats WHERE id = 1").fetchone()
        if stats:
            context['xp'] = {'total': stats['total_xp'], 'level': stats['level']}
        else:
            context['xp'] = {'total': 0, 'level': 1}
    except Exception:
        context['xp'] = {'total': 0, 'level': 1}

    # 2. Mood
    try:
        mood = conn.execute(
            "SELECT mood, energy FROM daily_checkins WHERE date = ?", (today,)
        ).fetchone()
        context['mood'] = {
            'mood': mood['mood'] if mood else None,
            'energy': mood['energy'] if mood else None,
        }
    except Exception:
        context['mood'] = {'mood': None, 'energy': None}

    # 3. Habits
    try:
        habits = conn.execute("SELECT * FROM habits WHERE active = 1").fetchall()
        completions = conn.execute(
            "SELECT habit_id FROM habit_completions WHERE date(completed_at) = ?", (today,)
        ).fetchall()
        completed_ids = {r['habit_id'] for r in completions}
        habit_list = []
        for h in habits:
            strength = conn.execute(
                "SELECT strength FROM habit_strength WHERE habit_id = ?", (h['id'],)
            ).fetchone()
            habit_list.append({
                'name': h['name'],
                'category': h['category'],
                'completed_today': h['id'] in completed_ids,
                'strength': round(strength['strength'], 1) if strength else 0,
            })
        context['habits'] = {
            'total': len(habits),
            'completed_today': len(completed_ids),
            'list': habit_list,
        }
    except Exception:
        context['habits'] = {'total': 0, 'completed_today': 0, 'list': []}

    # 4. Food
    try:
        food = conn.execute(
            "SELECT COUNT(*) as count, COALESCE(SUM(calories),0) as cals "
            "FROM food_logs WHERE date(logged_at) = ?",
            (today,),
        ).fetchone()
        goal_row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'daily_calorie_goal'"
        ).fetchone()
        calorie_goal = int(goal_row['value']) if goal_row else 2000
        # Get actual meal descriptions
        meals = conn.execute(
            "SELECT meal_type, description, calories, protein_g, carbs_g, fat_g FROM food_logs WHERE date(logged_at) = ? ORDER BY logged_at",
            (today,),
        ).fetchall()
        meal_list = [
            {'type': m['meal_type'], 'description': m['description'],
             'calories': m['calories'], 'protein': m['protein_g'], 'carbs': m['carbs_g'], 'fat': m['fat_g']}
            for m in meals
        ]
        context['food'] = {
            'meals_today': food['count'],
            'calories_today': food['cals'],
            'calorie_goal': calorie_goal,
            'meals': meal_list,
        }
    except Exception:
        context['food'] = {'meals_today': 0, 'calories_today': 0, 'calorie_goal': 2000}

    # 5. Fasting
    try:
        fast = conn.execute(
            "SELECT * FROM fasting_logs WHERE status = 'active' ORDER BY start_at DESC LIMIT 1"
        ).fetchone()
        if fast:
            start_dt = datetime.fromisoformat(fast['start_at'])
            hours = (datetime.now() - start_dt).total_seconds() / 3600
            context['fasting'] = {
                'active': True,
                'hours_elapsed': round(hours, 1),
                'target_hours': fast['target_hours'],
            }
        else:
            context['fasting'] = {'active': False}
    except Exception:
        context['fasting'] = {'active': False}

    # 6. Challenges
    try:
        challenges = conn.execute(
            "SELECT name, target_days, start_date FROM challenges WHERE status = 'active'"
        ).fetchall()
        context['challenges'] = [
            {
                'name': c['name'],
                'target_days': c['target_days'],
                'days_in': (date.today() - date.fromisoformat(c['start_date'])).days,
            }
            for c in challenges
        ]
    except Exception:
        context['challenges'] = []

    # 7. Deep Work
    try:
        dw = conn.execute(
            "SELECT COALESCE(SUM(duration_minutes),0) as mins "
            "FROM deep_work_sessions WHERE date(started_at) = ?",
            (today,),
        ).fetchone()
        context['deep_work'] = {'minutes_today': dw['mins']}
    except Exception:
        context['deep_work'] = {'minutes_today': 0}

    # 8. Finance (Firefly III if connected, otherwise local finance_log)
    try:
        from src.infrastructure.plugins import plugin_registry
        ff_config = plugin_registry.get_config('firefly')
        if ff_config.get('enabled'):
            from src.infrastructure.plugins.firefly_plugin import FireflyPlugin
            ff_cfg = ff_config.get('config', {})
            base_url = FireflyPlugin._base_url(ff_cfg.get('api_url', ''))
            token = ff_cfg.get('api_token', '')
            if base_url and token:
                import requests as _requests
                headers = {
                    'Authorization': f'Bearer {token}',
                    'Accept': 'application/json',
                }
                # Asset accounts
                try:
                    r = _requests.get(
                        f'{base_url}/api/v1/accounts?type=asset',
                        headers=headers,
                        timeout=10,
                    )
                    if r.status_code == 200:
                        accounts = []
                        for a in r.json().get('data', []):
                            attrs = a.get('attributes', {})
                            accounts.append({
                                'name': attrs.get('name', ''),
                                'balance': float(attrs.get('current_balance', 0)),
                                'currency': attrs.get('currency_code', 'USD'),
                            })
                        context['finance'] = {'accounts': accounts, 'source': 'firefly'}
                except Exception:
                    pass

                # Recent withdrawals
                try:
                    r = _requests.get(
                        f'{base_url}/api/v1/transactions?limit=10&type=withdrawal',
                        headers=headers,
                        timeout=10,
                    )
                    if r.status_code == 200:
                        txns = []
                        for t in r.json().get('data', [])[:10]:
                            attrs = t.get('attributes', {})
                            tx = attrs.get('transactions', [{}])[0]
                            txns.append({
                                'description': tx.get('description', ''),
                                'amount': float(tx.get('amount', 0)),
                                'category': tx.get('category_name', ''),
                                'date': (tx.get('date') or '')[:10],
                            })
                        context.setdefault('finance', {})['recent_transactions'] = txns
                        context['finance'].setdefault('source', 'firefly')
                except Exception:
                    pass
    except Exception:
        pass

    # Fallback: local finance_log
    if 'finance' not in context:
        try:
            local_spent = conn.execute(
                "SELECT COALESCE(SUM(amount),0) as total FROM finance_log "
                "WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"
            ).fetchone()
            context['finance'] = {
                'spent_this_month': local_spent['total'],
                'source': 'local',
            }
        except Exception:
            context['finance'] = {'source': 'none'}

    # 9. Active budget rules
    try:
        rules = conn.execute(
            "SELECT category, monthly_limit FROM finance_rules WHERE active = 1"
        ).fetchall()
        context['budget_rules'] = [
            {'category': r['category'], 'limit': r['monthly_limit']} for r in rules
        ]
    except Exception:
        context['budget_rules'] = []

    return context


def build_system_prompt(context: dict) -> str:
    """Build the AI system prompt with all module context injected."""
    return f"""You are the user's personal life advisor inside LifeHack OS. You have access to ALL their data across every module.

## Your Personality
- Direct and honest. No fluff, no sugarcoating.
- Strict with finances — challenge unnecessary spending.
- Encouraging with habits — celebrate progress, push through dips.
- Data-driven — always cite the user's actual numbers.
- Proactive — suggest actions, don't just answer questions.

## Current State (live data)
{json.dumps(context, indent=2, default=str)}

## Rules
- When asked about money: always check their actual balance and budget rules before advising.
- When asked about food: check calories today vs goal, active fasting, and eating habits.
- When asked about habits: reference their strength percentages and active phases.
- When they want to buy something: compare against budget rules and current spending.
- If they're struggling (low mood, low energy, broken streaks): be empathetic but push them forward.
- Never make up data. Only use what's in the Current State above.
- Keep responses concise — 2-3 sentences unless they ask for detail.
- Use their actual currency from Firefly (not always USD).
"""
