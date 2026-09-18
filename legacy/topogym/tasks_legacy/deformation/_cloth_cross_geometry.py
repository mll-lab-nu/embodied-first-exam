"""Sequential orthogonal knife folds of a sheet with a flat material metric.

The second fold rotates the first fold's normal, reversing its layer order in
the middle panel. This is not the sum of two height fields. Rounded hinges
provide collision clearance; their finite thickness requires relaxation against
the FLAT sheet's rest edges in the solver, never rest edges from this map.
"""
from __future__ import annotations

import math

import numpy as np

from ._cloth_unpleat_geometry import (
    EDGE_INSET_MAX,
    EDGE_INSET_MIN,
    WORKSPACE_MARGIN,
    pull_room,
    workspace_margin,
)


def dimensions(fold):
    lead, depth, tail, radius = (float(fold[k]) for k in ("lead", "depth", "tail", "radius"))
    return lead + depth + tail + 2 * np.pi * radius, lead - depth + tail


def rounded_pleat(s, fold):
    """Arc-length coordinate -> plan position, height and tangent angle."""
    a, w, t, r = (float(fold[k]) for k in ("lead", "depth", "tail", "radius"))
    s = np.asarray(s, dtype=float)
    length, span = dimensions(fold)
    if min(a, w, t, r) <= 0 or t <= w + r or a <= w + r:
        raise ValueError("cross fold needs positive hinges and bare ends past both turns")
    if np.any(s < -1e-6) or np.any(s > length + 1e-6):
        raise ValueError("material coordinate outside cross sheet")
    x, z, theta = s.copy(), np.zeros_like(s), np.zeros_like(s)
    turn = np.clip((s - a) / r, 0, np.pi)
    mask = (s >= a) & (s < a + np.pi * r)
    x[mask] = a + r * np.sin(turn[mask])
    z[mask] = r * (1 - np.cos(turn[mask]))
    theta[mask] = turn[mask]
    mask = (s >= a + np.pi * r) & (s < a + np.pi * r + w)
    x[mask] = a - (s[mask] - a - np.pi * r)
    z[mask], theta[mask] = 2 * r, np.pi
    turn = np.clip((s - a - np.pi * r - w) / r, 0, np.pi)
    mask = (s >= a + np.pi * r + w) & (s < a + 2 * np.pi * r + w)
    x[mask] = a - w - r * np.sin(turn[mask])
    z[mask] = 2 * r + r * (1 - np.cos(turn[mask]))
    theta[mask] = np.pi - turn[mask]
    mask = s >= a + 2 * np.pi * r + w
    x[mask] = a - w + s[mask] - a - 2 * np.pi * r - w
    z[mask] = 4 * r
    return x - span / 2, z, theta


