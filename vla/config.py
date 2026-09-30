"""YAML config loading shared by both processes (OmegaConf only).

A file may name a parent file in ``_base_`` (relative to the file). The parent is merged first, then the file
itself: mappings merge key by key and every other value, lists included, is replaced. ``${a.b}`` references
resolve against the merged result.
"""
from __future__ import annotations

from pathlib import Path

from omegaconf import OmegaConf


def load_yaml(path):
    path = Path(path)
    cfg = OmegaConf.load(path)
    base = cfg.pop("_base_", None)
    return OmegaConf.merge(load_yaml(path.parent / base), cfg) if base else cfg
