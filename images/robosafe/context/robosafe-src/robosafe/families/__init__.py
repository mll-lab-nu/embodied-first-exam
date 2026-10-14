"""Task families. Each subpackage of this package defines one family class named `FAMILY` (docs/CONTRACTS.md 5)."""
from __future__ import annotations

import importlib
import pkgutil

from .base import Family

_REGISTRY: dict | None = None


def registry() -> dict:
    global _REGISTRY
    if _REGISTRY is None:
        out = {}
        for mod in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
            if not mod.ispkg:
                continue
            fam = importlib.import_module(f"{__name__}.{mod.name}").FAMILY
            out[fam.id] = fam
        _REGISTRY = out
    return _REGISTRY


def get(family_id: str) -> Family:
    reg = registry()
    if family_id not in reg:
        raise KeyError(f"unknown family {family_id!r}; families: {sorted(reg)}")
    return reg[family_id]


__all__ = ["Family", "registry", "get"]
