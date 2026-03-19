"""Weekly financial digest generation.

Produces a summary of the previous week's spending, budgets, and notable events.
"""
import json
import logging
from collections import defaultdict
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def generate_digest(transactions: list, budgets: list, conn, ai_provider=None) -> dict:
    """Generate a weekly financial digest for the most recent complete week.

    Args:
        transactions: All transactions covering at least the past 2 weeks.
        budgets: Current budget data from the dashboard.
        conn: Database connection for storing the digest.
        ai_provider: Optional AI provider for generating a narrative summary.

    Returns:
        The digest dict.
    """
    today = date.today()
    # Previous complete week: Monday to Sunday
    days_since_monday = today.weekday()
    last_sunday = today - timedelta(days=days_since_monday + 1)
    last_monday = last_sunday - timedelta(days=6)

    week_start = last_monday.isoformat()
    week_end = last_sunday.isoformat()

    # Check if digest already exists
    existing = conn.execute(
        "SELECT * FROM finance_digests WHERE week_start = ?", (week_start,)
    ).fetchone()
    if existing:
        return {
            'id': existing['id'],
            'week_start': existing['week_start'],
            'week_end': existing['week_end'],
            'total_spent': existing['total_spent'],
            'top_categories': json.loads(existing['top_categories_json'] or '[]'),
            'budget_status': json.loads(existing['budget_status_json'] or '[]'),
            'notable_transactions': json.loads(existing['notable_transactions_json'] or '[]'),
            'recurring_total': existing['recurring_total'],
            'anomaly_count': existing['anomaly_count'],
            'ai_summary': existing['ai_summary'],
            'already_existed': True,
        }

    # Filter transactions to the target week (withdrawals only for spending)
    week_txns = [
        t for t in transactions
        if week_start <= (t.get('date', '')[:10]) <= week_end
    ]
    week_withdrawals = [t for t in week_txns if t.get('type') == 'withdrawal']

    total_spent = round(sum(float(t.get('amount', 0)) for t in week_withdrawals), 2)

    # Top categories
    cat_totals = defaultdict(float)
    for t in week_withdrawals:
        cat = t.get('category', '') or 'Uncategorized'
        cat_totals[cat] += float(t.get('amount', 0))
    top_categories = sorted(
        [{'category': k, 'amount': round(v, 2)} for k, v in cat_totals.items()],
        key=lambda x: x['amount'],
        reverse=True,
    )[:5]

    # Budget status snapshot
    budget_status = []
    for b in (budgets or []):
        budget_status.append({
            'name': b.get('name', ''),
            'limit': b.get('limit', 0),
            'spent': b.get('spent', 0),
            'velocity': b.get('velocity', 'on_track'),
        })

    # Notable transactions (top 3 largest)
    notable = sorted(week_withdrawals, key=lambda t: float(t.get('amount', 0)), reverse=True)[:3]
    notable_txns = [
        {'description': t.get('description', ''), 'amount': float(t.get('amount', 0)),
         'category': t.get('category', ''), 'date': t.get('date', '')[:10]}
        for t in notable
    ]

    # Recurring total from DB
    recurring_row = conn.execute(
        "SELECT COALESCE(SUM(estimated_amount), 0) AS total FROM finance_recurring WHERE active = 1 AND dismissed = 0"
    ).fetchone()
    recurring_total = round(recurring_row['total'], 2) if recurring_row else 0

    # Anomaly count from that week
    anomaly_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM finance_anomalies WHERE created_at >= ? AND created_at <= ?",
        (week_start, week_end + 'T23:59:59'),
    ).fetchone()['cnt']

    # AI summary (optional)
    ai_summary = ''
    if ai_provider and hasattr(ai_provider, 'generate_insight'):
        try:
            context = {
                'context': (
                    f"Generate a brief 2-3 sentence weekly financial summary. "
                    f"Week: {week_start} to {week_end}. "
                    f"Total spent: ${total_spent:.2f}. "
                    f"Top categories: {', '.join(c['category'] + ': $' + str(c['amount']) for c in top_categories)}. "
                    f"Notable transactions: {', '.join(t['description'] + ': $' + str(t['amount']) for t in notable_txns)}. "
                    f"Recurring obligations: ${recurring_total:.2f}/month. "
                    f"Be concise, friendly, and highlight any concerns."
                ),
            }
            insight = ai_provider.generate_insight(context)
            if insight:
                ai_summary = insight.content
        except Exception as exc:
            logger.warning("AI digest summary failed: %s", exc)

    # Store digest
    conn.execute(
        """INSERT OR REPLACE INTO finance_digests
           (week_start, week_end, total_spent, top_categories_json,
            budget_status_json, notable_transactions_json,
            recurring_total, anomaly_count, ai_summary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (week_start, week_end, total_spent,
         json.dumps(top_categories), json.dumps(budget_status),
         json.dumps(notable_txns), recurring_total, anomaly_count, ai_summary),
    )
    conn.commit()

    return {
        'week_start': week_start,
        'week_end': week_end,
        'total_spent': total_spent,
        'top_categories': top_categories,
        'budget_status': budget_status,
        'notable_transactions': notable_txns,
        'recurring_total': recurring_total,
        'anomaly_count': anomaly_count,
        'ai_summary': ai_summary,
    }
