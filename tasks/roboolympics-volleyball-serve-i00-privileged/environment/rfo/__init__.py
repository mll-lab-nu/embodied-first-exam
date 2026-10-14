"""RoboOlympics: single-humanoid sports tasks on the RoboOlympics simulator (docs/benchmarks/roboolympics.md)."""
import importlib


def load_task(name: str | None = None):
    """The family's Task: `rfo_task.py` next to the package (a task directory holds exactly one family), or, in the
    repository's scripts/roboolympics/shared/, rfo.tasks.<name>."""
    try:
        mod = importlib.import_module("rfo_task")
    except ModuleNotFoundError:
        if name is None:
            raise
        mod = importlib.import_module(f"rfo.tasks.{name.replace('-', '_')}")
    task = mod.Task()
    if name is not None and task.name != name:
        raise RuntimeError(f"this directory holds the family {task.name!r}, not {name!r}")
    return task
