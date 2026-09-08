"""cloth_fold's layout rules and feasibility checks, numpy only.

Kept apart from `cloth_fold.py` so the offline gate
(`tests/check_cloth_fold_geometry.py`) and the variation harness can load them
without Genesis: `cloth_fold.py` imports Genesis at module level. Everything
here takes the TASK config alone (a dict or an OmegaConf node under
``cfg.task``) and works in the task frame, metres, table at z = 0.

The scene, for the reader who has only this file: a square sheet (24 cm a
side) lies flat on the table with its edges along x and y, centred at
(`center_x`, `center_y`). The gripper takes ONE corner by its tip -- which one
is `grasp.corner`, named from the arm's point of view (far = +x, near = -x,
left = +y, right = -y) -- and carries it half a turn about the fold line.

HOW FAR it carries it is `goal.fold_fraction`: 1.0 puts the corner on the
opposite corner and the fold line is the other diagonal; 0.5 puts it on the
sheet's middle and the fold line sits halfway out towards the grasped corner.
The line always runs perpendicular to the corner-to-corner diagonal, offset
from the middle by ``material x (1 - fold_fraction)`` towards the grasped
corner, and the corner is joined to it by a fixed length of material -- so the
hand's path is a semicircle of radius ``material x fold_slack``, and both the
radius and the material shrink with the fraction.

Whichever corner is taken, one of the two points the hand has to reach at
table height (the grasp, or where the corner is put down) is on the far (+x)
side of the sheet. That point decides how far the sheet may sit from the arm,
which is why `center_x` is derived from a unit fraction under the reach disc
instead of being drawn on its own.
"""

from __future__ import annotations

import math

import numpy as np

# ------------------------------------------------------------- envelope rules
#: The four corners, as (sign along x, sign along y) from the sheet's middle.
CORNER_SIGNS: dict[str, tuple[int, int]] = {
    "far_left": (1, 1),
    "far_right": (1, -1),
    "near_left": (-1, 1),
    "near_right": (-1, -1),
}
#: How each corner is named in the instruction sentence.
CORNER_WORDS: dict[str, str] = {
    "far_left": "far left",
    "far_right": "far right",
    "near_left": "near left",
    "near_right": "near right",
}
#: How each `goal.fold_fraction` is named in the instruction sentence. The sheet
#: is plain and square, so nothing in the picture says where the crease belongs
#: -- the sentence is the only place it can come from, exactly as for the corner.
EXTENT_WORDS: dict[float, str] = {
    1.0: "over onto the opposite corner",
    0.9: "nine tenths of the way to the opposite corner",
    0.8: "four fifths of the way to the opposite corner",
}
#: `cloth.center_x` window before the reach disc caps its far side: the yaml's
#: baseline 0.040 +- 0.030, as planned in `variation_and_difficulty_plan_zh.md`
#: 3.9. The baseline itself sits at the reach cap (0.0402), so the drawn window
#: is [0.010, ~0.035..0.063] depending on the corner, `center_y` and, for the
#: near_* corners whose put-down point is the far one, `goal.fold_fraction`.
CENTER_X_MIN = 0.010
CENTER_X_MAX = 0.070
#: Smallest distance any corner of the resting sheet may come to the workspace
#: box's x / y edges (same value as cloth_unpleat / rope_unwinding).
WORKSPACE_MARGIN = 0.040


def corner_name(cfg) -> str:
    name = str(cfg["grasp"]["corner"])
    if name not in CORNER_SIGNS:
        raise ValueError(
            f"grasp.corner must be one of {sorted(CORNER_SIGNS)}, got {name!r}."
        )
    return name


def corner_signs(cfg) -> tuple[int, int]:
    """``(sx, sy)``: which way the grasped corner lies from the sheet's middle."""

    return CORNER_SIGNS[corner_name(cfg)]


def mesh_diagonal(cfg) -> str:
    """Which way the control mesh's triangle diagonals run: ``"up"`` (lower-left
    to upper-right) or ``"down"`` (lower-right to upper-left).

    The crease has to CROSS the diagonal edges. A PBD triangle mesh bends
    differently along its diagonal edges than across them, and a fold whose
    crease runs along the diagonal lets the flap slide sideways as it lands:
    measured 2026-09-06 on the far_right / near_left corners with the baseline
    "up" mesh -- crease on the line to 1 mm, but the moving half 30-38 mm off
    and 46% of particles out of place; the same layouts pass at 3.7 mm with the
    diagonal flipped. A mesh that alternates diagonals per quad would be
    symmetric, but Genesis then remeshes it to 4604 particles instead of the
    clean 4225 subdivision, and vertex order -- which every judge needs -- is
    lost. So the diagonal is chosen per corner: the fold line runs along
    (+1, -1) for the same-sign corners (far_left, near_right) and along (+1, +1)
    for the other two.
    """

    sx, sy = corner_signs(cfg)
    return "up" if sx * sy > 0 else "down"


