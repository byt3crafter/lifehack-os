"""Deep Work routes — projects, sessions, reports, and Vikunja integration."""
import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from .decorators import login_required
from src.infrastructure.database import get_connection
from src.infrastructure.database.repositories import StatsRepository
from src.infrastructure.plugins import plugin_registry

logger = logging.getLogger(__name__)

deepwork_bp = Blueprint("deepwork", __name__, url_prefix="/api/deepwork")

stats_repo = StatsRepository()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_vikunja_provider():
    """Return a ready VikunjaTaskProvider when the plugin is enabled, else None."""
    try:
        if not plugin_registry.has("vikunja"):
            return None
        stored = plugin_registry.get_config("vikunja")
        if not stored.get("enabled"):
            return None
        plugin = plugin_registry.get("vikunja")
        return plugin.get_provider(stored.get("config", {}))
    except Exception:
        logger.debug("Could not get Vikunja provider", exc_info=True)
        return None


def _project_row_to_dict(row) -> dict:
    """Convert a sqlite3.Row from deep_work_projects to a plain dict."""
    return {
        "id":            row["id"],
        "name":          row["name"],
        "description":   row["description"] or "",
        "color":         row["color"] or "#4f80ff",
        "active":        bool(row["active"]),
        "total_minutes": row["total_minutes"] or 0,
        "created_at":    row["created_at"],
        "source":        "local",
    }


def _session_row_to_dict(row) -> dict:
    """Convert a deep_work_sessions row to a plain dict, resolving project name."""
    d = dict(row)
    # Ensure consistent key names regardless of JOIN aliases present
    if "project_name" not in d:
        d["project_name"] = None
    return d


def _update_project_minutes(conn, local_project_id: int) -> None:
    """Recompute and store total_minutes for a local project."""
    if not local_project_id:
        return
    row = conn.execute(
        "SELECT COALESCE(SUM(duration_minutes), 0) as total FROM deep_work_sessions "
        "WHERE local_project_id = ? AND ended_at IS NOT NULL",
        (local_project_id,),
    ).fetchone()
    conn.execute(
        "UPDATE deep_work_projects SET total_minutes = ? WHERE id = ?",
        (row["total"], local_project_id),
    )


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@deepwork_bp.route("/projects")
@login_required
def list_projects():
    """List local projects merged with Vikunja projects (if connected)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM deep_work_projects WHERE active = 1 ORDER BY name"
    ).fetchall()
    projects = [_project_row_to_dict(r) for r in rows]

    # Merge Vikunja projects when the plugin is active
    provider = _get_vikunja_provider()
    if provider:
        try:
            vk_projects = provider.get_projects()
            for vp in vk_projects:
                projects.append({
                    "id":            f"vk_{vp.id}",
                    "name":          vp.title,
                    "description":   vp.description or "",
                    "color":         "#8b5cf6",
                    "active":        True,
                    "total_minutes": 0,
                    "created_at":    None,
                    "source":        "vikunja",
                    "task_count":    vp.task_count,
                })
        except Exception:
            logger.warning("Could not fetch Vikunja projects", exc_info=True)

    return jsonify(projects)


@deepwork_bp.route("/projects", methods=["POST"])
@login_required
def create_project():
    """Create a new local deep-work project."""
    data = request.json or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    description = (data.get("description") or "").strip()
    color = (data.get("color") or "#4f80ff").strip()

    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO deep_work_projects (name, description, color) VALUES (?, ?, ?)",
        (name, description, color),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM deep_work_projects WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return jsonify(_project_row_to_dict(row)), 201


@deepwork_bp.route("/projects/<int:project_id>", methods=["DELETE"])
@login_required
def delete_project(project_id):
    """Soft-delete a local project (sets active = 0)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM deep_work_projects WHERE id = ?", (project_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404

    # Disassociate sessions so they are not orphaned under a deleted project
    conn.execute(
        "UPDATE deep_work_sessions SET local_project_id = NULL WHERE local_project_id = ?",
        (project_id,),
    )
    conn.execute(
        "UPDATE deep_work_projects SET active = 0 WHERE id = ?", (project_id,)
    )
    conn.commit()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Session status
