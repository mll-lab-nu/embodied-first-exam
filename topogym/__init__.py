"""Genesis simulator modules; importing TopoGym does not start an engine."""
__all__ = ["SimulatorConfig", "StateRef", "env_list", "make"]


def __getattr__(name):
    # Accounting and runner hosts do not need NumPy, Genesis or CUDA.
    if name in __all__:
        from importlib import import_module
        value = getattr(import_module("topogym.simulator"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
