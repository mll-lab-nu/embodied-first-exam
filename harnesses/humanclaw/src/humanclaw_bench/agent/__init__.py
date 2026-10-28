"""Public agent interfaces for HumanClawBench."""

from .skills import SkillCall

__all__ = ["PSVEgoAgent", "SkillCall"]


def __getattr__(name: str):
    """Load the PSV agent lazily so native skill imports cannot form a cycle."""
    # Native harnesses import skills without loading the PSV planner, which in
    # turn imports experiments.integration while that module is initializing.
    if name == "PSVEgoAgent":
        from .ego_agent import PSVEgoAgent
        return PSVEgoAgent
    raise AttributeError(name)