# ---------------------------------------------------------------------------

@deepwork_bp.route("/status")
@login_required
def get_status():
    """Return the active session (if any) and recent history."""
    conn = get_connection()

    active = conn.execute(
        """SELECT dw.*,
                  COALESCE(dwp.name, p.name) AS project_name
           FROM   deep_work_sessions dw
           LEFT JOIN deep_work_projects dwp ON dw.local_project_id = dwp.id
           LEFT JOIN projects          p   ON dw.project_id = p.id
           WHERE  dw.ended_at IS NULL
           ORDER  BY dw.started_at DESC
           LIMIT  1"""
    ).fetchone()

    history = conn.execute(
        """SELECT dw.*,
                  COALESCE(dwp.name, p.name) AS project_name
           FROM   deep_work_sessions dw
           LEFT JOIN deep_work_projects dwp ON dw.local_project_id = dwp.id
           LEFT JOIN projects          p   ON dw.project_id = p.id
           WHERE  dw.ended_at IS NOT NULL
           ORDER  BY dw.ended_at DESC
           LIMIT  10"""
    ).fetchall()

    return jsonify({
        "active":  _session_row_to_dict(active) if active else None,
        "history": [_session_row_to_dict(r) for r in history],
    })


# ---------------------------------------------------------------------------
# Start / end sessions
# ---------------------------------------------------------------------------

@deepwork_bp.route("/start", methods=["POST"])
@login_required
def start_session():
    """Start a deep-work session.

    Body (all optional):
        project_id      int   — existing local deep_work_projects.id
        project_name    str   — create a new local project on the fly
        notes           str
        vikunja_task_id str   — Vikunja task to associate
        description     str   — session description
    """
    data = request.json or {}
    conn = get_connection()

    # Auto-close any open session
    conn.execute(
        "UPDATE deep_work_sessions SET ended_at = CURRENT_TIMESTAMP WHERE ended_at IS NULL"
    )

    local_project_id = data.get("project_id")
    vikunja_task_id  = data.get("vikunja_task_id")
    notes            = (data.get("notes") or "").strip()
    description      = (data.get("description") or "").strip()

    # Create project on the fly when only a name is supplied
    if not local_project_id and data.get("project_name"):
        pname = data["project_name"].strip()
        if pname:
            cursor = conn.execute(
                "INSERT INTO deep_work_projects (name) VALUES (?)", (pname,)
            )
            local_project_id = cursor.lastrowid

    cursor = conn.execute(
        """INSERT INTO deep_work_sessions
               (local_project_id, vikunja_task_id, notes, description)
           VALUES (?, ?, ?, ?)""",
        (local_project_id, vikunja_task_id, notes, description),
    )
    conn.commit()
    return jsonify({"success": True, "id": cursor.lastrowid}), 201


@deepwork_bp.route("/end", methods=["POST"])
@login_required
def end_session():
    """End the currently active deep-work session."""
    conn = get_connection()
    active = conn.execute(
        "SELECT id, started_at, local_project_id FROM deep_work_sessions WHERE ended_at IS NULL"
    ).fetchone()
    if not active:
        return jsonify({"error": "No active session"}), 400

    start_at  = datetime.fromisoformat(active["started_at"].replace(" ", "T"))
    end_at    = datetime.now()
    duration  = int((end_at - start_at).total_seconds() / 60)
    points    = int(duration / 10) * 5

    conn.execute(
        """UPDATE deep_work_sessions
           SET ended_at = ?, duration_minutes = ?, points_earned = ?
           WHERE id = ?""",
        (end_at.isoformat(), duration, points, active["id"]),
    )

    # Keep project total_minutes in sync
    if active["local_project_id"]:
        _update_project_minutes(conn, active["local_project_id"])

    stats_repo.add_points("deepwork", points, f"Deep Work: {duration} mins")
    conn.commit()
    return jsonify({"success": True, "duration": duration, "points": points})


