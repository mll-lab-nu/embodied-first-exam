"""Pure (numpy / dict) builders of the soft-world configs of the cloth tasks, shared by the Isaac tasks and the sidecar.

``cloth_edge_feed_world`` / ``cloth_fold_pinch_world`` return the ``cloth`` world block that :func:`spec.world_cfg`
completes; :func:`task_world` appends the gripper colliders and the solver settings the way the tasks do.  All numbers are
the nominal (fixed) scenes; quaternions xyzw, env-local metres, ``table_z`` is the table top.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from . import spec

#: the gripper's contact links mirrored into every soft world as kinematic boxes: gel pads, sensor cases, finger bodies
#: (``link`` = body name of the X-Trainer GelSight-Mini articulation; offsets in the link frame, xyz [+ xyzw])
GSMINI_COLLIDERS: List[Dict[str, Any]] = [
    {"name": "pad_left", "link": "gsmini_left", "half": [0.0105, 0.008, 0.002], "offset": [0.0, 0.0, 0.002], "mu": 1.0},
    {
        "name": "pad_right",
        "link": "gsmini_right",
        "half": [0.0105, 0.008, 0.002],
        "offset": [0.0, 0.0, 0.002],
        "mu": 1.0,
    },
    {
        "name": "case_left",
        "link": "gsmini_left",
        "half": [0.0175, 0.01445, 0.012],
        "offset": [0.0021, -0.00055, -0.012],
        "mu": 0.5,
    },
    {
        "name": "finger_left",
        "link": "gsmini_left",
        "half": [0.0613, 0.024, 0.01135],
        "offset": [-0.0417, -0.0005, -0.01615],
        "mu": 0.5,
    },
    {
        "name": "case_right",
        "link": "gsmini_right",
        "half": [0.0175, 0.01445, 0.012],
        "offset": [-0.0009, -0.00055, -0.012],
        "mu": 0.5,
    },
    {
        "name": "finger_right",
        "link": "gsmini_right",
        "half": [0.0613, 0.024, 0.01135],
        "offset": [0.0429, -0.0005, -0.01615],
        "mu": 0.5,
    },
]

#: the forearm of the parked left arm (sleeve task): a cylinder on link ``J2_3``, axis = the collider frame's z
FOREARM_COLLIDER: Dict[str, Any] = {
    "name": "forearm",
    "link": "J2_3",
    "shape": "cylinder",
    "radius": 0.04,
    "half_height": 0.22,
    "half": [0.0, 0.0, 0.0],
    "offset": [0.12, 0.0, -0.01, 0.0, 0.7071, 0.0, 0.7071],
    "mu": 0.7,
}

TABLE_Z = 1.102


def gsmini_colliders(pad_mu: float = 1.0) -> List[spec.ColliderSpec]:
    """The six gripper colliders with the gel pads' friction set to ``pad_mu`` (a per-task number)."""
    out = []
    for i, d in enumerate(GSMINI_COLLIDERS):
        d = dict(d)
        if i < 2:
            d["mu"] = float(pad_mu)
        out.append(spec.ColliderSpec.from_cfg(d))
    return out


def task_world(
    world: Dict[str, Any],
    colliders: List[spec.ColliderSpec],
    fps: int = 60,
    substeps: int = 10,
    iterations: int = 5,
    table_z: float = TABLE_Z,
) -> Dict[str, Any]:
    """The world block of a task: ``world`` (a builder below) + solver settings + the collider list (the way the tasks assemble it)."""
    cfg = spec.merge_dicts(world, {"substeps": int(substeps), "iterations": int(iterations)})
    cfg["fps"] = int(fps)
    cfg.setdefault("table", {})
    cfg["table"].setdefault("z", float(table_z))
    cfg["colliders"] = [s.world_cfg() for s in colliders]
    return cfg


# -- cloth_edge_feed --------------------------------------------------------------------------------------------------

