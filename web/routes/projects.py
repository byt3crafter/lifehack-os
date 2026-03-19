"""Projects and tasks routes."""
from flask import Blueprint, jsonify, request

from .decorators import login_required, current_user_id
from src.domain.entities import Project
from src.infrastructure.database import get_connection
from src.infrastructure.providers import get_task_provider

projects_bp = Blueprint('projects', __name__, url_prefix='/api')


@projects_bp.route('/projects')
@login_required
def get_projects():
    uid = current_user_id()
    provider = get_task_provider()
    projects = provider.get_projects()
    return jsonify([{
        'id': p.id, 'title': p.title, 'name': p.title,
        'description': p.description,
        'task_count': p.task_count, 'completed_count': p.completed_count,
        'progress': p.progress, 'provider': p.provider
    } for p in projects])


@projects_bp.route('/projects', methods=['POST'])
@login_required
def create_project():
    uid = current_user_id()
    data = request.json
    conn = get_connection()

    cursor = conn.execute(
        """INSERT INTO projects (user_id, name, description, status, points_start, points_complete)
           VALUES (?, ?, ?, 'active', 10, 100)""",
        (uid, data['name'], data.get('description', ''))
    )
    conn.commit()
    project_id = cursor.lastrowid

    from src.infrastructure.database.repositories import StatsRepository
    stats_repo = StatsRepository()
    stats_repo.add_points('project', 10, f"Started: {data['name']}", project_id)
    return jsonify({'id': project_id, 'success': True}), 201


@projects_bp.route('/projects/<int:project_id>', methods=['PUT'])
@login_required
def update_project(project_id):
    """Update a project's name or description."""
    uid = current_user_id()
    data = request.json
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM projects WHERE id = ? AND user_id = ?", (project_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    conn.execute(
        "UPDATE projects SET name = ?, description = ? WHERE id = ? AND user_id = ?",
        (data.get('name'), data.get('description', ''), project_id, uid)
    )
    conn.commit()
    return jsonify({'success': True})


@projects_bp.route('/projects/<int:project_id>', methods=['DELETE'])
@login_required
def delete_project(project_id):
    """Delete a project and all its milestones/tasks."""
    uid = current_user_id()
    conn = get_connection()
    result = conn.execute(
        "DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, uid)
    )
    conn.commit()
    if result.rowcount == 0:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'success': True})


@projects_bp.route('/tasks')
@login_required
def get_tasks():
    uid = current_user_id()
    provider = get_task_provider()
    project_id = request.args.get('project_id')
    tasks = provider.get_tasks(project_id)
    return jsonify([{
        'id': t.id, 'title': t.title, 'done': t.done,
        'project_id': t.project_id, 'project_name': t.project_name,
        'due_date': t.due_date.isoformat() if t.due_date else None,
        'priority': t.priority, 'provider': t.provider
    } for t in tasks])


@projects_bp.route('/tasks', methods=['POST'])
@login_required
def create_task():
    uid = current_user_id()
    data = request.json
    provider = get_task_provider()
    task = provider.create_task(
        project_id=data['project_id'],
        title=data['title'],
        description=data.get('description', ''),
        priority=data.get('priority', 0)
    )
    return jsonify({'success': True, 'id': task.id, 'provider': task.provider})


@projects_bp.route('/tasks/<task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    """Edit a task's title, priority, or due date."""
    uid = current_user_id()
    data = request.json
    conn = get_connection()
    row = conn.execute(
        "SELECT t.id FROM tasks t "
        "JOIN projects p ON t.milestone_id IN (SELECT id FROM milestones WHERE project_id = p.id) "
        "WHERE t.id = ? AND p.user_id = ?",
        (task_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    conn.execute(
        "UPDATE tasks SET name = ? WHERE id = ?",
        (data.get('title', data.get('name')), task_id)
    )
    conn.commit()
    return jsonify({'success': True})


@projects_bp.route('/tasks/<task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    """Delete a task."""
    uid = current_user_id()
    conn = get_connection()
    # Verify ownership via project chain before deleting
    row = conn.execute(
        "SELECT t.id FROM tasks t "
        "JOIN milestones m ON t.milestone_id = m.id "
        "JOIN projects p ON m.project_id = p.id "
        "WHERE t.id = ? AND p.user_id = ?",
        (task_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    result = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    if result.rowcount == 0:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'success': True})


@projects_bp.route('/tasks/<task_id>/complete', methods=['POST'])
@login_required
def complete_task(task_id):
    uid = current_user_id()
    provider = get_task_provider()
    task = provider.complete_task(task_id)
    if task:
        from src.infrastructure.database.repositories import StatsRepository
        stats_repo = StatsRepository()
        stats_repo.add_points('task', 10, f"Completed: {task.title}")
        return jsonify({'success': True, 'points': 10})
    return jsonify({'error': 'Task not found'}), 404


@projects_bp.route('/tasks/<task_id>/uncomplete', methods=['POST'])
@login_required
def uncomplete_task(task_id):
    uid = current_user_id()
    provider = get_task_provider()
    task = provider.uncomplete_task(task_id)
    return jsonify({'success': True}) if task else (jsonify({'error': 'Not found'}), 404)


@projects_bp.route('/milestones/<int:milestone_id>/complete', methods=['POST'])
@login_required
def complete_milestone(milestone_id):
    uid = current_user_id()
    conn = get_connection()
    # Verify ownership
    row = conn.execute(
        "SELECT m.id FROM milestones m "
        "JOIN projects p ON m.project_id = p.id "
        "WHERE m.id = ? AND p.user_id = ?",
        (milestone_id, uid)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    conn.execute(
        "UPDATE milestones SET completed_at = CURRENT_TIMESTAMP WHERE id = ?",
        (milestone_id,)
    )
    conn.commit()

    from src.infrastructure.database.repositories import StatsRepository
    stats_repo = StatsRepository()
    stats_repo.add_points('milestone', 50, "Milestone completed", milestone_id)
    return jsonify({'success': True})
