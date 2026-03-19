"""Finance module routes — Firefly III integration, savings goals, budget rules,
spending log, AI advice, and Stage 2 analytics (insights, recurring, anomalies, digest)."""
import calendar
import json
import logging
import traceback
from collections import defaultdict
from datetime import date, datetime, timedelta
from flask import Blueprint, jsonify, request

from .decorators import login_required
from src.infrastructure.database import get_connection
from src.infrastructure.services.firefly_service import firefly_service

logger = logging.getLogger(__name__)

finance_bp = Blueprint('finance', __name__, url_prefix='/api/finance')


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _current_month_range() -> tuple:
    """Return (start_date, end_date) ISO strings for the current calendar month.

    end_date is the first day of the *next* month (exclusive upper bound).
    """
    today = date.today()
    start = today.replace(day=1).isoformat()
    if today.month == 12:
        end = today.replace(year=today.year + 1, month=1, day=1)
    else:
        end = today.replace(month=today.month + 1, day=1)
    return start, end.isoformat()


def _serialize_rule(r) -> dict:
    return {
        'id': r['id'],
        'category': r['category'],
        'monthly_limit': r['monthly_limit'],
        'description': r['description'],
        'active': bool(r['active']),
        'created_at': r['created_at'],
    }


def _serialize_log(r) -> dict:
    return {
        'id': r['id'],
        'date': r['date'],
        'amount': r['amount'],
        'description': r['description'],
        'category': r['category'],
        'type': r['type'],
        'source': r['source'],
        'created_at': r['created_at'],
    }


def _serialize_goal(r) -> dict:
    target = r['target_amount'] or 0
    current = r['current_amount'] or 0
    pct = round(current / target * 100, 1) if target > 0 else 0.0
    return {
        'id': r['id'],
        'name': r['name'],
        'icon': r['icon'] or '🎯',
        'target_amount': target,
        'current_amount': current,
        'pct_complete': pct,
        'firefly_account_id': r['firefly_account_id'],
        'created_at': r['created_at'],
    }


def _budget_velocity(spent: float, limit: float, day_of_month: int, days_in_month: int) -> str:
    """Return 'ahead', 'on_track', or 'behind' relative to linear spend pace."""
    if limit <= 0:
        return 'on_track'
    expected_fraction = day_of_month / days_in_month
    actual_fraction = spent / limit
    if actual_fraction <= expected_fraction * 0.85:
        return 'behind'
    if actual_fraction >= expected_fraction * 1.15:
        return 'ahead'
    return 'on_track'


def _sync_goal_from_firefly(goal, accounts: list) -> float:
    """If a goal has a linked Firefly account, return that account's balance."""
    fid = goal['firefly_account_id']
    if not fid:
        return goal['current_amount'] or 0.0
    for acc in accounts:
        if str(acc['id']) == str(fid):
            return max(float(acc['balance']), 0.0)
    return goal['current_amount'] or 0.0


# ---------------------------------------------------------------------------
# GET /api/finance/dashboard
# ---------------------------------------------------------------------------