CLOTH_EDGE_FEED: Dict[str, Any] = {
    "shelf": {"x_front": 0.12, "depth": 0.10, "half_y": 0.09, "height": 0.20},
    "cloth_size": [0.10, 0.12],
    "cloth_cells": [10, 12],
    "overhang": 0.045,
    "clamp_len": 0.02,
    "center_y": 0.0,
    "radius": 0.0032,  # 6.4 mm thick: a light pinch between the gel pads (they close to 6.5 mm)
    # material
    "density": 0.40,
    "tri_ke": 1.0e4,
    "tri_ka": 1.0e4,
    "tri_kd": 1.0e-1,
    "edge_ke": 32.0,
    "edge_kd": 1.0e-3,
    # contact (soft contact = particle vs shape); pad_mu is the gel pads' collider friction
    "contact": {"ke": 1.0e3, "kd": 1.0e1, "mu": 0.8, "pad_mu": 0.45},
    # episode / policy numbers of the task
    "end_dx": 0.003,
    "corner_zone": [0.0085, 0.0075, 0.01],
    "pinch_overlap": 0.00025,
    "settle_ticks": 45,
}


def cloth_edge_feed_geometry(g: Dict[str, Any], table_z: float) -> Dict[str, Any]:
    """Derived geometry of the scene: shelf top, cloth origin, clamp bar box."""
    s = g["shelf"]
    lx, ly = (float(v) for v in g["cloth_size"])
    r = float(g["radius"])
    shelf_top = table_z + float(s["height"])
    origin = np.array([s["x_front"] - float(g["overhang"]), float(g["center_y"]) - 0.5 * ly, shelf_top + r + 0.0005])
    cl = float(g["clamp_len"])
    x_far = origin[0] + lx
    half = np.array([0.5 * cl, 0.5 * ly + 0.01, 0.008])
    centre = np.array([x_far - 0.5 * cl, float(g["center_y"]), shelf_top + 2.0 * r + 0.001 + half[2]])
    return {"shelf_top": shelf_top, "origin": origin, "clamp_centre": centre, "clamp_half": half, "x_far": x_far}


def cloth_edge_feed_world(g: Dict[str, Any], table_z: float) -> Dict[str, Any]:
    s = g["shelf"]
    lx, ly = (float(v) for v in g["cloth_size"])
    nx, ny = (int(v) for v in g["cloth_cells"])
    geo = cloth_edge_feed_geometry(g, table_z)
    o, cl = geo["origin"], float(g["clamp_len"])
    h = float(s["height"])
    cx = s["x_front"] + 0.5 * float(s["depth"])
    c = g["contact"]
    return {
        "table": {"z": table_z, "half": [1.0, 1.0], "center": [0.0, 0.0]},
        "statics": [
            {
                "name": "shelf",
                "pos": [cx, float(g["center_y"]), table_z + 0.5 * h],
                "half": [0.5 * float(s["depth"]), float(s["half_y"]), 0.5 * h],
                "mu": 0.5,
            },
            {"name": "clamp", "pos": geo["clamp_centre"].tolist(), "half": geo["clamp_half"].tolist(), "mu": 0.8},
        ],
        "soft_contact": {"ke": float(c["ke"]), "kd": float(c["kd"]), "mu": float(c["mu"]), "gap": 0.005},
        "cloth": {
            "origin": o.tolist(),
            "size": [lx, ly],
            "cells": [nx, ny],
            "radius": float(g["radius"]),
            "density": float(g["density"]),
            "tri_ke": float(g["tri_ke"]),
            "tri_ka": float(g["tri_ka"]),
            "tri_kd": float(g["tri_kd"]),
            "edge_ke": float(g["edge_ke"]),
            "edge_kd": float(g["edge_kd"]),
            "pin_regions": [{"min": [o[0] + lx - cl, o[1] - 0.001], "max": [o[0] + lx + 0.001, o[1] + ly + 0.001]}],
            "color": [0.78, 0.30, 0.28],
        },
    }


def cloth_edge_feed_nominal_world(table_z: float = TABLE_Z) -> Dict[str, Any]:
    """The complete sidecar world config of the nominal ``cloth_edge_feed`` scene (cloth + shelf + clamp + the six gripper
    colliders, 60 Hz, 10 substeps, 5 iterations)."""
    g = CLOTH_EDGE_FEED
    return task_world(
        cloth_edge_feed_world(g, table_z), gsmini_colliders(float(g["contact"]["pad_mu"])), table_z=table_z
    )


