"""Native task provider using local SQLite database."""
from typing import List, Optional
from datetime import datetime

from .base import TaskProvider, TaskItem, ProjectItem
from ..database.repositories import ProjectRepository
from ...domain.entities.project import Project, Task, Milestone, ProjectStatus


class NativeTaskProvider(TaskProvider):
    """Task provider using the native LifeHack database."""
    
    provider_name = "native"
    
    def __init__(self, user_id: int = None):
        self._user_id = user_id
        self.repo = ProjectRepository(user_id or 1)
    
    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            self.repo.get_all()
            return True
        except Exception:
            return False
    
    def get_projects(self) -> List[ProjectItem]:
        """Get all active projects."""
        projects = self.repo.get_all(include_completed=False)
        return [self._project_to_item(p) for p in projects]
    
    def get_project(self, project_id: str) -> Optional[ProjectItem]:
        """Get a single project."""
        project = self.repo.get_by_id(int(project_id))
        return self._project_to_item(project) if project else None
    
    def get_tasks(self, project_id: Optional[str] = None) -> List[TaskItem]:
        """Get all tasks, optionally filtered by project."""
        tasks = []
        projects = self.repo.get_all(include_completed=True)
        
        for project in projects:
            if project_id and str(project.id) != project_id:
                continue
            for milestone in project.milestones:
                for task in milestone.tasks:
                    tasks.append(self._task_to_item(task, project, milestone))
        
        return tasks
    
    def get_task(self, task_id: str) -> Optional[TaskItem]:
        """Get a single task by ID."""
        # Native tasks are nested, need to search
        for task in self.get_tasks():
            if task.id == task_id:
                return task
        return None
    
    def create_task(self, project_id: str, title: str, description: str = "",
                   due_date: Optional[datetime] = None, priority: int = 0) -> TaskItem:
        """Create a new task in a project's first milestone."""
        project = self.repo.get_by_id(int(project_id))
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        # Use first milestone or create one
        if not project.milestones:
            milestone = Milestone(project_id=project.id, name="Tasks", order=0)
            milestone = self.repo.add_milestone(milestone)
        else:
            milestone = project.milestones[0]
        
        # Create task (native schema uses milestones)
        task = Task(
            milestone_id=milestone.id,
            name=title,
            order=len(milestone.tasks)
        )
        # Note: Native schema doesn't have direct task creation - simplified
        # In production, would need to add task creation to repository
        
        return TaskItem(
            id=str(task.id or 0),
            title=title,
            done=False,
            project_id=str(project.id),
            project_name=project.name,
            provider="native"
        )
    
    def update_task(self, task_id: str, title: Optional[str] = None,
                   description: Optional[str] = None, due_date: Optional[datetime] = None,
                   priority: Optional[int] = None) -> TaskItem:
        """Update a task."""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        # Native implementation would update via repo
        if title:
            task.title = title
        return task
    
    def complete_task(self, task_id: str) -> TaskItem:
        """Mark task as complete."""
        # Would call repo method
        task = self.get_task(task_id)
        if task:
            task.done = True
            task.completed_at = datetime.now()
        return task
    
    def uncomplete_task(self, task_id: str) -> TaskItem:
        """Mark task as incomplete."""
        task = self.get_task(task_id)
        if task:
            task.done = False
            task.completed_at = None
        return task
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        # Would call repo delete method
        return True
    
    def create_project(self, title: str, description: str = "") -> ProjectItem:
        """Create a new project."""
        project = Project(name=title, description=description)
        project = self.repo.create(project)
        return self._project_to_item(project)
    
    def _project_to_item(self, project: Project) -> ProjectItem:
        """Convert native Project to ProjectItem."""
        task_count = sum(len(m.tasks) for m in project.milestones)
        completed = sum(1 for m in project.milestones for t in m.tasks if t.is_complete)
        
        return ProjectItem(
            id=str(project.id),
            title=project.name,
            description=project.description,
            task_count=task_count,
            completed_count=completed,
            provider="native",
            external_id=str(project.id)
        )
    
    def _task_to_item(self, task: Task, project: Project, milestone: Milestone) -> TaskItem:
        """Convert native Task to TaskItem."""
        return TaskItem(
            id=str(task.id),
            title=task.name,
            done=task.is_complete,
            project_id=str(project.id),
            project_name=project.name,
            completed_at=task.completed_at,
            provider="native",
            external_id=str(task.id)
        )
