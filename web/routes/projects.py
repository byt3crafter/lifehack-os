"""Projects and tasks routes."""
from flask import Blueprint, jsonify, request

from .decorators import login_required
from src.domain.entities import Project
from src.infrastructure.database.repositories import ProjectRepository, StatsRepository
from src.infrastructure.providers import get_task_provider

projects_bp = Blueprint('projects', __name__, url_prefix='/api')

project_repo = ProjectRepository()
stats_repo = StatsRepository()


@projects_bp.route('/projects')
@login_required
def get_projects():
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
    data = request.json
    project = Project(name=data['name'], description=data.get('description', ''))
    project = project_repo.create(project)
    stats_repo.add_points('project', project.points_start, f"Started: {project.name}", project.id)
    return jsonify({'id': project.id, 'success': True})


@projects_bp.route('/tasks')
@login_required
def get_tasks():
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
    data = request.json
    provider = get_task_provider()
    task = provider.create_task(
        project_id=data['project_id'],
        title=data['title'],
        description=data.get('description', ''),
        priority=data.get('priority', 0)
    )
    return jsonify({'success': True, 'id': task.id, 'provider': task.provider})


@projects_bp.route('/tasks/<task_id>/complete', methods=['POST'])
@login_required
def complete_task(task_id):
    provider = get_task_provider()
    task = provider.complete_task(task_id)
    if task:
        stats_repo.add_points('task', 10, f"Completed: {task.title}")
        return jsonify({'success': True, 'points': 10})
    return jsonify({'error': 'Task not found'}), 404


@projects_bp.route('/tasks/<task_id>/uncomplete', methods=['POST'])
@login_required
def uncomplete_task(task_id):
    provider = get_task_provider()
    task = provider.uncomplete_task(task_id)
    return jsonify({'success': True}) if task else (jsonify({'error': 'Not found'}), 404)


@projects_bp.route('/milestones/<int:milestone_id>/complete', methods=['POST'])
@login_required
def complete_milestone(milestone_id):
    project_repo.complete_milestone(milestone_id)
    stats_repo.add_points('milestone', 50, "Milestone completed", milestone_id)
    return jsonify({'success': True})
