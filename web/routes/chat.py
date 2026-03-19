"""Universal AI chat routes.

POST   /api/chat              — send a message, receive an AI response
GET    /api/chat/history      — retrieve conversation history (?limit=N, default 50)
DELETE /api/chat/history      — clear conversation history
"""
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request

from .decorators import login_required
from src.infrastructure.database import get_connection
from src.infrastructure.ai import get_ai_provider
from src.domain.services.chat_context import assemble_context, build_system_prompt

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")


# ---------------------------------------------------------------------------
# POST /api/chat
# ---------------------------------------------------------------------------

@chat_bp.route("", methods=["POST"])
@login_required
def send_message():
    """Send a user message, assemble full context, call AI, persist both turns."""
    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()

    if not user_message:
        return jsonify({"error": "message is required"}), 400

    # Resolve the AI provider
    provider = get_ai_provider("default")
    if not provider.is_available():
        return jsonify({"error": "No AI provider configured. Go to Settings > AI Providers."}), 503

    conn = get_connection()

    # Assemble live context from all modules
    try:
        context = assemble_context(conn)
    except Exception as exc:
        logger.error("Context assembly failed: %s", exc, exc_info=True)
        context = {}

    system_prompt = build_system_prompt(context)

    # Load last 10 messages for conversation continuity
    history_rows = conn.execute(
        """SELECT role, content FROM chat_messages
           ORDER BY created_at DESC, id DESC
           LIMIT 10"""
    ).fetchall()
    # Rows come back newest-first; reverse to chronological order
    prior_messages = [{"role": r["role"], "content": r["content"]} for r in reversed(history_rows)]

    # Append the current user turn
    conversation = prior_messages + [{"role": "user", "content": user_message}]

    # Persist the user message first (so it's stored even if AI fails)
    conn.execute(
        """INSERT INTO chat_messages (role, content, provider, model)
           VALUES (?, ?, ?, ?)""",
        ("user", user_message, "", ""),
    )
    conn.commit()

    # Call AI
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

    # Strip <think>...</think> reasoning tags (MiniMax includes these)
    import re
    ai_response = re.sub(r'<think>.*?</think>', '', ai_response, flags=re.DOTALL).strip()

    # Resolve provider/model metadata for storage
    provider_name = type(provider).__name__.replace("Provider", "").lower()
    model_name = getattr(provider, "model", "")

    # Persist the assistant response
    conn.execute(
        """INSERT INTO chat_messages (role, content, provider, model)
           VALUES (?, ?, ?, ?)""",
        ("assistant", ai_response, provider_name, model_name),
    )
    conn.commit()

    return jsonify({
        "response": ai_response,
        "provider": provider_name,
        "model": model_name,
    })


# ---------------------------------------------------------------------------
# GET /api/chat/history
# ---------------------------------------------------------------------------

@chat_bp.route("/history", methods=["GET"])
@login_required
def get_history():
    """Return conversation history, newest messages last."""
    try:
        limit = max(1, min(int(request.args.get("limit", 50)), 500))
    except (TypeError, ValueError):
        limit = 50

    conn = get_connection()
    rows = conn.execute(
        """SELECT id, role, content, provider, model, created_at
           FROM chat_messages
           ORDER BY created_at ASC, id ASC
           LIMIT ?""",
        (limit,),
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
    """Delete all chat messages."""
    conn = get_connection()
    conn.execute("DELETE FROM chat_messages")
    conn.commit()
    return "", 204