def _layered_rounded_pleat(s, fold, offset):
    """Map a second-fold section while preserving each layer's arc length.

    ``fold_flat_nodes`` first makes a stack with signed normal offset ``offset``.
    Treating every layer as the neutral surface (the old implementation) gives
    the inner and outer layers the same radius at the second hinge, so their
    material edges start with stretch/compression already baked into the spawn.
    A parallel curve has radius ``r - offset`` on the first half-turn and
    ``r + offset`` on the return half-turn.  Those two changes cancel in total,
    so the flat sheet's total length and both bare endpoints stay fixed while
    PBD is free to settle the hinge naturally.

    This is still only an initial fold pattern.  It does not impose a constraint
    after the scene is built; the existing settle window decides how much of the
    rounded hinge remains physically stable.
    """

    a, w, t, r = (float(fold[k]) for k in ("lead", "depth", "tail", "radius"))
    s, offset = np.broadcast_arrays(np.asarray(s, dtype=float), np.asarray(offset, dtype=float))
    length, span = dimensions(fold)
    if min(a, w, t, r) <= 0 or t <= w + r or a <= w + r:
        raise ValueError("cross fold needs positive hinges and bare ends past both turns")
    if np.any(s < -1e-6) or np.any(s > length + 1e-6):
        raise ValueError("material coordinate outside cross sheet")

    # The first-fold stack is only a few particle radii thick.  Keep the
    # calculation defined for a diagnostic config that asks for a tighter
    # second hinge, while retaining the authored sign of the offset.
    eps = np.finfo(float).eps
    q1 = np.maximum(r - offset, eps)
    q2 = np.maximum(r + offset, eps)
    b1 = a
    b2 = a + np.pi * q1
    b3 = b2 + w
    b4 = b3 + np.pi * q2

    x = s.copy()
    z = offset.copy()
    theta = np.zeros_like(s)

    mask = (s >= b1) & (s < b2)
    phi = (s - a) / q1
    x[mask] = a + q1[mask] * np.sin(phi[mask])
    z[mask] = r - q1[mask] * np.cos(phi[mask])
    theta[mask] = phi[mask]

    mask = (s >= b2) & (s < b3)
    x[mask] = a - (s[mask] - b2[mask])
    z[mask] = 2 * r - offset[mask]
    theta[mask] = np.pi

    mask = (s >= b3) & (s < b4)
    phi = (s - b3) / q2
    x[mask] = a - w - q2[mask] * np.sin(phi[mask])
    z[mask] = 3 * r - q2[mask] * np.cos(phi[mask])
    theta[mask] = np.pi - phi[mask]

    mask = s >= b4
    x[mask] = a - w + s[mask] - b4[mask]
    z[mask] = 4 * r + offset[mask]
    return x - span / 2, z, theta


def cross_dimensions(cfg):
    cross = cfg["cloth"]["cross"]
    return [dimensions(cross[key]) for key in ("first", "second")]


def fold_flat_nodes(nodes, cfg, origin=(0, 0, 0)):
    """Initialize remeshed flat particles; identities and rest edges stay intact."""
    cloth = cfg["cloth"]
    cross = cloth["cross"]
    axis = "xy".index(str(cloth["material_axis"]))
    other = 1 - axis
    origin = np.asarray(origin, dtype=float)
    centre = origin[:2] + [float(cloth["center_x"]), float(cloth["center_y"])]
    nodes = np.asarray(nodes, dtype=float)
    lengths = cross_dimensions(cfg)
    s = (nodes[:, axis] - centre[axis]) * float(cloth["band_flip"]) + lengths[0][0] / 2
    u = (nodes[:, other] - centre[other]) * float(cross["flip"]) + lengths[1][0] / 2
    y, h, _ = rounded_pleat(s, cross["first"])
    half_stack = 2 * float(cross["first"]["radius"])
    h -= half_stack
    # The first stack is centred on the second fold's neutral surface. Its
    # normal is rotated with each panel, including the inverted middle panel.
    # Give every offset layer its own parallel-curve radius at the second
    # hinge.  The resulting mesh is an initial pattern; after this call the
    # solver is free to settle it under gravity and cloth contact.
    x, z, _ = _layered_rounded_pleat(u, cross["second"], h)
    out = nodes.copy()
    out[:, axis] = centre[axis] + float(cloth["band_flip"]) * y
    # `_layered_rounded_pleat` already returns the parallel curve for the
    # signed first-fold offset.  Do not apply the old neutral-surface offset a
    # second time here; doing so collapses one of the nine intersection levels.
    out[:, other] = centre[other] + float(cross["flip"]) * x
    out[:, 2] = origin[2] + float(cloth["z"]) + half_stack + z
    return out


# --------------------------------------------------------------- the envelope
# Everything below turns the `variation:` block's unit fractions into the four
# numbers each fold needs. Read it against one picture: a flat sheet lying on
# the table, folded once along a line running across it and once along a line
# running down it. One fold is described by how much bare cloth precedes the
# first crease (``lead``), how far the flap folds back (``depth``), how much
# bare cloth follows the second crease (``tail``), and the radius the crease is
# rounded to so the layers have somewhere to sit (``radius``).

#: How far a fold may reach back over itself, metres. The floor is what the
#: birth check `cross_overlap` needs: it allows the nine tracked material
#: patches to scatter by half the shallower fold's depth before it calls the
#: cross smeared, and half of 16 mm is 8 mm of slack. The ceiling matches the
#: widest pleat the parallel layout draws, so "how deep a fold is" means the
#: same thing in both layouts.
DEPTH_MIN, DEPTH_MAX = 0.016, 0.030


