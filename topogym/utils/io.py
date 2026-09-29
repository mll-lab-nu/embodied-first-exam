"""Small, streaming provenance helpers shared by recorders and archives."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass


def code_provenance(root, task_id):
    """Record the actual relevant source bytes, including uncommitted edits."""
    import importlib.metadata
    import subprocess
    paths = list((root / "topogym/recording").rglob("*.py"))
    paths += list((root / "topogym/world").glob("*.py"))
    paths += [root / "topogym/tasks" / f"{task_id}.py"]
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True)
    versions = {}
    for package in ("genesis-world", "numpy", "omegaconf"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
    return dict(git_revision=revision.stdout.strip() if revision.returncode == 0 else None,
                source_hashes={p.relative_to(root).as_posix(): sha256_file(p) for p in sorted(paths) if p.is_file()},
                packages=versions)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def write_json_atomic(path, value, *, indent=2):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps(to_jsonable(value), indent=indent, ensure_ascii=False, allow_nan=False))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path):
    return json.loads(Path(path).read_text())


def to_jsonable(value):
    """Convert numerical records without silently coercing unsupported values."""
    import numpy as np
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("Serialized mapping keys must be strings")
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return to_jsonable(value.tolist())
    if isinstance(value, np.generic):
        return to_jsonable(value.item())
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Nonfinite numbers cannot be serialized")
        return value
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Unsupported serialized value: {type(value).__name__}")


def relative_file(root, relative):
    """Reject absolute paths, traversal and symlink escapes in artifact manifests."""
    root = Path(root).resolve()
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Expected a relative artifact path: {relative}")
    result = root / path
    if not result.resolve().is_relative_to(root) or any(p.is_symlink() for p in (result, *result.parents) if p != root and p.is_relative_to(root)):
        raise ValueError(f"Artifact path escapes its root: {relative}")
    return result
