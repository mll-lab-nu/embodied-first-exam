"""Trusted, source-only oracle development tools. Never expose to an agent RPC."""

__all__ = ["open_session", "CalibrationSession", "open_grasp_sweep", "parameter_grid",
           "compare_runs", "summarize_run", "UnsupportedCapability", "OperationTimeout"]


def __getattr__(name):
    if name in {"compare_runs", "summarize_run"}:
        from . import run_comparison
        return getattr(run_comparison, name)
    if name == "open_grasp_sweep":
        from .grasp_sweep import open_grasp_sweep
        return open_grasp_sweep
    if name == "parameter_grid":
        from .candidates import parameter_grid
        return parameter_grid
    if name in {"open_session", "CalibrationSession"}:
        from . import api
        return getattr(api, name)
    if name in {"UnsupportedCapability", "OperationTimeout"}:
        from . import contracts
        return getattr(contracts, name)
    raise AttributeError(name)