#: Second crease radius, in particle sizes. 1.5 is the floor the two clearance
#: rows give when read as equalities (see `fold_radii`). It is a separate knob
#: because it also sets how badly the fold map stretches the first fold's stack:
#: a layer h from the stack's middle traverses the second hinge on an arc of
#: radius ``r2 - h``, so its material spacing wants to scale by ``1 - h / r2``,
#: and `fold_flat_nodes` keeps every layer at its flat coordinate instead. At
#: the floor that is |1 +- 1/1.5| = 1.667 / 0.333 on the outer / inner layer.
SECOND_RADIUS_PARTICLES = 1.5


def _particle(cfg) -> float:
    return float(cfg["cloth"]["particle_size"])


def fold_radii(cfg) -> tuple[float, float]:
    """Crease radii the two folds must have, metres. Derived, never drawn.

    Both come from `ClothCrossLayout.checks()` read as equalities. The first
    fold's stack is two crease radii thick, and it has to be at least one
    particle thick or the solver cannot tell its layers apart, so
    ``r1 = particle / 2``. The second fold folds that whole stack back over
    itself, so its own crease has to clear four first-fold radii plus another
    particle: ``r2 = (particle + 4 * r1) / 2 = 1.5 * particle``.

    At the shipped 1 mm particle this is 0.0005 / 0.0015 -- the two numbers
    `configs/cloth_unpleat_cross.yaml` carries by hand.
    """

    particle = _particle(cfg)
    scale = float(cfg["cloth"]["cross"].get("second_radius_particles", SECOND_RADIUS_PARTICLES))
    if scale < SECOND_RADIUS_PARTICLES - 1e-9:
        raise ValueError(
            f"cloth.cross.second_radius_particles must be at least {SECOND_RADIUS_PARTICLES} "
            f"(the clearance row reads as an equality there), got {scale}."
        )
    return 0.5 * particle, scale * particle


def _bare_floor(cfg) -> float:
    """Bare cloth a grasped end needs past the crease, metres.

    The attachment disc (`grasp.attach_radius`) has to land wholly on single
    cloth, clear of the fold's multilayer strip, and the grasp point itself sits
    `grasp.edge_inset` in from the edge. So the bare panel outside the strip
    must hold both.
    """

    return float(cfg["grasp"]["attach_radius"]) + max(EDGE_INSET_MIN, 2.0 * _particle(cfg))


def run_floor(cfg, depth: float, radius: float) -> float:
    """Shortest ``lead`` or ``tail`` this fold can carry, metres.

    ``depth + radius`` is what the fold itself eats -- `rounded_pleat` refuses a
    fold whose bare ends do not clear both turns -- and `_bare_floor` is what
    the grasp needs on top of that.
    """

    return float(depth + radius + _bare_floor(cfg))


def depth_bounds(cfg, key: str) -> tuple[float, float]:
    return (DEPTH_MIN, DEPTH_MAX)


def depth_from_frac(cfg, key: str, frac: float) -> float:
    lo, hi = depth_bounds(cfg, key)
    return float(lo + min(max(float(frac), 0.0), 1.0) * (hi - lo))


def _sheet_max(cfg) -> float:
    return float(cfg["cloth"]["cross"]["sheet_max"])


def _sheet_min(cfg) -> float:
    return float(cfg["cloth"]["cross"].get("sheet_min", 0.0))