def cloth_edge_feed_ids(cells) -> Dict[str, np.ndarray]:
    """Particle ids the task reads: the overhanging free edge (ix = 0 column, ordered along +y) and its +y corner."""
    nx, ny = (int(v) for v in cells)
    return {"edge": np.arange(ny + 1) * (nx + 1), "corner": np.array([ny * (nx + 1)])}


def pad_poses_horizontal(mid: np.ndarray, gap_center_dist: float) -> np.ndarray:
    """Collider poses (2, 7) xyzw of the two gel pads for a horizontal pinch (approach +x, closing axis z) at ``mid``.
    Pad 0 below (its +z face looks up), pad 1 above, rotated 180 degrees about x so its face looks down."""
    below = [mid[0], mid[1], mid[2] - 0.5 * gap_center_dist, 0, 0, 0, 1]
    above = [mid[0], mid[1], mid[2] + 0.5 * gap_center_dist, 1, 0, 0, 0]
    return np.array([below, above], dtype=np.float32)


# -- cloth_fold_half (flat fixture variant) ---------------------------------------------------------------------------

CLOTH_FOLD_HALF: Dict[str, Any] = {
    "cloth_size": [0.14, 0.08],
    "cloth_cells": [14, 8],
    "origin_xy": [-0.02, -0.04],
    "radius": 0.003,
    "clamp_len": 0.012,
    "density": 0.35,
    "tri_ke": 1.0e4,
    "tri_ka": 1.0e4,
    "tri_kd": 1.0e-1,
    "edge_ke": 5.0e-2,  # limp enough to keep a fold (a stiffer sheet springs open after the release)
    "edge_kd": 1.0e-3,
    "contact": {"ke": 1.0e3, "kd": 1.0e1, "mu": 0.7},
}


def cloth_fold_half_world(g: Dict[str, Any], table_z: float) -> Dict[str, Any]:
    lx, ly = (float(v) for v in g["cloth_size"])
    nx, ny = (int(v) for v in g["cloth_cells"])
    o = np.array([g["origin_xy"][0], g["origin_xy"][1], table_z + float(g["radius"]) + 0.0005])
    cl = 0.5 * lx  # the fixture holds the whole near half (the fold line is its far edge)
    c = g["contact"]
    return {
        "table": {"z": table_z, "half": [1.0, 1.0], "center": [0.0, 0.0], "mu": 0.7},
        "soft_contact": {"ke": float(c["ke"]), "kd": float(c["kd"]), "mu": float(c["mu"]), "gap": 0.005},
        "cloth": {
            "origin": o.tolist(),
            "size": [lx, ly],
            "cells": [nx, ny],
            "radius": float(g["radius"]),
            "density": float(g["density"]),
            "tri_ke": float(g["tri_ke"]),
            "tri_ka": float(g["tri_ka"]),
            "tri_kd": float(g["tri_kd"]),
            "edge_ke": float(g["edge_ke"]),
            "edge_kd": float(g["edge_kd"]),
            "pin_regions": [{"min": [o[0] - 0.001, o[1] - 0.001], "max": [o[0] + cl, o[1] + ly + 0.001]}],
            "color": [0.30, 0.55, 0.80],
        },
    }


