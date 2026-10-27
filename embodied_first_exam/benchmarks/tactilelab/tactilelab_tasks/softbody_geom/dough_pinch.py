"""Direct-sensor dough tasks (pure numpy): the two gel pads of the gripper ARE the MPM colliders, no tool in between.

Geometry facts the designs follow:

* the gel pad is a thin box (``PAD_HALF``: 21 mm vertical, 16 mm along the ridge, 4 mm along the closing axis) on the inner face of
  each finger; the fully closed pads leave ~6.5 mm between the faces (the binary gripper closes fully or not at all), so the thickness
  of a pinched dough strip is set by the hardware, not by a commanded opening;
* the gel centre cannot go below ~21 mm above the plate (fingertip reach), so the gel covers z in [10.5, 31.5] mm: the dough ridge is
  tall enough (``ridge_h``) for the gel to reach its pinch band.

``make_pinch_scene`` is ``dough_press_thickness`` / ``dough_target_shape`` (direct): a dough ridge stands on the plate along y; the
pads straddle it with the closing axis along x, close, release, step along the ridge (the pinch-walk), and withdraw.
``pinch_report`` judges the pinched zone: thickness (x-width inside the pinch band), flatness along the ridge, little dough outside
the workspace.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import dough_metrics as dm
from . import dough_scene as ds
from .dough_task import DoughScene, plate_box

# gel pad box (half extents in the PAD frame: x vertical, y along the ridge, z = the closing axis) of the X-Trainer fingers
PAD_HALF = (0.0105, 0.008, 0.002)
PAD_MU = 1.0
GEL_CENTER_MIN_Z = 0.021  # gel centre above the plate when the fingertips touch it
CLOSED_FACE_GAP = 0.0065  # between the two gel faces with the gripper fully closed
OPEN_GAP = 0.106  # pad centre to pad centre, open
CLOSED_GAP = 0.0105  # pad centre to pad centre, closed


PAD_BACK = 0.016  # the MPM collider box extends this far BEHIND the gel face (the finger body is there): a 4 mm plate is thinner than 2 grid cells and leaks dough
PAD_MARGIN = 0.001  # collider margin of the pads [m]: ~ the particle radius (a 3 mm margin would leave 0.5 mm between closed faces)


def pad_tools(half=PAD_HALF, mu: float = PAD_MU, back: float = PAD_BACK, margin: float = PAD_MARGIN) -> List[dict]:
    """The two pads as kinematic MPM tools (dough world cfg ``tools``); their poses (T = 2, 7) come from the robot each step.  The pad
    frame's z points at the other pad and the gel face is at z = +half[2]: the box covers z in [half[2] - 2 hz, half[2]] with
    hz = (half[2] + back) / 2, i.e. the gel face stays where it is and the box is thicker on the far side."""
    hx, hy, hz0 = (float(h) for h in half)
    hz = 0.5 * (hz0 + float(back))
    # box spans z in [hz0 - 2 hz, hz0] -> centre at hz0 - hz
    return [
        {
            "name": n,
            "mu": float(mu),
            "margin": float(margin),
            "shapes": [{"type": "box", "half": [hx, hy, hz], "offset": [0.0, 0.0, hz0 - hz]}],
        }
        for n in ("pad_left", "pad_right")
    ]


# pad frame at heading 0 as world columns: x_p = -z (vertical), y_p = -x (along the ridge), z_p = +y (the closing axis); right-handed
_R_PAD0 = np.column_stack([[0.0, 0.0, -1.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])


def mat_to_quat(R: np.ndarray) -> np.ndarray:
    """xyzw quaternion of a rotation matrix."""
    t = np.trace(R)
    if t > 0:
        s = 0.5 / np.sqrt(t + 1.0)
        return np.array([(R[2, 1] - R[1, 2]) * s, (R[0, 2] - R[2, 0]) * s, (R[1, 0] - R[0, 1]) * s, 0.25 / s])
    i = int(np.argmax(np.diag(R)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = 2.0 * np.sqrt(1.0 + R[i, i] - R[j, j] - R[k, k])
    q = np.zeros(4)
    q[i] = 0.25 * s
    q[j] = (R[j, i] + R[i, j]) / s
    q[k] = (R[k, i] + R[i, k]) / s
    q[3] = (R[k, j] - R[j, k]) / s
    return q


def pad_pose(mid, heading: float, gap: float) -> np.ndarray:
    """Both pad poses ((2, 7): x y z qx qy qz qw) for the pad-pair centre ``mid``, closing-axis direction ``heading`` [rad, about +z;
    0 = closing along +y] and centre-to-centre pad distance ``gap``.  Pad 0 sits on the -n side, pad 1 on the +n side (n = the closing
    axis); pad 1's frame is pad 0's turned 180 deg about its own x (both z axes point at each other)."""
    c, s = np.cos(heading), np.sin(heading)
    Rz = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    R0 = Rz @ _R_PAD0
    n = R0[:, 2]
    out = np.zeros((2, 7))
    for k, (R, sgn) in enumerate(((R0, -1.0), (R0 @ np.diag([1.0, -1.0, -1.0]), 1.0))):
        out[k, :3] = np.asarray(mid, float) + sgn * 0.5 * gap * n
        out[k, 3:7] = mat_to_quat(R)
    return out


def make_pinch_scene(p: dict, anchor, rng: Optional[np.random.Generator] = None) -> DoughScene:
    """``dough_press_thickness`` (direct): a dough ridge (``ridge_w`` x ``ridge_len`` x ``ridge_h``) along y on the plate.  With
    ``slots`` (``dough_target_shape``) the episode pinches ``n_targets`` of the slots and the others must stay thick."""
    rng = np.random.default_rng(0) if rng is None else rng
    voxel = float(p.get("voxel", 0.003))
    w, L, H = float(p.get("ridge_w", 0.018)), float(p.get("ridge_len", 0.07)), float(p.get("ridge_h", 0.026))
    jit = float(p.get("center_jitter", 0.0))
    c = np.asarray(p.get("blob_center", [0.0, 0.0]), float) + rng.uniform(-jit, jit, size=2)
    blob = {"type": "box", "center": [c[0], c[1], float(p.get("blob_z0", 0.0003))], "size": [w, L, H]}
    pts, pvol = ds.blob_points(blob, voxel, int(p.get("ppc", 2)), int(rng.integers(1 << 30)))
    boxes = [plate_box(p.get("plate_half", [0.12, 0.12]))]
    th = float(
        p.get("trough_h", 0.0)
    )  # a shallow trough (two low rails) holds the base of the ridge: a pad that arrives early must not slide / topple it
    if th > 0.0:
        tt = float(p.get("trough_t", 0.004))
        for sgn in (-1.0, 1.0):
            boxes.append(
                {
                    "center": [c[0] + sgn * (0.5 * w + 0.5 * tt + 0.0005), c[1], 0.5 * th],
                    "half": [0.5 * tt, 0.5 * L + 0.005, 0.5 * th],
                    "mu": 0.6,
                }
            )
    cfg = {
        "material": p.get("material", "dough"),
        "voxel": voxel,
        "dt": float(p.get("dt", 1.0 / 30.0)),
        "substeps": int(p.get("substeps", 1)),
        "iterations": int(p.get("iterations", 60)),
        "collider_margin": float(p.get("collider_margin", voxel)),
        "boxes": boxes,
        "tools": pad_tools(tuple(p.get("pad_half", PAD_HALF)), float(p.get("pad_mu", PAD_MU))),
        "bounds": p.get("bounds", [[-0.1, -0.1, -0.02], [0.1, 0.1, 0.09]]),
        "ground": False,
    }
    grid = dm.HeightGrid(lo=(-0.1, -0.1), nx=50, ny=50, dx=0.004, z0=0.0)
    extra = {}
    slots = [float(v) for v in p.get("slots", [])]
    if slots:  # sculpt: this episode pinches a subset of the slots (the target pattern); the others must stay thick
        k = int(p.get("n_targets", 2))
        pick = sorted(int(i) for i in rng.choice(len(slots), size=min(k, len(slots)), replace=False))
        extra = {
            "pinch_offsets": [slots[i] for i in pick],
            "keep_offsets": [slots[i] for i in range(len(slots)) if i not in pick],
        }
    return DoughScene(
        kind="pinch",
        world_cfg=cfg,
        points=pts,
        pvol=pvol,
        anchor=np.asarray(anchor, float),
        grid=grid,
        masks={},
        info={
            "ridge_cx": float(c[0]),
            "ridge_cy": float(c[1]),
            "ridge_w": w,
            "ridge_len": L,
            "ridge_h": H,
            "volume": len(pts) * pvol,
        },
        extra=extra,
    )


@dataclass
class PinchReport:
    thickness_mean: float  # mean x-width of the dough in the pinch band over the pinched zone [m]
    flatness: float  # max - min of the bin widths over the pinched zone [m]
    outside_frac: float
    n_bins: int
    n_empty: int
    ok: bool
    why: str


def pinch_widths(
    q: np.ndarray,
    spacing: float,
    cy: float,
    y_lo: float,
    y_hi: float,
    band: Tuple[float, float],
    bin_len: float = 0.004,
    cx: float = 0.0,
    half_x: float = 0.03,
):
    """Per y-bin width [m] (x extent of the particles with z in ``band`` within ``half_x`` of the ridge axis; robust 2-98 percentile + one
    particle spacing) over ``[cy + y_lo, cy + y_hi]``; NaN for an empty bin."""
    edges = np.arange(cy + y_lo, cy + y_hi + 0.5 * bin_len, bin_len)
    out = np.full(len(edges) - 1, np.nan)
    sel = (q[:, 2] >= band[0]) & (q[:, 2] <= band[1]) & (np.abs(q[:, 0] - cx) <= half_x)
    for i in range(len(edges) - 1):
        m = sel & (q[:, 1] >= edges[i]) & (q[:, 1] < edges[i + 1])
        if m.sum() >= 5:
            x = q[m, 0]
            out[i] = float(np.percentile(x, 98) - np.percentile(x, 2)) + spacing
    return out


def pinch_report(
    q: np.ndarray,
    pvol: float,
    scene_info: Dict[str, float],
    centers: Sequence[float] = (-0.018, 0.018),
    half_len: float = 0.008,
    target_thickness: float = 0.0075,
    thickness_tol: float = 0.0015,
    flatness_tol: float = 0.0025,
    band: Tuple[float, float] = (0.013, 0.021),
    workspace_radius: float = 0.09,
    outside_tol: float = 0.03,
    keep_centers: Sequence[float] = (),
    keep_min: float = 0.014,
) -> PinchReport:
    """Judge the pinched zones (``centers``: y offsets from the ridge centre, each ``+- half_len``): mean x-width of the dough in ``band``
    must match the target, the widths of the bins must be flat, nothing may be missing, little dough outside the workspace."""
    spacing = float(pvol) ** (1.0 / 3.0)
    cy = float(scene_info.get("ridge_cy", 0.0))
    cx = float(scene_info.get("ridge_cx", 0.0))
    widths = (
        np.concatenate([pinch_widths(q, spacing, cy + float(c), -half_len, half_len, band, cx=cx) for c in centers])
        if len(centers)
        else np.zeros(0)
    )
    n_empty = int(np.isnan(widths).sum())
    d = np.hypot(q[:, 0], q[:, 1])
    outside = float((d > workspace_radius).mean()) if len(q) else 1.0
    if n_empty or not len(widths):
        return PinchReport(
            float("nan"),
            float("nan"),
            outside,
            len(widths),
            n_empty,
            False,
            f"{n_empty} of {len(widths)} bins of the pinched zones are empty",
        )
    mean = float(np.mean(widths))
    flat = float(widths.max() - widths.min())
    reasons = []
    if len(
        keep_centers
    ):  # sculpt: the zones that were NOT to be pinched must still be thick (the pattern, not just thin everywhere)
        kw = np.concatenate(
            [pinch_widths(q, spacing, cy + float(c), -half_len, half_len, band, cx=cx) for c in keep_centers]
        )
        kw = kw[np.isfinite(kw)]
        if len(kw) == 0 or float(np.mean(kw)) < keep_min:
            reasons.append(
                f"an untouched slot is not kept thick ({1e3 * float(np.mean(kw)) if len(kw) else 0:.1f} mm < {1e3 * keep_min:.0f})"
            )
    if abs(mean - target_thickness) > thickness_tol:
        reasons.append(
            f"thickness {1e3 * mean:.1f} mm vs target {1e3 * target_thickness:.1f} +- {1e3 * thickness_tol:.1f}"
        )
    if flat > flatness_tol:
        reasons.append(f"flatness {1e3 * flat:.1f} mm > {1e3 * flatness_tol:.1f}")
    if outside > outside_tol:
        reasons.append(f"{100 * outside:.1f}% of the dough outside the workspace")
    return PinchReport(mean, flat, outside, len(widths), 0, not reasons, "; ".join(reasons) or "ok")


# -- fill, DIRECT: straddle-push with the trailing gel pad ------------------------------------------------------------
def make_fill_push_scene(p: dict, anchor, rng: Optional[np.random.Generator] = None) -> DoughScene:
    """``dough_fill_tray`` (direct): a short open-backed tray (floor, front wall, two side walls; NO back wall: pad 0 stands behind the
    heap) with a tall heap against its back; the open hand straddles the heap (closing axis along +x), pad 0 (trailing, gel face looking
    along +x) pushes the dough toward the front wall while pad 1 stays 106 mm ahead, outside the tray (the tray is shorter than the open
    jaws).  The gel centre cannot go below 21 mm (fingertip reach): the heap is tall (24 mm) and the target level >= ~12 mm."""
    from . import dough_task as dt

    q = dict(p)
    q["side"] = -1.0  # heap on the -x side, pushed toward +x
    q.setdefault(
        "tray_inner", [0.094, 0.06]
    )  # inner length < the open jaws (106 mm): pad 1 starts outside the front wall
    q.setdefault("init_frac", 0.6)
    q.setdefault("blob_height", 0.024)
    q.setdefault("wall_h", 0.03)
    sc = dt.make_fill_scene(q, anchor, rng)
    inner = np.asarray(q["tray_inner"], float)
    wt = float(q.get("wall_t", 0.006))
    back_x = -(0.5 * inner[0] + 0.5 * wt)
    boxes = [
        b
        for b in sc.world_cfg["boxes"]
        if not (abs(b["center"][0] - back_x) < 1e-6 and b["half"][2] > 0.5 * float(q["wall_h"]) - 1e-6)
    ]
    assert len(boxes) == len(sc.world_cfg["boxes"]) - 1, "back wall not found"
    sc.world_cfg["boxes"] = boxes
    sc.world_cfg["tools"] = pad_tools(tuple(q.get("pad_half", PAD_HALF)), float(q.get("pad_mu", PAD_MU)))
    sc.world_cfg["bounds"] = q.get(
        "bounds",
        [[-0.5 * inner[0] - 0.03, -0.5 * inner[1] - 0.03, -0.02], [0.5 * inner[0] + 0.03, 0.5 * inner[1] + 0.03, 0.09]],
    )
    sc.kind = "fill_push"
    sc.info["back_x"] = -0.5 * float(inner[0])
    sc.info["front_x"] = 0.5 * float(inner[0])
    return sc


def grid_box_mesh(center, n_axis, y_axis, z_axis, size, cell=0.002):
    """The boundary of a regular node grid filling the same box as :func:`box_mesh` (``cell`` edge, like the FEM plug's surface):
    ``(V, 3)`` vertices, ``(F, 3)`` outward triangles."""
    from . import plug_scene as ps

    dims = tuple(max(1, int(round(float(sz) / float(cell)))) for sz in size)
    ax = [np.asarray(a, float) for a in (n_axis, y_axis, z_axis)]
    c = np.asarray(center, float)
    g = np.stack(
        np.meshgrid(*[np.linspace(-0.5, 0.5, n + 1) * float(sz) for n, sz in zip(dims, size)], indexing="ij"), axis=-1
    )  # (nx+1, ny+1, nz+1, 3)
    # plug_scene's node order: i + (nx + 1) * (j + (ny + 1) * k)  ->  x fastest
    nodes = np.transpose(g, (2, 1, 0, 3)).reshape(-1, 3)
    v = (c + nodes[:, 0:1] * ax[0] + nodes[:, 1:2] * ax[1] + nodes[:, 2:3] * ax[2]).astype(np.float32)
    f = ps.grid_surface_tris(dims)
    if (
        float(np.dot(np.cross(ax[0], ax[1]), ax[2])) < 0.0
    ):  # a left-handed pad frame mirrors the grid: restore the outward winding
        f = f[:, ::-1].copy()
    return v, f


def box_mesh(center, n_axis, y_axis, z_axis, size):
    """A closed box (8 vertices, 12 outward triangles) centred at ``center`` with edge vectors ``n_axis`` (thickness size[0]),
    ``y_axis`` (size[1]), ``z_axis`` (size[2])."""
    c = np.asarray(center, float)
    ax = [np.asarray(a, float) * 0.5 * float(sz) for a, sz in zip((n_axis, y_axis, z_axis), size)]
    v = np.array(
        [c + sx * ax[0] + sy * ax[1] + sz * ax[2] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], np.float32
    )
    f = np.array(
        [
            [0, 1, 3],
            [0, 3, 2],
            [4, 6, 7],
            [4, 7, 5],
            [0, 4, 5],
            [0, 5, 1],
            [2, 3, 7],
            [2, 7, 6],
            [0, 2, 6],
            [0, 6, 4],
            [1, 5, 7],
            [1, 7, 3],
        ],
        np.int32,
    )
    # orient every triangle outward
    for i, t in enumerate(f):
        nrm = np.cross(v[t[1]] - v[t[0]], v[t[2]] - v[t[0]])
        if float(nrm @ (v[t].mean(0) - c)) < 0.0:
            f[i] = t[::-1]
    return v, f
