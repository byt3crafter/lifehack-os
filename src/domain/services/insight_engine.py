"""Smart Insights Engine — pure SQL + Python math, no AI calls required.

Analyses user data across habits, wellness, finance, food, fasting, sleep,
and journaling to surface actionable insights as notifications.

Each insight function returns either a dict or None.  The orchestrator
``generate_insights`` runs all checks, respects per-type cooldowns, and
returns a list of insight dicts ready to be inserted into the notifications
table by the caller.
"""
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# Cooldown guard
# ---------------------------------------------------------------------------

def _insight_on_cooldown(conn, user_id: int, insight_type: str, cooldown_hours: int = 24) -> bool:
    """Return True if this insight type was already generated within the cooldown window."""
    try:
        row = conn.execute(
            "SELECT id FROM notifications WHERE user_id=? AND type=? "
            "AND created_at > datetime('now', ?)",
            (user_id, insight_type, f'-{cooldown_hours} hours'),
        ).fetchone()
        return row is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Individual insight checks
# ---------------------------------------------------------------------------

def _check_budget_alert(conn, user_id: int, today_str: str) -> Optional[dict]:
    """Alert when any budget category is >= 80% of its monthly limit.

    Combines local finance_log entries with Firefly III monthly spending if
    the integration is connected.
    """
    try:
        # Month boundary
        month_start = today_str[:7] + '-01'

        rules = conn.execute(
            "SELECT id, category, monthly_limit FROM finance_rules "
            "WHERE user_id=? AND active=1 AND monthly_limit IS NOT NULL AND monthly_limit > 0",
            (user_id,),
        ).fetchall()

        if not rules:
            return None

        # Local spending this month per category
        local_rows = conn.execute(
            """SELECT category, COALESCE(SUM(amount), 0) AS spent
               FROM finance_log
               WHERE user_id=? AND type='withdrawal'
                 AND date >= ? AND date <= ?
               GROUP BY category""",
            (user_id, month_start, today_str),
        ).fetchall()
        local_by_cat: dict[str, float] = {r['category'].lower(): float(r['spent']) for r in local_rows}

        # Optional Firefly monthly spending
        firefly_by_cat: dict[str, float] = {}
        try:
            from src.infrastructure.services.firefly_service import FireflyService
            ff = FireflyService()
            ff_data = ff.get_monthly_spending(user_id=user_id)
            firefly_by_cat = {k.lower(): v for k, v in ff_data.get('categories', {}).items()}
        except Exception:
            pass

        alerts = []
        for rule in rules:
            cat = rule['category'].lower()
            limit = float(rule['monthly_limit'])
            spent = local_by_cat.get(cat, 0.0) + firefly_by_cat.get(cat, 0.0)
            pct = spent / limit if limit > 0 else 0.0
            if pct >= 0.8:
                alerts.append((rule['category'], spent, limit, pct))

        if not alerts:
            return None

        # Report the worst offender
        alerts.sort(key=lambda x: x[3], reverse=True)
        cat_name, spent, limit, pct = alerts[0]
        pct_int = int(pct * 100)
        return {
            'title': f'Budget alert: {cat_name}',
            'body': (
                f"You've used {pct_int}% of your {cat_name} budget "
                f"(${spent:.0f} of ${limit:.0f}) this month."
            ),
            'icon': '💰',
            'link': '#finance',
        }
    except Exception:
        return None


def _check_habit_pattern(conn, user_id: int, today_str: str) -> Optional[dict]:
    """Detect which weekday has the most habit misses over the last 30 days."""
    try:
        thirty_ago = _days_ago(today_str, 30)

        rows = conn.execute(
            """SELECT strftime('%w', date) AS dow, COUNT(*) AS cnt
               FROM habit_miss_log
               WHERE user_id=? AND date >= ? AND date <= ?
               GROUP BY dow""",
            (user_id, thirty_ago, today_str),
        ).fetchall()

        if not rows:
            return None

        total_misses = sum(r['cnt'] for r in rows)
        worst = max(rows, key=lambda r: r['cnt'])
        worst_cnt = worst['cnt']
        worst_dow = worst['dow']

        # Only report if this day is significantly worse
        if worst_cnt < 3:
            return None
        if total_misses == 0 or (worst_cnt / total_misses) <= 0.5:
            return None

        day_names = {
            '0': 'Sunday', '1': 'Monday', '2': 'Tuesday',
            '3': 'Wednesday', '4': 'Thursday', '5': 'Friday', '6': 'Saturday',
        }
        day_name = day_names.get(str(worst_dow), f'day {worst_dow}')

        return {
            'title': f'Habit pattern: {day_name} struggles',
            'body': (
                f"You miss habits most on {day_name}s — {worst_cnt} misses "
                f"in the last 30 days. Plan ahead for next {day_name}."
            ),
            'icon': '📊',
            'link': '#habits',
        }
    except Exception:
        return None


