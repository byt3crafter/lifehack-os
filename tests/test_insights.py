"""Unit tests for the Smart Insights Engine.

Each test is independent and uses the test_conn fixture for a fresh in-memory DB.
No AI calls are made — the engine is pure SQL + Python math.
"""
import pytest
from datetime import date, timedelta

from src.domain.services.insight_engine import (
    generate_insights,
    _check_budget_alert,
    _check_habit_pattern,
    _check_sleep_mood_correlation,
    _check_food_gap,
    _check_water_streak,
    _check_fasting_optimization,
    _check_spending_trend,
    _check_journal_reminder,
    _insight_on_cooldown,
)

TODAY = date.today().isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_user(conn) -> int:
    """Return the id of the first user, creating one if the DB is empty.

    test_conn provides the schema but no users.  Tests that don't go through
    the Flask app (auth_client) must call this instead of querying users directly.
    """
    row = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
    if row:
        return row["id"]

    from werkzeug.security import generate_password_hash
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, display_name, is_admin) "
        "VALUES ('testuser', ?, 'Test User', 1)",
        (generate_password_hash("testpass"),),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.execute("INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)", (user_id,))
    conn.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user_id,))
    conn.commit()
    return user_id


def _get_user_id(conn) -> int:
    row = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
    return row["id"]


