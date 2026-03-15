"""Vikunja task provider for external task management."""
import requests
from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass

from .base import TaskProvider, TaskItem, ProjectItem


@dataclass
class VikunjaConfig:
    """Vikunja API configuration."""
    api_url: str = "https://tasks.micinthe.com/api/v1"
    username: str = ""
    password: str = ""
    token: str = ""
    token_expires: Optional[datetime] = None


class VikunjaTaskProvider(TaskProvider):
    """Task provider using Vikunja API."""
    
    provider_name = "vikunja"
    
    def __init__(self, config: Optional[VikunjaConfig] = None):
        self.config = config or VikunjaConfig()
        self._token: Optional[str] = None
    
    def _get_token(self) -> str:
        """Get or refresh JWT token."""
        if self._token:
            return self._token
        
        if self.config.token:
            self._token = self.config.token
            return self._token
        
        # Authenticate
        resp = requests.post(
            f"{self.config.api_url}/login",
            json={"username": self.config.username, "password": self.config.password},
            timeout=10
        )
        resp.raise_for_status()
        self._token = resp.json().get("token")
        return self._token
    
    def _headers(self) -> dict:
        """Get auth headers."""
        return {"Authorization": f"Bearer {self._get_token()}"}
    
    def _get(self, endpoint: str) -> dict:
        """GET request to Vikunja API."""
        resp = requests.get(
            f"{self.config.api_url}{endpoint}",
            headers=self._headers(),
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()
    
    def _post(self, endpoint: str, data: dict) -> dict:
        """POST request to Vikunja API."""
        resp = requests.post(
            f"{self.config.api_url}{endpoint}",
            headers=self._headers(),
            json=data,
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()
    
    def _put(self, endpoint: str, data: dict) -> dict:
        """PUT request to Vikunja API."""
        resp = requests.put(
            f"{self.config.api_url}{endpoint}",
            headers=self._headers(),
            json=data,
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()
    
    def _delete(self, endpoint: str) -> bool:
        """DELETE request to Vikunja API."""
        resp = requests.delete(
            f"{self.config.api_url}{endpoint}",
            headers=self._headers(),
            timeout=15
        )
        return resp.status_code in (200, 204)
    
    def test_connection(self) -> bool:
        """Test Vikunja API connection."""
        try:
            self._get_token()
            self._get("/user")
            return True
        except Exception:
            return False
    
    def get_projects(self) -> List[ProjectItem]:
        """Get all Vikunja projects."""
        data = self._get("/projects")
        return [self._project_from_api(p) for p in data if p.get("title")]
    
    def get_project(self, project_id: str) -> Optional[ProjectItem]:
        """Get a single project."""
        try:
            data = self._get(f"/projects/{project_id}")
            return self._project_from_api(data)
        except Exception:
            return None
    
    def get_tasks(self, project_id: Optional[str] = None) -> List[TaskItem]:
        """Get tasks, optionally filtered by project."""
        if project_id:
            data = self._get(f"/projects/{project_id}/tasks")
        else:
            # Get all tasks across projects
            data = self._get("/tasks/all")
        
        return [self._task_from_api(t) for t in data]
    
    def get_task(self, task_id: str) -> Optional[TaskItem]:
        """Get a single task."""
        try:
            data = self._get(f"/tasks/{task_id}")
            return self._task_from_api(data)
        except Exception:
            return None
    
    def create_task(self, project_id: str, title: str, description: str = "",
                   due_date: Optional[datetime] = None, priority: int = 0) -> TaskItem:
        """Create a new task in Vikunja."""
        payload = {
            "title": title,
            "description": description,
            "priority": priority
        }
        if due_date:
            payload["due_date"] = due_date.isoformat()
        
        data = self._put(f"/projects/{project_id}/tasks", payload)
        return self._task_from_api(data)
    
    def update_task(self, task_id: str, title: Optional[str] = None,
                   description: Optional[str] = None, due_date: Optional[datetime] = None,
                   priority: Optional[int] = None) -> TaskItem:
        """Update an existing task."""
        payload = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if due_date is not None:
            payload["due_date"] = due_date.isoformat()
        if priority is not None:
            payload["priority"] = priority
        
        data = self._post(f"/tasks/{task_id}", payload)
        return self._task_from_api(data)
    
    def complete_task(self, task_id: str) -> TaskItem:
        """Mark task as complete in Vikunja."""
        data = self._post(f"/tasks/{task_id}", {"done": True})
        return self._task_from_api(data)
    
    def uncomplete_task(self, task_id: str) -> TaskItem:
        """Mark task as incomplete."""
        data = self._post(f"/tasks/{task_id}", {"done": False})
        return self._task_from_api(data)
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        return self._delete(f"/tasks/{task_id}")
    
    def create_project(self, title: str, description: str = "") -> ProjectItem:
        """Create a new project in Vikunja."""
        data = self._put("/projects", {
            "title": title,
            "description": description
        })
        return self._project_from_api(data)
    
    def _project_from_api(self, data: dict) -> ProjectItem:
        """Convert Vikunja project to ProjectItem."""
        return ProjectItem(
            id=str(data.get("id", "")),
            title=data.get("title", ""),
            description=data.get("description", ""),
            task_count=data.get("task_count", 0),
            completed_count=0,  # Vikunja doesn't return this directly
            provider="vikunja",
            external_id=str(data.get("id", ""))
        )
    
    def _task_from_api(self, data: dict) -> TaskItem:
        """Convert Vikunja task to TaskItem."""
        due_date = None
        if data.get("due_date"):
            try:
                due_date = datetime.fromisoformat(data["due_date"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        
        created_at = None
        if data.get("created"):
            try:
                created_at = datetime.fromisoformat(data["created"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        
        completed_at = None
        if data.get("done_at"):
            try:
                completed_at = datetime.fromisoformat(data["done_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        
        return TaskItem(
            id=str(data.get("id", "")),
            title=data.get("title", ""),
            done=bool(data.get("done", False)),
            project_id=str(data.get("project_id", "")),
            project_name=None,  # Vikunja doesn't include this in task response
            due_date=due_date,
            priority=data.get("priority", 0),
            description=data.get("description", ""),
            created_at=created_at,
            completed_at=completed_at,
            provider="vikunja",
            external_id=str(data.get("id", ""))
        )
