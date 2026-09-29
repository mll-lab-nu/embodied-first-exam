"""Detached, immutable numerical records for observations and output consumers."""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
import numpy as np


def freeze(value):
    """Copy arrays into immutable storage, including nested dictionaries."""
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject:
            raise TypeError("Object arrays are not observation values")
        # A bytes owner prevents consumers from re-enabling WRITEABLE.
        contiguous = np.ascontiguousarray(value)
        return np.frombuffer(contiguous.tobytes(), dtype=value.dtype).reshape(value.shape)
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(freeze(item) for item in value)
    if isinstance(value, np.generic):
        return value.item()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported snapshot value: {type(value).__name__}")


def thaw(value):
    """Copy a frozen configuration into ordinary containers for its owner."""
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.copy()
    return value