def run_bounds(cfg, key: str, name: str) -> tuple[float, float]:
    """``[lo, hi]`` for one fold's ``lead`` or ``tail``, out of the sheet budget.

    The sheet's material length along this fold is ``lead + depth + tail +
    2 * pi * radius`` and may not pass `cloth.cross.sheet_max`, so the two bare
    runs share one budget. ``lead`` is drawn first out of the whole budget and
    ``tail`` out of what is left, the same order `derive_task_cfg` uses for the
    band's two end runs.
    """

    fold = cfg["cloth"]["cross"][key]
    depth, radius = float(fold["depth"]), float(fold["radius"])
    floor = run_floor(cfg, depth, radius)
    fixed = depth + 2.0 * math.pi * radius          # what the fold itself takes
    budget = _sheet_max(cfg) - fixed - 2.0 * floor
    if name == "tail":
        budget -= float(fold["lead"]) - floor
        # `cloth.cross.sheet_min`: the sheet may not come out shorter than this
        # on either axis. The lead has already been drawn, so the tail's floor
        # rises to whatever closes the gap; it never passes the ceiling as long
        # as sheet_min <= sheet_max, which `derive_cross_cfg` asserts.
        floor = max(floor, _sheet_min(cfg) - fixed - float(fold["lead"]))
        budget = min(budget, _sheet_max(cfg) - fixed - float(fold["lead"]) - floor)
    if budget < -1e-9:
        raise ValueError(
            f"cloth_unpleat: the {key} fold's {name} has no sheet length left "
            f"({budget:+.4f} m; depth {depth:.4f}, sheet cap {_sheet_max(cfg):.4f})."
        )
    return float(floor), float(floor + max(budget, 0.0))


def run_from_frac(cfg, key: str, name: str, frac: float) -> float:
    lo, hi = run_bounds(cfg, key, name)
    return float(lo + min(max(float(frac), 0.0), 1.0) * (hi - lo))


def cross_edge_inset_bounds(cfg):
    """``[lo, hi]`` for `grasp.edge_inset` on a cross sheet.

    Both grasped edges are bare tail panels. A tail panel is ``tail`` long in
    plan view, but the flap folded back over it covers its first
    ``depth + radius``, so the bare part is ``tail - depth - radius`` and the
    attachment disc plus the inset have to fit inside that.
    """

    lo = max(EDGE_INSET_MIN, 2.0 * _particle(cfg))
    hi = EDGE_INSET_MAX
    for key in ("first", "second"):
        fold = cfg["cloth"]["cross"][key]
        bare = float(fold["tail"]) - float(fold["depth"]) - float(fold["radius"])
        hi = min(hi, bare - float(cfg["grasp"]["attach_radius"]))
    if hi < lo - 1e-12:
        raise ValueError(
            f"cloth_unpleat: no edge_inset keeps the attachment disc on bare cross cloth: "
            f"window [{lo:.4f}, {hi:.4f}]."
        )
    return float(lo), float(hi)


def cross_edge_inset_from_frac(cfg, frac: float) -> float:
    lo, hi = cross_edge_inset_bounds(cfg)
    return float(lo + min(max(float(frac), 0.0), 1.0) * (hi - lo))


# ------------------------------------------------------- where the sheet sits


def cross_hand_offsets(cfg):
    """Where the hand is, relative to the sheet's middle, at the four moments
    that matter: the start and the end of each of the two pulls.

    Returns ``(along, across)`` pairs in metres, ``along`` on the axis the first
    fold runs along (`cloth.material_axis`) and ``across`` on the other one.
    They mirror `ClothCrossLayout.design_grasp_point` and `pull_direction`
    exactly; the offline rows assert that they agree.

    The sequence, in words: the hand first takes the corner of the sheet where
    the second fold's bare tail meets the first fold's bare lead panel, and
    pulls straight out along the second fold's own direction until that fold's
    material is paid back. It lets go, the sheet is now its full width; it then
    takes the first fold's bare tail edge -- which has moved sideways with the
    restored width -- and pulls out along the first fold's direction.
    """

    cloth = cfg["cloth"]
    cross = cloth["cross"]
    dims = cross_dimensions(cfg)
    (length_1, span_1), (length_2, span_2) = dims
    inset = float(cfg["grasp"]["edge_inset"])
    scale = float(cfg["physical"]["pull_extend_max_scale"])
    sign_along = float(cloth["band_flip"])
    sign_across = float(cross["flip"])

    # Pull 1 pays back the SECOND fold and travels across; pull 2 pays back the
    # first fold and travels along.
    travel_across = (length_2 - span_2) * scale
    travel_along = (length_1 - span_1) * scale

    first = cross["first"]
    strip_low = float(first["lead"]) - float(first["depth"]) - float(first["radius"]) - span_1 / 2
    lead_offset = min(0.0, strip_low - float(cfg["grasp"]["attach_radius"]) - 2.0 * _particle(cfg))

    if str(cross.get("grasp", "edges")) == "corner":
        # One grasp held through both strokes: the hand takes the free corner and
        # never lets go, so the second stroke starts where the first one ended.
        grasp_1 = (sign_along * (span_1 / 2 - inset), sign_across * (span_2 / 2 - inset))
        end_1 = (grasp_1[0], grasp_1[1] + sign_across * travel_across)
        grasp_2 = end_1
        end_2 = (grasp_2[0] + sign_along * travel_along, grasp_2[1])
        return [grasp_1, end_1, grasp_2, end_2]

    grasp_1 = (sign_along * lead_offset, sign_across * (span_2 / 2 - inset))
    end_1 = (grasp_1[0], grasp_1[1] + sign_across * travel_across)
    grasp_2 = (sign_along * (span_1 / 2 - inset), sign_across * (length_2 - span_2) / 2)
    end_2 = (grasp_2[0] + sign_along * travel_along, grasp_2[1])
    return [grasp_1, end_1, grasp_2, end_2]


