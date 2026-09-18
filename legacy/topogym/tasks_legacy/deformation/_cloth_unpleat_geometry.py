"""cloth_unpleat's layout rules and feasibility checks, numpy only.

Kept apart from `cloth_unpleat.py` so the offline gate
(`tests/check_cloth_unpleat_geometry.py`) and the variation harness can load
them without Genesis: `cloth_unpleat.py` imports Genesis at module level.
Everything here takes the TASK config alone (a dict or an OmegaConf node under
``cfg.task``) and works in the task frame, metres, table at z = 0: the
workspace box and the arm base are task-frame quantities, so no world origin
is needed for any row.

The scene, for the reader who has only this file: a cloth band 12 cm wide lies
on the table with its length along one horizontal axis (`material_axis`). It
carries ONE or TWO unpressed knife pleats, every crease square across the band
-- at each one the band doubles back and up to a crest, then comes back down
past the crease and continues -- so a strip of plan width `width` ending at
each crease stacks three layers deep. Between and either side of the pleats
the band is flat on the table; those flat runs are `cloth.lead`,
`cloth.pleat.gap` and `cloth.tail`, and they are drawn, not derived from a
fixed band length. **The band's length follows from them**:

    material_length  =  lead + w1 + gap + w2 + tail  +  stored(1) + stored(2)
                        \\_________ plan span _________/

The gripper takes the band's TAIL end `edge_inset` in from the edge and drags
it along the table, along the band's own axis, by that end's own pleat's stored
material times `pull_scale`. Every pull takes the tail: a knife pleat's two
arms continue into the tail side, so pulling the tail peels the fold open from
its top, while pulling the lead-in would drag the fold's bottom layer out from
under its own stack. For two pleats the nearer and farther strokes are joined
while the gripper stays attached; the lead-in end is the anchor throughout.

**No slanted creases.** The 2026-09-08 slant slid each sweep station's pleat a
different distance along the band, which keeps the outline rectangular but is
not a fold of a sheet along a line -- and the physics showed it: pulled along
the band the band bent at the crease by up to 43 mm at 34 degrees, pulled along
the crease normal it bent MORE (63 mm), because the material really is straight
along the band at every station. Removed 2026-09-10. Richer shapes come from
the pleat LAYOUT instead (`cloth.pleat.layout`): one pleat, two parallel ones,
and -- to come -- a cross, where the second pleat folds the band's width.
"""

from __future__ import annotations

import math

import numpy as np

from .cloth_profile_mesh import pleats_landmarks, pleats_profile

# ------------------------------------------------------------- envelope rules
#: A bare band end keeps at least this many control mesh spacings, so no pleat
#: sits at the very end of the band.
MIN_TAIL_SPACINGS = 4
#: `grasp.edge_inset` window before the three-layer clearance caps it. The
#: floor is two particle sizes (the attachment disc must land wholly on cloth);
#: the ceiling is the value the yaml has carried since 2026-08-23 plus 6 mm.
EDGE_INSET_MIN = 0.008
EDGE_INSET_MAX = 0.018
#: How far the band's middle may slide along its own axis from the yaml's
#: baseline position, before the reach and workspace rows cap it. 0.090 since
#: 2026-09-10: every pull takes the SAME end, so a two-pleat band's pulled end
#: travels both pleats' material while the other end never moves -- and the
#: room for that comes from spawning the band further toward the anchored side.
#: The arm base sits on this axis's zero and the workspace box is symmetric
#: about it, so nothing physical pinned the old +-0.030.
CENTER_ALONG_BASE = 0.0
CENTER_ALONG_SHIFT = 0.090
#: Smallest distance any point of the band -- spawn footprint or pull end -- may
#: come to the workspace box's x / y edges (same value as rope_unwinding).
WORKSPACE_MARGIN = 0.040
#: Per-pleat design allocation bound (the widest pleat asks 116 mm).
#: A continuous two-pleat grasp may use the SUM of both allocations, capped by
#: actual workspace/reach room; 120 mm is not a physical total-grasp limit.
PULL_MAX = 0.120
#: Shortest flat run the control mesh can carry between two pleats. A run of
#: zero would be a zero-length segment, which `resample_polyline` cannot sweep
#: into a grid; one particle is the smallest length the cloth resolves anyway.
MIN_GAP_PARTICLES = 1

LAYOUTS = ("single", "parallel", "cross")



def _cloth(cfg):
    return cfg["cloth"]


