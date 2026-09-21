"""Task-independent, irreversible segmented interaction for coding agents."""

from .protocol import TaskAdapter
from .session import Session

__all__ = ["Session", "TaskAdapter"]
