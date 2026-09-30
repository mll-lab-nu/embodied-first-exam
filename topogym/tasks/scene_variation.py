"""Seeded scene variation: one seed picks a difficulty tier and one pose/appearance draw.

``variation_id="seeded"`` resolves the tier as ``seed % 3`` (``VariantRng.tier``) and
overrides the leaves listed in ``AXES`` with values drawn from named streams of the
same seed. Only placement, orientation, colour and material leaves are listed, never
sizes or geometry, so every draw is a rigid move or a re-finish of the nominal scene.
Explicit tier names keep the nominal scene; nothing here runs for them.

Axis kinds:
- ``offset``: add U[lo, hi] to the tier's own default, per component (``None`` keeps
  that component);
- ``choice``: pick one entry of ``values`` with equal probability.
"""
from copy import deepcopy
from collections.abc import Mapping
from itertools import permutations

import numpy as np

from topogym.assets.geometry.lock_picking import DISC_COLORS
from topogym.tasks.base import _parameter_at
from topogym.utils.variant_rng import VariantRng

SCENE_VARIATION_VERSION = 1

# task_id -> axes shared by its three tiers (each offset applies to the tier's own default).
AXES = {
    "horseshoe_ring": (
        # Goal region pinned to -y; bounds keep the reach proxy within +2 cm (tests/check_scene_variation.py).
        dict(path="center_xy_m", kind="offset", range=[[-.03, .04], [-.01, .03]]),
        dict(path="yaw_deg", kind="offset", range=[-10., 10.]),
        # Silver would match the horseshoes; keep the ring distinguishable.
        dict(path="target_ring_finish", kind="choice", values=["copper", "coated_metal"], visual=True),
    ),
    "cast_coil": (
        # Both pieces move together; the silver offset stays in world XY. +y moves the
        # silver piece (already at y ~ 0.23) away from both arms, so y only decreases.
        dict(path="center_xy_m", kind="offset", range=[[-.03, .03], [-.03, 0.]]),
        dict(path="yaw_deg", kind="offset", range=[-10., 10.]),
        # Brightness of each metal; hue stays because the instruction names gold and silver.
        dict(path="piece_tint.gold", kind="offset", range=[-.1, .1], visual=True),
        dict(path="piece_tint.silver", kind="offset", range=[-.1, .1], visual=True),
    ),
    "cast_keyhole": (
        # Inside the reference policy's IK tolerance (+-20 mm); goal region pinned to +y.
        dict(path="center_xy_m", kind="offset", range=[[-.02, .02], [-.02, .02]]),
        dict(path="yaw_deg", kind="offset", range=[-5., 5.]),
        # Brightness of each metal; hue stays because the instruction names gold and silver.
        dict(path="piece_tint.gold", kind="offset", range=[-.1, .1], visual=True),
        dict(path="piece_tint.silver", kind="offset", range=[-.1, .1], visual=True),
    ),
    "hedgehog_in_cage": (
        # Panda base at x = -0.57: +x/+y moves away from it (reach proxy), so both lean negative.
        dict(path="center_xy_m", kind="offset", range=[[-.03, .01], [-.02, .01]]),
        dict(path="yaw_deg", kind="offset", range=[-5., 5.]),
        dict(path="wood_tint", kind="offset", range=[-.15, 0.], visual=True),
    ),
    "buzz_wire_3d": (
        # -y pushes the finish-side IK past tolerance and the far corner is 0.88 m from
        # the Panda base, so the fixture only moves -x/+y. No yaw: route frames are unrotated.
        dict(path="center_xy_m", kind="offset", range=[[-.015, 0.], [0., .015]]),
        dict(path="wood_tint", kind="offset", range=[-.2, 0.], visual=True),
        # Copper or brass; the steel loop stays distinct from either.
        dict(path="rail_rgb", kind="choice", values=[[.72, .33, .16], [.78, .60, .25]], visual=True),
    ),
    "fiber_bundling": (
        # Feeding holds the sheath near x ~ 0.2, ~0.8 m from the Panda base: no +x.
        # Strand fan/bend/curl are already drawn from the episode seed by FiberLayout.
        dict(path="center_xy_m", kind="offset", range=[[-.02, 0.], [-.02, .02]]),
    ),
    "lock_picking": (
        # Evaluator and planner read both from the geometry; world +x stays the key axis, so no yaw.
        # +x/-y move the key away from the Panda base; +y stops 4 cm short of its footprint.
        dict(path="geometry.first_x", kind="offset", range=[-.04, .01]),
        dict(path="geometry.center_y", kind="offset", range=[-.01, .02]),
        # Any order of the three rotor colours; all stay distinct from the yellow slot outline.
        dict(path="disc_colors", kind="choice", visual=True, values=[
            [DISC_COLORS[i] for i in order] for order in permutations(range(3))]),
        dict(path="base_finish", kind="choice", values=["coated_metal", "engineering_plastic"], visual=True),
    ),
    "orbits": (
        dict(path="yaw_deg", kind="offset", range=[-5., 5.]),
        # Goal region pinned to -y: the +y side already holds the handle.
        dict(path="base_center_xy_m", kind="offset", range=[[-.03, .03], [-.02, .02]]),
        # The handle stays wooden (the instruction names it).
        dict(path="cord_finish", kind="choice", values=["hemp", "orange_rope", "golden_rope"], visual=True),
    ),
    "rope_threading": (
        # The nominal scene fills 95-96% of cam_high/cam_low, and a turn swings the
        # 1.1 m rope's far end (5 deg -> ~5 cm), so this envelope is small.
        dict(path="geometry.translation_m", kind="offset", range=[[-.01, .02], [-.01, 0.], None]),
        dict(path="geometry.yaw_deg", kind="offset", range=[-2., 2.]),
        # Ring colours stay: the instruction orders the rings cyan, green, purple.
        dict(path="rope_finish", kind="choice", values=["hemp", "orange_rope", "golden_rope"], visual=True),
    ),
    "slotted_post_ring": (
        # FEM volumes cannot rotate, so translation only; -y beyond ~2.5 cm pushes the discs out of frame.
        dict(path="center_xy_m", kind="offset", range=[[-.05, .05], [-.02, .05]]),
        dict(path="cord_finish", kind="choice", values=["hemp", "orange_rope", "golden_rope"], visual=True),
    ),
    "interlocked_claws": (
        # No pose axes: the start is a two-hand pregrasp tied to arm joint angles and weld points.
        # The target stays brown (the instruction names it); the other piece takes any non-brown colour.
        dict(path="target_shade", kind="offset", range=[-.15, .15], visual=True),
        dict(path="other_rgb", kind="choice", visual=True, values=[
            None, [.18, .32, .65], [.25, .55, .30], [.50, .52, .55]]),
    ),
    "blanket_flatten": (
        # Drawn before freezing: each seeded instance gets its own prepared archive
        # (scripts/prepare_blanket_initial_states.py --seeded). Coverage is footprint
        # area / 0.288 m^2, independent of position; -y would crowd the home grippers.
        dict(path="color", kind="choice", visual=True, values=[
            [.22, .46, .70], [.70, .20, .18], [.22, .52, .30], [.80, .62, .18], [.45, .47, .50]]),
        dict(path="texture.pattern", kind="choice", values=["grid", "stripes"], visual=True),
        dict(path="center_xy_m", kind="offset", range=[[-.04, .04], [0., .03]]),
    ),
    "knot_untying": (
        # The knot sits at world x = 0, 13.6 cm right of the table centre: shift leans -x.
        # Its tails point -y, away from the arm line (y = -0.019): -y and a positive turn
        # push them out of reach (reach proxy), so both bounds are asymmetric.
        dict(path="origin_xy_m", kind="offset", range=[[-.06, .02], [-.01, .04]]),
        # Success counts projected crossings, invariant under a turn about z.
        dict(path="yaw_deg", kind="offset", range=[-30., 15.]),
        dict(path="rope_finish", kind="choice", values=["hemp", "orange_rope", "golden_rope"], visual=True),
    ),
}