def _check_sleep_mood_correlation(conn, user_id: int, today_str: str) -> Optional[dict]:
    """Detect if good sleep correlates with better mood over the last 14 days."""
    try:
        fourteen_ago = _days_ago(today_str, 14)

        rows = conn.execute(
            """SELECT sl.hours, dc.mood
               FROM sleep_logs sl
               JOIN daily_checkins dc ON dc.date = sl.date AND dc.user_id = sl.user_id
               WHERE sl.user_id=? AND sl.date >= ? AND sl.date <= ?
                 AND sl.hours IS NOT NULL AND dc.mood IS NOT NULL""",
            (user_id, fourteen_ago, today_str),
        ).fetchall()

        if len(rows) < 4:
            return None

        good_moods = [r['mood'] for r in rows if r['hours'] >= 7]
        bad_moods  = [r['mood'] for r in rows if r['hours'] < 6]

        if len(good_moods) < 2 or len(bad_moods) < 2:
            return None

        avg_good = sum(good_moods) / len(good_moods)
        avg_bad  = sum(bad_moods)  / len(bad_moods)
        diff = avg_good - avg_bad

        if diff < 1.0:
            return None

        return {
            'title': 'Sleep boosts your mood',
            'body': (
                f"Over the last 14 days, you're in a {diff:.1f}-point better mood "
                f"after 7+ hours of sleep (avg {avg_good:.1f}) vs. under 6 hours "
                f"(avg {avg_bad:.1f})."
            ),
            'icon': '😴',
            'link': '#wellness',
        }
    except Exception:
        return None


def _check_food_gap(conn, user_id: int, today_str: str) -> Optional[dict]:
    """Alert when average daily calories over the last 7 days is < 80% of goal."""
    try:
        seven_ago = _days_ago(today_str, 7)

        rows = conn.execute(
            """SELECT date(logged_at) AS day, COALESCE(SUM(calories), 0) AS total
               FROM food_logs
               WHERE user_id=? AND date(logged_at) >= ? AND date(logged_at) <= ?
                 AND calories IS NOT NULL
               GROUP BY day""",
            (user_id, seven_ago, today_str),
        ).fetchall()

        if not rows:
            return None

        daily_avg = sum(r['total'] for r in rows) / len(rows)

        # Per-user calorie goal, fallback to 2000
        goal_row = conn.execute(
            "SELECT value FROM user_settings WHERE user_id=? AND key='daily_calorie_goal'",
            (user_id,),
        ).fetchone()
        goal = float(goal_row['value']) if goal_row else 2000.0

        if goal <= 0 or daily_avg >= goal * 0.8:
            return None

        pct = int((daily_avg / goal) * 100)
        return {
            'title': 'Calorie intake below goal',
            'body': (
                f"Your average daily intake over the last 7 days is {daily_avg:.0f} kcal "
                f"— only {pct}% of your {goal:.0f} kcal goal. Consider logging more meals."
            ),
            'icon': '🍽️',
            'link': '#food',
        }
    except Exception:
        return None


