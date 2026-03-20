"""AI usage tracking — per-user plan limits and call logging."""

PLAN_LIMITS = {
    'free':      {'daily_ai_calls': 10,     'name': 'Free'},
    'personal':  {'daily_ai_calls': 100,    'name': 'Personal'},
    'pro':       {'daily_ai_calls': 1000,   'name': 'Pro'},
    'unlimited': {'daily_ai_calls': 999999, 'name': 'Unlimited'},
}


def check_ai_usage(user_id: int, conn) -> dict:
    """Check whether a user can make an AI call.

    Returns a dict with keys:
        allowed     — bool, True if the user is within their daily limit
        used        — int, calls made today
        limit       — int, daily call ceiling for the user's plan
        plan        — str, raw plan key (e.g. 'free')
        plan_name   — str, human-readable plan name (e.g. 'Free')
    """
    user = conn.execute(
        "SELECT plan FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    plan = (user['plan'] if user and user['plan'] else 'free')
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS['free'])

    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM ai_usage_log "
        "WHERE user_id = ? AND date(timestamp) = date('now')",
        (user_id,),
    ).fetchone()
    used = row['cnt'] if row else 0

    return {
        'allowed':    used < limits['daily_ai_calls'],
        'used':       used,
        'limit':      limits['daily_ai_calls'],
        'plan':       plan,
        'plan_name':  limits['name'],
    }


def log_ai_call(
    user_id: int,
    provider: str,
    model: str,
    action: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    success: bool,
    duration_ms: int,
    conn,
) -> None:
    """Insert a row into ai_usage_log attributed to *user_id*.

    Errors are swallowed so a logging failure never interrupts the request.
    """
    try:
        conn.execute(
            """INSERT INTO ai_usage_log
               (user_id, provider, model, action,
                input_tokens, output_tokens, total_tokens, cost_usd,
                success, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id, provider, model, action,
                input_tokens, output_tokens, input_tokens + output_tokens,
                cost_usd, 1 if success else 0, duration_ms,
            ),
        )
        conn.commit()
    except Exception:
        pass
