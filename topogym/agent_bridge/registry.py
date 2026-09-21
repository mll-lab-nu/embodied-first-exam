"""One lazy adapter registry for local and HTTP transports; no simulator imports."""
from functools import partial
import importlib

TASKS = ("counter", "cast_coil", "horseshoe_ring", "cast_keyhole", "hedgehog_in_cage", "lock_picking", "interlocked_claws", "buzz_wire_3d", "knot_untying")


def factory_for(task, backend, renderer, factory=None, *, objective="assemble"):
    if factory:
        module, function = factory.split(":", 1)
        return getattr(importlib.import_module(module), function)
    if task not in TASKS:
        raise ValueError(f"Unknown adapter: {task}")
    if task == "counter":
        from .adapters import CounterTask
        return CounterTask
    module = importlib.import_module(f"topogym.tasks.{task}.agent_adapter")
    options = dict(backend=backend, renderer=renderer)
    if task == "cast_coil":
        options["objective"] = objective
    return partial(module.create, **options)
