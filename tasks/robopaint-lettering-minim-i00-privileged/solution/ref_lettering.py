"""Reference writer for the RoboPaint lettering oracle (solution/ only; generation time, on the graders' full instance, whose truth
holds the exemplar's pen paths). Per stroke: a dip before the first stroke, travel 15 mm above the paper with the tool yawed to the
stroke's pen angle (broad nib: the edge along the tool's y axis, yaw 0 = the start pose = pen angle 0; pointed pen: the tines'
spread axis, the same convention), a vertical touch-down at the stroke's start, the path at 2 cm/s (pointed pen: slowed to 4 mm/s at the retrace cusps and to
at most 6 mm/s of press change), lift. Broad nib: a constant
press of 1 mm (a steel edge does not widen); pointed pen: the press depth of each point from the mark's width (the pen's
width_of inverted; hairlines at 0.7 mm, inside the unflexed range with more room above the paper: the arm overshoots upwards after a deep press). Tracking: IK(desired tip 0.125 s ahead) per control step and
three (pointed pen: five) passes of iterative learning control on the realized 100 Hz tip path (x, y and z); the arm parks at the end.
The keyword arguments only serve the perturbation study (a wrong or guessed pen angle, a shifted word, a constant or scaled press)."""
from __future__ import annotations
import math
import numpy as np

LAG_S, V_WRITE, V_TRAVEL, Z_TRAVEL, HZ, CTRL, PRESS_NIB, PRESS_HAIR, V_PRESS = 0.125, 0.02, 0.12, 0.015, 100, 20, 0.001, 0.0007, 0.006


class _TipLog:
    def __init__(self, painter):
        self.painter, self.orig, self.log = painter, painter.sample, []
        painter.sample = self._sample

    def _sample(self, p, R):
        self.log.append(np.asarray(p, np.float64).copy()); self.orig(p, R)

    def close(self):
        self.painter.sample = self.orig


def press_of_width(brush: dict, w_m: np.ndarray) -> np.ndarray:
    """Pointed pen: the press depth that writes width w (the inverse of PointedPenPainter.width_of)."""
    w0, w1, p0, p1 = (float(brush[k]) for k in ("hairline_m", "max_width_m", "flex_start_m", "full_flex_m"))
    w = np.asarray(w_m, np.float64)
    return np.where(w <= w0 + 1e-9, PRESS_HAIR, p0 + np.clip((w - w0) / (w1 - w0), 0, 1) * (p1 - p0))


