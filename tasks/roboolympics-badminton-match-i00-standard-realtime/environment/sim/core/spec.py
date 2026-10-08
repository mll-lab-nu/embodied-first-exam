"""The sport's declarations (sport.toml next to its plugin.py, docs/framework_zh.md §4.2): data, read by the core
(observation whitelist, team channel, success line, timing), the generator, the checks and the documentation."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path


def load(plugin_path: str | os.PathLike) -> dict:
    p = Path(plugin_path)
    p = p / "sport.toml" if p.is_dir() else p.with_name("sport.toml")
    if not p.exists():
        return {}
    return tomllib.loads(p.read_text())


def whitelist(decl: dict) -> set[str] | None:
    fields = (decl.get("observation") or {}).get("fields")
    return set(fields) if fields is not None else None
