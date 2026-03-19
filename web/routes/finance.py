"""Finance module routes — budget rules, spending log, AI advice."""
import traceback
from datetime import date, datetime
from flask import Blueprint, jsonify, request

from .decorators import login_required
from src.infrastructure.database import get_connection

finance_bp = Blueprint('finance', __name__, url_prefix='/api/finance')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_month_range() -> tuple:
    """Return (start_date, end_date) strings for the current calendar month."""
    today = date.today()
    start = today.replace(day=1).isoformat()
    # Last day of month: first day of next month minus one day
    if today.month == 12:
        end = today.replace(year=today.year + 1, month=1, day=1)
    else:
        end = today.replace(month=today.month + 1, day=1)
    # end is exclusive upper bound — use it as-is for < comparisons
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


# ---------------------------------------------------------------------------
# GET /api/finance/summary
# ---------------------------------------------------------------------------

@finance_bp.route('/summary')
@login_required
def get_summary():
    """Dashboard summary: total spent, per-category budget remaining, warnings."""
    conn = get_connection()
    start, end = _current_month_range()

    # Aggregate spending by category this month (withdrawals only)
    rows = conn.execute(
        """SELECT category, SUM(amount) AS total
           FROM finance_log
           WHERE date >= ? AND date < ? AND type = 'withdrawal'
           GROUP BY category""",
        (start, end),
    ).fetchall()

    spent_by_category = {r['category']: r['total'] for r in rows}
    total_spent = sum(spent_by_category.values()) if spent_by_category else 0.0

    # Active budget rules
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

        entry = {
            'category': cat,
            'spent': spent,
            'limit': limit,
            'remaining': remaining,
            'pct_used': pct,
        }
        categories.append(entry)

        if limit and pct is not None:
            if pct >= 100:
                warnings.append({'category': cat, 'message': f'Over budget ({pct}% used)', 'level': 'danger'})
            elif pct >= 80:
                warnings.append({'category': cat, 'message': f'Approaching limit ({pct}% used)', 'level': 'warning'})

    # Recent transactions (last 10)
    recent = conn.execute(
        """SELECT * FROM finance_log ORDER BY date DESC, id DESC LIMIT 10"""
    ).fetchall()

    return jsonify({
        'month': start[:7],  # e.g. "2026-03"
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

    # Build spending context
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

        # Build a rich user_state to drive generate_insight
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

        # Parse recommendation tag from advice text
        recommendation = 'caution'
        lower = advice_text.lower()
        if '[ok]' in lower:
            recommendation = 'ok'
        elif '[wait]' in lower:
            recommendation = 'wait'
        elif '[caution]' in lower:
            recommendation = 'caution'

        # Persist advice
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
        return jsonify({'error': 'AI request failed', 'detail': str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /api/finance/rules
# ---------------------------------------------------------------------------

@finance_bp.route('/rules')
@login_required
def list_rules():
    """List all active budget rules."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM finance_rules ORDER BY category"
    ).fetchall()
    return jsonify([_serialize_rule(r) for r in rows])


# ---------------------------------------------------------------------------
# POST /api/finance/rules
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# DELETE /api/finance/rules/<id>
# ---------------------------------------------------------------------------

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
# POST /api/finance/log  — manual transaction entry
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
    month = request.args.get('month')  # optional: "2026-02"
    if month:
        try:
            year, mon = map(int, month.split('-'))
            start = date(year, mon, 1).isoformat()
            if mon == 12:
                end = date(year + 1, 1, 1).isoformat()
            else:
                end = date(year, mon + 1, 1).isoformat()
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

    total_withdrawn = sum(
        r['total'] for r in rows if r['type'] == 'withdrawal'
    )
    total_deposited = sum(
        r['total'] for r in rows if r['type'] == 'deposit'
    )

    return jsonify({
        'month': month,
        'total_withdrawn': total_withdrawn,
        'total_deposited': total_deposited,
        'net': total_deposited - total_withdrawn,
        'breakdown': breakdown,
    })