def _days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _insert_habit(conn, user_id: int, name: str = "Test Habit") -> int:
    cur = conn.execute(
        "INSERT INTO habits (user_id, name, active) VALUES (?, ?, 1)",
        (user_id, name),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Orchestrator Tests
# ---------------------------------------------------------------------------

class TestGenerateInsightsOrchestrator:
    def test_generate_insights_empty_db(self, test_conn):
        """Fresh DB with no user data returns an empty list."""
        user_id = _ensure_user(test_conn)
        result = generate_insights(test_conn, user_id)
        assert result == []

    def test_generate_insights_returns_list(self, test_conn):
        """Return type is always a list, even with no data."""
        user_id = _ensure_user(test_conn)
        result = generate_insights(test_conn, user_id)
        assert isinstance(result, list)

    def test_insight_cooldown(self, test_conn):
        """After a notification of a given type is inserted, the same type is
        skipped by the cooldown guard within the cooldown window."""
        user_id = _ensure_user(test_conn)
        insight_type = "insight_budget_alert"

        # Insert a notification of that type with created_at = now
        test_conn.execute(
            "INSERT INTO notifications (user_id, type, title, body, icon, link) "
            "VALUES (?, ?, 'Budget alert', 'body', '💰', '#finance')",
            (user_id, insight_type),
        )
        test_conn.commit()

        # The cooldown guard must detect the recent entry and return True
        on_cooldown = _insight_on_cooldown(test_conn, user_id, insight_type, cooldown_hours=24)
        assert on_cooldown is True

    def test_insight_not_on_cooldown_when_no_prior_entry(self, test_conn):
        """No prior notification of the type means it is not on cooldown."""
        user_id = _ensure_user(test_conn)
        on_cooldown = _insight_on_cooldown(test_conn, user_id, "insight_budget_alert", cooldown_hours=24)
        assert on_cooldown is False


# ---------------------------------------------------------------------------
# Budget Alert
# ---------------------------------------------------------------------------

class TestBudgetAlert:
    def test_budget_alert_no_rules(self, test_conn):
        """No budget rules defined returns None."""
        user_id = _ensure_user(test_conn)
        result = _check_budget_alert(test_conn, user_id, TODAY)
        assert result is None

    def test_budget_alert_triggered(self, test_conn):
        """Budget at 85% of monthly limit returns an insight dict."""
        user_id = _ensure_user(test_conn)

        # Create a rule: Groceries, $500/month limit
        test_conn.execute(
            "INSERT INTO finance_rules (user_id, category, monthly_limit, active) "
            "VALUES (?, 'Groceries', 500.0, 1)",
            (user_id,),
        )
        # Spend $425 this month (85%)
        month_start = TODAY[:7] + "-01"
        test_conn.execute(
            "INSERT INTO finance_log (user_id, date, amount, category, type) "
            "VALUES (?, ?, 425.0, 'Groceries', 'withdrawal')",
            (user_id, month_start),
        )
        test_conn.commit()

        result = _check_budget_alert(test_conn, user_id, TODAY)

        assert result is not None
        assert result["title"] == "Budget alert: Groceries"
        assert "85%" in result["body"]
        assert result["icon"] == "💰"

    def test_budget_alert_under_threshold(self, test_conn):
        """Budget at 50% of limit does not trigger an alert."""
        user_id = _ensure_user(test_conn)

        test_conn.execute(
            "INSERT INTO finance_rules (user_id, category, monthly_limit, active) "
            "VALUES (?, 'Groceries', 500.0, 1)",
            (user_id,),
        )
        month_start = TODAY[:7] + "-01"
        test_conn.execute(
            "INSERT INTO finance_log (user_id, date, amount, category, type) "
            "VALUES (?, ?, 250.0, 'Groceries', 'withdrawal')",
            (user_id, month_start),
        )
        test_conn.commit()

        result = _check_budget_alert(test_conn, user_id, TODAY)
        assert result is None

    def test_budget_alert_reports_worst_offender(self, test_conn):
        """When multiple categories exceed the threshold, the worst is reported."""
        user_id = _ensure_user(test_conn)
        month_start = TODAY[:7] + "-01"

        # Dining: 90% spent, Entertainment: 82% spent
        for cat, limit, spent in [("Dining", 200.0, 180.0), ("Entertainment", 100.0, 82.0)]:
            test_conn.execute(
                "INSERT INTO finance_rules (user_id, category, monthly_limit, active) "
                "VALUES (?, ?, ?, 1)",
                (user_id, cat, limit),
            )
            test_conn.execute(
                "INSERT INTO finance_log (user_id, date, amount, category, type) "
                "VALUES (?, ?, ?, ?, 'withdrawal')",
                (user_id, month_start, spent, cat),
            )
        test_conn.commit()

        result = _check_budget_alert(test_conn, user_id, TODAY)

        assert result is not None
        assert "Dining" in result["title"]


# ---------------------------------------------------------------------------
# Habit Pattern
# ---------------------------------------------------------------------------

class TestHabitPattern:
    def test_habit_pattern_no_data(self, test_conn):
        """No habit miss records returns None."""
        user_id = _ensure_user(test_conn)
        result = _check_habit_pattern(test_conn, user_id, TODAY)
        assert result is None

    def test_habit_pattern_found(self, test_conn):
        """Concentrated misses on one weekday (>50% of total, >=3) returns insight."""
        user_id = _ensure_user(test_conn)
        habit_id = _insert_habit(test_conn, user_id)

        # Find the most recent Monday within the last 30 days
        today = date.today()
        monday = today - timedelta(days=(today.weekday()))  # most recent Monday

        # Insert 4 misses on Monday (represents weekday 1)
        for week in range(4):
            miss_date = (monday - timedelta(weeks=week)).isoformat()
            if miss_date >= _days_ago(30):
                test_conn.execute(
                    "INSERT INTO habit_miss_log (user_id, habit_id, date) VALUES (?, ?, ?)",
                    (user_id, habit_id, miss_date),
                )

        # One miss on a different day (Sunday)
        sunday = (monday - timedelta(days=1)).isoformat()
        test_conn.execute(
            "INSERT INTO habit_miss_log (user_id, habit_id, date) VALUES (?, ?, ?)",
            (user_id, habit_id, sunday),
        )
        test_conn.commit()

        result = _check_habit_pattern(test_conn, user_id, TODAY)

        assert result is not None
        assert "Monday" in result["title"] or "struggles" in result["title"]
        assert result["icon"] == "📊"

    def test_habit_pattern_not_triggered_below_min_count(self, test_conn):
        """Only 2 misses on worst day (below threshold of 3) returns None."""
        user_id = _ensure_user(test_conn)
        habit_id = _insert_habit(test_conn, user_id)

        # 2 misses on Monday — below the minimum of 3
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        for week in range(2):
            miss_date = (monday - timedelta(weeks=week)).isoformat()
            if miss_date >= _days_ago(30):
                test_conn.execute(
                    "INSERT INTO habit_miss_log (user_id, habit_id, date) VALUES (?, ?, ?)",
                    (user_id, habit_id, miss_date),
                )
        test_conn.commit()

        result = _check_habit_pattern(test_conn, user_id, TODAY)
        assert result is None


# ---------------------------------------------------------------------------
# Sleep / Mood Correlation
# ---------------------------------------------------------------------------

class TestSleepMoodCorrelation:
    def test_sleep_mood_no_data(self, test_conn):
        """No sleep or mood logs returns None."""
        user_id = _ensure_user(test_conn)
        result = _check_sleep_mood_correlation(test_conn, user_id, TODAY)
        assert result is None

    def test_sleep_mood_correlation(self, test_conn):
        """Good sleep (>=7h) paired with high mood, bad sleep (<6h) with low mood
        and a difference >= 1.0 returns an insight dict."""
        user_id = _ensure_user(test_conn)

        # 3 good-sleep/high-mood nights + 3 bad-sleep/low-mood nights
        combos = [
            (8.0, 5),  # good sleep → high mood
            (7.5, 4),
            (7.0, 5),
            (5.0, 2),  # bad sleep → low mood
            (4.5, 2),
            (5.5, 1),
        ]
        for i, (hours, mood) in enumerate(combos):
            day = _days_ago(i + 1)
            test_conn.execute(
                "INSERT INTO sleep_logs (user_id, date, hours) VALUES (?, ?, ?)",
                (user_id, day, hours),
            )
            test_conn.execute(
                "INSERT INTO daily_checkins (user_id, date, mood) VALUES (?, ?, ?)",
                (user_id, day, mood),
            )
        test_conn.commit()

        result = _check_sleep_mood_correlation(test_conn, user_id, TODAY)

        assert result is not None
        assert result["title"] == "Sleep boosts your mood"
        assert result["icon"] == "😴"

    def test_sleep_mood_insufficient_samples(self, test_conn):
        """Fewer than 4 matched sleep+mood records returns None."""
        user_id = _ensure_user(test_conn)

        for i in range(3):
            day = _days_ago(i + 1)
            test_conn.execute(
                "INSERT INTO sleep_logs (user_id, date, hours) VALUES (?, ?, ?)",
                (user_id, day, 7.0),
            )
            test_conn.execute(
                "INSERT INTO daily_checkins (user_id, date, mood) VALUES (?, ?, ?)",
                (user_id, day, 4),
            )
        test_conn.commit()

        result = _check_sleep_mood_correlation(test_conn, user_id, TODAY)
        assert result is None


# ---------------------------------------------------------------------------
# Food Gap
# ---------------------------------------------------------------------------

class TestFoodGap:
    def test_food_gap_no_data(self, test_conn):
        """No food log entries returns None."""
        user_id = _ensure_user(test_conn)
        result = _check_food_gap(test_conn, user_id, TODAY)
        assert result is None

    def test_food_gap_detected(self, test_conn):
        """Average daily calories below 80% of 2000 kcal goal returns insight."""
        user_id = _ensure_user(test_conn)

        # Log 1000 kcal/day for the last 5 days (50% of 2000 goal)
        for i in range(5):
            day = _days_ago(i)
            test_conn.execute(
                "INSERT INTO food_logs (user_id, logged_at, calories) VALUES (?, ?, ?)",
                (user_id, day + "T12:00:00", 1000.0),
            )
        test_conn.commit()

        result = _check_food_gap(test_conn, user_id, TODAY)

        assert result is not None
        assert result["title"] == "Calorie intake below goal"
        assert "1000" in result["body"]

    def test_food_gap_on_target(self, test_conn):
        """Average calories meeting 80% of goal returns None."""
        user_id = _ensure_user(test_conn)

        # Log 1800 kcal/day (90% of 2000 default goal — above the 80% threshold)
        for i in range(5):
            day = _days_ago(i)
            test_conn.execute(
                "INSERT INTO food_logs (user_id, logged_at, calories) VALUES (?, ?, ?)",
                (user_id, day + "T12:00:00", 1800.0),
            )
        test_conn.commit()

        result = _check_food_gap(test_conn, user_id, TODAY)
        assert result is None

    def test_food_gap_respects_custom_goal(self, test_conn):
        """A custom calorie goal stored in user_settings is used instead of 2000."""
        user_id = _ensure_user(test_conn)

        # Set a custom goal of 2500 kcal
        test_conn.execute(
            "INSERT INTO user_settings (user_id, key, value) VALUES (?, 'daily_calorie_goal', '2500')",
            (user_id,),
        )
        # Log 1800 kcal/day (72% of 2500 — below the 80% threshold)
        for i in range(5):
            day = _days_ago(i)
            test_conn.execute(
                "INSERT INTO food_logs (user_id, logged_at, calories) VALUES (?, ?, ?)",
                (user_id, day + "T12:00:00", 1800.0),
            )
        test_conn.commit()

        result = _check_food_gap(test_conn, user_id, TODAY)
        assert result is not None
        assert "2500" in result["body"]


# ---------------------------------------------------------------------------
# Water Streak
# ---------------------------------------------------------------------------

class TestWaterStreak:
    def test_water_streak_no_data(self, test_conn):
        """No water log entries returns None."""
        user_id = _ensure_user(test_conn)
        result = _check_water_streak(test_conn, user_id, TODAY)
        assert result is None

    def test_water_streak_positive(self, test_conn):
        """3+ consecutive days at 8+ glasses returns a streak insight."""
        user_id = _ensure_user(test_conn)

        # Log 8 glasses for 4 consecutive days ending today
        for i in range(4):
            day = _days_ago(i)
            test_conn.execute(
                "INSERT INTO water_logs (user_id, glasses, logged_at) VALUES (?, 8, ?)",
                (user_id, day + "T08:00:00"),
            )
        test_conn.commit()

        result = _check_water_streak(test_conn, user_id, TODAY)

        assert result is not None
        assert "streak" in result["title"].lower()
        assert result["icon"] == "💧"

    def test_water_streak_below_3_days(self, test_conn):
        """Only 2 consecutive days at target — below 3-day threshold — no streak."""
        user_id = _ensure_user(test_conn)

        for i in range(2):
            day = _days_ago(i)
            test_conn.execute(
                "INSERT INTO water_logs (user_id, glasses, logged_at) VALUES (?, 8, ?)",
                (user_id, day + "T08:00:00"),
            )
        test_conn.commit()

        result = _check_water_streak(test_conn, user_id, TODAY)
        # Two days is insufficient for the streak branch; also no week-over-week drop
        # since there is no "last week" data — expect None
        assert result is None


# ---------------------------------------------------------------------------
# Fasting Optimization
# ---------------------------------------------------------------------------

class TestFastingOptimization:
    def test_fasting_optimization_no_data(self, test_conn):
        """No fasting logs returns None."""
        user_id = _ensure_user(test_conn)
        result = _check_fasting_optimization(test_conn, user_id, TODAY)
        assert result is None

    def test_fasting_optimization_insufficient_samples(self, test_conn):
        """Fewer than 4 matched fasting+sleep pairs returns None."""
        user_id = _ensure_user(test_conn)

        for i in range(3):
            fast_day = _days_ago(i + 1)
            sleep_night = _days_ago(i + 2)  # night before the fast
            test_conn.execute(
                "INSERT INTO sleep_logs (user_id, date, hours) VALUES (?, ?, 7.5)",
                (user_id, sleep_night),
            )
            test_conn.execute(
                "INSERT INTO fasting_logs "
                "(user_id, start_at, end_at, status) "
                "VALUES (?, ?, ?, 'completed')",
                (user_id, fast_day + "T08:00:00", fast_day + "T24:00:00"),
            )
        test_conn.commit()

        result = _check_fasting_optimization(test_conn, user_id, TODAY)
        assert result is None

    def test_fasting_optimization_detected(self, test_conn):
        """Good sleep nights (>=7h) followed by longer fasts vs. bad sleep (<6h)
        nights with a 2h+ difference returns an insight."""
        user_id = _ensure_user(test_conn)

        def _next_day(day_str: str) -> str:
            return (date.fromisoformat(day_str) + timedelta(days=1)).isoformat()

        # 3 good-sleep/long-fast combos: 18-hour fasts (08:00 → next day 02:00)
        # after 7.5h sleep the previous night
        for i in range(3):
            fast_day = _days_ago(i + 1)
            sleep_night = _days_ago(i + 2)
            test_conn.execute(
                "INSERT INTO sleep_logs (user_id, date, hours) VALUES (?, ?, 7.5)",
                (user_id, sleep_night),
            )
            test_conn.execute(
                "INSERT INTO fasting_logs "
                "(user_id, start_at, end_at, status) VALUES (?, ?, ?, 'completed')",
                (user_id, fast_day + "T08:00:00", _next_day(fast_day) + "T02:00:00"),  # 18h
            )

        # 3 bad-sleep/short-fast combos: 14-hour fasts (08:00 → 22:00) after 5h sleep
        for i in range(3, 6):
            fast_day = _days_ago(i + 1)
            sleep_night = _days_ago(i + 2)
            test_conn.execute(
                "INSERT INTO sleep_logs (user_id, date, hours) VALUES (?, ?, 5.0)",
                (user_id, sleep_night),
            )
            test_conn.execute(
                "INSERT INTO fasting_logs "
                "(user_id, start_at, end_at, status) VALUES (?, ?, ?, 'completed')",
                (user_id, fast_day + "T08:00:00", fast_day + "T22:00:00"),  # 14h
            )
        test_conn.commit()

        result = _check_fasting_optimization(test_conn, user_id, TODAY)

        assert result is not None
        assert result["title"] == "Sleep improves your fasts"
        assert result["icon"] == "⏱️"


# ---------------------------------------------------------------------------
# Spending Trend
# ---------------------------------------------------------------------------

class TestSpendingTrend:
    def test_spending_trend_no_data(self, test_conn):
        """No finance_log entries returns None."""
        user_id = _ensure_user(test_conn)
        result = _check_spending_trend(test_conn, user_id, TODAY)
        assert result is None

    def test_spending_trend_spike(self, test_conn):
        """This week's spending 50% more than last week triggers the alert."""
        user_id = _ensure_user(test_conn)

        # Last week: $100 (8–14 days ago)
        last_week_day = _days_ago(10)
        test_conn.execute(
            "INSERT INTO finance_log (user_id, date, amount, type) VALUES (?, ?, 100.0, 'withdrawal')",
            (user_id, last_week_day),
        )
        # This week: $200 (1–7 days ago)
        this_week_day = _days_ago(3)
        test_conn.execute(
            "INSERT INTO finance_log (user_id, date, amount, type) VALUES (?, ?, 200.0, 'withdrawal')",
            (user_id, this_week_day),
        )
        test_conn.commit()

        result = _check_spending_trend(test_conn, user_id, TODAY)

        assert result is not None
        assert result["title"] == "Spending up this week"
        assert "100%" in result["body"] or "200" in result["body"]

    def test_spending_trend_no_spike(self, test_conn):
        """Spending within 30% of last week returns None."""
        user_id = _ensure_user(test_conn)

        last_week_day = _days_ago(10)
        test_conn.execute(
            "INSERT INTO finance_log (user_id, date, amount, type) VALUES (?, ?, 100.0, 'withdrawal')",
            (user_id, last_week_day),
        )
        this_week_day = _days_ago(3)
        test_conn.execute(
            "INSERT INTO finance_log (user_id, date, amount, type) VALUES (?, ?, 110.0, 'withdrawal')",
            (user_id, this_week_day),
        )
        test_conn.commit()

        result = _check_spending_trend(test_conn, user_id, TODAY)
        assert result is None

    def test_spending_trend_no_last_week_data(self, test_conn):
        """Spending only this week with no last-week baseline returns None."""
        user_id = _ensure_user(test_conn)

        this_week_day = _days_ago(3)
        test_conn.execute(
            "INSERT INTO finance_log (user_id, date, amount, type) VALUES (?, ?, 500.0, 'withdrawal')",
            (user_id, this_week_day),
        )
        test_conn.commit()

        result = _check_spending_trend(test_conn, user_id, TODAY)
        assert result is None


# ---------------------------------------------------------------------------
# Journal Reminder
# ---------------------------------------------------------------------------

class TestJournalReminder:
    def test_journal_reminder_no_entries(self, test_conn):
        """No journal entries at all returns None (onboarding handles first-time)."""
        user_id = _ensure_user(test_conn)
        result = _check_journal_reminder(test_conn, user_id, TODAY)
        assert result is None

    def test_journal_reminder_recent(self, test_conn):
        """Journaled today (0 days ago) returns None."""
        user_id = _ensure_user(test_conn)

        test_conn.execute(
            "INSERT INTO journal_entries (user_id, date, content) VALUES (?, ?, 'wrote today')",
            (user_id, TODAY),
        )
        test_conn.commit()

        result = _check_journal_reminder(test_conn, user_id, TODAY)
        assert result is None

    def test_journal_reminder_two_days_ago(self, test_conn):
        """Journaled 2 days ago — within 3-day window — returns None."""
        user_id = _ensure_user(test_conn)

        test_conn.execute(
            "INSERT INTO journal_entries (user_id, date, content) VALUES (?, ?, 'two days ago')",
            (user_id, _days_ago(2)),
        )
        test_conn.commit()

        result = _check_journal_reminder(test_conn, user_id, TODAY)
        assert result is None

    def test_journal_reminder_stale(self, test_conn):
        """Last journal entry 5 days ago triggers the reminder."""
        user_id = _ensure_user(test_conn)

        test_conn.execute(
            "INSERT INTO journal_entries (user_id, date, content) VALUES (?, ?, 'five days ago')",
            (user_id, _days_ago(5)),
        )
        test_conn.commit()

        result = _check_journal_reminder(test_conn, user_id, TODAY)

        assert result is not None
        assert result["title"] == "Journal check-in"
        assert "5 days" in result["body"]
        assert result["icon"] == "📝"

    def test_journal_reminder_includes_mood_note_on_declining_trend(self, test_conn):
        """When mood has been declining over 3 check-ins, the body includes a note."""
        user_id = _ensure_user(test_conn)

        # Journal entry 5 days ago
        test_conn.execute(
            "INSERT INTO journal_entries (user_id, date, content) VALUES (?, ?, 'old entry')",
            (user_id, _days_ago(5)),
        )
        # Declining mood: 5 → 4 → 3 (most recent first when queried)
        # The check-in query orders DESC, so [0]=most recent, should be: 3,4,5
        for i, mood in enumerate([3, 4, 5]):
            test_conn.execute(
                "INSERT INTO daily_checkins (user_id, date, mood) VALUES (?, ?, ?)",
                (user_id, _days_ago(i), mood),
            )
        test_conn.commit()

        result = _check_journal_reminder(test_conn, user_id, TODAY)

        assert result is not None
        assert "declining" in result["body"].lower()


# ---------------------------------------------------------------------------
# Integration Test — insights saved as notifications
# ---------------------------------------------------------------------------

class TestInsightsSavedAsNotifications:
    def test_insights_saved_as_notifications(self, auth_client, test_conn):
        """generate_insights results, when inserted into notifications, appear in
        GET /api/notifications."""
        user_id = _ensure_user(test_conn)

        # Create the conditions to trigger a journal reminder insight
        test_conn.execute(
            "INSERT INTO journal_entries (user_id, date, content) VALUES (?, ?, 'old entry')",
            (user_id, _days_ago(7)),
        )
        test_conn.commit()

        insights = generate_insights(test_conn, user_id)

        # At minimum the journal reminder should fire
        journal_insights = [i for i in insights if "journal" in i.get("type", "")]
        assert len(journal_insights) >= 1, "Expected at least one journal_reminder insight"

        # Insert all insights into the notifications table
        for insight in insights:
            test_conn.execute(
                "INSERT INTO notifications (user_id, type, title, body, icon, link) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    insight["type"],
                    insight["title"],
                    insight["body"],
                    insight.get("icon", "bell"),
                    insight.get("link", ""),
                ),
            )
        test_conn.commit()

        resp = auth_client.get("/api/notifications")
        assert resp.status_code == 200
        data = resp.get_json()

        inserted_types = {i["type"] for i in insights}
        returned_types = {n["type"] for n in data["notifications"]}

        assert inserted_types.issubset(returned_types), (
            f"Not all insight types appeared in GET /api/notifications.\n"
            f"Missing: {inserted_types - returned_types}"
        )

    def test_insights_have_required_keys(self, test_conn):
        """Every insight dict returned by generate_insights contains all required keys."""
        user_id = _ensure_user(test_conn)

        # Trigger the journal reminder
        test_conn.execute(
            "INSERT INTO journal_entries (user_id, date, content) VALUES (?, ?, 'old')",
            (user_id, _days_ago(7)),
        )
        test_conn.commit()

        insights = generate_insights(test_conn, user_id)
        required_keys = {"type", "title", "body", "icon", "link"}

        for insight in insights:
            missing = required_keys - set(insight.keys())
            assert not missing, f"Insight missing keys {missing}: {insight}"
