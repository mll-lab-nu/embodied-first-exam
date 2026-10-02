"""The per-tick finiteness check of GenesisWorld.read_state, as one iterative pass.

state.require_finite_state names the first bad path but builds a path string per node; read_state runs the check every
physics tick, so the verdict comes from this walk (exact-type tests first, then the same checks) and only a failure
calls the recursive walk for its error. Kept out of state.py: that file's hash is part of the frozen blanket states'
backend identity (world/physics/pbd_initial_state.py). Same verdicts and errors: scripts/check_fast_paths.py.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np

_NOT_NUMERIC_CONTAINERS = (int, bool, str, type(None))


def require_finite(value, path="world"):
    stack = [value]
    while stack:
        item = stack.pop()
        kind = type(item)
        if kind is dict:
            stack.extend(item.values())
        elif kind is list or kind is tuple:
            stack.extend(item)
        elif kind is np.ndarray:
            if item.dtype.kind in "fc" and not np.isfinite(item).all():
                return _explain(value, path)
        elif kind is float or kind is np.float64 or kind is np.float32:
            if not math.isfinite(item):
                return _explain(value, path)
        elif kind in _NOT_NUMERIC_CONTAINERS:
            pass
        elif isinstance(item, Mapping):
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        elif isinstance(item, np.ndarray):
            if item.dtype.kind in "fc" and not np.isfinite(item).all():
                return _explain(value, path)
        elif isinstance(item, (float, np.floating)) and not np.isfinite(item):
            return _explain(value, path)


def _explain(value, path):
    from topogym.world.state import require_finite_state
    require_finite_state(value, path)