def material_axis(cfg) -> int:
    """0 when the band's length runs along task x, 1 along task y."""

    axis = str(_cloth(cfg)["material_axis"]).lower()
    if axis not in ("x", "y"):
        raise ValueError(f"cloth.material_axis must be 'x' or 'y', got {axis!r}.")
    return 0 if axis == "x" else 1


def band_sign(cfg) -> float:
    """+1 for the band as built, -1 for the whole band mirrored on its own axis.

    `cloth.band_flip: -1` reflects the ENTIRE band -- profile and placement --
    about its middle, so the end that was the tail lies at the negative end of
    the material axis and every pull runs the other way. It is a mirror, not a
    different shape: every length below reads the same for both signs, and the
    arm base sits on y = 0 with the workspace box symmetric about it, so with
    the band along y the two signs are equally reachable.

    Reversing a SINGLE pleat inside the band would not be this. A knife pleat is
    not symmetric -- the arms are ``hypot(w, h)`` and ``hypot(2w, h)`` -- so that
    is a different shape (`cloth_profile_mesh.pleats_profile` says which), and
    the task does not use it.
    """

    cloth = _cloth(cfg)
    flip = cloth.get("band_flip", 1) if hasattr(cloth, "get") else 1
    return -1.0 if int(flip) < 0 else 1.0


def band_centre_task(cfg) -> np.ndarray:
    """Task-frame (x, y) of the band's plan-view middle."""

    cloth = _cloth(cfg)
    return np.array([float(cloth["center_x"]), float(cloth["center_y"])], dtype=float)


# ------------------------------------------------------------- the pleat list


def pleat_layout(cfg) -> str:
    """``single`` or ``parallel`` (a cross is the next shape to land)."""

    value = str(_cloth(cfg)["pleat"]["layout"])
    if value not in LAYOUTS:
        raise ValueError(f"cloth.pleat.layout must be one of {LAYOUTS}, got {value!r}.")
    return value


def pleat_count(cfg) -> int:
    """How many pleats the layout has, counting both axes."""

    return 1 if pleat_layout(cfg) == "single" else 2



def pleat_sizes(cfg) -> list[tuple[float, float]]:
    """``[(width, crest_height)]`` per pleat, in material order."""

    pleat = _cloth(cfg)["pleat"]
    keys = ("a", "b") if pleat_layout(cfg) == "parallel" else ("a",)
    return [(float(pleat[k]["width"]), float(pleat[k]["crest_height"])) for k in keys]









def band_runs(cfg) -> list[float]:
    """The flat runs, in material order: ``[lead, tail]`` or ``[lead, gap, tail]``."""

    cloth = _cloth(cfg)
    if pleat_count(cfg) == 1:
        return [float(cloth["lead"]), float(cloth["tail"])]
    return [float(cloth["lead"]), float(cloth["pleat"]["gap"]), float(cloth["tail"])]


def band_profile(cfg) -> np.ndarray:
    """The (along-band, height) corners of the band's profile, unmirrored."""

    return pleats_profile(runs=band_runs(cfg), pleats=pleat_sizes(cfg), rest_z=float(_cloth(cfg)["z"]))


def pleat_marks(cfg) -> dict:
    """`pleats_landmarks` of the profile, plus the band's own lengths.

    ``bare_runs`` is the flat length at each END that carries no three-layer
    strip -- the lead-in minus the first pleat's width at the start, the tail as
    it stands at the finish. The tail is what the gripper takes. The sign is not
    applied here: these are lengths.
    """

    marks = pleats_landmarks(band_profile(cfg))
    runs, sizes = marks["runs"], pleat_sizes(cfg)
    marks["lead"] = runs[0]
    marks["tail"] = runs[-1]
    marks["gap"] = runs[1] if len(runs) > 2 else None
    marks["bare_runs"] = [runs[0] - sizes[0][0], runs[-1]]
    marks["half_span"] = 0.5 * float(marks["plan_span"])
    return marks


# ---------------------------------------------------------------- floors


def grasp_clearance(cfg) -> float:
    """Bare band an end needs before the gripper can take it: inset + disc."""

    inset_floor = max(EDGE_INSET_MIN, 2.0 * float(_cloth(cfg)["particle_size"]))
    return inset_floor + 2.0 * float(cfg["grasp"]["attach_radius"])


