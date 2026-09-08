"""cloth_unroll's layout rules and feasibility checks, numpy only.

Kept apart from `cloth_unroll.py` so the offline gate
(`tests/check_cloth_unroll_geometry.py`) and the variation harness can load
them without Genesis: `cloth_unroll.py` imports Genesis at module level.
Everything here takes the TASK config alone (a dict or an OmegaConf node under
``cfg.task``) and works in the task frame, metres, table at z = 0: the
workspace box and the arm base are task-frame quantities, so no world origin
is needed for any row.

The scene, for the reader who has only this file: a small dispenser stands on
the table -- two posts at ``x = center_x +- span / 2``, ``y = center_y``, and a
thin bar between them at `dispenser.bar_height`, running along x. A 28 cm x
12 cm cloth band is wound `roll.turns` times round the bar with `roll.pitch`
between the layers, leaves the roll tangentially on its +y side, hangs down to
the table and lies flat along +y (the flat run). The gripper takes the free end
`grasp.edge_inset` in from the edge and drags it straight along the table by
``flat_travel x pull_scale``; the bar pays the roll out and the band ends up
flat. `cloth.pull_side: -1` is the mirror layout: the same scene reflected in
the y = 0 plane, the band leaving the roll on its -y side and pulled toward -y.

Since 2026-09-06 the bar is a spool (`cloth.spool`): the wound band is bound
to it, the spool turns as the hand pays the band out so the peel point stays
at the exit tangent, and the inner `anchor_arc` of band stays glued to it.
Pulled just enough, the band runs from that glued tail down to the table and
lies flat to the free end; pulled past taut by more than `tear_allowance`,
the glue lets go (the environment releases the tail) and the episode fails.

Two facts shape the envelope (computed offline, 2026-09-05):

- The flat run is what the spiral leaves over -- material length minus the
  spiral's arc minus the drape. More turns or a wider pitch eat it, and the
  grasp on it has to keep `SHOVE_BAR_CLEARANCE` from the bar's axis, so the
  pitch window depends on the drawn turns and bar height (`pitch_bounds`). At
  0.280 m of material, 1.75 turns leaves no flat run at any pitch.
- Where the pull ENDS does not depend on the roll at all
  (`ClothUnrollLayout.final_grasp_position`): only the dispenser's position,
  the material length and the grasp inset move it. So reach caps the band's
  along-axis position, never the turns (`center_along_bounds`).
"""

from __future__ import annotations

import math

import numpy as np

from topogym.planning.cloth_unroll_planner import SHOVE_BAR_CLEARANCE

from .cloth_profile_mesh import spiral_landmarks, spiral_profile

# ------------------------------------------------------------- envelope rules
#: `roll.pitch` window before the flat-run rows cap it. The floor is the render
#: binding map's rule (3.8 x the measured 3.7 mm particle spacing, task yaml);
#: the ceiling is the plan's "increase only" envelope.
PITCH_MIN = 0.014
PITCH_MAX = 0.018
#: The flat run keeps at least this many control mesh spacings (the same bar
#: `spiral_profile` raises on).
MIN_FLAT_SPACINGS = 4
#: How far the dispenser may slide along the band's axis from the yaml's
#: baseline, before the reach and workspace rows cap the far side.
CENTER_ALONG_BASE = -0.100
CENTER_ALONG_SHIFT = 0.030
#: Smallest distance any point of the spawn footprint or the pull end may come
#: to the workspace box's x / y edges (same value as cloth_unpleat).
WORKSPACE_MARGIN = 0.040
#: How much the settled roll may spread beyond its designed plan span before
#: the demo's start-state guard calls it released. The baseline roll settles
#: from a designed 0.392 to 0.457 (2026-08-25); 0.11 keeps the baseline guard
#: at the 0.50 the yaml carried, and a one-turn roll (designed 0.60-0.66) gets
#: the same slack instead of being refused at spawn.
START_SPREAD_SLACK = 0.11


def material_axis(cfg) -> int:
    """0 when the band's length runs along task x, 1 along task y."""

    axis = str(cfg["cloth"]["material_axis"]).lower()
    if axis not in ("x", "y"):
        raise ValueError(f"cloth.material_axis must be 'x' or 'y', got {axis!r}.")
    return 0 if axis == "x" else 1