def _check_water_streak(conn, user_id: int, today_str: str) -> Optional[dict]:
    """Positive streak insight (3+ days meeting target) or drop alert (-30%)."""
    try:
        target = 8  # glasses

        # Last 14 days so we can compare two weeks
        fourteen_ago = _days_ago(today_str, 14)
        rows = conn.execute(
            """SELECT date(logged_at) AS day, COALESCE(SUM(glasses), 0) AS total
               FROM water_logs
               WHERE user_id=? AND date(logged_at) >= ? AND date(logged_at) <= ?
               GROUP BY day
               ORDER BY day DESC""",
            (user_id, fourteen_ago, today_str),
        ).fetchall()

        if not rows:
            return None

        by_day = {r['day']: r['total'] for r in rows}

        # Check current consecutive streak (walking backwards from today)
        streak = 0
        check_date = date.fromisoformat(today_str)
        for _ in range(14):
            ds = check_date.isoformat()
            if by_day.get(ds, 0) >= target:
                streak += 1
                check_date = _prev_date(check_date)
            else:
                break

        if streak >= 3:
            return {
                'title': f'{streak}-day hydration streak!',
                'body': (
                    f"You've hit your {target}-glass water goal {streak} days in a row. "
                    "Keep it up!"
                ),
                'icon': '💧',
                'link': '#wellness',
            }

        # Compare this week vs last week averages
        this_week_start = _days_ago(today_str, 7)
        this_week_days = [r for r in rows if r['day'] >= this_week_start]
        last_week_days  = [r for r in rows if r['day'] < this_week_start]

        if not this_week_days or not last_week_days:
            return None

        avg_this = sum(r['total'] for r in this_week_days) / len(this_week_days)
        avg_last = sum(r['total'] for r in last_week_days) / len(last_week_days)

        if avg_last > 0 and avg_this < avg_last * 0.7:
            drop_pct = int((1 - avg_this / avg_last) * 100)
            return {
                'title': 'Water intake dropping',
                'body': (
                    f"Your average water intake dropped {drop_pct}% this week "
                    f"({avg_this:.1f} vs {avg_last:.1f} glasses/day last week)."
                ),
                'icon': '💧',
                'link': '#wellness',
            }

        return None
    except Exception:
        return None


def _check_fasting_optimization(conn, user_id: int, today_str: str) -> Optional[dict]:
    """Detect if fasting durations are longer after good sleep nights."""
    try:
        thirty_ago = _days_ago(today_str, 30)

        rows = conn.execute(
            """SELECT
                 fl.start_at,
                 fl.end_at,
                 sl.hours AS sleep_hours,
                 (julianday(fl.end_at) - julianday(fl.start_at)) * 24.0 AS fast_hours
               FROM fasting_logs fl
               JOIN sleep_logs sl
                 ON date(sl.date) = date(fl.start_at, '-1 day')
                 AND sl.user_id = fl.user_id
               WHERE fl.user_id=? AND fl.status='completed'
                 AND date(fl.start_at) >= ? AND date(fl.start_at) <= ?
                 AND fl.end_at IS NOT NULL
                 AND sl.hours IS NOT NULL""",
            (user_id, thirty_ago, today_str),
        ).fetchall()

        if len(rows) < 4:
            return None

        good_sleep_fasts = [r['fast_hours'] for r in rows if r['sleep_hours'] >= 7]
        bad_sleep_fasts  = [r['fast_hours'] for r in rows if r['sleep_hours'] < 6]

        if len(good_sleep_fasts) < 2 or len(bad_sleep_fasts) < 2:
            return None

        avg_good = sum(good_sleep_fasts) / len(good_sleep_fasts)
        avg_bad  = sum(bad_sleep_fasts)  / len(bad_sleep_fasts)
        diff = avg_good - avg_bad

        if diff < 2.0:
            return None

        return {
            'title': 'Sleep improves your fasts',
            'body': (
                f"You fast {diff:.1f} hours longer when you slept 7+ hours the night before "
                f"(avg {avg_good:.1f}h vs {avg_bad:.1f}h after under 6h sleep)."
            ),
            'icon': '⏱️',
            'link': '#fasting',
        }
    except Exception:
        return None


