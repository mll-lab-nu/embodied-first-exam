"""Canonical private evidence and bounded, non-executable trajectory archives."""
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
import hashlib
import json
import math
from pathlib import Path
import zipfile
import numpy as np


def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)):
        return [plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def json_bytes(value):
    return json.dumps(plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def rounded_state(value):
    """Canonical SI measurements at 12 decimal places; raw evidence is kept.

    This only removes last-bit float64 reduction noise. Integer identities,
    counters, topology, booleans and success predicates remain exact.
    """
    if isinstance(value,float):
        result=round(value,12)
        return 0. if result == 0 else result
    if isinstance(value,dict):
        return {k:rounded_state(v) for k,v in value.items()}
    if isinstance(value,list):
        return [rounded_state(v) for v in value]
    return value


def equivalent_states(a,b):
    """SI numeric replay check, atol=rtol=1e-9; discrete facts stay exact.

    GPU constraint reductions can differ below a nanometre/radian even when
    rounded fingerprints differ at a bin boundary. Report this separately from
    fingerprint determinism. Contacts form a multiset, not an ordered vector.
    """
    if type(a) is not type(b):
        return False
    if isinstance(a,float):
        return math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-9)
    if isinstance(a,dict):
        if a.keys()!=b.keys():
            return False
        for key in a:
            if key=="contacts" and isinstance(a[key],list) and isinstance(b[key],list):
                remaining=list(b[key])
                if len(a[key])!=len(remaining):
                    return False
                for row in a[key]:
                    match=next((i for i,candidate in enumerate(remaining) if equivalent_states(row,candidate)),None)
                    if match is None:
                        return False
                    remaining.pop(match)
            elif not equivalent_states(a[key],b[key]):
                return False
        return True
    if isinstance(a,list):
        return len(a)==len(b) and all(equivalent_states(x,y) for x,y in zip(a,b))
    return a==b


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix+".tmp")
    pending.write_bytes(json_bytes(value)+b"\n")
    pending.replace(path)


def canonical_state(env):
    record = plain(env.tick_record())
    # Episode UUIDs/branch IDs are process identities, not physics.
    for name in ("episode_id", "branch_id", "state_id", "parent_state_id"):
        record["state"].pop(name, None)
    # Contact enumeration order is a solver implementation detail. Keep every
    # measured contact and its exact numeric values, in a canonical row order.
    contacts = record.get("world",{}).get("contacts",{})
    if contacts and isinstance(contacts.get("link_a"),list):
        count=len(contacts["link_a"])
        if all(isinstance(v,list) and len(v)==count for v in contacts.values()):
            rows=[{k:v[i] for k,v in contacts.items()} for i in range(count)]
            record["world"]["contacts"] = sorted(rows,key=lambda r:json_bytes(rounded_state(r)))
    return record


def fingerprint(env):
    return digest(rounded_state(canonical_state(env)))


def load_trajectory(path, *, max_bytes=512*1024*1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("Missing or oversized trajectory")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if sorted(i.filename for i in entries) != ["actions.npy", "identity.npy", "initial.npy", "physics_steps.npy"] or sum(i.file_size for i in entries) > max_bytes:
            raise ValueError("Invalid trajectory archive members or expanded size")
    with np.load(path, allow_pickle=False) as archive:
        actions, steps = archive["actions"], archive["physics_steps"]
        identity, initial = archive["identity"], archive["initial"]
    if actions.dtype != np.float64 or actions.ndim != 2 or not np.isfinite(actions).all() or steps.dtype != np.int64 or steps.shape != (len(actions),) or np.any(steps < 1):
        raise ValueError("Malformed trajectory arrays")
    for value in (identity, initial):
        if value.shape != () or value.dtype.kind != "U" or len(str(value)) != 64 or any(c not in "0123456789abcdef" for c in str(value)):
            raise ValueError("Malformed trajectory identity")
    return actions, steps, str(identity), str(initial)