@finance_bp.route('/dashboard')
@login_required
def get_dashboard():
    """All-in-one dashboard payload for the Finance module.

    Returns accounts, net worth, monthly spending with projection, budgets
    (Firefly + local rules), recent transactions, and savings goals.
    """
    try:
        conn = get_connection()
        today = date.today()
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        day_of_month = today.day

        connected = firefly_service.is_connected()

        # -- Accounts & net worth (Firefly) ----------------------------------
        accounts = firefly_service.get_accounts() if connected else []
        net_worth = round(sum(a['balance'] for a in accounts), 2)
        currency = firefly_service.get_default_currency() if connected else {'code': 'USD', 'symbol': '$'}

        # -- Monthly spending (Firefly) ---------------------------------------
        monthly_data = firefly_service.get_monthly_spending() if connected else {'categories': {}, 'total': 0.0, 'currency': currency['code']}
        total_spent = monthly_data['total']

        # Linear projection: if we've spent X in D days, month-end = X / D * days_in_month
        if day_of_month > 0 and total_spent > 0:
            projected = round(total_spent / day_of_month * days_in_month, 2)
        else:
            projected = 0.0

        monthly_payload = {
            'total_spent': total_spent,
            'categories': monthly_data['categories'],
            'days_in_month': days_in_month,
            'day_of_month': day_of_month,
            'projected_month_end': projected,
        }

        # -- Budgets (Firefly budgets merged with local rules) ----------------
        firefly_budgets = firefly_service.get_budgets() if connected else []
        firefly_budget_names = {b['name'] for b in firefly_budgets}

        # Local rules act as budgets when Firefly has no matching budget
        start, end = _current_month_range()
        local_rules = conn.execute(
            "SELECT * FROM finance_rules WHERE active = 1"
        ).fetchall()
        local_spending_rows = conn.execute(
            """SELECT category, SUM(amount) AS total
               FROM finance_log
               WHERE date >= ? AND date < ? AND type = 'withdrawal'
               GROUP BY category""",
            (start, end),
        ).fetchall()
        local_spent_by_cat = {r['category']: r['total'] for r in local_spending_rows}

        budgets_payload = []
        # Firefly budgets first
        for b in firefly_budgets:
            budgets_payload.append({
                'name': b['name'],
                'limit': b['limit'],
                'spent': b['spent'],
                'velocity': _budget_velocity(b['spent'], b['limit'], day_of_month, days_in_month),
                'source': 'firefly',
            })
        # Local rules not already covered by a Firefly budget
        for rule in local_rules:
            if rule['category'] not in firefly_budget_names:
                spent = local_spent_by_cat.get(rule['category'], 0.0)
                limit = rule['monthly_limit'] or 0.0
                budgets_payload.append({
                    'name': rule['category'],
                    'limit': limit,
                    'spent': spent,
                    'velocity': _budget_velocity(spent, limit, day_of_month, days_in_month),
                    'source': 'local',
                })

        # -- Recent transactions (Firefly, fallback to local log) ------------
        if connected:
            recent_txns = firefly_service.get_transactions(days=30, limit=10)
        else:
            rows = conn.execute(
                "SELECT * FROM finance_log ORDER BY date DESC, id DESC LIMIT 10"
            ).fetchall()
            recent_txns = [_serialize_log(r) for r in rows]

        # -- Savings goals ---------------------------------------------------
        goal_rows = conn.execute(
            "SELECT * FROM savings_goals ORDER BY created_at DESC"
        ).fetchall()

        goals_payload = []
        for g in goal_rows:
            serialized = _serialize_goal(g)
            # Sync current_amount from linked Firefly account if applicable
            if connected and g['firefly_account_id']:
                live_balance = _sync_goal_from_firefly(g, accounts)
                serialized['current_amount'] = live_balance
                target = serialized['target_amount']
                serialized['pct_complete'] = round(live_balance / target * 100, 1) if target > 0 else 0.0
            goals_payload.append(serialized)

        return jsonify({
            'accounts': accounts,
            'net_worth': net_worth,
            'currency': currency,
            'monthly': monthly_payload,
            'budgets': budgets_payload,
            'recent_transactions': recent_txns,
            'savings_goals': goals_payload,
            'firefly_connected': connected,
        })

    except Exception:
        logger.exception("Finance dashboard error")
        return jsonify({'error': 'Failed to load dashboard'}), 500


# ---------------------------------------------------------------------------
# GET /api/finance/transactions
# ---------------------------------------------------------------------------

@finance_bp.route('/transactions')
@login_required
def get_transactions():
    """Paginated transaction list.

    Query params:
        days     — how far back to look (default 30)
        limit    — max results (default 50, max 200)
        category — filter by category name (case-insensitive partial match)
        search   — filter by description (case-insensitive partial match)
    """
    try:
        days = min(int(request.args.get('days', 30)), 365)
        limit = min(int(request.args.get('limit', 50)), 200)
        category_filter = (request.args.get('category') or '').strip().lower()
        search_filter = (request.args.get('search') or '').strip().lower()
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid query parameters'}), 400

    connected = firefly_service.is_connected()

    if connected:
        txns = firefly_service.get_transactions(days=days, limit=limit)
    else:
        # Fallback to local finance_log
        from datetime import timedelta
        start = (date.today() - timedelta(days=days)).isoformat()
        rows = get_connection().execute(
            """SELECT * FROM finance_log
               WHERE date >= ?
               ORDER BY date DESC, id DESC
               LIMIT ?""",
            (start, limit),
        ).fetchall()
        txns = [_serialize_log(r) for r in rows]

    # Apply client-side filters (works for both Firefly and local data)
    if category_filter:
        txns = [t for t in txns if category_filter in (t.get('category') or '').lower()]
    if search_filter:
        txns = [t for t in txns if search_filter in (t.get('description') or '').lower()]

    return jsonify({
        'transactions': txns,
        'count': len(txns),
        'firefly_connected': connected,
    })


