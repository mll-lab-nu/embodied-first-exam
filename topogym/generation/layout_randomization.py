"""Seeded layout randomization: turn one episode seed into one task variant.

Every demo does ``cfg = load_configs(...)`` then ``<Task>SceneBuilder(cfg.env,
cfg.task, ...).build()``. This module sits between the two: ``randomize_task_cfg``
takes the loaded config, rewrites the leaves under ``cfg.task`` that the task's
yaml declares as variation axes, and hands the rewritten config to the builder.
Scene builders, planners and verifiers never sample anything themselves; they read
the config (or the live scene) and adapt. Which leaves may vary, and why, is the
subject of ``docs/develop/tasks/variation_axes_plain_zh.md``.

**Where the axes are declared.** In the task yaml, as a ``variation:`` list next
to the geometry the bounds come from (there is no registry in Python; a task
without the block is left untouched). One entry per axis::

    variation:
      - {kind: choice,          path: zones.target, values: [color_1, color_2]}
      - {kind: uniform,         path: linkbar.init_angle_deg, lo: -15.0, hi: 15.0}
      - {kind: distinct_choice, paths: [a, b], keys_of: zones.colors}
      - {kind: spaced_pair,     paths: [lo_path, hi_path], lo: -82.0, hi: 82.0, min_gap: 16.0}
      - {kind: derived,         fn: "package.module:function"}   # at most one
      - {kind: validate,        fn: "package.module:function"}   # at most one

``kind`` names a directive class below; the other keys are its fields. ``fn`` is
imported when ``randomize_task_cfg`` runs, not when this module is, so a task
module that pulls in Genesis does not make this module need it.

Rules the declarations follow:

- **Only leaves the oracle reads back.** A varied value the planner does not
  consult (a hand-written height, an absolute waypoint) would desync the plan from
  the scene. Such leaves stay fixed until they are derived from the layout.
- **Envelope, not difficulty.** Each axis samples its full feasible range (bounded
  by the task's validator, measured incidents, or arm reach). Difficulty tiers are
  cut from sweep results afterwards, not by shrinking ranges here.
- **One named stream per leaf.** Draws come from ``VariantRng(seed).stream(
  "<task_id>/<leaf path>")``, so adding or reordering axes never changes another
  leaf's value for the same seed, and a rejected sample is redrawn under
  ``retry=k`` -- the k-th redraw is itself a pure function of the seed. Renaming a
  path therefore changes which variant a seed produces.
- **Coupled bounds are derived, not rejected.** When one leaf's feasible range
  depends on other axes (where a ball may spawn depends on where the fork is; how
  far a fork may sit depends on the branch angle and the lever's reach), the yaml
  samples a unit fraction ``[0, 1]`` and a ``derived`` entry names a task-module
  function that maps it onto the range the *current* geometry allows and writes
  the real leaf. It runs after every sampling directive and before ``validate``,
  draws nothing, and is a pure function of the sampled leaves. ``spaced_pair`` is
  the same idea for two leaves of one axis. Rejection stays for what cannot be
  built in (an empty derived range).
- **Validate, then reject.** The ``validate`` entry names a function taking the
  task config; a ``ValueError`` from it rejects the draw and the whole set of axes
  is resampled. Every task's block must keep the first-draw rejection rate under
  ``tests/check_variant_rng.py``'s bar (2%); above it, the fix is a derived
  entry or a narrower range, never more retries.


History: a Python registry (``_REGISTRY``) held the entries until 2026-09-01; the
2026-07 entries for the legacy tasks (untangle, cable_routing, stacked_plate,
peeling) were removed on 2026-08-29 together with their difficulty multiplier.
"""

from __future__ import annotations

import copy
import importlib
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
    values: tuple  # e.g. ("color_1", "color_2")


@dataclass(frozen=True)
class _ScalarJitter:
    """Replace the scalar leaf at ``path`` with U(lo, hi)."""

    path: str  # e.g. "linkbar.init_angle_deg"
    lo: float
    hi: float


@dataclass(frozen=True)
class _DistinctChoiceJitter:
    """Fill the leaves in ``paths`` with distinct keys of the mapping at ``keys_of``.

    One draw (a permutation without replacement) for the whole group, so the
    group shares one stream named after ``keys_of``.
    """

    paths: tuple  # e.g. ("zones.assignment.color_1", "zones.assignment.color_2")
    keys_of: str  # e.g. "zones.colors"


@dataclass(frozen=True)
class _SpacedPairJitter:
    """Fill two scalar leaves with an ordered pair from ``[lo, hi]`` at least ``min_gap`` apart.

    Two values are drawn uniformly on ``[lo, hi - min_gap]``, sorted, and the
    larger one is shifted up by ``min_gap``: that is the uniform distribution over
    non-overlapping pairs, so no draw has to be rejected for overlap. The first
    path always gets the smaller value. One stream for the pair.
    """

    paths: tuple  # (low_path, high_path)
    lo: float
    hi: float
    min_gap: float


@dataclass(frozen=True)
class _Derived:
    """Call ``fn(task_cfg)`` after sampling; it writes derived leaves in place.

    For leaves whose feasible range depends on other sampled leaves: the yaml
    samples a unit fraction and ``fn`` maps it onto the range the drawn geometry
    allows. Runs before ``validate``; draws no random numbers.
    """

    fn: object  # callable(task_cfg) or "package.module:function"