def pull_sign(cfg) -> float:
    """+1 when the band leaves the roll toward the positive end of its axis, -1 mirrored.

    `cloth.pull_side: -1` IS the mirror layout: the profile is reflected in the
    band's own axis, the flat run lies at the negative side of the bar and the
    pull runs toward negative coordinates. The arm base sits on y = 0 and the
    workspace box is symmetric about it, so with the band along y every row
    below reads the same for both signs.
    """

    cloth = cfg["cloth"]
    side = cloth.get("pull_side", 1) if hasattr(cloth, "get") else 1
    return -1.0 if int(side) < 0 else 1.0


def bar_centre_task(cfg) -> np.ndarray:
    """Task-frame (x, y) of the bar's axis."""

    cloth = cfg["cloth"]
    return np.array([float(cloth["center_x"]), float(cloth["center_y"])], dtype=float)


def _profile_at(cfg, pitch: float) -> np.ndarray:
    """The unmirrored spiral profile with the layer pitch replaced by ``pitch``."""

    cloth, dispenser = cfg["cloth"], cfg["dispenser"]
    return spiral_profile(
        material_length=float(cloth["material_length"]),
        bar_radius=float(dispenser["bar_radius"]),
        clearance=float(cloth["roll"]["clearance"]),
        pitch=float(pitch),
        turns=float(cloth["roll"]["turns"]),
        bar_height=float(dispenser["bar_height"]),
        rest_z=float(cloth["z"]),
        spacing=float(cloth["mesh"]["spacing"]),
    )


def profile(cfg) -> np.ndarray:
    """The band's (material offset, height) profile, unmirrored, as the mesh builds it."""

    return _profile_at(cfg, float(cfg["cloth"]["roll"]["pitch"]))


def _marks_at(cfg, pitch: float) -> dict:
    prof = _profile_at(cfg, pitch)
    marks = spiral_landmarks(
        prof, bar_height=float(cfg["dispenser"]["bar_height"]), rest_z=float(cfg["cloth"]["z"])
    )
    # Unsigned distance from the bar's axis to the spawn's far edge (the back
    # of the roll), for the footprint rows.
    marks["back_s"] = -float(prof[:, 0].min())
    return marks


def roll_marks(cfg) -> dict:
    """`spiral_landmarks` of the unmirrored profile plus ``back_s``.

    Offsets are lengths along the band's axis measured from the bar; the sign
    is not applied here.
    """

    return _marks_at(cfg, float(cfg["cloth"]["roll"]["pitch"]))


# ---------------------------------------------------------------- derivations


def _roll_rows(cfg, pitch: float) -> list[tuple[str, float, float]]:
    """The five ``(name, measured, limit)`` rows the drawn pitch can push over.

    All of them fall as the pitch grows (a wider pitch fattens the roll and
    eats the flat run), which is what lets `pitch_bounds` bisect on them.
    Raises `ValueError` from `spiral_profile` when the flat run is gone.
    """

    cloth, dispenser, grasp = cfg["cloth"], cfg["dispenser"], cfg["grasp"]
    marks = _marks_at(cfg, pitch)
    inset = float(grasp["edge_inset"])
    grasp_s = float(marks["free_end_s"]) - inset
    return [
        ("flat_run_fits_grasp", float(marks["flat_run"]), MIN_FLAT_SPACINGS * float(cloth["mesh"]["spacing"])),
        # The attachment disc is a circle in plan; the nearest material that is
        # not flat is the drape, which in plan sits at the roll's edge `exit_s`.
        ("grasp_clears_drape", grasp_s - float(marks["exit_s"]), float(grasp["attach_radius"]) + 2.0 * float(cloth["particle_size"])),
        # Measured 2026-08-25: the hand stops dead this far from the bar's axis.
        ("grasp_clears_dispenser", grasp_s, SHOVE_BAR_CLEARANCE),
        ("roll_clears_table", float(dispenser["bar_height"]) - float(marks["roll_radius"]) - float(cloth["z"]), float(cloth["particle_size"])),
        ("posts_above_roll", float(dispenser["post_height"]) - (float(dispenser["bar_height"]) + float(marks["roll_radius"])), 0.0),
    ]