def half_size(cfg) -> np.ndarray:
    return 0.5 * np.asarray([float(v) for v in cfg["cloth"]["size"]], dtype=float)


def cloth_centre_task(cfg) -> np.ndarray:
    """Task-frame (x, y) of the sheet's middle. The fold line passes through it."""

    cloth = cfg["cloth"]
    return np.array([float(cloth["center_x"]), float(cloth["center_y"])], dtype=float)


def fold_fraction(cfg) -> float:
    """How far along the diagonal the grasped corner is carried, as a fraction.

    1.0 is corner onto corner; 0.5 stops on the sheet's middle. Values above 1
    are refused: the flap would land past the opposite corner on bare table,
    while `fold_targets` raises EVERY moving particle by one cloth thickness,
    so the overhanging strip would carry a 4 mm bias against a 7.5 mm gate.
    """

    value = float(cfg["goal"]["fold_fraction"])
    if value not in EXTENT_WORDS:
        raise ValueError(
            f"goal.fold_fraction must be one of {sorted(EXTENT_WORDS)}, got {value}. "
            f"The sentence the policy reads is built from `EXTENT_WORDS`, so a "
            f"fraction with no phrase would be commanded but never stated."
        )
    return value


def grasp_offset(cfg) -> np.ndarray:
    """Offset from the sheet's middle to the grasp point, in the plane.

    The tip itself. `grasp.at: edge_mid` (kept for the record, measured not to
    work with one gripper) takes the middle of the far edge on the corner's x
    side.
    """

    half = half_size(cfg)
    sx, sy = corner_signs(cfg)
    mode = str(cfg["grasp"]["at"])
    if mode == "corner":
        return np.array([sx * half[0], sy * half[1]], dtype=float)
    if mode == "edge_mid":
        return np.array([sx * half[0], 0.0], dtype=float)
    raise ValueError(f"task.grasp.at must be 'corner' or 'edge_mid', got {mode!r}.")


def grasp_point_task(cfg) -> np.ndarray:
    return cloth_centre_task(cfg) + grasp_offset(cfg)


def fold_normal_task(cfg) -> np.ndarray:
    """Unit in-plane normal of the fold line, pointing at the half that lifts."""

    offset = grasp_offset(cfg)
    return offset / max(float(np.linalg.norm(offset)), 1e-12)


def fold_point_task(cfg) -> np.ndarray:
    """A point ON the fold line: the middle, pushed out towards the grasped corner.

    At `fold_fraction` 1.0 this is the middle itself and the line is the other
    diagonal, which is what every reading was calibrated on. Below that the line
    slides towards the grasped corner, so less material moves.
    """

    shift = float(np.linalg.norm(grasp_offset(cfg))) * (1.0 - fold_fraction(cfg))
    return cloth_centre_task(cfg) + shift * fold_normal_task(cfg)


def fold_target_task(cfg) -> np.ndarray:
    """Where the grasped corner is put down: its mirror across the fold line.

    Mirroring the grasp point across a line offset by ``d`` puts it at
    ``centre + (1 - 2f) * offset``: the opposite corner at f = 1, the middle at
    f = 0.5.
    """

    return cloth_centre_task(cfg) + (1.0 - 2.0 * fold_fraction(cfg)) * grasp_offset(cfg)


def material_distance(cfg) -> float:
    """Cloth between the fold line and the grasp point, measured flat."""

    return float(np.linalg.norm(grasp_offset(cfg))) * fold_fraction(cfg)


def fold_radius(cfg) -> float:
    return material_distance(cfg) * float(cfg["physical"]["fold_slack"])


def slack_shortfall(cfg) -> float:
    """How far short of the opposite corner the hand stops: material x (1 - slack)."""

    return material_distance(cfg) * (1.0 - float(cfg["physical"]["fold_slack"]))


def apex_height(cfg) -> float:
    """Height of the hand at the top of the arc, table = 0."""

    return float(cfg["cloth"]["z"]) + fold_radius(cfg) + float(cfg["grasp"]["touch_clearance"])


# ---------------------------------------------------------------- derivations


def far_corner_task(cfg) -> np.ndarray:
    """The one of grasp point / put-down point on the +x side.

    The hand has to be there at table height either to take the corner (far_*)
    or to put it down (near_*), so it is the point the reach disc constrains.
    """

    grasp, target = grasp_point_task(cfg), fold_target_task(cfg)
    return grasp if grasp[0] >= target[0] else target


def _far_corner_offset(cfg) -> np.ndarray:
    """Offset from the sheet's middle to the far corner, independent of `center_x`.

    Same rule as `far_corner_task`, written from the offsets alone because
    `center_x_bounds` needs it BEFORE `center_x` exists. For a far_* corner the
    grasp point wins whatever the fraction; for a near_* corner the put-down
    point wins, and it walks back towards the middle as the fraction falls, so
    a shorter fold leaves those layouts MORE room under the reach disc.
    """

    offset = grasp_offset(cfg)
    landing = (1.0 - 2.0 * fold_fraction(cfg)) * offset
    return offset if offset[0] >= landing[0] else landing


