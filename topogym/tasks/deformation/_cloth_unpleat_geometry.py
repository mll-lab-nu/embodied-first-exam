"""cloth_unpleat's layout rules and feasibility checks, numpy only.

Kept apart from `cloth_unpleat.py` so the offline gate
(`tests/check_cloth_unpleat_geometry.py`) and the variation harness can load
them without Genesis: `cloth_unpleat.py` imports Genesis at module level.
Everything here takes the TASK config alone (a dict or an OmegaConf node under
``cfg.task``) and works in the task frame, metres, table at z = 0: the
workspace box and the arm base are task-frame quantities, so no world origin
is needed for any row.

The scene, for the reader who has only this file: a 26 cm x 12 cm cloth band
lies on the table with its length along one horizontal axis (`material_axis`).
Its middle carries an unpressed knife pleat -- the band doubles back and up to
a crest, then comes back down past the crease and continues -- so a strip of
plan width `pleat.width` about the crease stacks three layers deep. The band's
plan span is 2 x `lead`; the material the pleat stores is the band's material
length minus that span. The gripper takes the band's free END (the tail side,
`pull_side` decides which end of the axis that is) `edge_inset` in from the
edge and drags it along the table by ``stored x pull_scale``.
"""

from __future__ import annotations

import math

import numpy as np

from .cloth_profile_mesh import pleat_landmarks, pleat_profile

# ------------------------------------------------------------- envelope rules
#: The band's tail (flat run past the crest) keeps at least this many control
#: mesh spacings, so the pleat never sits at the very end of the band.
MIN_TAIL_SPACINGS = 4
#: `grasp.edge_inset` window before the three-layer clearance caps it. The
#: floor is two particle sizes (the attachment disc must land wholly on cloth);
#: the ceiling is the value the yaml has carried since 2026-08-23 plus 6 mm.
EDGE_INSET_MIN = 0.008
EDGE_INSET_MAX = 0.018
#: How far the band may slide along its own axis from the yaml's baseline
#: position, before the reach and workspace rows cap the far side.
CENTER_ALONG_BASE = 0.0
CENTER_ALONG_SHIFT = 0.030
#: Smallest distance any point of the band -- spawn footprint or pull end -- may
#: come to the workspace box's x / y edges (same value as rope_unwinding).
WORKSPACE_MARGIN = 0.040
#: Longest pull one grasp is allowed to command. The shipped pull is 64 mm; the
#: envelope's widest pleat asks 95 mm. Beyond this the arm's follow error at
#: table height has no measurement.
PULL_MAX = 0.120


def material_axis(cfg) -> int:
    """0 when the band's length runs along task x, 1 along task y."""

    axis = str(cfg["cloth"]["material_axis"]).lower()
    if axis not in ("x", "y"):
        raise ValueError(f"cloth.material_axis must be 'x' or 'y', got {axis!r}.")
    return 0 if axis == "x" else 1


def pull_sign(cfg) -> float:
    """+1 when the free end is at the positive end of the material axis, -1 mirrored.

    `cloth.pull_side: -1` IS the mirror layout: the pleat profile is reflected
    in the band's own axis, so the tail (the end the gripper takes) lies at the
    negative end and the pull runs toward negative coordinates. The arm base sits
    on y = 0 and the workspace box is symmetric about it, so with the band along
    y every row below reads the same for both signs.
    """

    cloth = cfg["cloth"]
    side = cloth.get("pull_side", 1) if hasattr(cloth, "get") else 1
    return -1.0 if int(side) < 0 else 1.0


def band_centre_task(cfg) -> np.ndarray:
    """Task-frame (x, y) of the band's plan-view middle."""

    cloth = cfg["cloth"]
    return np.array([float(cloth["center_x"]), float(cloth["center_y"])], dtype=float)