# ---------------------------------------------------------------------------
# Delete a session
# ---------------------------------------------------------------------------

@deepwork_bp.route("/sessions/<int:session_id>", methods=["DELETE"])
@login_required
def delete_session(session_id):
    """Delete a completed session and recompute the project total."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, local_project_id FROM deep_work_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404

    local_project_id = row["local_project_id"]
    conn.execute("DELETE FROM deep_work_sessions WHERE id = ?", (session_id,))

    if local_project_id:
        _update_project_minutes(conn, local_project_id)

    conn.commit()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@deepwork_bp.route("/report")
@login_required
def get_report():
    """Return weekly and monthly aggregated deep-work stats."""
    conn = get_connection()

    now       = datetime.now()
    week_start  = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _hours_by_project(since: datetime) -> list[dict]:
        rows = conn.execute(
            """SELECT COALESCE(dwp.name, p.name, 'Unknown') AS project_name,
                      COALESCE(dw.local_project_id, dw.project_id)  AS project_id,
                      SUM(dw.duration_minutes) AS total_minutes,
                      COUNT(*)                 AS session_count
               FROM   deep_work_sessions dw
               LEFT JOIN deep_work_projects dwp ON dw.local_project_id = dwp.id
               LEFT JOIN projects          p   ON dw.project_id = p.id
               WHERE  dw.ended_at IS NOT NULL
                 AND  dw.started_at >= ?
               GROUP  BY project_name
               ORDER  BY total_minutes DESC""",
            (since.isoformat(),),
        ).fetchall()
        return [
            {
                "project_name":  r["project_name"],
                "project_id":    r["project_id"],
                "total_minutes": r["total_minutes"] or 0,
                "total_hours":   round((r["total_minutes"] or 0) / 60, 2),
                "session_count": r["session_count"],
            }
            for r in rows
        ]

    def _totals(since: datetime) -> dict:
        row = conn.execute(
            """SELECT COUNT(*)                 AS sessions,
                      COALESCE(SUM(duration_minutes), 0) AS total_minutes,
                      COALESCE(AVG(duration_minutes), 0) AS avg_minutes
               FROM   deep_work_sessions
               WHERE  ended_at IS NOT NULL
                 AND  started_at >= ?""",
            (since.isoformat(),),
        ).fetchone()
        return {
            "sessions":      row["sessions"],
            "total_minutes": row["total_minutes"],
            "total_hours":   round(row["total_minutes"] / 60, 2),
            "avg_minutes":   round(row["avg_minutes"], 1),
        }

    return jsonify({
        "week": {
            "start":   week_start.isoformat(),
            "totals":  _totals(week_start),
            "projects": _hours_by_project(week_start),
        },
        "month": {
            "start":   month_start.isoformat(),
            "totals":  _totals(month_start),
            "projects": _hours_by_project(month_start),
        },
    })


# ---------------------------------------------------------------------------
# Vikunja tasks for a project
# ---------------------------------------------------------------------------

@deepwork_bp.route("/vikunja-tasks")
@login_required
def vikunja_tasks():
    """Return Vikunja tasks for a given project_id (?project_id=X)."""
    provider = _get_vikunja_provider()
    if not provider:
        return jsonify({"enabled": False, "tasks": []})

    project_id = request.args.get("project_id")
    try:
        tasks = provider.get_tasks(project_id=project_id)
    except Exception:
        logger.warning("Failed to fetch Vikunja tasks", exc_info=True)
        return jsonify({"error": "Could not fetch tasks from Vikunja"}), 502

    return jsonify({
        "enabled": True,
        "tasks": [
            {
                "id":          t.id,
                "title":       t.title,
                "done":        t.done,
                "priority":    t.priority,
                "description": t.description or "",
                "due_date":    t.due_date.isoformat() if t.due_date else None,
                "project_id":  t.project_id,
            }
            for t in tasks
        ],
    })