def gap_floor(cfg) -> float:
    """Shortest flat run allowed between two parallel pleats, metres.

    One particle is the mesh's hard floor (a zero-length run cannot be swept
    into a grid). And ``parallel`` means the two three-layer strips lie side by
    side, never one over the other: the second strip runs back ``w2`` from its
    crease, so the run in front of that crease has to be at least ``w2 - w1``
    for it to stop short of the first strip. Overlapping strips are the cross
    layout's business, not this one's.
    """

    particle = float(_cloth(cfg)["particle_size"])
    floor = MIN_GAP_PARTICLES * particle
    if pleat_count(cfg) < 2:
        return floor
    (w1, _), (w2, _) = pleat_sizes(cfg)
    return float(max(floor, w2 - w1))


def lead_floor(cfg) -> float:
    """Shortest lead-in: it carries the first pleat's strip and is never grasped."""

    width = pleat_sizes(cfg)[0][0]
    spacings = MIN_TAIL_SPACINGS * float(_cloth(cfg)["mesh"]["spacing"])
    # With two pulls the opened tail is longer and its drag can tow the short
    # anchor instead of opening the remaining fold. Fixed-length A/B moves
    # material from the gap to the lead-in; the shallow c017 needs 130 mm.
    return float(max(width + spacings, 0.130))


def tail_floor(cfg) -> float:
    """Shortest tail: bare, and always grasped."""

    spacings = MIN_TAIL_SPACINGS * float(_cloth(cfg)["mesh"]["spacing"])
    return float(max(spacings, grasp_clearance(cfg)))






def run_floors(cfg) -> list[float]:
    """Each flat run's floor, in material order."""

    out = [lead_floor(cfg)]
    if pleat_count(cfg) > 1:
        out.append(gap_floor(cfg))
    out.append(tail_floor(cfg))
    return out


def stored_per_pleat(cfg) -> list[float]:
    """Material each pleat holds, metres. Independent of where the pleats sit."""

    return [math.hypot(w, h) + math.hypot(2.0 * w, h) - w for w, h in pleat_sizes(cfg)]


def band_length_floor(cfg) -> float:
    """Shortest band that fits this set of pleats, every run at its floor."""

    sizes = pleat_sizes(cfg)
    return float(sum(run_floors(cfg)) + sum(w for w, _ in sizes) + sum(stored_per_pleat(cfg)))


def _inset_floor(cfg) -> float:
    return max(EDGE_INSET_MIN, 2.0 * float(_cloth(cfg)["particle_size"]))


def _pull_overshoot(cfg) -> float:
    """How far past its spawn position the pulled end goes, at the furthest.

    Every pull takes the same end, so the strokes ADD UP: reserve the sum of
    every earlier pull's maximum stroke plus this one's.

    It must be the SUM OF `pull_distance_max`, not the sum of the pleats'
    stored material plus this pull's maximum. `center_along_bounds` places the
    band with the former, so reserving the latter here under-books the room by
    ``(pull_extend_max_scale - 1) x earlier pleats' stored`` -- 27.7 mm at the
    shipped 1.5 and a 55 mm first pleat. `band_length_ceiling` would then admit
    bands whose along window is empty, and a quarter of the analytic corners
    (3072 of 12288) and 12.7% of first draws were rejected for exactly that.
    """

    along = [
        sum(pull_distance_max(cfg, j) for j in range(i + 1))
        for i, p in enumerate(pulls(cfg))
        if p["axis"] == "along"
    ]
    return max(along)


def _room(cfg) -> float:
    """How far from the band's middle a hand may finish: reach disc AND box."""

    axis = material_axis(cfg)
    across = float(band_centre_task(cfg)[1 - axis])
    chord = _reach_half_width(cfg, across)
    if chord < 0.0:
        raise ValueError(
            f"cloth_unpleat: the band's across position {across:+.4f} lies outside the reach disc."
        )
    box = cfg["workspace"]["x" if axis == 0 else "y"]
    return float(min(chord, 0.5 * (float(box[1]) - float(box[0])) - WORKSPACE_MARGIN))


def _room_needed(cfg, length: float) -> float:
    """How much `_room` a band of material length ``length`` would ask for.

    NOT ``length / 2``. The hand does not stop where the flat band ends: the
    closed loop is allowed to keep pulling to ``stored x pull_extend_max_scale``,
    so it finishes ``0.15 x stored`` PAST the flat position on the pull that
    carries the most material, measured from the band's spawn middle:

        half of the spawn span  -  edge_inset  +  the furthest pull

    less however far toward the anchor the band can be shifted to make room --
    the along window allows CENTER_ALONG_SHIFT, but the anchored end has to stay
    inside the box, and a long band runs out of box before it runs out of window.
    """

    stored = sum(stored_per_pleat(cfg))
    half_span = 0.5 * (float(length) - stored)
    axis = material_axis(cfg)
    box = cfg["workspace"]["x" if axis == 0 else "y"]
    box_room = -(float(box[0]) + WORKSPACE_MARGIN)
    shift = min(CENTER_ALONG_SHIFT, box_room - half_span)
    return float(half_span - _inset_floor(cfg) + _pull_overshoot(cfg) - max(shift, 0.0))


