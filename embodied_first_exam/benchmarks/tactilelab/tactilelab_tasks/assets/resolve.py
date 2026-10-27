"""Locate asset files by their path relative to the assets directory.

Task configurations name assets relative to ``tactilelab_tasks/assets`` (for example
``objects/assembly/square_table_top/Object.usd``). Every file the tasks need is
shipped with the package (the files over 2 MB come from the data-only files image and are
copied into the same directory); a path is searched in this order:

1. every directory listed in the ``TACTILELAB_ASSET_ROOTS`` environment variable
   (colon separated, highest priority first) - an explicit override;
2. ``tactilelab_tasks/assets/`` - the files shipped with the package;
3. ``tactilelab_tasks/assets/_local/`` - an optional, never committed mirror of the
   assets layout (extra or experimental files); only consulted for paths the
   package does not ship.

Annotation files (``Annotation/grasp_pose.json`` ...) live next to their USD in
the same layout and are resolved with the same search.
"""

from __future__ import annotations

import os
from typing import List, Optional

PACKAGE_ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_ASSET_DIR = os.path.join(PACKAGE_ASSET_DIR, "_local")
ENV_VAR = "TACTILELAB_ASSET_ROOTS"

__all__ = [
    "asset_roots",
    "find_asset",
    "resolve_asset",
    "annotation_file",
    "PACKAGE_ASSET_DIR",
    "LOCAL_ASSET_DIR",
    "ENV_VAR",
]


def asset_roots() -> List[str]:
    """Search roots in priority order (environment override, package, local mirror)."""
    roots: List[str] = []
    for r in os.environ.get(ENV_VAR, "").split(":"):
        r = os.path.expanduser(r.strip())
        if r and r not in roots:
            roots.append(r)
    for r in (PACKAGE_ASSET_DIR, LOCAL_ASSET_DIR):
        if r not in roots:
            roots.append(r)
    return roots


def find_asset(rel_path: str) -> Optional[str]:
    """Absolute path of the first root that contains ``rel_path``; None when absent."""
    rel = rel_path.replace("\\", "/").lstrip("/")
    if os.path.isabs(rel_path) and os.path.exists(rel_path):
        return rel_path
    for root in asset_roots():
        p = os.path.join(root, rel)
        if os.path.exists(p):
            return p
    return None


def resolve_asset(rel_path: str) -> str:
    """Like :func:`find_asset` but raises ``FileNotFoundError`` with the roots searched."""
    p = find_asset(rel_path)
    if p is None:
        raise FileNotFoundError(
            f"asset {rel_path!r} not found in any asset root: {asset_roots()} (see scripts/fetch_assets.py or set ${ENV_VAR})"
        )
    return p


def annotation_file(usd_rel_path: str, name: str) -> str:
    """``<dir of usd>/Annotation/<name>.json`` resolved through the asset roots."""
    d = os.path.dirname(usd_rel_path.replace("\\", "/"))
    return resolve_asset(os.path.join(d, "Annotation", f"{name}.json"))
