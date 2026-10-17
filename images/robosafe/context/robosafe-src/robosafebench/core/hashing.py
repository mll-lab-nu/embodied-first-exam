"""Canonical serialisation and digests of simulator state (floats are written exactly, as hex)."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical(obj: Any) -> Any:
    """Turn nested state into JSON-serialisable data with exact floats and sorted keys."""
    if isinstance(obj, float):
        return obj.hex()
    if isinstance(obj, (bool, int, str)) or obj is None:
        return obj
    if isinstance(obj, dict):
        return {str(k): canonical(obj[k]) for k in sorted(obj, key=str)}
    if isinstance(obj, (list, tuple)):
        return [canonical(x) for x in obj]
    if hasattr(obj, "tolist"):  # numpy scalars and arrays
        return canonical(obj.tolist())
    if hasattr(obj, "snapshot"):
        return canonical(obj.snapshot())
    raise TypeError(f"cannot serialise {type(obj).__name__}")


def digest(obj: Any) -> str:
    data = json.dumps(canonical(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(data.encode("ascii")).hexdigest()