def band_length_ceiling(cfg) -> float:
    """Longest band this set of pleats may sit on. Three separate limits.

    **Reach and the box, for the pulled end** -- `_room_needed` solved for the
    length, with the band shifted toward the anchor as far as the along window
    allows. **The box, for the anchored end**, which has to spawn inside it
    after that shift. And **the start-state design ceiling**:
    `grasp.max_start_spread_ratio` says the band may not spawn more than that
    fraction of its material already spread out -- the pleats have to still
    hold something worth pulling. Since the spawn span is ``L - stored``, that
    reads ``L <= stored / (1 - ratio)``: at the shipped 0.80 the band may be at
    most five times the material its pleats hold. This last one is a task
    design choice, not a physical limit; the settle guard that used to share the
    number is relative now (`grasp.max_start_spread_drift`).
    """

    stored = sum(stored_per_pleat(cfg))
    axis = material_axis(cfg)
    box = cfg["workspace"]["x" if axis == 0 else "y"]
    lo_box = float(box[0]) + WORKSPACE_MARGIN
    overshoot, inset = _pull_overshoot(cfg), _inset_floor(cfg)
    by_reach = 2.0 * (_room(cfg) + CENTER_ALONG_SHIFT + inset - overshoot) + stored
    by_anchor = 2.0 * (CENTER_ALONG_SHIFT - lo_box) + stored
    by_box = (_room(cfg) - lo_box) + inset - overshoot + stored
    ratio = float(cfg["grasp"]["max_start_spread_ratio"])
    by_guard = stored / max(1.0 - ratio, 1e-9)
    return float(min(by_reach, by_anchor, by_box, by_guard, float(_cloth(cfg).get("material_length_max", float("inf")))))


def band_budget(cfg) -> float:
    """Slack, in metres, between the shortest band that fits and the longest allowed.

    The gap and the two end runs are drawn out of this one number, in the order
    `cloth_unpleat.derive_task_cfg` runs them.
    """

    return float(band_length_ceiling(cfg) - band_length_floor(cfg))


# ---------------------------------------------------------------- derivations


def center_across_bounds(cfg) -> tuple[float, float]:
    """``[lo, hi]`` for the band's centre on the axis it does NOT run along.

    Drawn AFTER the pleats, because how far out the band may sit depends on how
    much material they hold: the reach disc's chord shrinks as the band moves
    away from the base's own line, and the shortest band that fits this set of
    pleats still needs `_room_needed` of it. Solving that for the chord gives
    the cap.
    """

    axis = material_axis(cfg)
    cloth = _cloth(cfg)
    base = np.asarray([float(v) for v in cfg["reach"]["base_xy"]], dtype=float)
    radius = float(cfg["reach"]["max_hand_dist"])
    box = cfg["workspace"]["x" if axis == 0 else "y"]
    box_room = 0.5 * (float(box[1]) - float(box[0])) - WORKSPACE_MARGIN

    needed = _room_needed(cfg, band_length_floor(cfg))
    if needed > box_room or needed >= radius:
        raise ValueError(
            f"cloth_unpleat: these pleats need {needed:.4f} m of room from the band's "
            f"middle; the workspace allows {box_room:.4f} m and the reach radius is {radius:.4f} m."
        )
    half = math.sqrt(radius * radius - needed * needed)
    lo = float(cloth["center_across_min"])
    hi = min(float(cloth["center_across_max"]), float(base[1 - axis] + half))
    if hi < lo - 1e-12:
        raise ValueError(
            f"cloth_unpleat: no across position leaves room for these pleats: "
            f"window [{lo:+.4f}, {hi:+.4f}] (needs {needed:.4f} m)."
        )
    return float(lo), float(hi)


def center_across_from_frac(cfg, frac: float) -> float:
    lo, hi = center_across_bounds(cfg)
    return float(lo + float(np.clip(frac, 0.0, 1.0)) * (hi - lo))


def across_leaf(cfg) -> str:
    """Name of the `cloth.center_*` leaf that runs across the band."""

    return "center_y" if material_axis(cfg) == 0 else "center_x"


def second_crest_bounds(cfg) -> tuple[float, float]:
    pleat = _cloth(cfg)["pleat"]["b"]
    return float(pleat["crest_min"]), float(pleat["crest_max"])