def cross_travel(cfg) -> tuple[float, float]:
    """Furthest each pull may travel, metres: pull 1 across, pull 2 along.

    The closed loop is allowed to keep pulling to the fold's stored material
    times `physical.pull_extend_max_scale`, so the feasibility rows book that,
    not the opening stroke's `physical.pull_scale`.
    """

    (length_1, span_1), (length_2, span_2) = cross_dimensions(cfg)
    scale = float(cfg["physical"]["pull_extend_max_scale"])
    return (length_2 - span_2) * scale, (length_1 - span_1) * scale


def cross_checks(cfg):
    """``[(name, measured, limit, ok)]``: what a spawnable, solvable cross needs.

    One list for the randomizer's reject step, the offline gate, the corner
    harness and the demo's start-up print -- the cross's counterpart to
    `_cloth_unpleat_geometry.cloth_unpleat_checks`. Metres; task frame.

    - ``band_in_workspace``  the flat sheet's four spawn corners clear the box.
    - ``first_layer_clearance``  the first fold's stack is two crease radii
      thick and the solver cannot separate layers thinner than one particle.
    - ``cross_stack_clearance``  the second fold folds that whole stack back
      over itself, so its crease has to clear four first-fold radii and another
      particle on top.
    - ``pull1_room`` / ``pull2_room``  straight travel left from each grasp
      point, inside both the reach disc and the box, against what that pull owes.
    """

    axis, across = _axes(cfg)
    cloth = cfg["cloth"]
    cross = cloth["cross"]
    dims = cross_dimensions(cfg)
    centre = np.zeros(2)
    centre[0], centre[1] = float(cloth["center_x"]), float(cloth["center_y"])
    half = np.zeros(2)
    half[axis], half[across] = dims[0][1] / 2, dims[1][1] / 2
    footprint = [centre + half * [sx, sy] for sx in (-1, 1) for sy in (-1, 1)]
    # The 1e-9 slack is not cosmetic: `cross_center_across_bounds` and
    # `cross_center_along_bounds` put the sheet EXACTLY on this limit when their
    # fraction is drawn at the end of the window, so an exact comparison would
    # reject the corner its own derivation just produced. Same slack, same
    # reason, as `_cloth_unpleat_geometry.cloth_unpleat_checks`.
    margin = workspace_margin(cfg, footprint)
    rows = [("band_in_workspace", margin, WORKSPACE_MARGIN, margin >= WORKSPACE_MARGIN - 1e-9)]

    particle = _particle(cfg)
    first_gap = 2 * float(cross["first"]["radius"])
    clearance = 2 * float(cross["second"]["radius"]) - 4 * float(cross["first"]["radius"])
    rows.append(("first_layer_clearance", first_gap, particle, first_gap >= particle - 1e-9))
    rows.append(("cross_stack_clearance", clearance, particle, clearance >= particle - 1e-9))

    offsets = cross_hand_offsets(cfg)
    travels = cross_travel(cfg)
    signs = (float(cross["flip"]), float(cloth["band_flip"]))
    for index in range(2):
        along, across_off = offsets[2 * index]
        point = centre.copy()
        point[axis] += along
        point[across] += across_off
        direction = np.zeros(2)
        direction[across if index == 0 else axis] = signs[index]
        room = pull_room(cfg, point, direction=direction)
        travel = travels[index]
        rows.append((f"pull{index + 1}_room", room, travel, room >= travel - 1e-9))
    return rows