def _far_corner_y(cfg) -> float:
    """y of the far corner, which does not depend on `center_x`."""

    return float(cfg["cloth"]["center_y"]) + float(_far_corner_offset(cfg)[1])


def center_x_bounds(cfg) -> tuple[float, float]:
    """``[lo, hi]`` for `cloth.center_x` under the drawn corner, `center_y`, fraction.

    ``hi`` is the smaller of `CENTER_X_MAX` and the value at which the far
    corner sits exactly on the reach disc (`reach:`): the disc's chord at the
    far corner's y is ``sqrt(R^2 - (y_far - base_y)^2)``, so the far corner's x
    may reach ``base_x + chord`` and the middle sits its own x offset behind it.
    Raises when the window is empty (the draw is rejected).
    """

    base = np.asarray([float(v) for v in cfg["reach"]["base_xy"]], dtype=float)
    radius = float(cfg["reach"]["max_hand_dist"])
    gap = _far_corner_y(cfg) - base[1]
    inside = radius * radius - gap * gap
    if inside <= 0.0:
        raise ValueError(
            f"cloth_fold: the far corner's y {_far_corner_y(cfg):+.4f} lies outside the reach disc."
        )
    hi = min(CENTER_X_MAX, base[0] + math.sqrt(inside) - float(_far_corner_offset(cfg)[0]))
    lo = CENTER_X_MIN
    if hi < lo - 1e-12:
        raise ValueError(
            f"cloth_fold: no center_x keeps the far corner inside reach: "
            f"window [{lo:.4f}, {hi:.4f}] (corner {corner_name(cfg)}, "
            f"center_y {float(cfg['cloth']['center_y']):+.4f}, "
            f"fold_fraction {fold_fraction(cfg):.2f})."
        )
    # Plain floats: the derived value is written back into an OmegaConf leaf,
    # which refuses numpy scalars.
    return float(lo), float(hi)


def center_x_from_frac(cfg, frac: float) -> float:
    lo, hi = center_x_bounds(cfg)
    return float(lo + float(np.clip(frac, 0.0, 1.0)) * (hi - lo))


# --------------------------------------------------------------------- checks


def cloth_footprint_task(cfg) -> np.ndarray:
    """Task-frame (x, y) of the resting sheet's four corners."""

    half = half_size(cfg)
    centre = cloth_centre_task(cfg)
    return np.asarray(
        [centre + np.array([sx * half[0], sy * half[1]]) for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)],
        dtype=float,
    )


def workspace_margin(cfg, points_xy) -> float:
    """Smallest distance from any of ``points_xy`` (task frame) to the box's x / y edges."""

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


def cloth_fold_checks(cfg) -> list[tuple[str, float, float, bool]]:
    """``[(name, measured, limit, ok)]`` for a spawnable, solvable layout.

    One list for the randomizer's reject step, the offline gate, the corner
    harness and the demo's start-up print. Metres throughout.
    """

    base = np.asarray([float(v) for v in cfg["reach"]["base_xy"]], dtype=float)
    reach = float(np.linalg.norm(far_corner_task(cfg) - base))
    max_reach = float(cfg["reach"]["max_hand_dist"])
    apex = apex_height(cfg)
    z_top = float(cfg["workspace"]["z"][1])
    shortfall = slack_shortfall(cfg)
    gate = float(cfg["success"]["particle_error_mean_max"])
    margin = workspace_margin(cfg, cloth_footprint_task(cfg))

    rows = [
        ("far_corner_reach", reach, max_reach, reach <= max_reach + 1e-9),
        ("cloth_in_workspace", margin, WORKSPACE_MARGIN, margin >= WORKSPACE_MARGIN - 1e-9),
        ("apex_below_workspace_top", apex, z_top, apex <= z_top + 1e-9),
        ("slack_within_gate", shortfall, gate, shortfall <= gate + 1e-9),
    ]
    return rows


__all__ = [
    "CENTER_X_MAX",
    "CENTER_X_MIN",
    "CORNER_SIGNS",
    "CORNER_WORDS",
    "EXTENT_WORDS",
    "WORKSPACE_MARGIN",
    "apex_height",
    "center_x_bounds",
    "center_x_from_frac",
    "cloth_centre_task",
    "cloth_fold_checks",
    "cloth_footprint_task",
    "corner_name",
    "corner_signs",
    "far_corner_task",
    "fold_fraction",
    "fold_normal_task",
    "fold_point_task",
    "fold_radius",
    "fold_target_task",
    "grasp_offset",
    "grasp_point_task",
    "half_size",
    "material_distance",
    "mesh_diagonal",
    "slack_shortfall",
    "workspace_margin",
]
