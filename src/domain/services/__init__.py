"""Domain services."""
from .habit_strength import (
    calculate_strength_change,
    calculate_miss_penalty,
    get_strength_label,
    should_unlock_next_phase,
)
from .micro_task_verification import (
    VerificationResult,
    verify_micro_task,
    verify_phase_tasks,
    are_all_tasks_complete,
)
from .chat_tools import TOOL_DEFINITIONS
from .chat_tool_executor import execute_tool

__all__ = [
    'calculate_strength_change',
    'calculate_miss_penalty',
    'get_strength_label',
    'should_unlock_next_phase',
    'VerificationResult',
    'verify_micro_task',
    'verify_phase_tasks',
    'are_all_tasks_complete',
    'TOOL_DEFINITIONS',
    'execute_tool',
]
