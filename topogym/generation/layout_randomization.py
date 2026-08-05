"""Seeded, bounded layout randomization (the generation "seam").

Today each task's layout is deterministic: `build_*_episode_spec` copies config
values into the EpisodeSpec identity, and the scene builder reads `cfg.task`
straight from the yaml. This module adds per-seed variation WITHOUT touching the
scene builders: a demo applies `randomize_task_cfg(cfg, task_id, seed, ...)`
right after `load_configs`, and the (jittered) `cfg.task` flows into the builder
as usual.

Design (per the approved plan):
- **Bounded perturbation only** — nudge positions / spacing within safe ranges;
  never change topology, object counts, or the oracle's structure. This keeps
  the oracle solvable and the success criterion unchanged.
- **Only oracle-consumed axes** — jitter is only applied to fields the active
  oracle reads back from config, so the solution adapts. Axes where the oracle
  is hand-authored (absolute waypoints) are intentionally NOT jittered.
- **Layout only** — touches `cfg.task` layout leaves; never robot home / env /
  shared config (see memory `shared-home-parity-rule`).
- **Deterministic + bounded** — `np.random.default_rng(seed)`; every jittered
  value provably stays within its declared bound. Unregistered task -> no-op.

The magnitudes below are conservative STARTING guesses; the safe envelope is
found empirically with `bash_scripts/tests/stability_sweep.sh ... RANDOMIZE=1`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np

try:  # OmegaConf configs may be readonly/struct-locked after load; unlock the copy.
    from omegaconf import OmegaConf
except Exception:  # pragma: no cover - plain-dict callers (tests) don't need it
    OmegaConf = None

# difficulty label -> multiplier on every jitter magnitude (the "difficulty axis"
# is realized as wider/narrower perturbation, not separate hand-tuned layouts).
_DIFFICULTY_SCALE = {"easy": 0.5, "smoke": 0.5, "default": 1.0, "hard": 1.8}


@dataclass(frozen=True)
class _AbsXYJitter:
    """Add U(-r, r) meters to x and y of an ``[x, y, z]`` leaf; z untouched."""

    path: str  # dotted path under cfg.task, e.g. "fixtures.P1.pos"
    radius_m: float  # half-range in meters at difficulty=default


@dataclass(frozen=True)
class _FracJitter:
    """Scale each component of a numeric-list leaf by ``(1 + U(-f, f))``."""

    path: str  # e.g. "holes.spacing"
    frac: float  # fractional half-range at difficulty=default


@dataclass(frozen=True)
class _EachScalarJitter:
    """For every child of the dict at ``dict_path``, add U(-a, a) to child[field]."""

    dict_path: str  # e.g. "disks"
    field: str  # e.g. "init_angle_deg"
    amount: float  # absolute half-range in the field's units, at difficulty=default


@dataclass(frozen=True)
class _EachAbsXYJitter:
    """For every child of the dict at ``dict_path``, jitter x,y of child[field]."""

    dict_path: str  # e.g. "separation_slots.slots"
    field: str  # e.g. "pos"
    radius_m: float  # half-range in meters at difficulty=default


# task_id -> ordered jitter directives. ONLY oracle-safe axes (see per-entry note).
_REGISTRY: dict[str, list] = {
    # Grid spacing changes rope slack/tension -> real PBD-stability variation, while
    # hole indices + z_offset (the crossing ground-truth) stay fixed; the oracle reads
    # hole positions derived from spacing, so it adapts.
    "untangle": [
        _FracJitter("holes.spacing", frac=0.06),
    ],
    # Peg positions: the smooth-route oracle (routing.smooth_route: true) centers its
    # wrap arcs on each peg's pos, so it adapts. REQUIRES smooth_route=true; the
    # hand-authored endpoint_oracle_waypoints (smooth_route=false path) are absolute
    # and would desync -- do not enable randomization on that path.
    "cable_routing": [
        _AbsXYJitter("fixtures.P1.pos", radius_m=0.010),
        _AbsXYJitter("fixtures.P2.pos", radius_m=0.010),
    ],
    # Each disk's initial angle; the contact-driven rotate primitive reads the LIVE
    # disk angle and rotates toward oracle.target_angle_deg, so it adapts. The rod/disk
    # stack geometry (center/radius) is left untouched.
    "stacked_plate": [
        _EachScalarJitter("disks", "init_angle_deg", amount=6.0),
    ],
    # ONLY the separation-slot drop targets (the oracle reads slot pos to place the
    # peeled film). We deliberately do NOT jitter film pos/yaw: that changes the
    # layer-overlap topology the peel-order oracle/success depend on. Modest variation
    # but topology-safe; stronger peeling randomization is deferred until sweep-validated.
    "peeling": [
        _EachAbsXYJitter("separation_slots.slots", "pos", radius_m=0.008),
    ],
}


def registered_tasks() -> tuple[str, ...]:
    """Task ids that have a layout randomizer (others are a safe no-op)."""
    return tuple(_REGISTRY)


def _get_node(root, dotted: str):
    """Navigate ``root[a][b]...`` for a dotted path (works on OmegaConf & dict)."""
    node = root
    for part in dotted.split("."):
        node = node[part]
    return node


def _set_node(root, dotted: str, value) -> None:
    """Set the leaf at a dotted path (works on OmegaConf & dict)."""
    parts = dotted.split(".")
    parent = _get_node(root, ".".join(parts[:-1])) if len(parts) > 1 else root
    parent[parts[-1]] = value


def randomize_task_cfg(cfg, task_id, seed, *, difficulty: str = "default"):
    """Return a copy of ``cfg`` with ``cfg.task`` layout bounded-jittered by seed.

    No-op (returns ``cfg`` unchanged, same object) for tasks without a registered
    randomizer. Deterministic in ``seed``; only ``cfg.task`` layout leaves change.
    """
    directives = _REGISTRY.get(str(task_id))
    if not directives:
        return cfg

    scale = _DIFFICULTY_SCALE.get(str(difficulty), 1.0)
    rng = np.random.default_rng(int(seed))
    out = copy.deepcopy(cfg)
    if OmegaConf is not None and OmegaConf.is_config(out):
        OmegaConf.set_readonly(out, False)
        OmegaConf.set_struct(out, False)
    task = out["task"]

    for directive in directives:
        if isinstance(directive, _AbsXYJitter):
            vals = [float(v) for v in _get_node(task, directive.path)]
            r = directive.radius_m * scale
            vals[0] += float(rng.uniform(-r, r))
            vals[1] += float(rng.uniform(-r, r))
            _set_node(task, directive.path, vals)
        elif isinstance(directive, _FracJitter):
            f = directive.frac * scale
            vals = [
                float(v) * (1.0 + float(rng.uniform(-f, f)))
                for v in _get_node(task, directive.path)
            ]
            _set_node(task, directive.path, vals)
        elif isinstance(directive, _EachScalarJitter):
            node = _get_node(task, directive.dict_path)
            a = directive.amount * scale
            for key in list(node):
                child = node[key]
                child[directive.field] = float(child[directive.field]) + float(
                    rng.uniform(-a, a)
                )
        elif isinstance(directive, _EachAbsXYJitter):
            node = _get_node(task, directive.dict_path)
            r = directive.radius_m * scale
            for key in list(node):
                child = node[key]
                vals = [float(v) for v in child[directive.field]]
                vals[0] += float(rng.uniform(-r, r))
                vals[1] += float(rng.uniform(-r, r))
                child[directive.field] = vals

    return out