# ---------------------------------------------------------------------------
# Savings goals CRUD
# ---------------------------------------------------------------------------

@finance_bp.route('/goals')
@login_required
def list_goals():
    """List all savings goals."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM savings_goals ORDER BY created_at DESC"
    ).fetchall()

    connected = firefly_service.is_connected()
    accounts = firefly_service.get_accounts() if connected else []

    goals = []
    for g in rows:
        s = _serialize_goal(g)
        if connected and g['firefly_account_id']:
            live = _sync_goal_from_firefly(g, accounts)
            s['current_amount'] = live
            target = s['target_amount']
            s['pct_complete'] = round(live / target * 100, 1) if target > 0 else 0.0
        goals.append(s)

    return jsonify(goals)


@finance_bp.route('/goals', methods=['POST'])
@login_required
def create_goal():
    """Create a savings goal.

    Body: {name, target_amount, icon?, current_amount?, firefly_account_id?}
    """
    data = request.json or {}
    name = (data.get('name') or '').strip()
    icon = (data.get('icon') or '🎯').strip()
    target_amount = data.get('target_amount')
    current_amount = data.get('current_amount', 0)
    firefly_account_id = (data.get('firefly_account_id') or '').strip() or None

    if not name:
        return jsonify({'error': 'name is required'}), 400
    if target_amount is None:
        return jsonify({'error': 'target_amount is required'}), 400
    try:
        target_amount = float(target_amount)
        current_amount = float(current_amount)
    except (TypeError, ValueError):
        return jsonify({'error': 'target_amount and current_amount must be numbers'}), 400
    if target_amount <= 0:
        return jsonify({'error': 'target_amount must be greater than zero'}), 400

    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO savings_goals (name, icon, target_amount, current_amount, firefly_account_id)
           VALUES (?, ?, ?, ?, ?)""",
        (name, icon, target_amount, current_amount, firefly_account_id),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM savings_goals WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return jsonify(_serialize_goal(row)), 201


@finance_bp.route('/goals/<int:goal_id>', methods=['PUT'])
@login_required
def update_goal(goal_id: int):
    """Update a savings goal.

    Body: any subset of {name, icon, target_amount, current_amount, firefly_account_id}
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM savings_goals WHERE id = ?", (goal_id,)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Goal not found'}), 404

    data = request.json or {}

    name = (data.get('name') or row['name']).strip()
    icon = (data.get('icon') or row['icon'] or '🎯').strip()
    firefly_account_id = data.get('firefly_account_id', row['firefly_account_id'])
    if firefly_account_id is not None:
        firefly_account_id = str(firefly_account_id).strip() or None

    try:
        target_amount = float(data['target_amount']) if 'target_amount' in data else row['target_amount']
        current_amount = float(data['current_amount']) if 'current_amount' in data else row['current_amount']
    except (TypeError, ValueError):
        return jsonify({'error': 'target_amount and current_amount must be numbers'}), 400

    if target_amount <= 0:
        return jsonify({'error': 'target_amount must be greater than zero'}), 400

    conn.execute(
        """UPDATE savings_goals
           SET name = ?, icon = ?, target_amount = ?, current_amount = ?,
               firefly_account_id = ?
           WHERE id = ?""",
        (name, icon, target_amount, current_amount, firefly_account_id, goal_id),
    )
    conn.commit()

    updated = conn.execute(
        "SELECT * FROM savings_goals WHERE id = ?", (goal_id,)
    ).fetchone()
    return jsonify(_serialize_goal(updated))


@finance_bp.route('/goals/<int:goal_id>', methods=['DELETE'])
@login_required
def delete_goal(goal_id: int):
    """Delete a savings goal."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM savings_goals WHERE id = ?", (goal_id,)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Goal not found'}), 404

    conn.execute("DELETE FROM savings_goals WHERE id = ?", (goal_id,))
    conn.commit()
    return '', 204