def _roll_fits(cfg, pitch: float) -> bool:
    try:
        rows = _roll_rows(cfg, pitch)
    except ValueError:
        return False
    return all(value >= limit - 1e-9 for _, value, limit in rows)


def pitch_bounds(cfg) -> tuple[float, float]:
    """``[lo, hi]`` for `roll.pitch` under the drawn turns and bar height.

    Floor `PITCH_MIN`; ceiling `PITCH_MAX`, or less when the roll would eat the
    flat run: the largest pitch that keeps all five `_roll_rows` passing, found
    by bisection (every row falls with the pitch). Raises when even the floor
    fails (the draw is rejected).
    """

    if not _roll_fits(cfg, PITCH_MIN):
        raise ValueError(
            f"cloth_unroll: {float(cfg['cloth']['roll']['turns'])} turns at bar height "
            f"{float(cfg['dispenser']['bar_height']):.3f} leaves no flat run even at pitch {PITCH_MIN}."
        )
    if _roll_fits(cfg, PITCH_MAX):
        return PITCH_MIN, PITCH_MAX
    good, bad = PITCH_MIN, PITCH_MAX
    while bad - good > 1e-6:
        mid = 0.5 * (good + bad)
        if _roll_fits(cfg, mid):
            good = mid
        else:
            bad = mid
    return PITCH_MIN, float(good)


def pitch_from_frac(cfg, frac: float) -> float:
    lo, hi = pitch_bounds(cfg)
    return float(lo + float(np.clip(frac, 0.0, 1.0)) * (hi - lo))


def spool_cfg(cfg) -> dict:
    """The `cloth.spool` block as floats: lead, anchor_arc, tear_allowance, pull_slack."""

    block = cfg["cloth"]["spool"]
    return {k: float(block[k]) for k in ("lead", "anchor_arc", "tear_allowance", "pull_slack")}


def tail_radius(cfg) -> float:
    """Distance from the bar's axis of the glued tail's outer end (arc `anchor_arc`)."""

    prof = profile(cfg)
    arcs = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(prof, axis=0), axis=1))])
    a = spool_cfg(cfg)["anchor_arc"]
    m = float(np.interp(a, arcs, prof[:, 0]))
    z = float(np.interp(a, arcs, prof[:, 1]))
    return float(math.hypot(m, z - float(cfg["dispenser"]["bar_height"])))


def hang_height(cfg) -> float:
    """Height of the glued tail's end above the band's rest height on the table."""

    return float(cfg["dispenser"]["bar_height"]) - float(cfg["cloth"]["z"])


def taut_length(cfg) -> float:
    """Band between the glued tail's end and the grasp point: material minus the glued arc and the inset."""

    return float(cfg["cloth"]["material_length"]) - spool_cfg(cfg)["anchor_arc"] - float(cfg["grasp"]["edge_inset"])


def taut_reach(cfg, slack: float) -> float:
    """Along-axis distance from the tail's end to the grasp point when the band has ``slack`` to spare.

    The tail's end sits `hang_height` above the table; a straight band of
    length ``L - slack`` from there reaches ``sqrt((L - slack)^2 - h^2)`` along
    the table. Raises when the band cannot reach the table at all.
    """

    length = taut_length(cfg) - float(slack)
    h = hang_height(cfg)
    if length <= h:
        raise ValueError(f"cloth_unroll: band of {length:.3f} m cannot reach the table from {h:.3f} m up.")
    return float(math.sqrt(length * length - h * h))


def relaxed_front_offset(cfg) -> float:
    """Along-axis distance from the bar's axis to the band's FREE end once let go after a full pull.

    Released, the band hangs straight down from the glued tail's end (it is
    only a diagonal while the hand holds it taut) and lies flat from the foot:
    ``tail_radius + (taut_length - hang_height) + edge_inset``. The judge's
    `over_pull` is measured from here, and it is the far end of `span_max`.
    """

    return tail_radius(cfg) + taut_length(cfg) - hang_height(cfg) + float(cfg["grasp"]["edge_inset"])