# -- cloth_fold_half with a real pinch (the shipped variant) ----------------------------------------------------------
# The cloth lies on a pedestal ("shelf"); the near half is held down by a fixture (pinned particles, the fold line is the
# first pinned column) and the far half overhangs the pedestal edge, toward the robot.  The gel pads pinch the overhang's
# free edge, carry it over the fold line on a circle around it (the sheet cannot stretch) and let it land on the pinned
# half.  A stiff sheet holds the overhang up for the pinch; plastic bending (crease memory) keeps the crease after the release.
CLOTH_FOLD_PINCH: Dict[str, Any] = {
    "shelf": {
        "x_front": 0.10,
        "depth": 0.045,
        "half_y": 0.09,
        "height": 0.20,
    },  # short: the lower pad opens in free air behind the shelf
    "cloth_size": [0.12, 0.08],
    "cloth_cells": [12, 8],
    "overhang": 0.06,
    "center_y": 0.0,
    "radius": 0.0032,
    "attach_columns": 2,  # (the strip metric: the flap's free-edge columns)
    "density": 0.40,
    "tri_ke": 1.0e4,
    "tri_ka": 1.0e4,
    "tri_kd": 1.0e-1,
    "edge_ke": 30.0,  # holds the 6 cm overhang up for the pinch (the sag at the tip stays ~17 mm)
    "edge_kd": 1.0e-3,
    "bend_crease_angle": 0.8,  # rad: hinges folded sharper than this keep a crease
    "bend_plastic_rate": 1.0,
    "contact": {"ke": 1.0e3, "kd": 1.0e1, "mu": 0.8, "pad_mu": 1.0},
    "layout": {"yaw_deg": 90, "root_xy": [0.1, -0.15]},  # the whole layout turned about z (pinch_layout_xf)
    # policy numbers of the task
    "roll_release_deg": 120,
    "arc_segments": 8,
    "pinch_overlap": 0.00035,
}


