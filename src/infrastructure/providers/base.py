"""Abstract base class for task providers."""
from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TaskItem:
    """Unified task representation across providers."""
    id: str  # String to support external IDs
    title: str
    done: bool = False
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: int = 0
    description: str = ""
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Provider metadata
    provider: str = "native"
    external_id: Optional[str] = None


@dataclass
class ProjectItem:
    """Unified project representation across providers."""
    id: str
    title: str
    description: str = ""
    task_count: int = 0
    completed_count: int = 0
    
    # Provider metadata
    provider: str = "native"
    external_id: Optional[str] = None
    
    @property
    def progress(self) -> float:
        if self.task_count == 0:
            return 0.0
        return self.completed_count / self.task_count


class TaskProvider(ABC):
    """Abstract interface for task/project providers."""
    
    provider_name: str = "base"
    
    @abstractmethod
    def test_connection(self) -> bool:
        """Test if the provider is accessible."""
        pass
    
    @abstractmethod
    def get_projects(self) -> List[ProjectItem]:
        """Get all projects."""
        pass
    
    @abstractmethod
    def get_project(self, project_id: str) -> Optional[ProjectItem]:
        """Get a single project by ID."""
        pass
    
    @abstractmethod
    def get_tasks(self, project_id: Optional[str] = None) -> List[TaskItem]:
        """Get tasks, optionally filtered by project."""
        pass
    
    @abstractmethod
    def get_task(self, task_id: str) -> Optional[TaskItem]:
        """Get a single task by ID."""
        pass
    
    @abstractmethod
    def create_task(self, project_id: str, title: str, description: str = "", 
                   due_date: Optional[datetime] = None, priority: int = 0) -> TaskItem:
        """Create a new task."""
        pass
    
    @abstractmethod
    def update_task(self, task_id: str, title: Optional[str] = None,
                   description: Optional[str] = None, due_date: Optional[datetime] = None,
                   priority: Optional[int] = None) -> TaskItem:
        """Update an existing task."""
        pass
    
    @abstractmethod
    def complete_task(self, task_id: str) -> TaskItem:
        """Mark a task as complete."""
        pass
    
    @abstractmethod
    def uncomplete_task(self, task_id: str) -> TaskItem:
        """Mark a task as incomplete."""
        pass
    
    @abstractmethod
    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        pass
    
    def create_project(self, title: str, description: str = "") -> ProjectItem:
        """Create a new project (optional - not all providers support this)."""
        raise NotImplementedError(f"{self.provider_name} does not support project creation")