def _check_spending_trend(conn, user_id: int, today_str: str) -> Optional[dict]:
    """Alert when this week's spending is 30%+ higher than last week's."""
    try:
        # ISO week boundaries: this week = last 7 days, last week = 8–14 days ago
        this_week_start = _days_ago(today_str, 7)
        last_week_start = _days_ago(today_str, 14)
        last_week_end   = _days_ago(today_str, 8)

        def _local_spending(start: str, end: str) -> float:
            row = conn.execute(
                """SELECT COALESCE(SUM(amount), 0) FROM finance_log
                   WHERE user_id=? AND type='withdrawal'
                     AND date >= ? AND date <= ?""",
                (user_id, start, end),
            ).fetchone()
            return float(row[0]) if row else 0.0

        this_total = _local_spending(this_week_start, today_str)
        last_total = _local_spending(last_week_start, last_week_end)

        # Add Firefly data if connected
        try:
            from src.infrastructure.services.firefly_service import FireflyService
            ff = FireflyService()
            ff_txns = ff.get_transactions(days=14, limit=500, user_id=user_id)
            for t in ff_txns:
                if t.get('type') != 'withdrawal':
                    continue
                txn_date = (t.get('date') or '')[:10]
                if txn_date >= this_week_start:
                    this_total += float(t.get('amount', 0))
                elif txn_date >= last_week_start:
                    last_total += float(t.get('amount', 0))
        except Exception:
            pass

        if last_total <= 0 or this_total <= last_total * 1.3:
            return None

        increase_pct = int(((this_total - last_total) / last_total) * 100)
        return {
            'title': 'Spending up this week',
            'body': (
                f"You've spent ${this_total:.0f} this week — {increase_pct}% more than last "
                f"week (${last_total:.0f}). Review your recent transactions."
            ),
            'icon': '📈',
            'link': '#finance',
        }
    except Exception:
        return None


def _check_journal_reminder(conn, user_id: int, today_str: str) -> Optional[dict]:
    """Remind the user to journal if they haven't in 3+ days.

    Also mentions a declining mood trend if the last 3 check-ins trended down.
    """
    try:
        latest_row = conn.execute(
            "SELECT date FROM journal_entries WHERE user_id=? ORDER BY date DESC LIMIT 1",
            (user_id,),
        ).fetchone()

        if not latest_row:
            return None  # Never journaled — let onboarding handle it

        last_date = date.fromisoformat(latest_row['date'])
        today = date.fromisoformat(today_str)
        days_since = (today - last_date).days

        if days_since < 3:
            return None

        # Check for declining mood in last 3 check-ins
        mood_rows = conn.execute(
            """SELECT mood FROM daily_checkins
               WHERE user_id=? ORDER BY date DESC LIMIT 3""",
            (user_id,),
        ).fetchall()

        mood_note = ''
        if len(mood_rows) == 3:
            moods = [r['mood'] for r in mood_rows]
            # moods[0] = most recent; declining means each value is < the one before it
            if moods[0] < moods[1] < moods[2]:
                mood_note = " Your mood has been declining lately — journaling can help."

        return {
            'title': "Journal check-in",
            'body': (
                f"You haven't journaled in {days_since} days.{mood_note} "
                "A few minutes of reflection can improve clarity and mood."
            ),
            'icon': '📝',
            'link': '#journal',
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def generate_insights(conn, user_id: int) -> list[dict]:
    """Run all insight checks for a user and return insertable notification dicts.

    Each dict contains: type, title, body, icon, link.
    Cooldowns are enforced per insight type so they don't spam the user.
    """
    today_str = date.today().isoformat()
    results: list[dict] = []

    checks = [
        (_check_budget_alert,             24),
        (_check_habit_pattern,           168),
        (_check_sleep_mood_correlation,  168),
        (_check_food_gap,                 24),
        (_check_water_streak,             24),
        (_check_fasting_optimization,    168),
        (_check_spending_trend,          168),
        (_check_journal_reminder,         72),
    ]

    for check_fn, cooldown in checks:
        insight_type = 'insight_' + check_fn.__name__.replace('_check_', '')
        if _insight_on_cooldown(conn, user_id, insight_type, cooldown):
            continue
        try:
            result = check_fn(conn, user_id, today_str)
            if result:
                result['type'] = insight_type
                results.append(result)
        except Exception:
            pass  # never crash on a single insight

    return results


# ---------------------------------------------------------------------------
# Private date helpers
# ---------------------------------------------------------------------------

def _days_ago(today_str: str, days: int) -> str:
    """Return ISO date string ``days`` before ``today_str``."""
    d = date.fromisoformat(today_str)
    from datetime import timedelta
    return (d - timedelta(days=days)).isoformat()


def _prev_date(d: date) -> date:
    """Return the date one day before ``d``."""
    from datetime import timedelta
    return d - timedelta(days=1)
