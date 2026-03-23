"""AI-generated reports — morning briefing, evening recap, and weekly digest.

Reports are generated as assistant messages inside a dedicated chat conversation
so users can read them inline, reference them later, and reply with follow-up
questions.  Each report type is idempotent within its time window (daily for
morning/evening, weekly for the weekly report) so cron jobs can run safely
without producing duplicates.
"""
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompts for each report type
# ---------------------------------------------------------------------------

REPORT_PROMPTS: dict[str, str] = {
    'morning': """You are generating a personalised Morning Briefing report for {name}.

Your job is to give them an actionable, energising overview of today.

## Structure — output EXACTLY in this order:

1. A short warm greeting (1 sentence, use their name).
2. A ```metrics block with today's key numbers (habits scheduled, calories goal, water target, any active fast).
3. A ```progress block summarising yesterday's habit completions vs total.
4. Habit priorities for today — a short bulleted list (3–5 habits) with the most important ones highlighted.
5. A ```chart block showing the past 7 days of habit completions (bar chart).
6. One finance check-in: current budget status or a spending reminder if they are over in any category.
7. A brief motivational close (1–2 sentences) that references something specific from their data (a streak, a goal, an upcoming discovery).

## Rules
- Use their ACTUAL data from the context — never invent numbers.
- Keep the tone energising and direct. No filler.
- If data for a section is missing, skip that section gracefully.
- Use ```metrics, ```progress, and ```chart blocks as described above.
- Charts must use dark theme colours (background #141416, text #f0f0f2, accent #4f80ff, grid #2a2a2e).
""",

    'evening': """You are generating a personalised Evening Recap report for {name}.

Your job is to give them a clear, honest summary of how the day went.

## Structure — output EXACTLY in this order:

1. A short, warm opening line (1 sentence, use their name).
2. A ```metrics block: habits completed vs scheduled, calories consumed vs goal, water glasses logged, deep work minutes.
3. A ```progress block for today's key goals (calorie goal, water goal, habit completion rate).
4. Food summary — a short markdown table of meals logged with calories and protein.
5. One win: call out the best thing they did today (specific, data-backed).
6. One constructive note: one area they can improve tomorrow (specific, not generic).
7. A ```chart block: today's calorie intake by meal (bar or doughnut chart).
8. Tomorrow's setup: 2–3 specific actions they can take tonight or first thing tomorrow.

## Rules
- Use their ACTUAL data — never invent numbers.
- Be honest and direct. Celebrate wins; name gaps without being harsh.
- If data for a section is missing, skip that section gracefully.
- Use ```metrics, ```progress, and ```chart blocks as described above.
- Charts must use dark theme colours (background #141416, text #f0f0f2, accent #4f80ff, grid #2a2a2e).
""",

    'weekly': """You are generating a personalised Weekly Report for {name}.

This is their full 7-day performance digest. Be thorough but scannable.

## Structure — output EXACTLY in this order:

1. A short headline summary (1 sentence) — what kind of week was it overall?
2. A ```metrics block: total habit completions, average completion rate, total calories, average sleep, total deep work minutes, total spending.
3. Habits deep-dive:
   - A ```chart block: daily habit completions over the 7 days (bar chart).
   - Top 3 strongest habits and top 3 habits that slipped — use actual names and data.
4. Nutrition week:
   - A ```chart block: daily calorie totals for the 7 days.
   - One observation about macro trends (protein, carbs, fat).
5. Finance check:
   - Spending by category (markdown table).
   - One budget alert if any category is over limit.
6. Wins of the week: 3 specific data-backed wins.
7. Focus areas for next week: 3 specific, actionable priorities.
8. One motivational close referencing a longer-term trend (streak, weight trend, savings goal progress).

## Rules
- Use their ACTUAL data — never invent numbers.
- Reference SPECIFIC values: streak lengths, calorie totals, spending amounts.
- If data for a section is missing, skip that section gracefully.
- Use ```metrics, ```progress, and ```chart blocks as described above.
- Charts must use dark theme colours (background #141416, text #f0f0f2, accent #4f80ff, grid #2a2a2e).
""",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_report(conn, user_id: int, report_type: str) -> Optional[dict]:
    """Generate an AI report for a user and persist it.

    Args:
        conn: Active SQLite connection.
        user_id: Target user's ID.
        report_type: One of 'morning', 'evening', 'weekly'.

    Returns:
        {'success': True, 'report_id': int, 'conversation_id': int} on success.
        None if the report was skipped (idempotency) or AI is unavailable.
        None on unrecoverable error (logged server-side).
    """
    if report_type not in REPORT_PROMPTS:
        logger.warning("generate_report: unknown report_type=%r for user %s", report_type, user_id)
        return None

    try:
        from src.domain.services.chat_context import assemble_context, _user_now

        user_now = _user_now(conn, user_id)
        today_str = user_now.date().isoformat()

        # ── 1. Idempotency check ──────────────────────────────────────────────
        if report_type == 'weekly':
            # Weekly reports are idempotent within the current ISO week
            week_start = (user_now.date() - timedelta(days=user_now.weekday())).isoformat()
            existing = conn.execute(
                "SELECT id FROM ai_reports WHERE user_id=? AND type=? AND period_start=?",
                (user_id, report_type, week_start),
            ).fetchone()
        else:
            existing = conn.execute(
                "SELECT id FROM ai_reports WHERE user_id=? AND type=? AND date(created_at)=?",
                (user_id, report_type, today_str),
            ).fetchone()

        if existing:
            logger.debug(
                "generate_report: skipping %s report for user %s — already generated",
                report_type, user_id,
            )
            return None

        # ── 2. Assemble context ───────────────────────────────────────────────
        context = assemble_context(conn, user_id)

        # ── 3. Extra data for weekly reports ──────────────────────────────────
        if report_type == 'weekly':
            _add_weekly_context(conn, user_id, user_now, context)

        # ── 4. Build system prompt ────────────────────────────────────────────
        user_name = _resolve_user_name(context)
        raw_prompt = REPORT_PROMPTS[report_type].replace('{name}', user_name)
        system_prompt = (
            raw_prompt
            + "\n\n## User's Live Data\n"
            + json.dumps(context, indent=2, default=str)
        )

        # ── 5. Get AI provider ────────────────────────────────────────────────
        from src.infrastructure.ai.factory import get_ai_provider
        provider = get_ai_provider('reports', user_id=user_id)

        # ── 6. Check availability ─────────────────────────────────────────────
        if not provider.is_available():
            logger.info(
                "generate_report: skipping %s report for user %s — AI provider not available",
                report_type, user_id,
            )
            return None

        # ── 7. Call the AI ────────────────────────────────────────────────────
        try:
            content = provider.chat_with_context(
                system_prompt,
                [{"role": "user", "content": "Generate my report."}],
            )
        except Exception as exc:
            logger.error(
                "generate_report: AI call failed for user %s (%s report): %s",
                user_id, report_type, exc,
            )
            return None

        # ── 8. Validate response ──────────────────────────────────────────────
        if not content or not content.strip():
            logger.warning(
                "generate_report: AI returned empty content for user %s (%s report)",
                user_id, report_type,
            )
            return None

        # ── 9. Get or create destination conversation ─────────────────────────
        if report_type == 'weekly':
            conv_id = _create_weekly_conversation(conn, user_id, user_now)
        else:
            conv_id = _get_or_create_reports_conversation(conn, user_id)

        # ── 10. Insert assistant message ──────────────────────────────────────
        conn.execute(
            """INSERT INTO chat_messages (user_id, conversation_id, role, content, provider, model)
               VALUES (?, ?, 'assistant', ?, 'system', 'report')""",
            (user_id, conv_id, content),
        )
        # Bump last_message_at on the conversation
        conn.execute(
            "UPDATE chat_conversations SET last_message_at=CURRENT_TIMESTAMP WHERE id=?",
            (conv_id,),
        )

        # ── 11. Insert ai_reports row ─────────────────────────────────────────
        if report_type == 'weekly':
            period_start = week_start
            period_end = today_str
        else:
            period_start = today_str
            period_end = today_str

        cursor = conn.execute(
            """INSERT INTO ai_reports (user_id, type, content, conversation_id, period_start, period_end)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, report_type, content, conv_id, period_start, period_end),
        )
        report_id = cursor.lastrowid

        # ── 12. Insert notification ───────────────────────────────────────────
        type_labels = {
            'morning': 'Morning Briefing',
            'evening': 'Evening Recap',
            'weekly':  'Weekly Report',
        }
        label = type_labels.get(report_type, 'AI Report')
        conn.execute(
            """INSERT INTO notifications (user_id, type, title, body, icon, link)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                f'ai_report_{report_type}',
                f'Your {label} is ready',
                f'Your {label} has been generated. Tap to read it.',
                'bar-chart-2',
                f'/chat?conv={conv_id}',
            ),
        )

        conn.commit()
        logger.info(
            "generate_report: created %s report (id=%s) for user %s in conv %s",
            report_type, report_id, user_id, conv_id,
        )
        return {'success': True, 'report_id': report_id, 'conversation_id': conv_id}

    except Exception as exc:
        logger.error(
            "generate_report: unexpected error for user %s (%s report): %s",
            user_id, report_type, exc,
        )
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _add_weekly_context(conn, user_id: int, user_now: datetime, context: dict) -> None:
    """Enrich context with 7-day aggregates for weekly reports."""
    from src.domain.services.chat_context import _safe_query

    week_start = (user_now.date() - timedelta(days=6)).isoformat()
    today = user_now.date().isoformat()

    context['weekly_habit_completions_by_day'] = _safe_query(
        conn,
        """SELECT date(completed_at) as day, COUNT(*) as completions
           FROM habit_completions
           WHERE user_id=? AND date(completed_at) BETWEEN ? AND ?
           GROUP BY day ORDER BY day""",
        (user_id, week_start, today),
    )

    context['weekly_food_totals_by_day'] = _safe_query(
        conn,
        """SELECT date(logged_at) as day,
                  CAST(SUM(calories) AS INTEGER) as total_calories,
                  CAST(SUM(protein_g) AS INTEGER) as total_protein
           FROM food_logs
           WHERE user_id=? AND date(logged_at) BETWEEN ? AND ?
           GROUP BY day ORDER BY day""",
        (user_id, week_start, today),
    )

    context['weekly_spending_by_day'] = _safe_query(
        conn,
        """SELECT date(date) as day, SUM(amount) as total_spent
           FROM finance_log
           WHERE user_id=? AND date BETWEEN ? AND ?
           GROUP BY day ORDER BY day""",
        (user_id, week_start, today),
    )


