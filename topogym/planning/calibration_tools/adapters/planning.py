"""Trusted worker-local planning adapters; no recursive session requests."""
from dataclasses import dataclass
import importlib.util
from pathlib import Path

from ..contracts import digest, json_value


@dataclass(frozen=True)
class QueryContext:
    """Read-only conveniences supplied to custom make_adapter(context, **kwargs).

    This is an API boundary, not a sandbox for arbitrary trusted Python.
    """
    inspect: object
    solve_ik: object
    check_robot_path: object
    cancelled: object
    source_identity: str


def load_adapter(owner, specification):
    if specification == "keyhole_tcp":
        from .keyhole_plans import KeyholeTCPAdapter
        return KeyholeTCPAdapter(owner)
    if not isinstance(specification, dict) or set(specification)-{"path", "factory", "kwargs"}:
        raise ValueError("adapter is 'keyhole_tcp' or {path, factory, kwargs}")
    path = Path(specification["path"]).resolve()
    payload = path.read_bytes()
    key = digest(dict(source=payload.decode(), factory=specification.get("factory", "make_adapter"),
                      kwargs=specification.get("kwargs", {})))
    folder = owner.output / "planning_adapters"
    folder.mkdir(exist_ok=True)
    saved = folder / (key+".py")
    if not saved.exists():
        saved.write_bytes(payload)
    spec = importlib.util.spec_from_file_location("calibration_adapter_"+key, saved)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    context = QueryContext(owner.inspect, owner.solve_ik, owner.check_robot_path, owner.cancelled, key)
    adapter = getattr(module, specification.get("factory", "make_adapter"))(context, **specification.get("kwargs", {}))
    if not all(callable(getattr(adapter, m, None)) for m in ("identity", "snapshot", "validate", "plan")):
        raise TypeError("Adapter needs identity(request), snapshot(request), validate(bundle), plan(request, seed=None)")
    if not getattr(adapter, "required_coverage", None):
        raise ValueError("Adapter must declare required_coverage")
    owner.evidence.event("planning_adapter_loaded", identity=key, specification=json_value(specification))
    return adapter
