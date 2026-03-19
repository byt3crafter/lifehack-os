"""Transaction anomaly detection.

Flags unusually large transactions compared to category averages.
"""
import logging
import math
from collections import defaultdict

logger = logging.getLogger(__name__)


def detect_anomalies(transactions: list, conn, lookback_days: int = 7) -> list:
    """Detect anomalous transactions from recent history.

    Args:
        transactions: All transactions (90+ days) for computing baselines.
        conn: Database connection for storing alerts.
        lookback_days: Only flag transactions within this many recent days.

    Returns:
        List of anomaly dicts.
    """
    withdrawals = [t for t in transactions if t.get('type') == 'withdrawal']
    if not withdrawals:
        return []

    # Sort by date
    withdrawals.sort(key=lambda t: t.get('date', ''))

    # Compute per-category stats from all transactions
    cat_amounts = defaultdict(list)
    for tx in withdrawals:
        cat = tx.get('category', '') or 'Uncategorized'
        amount = float(tx.get('amount', 0))
        if amount > 0:
            cat_amounts[cat].append(amount)

    cat_stats = {}
    for cat, amounts in cat_amounts.items():
        if len(amounts) < 3:
            continue
        mean = sum(amounts) / len(amounts)
        variance = sum((a - mean) ** 2 for a in amounts) / len(amounts)
        std = math.sqrt(variance) if variance > 0 else 0
        cat_stats[cat] = {'mean': mean, 'std': std, 'count': len(amounts)}

    # Find the cutoff date for recent transactions
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()

    anomalies = []
    seen_ids = set()

    # Check which transaction IDs are already stored
    existing = conn.execute(
        "SELECT transaction_id FROM finance_anomalies WHERE transaction_id IS NOT NULL"
    ).fetchall()
    already_flagged = {r['transaction_id'] for r in existing}

    for tx in withdrawals:
        tx_date = tx.get('date', '')[:10]
        if tx_date < cutoff:
            continue

        tx_id = str(tx.get('id', ''))
        if tx_id in already_flagged or tx_id in seen_ids:
            continue

        amount = float(tx.get('amount', 0))
        cat = tx.get('category', '') or 'Uncategorized'
        stats = cat_stats.get(cat)

        if not stats:
            continue

        mean = stats['mean']
        std = stats['std']

        # Flag if > 2 standard deviations above mean, or > 3x the average
        deviation = 0
        if std > 0:
            deviation = (amount - mean) / std
        multiplier = amount / mean if mean > 0 else 0

        if deviation > 2.0 or multiplier > 3.0:
            seen_ids.add(tx_id)
            anomalies.append({
                'transaction_id': tx_id,
                'description': tx.get('description', ''),
                'amount': amount,
                'category': cat,
                'category_average': round(mean, 2),
                'deviation_factor': round(max(deviation, multiplier), 1),
                'alert_type': 'high_spend',
            })

    # Store new anomalies
    for a in anomalies:
        conn.execute(
            """INSERT INTO finance_anomalies
               (transaction_id, description, amount, category,
                category_average, deviation_factor, alert_type)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (a['transaction_id'], a['description'], a['amount'],
             a['category'], a['category_average'], a['deviation_factor'],
             a['alert_type']),
        )
    conn.commit()

    return anomalies