def second_crest_from_frac(cfg, frac: float) -> float:
    lo, hi = second_crest_bounds(cfg)
    return float(lo + float(np.clip(frac, 0.0, 1.0)) * (hi - lo))


def second_width_bounds(cfg) -> tuple[float, float]:
    pleat = _cloth(cfg)["pleat"]["b"]
    return float(pleat["width_min"]), float(pleat["width_max"])


def second_width_from_frac(cfg, frac: float) -> float:
    lo, hi = second_width_bounds(cfg)
    return float(lo + float(np.clip(frac, 0.0, 1.0)) * (hi - lo))


def _budget_left(cfg, *, drawn: tuple = ()) -> float:
    """Band length still unspent over every run's floor.

    ``drawn`` names the runs already fixed by this draw, and it is NOT inferred
    from the leaves: every run has a value in the yaml at all times, so reading
    them back would charge the default lead and tail against the budget before
    either has been drawn. `derive_task_cfg` fixes them in the order gap, lead,
    tail, and passes that here.
    """

    cloth, floors = _cloth(cfg), run_floors(cfg)
    left = band_budget(cfg)
    if "gap" in drawn and pleat_count(cfg) > 1:
        left -= float(cloth["pleat"]["gap"]) - floors[1]
    if "lead" in drawn:
        left -= float(cloth["lead"]) - floors[0]
    if "tail" in drawn:
        left -= float(cloth["tail"]) - floors[-1]
    return float(left)


def _run_bounds(cfg, name: str, index: int, drawn: tuple) -> tuple[float, float]:
    lo = run_floors(cfg)[index]
    left = _budget_left(cfg, drawn=drawn)
    if left < -1e-9:
        raise ValueError(f"cloth_unpleat: no band length left for the {name} ({left:+.4f} m).")
    return float(lo), float(lo + max(left, 0.0))


def gap_bounds(cfg) -> tuple[float, float]:
    if pleat_count(cfg) < 2:
        raise ValueError("cloth_unpleat: a single pleat has no gap to derive.")
    return _run_bounds(cfg, "gap", 1, ())


def gap_from_frac(cfg, frac: float) -> float:
    lo, hi = gap_bounds(cfg)
    return float(lo + float(np.clip(frac, 0.0, 1.0)) * (hi - lo))


def lead_bounds(cfg) -> tuple[float, float]:
    return _run_bounds(cfg, "lead-in", 0, ("gap",))


def lead_from_frac(cfg, frac: float) -> float:
    lo, hi = lead_bounds(cfg)
    return float(lo + float(np.clip(frac, 0.0, 1.0)) * (hi - lo))


def tail_bounds(cfg) -> tuple[float, float]:
    return _run_bounds(cfg, "tail", -1, ("gap", "lead"))


def tail_from_frac(cfg, frac: float) -> float:
    lo, hi = tail_bounds(cfg)
    return float(lo + float(np.clip(frac, 0.0, 1.0)) * (hi - lo))






def band_length(cfg) -> float:
    """The band's material length, once the runs and the pleats are settled."""

    sizes = pleat_sizes(cfg)
    return float(sum(band_runs(cfg)) + sum(w for w, _ in sizes) + sum(stored_per_pleat(cfg)))


def edge_inset_bounds(cfg) -> tuple[float, float]:
    """``[lo, hi]`` for `grasp.edge_inset` at the grasped (tail) end.

    Floor: two particle sizes (never below `EDGE_INSET_MIN`). Ceiling: the
    yaml's `EDGE_INSET_MAX`, or less when the tail is short -- the attachment
    disc has to stay ``2 x attach_radius`` clear of the nearest three-layer
    strip. Raises when the window is empty (the draw is rejected).
    """

    tail = pleat_marks(cfg)["bare_runs"][1]
    lo = max(EDGE_INSET_MIN, 2.0 * float(_cloth(cfg)["particle_size"]))
    hi = min(EDGE_INSET_MAX, tail - 2.0 * float(cfg["grasp"]["attach_radius"]))
    if hi < lo - 1e-12:
        raise ValueError(
            f"cloth_unpleat: no edge_inset keeps the attachment disc off the pleat: "
            f"window [{lo:.4f}, {hi:.4f}] (tail {tail:.4f})."
        )
    return float(lo), float(hi)


def edge_inset_from_frac(cfg, frac: float) -> float:
    lo, hi = edge_inset_bounds(cfg)
    return float(lo + float(np.clip(frac, 0.0, 1.0)) * (hi - lo))


