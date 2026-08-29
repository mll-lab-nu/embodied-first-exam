"""Seeded layout randomization: turn one episode seed into one task variant.

Every demo does ``cfg = load_configs(...)`` then ``<Task>SceneBuilder(cfg.env,
cfg.task, ...).build()``. This module sits between the two: ``randomize_task_cfg``
takes the loaded config, rewrites the leaves under ``cfg.task`` that the task has
registered as variation axes, and hands the rewritten config to the builder. Scene
builders, planners and verifiers never sample anything themselves; they read the
config (or the live scene) and adapt. Which leaves may vary, and why, is the
subject of ``docs/develop/tasks/variation_axes_plain_zh.md``.

Rules the registry follows:

- **Only leaves the oracle reads back.** A varied value the planner does not
  consult (a hand-written height, an absolute waypoint) would desync the plan from
  the scene. Such leaves stay fixed until they are derived from the layout.
- **Envelope, not difficulty.** Each axis samples its full feasible range (bounded
  by the task's validator, measured incidents, or arm reach). Difficulty tiers are
  cut from sweep results afterwards, not by shrinking ranges here.
- **One named stream per leaf.** Draws come from ``VariantRng(seed).stream(
  "<task_id>/<leaf path>")``, so adding or reordering axes never changes another
  leaf's value for the same seed, and a rejected sample is redrawn under
  ``retry=k`` -- the k-th redraw is itself a pure function of the seed.
- **Validate, then reject.** A task may register a ``_Validate`` hook (its
  ``Layout.validate()`` / ``checks()``); a ``ValueError`` from it rejects the draw
  and the whole set of axes is resampled. A rejection rate above a few percent
  means the declared envelope is too wide, not that retries should be raised.

Only tasks with a recording under ``runs/videos/`` are registered; the 2026-07
entries for the replaced tasks (untangle, cable_routing, stacked_plate, peeling)
were removed on 2026-08-29 together with their difficulty multiplier.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from topogym.generation.variant_rng import VariantRng

try:  # OmegaConf configs may be readonly/struct-locked after load; unlock the copy.
    from omegaconf import OmegaConf
except Exception:  # pragma: no cover - plain-dict callers (tests) don't need it
    OmegaConf = None


# ------------------------------------------------------------------ directives
# A directive says: for this leaf (dotted path under cfg.task), draw a value this
# way. Sampling directives get their own named stream; derived ones draw nothing.


@dataclass(frozen=True)
class _ChoiceJitter:
    """Replace the leaf at ``path`` with one of ``values``, drawn uniformly."""

    path: str  # e.g. "zones.target"
    values: tuple  # e.g. ("left", "right")


@dataclass(frozen=True)
class _ScalarJitter:
    """Replace the scalar leaf at ``path`` with U(lo, hi)."""

    path: str  # e.g. "zones.left.angle_deg"
    lo: float
    hi: float


@dataclass(frozen=True)
class _SwapJitter:
    """With probability 1/2, exchange the values at ``path_a`` and ``path_b``."""

    path_a: str
    path_b: str


@dataclass(frozen=True)
class _ShiftBy:
    """Add the value at ``by_path`` to every leaf in ``paths`` (derived, no draw).

    Keeps a group of leaves rigid relative to a sampled reference, e.g. zone
    angles that must move with the beam's sampled initial angle.
    """

    paths: tuple
    by_path: str


@dataclass(frozen=True)
class _Validate:
    """Call ``fn(task_cfg)`` after sampling; a ``ValueError`` rejects the sample.

    On rejection every sampling directive is redrawn with ``retry`` incremented,
    so the k-th redraw is still a pure function of the seed (see variant_rng).
    """

    fn: object  # callable(task_cfg) -> None, raising ValueError to reject
    max_retries: int = 20


def _validate_linkbar_rotate_to_zone(task_cfg) -> None:
    # Imported lazily: the task module pulls in Genesis, which this module must not
    # require (the unit test runs without it).
    from topogym.tasks.connectivity.linkbar_rotate_to_zone import LinkbarRotateLayout

    LinkbarRotateLayout(task_cfg).validate()


# ------------------------------------------------------------------- registry
# task_id -> ordered directives. Sampling directives first, then derived ones,
# then at most one _Validate.
_REGISTRY: dict[str, list] = {
    # Anti-shortcut axes: which zone is the target (the pin takes its colour) and
    # whether the two colours are swapped. Layout axes: each zone's angle, drawn
    # within [min_sweep, max_sweep] on its own side, and the beam's initial angle;
    # both zone angles are then shifted with the beam so the sweeps stay in range.
    # The oracle asks `layout.target_zone()` / `pin_color()` and reads the live joint
    # angle, so nothing in the planner changes. `LinkbarRotateLayout.validate`
    # (opposite sides, sweep range, zone separation, distinct colours) rejects the
    # draw where the shift pushes a sweep past the ceiling.
    "linkbar_rotate_to_zone": [
        _ChoiceJitter("zones.target", ("left", "right")),
        _SwapJitter("zones.assignment.left", "zones.assignment.right"),
        _ScalarJitter("zones.left.angle_deg", 35.0, 75.0),
        _ScalarJitter("zones.right.angle_deg", -75.0, -35.0),
        _ScalarJitter("linkbar.init_angle_deg", -15.0, 15.0),
        _ShiftBy(("zones.left.angle_deg", "zones.right.angle_deg"), "linkbar.init_angle_deg"),
        _Validate(_validate_linkbar_rotate_to_zone),
    ],
}


def registered_tasks() -> tuple[str, ...]:
    """Task ids that have a layout randomizer (others are a safe no-op)."""
    return tuple(_REGISTRY)


def sampled_leaves(task_id) -> tuple[str, ...]:
    """Dotted paths under ``cfg.task`` that randomization may rewrite for ``task_id``."""
    leaves: list[str] = []
    for d in _REGISTRY.get(str(task_id), ()):
        if isinstance(d, (_ChoiceJitter, _ScalarJitter)):
            leaves.append(d.path)
        elif isinstance(d, _SwapJitter):
            leaves.extend((d.path_a, d.path_b))
        elif isinstance(d, _ShiftBy):
            leaves.extend(d.paths)
    out: list[str] = []
    for leaf in leaves:
        if leaf not in out:
            out.append(leaf)
    return tuple(out)


# --------------------------------------------------------------- tree helpers


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


def _same_type(template, value):
    """Coerce a drawn value back to the leaf's original Python type."""
    if isinstance(template, bool):
        return bool(value)
    if isinstance(template, int):
        return int(value)
    if isinstance(template, float):
        return float(value)
    if isinstance(template, str):
        return str(value)
    return value