# ---------------------------------------------------------------------------
# GET /api/finance/summary  (kept for backwards compatibility)
# ---------------------------------------------------------------------------

@finance_bp.route('/summary')
@login_required
def get_summary():
    """Dashboard summary: total spent, per-category budget remaining, warnings.

    Retained for backward compatibility. New code should use /dashboard.
    """
    conn = get_connection()
    start, end = _current_month_range()

    rows = conn.execute(
        """SELECT category, SUM(amount) AS total
           FROM finance_log
           WHERE date >= ? AND date < ? AND type = 'withdrawal'
           GROUP BY category""",
        (start, end),
    ).fetchall()

    spent_by_category = {r['category']: r['total'] for r in rows}
    total_spent = sum(spent_by_category.values()) if spent_by_category else 0.0

    rules = conn.execute(
        "SELECT * FROM finance_rules WHERE active = 1"
    ).fetchall()

    categories = []
    warnings = []
    for rule in rules:
        cat = rule['category']
        spent = spent_by_category.get(cat, 0.0)
        limit = rule['monthly_limit']
        remaining = (limit - spent) if limit is not None else None
        pct = round((spent / limit * 100), 1) if limit else None

        categories.append({
            'category': cat,
            'spent': spent,
            'limit': limit,
            'remaining': remaining,
            'pct_used': pct,
        })

        if limit and pct is not None:
            if pct >= 100:
                warnings.append({'category': cat, 'message': f'Over budget ({pct}% used)', 'level': 'danger'})
            elif pct >= 80:
                warnings.append({'category': cat, 'message': f'Approaching limit ({pct}% used)', 'level': 'warning'})

    recent = conn.execute(
        "SELECT * FROM finance_log ORDER BY date DESC, id DESC LIMIT 10"
    ).fetchall()

    return jsonify({
        'month': start[:7],
        'total_spent': total_spent,
        'categories': categories,
        'warnings': warnings,
        'recent_transactions': [_serialize_log(r) for r in recent],
    })


# ---------------------------------------------------------------------------
# POST /api/finance/ask  — "Should I buy this?"
# ---------------------------------------------------------------------------

@finance_bp.route('/ask', methods=['POST'])
@login_required
def ask_finance():
    """AI advice: should I buy this? Accepts {question, amount, category}."""
    data = request.json or {}
    question = (data.get('question') or '').strip()
    amount = data.get('amount')
    category = (data.get('category') or '').strip()

    if not question:
        return jsonify({'error': 'question is required'}), 400

    conn = get_connection()
    start, end = _current_month_range()

    rows = conn.execute(
        """SELECT category, SUM(amount) AS total
           FROM finance_log
           WHERE date >= ? AND date < ? AND type = 'withdrawal'
           GROUP BY category""",
        (start, end),
    ).fetchall()
    spent_by_category = {r['category']: r['total'] for r in rows}
    total_spent = sum(spent_by_category.values()) if spent_by_category else 0.0

    rules = conn.execute(
        "SELECT * FROM finance_rules WHERE active = 1"
    ).fetchall()
    rules_summary = ', '.join(
        f"{r['category']}: ${r['monthly_limit']:.0f}/mo" for r in rules if r['monthly_limit']
    )

    cat_spent = spent_by_category.get(category, 0.0) if category else None
    cat_rule = next((r for r in rules if r['category'] == category), None)

    try:
        from src.infrastructure.ai import get_ai_provider

        provider = get_ai_provider()
        if not provider.is_available():
            return jsonify({'error': 'AI provider not configured'}), 503

        user_state = {
            'finance_question': question,
            'purchase_amount': amount,
            'purchase_category': category,
            'month_total_spent': total_spent,
            'category_spent_this_month': cat_spent,
            'category_monthly_limit': cat_rule['monthly_limit'] if cat_rule else None,
            'budget_rules': rules_summary,
            'context': (
                f"The user is asking about a potential purchase: \"{question}\". "
                f"Amount: ${amount}. Category: {category}. "
                f"This month they have spent ${total_spent:.2f} total. "
                f"Budget rules: {rules_summary or 'none set'}. "
                f"Category spend this month: ${cat_spent:.2f if cat_spent else 0}. "
                "Reply with practical financial advice and end with a clear "
                "recommendation tag: [WAIT], [OK], or [CAUTION]."
            ),
        }

        insight = provider.generate_insight(user_state)
        advice_text = insight.content if insight else 'Unable to generate advice.'

        recommendation = 'caution'
        lower = advice_text.lower()
        if '[ok]' in lower:
            recommendation = 'ok'
        elif '[wait]' in lower:
            recommendation = 'wait'
        elif '[caution]' in lower:
            recommendation = 'caution'

        conn.execute(
            """INSERT INTO finance_advice (question, advice, amount, category)
               VALUES (?, ?, ?, ?)""",
            (question, advice_text, amount, category),
        )
        conn.commit()

        return jsonify({
            'advice': advice_text,
            'recommendation': recommendation,
            'context': {
                'total_spent_this_month': total_spent,
                'category_spent': cat_spent,
                'category_limit': cat_rule['monthly_limit'] if cat_rule else None,
            },
        })

    except Exception as exc:
        logger.exception("Finance AI ask failed")
        return jsonify({'error': 'AI request failed', 'detail': str(exc)}), 500