# ----------------------------------------------------------------- the pulls


def pulls(cfg) -> list[dict]:
    """One entry per pull: which pleat it opens and how far the end has already gone.

    **Every pull takes the tail end** -- ``+1`` in material order, the one the
    pleats' upper layers run into (2026-09-10). One pleat is one such pull. Two
    pleats are two consecutive strokes within one continuous grasp, the nearer
    pleat first, then the farther one; the lead-in end is the anchor throughout.

    ``offset`` is the material the earlier pulls have already paid out, i.e. how
    far along the band the end has moved when this pull begins. ``end`` is +-1
    along the material axis BEFORE `band_sign` is applied and is always +1.
    """

    stored = stored_per_pleat(cfg)
    if pleat_layout(cfg) == "parallel":
        return [
            {"axis": "along", "end": +1.0, "pleat": 1, "stored": stored[1], "offset": 0.0},
            {"axis": "along", "end": +1.0, "pleat": 0, "stored": stored[0], "offset": stored[1]},
        ]
    return [{"axis": "along", "end": +1.0, "pleat": 0, "stored": stored[0], "offset": 0.0}]


def pull_direction(cfg, index: int = 0) -> np.ndarray:
    """Task-frame (x, y) unit vector pull ``index`` runs along: the band's own axis.

    Every crease is square across the band, so the fold comes open by moving the
    end straight along the band. (The 2026-09-08 slanted crease needed a
    different answer and did not have one -- see the module docstring.)
    """

    axis = material_axis(cfg)
    pull = pulls(cfg)[int(index)]
    direction = np.zeros(2, dtype=float)
    direction[axis] = band_sign(cfg) * float(pull["end"])
    return direction


def pull_distance(cfg, index: int = 0) -> float:
    """The PLANNED distance of one pull: its pleat's stored material x `pull_scale`."""

    return float(pulls(cfg)[index]["stored"]) * float(cfg["physical"]["pull_scale"])


def pull_distance_max(cfg, index: int = 0) -> float:
    """The farthest one pull may go: its stored material x `pull_extend_max_scale`.

    The oracle pulls `pull_distance` first, then extends while the band's spread
    is short of its target, never beyond this cap (planner `PullExtender`). Every
    row about where the hand ends up uses this bound, not the planned distance.
    """

    scale = max(float(cfg["physical"]["pull_scale"]), float(cfg["physical"]["pull_extend_max_scale"]))
    return float(pulls(cfg)[index]["stored"]) * scale


def grasp_point_task(cfg, index: int = 0) -> np.ndarray:
    """Task-frame (x, y) of pull ``index``'s design grasp.

    The tail end, `edge_inset` in from the edge, carried along the band by the
    material every earlier pull released. The demo re-observes the real end
    before each pull; this is what the checks plan on.
    """

    inset = float(cfg["grasp"]["edge_inset"])
    point = band_centre_task(cfg).copy()
    marks = pleat_marks(cfg)
    point += pull_direction(cfg, 0) * (marks["half_span"] - inset)
    for earlier in range(int(index)):
        point += pull_direction(cfg, earlier) * float(pulls(cfg)[earlier]["stored"])
    return point


def pull_end_task(cfg, index: int = 0) -> np.ndarray:
    """Task-frame (x, y) of the farthest point pull ``index`` may take its material to."""

    point = grasp_point_task(cfg, 0).copy()
    for earlier in range(index + 1):
        point += pull_direction(cfg, earlier) * pull_distance_max(cfg, earlier)
    return point


def all_pull_ends_task(cfg) -> np.ndarray:
    return np.asarray([pull_end_task(cfg, i) for i in range(len(pulls(cfg)))], dtype=float)


def pull_room(cfg, point_xy, index: int = 0, *, direction=None) -> float:
    """Remaining straight travel from an observed task-frame point, metres.

    Intersect the pull ray with both the workspace's safety inset and the
    configured horizontal reach disc. A point already outside has no room.
    """
    point = np.asarray(point_xy, dtype=float)
    direction = pull_direction(cfg, index) if direction is None else np.asarray(direction, dtype=float)
    base = np.asarray(cfg["reach"]["base_xy"], dtype=float)
    radius = float(cfg["reach"]["max_hand_dist"])
    delta = point - base
    if workspace_margin(cfg, [point]) < WORKSPACE_MARGIN - 1e-9 or np.linalg.norm(delta) > radius + 1e-9:
        return 0.0
    projection = float(delta @ direction)
    room = -projection + math.sqrt(max(0.0, projection**2 + radius**2 - float(delta @ delta)))
    for axis, key in enumerate(("x", "y")):
        if abs(direction[axis]) < 1e-12:
            continue
        edge = float(cfg["workspace"][key][1 if direction[axis] > 0 else 0])
        edge -= math.copysign(WORKSPACE_MARGIN, direction[axis])
        room = min(room, (edge - point[axis]) / direction[axis])
    return max(0.0, float(room))