# ------------------------------------------------------------------ sampling


def _apply(task, directives, vrng: VariantRng, prefix: str, retry: int) -> None:
    for d in directives:
        if isinstance(d, _ChoiceJitter):
            rng = vrng.stream(f"{prefix}/{d.path}", retry=retry)
            pick = d.values[int(rng.integers(len(d.values)))]
            _set_node(task, d.path, _same_type(_get_node(task, d.path), pick))
        elif isinstance(d, _ScalarJitter):
            rng = vrng.stream(f"{prefix}/{d.path}", retry=retry)
            _set_node(task, d.path, float(rng.uniform(d.lo, d.hi)))
        elif isinstance(d, _SwapJitter):
            rng = vrng.stream(f"{prefix}/{d.path_a}<->{d.path_b}", retry=retry)
            if rng.random() < 0.5:
                a, b = _get_node(task, d.path_a), _get_node(task, d.path_b)
                _set_node(task, d.path_a, b)
                _set_node(task, d.path_b, a)
        elif isinstance(d, _ShiftBy):
            by = float(_get_node(task, d.by_path))
            for path in d.paths:
                _set_node(task, path, float(_get_node(task, path)) + by)
        elif isinstance(d, _Validate):
            continue
        else:  # pragma: no cover - registry typo
            raise TypeError(f"Unknown directive {d!r}")


def _unlocked_copy(cfg):
    out = copy.deepcopy(cfg)
    if OmegaConf is not None and OmegaConf.is_config(out):
        OmegaConf.set_readonly(out, False)
        OmegaConf.set_struct(out, False)
    return out


def randomize_task_cfg(cfg, task_id, seed, *, difficulty: str = "envelope"):
    """Return a copy of ``cfg`` with ``cfg.task`` rewritten for episode ``seed``.

    No-op (returns ``cfg`` unchanged, same object) for tasks without a registered
    randomizer. Deterministic in ``seed``; only registered ``cfg.task`` leaves
    change. ``difficulty`` is accepted for call-site compatibility and currently
    unused: every axis samples its full envelope until tiers are cut from sweep
    data (variation_axes_plain_zh.md section 5).
    """
    directives = _REGISTRY.get(str(task_id))
    if not directives:
        return cfg

    validators = [d for d in directives if isinstance(d, _Validate)]
    if len(validators) > 1:
        raise ValueError(f"{task_id}: at most one _Validate directive, got {len(validators)}")
    validate = validators[0] if validators else None
    max_retries = int(validate.max_retries) if validate else 0

    vrng = VariantRng(seed)
    prefix = str(task_id)
    last_error = None
    for retry in range(max_retries + 1):
        out = _unlocked_copy(cfg)
        _apply(out["task"], directives, vrng, prefix, retry)
        if validate is None:
            return out
        try:
            validate.fn(out["task"])
        except ValueError as exc:
            last_error = exc
            continue
        return out
    raise RuntimeError(
        f"{task_id}: layout rejected {max_retries + 1} times for seed {int(seed)}; "
        f"the declared envelope is too wide. Last reason: {last_error}"
    )
