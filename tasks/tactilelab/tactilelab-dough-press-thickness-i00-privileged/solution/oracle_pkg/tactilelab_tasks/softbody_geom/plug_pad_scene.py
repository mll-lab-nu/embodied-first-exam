"""Scene of ``fem_plug_insert`` DIRECT (pure numpy): the two gel pads pinch a compliant FEM plug themselves, no carrier.

Frames: env-local metres, z up; the plate top is z = 0.  The plate has two square-ish holes along x: a loose PICK socket (the plug
stands in it, 10 mm deep) and the press-fit TARGET hole (``interference`` mm tighter than the plug).  Geometry facts: the gel
centre cannot go below ~21 mm above the surface (fingertip reach) and the closed pads leave ~6.5 mm between the faces: the plug is
8 mm wide along the closing axis (x) - 1.5 mm of squeeze - and 12 mm along the gel (y); the pads grip the plug 3 mm below its top
(pad centre = surface + 21 mm both when picking and when seating, because the plug is 34 mm long and both holes are 10 mm deep):
the fingertips just clear the plate / rim at both ends.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional

import numpy as np

from . import dough_metrics as dm
from . import plug_scene as ps
from .dough_task import DoughScene

PICK_X = -0.03
TARGET_X = 0.03
GRIP_BELOW_TOP = 0.003  # pad centre below the plug's top face while carrying [m]


def specs_from_params(p: dict) -> Dict[str, ps.PlugSpec]:
    """``{"plug": spec of the plug itself (hole = the target hole), "pick": spec with the loose socket}``."""
    size = tuple(float(v) for v in p.get("plug_size", (0.008, 0.012, 0.034)))
    radius = float(p.get("particle_radius", 0.0005))
    interference = float(p.get("interference", 0.0008))
    base = ps.PlugSpec(
        size=size,
        cell=float(p.get("cell", 0.002)),
        density=float(p.get("density", 1100.0)),
        k_mu=float(p.get("k_mu", 2.0e5)),
        k_lambda=float(p.get("k_lambda", 6.0e5)),
        k_damp=float(p.get("k_damp", 1.0e-3)),
        hole=(size[0] - interference + 2 * radius, size[1] - interference + 2 * radius),
        hole_depth=float(p.get("hole_depth", 0.010)),
        wall=float(p.get("wall", 0.03)),
        floor=float(p.get("floor", 0.010)),
        grip_band=0.0,
        mu=float(p.get("plug_mu", 0.2)),
    )
    loose = float(p.get("socket_play", 0.0004))
    pick = replace(base, hole=(size[0] + 2 * loose + 2 * radius, size[1] + 2 * loose + 2 * radius))
    return {"plug": base, "pick": pick}


def make_plug_pad_scene(p: dict, anchor, rng: Optional[np.random.Generator] = None) -> DoughScene:
    """The plug standing in the pick socket (anchored frame: plate top z = 0), the target hole ``TARGET_X - PICK_X`` further along x."""
    from . import dough_pinch as dp

    rng = np.random.default_rng(0) if rng is None else rng
    specs = specs_from_params(p)
    sp = specs["plug"]
    jit = float(p.get("hole_jitter", 0.0))
    off = rng.uniform(-jit, jit, size=2) if jit > 0 else np.zeros(2)
    pick_xy = np.array([float(p.get("pick_x", PICK_X)), 0.0])
    tgt_xy = np.array([float(p.get("target_x", TARGET_X)), 0.0]) + off
    pts = ps.plug_particle_grid(sp, tuple(pick_xy), -sp.hole_depth + 0.0003)  # standing on the socket floor
    half = tuple(p.get("pad_half", dp.PAD_HALF))
    cfg = {
        "plug": {
            "size": list(sp.size),
            "cell": sp.cell,
            "density": sp.density,
            "k_mu": sp.k_mu,
            "k_lambda": sp.k_lambda,
            "k_damp": sp.k_damp,
            "hole": list(sp.hole),
            "hole_depth": sp.hole_depth,
            "wall": sp.wall,
            "floor": sp.floor,
            "grip_band": 0.0,
            "mu": sp.mu,
        },  # fmt: skip
        "pick": {"hole": list(specs["pick"].hole)},
        "pick_xy": pick_xy.tolist(),
        "hole_xy": tgt_xy.tolist(),
        "top_z": 0.0,
        "fps": int(p.get("fps", 30)),
        "substeps": int(p.get("substeps", 10)),
        "iterations": int(p.get("iterations", 5)),
        "contact_gap": float(p.get("contact_gap", 0.002)),
        "particle_radius": float(p.get("particle_radius", 0.0005)),
        "plate_mu": float(p.get("plate_mu", 0.2)),
        "lead_in": float(p.get("lead_in", 0.0)),
        "contact_ke": float(p.get("contact_ke", 2.0e6)),
        "pads": {
            "half": list(half),
            "back": float(p.get("pad_back", 0.016)),
            "mu": float(p.get("pad_mu", 2.0)),
        },  # shape mu 2.0 + soft_contact_mu 0.2 -> ~1.1 at the pads
    }
    grid = dm.HeightGrid(lo=(-0.05, -0.05), nx=25, ny=25, dx=0.004, z0=0.0)
    return DoughScene(
        kind="plug_pads",
        world_cfg=cfg,
        points=pts,
        pvol=float(np.prod(sp.size) / max(len(pts), 1)),
        anchor=np.asarray(anchor, float),
        grid=grid,
        masks={},
        info={
            "interference": sp.interference,
            "hole_depth": sp.hole_depth,
            "hole_x": float(tgt_xy[0]),
            "hole_y": float(tgt_xy[1]),
            "pick_x": float(pick_xy[0]),
            "pick_y": float(pick_xy[1]),
            "plug_len": float(sp.size[2]),
        },
        extra={"spec": sp, "pick_spec": specs["pick"]},
    )


@dataclass
class PlugPadReport:
    depth: float
    seated_frac: float
    width_x: float
    compression: float
    tilt_deg: float
    off_mm: float
    ok: bool
    why: str


def plug_pad_report(
    q: np.ndarray,
    spec: ps.PlugSpec,
    hole_xy,
    top_z: float = 0.0,
    seated_min: float = 0.85,
    compression_range=(0.02, 0.30),
    tilt_max_deg: float = 6.0,
    xy_tol: float = 0.004,
) -> PlugPadReport:
    """Seated depth + press-fit squeeze + tilt + centring of the plug (particles ``q`` (P, 3)) once the pads are away (nothing is held)."""
    zmin = float(q[:, 2].min())
    depth = top_z - zmin
    seated = depth / spec.hole_depth
    inside = q[:, 2] < top_z - 1e-4
    wx = float(np.ptp(q[inside, 0])) if inside.sum() >= 8 else float(spec.size[0])
    comp = 1.0 - wx / float(spec.size[0])
    low = q[q[:, 2] < zmin + 0.004]
    high = q[q[:, 2] > q[:, 2].max() - 0.004]
    axis = high.mean(0) - low.mean(0)
    tilt = float(np.degrees(np.arccos(np.clip(axis[2] / max(np.linalg.norm(axis), 1e-9), -1, 1))))
    off = float(np.hypot(*(low.mean(0)[:2] - np.asarray(hole_xy, float))))
    why = []
    if seated < seated_min:
        why.append(f"seated {seated:.2f} < {seated_min:.2f}")
    if not (compression_range[0] <= comp <= compression_range[1]):
        why.append(f"compression {comp:.3f} outside {compression_range}")
    if tilt > tilt_max_deg:
        why.append(f"tilt {tilt:.1f} deg > {tilt_max_deg}")
    if off > xy_tol:
        why.append(f"{1e3 * off:.1f} mm off the hole axis")
    return PlugPadReport(depth, seated, wx, comp, tilt, 1e3 * off, not why, "; ".join(why) or "ok")


def plug_pad_script(plan: Dict, p: Dict) -> List[Dict]:
    """Pick the plug from the socket with the gel pads, carry it, seat it in the target hole, release, withdraw (pad-pair frame:
    ``xyz`` = centre between the pads, ``yaw`` = closing axis; -pi/2 = along +x).  Pad centre = surface + ``grip_h`` (21 mm: the
    fingertips clear the plate / rim) at both the pick and the seat."""
    anc = np.asarray(plan["anchor"], float)
    z0 = float(anc[2])
    grip_h = float(p.get("grip_h", 0.021)) + float(p.get("grip_bias", 0.001))
    hover = z0 + float(p.get("hover", 0.07))
    lift = z0 + float(p.get("lift_h", 0.06))
    yaw = float(p.get("closing_yaw", -0.5 * np.pi))
    px, py = anc[0] + float(plan["pick_x"]), anc[1] + float(plan["pick_y"])
    tx, ty = anc[0] + float(plan["hole_x"]), anc[1] + float(plan["hole_y"])
    seat = float(
        p.get("seat_z", 0.0)
    )  # extra push below the grip height (0: the plug bottom reaches the socket floor at grip_h)
    return [
        {"op": "open", "label": "open"},
        {"op": "move", "xyz": [px, py, hover], "yaw": yaw, "label": "hover_pick"},
        {"op": "move", "xyz": [px, py, z0 + grip_h], "yaw": yaw, "label": "descend_pick"},
        {"op": "close", "label": "pinch"},
        {"op": "wait", "ticks": int(p.get("hold_ticks", 20)), "label": "grip"},
        {"op": "move", "xyz": [px, py, lift], "yaw": yaw, "label": "lift"},
        {"op": "move", "xyz": [tx, ty, lift], "yaw": yaw, "label": "carry"},
        {"op": "move", "xyz": [tx, ty, z0 + grip_h + 0.012], "yaw": yaw, "label": "approach"},
        {"op": "move", "xyz": [tx, ty, z0 + grip_h - seat], "yaw": yaw, "label": "insert"},
        {"op": "wait", "ticks": int(p.get("dwell_ticks", 15)), "label": "dwell"},
        {"op": "open", "label": "release"},
        {"op": "move", "xyz": [tx, ty, hover], "yaw": yaw, "label": "retreat"},
    ]