def axes(task_class):
    return tuple(AXES.get(task_class.task_id, ()))


def _stream_name(task_class, axis):
    return f"{'visual/' if axis.get('visual') else ''}{task_class.task_id}/{axis['path']}"


def _plain(value):
    """JSON-safe Python values; numpy scalars break the instance_id hash."""
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_plain(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return deepcopy(value)


def _assign(tree, path, value):
    *parents, leaf = path.split(".")
    for name in parents:
        tree = tree.setdefault(name, {})
    tree[leaf] = value


def draw(task_class, seed):
    """Nested task-parameter overrides for ``seed``; a pure function of (seed, axis name)."""
    rng = VariantRng(seed)
    values = {}
    for axis in axes(task_class):
        stream = rng.stream(_stream_name(task_class, axis))
        if axis["kind"] == "offset":
            base = _parameter_at(task_class.defaults, axis["path"])
            if np.ndim(base) == 0:
                lo, hi = axis["range"]
                value = float(base) + float(stream.uniform(lo, hi))
            else:
                value = [float(b) if r is None else float(b) + float(stream.uniform(*r))
                         for b, r in zip(base, axis["range"], strict=True)]
        elif axis["kind"] == "choice":
            value = axis["values"][int(stream.integers(len(axis["values"])))]
        else:
            raise ValueError(f"Unknown scene variation kind: {axis['kind']!r}")
        _assign(values, axis["path"], _plain(value))
    return values


def within_envelope(task_class, config, *, atol=1e-9):
    """True if ``config`` equals the tier defaults except for in-envelope axis leaves."""
    listed = {axis["path"]: axis for axis in axes(task_class)}
    for path, axis in listed.items():
        value, base = _parameter_at(config, path), _parameter_at(task_class.defaults, path)
        if axis["kind"] == "choice":
            if _plain(value) not in [_plain(v) for v in axis["values"]] and _plain(value) != _plain(base):
                return False
            continue
        ranges = [axis["range"]] if np.ndim(base) == 0 else axis["range"]
        delta = np.atleast_1d(np.asarray(value, float) - np.asarray(base, float))
        for d, r in zip(delta, ranges, strict=True):
            if (r is None and abs(d) > atol) or (r is not None and not r[0] - atol <= d <= r[1] + atol):
                return False

    def rest(tree, prefix=""):
        # Everything outside the listed axis leaves, flattened by dotted path.
        out = {}
        for key, value in tree.items():
            path = f"{prefix}{key}"
            if path in listed:
                continue
            if isinstance(value, Mapping):
                out.update(rest(value, path + "."))
            else:
                out[path] = value
        return out

    return rest(_plain_tree(config)) == rest(_plain_tree(task_class.defaults))


def _plain_tree(tree):
    return {k: _plain_tree(v) if isinstance(v, Mapping) else _plain(v) for k, v in tree.items()}