def _slow_profile(P_world: np.ndarray, d: np.ndarray, press: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pointed pen: the writing speed along the path (m/s at each point): V_WRITE, slowed to 20 % within 2.5 mm of a sharp turn
    (> 60°: the retrace cusps) and so that the press changes at most V_PRESS (m/s)."""
    t = np.diff(P_world, axis=0); L = np.hypot(t[:, 0], t[:, 1]); ok = L > 1e-9
    u = np.zeros_like(t); u[ok] = t[ok] / L[ok, None]
    cosang = np.sum(u[1:] * u[:-1], axis=1)
    corners = d[1:-1][(cosang < 0.5) & ok[1:] & ok[:-1]]
    v = np.full(len(d), V_WRITE)
    for c in corners:
        v = np.minimum(v, V_WRITE * np.clip(np.abs(d - c) / 0.0025, 0.2, 1.0))
    dp = np.abs(np.gradient(press, d, edge_order=1)) if len(d) > 2 else np.zeros(len(d))
    v = np.minimum(v, np.where(dp > 1e-9, V_PRESS / np.maximum(dp, 1e-9), V_WRITE))
    return d, np.maximum(v, 0.2 * V_WRITE)


def segment(P_world: np.ndarray, paper_z: float, press: np.ndarray, step: float = V_WRITE / HZ, slow: bool = False) -> np.ndarray:
    """Desired tip samples at 100 Hz: vertical touch-down to the first press, the path at 2 cm/s with its press profile (pointed
    pen: slower at cusps and fast press changes), lift."""
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(P_world, axis=0).T))]
    if slow:
        dd, v = _slow_profile(P_world, d, press)
        s_list = [0.0]
        while s_list[-1] < d[-1]:
            s_list.append(min(d[-1], s_list[-1] + float(np.interp(s_list[-1], dd, v)) / HZ))
        s_ = np.asarray(s_list)
    else:
        n = max(2, int(math.ceil(d[-1] / step)) + 1)
        s_ = np.linspace(0, d[-1], n)
    xy = np.stack([np.interp(s_, d, P_world[:, 0]), np.interp(s_, d, P_world[:, 1])], 1)
    pr = np.interp(s_, d, press)
    above = 0.004
    n_v = int(round((above + pr[0]) / step))
    down = [np.r_[xy[0], paper_z + above - (above + pr[0]) * a] for a in np.linspace(0, 1, n_v + 1)]
    body = np.c_[xy, paper_z - pr]
    n_u = int(round((above + pr[-1]) / step))
    up = [np.r_[xy[-1], paper_z - pr[-1] + (above + pr[-1]) * a] for a in np.linspace(0, 1, n_u + 1)[1:]]
    return np.vstack([np.asarray(down), body, np.asarray(up)])


def paint(s, p, ilc_passes: int | None = None, verbose: bool = True, angle_offset_deg: float = 0.0, angle_abs_deg: float | None = None,
          shift_mm: tuple = (0.0, 0.0), press_const_mm: float | None = None, press_scale: float = 1.0) -> dict:
    t = s.inst.get("truth") or {}
    if not t.get("strokes"):
        raise ValueError("the reference writer needs the graders' full instance (with the exemplar's pen paths)")
    pointed = s.medium == "pointed_pen"
    if ilc_passes is None:
        ilc_passes = 5 if pointed else 3
    paper_z = s.geo.z
    well = s.wells()[0]
    D, Q = [], []
    for st in t["strokes"]:
        P = np.asarray(st["points_mm"], np.float64) + np.asarray(shift_mm, np.float64)
        x, y = s.geo.mm_to_world(P[:, 0], P[:, 1])
        ang = st["angle_deg"] + angle_offset_deg if angle_abs_deg is None else angle_abs_deg
        if pointed:
            pr = press_of_width(s.inst["brush"], np.asarray(st["widths_mm"], np.float64) / 1000.0)
            if press_const_mm is not None:
                pr = np.full_like(pr, press_const_mm / 1000.0)
            pr = np.maximum(PRESS_HAIR * 0.6, pr * press_scale)
        else:
            pr = np.full(len(P), PRESS_NIB)
        D.append(segment(np.stack([x, y], 1), paper_z, pr, slow=pointed)); Q.append(s.tip_down_quat(math.radians(ang)))
    corr = [np.zeros_like(d) for d in D]
    recording = s._recording is not None
    hist = []
    for it in range(ilc_passes + 1):
        final = it == ilc_passes
        if it > 0:
            s.reset()
        if final and recording:
            s._recording = []
        logs = []
        (wx, wy), wz = well["center_xy"], well["surface_z"]
        p["move_tip"]([wx, wy, wz + 0.015], speed=V_TRAVEL)
        p["move_tip"]([wx, wy, wz - 0.003], speed=0.03, settle=3)
        p["move_tip"]([wx, wy, wz + 0.015], speed=0.04)
        for k, (d, q) in enumerate(zip(D, Q)):
            x0 = d[0]
            p["move_tip"]([x0[0], x0[1], paper_z + Z_TRAVEL], q, speed=V_TRAVEL)
            p["move_tip"](x0, q, speed=0.03, settle=12)
            tl = _TipLog(s.painter)
            C = d + corr[k]
            n_ctrl = int(math.ceil(len(d) / (HZ / CTRL)))
            for j in range(1, n_ctrl + 1):
                i = min(len(C) - 1, int(round(j * (HZ / CTRL) + LAG_S * HZ)))
                qj, ok, _ = s.ik(C[i], q)
                s.step(qj if ok else s.hold_action())
            for _ in range(10):
                s.step(s.hold_action())
            tl.close()
            logs.append(np.asarray(tl.log))
        errs = []
        for k, d in enumerate(D):
            R = logs[k]; n = min(len(R), len(d)); e = d[:n] - R[:n]
            errs.append(float(np.percentile(np.linalg.norm(e[:, :2], axis=1), 95)) * 1000)
            if not final:
                corr[k][:n] += e
        hist.append({"pass": it, "p95_xy_err_mm_per_stroke": [round(v, 3) for v in errs]})
        if verbose:
            print("ILC pass", it, "p95 tracking error (mm):", [round(v, 3) for v in errs], flush=True)
    p["move_tip"]([s.geo.center[0], s.geo.center[1] + 0.25, paper_z + 0.16], speed=0.15, settle=10)
    return {"strokes": len(D), "ilc": hist}
