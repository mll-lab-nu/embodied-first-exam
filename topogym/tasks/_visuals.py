from __future__ import annotations

import numpy as np
from omegaconf import OmegaConf


def _to_container(value):
    if OmegaConf.is_config(value):
        return OmegaConf.to_container(value, resolve=True)
    return value


def _cfg_get(cfg, name: str, default=None):
    if OmegaConf.is_config(cfg):
        return OmegaConf.select(cfg, name, default=default)
    return getattr(cfg, name, default)


def box_entity_enabled(cfg, *, default: bool = True) -> bool:
    """Return whether a configured box should be materialized in Genesis."""

    if cfg is None or not bool(_cfg_get(cfg, "enabled", default)):
        return False

    size = _cfg_get(cfg, "size", None)
    if size is None:
        return True
    values = np.asarray(_to_container(size), dtype=float)
    if values.size == 0:
        return False
    return bool(np.all(values > 0.0))