def band_footprint_task(cfg) -> np.ndarray:
    """Task-frame (x, y) of the spawn band's four plan corners."""

    axis = material_axis(cfg)
    marks = pleat_marks(cfg)
    centre = band_centre_task(cfg)
    half_w = 0.5 * float(_cloth(cfg)["width"])
    out = []
    for s_along in (-1.0, 1.0):
        for s_across in (-1.0, 1.0):
            point = centre.copy()
            point[axis] += s_along * marks["half_span"]
            point[1 - axis] += s_across * half_w
            out.append(point)
    return np.asarray(out, dtype=float)


# ------------------------------------------------------- along-axis position


def _reach_half_width(cfg, across: float) -> float:
    """Half-width of the reach disc's chord at the band's across-axis position.

    The disc is centred on `reach.base_xy` with radius `reach.max_hand_dist`;
    ``across`` is the band's coordinate on the axis the band does NOT run along.
    Returns a negative number when the chord does not exist (band too far out).
    """

    axis = material_axis(cfg)
    base = np.asarray([float(v) for v in cfg["reach"]["base_xy"]], dtype=float)
    radius = float(cfg["reach"]["max_hand_dist"])
    gap = across - base[1 - axis]
    inside = radius * radius - gap * gap
    return math.sqrt(inside) if inside > 0.0 else -1.0


def center_along_bounds(cfg) -> tuple[float, float]:
    """``[lo, hi]`` for the band's centre coordinate ALONG its own axis.

    Starts from ``CENTER_ALONG_BASE +- CENTER_ALONG_SHIFT`` and caps it: every
    pull's end point must stay inside the reach disc (`reach:`) and inside the
    workspace box by `WORKSPACE_MARGIN`, and so must the spawn footprint. Every
    pull takes the same end, so the window is one-sided -- the band sits toward
    the anchored end to make room. Raises when it is empty (the draw is rejected).
    """

    axis = material_axis(cfg)
    marks = pleat_marks(cfg)
    across = float(band_centre_task(cfg)[1 - axis])
    base = np.asarray([float(v) for v in cfg["reach"]["base_xy"]], dtype=float)
    box = cfg["workspace"]["x" if axis == 0 else "y"]
    lo_box, hi_box = float(box[0]) + WORKSPACE_MARGIN, float(box[1]) - WORKSPACE_MARGIN
    chord = _reach_half_width(cfg, across)
    if chord < 0.0:
        raise ValueError(
            f"cloth_unpleat: the band's across position {across:+.4f} lies outside the reach disc."
        )

    lo, hi = CENTER_ALONG_BASE - CENTER_ALONG_SHIFT, CENTER_ALONG_BASE + CENTER_ALONG_SHIFT
    sign = band_sign(cfg)
    for index, pull in enumerate(pulls(cfg)):
        # Offset of this pull's end point from the band's middle, signed.
        off = sign * float(pull["end"]) * (
            marks["half_span"] - float(cfg["grasp"]["edge_inset"])
            + sum(pull_distance_max(cfg, i) for i in range(index + 1))
        )
        lo = max(lo, base[axis] - chord - off, lo_box - off)
        hi = min(hi, base[axis] + chord - off, hi_box - off)
    lo = max(lo, lo_box + marks["half_span"])
    hi = min(hi, hi_box - marks["half_span"])
    if hi < lo - 1e-12:
        raise ValueError(
            f"cloth_unpleat: no centre position keeps every pull inside reach and workspace: "
            f"window [{lo:+.4f}, {hi:+.4f}] (half span {marks['half_span']:.4f}, reach chord {chord:.4f})."
        )
    # Plain floats: the derived value is written back into an OmegaConf leaf,
    # which refuses numpy scalars.
    return float(lo), float(hi)


def center_along_from_frac(cfg, frac: float) -> float:
    lo, hi = center_along_bounds(cfg)
    return float(lo + float(np.clip(frac, 0.0, 1.0)) * (hi - lo))


def along_leaf(cfg) -> str:
    """Name of the `cloth.center_*` leaf that runs along the band."""

    return "center_x" if material_axis(cfg) == 0 else "center_y"