def _axes(cfg):
    axis = "xy".index(str(cfg["cloth"]["material_axis"]))
    return axis, 1 - axis


def _box(cfg, index: int):
    box = cfg["workspace"]["x" if index == 0 else "y"]
    return float(box[0]) + WORKSPACE_MARGIN, float(box[1]) - WORKSPACE_MARGIN


def cross_center_across_bounds(cfg):
    """``[lo, hi]`` for the sheet's middle on the axis the first fold does NOT
    run along -- for the shipped `material_axis: y` that is task x, the
    direction that carries the sheet away from the arm's base.

    Drawn before the along position, because it is what fixes how much of the
    reach disc is left. The guard is the same one `center_across_bounds` uses
    for the band: assume the along position cannot help (the sheet's middle
    stays on the base's own line), work out the chord that leaves, and refuse
    any across position whose furthest hand point falls outside it.

    Unlike the band, this does NOT clamp to `cloth.center_across_min/max`. Those
    two are the band's own statement that a 12 cm strip's footprint has to stay
    inside the workspace box; a 21 cm sheet whose hand travels 16 cm across has
    a different footprint and a different answer, and the box is read directly
    here. Nothing stops the sheet sitting at negative x: that is TOWARD the
    arm's base, which costs reach nothing.
    """

    axis, across = _axes(cfg)
    base = [float(v) for v in cfg["reach"]["base_xy"]]
    radius = float(cfg["reach"]["max_hand_dist"])
    offsets = cross_hand_offsets(cfg)
    half_w = cross_dimensions(cfg)[1][1] / 2

    needed_along = max(abs(a) for a, _ in offsets)
    if needed_along >= radius:
        raise ValueError(
            f"cloth_unpleat: the cross's hand path reaches {needed_along:.4f} m along the "
            f"sheet, past the {radius:.4f} m reach radius."
        )
    chord = math.sqrt(radius * radius - needed_along * needed_along)

    lo_box, hi_box = _box(cfg, across)
    spans = [b for _, b in offsets] + [-half_w, half_w]
    lo = max(lo_box - min(spans), base[across] - chord - min(b for _, b in offsets))
    hi = min(hi_box - max(spans), base[across] + chord - max(b for _, b in offsets))
    if hi < lo - 1e-12:
        raise ValueError(
            f"cloth_unpleat: no across position keeps the cross's hand path inside reach "
            f"and workspace: window [{lo:+.4f}, {hi:+.4f}] (reach chord {chord:.4f})."
        )
    return float(lo), float(hi)


def cross_center_along_bounds(cfg):
    """``[lo, hi]`` for the sheet's middle on the axis the first fold runs along.

    With the across position fixed, each of the four hand points sits at a known
    distance from the base's line, so the reach disc gives each one its own
    chord; the window is where all four chords and the workspace box overlap,
    and the spawn footprint has to stay inside the box too.
    """

    axis, across = _axes(cfg)
    base = [float(v) for v in cfg["reach"]["base_xy"]]
    radius = float(cfg["reach"]["max_hand_dist"])
    centre_across = float(cfg["cloth"]["center_x" if across == 0 else "center_y"])
    offsets = cross_hand_offsets(cfg)
    half_l = cross_dimensions(cfg)[0][1] / 2

    lo_box, hi_box = _box(cfg, axis)
    lo, hi = lo_box + half_l, hi_box - half_l
    for along, across_off in offsets:
        gap = centre_across + across_off - base[across]
        inside = radius * radius - gap * gap
        if inside <= 0.0:
            raise ValueError(
                f"cloth_unpleat: a cross hand point sits {abs(gap):.4f} m off the base's line, "
                f"outside the {radius:.4f} m reach radius."
            )
        chord = math.sqrt(inside)
        lo = max(lo, base[axis] - chord - along, lo_box - along)
        hi = min(hi, base[axis] + chord - along, hi_box - along)
    if hi < lo - 1e-12:
        raise ValueError(
            f"cloth_unpleat: no along position keeps the cross's hand path inside reach and "
            f"workspace: window [{lo:+.4f}, {hi:+.4f}] (half length {half_l:.4f})."
        )
    return float(lo), float(hi)


