"""Local simulator entry points; importing this package does not start Genesis."""
from .config import SimulatorConfig
from .api import env_list, make
from .history import StateRef

__all__ = ["SimulatorConfig", "StateRef", "env_list", "make", "Env", "SegmentRunner"]


def __getattr__(name):
    if name == "Env":
        from .env import Env
        return Env
    if name == "SegmentRunner":
        from .rollout_simulation.segment import SegmentRunner
        return SegmentRunner
    raise AttributeError(name)
