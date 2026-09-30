"""YAML config loading shared by both processes (OmegaConf only).

A file may name parent files in ``_base_`` (one path or a list, relative to the file). Parents are merged in
order, then the file itself: mappings merge key by key and every other value, lists included, is replaced.
``${a.b}`` references resolve against the merged result.
"""
from __future__ import annotations

from pathlib import Path

from omegaconf import OmegaConf


def load_yaml(path):
    path = Path(path)
    cfg = OmegaConf.load(path)
    bases = cfg.pop("_base_", [])
    bases = [bases] if isinstance(bases, str) else bases
    return OmegaConf.merge(*(load_yaml(path.parent / base) for base in bases), cfg)
