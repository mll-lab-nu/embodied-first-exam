"""Project registrations are driven only by the canonical manifest."""

from importlib import import_module
from panda_dynamics.manifest import BENCHMARK, ensure_registered

TASKS = []
for spec in BENCHMARK:
    ensure_registered(spec.code)
    TASKS.append(
        getattr(import_module("panda_dynamics.tasks." + spec.module), spec.name)
    )
TASKS = tuple(TASKS)
