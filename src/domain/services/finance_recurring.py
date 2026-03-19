"""Recurring expense detection from transaction history.

Analyses transaction patterns to find subscriptions, rent, utilities, etc.
"""
import logging
import re
from collections import defaultdict
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def _normalize_description(desc: str) -> str:
    """Normalize a transaction description for grouping."""
    text = desc.lower().strip()
    # Remove dates, invoice numbers, reference codes
    text = re.sub(r'\d{2,}', '', text)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def detect_recurring(transactions: list, conn, user_id: int) -> list:
    """Detect recurring expenses from a list of transactions.

    Args:
        transactions: List of transaction dicts with date, description, amount, type, category
        conn: Database connection for storing results
        user_id: The user whose data is being analysed

    Returns:
        List of detected recurring expense dicts
    """
    # Only look at withdrawals
    withdrawals = [t for t in transactions if t.get('type') == 'withdrawal']
    if not withdrawals:
        return []

    # Group by normalized description
    groups = defaultdict(list)
    for tx in withdrawals:
        key = _normalize_description(tx.get('description', ''))
        if len(key) < 3:
            continue
        groups[key].append(tx)

    recurring = []

    for key, txs in groups.items():
        if len(txs) < 2:
            continue

        # Sort by date
        txs.sort(key=lambda t: t.get('date', ''))

        # Check amount consistency (within 15% of median)
        amounts = [float(t.get('amount', 0)) for t in txs]
        median_amount = sorted(amounts)[len(amounts) // 2]
        if median_amount <= 0:
            continue

        consistent_amounts = all(
            abs(a - median_amount) / median_amount < 0.15
            for a in amounts
        )

        if not consistent_amounts:
            continue

        # Check interval consistency (25-35 days for monthly)
        dates = []
        for t in txs:
            try:
                dates.append(date.fromisoformat(t['date'][:10]))
            except (ValueError, KeyError):
                continue

        if len(dates) < 2:
            continue

        intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        avg_interval = sum(intervals) / len(intervals)

        # Determine frequency
        if 25 <= avg_interval <= 35:
            frequency = 'monthly'
        elif 12 <= avg_interval <= 16:
            frequency = 'biweekly'
        elif 5 <= avg_interval <= 9:
            frequency = 'weekly'
        else:
            continue

        # Confidence score (0-1)
        amount_consistency = 1.0 - (max(abs(a - median_amount) for a in amounts) / median_amount) if median_amount else 0
        count_score = min(len(txs) / 4, 1.0)
        confidence = round((amount_consistency * 0.6 + count_score * 0.4), 2)

        recurring.append({
            'description': txs[0].get('description', key),
            'category': txs[0].get('category', ''),
            'estimated_amount': round(median_amount, 2),
            'frequency': frequency,
            'confidence': confidence,
            'last_seen_date': dates[-1].isoformat(),
            'transaction_count': len(txs),
        })

    # Store results in DB
    _store_recurring(recurring, conn, user_id)

    return recurring


def _store_recurring(recurring: list, conn, user_id: int) -> None:
    """Upsert detected recurring expenses into the database."""
    for r in recurring:
        norm_desc = _normalize_description(r['description'])
        existing = conn.execute(
            """SELECT id, dismissed FROM finance_recurring
               WHERE user_id = ? AND (description = ? OR description = ?)""",
            (user_id, r['description'], norm_desc),
        ).fetchone()

        if existing:
            if existing['dismissed']:
                continue
            conn.execute(
                """UPDATE finance_recurring
                   SET estimated_amount = ?, frequency = ?, confidence = ?,
                       last_seen_date = ?, transaction_count = ?, category = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND user_id = ?""",
                (r['estimated_amount'], r['frequency'], r['confidence'],
                 r['last_seen_date'], r['transaction_count'], r['category'],
                 existing['id'], user_id),
            )
        else:
            conn.execute(
                """INSERT INTO finance_recurring
                   (description, category, estimated_amount, frequency, confidence,
                    last_seen_date, transaction_count, user_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (r['description'], r['category'], r['estimated_amount'],
                 r['frequency'], r['confidence'], r['last_seen_date'],
                 r['transaction_count'], user_id),
            )

    conn.commit()
