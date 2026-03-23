"""Universal AI chat routes.

POST   /api/chat              — send a message, receive an AI response
GET    /api/chat/history      — retrieve conversation history (?limit=N, default 50)
DELETE /api/chat/history      — clear conversation history
"""
import json
import logging
import re
from datetime import datetime
from flask import Blueprint, jsonify, request

from .decorators import login_required, current_user_id
from src.infrastructure.database import get_connection
from src.infrastructure.ai import get_ai_provider
from src.domain.services.chat_context import assemble_context, build_system_prompt
from src.domain.services.chat_tools import TOOL_DEFINITIONS
from src.domain.services.chat_tool_executor import execute_tool

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")

# Matches: [TOOL: tool_name] {"key": "value", ...}
# The JSON block may span multiple lines, so re.DOTALL is required.
_TOOL_PATTERN = re.compile(r'\[TOOL:\s*(\w+)\]\s*(\{.*?\})', re.DOTALL)
_THINK_PATTERN = re.compile(r'<think>.*?</think>', re.DOTALL)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks (e.g. MiniMax)."""
    return _THINK_PATTERN.sub('', text).strip()


def _parse_and_execute_tools(ai_response: str, conn, user_id: int) -> tuple[str, list]:
    """Find [TOOL: ...] calls in *ai_response*, execute them, return results.

    Returns:
        clean_response  — the AI text with tool-call lines removed
        tool_results    — list of {tool, args, result} dicts
    """
    matches = _TOOL_PATTERN.findall(ai_response)
    if not matches:
        return ai_response, []

    results = []
    for tool_name, args_json in matches:
        try:
            args = json.loads(args_json)
        except json.JSONDecodeError:
            logger.warning("Could not parse tool args JSON for '%s': %s", tool_name, args_json)
            args = {}

        result = execute_tool(tool_name, args, conn, user_id)
        logger.info("Tool '%s' executed — result: %s", tool_name, result)
        results.append({"tool": tool_name, "args": args, "result": result})

    # Strip tool-call lines from the visible response
    clean_response = _TOOL_PATTERN.sub('', ai_response).strip()

    return clean_response, results


# ---------------------------------------------------------------------------
# POST /api/chat
# ---------------------------------------------------------------------------

@chat_bp.route("", methods=["POST"])
@login_required
def send_message():
    """Send a user message, assemble full context, call AI, persist both turns."""
    uid = current_user_id()
    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()
    image_base64 = (data.get("image_base64") or "").strip()
    conversation_id = data.get("conversation_id")  # optional

    if not user_message:
        return jsonify({"error": "message is required"}), 400

    conn = get_connection()

    # Validate conversation ownership if provided
    conv_category = 'general'
    if conversation_id:
        conv = conn.execute(
            "SELECT id, category FROM chat_conversations WHERE id = ? AND user_id = ?",
            (conversation_id, uid),
        ).fetchone()
        if not conv:
            return jsonify({"error": "Conversation not found"}), 404
        conv_category = conv['category'] or 'general'

    # Check daily AI usage limits before touching the provider
    from src.infrastructure.ai.usage import check_ai_usage
    usage = check_ai_usage(uid, conn)
    if not usage['allowed']:
        return jsonify({
            'error': (
                f"Daily AI limit reached ({usage['used']}/{usage['limit']} calls). "
                "Upgrade your plan for more."
            ),
            'usage': usage,
        }), 429

    # Resolve the AI provider — pass user_id so BYOK keys are respected
    provider = get_ai_provider("default", user_id=uid)
    if not provider.is_available():
        return jsonify({"error": "No AI provider configured. Go to Settings > AI Providers."}), 503

    # Assemble live context from all modules
    try:
        context = assemble_context(conn, uid)
    except Exception as exc:
        logger.error("Context assembly failed: %s", exc, exc_info=True)
        context = {}

    system_prompt = build_system_prompt(context, tools=TOOL_DEFINITIONS, category=conv_category)

    # Add receipt scanning instructions when image is present
    if image_base64:
        system_prompt += (
            "\n\n## Receipt Scanner\n"
            "The user has attached an image. If it is a receipt, extract:\n"
            "- Merchant/store name\n"
            "- Total amount\n"
            "- Date (if visible)\n"
            "- Category (food, clothing, electronics, entertainment, health, transport, or other)\n\n"
            "Then call the log_transaction tool to record it. Example:\n"
            '[TOOL: log_transaction] {"description": "Walmart Grocery", "amount": 45.67, '
            '"category": "food", "date": "2026-03-15", "type": "withdrawal"}\n\n'
            "If it's not a receipt, describe what you see and respond normally."
        )

    # Load last 10 messages for conversation continuity
    if conversation_id:
        history_rows = conn.execute(
            """SELECT role, content FROM chat_messages
               WHERE user_id = ? AND conversation_id = ?
               ORDER BY created_at DESC, id DESC
               LIMIT 10""",
            (uid, conversation_id),
        ).fetchall()
    else:
        history_rows = conn.execute(
            """SELECT role, content FROM chat_messages
               WHERE user_id = ? AND conversation_id IS NULL
               ORDER BY created_at DESC, id DESC
               LIMIT 10""",
            (uid,),
        ).fetchall()
    # Rows come back newest-first; reverse to chronological order
    prior_messages = [{"role": r["role"], "content": r["content"]} for r in reversed(history_rows)]

    # Build the current user turn — include image for vision models
    if image_base64:
        user_content = [
            {"type": "text", "text": user_message},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}",
                    "detail": "low",
                },
            },
        ]
        user_turn = {"role": "user", "content": user_content}
    else:
        user_turn = {"role": "user", "content": user_message}

    conversation = prior_messages + [user_turn]

    # Persist the user message first (so it's stored even if AI fails)
    conn.execute(
        """INSERT INTO chat_messages (user_id, role, content, provider, model, conversation_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (uid, "user", user_message, "", "", conversation_id),
    )
    conn.commit()

    # ── First AI call ────────────────────────────────────────────────────────
    try:
        ai_response = provider.chat_with_context(system_prompt, conversation)
    except Exception as exc:
        logger.error("AI chat call failed: %s", exc, exc_info=True)
        try:
            from web.routes.app_log import log_event
            import traceback
            log_event("error", "ai", f"chat_with_context failed: {exc}", traceback.format_exc())
        except Exception:
            pass
        return jsonify({"error": "AI request failed. Please try again."}), 500

    if not ai_response:
        return jsonify({"error": "AI returned an empty response. Check provider settings."}), 502

    # Strip <think> tags before processing
    ai_response = _strip_think_tags(ai_response)

    # ── Tool execution ───────────────────────────────────────────────────────
    clean_response, tool_results = _parse_and_execute_tools(ai_response, conn, uid)

    if tool_results:
        # Feed tool results back to the AI for a concise user-facing summary
        tool_summary = json.dumps(tool_results, default=str)
        followup_messages = conversation + [
            {"role": "assistant", "content": ai_response},
            {
                "role": "user",
                "content": (
                    f"[TOOL RESULTS] {tool_summary}\n\n"
                    "Summarise what just happened in 1-2 friendly sentences for the user. "
                    "Do NOT repeat the raw JSON. Do NOT call any more tools."
                ),
            },
        ]

        try:
            final_response = provider.chat_with_context(system_prompt, followup_messages)
            final_response = _strip_think_tags(final_response)
            # Make sure the follow-up didn't inject new tool calls
            final_response = _TOOL_PATTERN.sub('', final_response).strip()
            if final_response:
                clean_response = final_response
        except Exception as exc:
            logger.warning("Follow-up AI call after tool execution failed: %s", exc)
            # Fall back to the cleaned first response (tool calls stripped)

        if not clean_response:
            clean_response = "Done!"

    # ── Resolve provider/model metadata for storage ──────────────────────────
    provider_name = type(provider).__name__.replace("Provider", "").lower()
    model_name = getattr(provider, "model", "")

    # Persist the assistant response (cleaned — no [TOOL: ...] lines)
    conn.execute(
        """INSERT INTO chat_messages (user_id, role, content, provider, model, conversation_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (uid, "assistant", clean_response, provider_name, model_name, conversation_id),
    )
    conn.commit()

    # Update conversation's last_message_at
    if conversation_id:
        conn.execute(
            "UPDATE chat_conversations SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,),
        )
        conn.commit()

    # ── Log AI usage for rate-limiting / billing ──────────────────────────────
    from src.infrastructure.ai.usage import log_ai_call
    input_tok = getattr(provider, '_last_input_tokens', 0) or 0
    output_tok = getattr(provider, '_last_output_tokens', 0) or 0
    cost = getattr(provider, '_last_cost_usd', 0.0) or 0.0
    duration = getattr(provider, '_last_duration_ms', 0) or 0
    log_ai_call(
        user_id=uid,
        provider=provider_name,
        model=model_name,
        action='chat',
        input_tokens=input_tok,
        output_tokens=output_tok,
        cost_usd=cost,
        success=True,
        duration_ms=duration,
        conn=conn,
    )

    response_payload = {
        "response": clean_response,
        "provider": provider_name,
        "model": model_name,
    }
    if tool_results:
        response_payload["tools_used"] = [r["tool"] for r in tool_results]

    return jsonify(response_payload)


# ---------------------------------------------------------------------------
# GET /api/chat/history
# ---------------------------------------------------------------------------

@chat_bp.route("/history", methods=["GET"])
@login_required
def get_history():
    """Return conversation history, newest messages last."""
    uid = current_user_id()
    try:
        limit = max(1, min(int(request.args.get("limit", 50)), 500))
    except (TypeError, ValueError):
        limit = 50

    conn = get_connection()

    # Check if bookmarked column exists (migration may not have run)
    msg_cols = [r[1] for r in conn.execute("PRAGMA table_info(chat_messages)").fetchall()]
    bm_col = "COALESCE(bookmarked, 0) as bookmarked" if 'bookmarked' in msg_cols else "0 as bookmarked"

    # Subquery gets the last N messages, outer query re-orders them chronologically
    rows = conn.execute(
        f"""SELECT * FROM (
               SELECT id, role, content, provider, model, created_at, {bm_col}
               FROM chat_messages
               WHERE user_id = ?
               ORDER BY created_at DESC, id DESC
               LIMIT ?
           ) ORDER BY created_at ASC, id ASC""",
        (uid, limit),
    ).fetchall()

    return jsonify({
        "messages": [
            {
                "id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "provider": r["provider"],
                "model": r["model"],
                "created_at": r["created_at"],
                "bookmarked": r["bookmarked"],
            }
            for r in rows
        ]
    })


# ---------------------------------------------------------------------------
# DELETE /api/chat/history
# ---------------------------------------------------------------------------

@chat_bp.route("/history", methods=["DELETE"])
@login_required
def clear_history():
    """Delete all chat messages for the current user."""
    uid = current_user_id()
    conn = get_connection()
    conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (uid,))
    conn.commit()
    return "", 204