# ---------------------------------------------------------------------------
# Budget rules CRUD
# ---------------------------------------------------------------------------

@finance_bp.route('/rules')
@login_required
def list_rules():
    """List all budget rules."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM finance_rules ORDER BY category"
    ).fetchall()
    return jsonify([_serialize_rule(r) for r in rows])


@finance_bp.route('/rules', methods=['POST'])
@login_required
def create_or_update_rule():
    """Create a new budget rule or update the limit for an existing category."""
    data = request.json or {}
    category = (data.get('category') or '').strip()
    monthly_limit = data.get('monthly_limit')
    description = (data.get('description') or '').strip()

    if not category:
        return jsonify({'error': 'category is required'}), 400

    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM finance_rules WHERE category = ?", (category,)
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE finance_rules
               SET monthly_limit = ?, description = ?, active = 1
               WHERE category = ?""",
            (monthly_limit, description, category),
        )
    else:
        conn.execute(
            """INSERT INTO finance_rules (category, monthly_limit, description)
               VALUES (?, ?, ?)""",
            (category, monthly_limit, description),
        )

    conn.commit()

    row = conn.execute(
        "SELECT * FROM finance_rules WHERE category = ?", (category,)
    ).fetchone()
    return jsonify(_serialize_rule(row)), 201 if not existing else 200


