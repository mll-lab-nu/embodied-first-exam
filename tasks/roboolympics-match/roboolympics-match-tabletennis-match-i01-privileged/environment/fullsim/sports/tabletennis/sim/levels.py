"""The action-level switch: `high` (the high-level plugin on) or `low` (off: the arm command layer only)."""
import importlib


def plugin(level: str):
    if level not in ("high", "low"):
        raise ValueError(f"action level must be high or low, not {level!r}")
    return importlib.import_module("action_" + level)