def pleat_marks(cfg) -> dict:
    """`pleat_landmarks` of the unmirrored profile plus the flat runs.

    ``lead`` is the flat run before the crease, ``tail`` the one after the
    crest's arm lands; ``half_span`` is half the plan span. The sign is not
    applied here -- these are lengths.
    """

    cloth = cfg["cloth"]
    corners = pleat_profile(
        material_length=float(cloth["material_length"]),
        pleat_width=float(cloth["pleat"]["width"]),
        crest_height=float(cloth["pleat"]["crest_height"]),
        rest_z=float(cloth["z"]),
    )
    marks = pleat_landmarks(corners)
    width = float(cloth["pleat"]["width"])
    lead = -float(corners[0][0])
    marks["lead"] = lead
    marks["tail"] = lead - width
    marks["half_span"] = 0.5 * float(marks["plan_span"])
    return marks


# ---------------------------------------------------------------- derivations


def edge_inset_bounds(cfg) -> tuple[float, float]:
    """``[lo, hi]`` for `grasp.edge_inset` under the drawn pleat.

    Floor: two particle sizes (never below `EDGE_INSET_MIN`). Ceiling: the
    yaml's `EDGE_INSET_MAX`, or less when the pleat is wide -- the attachment
    disc has to stay ``2 x attach_radius`` clear of the three-layer strip, which
    occupies ``[-width, +width]`` about the crease. Raises when the window is
    empty (the draw is rejected).
    """

    marks = pleat_marks(cfg)
    width = float(cfg["cloth"]["pleat"]["width"])
    lo = max(EDGE_INSET_MIN, 2.0 * float(cfg["cloth"]["particle_size"]))
    hi = min(EDGE_INSET_MAX, marks["half_span"] - width - 2.0 * float(cfg["grasp"]["attach_radius"]))
    if hi < lo - 1e-12:
        raise ValueError(
            f"cloth_unpleat: no edge_inset keeps the attachment disc off the pleat: "
            f"window [{lo:.4f}, {hi:.4f}] (width {width:.3f}, half span {marks['half_span']:.4f})."
        )
    return lo, hi


def edge_inset_from_frac(cfg, frac: float) -> float:
    lo, hi = edge_inset_bounds(cfg)
    return float(lo + float(np.clip(frac, 0.0, 1.0)) * (hi - lo))


def pull_distance(cfg) -> float:
    """How far the free end travels: the stored material times `pull_scale`."""

    return float(pleat_marks(cfg)["stored"]) * float(cfg["physical"]["pull_scale"])


def _end_offset(cfg) -> float:
    """Unsigned distance from the band's middle to the pull's END point, along the axis."""

    marks = pleat_marks(cfg)
    return marks["half_span"] - float(cfg["grasp"]["edge_inset"]) + pull_distance(cfg)


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

    Starts from ``CENTER_ALONG_BASE +- CENTER_ALONG_SHIFT`` and caps the side
    the pull runs toward twice: the pull's end point must stay inside the reach
    disc (`reach:`), and inside the workspace box by `WORKSPACE_MARGIN`; the
    other side is capped by the spawn footprint staying inside the box. Written
    for either `pull_side`: the caps are computed for +1 and mirrored. Raises
    when the window is empty (the draw is rejected).
    """

    axis = material_axis(cfg)
    sign = pull_sign(cfg)
    marks = pleat_marks(cfg)
    centre = band_centre_task(cfg)
    across = float(centre[1 - axis])
    base = np.asarray([float(v) for v in cfg["reach"]["base_xy"]], dtype=float)
    box = cfg["workspace"]["x" if axis == 0 else "y"]
    lo_box, hi_box = float(box[0]) + WORKSPACE_MARGIN, float(box[1]) - WORKSPACE_MARGIN

    off = _end_offset(cfg)
    chord = _reach_half_width(cfg, across)
    if chord < 0.0:
        raise ValueError(
            f"cloth_unpleat: the band's across position {across:+.4f} lies outside the reach disc."
        )
    # In the +1 orientation the end point is centre + off and the spawn's far
    # edge is centre - half_span.
    hi_reach = base[axis] + chord - off
    hi_ws = hi_box - off
    lo_ws = lo_box + marks["half_span"]
    lo_plus = max(CENTER_ALONG_BASE - CENTER_ALONG_SHIFT, lo_ws)
    hi_plus = min(CENTER_ALONG_BASE + CENTER_ALONG_SHIFT, hi_reach, hi_ws)
    if sign > 0:
        lo, hi = lo_plus, hi_plus
    else:
        lo, hi = -hi_plus, -lo_plus
    if hi < lo - 1e-12:
        raise ValueError(
            f"cloth_unpleat: no centre position keeps the pull inside reach and workspace: "
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


# --------------------------------------------------------------------- points


def grasp_point_task(cfg) -> np.ndarray:
    """Task-frame (x, y) of the design grasp: the free end, `edge_inset` in."""

    axis = material_axis(cfg)
    marks = pleat_marks(cfg)
    point = band_centre_task(cfg).copy()
    point[axis] += pull_sign(cfg) * (marks["half_span"] - float(cfg["grasp"]["edge_inset"]))
    return point


def pull_end_task(cfg) -> np.ndarray:
    """Task-frame (x, y) where the grasped material ends up after the pull."""

    axis = material_axis(cfg)
    point = grasp_point_task(cfg)
    point[axis] += pull_sign(cfg) * pull_distance(cfg)
    return point


def band_footprint_task(cfg) -> np.ndarray:
    """Task-frame (x, y) of the spawn band's four plan corners."""

    axis = material_axis(cfg)
    marks = pleat_marks(cfg)
    centre = band_centre_task(cfg)
    half_w = 0.5 * float(cfg["cloth"]["width"])
    out = []
    for s_along in (-1.0, 1.0):
        for s_across in (-1.0, 1.0):
            point = centre.copy()
            point[axis] += s_along * marks["half_span"]
            point[1 - axis] += s_across * half_w
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