def _from_frac(bounds, frac):
    lo, hi = bounds
    return float(lo + min(max(float(frac), 0.0), 1.0) * (hi - lo))


#: Locked tabletop preset the cross layout runs under. Same geometry as
#: `topogym_tabletop_v1`, 16 substeps instead of 4; declared in
#: `topogym/world/tabletop.py` so the lock still checks it.
CROSS_PRESET_ID = "topogym_tabletop_v1_fine"


def apply_cross_solver(task_cfg) -> None:
    """Write the task-side half of the cross's solver preset (see the yaml).

    Particle size, the height the sheet spawns at (one particle radius, the
    balance height of cloth resting on the table) and the control mesh's
    spacing. The other half -- the solver's substep count -- lives under
    ``env`` and is set by `cloth_unpleat.apply_layout_solver`.

    Idempotent, and called from two places on purpose: `derive_cross_cfg` needs
    the particle size before it can derive the crease radii, and a run with no
    ``variation:`` block never reaches `derive_cross_cfg` at all.
    """

    solver = task_cfg["cloth"]["cross"]["solver"]
    cloth = task_cfg["cloth"]
    cloth["particle_size"] = float(solver["particle_size"])
    cloth["z"] = 0.5 * float(solver["particle_size"])
    cloth["mesh"]["spacing"] = float(solver["mesh_spacing"])


def derive_cross_cfg(cfg):
    """Turn the drawn fractions into a cross sheet, in dependency order.

    0. the solver preset's task-side leaves, because the particle size is what
       the crease radii come from;
    1. the crease radii, which only the particle size decides;
    2. how deep each fold reaches back;
    3. each fold's two bare runs, out of the sheet-size budget -- **the sheet's
       material length and width fall out of those** and are written back,
       because the judge divides both recovery readings by them;
    4. the grasp inset, whose window is what the bare tails leave;
    5. the sheet's across position, then its along position, both of which need
       every hand point of both pulls.

    A ``ValueError`` (an empty window) rejects the draw.
    """

    # Item access throughout, never attributes: the offline gate runs this on
    # plain dicts loaded with PyYAML, the sampler on an OmegaConf node.
    apply_cross_solver(cfg)
    if _sheet_min(cfg) > _sheet_max(cfg) + 1e-12:
        raise ValueError(
            f"cloth_unpleat: cloth.cross.sheet_min {_sheet_min(cfg)} exceeds sheet_max {_sheet_max(cfg)}."
        )
    cloth = cfg["cloth"]
    cross = cloth["cross"]
    for key, radius in zip(("first", "second"), fold_radii(cfg)):
        cross[key]["radius"] = float(radius)
        cross[key]["depth"] = depth_from_frac(cfg, key, float(cross[key]["depth_frac"]))
    for key in ("first", "second"):
        for name in ("lead", "tail"):
            cross[key][name] = run_from_frac(cfg, key, name, float(cross[key][f"{name}_frac"]))

    lengths = cross_dimensions(cfg)
    cloth["material_length"] = float(lengths[0][0])
    cloth["width"] = float(lengths[1][0])

    # The two pulls run on perpendicular axes, so a wrist yaw tied to "the pull
    # direction" would have to flip between the legs. The validated sample let
    # the arm choose its own posture; follow that rather than the band's value.
    cfg["grasp"]["finger_axis"] = str(cfg["cloth"]["cross"]["finger_axis"])
    cfg["grasp"]["edge_inset"] = cross_edge_inset_from_frac(cfg, float(cfg["grasp"]["edge_inset_frac"]))
    axis, across = _axes(cfg)
    across_leaf = "center_x" if across == 0 else "center_y"
    along_leaf = "center_x" if axis == 0 else "center_y"
    cloth[across_leaf] = _from_frac(cross_center_across_bounds(cfg), float(cloth[f"{across_leaf}_frac"]))
    cloth[along_leaf] = _from_frac(cross_center_along_bounds(cfg), float(cloth[f"{along_leaf}_frac"]))