def _resolve_user_name(context: dict) -> str:
    """Extract the user's preferred display name from assembled context."""
    profile_list = context.get('user_profile')
    if profile_list:
        profile = profile_list[0] if isinstance(profile_list, list) else profile_list
        name = (profile.get('preferred_name') or '').strip() or \
               (profile.get('display_name') or '').strip()
        if name:
            return name
    return 'there'


def _get_or_create_reports_conversation(conn, user_id: int) -> int:
    """Return the shared 'AI Reports' conversation ID, creating it if absent.

    The conversation is pinned and categorised as 'reports' so it surfaces
    at the top of the sidebar under the Reports filter.
    """
    row = conn.execute(
        """SELECT id FROM chat_conversations
           WHERE user_id=? AND title='AI Reports' AND category='reports'
           LIMIT 1""",
        (user_id,),
    ).fetchone()

    if row:
        return row['id']

    cursor = conn.execute(
        """INSERT INTO chat_conversations (user_id, title, category, pinned)
           VALUES (?, 'AI Reports', 'reports', 1)""",
        (user_id,),
    )
    conn.commit()
    return cursor.lastrowid


def _create_weekly_conversation(conn, user_id: int, user_now: datetime) -> int:
    """Create a fresh conversation for this week's report.

    The title includes the human-readable date range, e.g.
    "Weekly Report · Mar 17-23".
    """
    week_start = user_now.date() - timedelta(days=user_now.weekday())
    week_end = week_start + timedelta(days=6)

    # Format: "Mar 17-23" (same month) or "Mar 28 – Apr 3" (cross-month)
    if week_start.month == week_end.month:
        label = f"{week_start.strftime('%b')} {week_start.day}-{week_end.day}"
    else:
        label = f"{week_start.strftime('%b %-d')} – {week_end.strftime('%b %-d')}"

    title = f"Weekly Report · {label}"

    cursor = conn.execute(
        """INSERT INTO chat_conversations (user_id, title, category, pinned)
           VALUES (?, ?, 'reports', 1)""",
        (user_id, title),
    )
    conn.commit()
    return cursor.lastrowid