# --------------------------------------------------------------------- checks


def cloth_unpleat_checks(cfg) -> list[tuple[str, float, float, bool]]:
    """``[(name, measured, limit, ok)]`` for a spawnable, solvable layout.

    One list for the randomizer's reject step, the offline gate, the corner
    harness and the demo's start-up print. Metres throughout.
    """

    cloth = cfg["cloth"]
    marks = pleat_marks(cfg)
    width = float(cloth["pleat"]["width"])
    inset = float(cfg["grasp"]["edge_inset"])
    end = pull_end_task(cfg)
    base = np.asarray([float(v) for v in cfg["reach"]["base_xy"]], dtype=float)
    reach = float(np.linalg.norm(end - base))
    max_reach = float(cfg["reach"]["max_hand_dist"])
    pull = pull_distance(cfg)
    spread = float(marks["plan_span"]) / float(cloth["material_length"])
    max_spread = float(cfg["grasp"]["max_start_spread_ratio"])

    ge = [
        ("pleat_fits_band", float(marks["tail"]), MIN_TAIL_SPACINGS * float(cloth["mesh"]["spacing"])),
        ("crest_above_underlayer", float(cloth["pleat"]["crest_height"]), float(cloth["particle_size"])),
        ("grasp_clears_three_layers", marks["half_span"] - inset - width, 2.0 * float(cfg["grasp"]["attach_radius"])),
        ("band_in_workspace", workspace_margin(cfg, np.vstack([band_footprint_task(cfg), end[None, :]])), WORKSPACE_MARGIN),
    ]
    rows = [(name, value, limit, value >= limit - 1e-9) for name, value, limit in ge]
    rows.append(("hand_reach", reach, max_reach, reach <= max_reach + 1e-9))
    rows.append(("pull_within_stroke", pull, PULL_MAX, pull <= PULL_MAX + 1e-9))
    rows.append(("start_still_stored", spread, max_spread, spread <= max_spread + 1e-9))
    return rows


__all__ = [
    "CENTER_ALONG_BASE",
    "CENTER_ALONG_SHIFT",
    "EDGE_INSET_MAX",
    "EDGE_INSET_MIN",
    "MIN_TAIL_SPACINGS",
    "PULL_MAX",
    "WORKSPACE_MARGIN",
    "along_leaf",
    "band_centre_task",
    "band_footprint_task",
    "center_along_bounds",
    "center_along_from_frac",
    "cloth_unpleat_checks",
    "edge_inset_bounds",
    "edge_inset_from_frac",
    "grasp_point_task",
    "material_axis",
    "pleat_marks",
    "pull_distance",
    "pull_end_task",
    "pull_sign",
    "workspace_margin",
]