def workspace_margin(cfg, points_xy) -> float:
    """Smallest distance from any of ``points_xy`` (task frame) to the box's edges."""

    pts = np.asarray(points_xy, dtype=float).reshape(-1, 2)
    ws = cfg["workspace"]
    wx = (float(ws["x"][0]), float(ws["x"][1]))
    wy = (float(ws["y"][0]), float(ws["y"][1]))
    return float(
        min(
            (pts[:, 0] - wx[0]).min(),
            (wx[1] - pts[:, 0]).min(),
            (pts[:, 1] - wy[0]).min(),
            (wy[1] - pts[:, 1]).min(),
        )
    )


# --------------------------------------------------------------------- checks


def cloth_unpleat_checks(cfg) -> list[tuple[str, float, float, bool]]:
    """``[(name, measured, limit, ok)]`` for a spawnable, solvable layout.

    One list for the randomizer's reject step, the offline gate, the corner
    harness and the demo's start-up print. Metres throughout.
    """

    cloth = _cloth(cfg)
    marks = pleat_marks(cfg)
    sizes = pleat_sizes(cfg)
    inset = float(cfg["grasp"]["edge_inset"])
    particle = float(cloth["particle_size"])
    attach = float(cfg["grasp"]["attach_radius"])
    spacings = MIN_TAIL_SPACINGS * float(cloth["mesh"]["spacing"])

    base = np.asarray([float(v) for v in cfg["reach"]["base_xy"]], dtype=float)
    reaches = [float(np.linalg.norm(pull_end_task(cfg, i) - base)) for i in range(len(pulls(cfg)))]
    strokes = [pull_distance_max(cfg, i) for i in range(len(pulls(cfg)))]
    span_points = np.vstack([band_footprint_task(cfg), all_pull_ends_task(cfg)])

    ge = [
        ("pleat_fits_band", min(marks["bare_runs"]), spacings),
        ("crest_above_underlayer", min(h for _, h in sizes), particle),
        ("grasp_clears_three_layers", marks["bare_runs"][1] - inset, 2.0 * attach),
        ("band_in_workspace", workspace_margin(cfg, span_points), WORKSPACE_MARGIN),
    ]
    rows = [(name, value, limit, value >= limit - 1e-9) for name, value, limit in ge]
    max_reach = float(cfg["reach"]["max_hand_dist"])
    rows.append(("hand_reach", max(reaches), max_reach, max(reaches) <= max_reach + 1e-9))
    rows.append(("pull_within_stroke", max(strokes), PULL_MAX, max(strokes) <= PULL_MAX + 1e-9))
    spread = float(marks["plan_span"]) / float(cloth["material_length"])
    max_spread = float(cfg["grasp"]["max_start_spread_ratio"])
    rows.append(("start_still_stored", spread, max_spread, spread <= max_spread + 1e-9))
    return rows


__all__ = [
    "CENTER_ALONG_BASE",
    "CENTER_ALONG_SHIFT",
    "EDGE_INSET_MAX",
    "EDGE_INSET_MIN",
    "LAYOUTS",
    "MIN_GAP_PARTICLES",
    "MIN_TAIL_SPACINGS",
    "PULL_MAX",
    "WORKSPACE_MARGIN",
    "across_leaf",
    "all_pull_ends_task",
    "along_leaf",
    "band_budget",
    "band_centre_task",
    "band_footprint_task",
    "band_length",
    "band_length_ceiling",
    "band_length_floor",
    "band_profile",
    "band_runs",
    "band_sign",
    "center_across_bounds",
    "center_across_from_frac",
    "center_along_bounds",
    "center_along_from_frac",
    "cloth_unpleat_checks",
    "edge_inset_bounds",
    "edge_inset_from_frac",
    "gap_bounds",
    "gap_floor",
    "gap_from_frac",
    "grasp_clearance",
    "grasp_point_task",
    "lead_bounds",
    "lead_floor",
    "lead_from_frac",
    "material_axis",
    "pleat_count",
    "pleat_layout",
    "pleat_marks",
    "pleat_sizes",
    "pull_direction",
    "pull_distance",
    "pull_distance_max",
    "pull_end_task",
    "pull_room",
    "pulls",
    "run_floors",
    "second_crest_bounds",
    "second_crest_from_frac",
    "second_width_bounds",
    "second_width_from_frac",
    "stored_per_pleat",
    "tail_bounds",
    "tail_floor",
    "tail_from_frac",
    "workspace_margin",
]