def cross_stack_report(nodes, material, cfg):
    """Track nine material patches through remeshing, including layer reversal.

    This oracle uses flat material positions saved by the builder, never an
    assumed rectangular particle order. Coincident layers do not count as an
    intact cross even if the outline still stores material along both axes.
    """
    cloth = cfg["cloth"]
    dims = cross_dimensions(cfg)
    axis = "xy".index(str(cloth["material_axis"]))
    across = 1 - axis
    # Mesh remeshing need not distribute particles symmetrically; its actual
    # boundary extrema recover the authored flat rectangle's centre exactly.
    material = np.asarray(material)
    centres = (np.min(material[:, :2], axis=0) + np.max(material[:, :2], axis=0)) / 2
    locations = []
    for key in ("first", "second"):
        f = cloth["cross"][key]
        a, w, r = (float(f[k]) for k in ("lead", "depth", "radius"))
        locations.append([a - w / 2, a + np.pi * r + w / 2,
                          a + 2 * np.pi * r + 1.5 * w])
    patches = []
    radius = max(1.5 * float(cloth["particle_size"]), float(cloth["mesh"]["spacing"]))
    for u in locations[1]:
        for s in locations[0]:
            xy = centres.copy()
            xy[axis] += float(cloth["band_flip"]) * (s - dims[0][0] / 2)
            xy[across] += float(cloth["cross"]["flip"]) * (u - dims[1][0] / 2)
            ids = np.linalg.norm(material[:, :2] - xy, axis=1) <= radius
            if not ids.any():
                raise ValueError("no material particles in cross layer probe")
            patches.append(np.median(np.asarray(nodes)[ids], axis=0))
    patches = np.asarray(patches)
    order = [0, 1, 2, 5, 4, 3, 6, 7, 8]
    return dict(min_layer_gap=float(np.diff(patches[order, 2]).min()),
                patch_span=float(np.ptp(patches[:, :2], axis=0).max()))


def cross_spawn_checks(earlier, nodes, material, cfg):
    """A cross must survive an unforced observation window before any grasp."""
    dims = cross_dimensions(cfg)
    axis = "xy".index(str(cfg["cloth"]["material_axis"]))
    spans = np.ptp(np.asarray(nodes)[:, :2], axis=0)
    drift = float(np.max(np.abs(spans - np.ptp(np.asarray(earlier)[:, :2], axis=0))))
    stack = cross_stack_report(nodes, material, cfg)
    particle = float(cfg["cloth"]["particle_size"])
    first, second = (cfg["cloth"]["cross"][key] for key in ("first", "second"))
    return [
        ("unforced_span_drift", drift, 0.002, drift <= 0.002),
        ("length_stored", dims[0][0] - spans[axis], 2 * float(first["depth"]) - particle,
         dims[0][0] - spans[axis] >= 2 * float(first["depth"]) - particle),
        ("width_stored", dims[1][0] - spans[1-axis], 2 * float(second["depth"]) - particle,
         dims[1][0] - spans[1-axis] >= 2 * float(second["depth"]) - particle),
        ("cross_layer_order", stack["min_layer_gap"], 0.25 * particle,
         stack["min_layer_gap"] >= 0.25 * particle),
        ("cross_overlap", stack["patch_span"], min(float(first["depth"]), float(second["depth"])) / 2,
         stack["patch_span"] <= min(float(first["depth"]), float(second["depth"])) / 2),
    ]
