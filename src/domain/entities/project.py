"""Project, Milestone, and Task entities."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List


class ProjectStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETE = "complete"
    ARCHIVED = "archived"


@dataclass
class Task:
    """A single task within a milestone."""
    id: Optional[int] = None
    milestone_id: int = 0
    name: str = ""
    points: int = 5
    completed_at: Optional[datetime] = None
    order: int = 0
    
    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None


@dataclass
class Milestone:
    """A milestone within a project."""
    id: Optional[int] = None
    project_id: int = 0
    name: str = ""
    points: int = 50
    order: int = 0
    completed_at: Optional[datetime] = None
    tasks: List[Task] = field(default_factory=list)
    
    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None
    
    @property
    def progress(self) -> float:
        if not self.tasks:
            return 1.0 if self.is_complete else 0.0
        completed = sum(1 for t in self.tasks if t.is_complete)
        return completed / len(self.tasks)


@dataclass
class Project:
    """A project with milestones and tasks."""
    id: Optional[int] = None
    name: str = ""
    description: str = ""
    status: ProjectStatus = ProjectStatus.ACTIVE
    points_start: int = 25
    points_complete: int = 100
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    milestones: List[Milestone] = field(default_factory=list)
    
    @property
    def is_complete(self) -> bool:
        return self.status == ProjectStatus.COMPLETE
    
    @property
    def progress(self) -> float:
        if not self.milestones:
            return 1.0 if self.is_complete else 0.0
        completed = sum(1 for m in self.milestones if m.is_complete)
        return completed / len(self.milestones)