@finance_bp.route('/rules/<int:rule_id>', methods=['DELETE'])
@login_required
def delete_rule(rule_id: int):
    """Delete a budget rule."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM finance_rules WHERE id = ?", (rule_id,)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Rule not found'}), 404

    conn.execute("DELETE FROM finance_rules WHERE id = ?", (rule_id,))
    conn.commit()
    return '', 204


# ---------------------------------------------------------------------------
# Manual transaction log
# ---------------------------------------------------------------------------

@finance_bp.route('/log', methods=['POST'])
@login_required
def log_transaction():
    """Manually log a spending transaction."""
    data = request.json or {}
    tx_date = (data.get('date') or date.today().isoformat()).strip()
    amount = data.get('amount')
    description = (data.get('description') or '').strip()
    category = (data.get('category') or '').strip()
    tx_type = (data.get('type') or 'withdrawal').strip()
    source = (data.get('source') or 'manual').strip()

    if amount is None:
        return jsonify({'error': 'amount is required'}), 400
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify({'error': 'amount must be a number'}), 400
    if tx_type not in ('withdrawal', 'deposit', 'transfer'):
        return jsonify({'error': 'type must be withdrawal, deposit, or transfer'}), 400

    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO finance_log (date, amount, description, category, type, source)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (tx_date, amount, description, category, tx_type, source),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM finance_log WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return jsonify(_serialize_log(row)), 201


# ---------------------------------------------------------------------------
# GET /api/finance/report  — monthly spending report
# ---------------------------------------------------------------------------

@finance_bp.route('/report')
@login_required
def get_report():
    """Monthly spending breakdown with comparison to budget rules."""
    month = request.args.get('month')
    if month:
        try:
            year, mon = map(int, month.split('-'))
            start = date(year, mon, 1).isoformat()
            end = date(year + 1, 1, 1).isoformat() if mon == 12 else date(year, mon + 1, 1).isoformat()
        except (ValueError, AttributeError):
            return jsonify({'error': 'month must be YYYY-MM'}), 400
    else:
        start, end = _current_month_range()
        month = start[:7]

    conn = get_connection()

    rows = conn.execute(
        """SELECT category, type, SUM(amount) AS total, COUNT(*) AS count
           FROM finance_log
           WHERE date >= ? AND date < ?
           GROUP BY category, type
           ORDER BY total DESC""",
        (start, end),
    ).fetchall()

    rules = conn.execute(
        "SELECT * FROM finance_rules WHERE active = 1"
    ).fetchall()
    rule_map = {r['category']: r['monthly_limit'] for r in rules}

    breakdown = []
    for r in rows:
        cat = r['category']
        limit = rule_map.get(cat)
        total = r['total']
        breakdown.append({
            'category': cat,
            'type': r['type'],
            'total': total,
            'count': r['count'],
            'limit': limit,
            'pct_used': round(total / limit * 100, 1) if limit and r['type'] == 'withdrawal' else None,
        })

    total_withdrawn = sum(r['total'] for r in rows if r['type'] == 'withdrawal')
    total_deposited = sum(r['total'] for r in rows if r['type'] == 'deposit')

    return jsonify({
        'month': month,
        'total_withdrawn': total_withdrawn,
        'total_deposited': total_deposited,
        'net': total_deposited - total_withdrawn,
        'breakdown': breakdown,
    })


# ---------------------------------------------------------------------------
# Card visibility settings
# ---------------------------------------------------------------------------

_DEFAULT_CARD_VISIBILITY = {
    'accounts': True,
    'budgets': True,
    'goals': True,
    'transactions': True,
    'insights': True,
    'recurring': True,
    'anomalies': True,
    'digest': True,
}


@finance_bp.route('/card-settings')
@login_required
def get_card_settings():
    """Return card visibility preferences."""
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = 'finance_card_visibility'"
    ).fetchone()
    if row and row['value']:
        try:
            saved = json.loads(row['value'])
            merged = {**_DEFAULT_CARD_VISIBILITY, **saved}
            return jsonify(merged)
        except (json.JSONDecodeError, TypeError):
            pass
    return jsonify(_DEFAULT_CARD_VISIBILITY)


@finance_bp.route('/card-settings', methods=['PUT'])
@login_required
def update_card_settings():
    """Update card visibility preferences."""
    data = request.json or {}
    conn = get_connection()
    # Merge with existing
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = 'finance_card_visibility'"
    ).fetchone()
    current = {}
    if row and row['value']:
        try:
            current = json.loads(row['value'])
        except (json.JSONDecodeError, TypeError):
            pass
    current.update(data)
    conn.execute(
        """INSERT INTO app_settings (key, value, updated_at)
           VALUES ('finance_card_visibility', ?, CURRENT_TIMESTAMP)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                          updated_at = excluded.updated_at""",
        (json.dumps(current),),
    )
    conn.commit()
    merged = {**_DEFAULT_CARD_VISIBILITY, **current}
    return jsonify(merged)


# ---------------------------------------------------------------------------
# GET /api/finance/insights — spending insights
# ---------------------------------------------------------------------------

@finance_bp.route('/insights')
@login_required
def get_insights():
    """Spending insights: top categories, month-over-month, daily avg, biggest tx."""
    try:
        connected = firefly_service.is_connected()
        if not connected:
            return jsonify({'error': 'Firefly not connected'}), 503

        currency = firefly_service.get_default_currency()
        today = date.today()

        # Current month transactions
        cur_start = today.replace(day=1)
        cur_txns = firefly_service.get_transactions(days=today.day, limit=500)
        cur_withdrawals = [t for t in cur_txns if t.get('type') == 'withdrawal']

        # Previous month transactions
        prev_end = cur_start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        prev_days = (today - prev_start).days
        all_txns = firefly_service.get_transactions(days=prev_days, limit=500)
        prev_withdrawals = [
            t for t in all_txns
            if t.get('type') == 'withdrawal'
            and prev_start.isoformat() <= (t.get('date', '')[:10]) <= prev_end.isoformat()
        ]

        # Top categories (current month)
        cat_totals = defaultdict(float)
        for t in cur_withdrawals:
            cat = t.get('category', '') or 'Uncategorized'
            cat_totals[cat] += float(t.get('amount', 0))
        top_categories = sorted(
            [{'category': k, 'amount': round(v, 2)} for k, v in cat_totals.items()],
            key=lambda x: x['amount'], reverse=True,
        )[:5]

        # Month-over-month
        cur_total = sum(float(t.get('amount', 0)) for t in cur_withdrawals)
        prev_total = sum(float(t.get('amount', 0)) for t in prev_withdrawals)
        mom_pct = round(((cur_total - prev_total) / prev_total * 100), 1) if prev_total > 0 else 0

        # Daily average
        day_of_month = today.day
        daily_avg = round(cur_total / day_of_month, 2) if day_of_month > 0 else 0

        # Biggest transaction
        biggest = None
        if cur_withdrawals:
            big_tx = max(cur_withdrawals, key=lambda t: float(t.get('amount', 0)))
            biggest = {
                'description': big_tx.get('description', ''),
                'amount': float(big_tx.get('amount', 0)),
                'category': big_tx.get('category', ''),
                'date': big_tx.get('date', '')[:10],
            }

        # Category trends (current vs previous)
        prev_cat_totals = defaultdict(float)
        for t in prev_withdrawals:
            cat = t.get('category', '') or 'Uncategorized'
            prev_cat_totals[cat] += float(t.get('amount', 0))
        category_trends = []
        all_cats = set(list(cat_totals.keys()) + list(prev_cat_totals.keys()))
        for cat in list(all_cats)[:8]:
            cur_amt = cat_totals.get(cat, 0)
            prev_amt = prev_cat_totals.get(cat, 0)
            category_trends.append({
                'category': cat,
                'current': round(cur_amt, 2),
                'previous': round(prev_amt, 2),
                'change_pct': round(((cur_amt - prev_amt) / prev_amt * 100), 1) if prev_amt > 0 else 0,
            })

        return jsonify({
            'top_categories': top_categories,
            'month_over_month': {
                'current_total': round(cur_total, 2),
                'previous_total': round(prev_total, 2),
                'change_pct': mom_pct,
            },
            'daily_average': daily_avg,
            'biggest_transaction': biggest,
            'category_trends': category_trends,
            'currency': currency,
        })
    except Exception:
        logger.exception("Insights error")
        return jsonify({'error': 'Failed to generate insights'}), 500


# ---------------------------------------------------------------------------
# Recurring expense detection
# ---------------------------------------------------------------------------

@finance_bp.route('/recurring')
@login_required
def list_recurring():
    """List detected recurring expenses."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM finance_recurring
           WHERE active = 1 AND dismissed = 0
           ORDER BY estimated_amount DESC"""
    ).fetchall()
    return jsonify([{
        'id': r['id'],
        'description': r['description'],
        'category': r['category'],
        'estimated_amount': r['estimated_amount'],
        'frequency': r['frequency'],
        'confidence': r['confidence'],
        'last_seen_date': r['last_seen_date'],
        'transaction_count': r['transaction_count'],
    } for r in rows])


@finance_bp.route('/recurring/detect', methods=['POST'])
@login_required
def detect_recurring_expenses():
    """Trigger recurring expense detection from the last 90 days."""
    try:
        connected = firefly_service.is_connected()
        if not connected:
            return jsonify({'error': 'Firefly not connected'}), 503

        txns = firefly_service.get_transactions(days=90, limit=500)
        conn = get_connection()

        from src.domain.services.finance_recurring import detect_recurring
        results = detect_recurring(txns, conn)

        return jsonify({
            'detected': len(results),
            'recurring': results,
        })
    except Exception:
        logger.exception("Recurring detection error")
        return jsonify({'error': 'Detection failed'}), 500


@finance_bp.route('/recurring/<int:rec_id>/dismiss', methods=['PUT'])
@login_required
def dismiss_recurring(rec_id: int):
    """Dismiss a recurring expense detection."""
    conn = get_connection()
    conn.execute(
        "UPDATE finance_recurring SET dismissed = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (rec_id,),
    )
    conn.commit()
    return '', 204


# ---------------------------------------------------------------------------
# Transaction anomaly alerts
# ---------------------------------------------------------------------------

@finance_bp.route('/anomalies')
@login_required
def list_anomalies():
    """List unacknowledged anomaly alerts."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM finance_anomalies
           WHERE acknowledged = 0
           ORDER BY created_at DESC"""
    ).fetchall()
    return jsonify([{
        'id': r['id'],
        'transaction_id': r['transaction_id'],
        'description': r['description'],
        'amount': r['amount'],
        'category': r['category'],
        'category_average': r['category_average'],
        'deviation_factor': r['deviation_factor'],
        'alert_type': r['alert_type'],
        'created_at': r['created_at'],
    } for r in rows])


@finance_bp.route('/anomalies/scan', methods=['POST'])
@login_required
def scan_anomalies():
    """Trigger anomaly detection on recent transactions."""
    try:
        connected = firefly_service.is_connected()
        if not connected:
            return jsonify({'error': 'Firefly not connected'}), 503

        txns = firefly_service.get_transactions(days=90, limit=500)
        conn = get_connection()

        from src.domain.services.finance_anomalies import detect_anomalies
        results = detect_anomalies(txns, conn)

        return jsonify({
            'detected': len(results),
            'anomalies': results,
        })
    except Exception:
        logger.exception("Anomaly scan error")
        return jsonify({'error': 'Scan failed'}), 500


@finance_bp.route('/anomalies/<int:anomaly_id>/acknowledge', methods=['PUT'])
@login_required
def acknowledge_anomaly(anomaly_id: int):
    """Acknowledge an anomaly alert."""
    conn = get_connection()
    conn.execute(
        "UPDATE finance_anomalies SET acknowledged = 1 WHERE id = ?",
        (anomaly_id,),
    )
    conn.commit()
    return '', 204


# ---------------------------------------------------------------------------
# Weekly financial digest
# ---------------------------------------------------------------------------

@finance_bp.route('/digest')
@login_required
def get_digest():
    """Get the most recent weekly digest, or history with ?history=true."""
    conn = get_connection()
    show_history = request.args.get('history', '').lower() in ('true', '1')

    if show_history:
        rows = conn.execute(
            "SELECT * FROM finance_digests ORDER BY week_start DESC LIMIT 12"
        ).fetchall()
        return jsonify([{
            'id': r['id'],
            'week_start': r['week_start'],
            'week_end': r['week_end'],
            'total_spent': r['total_spent'],
            'top_categories': json.loads(r['top_categories_json'] or '[]'),
            'budget_status': json.loads(r['budget_status_json'] or '[]'),
            'notable_transactions': json.loads(r['notable_transactions_json'] or '[]'),
            'recurring_total': r['recurring_total'],
            'anomaly_count': r['anomaly_count'],
            'ai_summary': r['ai_summary'],
        } for r in rows])

    row = conn.execute(
        "SELECT * FROM finance_digests ORDER BY week_start DESC LIMIT 1"
    ).fetchone()
    if not row:
        return jsonify({'message': 'No digests yet. Click Generate to create one.'}), 404

    return jsonify({
        'id': row['id'],
        'week_start': row['week_start'],
        'week_end': row['week_end'],
        'total_spent': row['total_spent'],
        'top_categories': json.loads(row['top_categories_json'] or '[]'),
        'budget_status': json.loads(row['budget_status_json'] or '[]'),
        'notable_transactions': json.loads(row['notable_transactions_json'] or '[]'),
        'recurring_total': row['recurring_total'],
        'anomaly_count': row['anomaly_count'],
        'ai_summary': row['ai_summary'],
    })


@finance_bp.route('/digest/generate', methods=['POST'])
@login_required
def generate_digest():
    """Generate a weekly digest for the most recent complete week."""
    try:
        connected = firefly_service.is_connected()
        if not connected:
            return jsonify({'error': 'Firefly not connected'}), 503

        txns = firefly_service.get_transactions(days=30, limit=500)
        budgets = firefly_service.get_budgets()
        conn = get_connection()

        # Try to get AI provider for narrative summary
        ai_provider = None
        try:
            from src.infrastructure.ai import get_ai_provider
            provider = get_ai_provider()
            if provider.is_available():
                ai_provider = provider
        except Exception:
            pass

        from src.domain.services.finance_digest import generate_digest as gen
        result = gen(txns, budgets, conn, ai_provider)

        return jsonify(result)
    except Exception:
        logger.exception("Digest generation error")
        return jsonify({'error': 'Digest generation failed'}), 500