def glued_back_offset(cfg) -> float:
    """How far BEHIND the bar's axis (against the pull) the glued tail reaches once the roll is paid out.

    The inner `anchor_arc` of the profile turned so its outer end sits at the
    exit direction; the rear-most of those points, measured against the pull.
    """

    prof = profile(cfg)
    bar_h = float(cfg["dispenser"]["bar_height"])
    arcs, angles = spiral_angles(prof, bar_h)
    anchor = spool_cfg(cfg)["anchor_arc"]
    theta = -float(np.interp(anchor, arcs, angles))
    keep = prof[: int(np.searchsorted(arcs, anchor)) + 1]
    m, z = keep[:, 0], keep[:, 1] - bar_h
    turned_m = np.cos(theta) * m - np.sin(theta) * z
    return float(max(0.0, -turned_m.min()))


def span_max(cfg) -> float:
    """The band's largest possible extent along the pull with the tail glued: glued back to relaxed free end."""

    return glued_back_offset(cfg) + relaxed_front_offset(cfg)


def _end_offset(cfg) -> float:
    """Unsigned distance from the bar's axis to the pull's END point (the grasp, after the oracle's pull)."""

    return tail_radius(cfg) + taut_reach(cfg, spool_cfg(cfg)["pull_slack"])


def pull_distance(cfg) -> float:
    """How far the grasp travels: from the design grasp to the taut end minus `pull_slack`."""

    marks = roll_marks(cfg)
    return _end_offset(cfg) - (float(marks["free_end_s"]) - float(cfg["grasp"]["edge_inset"]))


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
    """``[lo, hi]`` for the bar's centre coordinate ALONG the band's axis.

    Starts from ``CENTER_ALONG_BASE +- CENTER_ALONG_SHIFT`` and caps the side
    the pull runs toward twice: the pull's end point must stay inside the reach
    disc (`reach:`), and inside the workspace box by `WORKSPACE_MARGIN`; the
    other side is capped by the roll's back staying inside the box. Written for
    the +1 orientation and mirrored for `pull_side` -1. Raises when the window
    is empty (the draw is rejected).
    """

    axis = material_axis(cfg)
    sign = pull_sign(cfg)
    marks = roll_marks(cfg)
    centre = bar_centre_task(cfg)
    across = float(centre[1 - axis])
    base = np.asarray([float(v) for v in cfg["reach"]["base_xy"]], dtype=float)
    box = cfg["workspace"]["x" if axis == 0 else "y"]
    lo_box, hi_box = float(box[0]) + WORKSPACE_MARGIN, float(box[1]) - WORKSPACE_MARGIN

    off = _end_offset(cfg)
    chord = _reach_half_width(cfg, across)
    if chord < 0.0:
        raise ValueError(
            f"cloth_unroll: the bar's across position {across:+.4f} lies outside the reach disc."
        )
    hi_reach = base[axis] + chord - off
    hi_ws = hi_box - off
    lo_ws = lo_box + float(marks["back_s"])
    lo_plus = max(CENTER_ALONG_BASE - CENTER_ALONG_SHIFT, lo_ws)
    hi_plus = min(CENTER_ALONG_BASE + CENTER_ALONG_SHIFT, hi_reach, hi_ws)
    if sign > 0:
        lo, hi = lo_plus, hi_plus
    else:
        lo, hi = -hi_plus, -lo_plus
    if hi < lo - 1e-12:
        raise ValueError(
            f"cloth_unroll: no bar position keeps the pull inside reach and workspace: "
            f"window [{lo:+.4f}, {hi:+.4f}] (pull end offset {off:.4f}, reach chord {chord:.4f})."
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


def design_spread_ratio(cfg) -> float:
    """Plan span over material length of the band as built (before settling)."""

    marks = roll_marks(cfg)
    return float(marks["plan_span"]) / float(cfg["cloth"]["material_length"])


def start_spread_limit(cfg) -> float:
    """`grasp.max_start_spread_ratio` for this roll: its designed spread plus the slack."""

    return float(design_spread_ratio(cfg) + START_SPREAD_SLACK)


# --------------------------------------------------------------------- points


def grasp_point_task(cfg) -> np.ndarray:
    """Task-frame (x, y) of the design grasp: the free end, `edge_inset` in."""

    axis = material_axis(cfg)
    point = bar_centre_task(cfg).copy()
    point[axis] += pull_sign(cfg) * (float(roll_marks(cfg)["free_end_s"]) - float(cfg["grasp"]["edge_inset"]))
    return point


def pull_end_task(cfg) -> np.ndarray:
    """Task-frame (x, y) where the grasped material ends up after the pull."""

    axis = material_axis(cfg)
    point = bar_centre_task(cfg).copy()
    point[axis] += pull_sign(cfg) * _end_offset(cfg)
    return point


def tail_point_task(cfg) -> np.ndarray:
    """Task-frame (x, y, z) of the glued tail's end once the roll is paid out: at the exit direction."""

    axis = material_axis(cfg)
    centre = bar_centre_task(cfg)
    point = np.array([centre[0], centre[1], float(cfg["dispenser"]["bar_height"])], dtype=float)
    point[axis] += pull_sign(cfg) * tail_radius(cfg)
    return point


def spawn_footprint_task(cfg) -> np.ndarray:
    """Task-frame (x, y) corners of the spawn: band plus posts, in plan view.

    Along the axis from the roll's back to the free end; across it the wider of
    the band and the posts.
    """

    axis = material_axis(cfg)
    sign = pull_sign(cfg)
    marks = roll_marks(cfg)
    centre = bar_centre_task(cfg)
    dispenser = cfg["dispenser"]
    half_across = max(
        0.5 * float(cfg["cloth"]["width"]),
        0.5 * float(dispenser["span"]) + float(dispenser["post_radius"]),
    )
    out = []
    for s_along in (-float(marks["back_s"]), float(marks["free_end_s"])):
        for s_across in (-1.0, 1.0):
            point = centre.copy()
            point[axis] += sign * s_along
            point[1 - axis] += s_across * half_across
            out.append(point)
    return np.asarray(out, dtype=float)


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


# ----------------------------------------------------------------------- tape


def arc_positions(points_mz, profile) -> np.ndarray:
    """Arc length along ``profile`` of the point on it nearest to each of ``points_mz``.

    ``profile`` is the (material offset, height) polyline `spiral_profile`
    builds, unmirrored; ``points_mz`` are particles in the same plane. Each
    point is projected onto every segment and the nearest projection wins, so
    a particle between two samples gets a fractional arc length. Neighbouring
    turns sit a full pitch (>= 14 mm) apart and the flat run starts a roll
    radius away from the roll's foot, so the nearest segment is never the
    wrong turn or the wrong run.
    """

    pts = np.asarray(points_mz, dtype=float).reshape(-1, 2)
    prof = np.asarray(profile, dtype=float)
    head, tail = prof[:-1], prof[1:]
    seg = tail - head
    length = np.linalg.norm(seg, axis=1)
    arcs = np.concatenate([[0.0], np.cumsum(length)])
    rel = pts[:, None, :] - head[None, :, :]
    t = np.einsum("psk,sk->ps", rel, seg) / np.maximum(length * length, 1e-18)[None, :]
    t = np.clip(t, 0.0, 1.0)
    closest = head[None, :, :] + t[..., None] * seg[None, :, :]
    best = np.argmin(np.sum((pts[:, None, :] - closest) ** 2, axis=2), axis=1)
    return arcs[best] + t[np.arange(len(pts)), best] * length[best]


def spool_plan(points_mz, profile, marks, lead: float, anchor_arc: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Which particles ride on the spool at birth, how much band each has before the exit, and which are glued.

    ``marks["rolled"]`` is the arc from the inner end to the exit tangent (where
    the band leaves the bar). A particle at arc ``a`` has ``b = rolled - a`` of
    band between it and the exit; every particle on the bar with ``b > lead`` is
    bound to the spool and freed once the pull has paid out ``b - lead``, except
    the glued tail (``a <= anchor_arc``), which is never freed by the pull.
    Returns ``(held particle indices, their b, glued mask over held)``.
    """

    a = arc_positions(points_mz, profile)
    exit_arc = float(marks["rolled"])
    b = exit_arc - a
    held = np.flatnonzero((a <= exit_arc + 1e-9) & (b > float(lead)))
    return held, b[held], a[held] <= float(anchor_arc) + 1e-9


def spiral_angles(profile, bar_height: float) -> tuple[np.ndarray, np.ndarray]:
    """``(arcs, angles)`` of the wound part of the profile: unwrapped angle about the bar per sample.

    The angle is measured in the (material offset, height) plane, zero at the
    exit direction (level with the axis on the pull side), and unwrapped so it
    runs monotonically from ``2 pi x turns`` at the inner end down to zero at
    the exit tangent.
    """

    prof = np.asarray(profile, dtype=float)
    on_table = np.flatnonzero(prof[:, 1] <= prof[-1, 1] + 1e-9)
    exit_index = int(on_table[0]) if on_table.size else len(prof) - 2
    wound = prof[:exit_index]
    arcs = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(wound, axis=0), axis=1))])
    angles = np.unwrap(np.arctan2(wound[:, 1] - float(bar_height), wound[:, 0]))
    angles = angles - angles[-1]
    return arcs, angles


def spool_angle(cfg, paid_out: float) -> float:
    """How far the spool has turned (radians, in the profile plane) after ``paid_out`` of band.

    The peel front sits at arc ``rolled - paid_out``; the spool turns so that
    front is at the exit direction, i.e. by minus that sample's unwrapped angle.
    Once the front reaches the glued tail (``paid_out >= rolled - anchor_arc``)
    the spool stops. Negative values are the winding sense (clockwise in the
    profile plane).
    """

    arcs, angles = spiral_angles(profile(cfg), float(cfg["dispenser"]["bar_height"]))
    exit_arc = float(arcs[-1])
    front = max(exit_arc - float(paid_out), spool_cfg(cfg)["anchor_arc"])
    front = min(front, exit_arc)
    return -float(np.interp(front, arcs, angles))


# --------------------------------------------------------------------- checks


def cloth_unroll_checks(cfg) -> list[tuple[str, float, float, bool]]:
    """``[(name, measured, limit, ok)]`` for a spawnable, solvable layout.

    One list for the randomizer's reject step, the offline gate, the corner
    harness and the demo's start-up print. Metres throughout. The first five
    rows are the pitch-sensitive ones `pitch_bounds` bisects on.
    """

    cloth = cfg["cloth"]
    pitch = float(cloth["roll"]["pitch"])
    end = pull_end_task(cfg)
    base = np.asarray([float(v) for v in cfg["reach"]["base_xy"]], dtype=float)
    reach = float(np.linalg.norm(end - base))
    max_reach = float(cfg["reach"]["max_hand_dist"])
    pull = pull_distance(cfg)
    max_pull = float(cfg["physical"]["stroke_m"])
    spread = design_spread_ratio(cfg)
    max_spread = float(cfg["grasp"]["max_start_spread_ratio"])

    ge = _roll_rows(cfg, pitch) + [
        ("layers_spaced", pitch, PITCH_MIN),
        ("band_in_workspace", workspace_margin(cfg, np.vstack([spawn_footprint_task(cfg), end[None, :]])), WORKSPACE_MARGIN),
    ]
    rows = [(name, value, limit, value >= limit - 1e-9) for name, value, limit in ge]
    rows.append(("hand_reach", reach, max_reach, reach <= max_reach + 1e-9))
    rows.append(("pull_within_stroke", pull, max_pull, pull <= max_pull + 1e-9))
    rows.append(("start_still_stored", spread, max_spread, spread <= max_spread + 1e-9))
    return rows


__all__ = [
    "CENTER_ALONG_BASE",
    "CENTER_ALONG_SHIFT",
    "MIN_FLAT_SPACINGS",
    "PITCH_MAX",
    "PITCH_MIN",
    "SHOVE_BAR_CLEARANCE",
    "START_SPREAD_SLACK",
    "WORKSPACE_MARGIN",
    "along_leaf",
    "arc_positions",
    "bar_centre_task",
    "center_along_bounds",
    "center_along_from_frac",
    "cloth_unroll_checks",
    "design_spread_ratio",
    "grasp_point_task",
    "material_axis",
    "pitch_bounds",
    "pitch_from_frac",
    "profile",
    "pull_distance",
    "pull_end_task",
    "pull_sign",
    "roll_marks",
    "spawn_footprint_task",
    "spiral_angles",
    "spool_angle",
    "spool_cfg",
    "spool_plan",
    "start_spread_limit",
    "tail_point_task",
    "tail_radius",
    "taut_length",
    "taut_reach",
    "hang_height",
    "relaxed_front_offset",
    "glued_back_offset",
    "span_max",
    "workspace_margin",
]
