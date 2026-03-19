"""Task providers for LifeHack integrations."""
from .base import TaskProvider, TaskItem, ProjectItem
from .native import NativeTaskProvider
from .vikunja import VikunjaTaskProvider
from .firefly import FireflyProvider, FireflyAccount, FireflyTransaction
from .factory import (
    get_task_provider, get_integration_status,
    enable_vikunja, disable_vikunja,
    enable_firefly, disable_firefly, get_firefly_provider
)

__all__ = [
    'TaskProvider', 'TaskItem', 'ProjectItem',
    'NativeTaskProvider', 'VikunjaTaskProvider',
    'FireflyProvider', 'FireflyAccount', 'FireflyTransaction',
    'get_task_provider', 'get_integration_status',
    'enable_vikunja', 'disable_vikunja',
    'enable_firefly', 'disable_firefly', 'get_firefly_provider'
]