@dataclass(frozen=True)
class _Validate:
    """Call ``fn(task_cfg)`` after sampling; a ``ValueError`` rejects the sample.

    On rejection every sampling directive is redrawn with ``retry`` incremented,
    so the k-th redraw is still a pure function of the seed (see variant_rng).
    """

    fn: object  # callable(task_cfg) or "package.module:function"; raises ValueError to reject
    max_retries: int = 20


_KINDS = {
    "choice": _ChoiceJitter,
    "uniform": _ScalarJitter,
    "distinct_choice": _DistinctChoiceJitter,
    "spaced_pair": _SpacedPairJitter,
    "derived": _Derived,
    "validate": _Validate,
}


def _plain(value):
    """OmegaConf node -> plain Python (lists become lists, not ListConfig)."""
    if OmegaConf is not None and OmegaConf.is_config(value):
        return OmegaConf.to_container(value, resolve=True)
    return value


def _parse_directives(task_cfg) -> list:
    """The task yaml's ``variation:`` block as directive objects; ``[]`` if absent."""
    block = _plain(task_cfg.get("variation")) if hasattr(task_cfg, "get") else None
    if not block:
        return []
    task_id = task_cfg.get("task", {}).get("id", "?") if hasattr(task_cfg, "get") else "?"
    out = []
    for index, entry in enumerate(block):
        entry = dict(entry or {})
        kind = entry.pop("kind", None)
        cls = _KINDS.get(str(kind))
        if cls is None:
            raise ValueError(
                f"{task_id}: variation[{index}] has kind={kind!r}; expected one of "
                f"{sorted(_KINDS)}"
            )
        for key in ("paths", "values"):
            if key in entry:
                entry[key] = tuple(entry[key])
        try:
            out.append(cls(**entry))
        except TypeError as exc:
            raise ValueError(f"{task_id}: variation[{index}] ({kind}): {exc}") from None
    for cls, label in ((_Validate, "validate"), (_Derived, "derived")):
        if sum(isinstance(d, cls) for d in out) > 1:
            raise ValueError(f"{task_id}: at most one {label} entry in variation:, got more")
    return out


def _resolve_fn(fn):

    """``"package.module:function"`` -> the function; a callable is returned as is."""
    if callable(fn):
        return fn
    module_name, _, attr = str(fn).partition(":")
    if not module_name or not attr:
        raise ValueError(f"fn={fn!r}; expected 'package.module:function'")

    return getattr(importlib.import_module(module_name), attr)


def has_variation(task_cfg) -> bool:
    """Does this task config declare any variation axes?"""
    return bool(_parse_directives(task_cfg))


def sampled_leaves(task_cfg) -> tuple[str, ...]:
    """Dotted paths under ``cfg.task`` that randomization may rewrite."""
    leaves: list[str] = []
    for d in _parse_directives(task_cfg):
        if isinstance(d, (_ChoiceJitter, _ScalarJitter)):
            leaves.append(d.path)
        elif isinstance(d, (_DistinctChoiceJitter, _SpacedPairJitter)):
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
        elif isinstance(d, _DistinctChoiceJitter):
            rng = vrng.stream(f"{prefix}/{d.keys_of}", retry=retry)
            keys = list(_get_node(task, d.keys_of).keys())
            if len(keys) < len(d.paths):
                raise ValueError(
                    f"{d.keys_of} has {len(keys)} entries; need {len(d.paths)} distinct"
                )
            picks = rng.choice(len(keys), size=len(d.paths), replace=False)
            for path, i in zip(d.paths, picks):
                _set_node(task, path, _same_type(_get_node(task, path), keys[int(i)]))
        elif isinstance(d, _SpacedPairJitter):
            rng = vrng.stream(f"{prefix}/{d.paths[0]}&{d.paths[1]}", retry=retry)
            low, high = sorted(rng.uniform(d.lo, d.hi - d.min_gap, size=2).tolist())
            _set_node(task, d.paths[0], float(low))
            _set_node(task, d.paths[1], float(high + d.min_gap))
        elif isinstance(d, (_Derived, _Validate)):
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

    No-op (returns ``cfg`` unchanged, same object) for a task whose yaml has no
    ``variation:`` block. Deterministic in ``seed``; only declared ``cfg.task``
    leaves change. ``difficulty`` is accepted for call-site compatibility and
    currently unused: every axis samples its full envelope until tiers are cut
    from sweep data (variation_axes_plain_zh.md section 5).
    """
    directives = _parse_directives(cfg["task"])
    if not directives:
        return cfg

    derived = next((d for d in directives if isinstance(d, _Derived)), None)
    derive_fn = _resolve_fn(derived.fn) if derived else None
    validate = next((d for d in directives if isinstance(d, _Validate)), None)
    validate_fn = _resolve_fn(validate.fn) if validate else None
    max_retries = int(validate.max_retries) if validate else 0

    vrng = VariantRng(seed)
    prefix = str(task_id)
    last_error = None
    for retry in range(max_retries + 1):
        out = _unlocked_copy(cfg)
        _apply(out["task"], directives, vrng, prefix, retry)
        try:
            if derive_fn is not None:
                derive_fn(out["task"])  # a ValueError here (empty range) rejects too
            if validate_fn is not None:
                validate_fn(out["task"])
        except ValueError as exc:
            if validate is None:
                raise
            last_error = exc
            continue
        return out
    raise RuntimeError(
        f"{task_id}: layout rejected {max_retries + 1} times for seed {int(seed)}; "
        f"the declared envelope is too wide. Last reason: {last_error}"
    )
