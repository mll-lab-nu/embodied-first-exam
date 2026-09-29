"""Packaged resource lookup and validated, content-addressed asset build records."""

from __future__ import annotations

from dataclasses import dataclass
import os
import hashlib
import json
from pathlib import Path
from typing import Mapping


RESOURCE_ROOT = Path(__file__).parent / "resources"


def resource_path(resource_id: str) -> Path:
    """Resolve one catalog identity; never search historical run directories."""
    catalog = json.loads((RESOURCE_ROOT / "catalog.json").read_text())
    try:
        record = catalog["resources"][resource_id]
    except KeyError as exc:
        raise ValueError(f"Unknown packaged resource: {resource_id}") from exc
    path = (RESOURCE_ROOT / record["path"]).resolve()
    if not path.is_relative_to(RESOURCE_ROOT.resolve()) or not path.is_file():
        raise FileNotFoundError(f"Missing packaged resource: {resource_id}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
        raise ValueError(f"Packaged resource hash mismatch: {resource_id}")
    return path


@dataclass(frozen=True)
class AssetBuild:
    """A build's explicit inputs, resource roles and output hashes; no engine handles."""

    task_id: str
    root: Path
    files: Mapping[str, str]
    sha256: Mapping[str, str]
    parameters: Mapping
    seed: int
    units: str = "m"
    coordinate_frame: str = "task-local, z-up"


def describe_build(task_id, root, parameters, seed) -> AssetBuild:
    """Validate a completed generator output without executing simulation."""
    root = Path(root).resolve()
    files, hashes = {}, {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if not path.resolve().is_relative_to(root):
            raise ValueError("Generated assets may not escape their output directory")
        name = str(path.relative_to(root))
        files[name] = name
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    # Primitive-only tasks legitimately have no generated files.
    return AssetBuild(task_id, root, files, hashes, dict(parameters), int(seed))


def visual_asset_path(value) -> Path:
    """Resolve visual assets from an explicit directory or the user cache."""
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    cache = Path(
        os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    ).expanduser()
    root = Path(
        os.environ.get("TOPOGYM_VISUAL_ASSET_ROOT", str(cache / "topogym/visuals/nyx"))
    )
    return root.expanduser().resolve() / path
