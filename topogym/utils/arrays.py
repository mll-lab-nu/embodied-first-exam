"""Explicit host-array conversion and ownership, without engine initialization."""
from __future__ import annotations

import numpy as np


def to_numpy(value, *, copy=True):
    """Detach tensors and transfer to host; copy by default to isolate state.

    ``copy=False`` may return shared storage. Callers choosing it must consume
    the result before its source buffer is updated and must not modify it.
    This operation preserves dtype; it does not normalize units or precision.
    """
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    result = np.asarray(value)
    return result.copy() if copy else result