def pinch_layout_xf(g: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
    """``(R, t)`` of the fold-pinch layout: world = R @ local + t.  The layout is authored in a local frame (fold line along +y at
    ``shelf.x_front``, the flap overhanging toward -x); ``g["layout"] = {"yaw_deg", "root_xy"}`` turns it about z by a multiple of
    90 deg and puts the middle of the fold line at ``root_xy``.  No ``layout``: the identity."""
    lay = g.get("layout") or {}
    yaw = float(lay.get("yaw_deg", 0.0))
    if abs(yaw / 90.0 - round(yaw / 90.0)) > 1e-9:
        raise ValueError(f"pinch layout yaw must be a multiple of 90 deg (axis-aligned pins / boxes), got {yaw}")
    c, s_ = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
    R = np.array([[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]])
    R[np.abs(R) < 1e-12] = 0.0
    if "root_xy" not in lay:
        return R, np.zeros(3)
    root_l = np.array([float(g["shelf"]["x_front"]), float(g["center_y"]), 0.0])
    return R, np.array([float(lay["root_xy"][0]), float(lay["root_xy"][1]), 0.0]) - R @ root_l


def _xf_box(R: np.ndarray, t: np.ndarray, centre, half) -> Tuple[List[float], List[float]]:
    """An axis-aligned box (centre, half) through the layout transform (90-deg multiples keep it axis-aligned: the halves swap)."""
    c = R @ np.asarray(centre, dtype=np.float64) + t
    h = np.abs(R) @ np.asarray(half, dtype=np.float64)
    return c.tolist(), h.tolist()


def cloth_fold_pinch_geometry(g: Dict[str, Any], table_z: float) -> Dict[str, Any]:
    s = g["shelf"]
    lx, ly = (float(v) for v in g["cloth_size"])
    r = float(g["radius"])
    shelf_top = table_z + float(s["height"])
    R, t = pinch_layout_xf(g)
    origin = np.array(
        [float(s["x_front"]) - float(g["overhang"]), float(g["center_y"]) - 0.5 * ly, shelf_top + r + 0.0005]
    )
    root = np.array([float(s["x_front"]), float(g["center_y"]), shelf_top + r])
    return {
        "shelf_top": shelf_top,
        "origin": R @ origin + t,
        "fold_x": float(s["x_front"]),
        "root": R @ root + t,
        "root_local": root,
        "yaw": float(np.arctan2(R[1, 0], R[0, 0])),
        "R": R,
        "t": t,
        "origin_local": origin,
    }


def cloth_fold_pinch_world(g: Dict[str, Any], table_z: float) -> Dict[str, Any]:
    s = g["shelf"]
    lx, ly = (float(v) for v in g["cloth_size"])
    nx, ny = (int(v) for v in g["cloth_cells"])
    geo = cloth_fold_pinch_geometry(g, table_z)
    o = geo[
        "origin_local"
    ]  # the pin region and the shelf are authored in the layout frame, then turned (pinch_layout_xf)
    R, t = geo["R"], geo["t"]
    h = float(s["height"])
    cx = float(s["x_front"]) + 0.5 * float(s["depth"])
    shelf_c, shelf_h = _xf_box(
        R, t, [cx, float(g["center_y"]), table_z + 0.5 * h], [0.5 * float(s["depth"]), float(s["half_y"]), 0.5 * h]
    )
    pin_c, pin_h = _xf_box(
        R, t,
        [0.5 * (geo["fold_x"] - 0.001 + o[0] + lx + 0.001), o[1] + 0.5 * ly, 0.0],
        [0.5 * (o[0] + lx + 0.001 - geo["fold_x"] + 0.001), 0.5 * ly + 0.001, 0.0],
    )  # fmt: skip
    c = g["contact"]
    return {
        "table": {"z": table_z, "half": [1.0, 1.0], "center": [0.0, 0.0]},
        "statics": [{"name": "shelf", "pos": shelf_c, "half": shelf_h, "mu": 0.5}],
        "soft_contact": {"ke": float(c["ke"]), "kd": float(c["kd"]), "mu": float(c["mu"]), "gap": 0.005},
        "cloth": {
            "origin": geo["origin"].tolist(),
            "yaw": geo["yaw"],
            "size": [lx, ly],
            "cells": [nx, ny],
            "radius": float(g["radius"]),
            "density": float(g["density"]),
            "tri_ke": float(g["tri_ke"]),
            "tri_ka": float(g["tri_ka"]),
            "tri_kd": float(g["tri_kd"]),
            "edge_ke": float(g["edge_ke"]),
            "edge_kd": float(g["edge_kd"]),
            "bend_crease_angle": float(g["bend_crease_angle"]),
            "bend_plastic_rate": float(g["bend_plastic_rate"]),
            # the fixture: every particle from the fold line (the shelf front edge) on
            "pin_regions": [
                {"min": [pin_c[0] - pin_h[0], pin_c[1] - pin_h[1]], "max": [pin_c[0] + pin_h[0], pin_c[1] + pin_h[1]]}
            ],
            "color": [0.30, 0.55, 0.80],
        },
    }


def cloth_fold_pinch_nominal_world(table_z: float = TABLE_Z) -> Dict[str, Any]:
    g = CLOTH_FOLD_PINCH
    return task_world(
        cloth_fold_pinch_world(g, table_z), gsmini_colliders(float(g["contact"]["pad_mu"])), table_z=table_z
    )


def fold_arc(
    root: np.ndarray,
    rel0: np.ndarray,
    phi1: float,
    a: float,
    hl: float = 0.0,
    margin: float = 0.97,
    margin_end: float = 1.0,
) -> np.ndarray:
    """Pad-centre position at fraction ``a`` (0..1) of the lift-and-carry arc around the fold line: a circle in the x-z plane about
    ``root`` of radius ``|rel0|`` (``rel0`` = the pinch centre relative to the root at the start), from the start angle to ``phi1``
    (measured from the -x axis, counter-clockwise over the top to +x).

    ``hl`` = half length of the pads along the approach axis.  The pads stay horizontal while the sheet turns over, and the sheet
    cannot stretch: the free sheet runs from the pad's end nearer the root, so the pad centre has to stay within
    ``R_max(phi) = hl |cos phi| + sqrt(L^2 - (hl sin phi)^2)`` of the root, ``L = R0 - hl`` (the free length at the start).  Long
    pads pull the tip out of the pinch on a plain circle; the radius is shrunk where needed (``margin`` x the limit, rising to
    ``margin_end`` at the landing so the tip lands where it should)."""
    R0 = float(np.hypot(rel0[0], rel0[2]))
    phi0 = float(np.arctan2(rel0[2], -rel0[0]))
    phi = phi0 + float(a) * (float(phi1) - phi0)
    R = R0
    if hl > 0.0:
        L = max(R0 - hl, 1e-3)
        R = min(
            R0,
            (margin + (margin_end - margin) * float(a) ** 3)
            * (hl * abs(np.cos(phi)) + np.sqrt(max(L * L - (hl * np.sin(phi)) ** 2, 0.0))),
        )
    return np.array([root[0] - R * np.cos(phi), root[1] + rel0[1], root[2] + R * np.sin(phi)])
