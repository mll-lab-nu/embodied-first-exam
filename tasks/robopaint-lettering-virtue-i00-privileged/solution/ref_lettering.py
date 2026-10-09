"""Reference writer for the RoboPaint lettering oracle (solution/ only; generation time). solution/plans.json holds the exemplar's
contacts, one writing route each: the route on the main sheet (sheet mm) with the tines' spread per point, and the pen's spread
axis; they come from the exemplar file that scripts/robopaint_lettering/lt_exemplar.py made from the scan (a connected piece of the
exemplar's ink = one contact; its route runs once over every part of it and twice over the parts it has to go back along).
The pointed pen is turned to the spread axis for the whole word; one dip; per contact: travel 15 mm above the paper, a vertical
touch-down at the route's start, a pause of 0.2 s at the press, the route at 5 mm/s (slowed to 1 mm/s around sharp turns and turn-backs and to at most 6 mm/s of
press change), the press depth of each point from the spread (the inverse of PointedPenPainter.width_of; hairlines at 0.8 mm,
inside the unflexed range), a pause of 0.2 s, a vertical lift. Tracking: IK(desired tip 0.125 s ahead) per control step and eight passes of iterative
learning control on the realized 100 Hz tip path (x, y and z; the update smoothed, gain 0.7, vertical corrections within 0.5 mm);
the recorded pass uses the corrections of the best pass (every contact one stroke, the smallest tracking error); the arm parks at
the end."""
from __future__ import annotations
import math
import numpy as np

LAG_S, V_WRITE, V_TRAVEL, Z_TRAVEL, HZ, CTRL, PRESS_HAIR, V_PRESS = 0.125, 0.005, 0.12, 0.015, 100, 20, 0.0008, 0.006
DWELL_S = 0.2                                                      # the pause at the press at a route's start and end
ILC_PASSES, ILC_GAIN, ILC_SIGMA, ILC_ZCAP = 8, 0.7, 3.0, 0.0005   # passes; learning gain; the error's zero-phase smoothing (100 Hz
                                                                   # samples); the largest vertical correction (m)


class _TipLog:
    def __init__(self, painter):
        self.painter, self.orig, self.log = painter, painter.sample, []
        painter.sample = self._sample

    def _sample(self, p, R):
        self.log.append(np.asarray(p, np.float64).copy()); self.orig(p, R)

    def close(self):
        self.painter.sample = self.orig


def press_of_width(brush: dict, w_m: np.ndarray) -> np.ndarray:
    """The press depth that opens the tines to w (the inverse of PointedPenPainter.width_of); a hairline at PRESS_HAIR."""
    w0, w1, p0, p1 = (float(brush[k]) for k in ("hairline_m", "max_width_m", "flex_start_m", "full_flex_m"))
    w = np.asarray(w_m, np.float64)
    return np.where(w <= w0 + 1e-9, PRESS_HAIR, p0 + np.clip((w - w0) / (w1 - w0), 0, 1) * (p1 - p0))


def _speeds(P: np.ndarray, d: np.ndarray, press: np.ndarray) -> np.ndarray:
    """The writing speed at each point (m/s): V_WRITE, slowed to 20 % within 2.5 mm of a sharp turn (> 60°) and so that the press
    changes at most V_PRESS (m/s)."""
    t = np.diff(P, axis=0); L = np.hypot(t[:, 0], t[:, 1]); ok = L > 1e-9
    u = np.zeros_like(t); u[ok] = t[ok] / L[ok, None]
    v = np.full(len(d), V_WRITE)
    if len(P) > 6:
        k = 5                                                     # turn measured over +-5 points (~0.5 mm): pixel-scale wiggles do not count
        a = P[2 * k:] - P[k:-k]; b = P[k:-k] - P[:-2 * k]
        na, nb = np.hypot(*a.T), np.hypot(*b.T)
        good = (na > 1e-9) & (nb > 1e-9)
        cosang = np.where(good, np.sum(a * b, 1) / np.maximum(na * nb, 1e-18), 1.0)
        for c in d[k:-k][cosang < 0.5]:
            v = np.minimum(v, V_WRITE * np.clip(np.abs(d - c) / 0.0025, 0.2, 1.0))
    dp = np.abs(np.gradient(press, d, edge_order=1)) if len(d) > 2 and d[-1] > 0 else np.zeros(len(d))
    v = np.minimum(v, np.where(dp > 1e-9, V_PRESS / np.maximum(dp, 1e-9), V_WRITE))
    return np.maximum(v, 0.2 * V_WRITE)


def segment(P_world: np.ndarray, paper_z: float, press: np.ndarray) -> np.ndarray:
    """Desired tip samples at 100 Hz: a vertical touch-down to the first press, the route with its press profile, a vertical lift."""
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(P_world, axis=0).T))]
    if d[-1] > 1e-4:                                              # resampled every 0.1 mm (the route file keeps few points on straight runs)
        s0 = np.linspace(0, d[-1], int(math.ceil(d[-1] / 1e-4)) + 1)
        P_world = np.stack([np.interp(s0, d, P_world[:, 0]), np.interp(s0, d, P_world[:, 1])], 1)
        press = np.interp(s0, d, press); d = s0
    if d[-1] > 1e-9:
        v = _speeds(P_world, d, press)
        s_list = [0.0]
        while s_list[-1] < d[-1]:
            s_list.append(min(d[-1], s_list[-1] + float(np.interp(s_list[-1], d, v)) / HZ))
        s_ = np.asarray(s_list)
        xy = np.stack([np.interp(s_, d, P_world[:, 0]), np.interp(s_, d, P_world[:, 1])], 1)
        pr = np.interp(s_, d, press)
    else:                                                         # a single point: press there
        xy = P_world[:1].copy(); pr = np.full(1, float(np.max(press)))
    dwell = int(round(DWELL_S * HZ))                             # the pen settles at the press at both ends (a dot is all ends)
    xy = np.vstack([np.repeat(xy[:1], dwell, axis=0), xy, np.repeat(xy[-1:], dwell, axis=0)])
    pr = np.r_[np.full(dwell, pr[0]), pr, np.full(dwell, pr[-1])]
    step = V_WRITE / HZ
    above = 0.004
    n_v = int(round((above + pr[0]) / step))
    down = [np.r_[xy[0], paper_z + above - (above + pr[0]) * a] for a in np.linspace(0, 1, n_v + 1)]
    body = np.c_[xy, paper_z - pr]
    n_u = int(round((above + pr[-1]) / step))
    up = [np.r_[xy[-1], paper_z - pr[-1] + (above + pr[-1]) * a] for a in np.linspace(0, 1, n_u + 1)[1:]]
    return np.vstack([np.asarray(down), body, np.asarray(up)])


def paint(s, p, plans: dict, ilc_passes: int = ILC_PASSES, verbose: bool = True) -> dict:
    if s.medium != "pointed_pen":
        raise ValueError("the lettering reference writes with the pointed pen")
    paper_z = s.geo.z
    well = s.wells()[0]
    q = s.tip_down_quat(math.radians(float(plans["axis_deg"])))
    D = []
    for r in plans["routes"]:
        P = np.asarray(r["points_mm"], np.float64)
        x, y = s.geo.mm_to_world(P[:, 0], P[:, 1])
        pr = press_of_width(s.inst["brush"], np.asarray(r["widths_mm"], np.float64) / 1000.0)
        D.append(segment(np.stack([x, y], 1), paper_z, pr))
    corr = [np.zeros_like(d) for d in D]
    best = None                                                   # (worst p95 error, corrections) of the best pass so far
    recording = s._recording is not None
    hist = []
    from scipy.ndimage import gaussian_filter1d
    for it in range(ilc_passes + 1):
        final = it == ilc_passes
        if it > 0:
            s.reset()
        if final and best is not None:
            corr = best[1]                                        # the final (recorded) pass uses the best corrections found
        if final and recording:
            s._recording = []
        logs = []
        n_ik_fail = 0
        strokes0 = len(s.painter.strokes)
        (wx, wy), wz = well["center_xy"], well["surface_z"]
        p["move_tip"]([wx, wy, wz + 0.015], q, speed=V_TRAVEL)
        p["move_tip"]([wx, wy, wz - 0.003], q, speed=0.03, settle=3)
        p["move_tip"]([wx, wy, wz + 0.015], q, speed=0.04)
        for k, d in enumerate(D):
            x0 = d[0]
            p["move_tip"]([x0[0], x0[1], paper_z + Z_TRAVEL], q, speed=V_TRAVEL)
            p["move_tip"](x0, q, speed=0.03, settle=12)
            tl = _TipLog(s.painter)
            C = d + corr[k]
            n_ctrl = int(math.ceil(len(d) / (HZ / CTRL)))
            for j in range(1, n_ctrl + 1):
                i = min(len(C) - 1, int(round(j * (HZ / CTRL) + LAG_S * HZ)))
                qj, ok, _ = s.ik(C[i], q)
                n_ik_fail += 0 if ok else 1
                s.step(qj if ok else s.hold_action())
            for _ in range(10):
                s.step(s.hold_action())
            tl.close()
            logs.append(np.asarray(tl.log))
        errs, zup = [], []
        for k, d in enumerate(D):
            R = logs[k]; n = min(len(R), len(d)); e = d[:n] - R[:n]
            errs.append(float(np.percentile(np.linalg.norm(e[:, :2], axis=1), 95)) * 1000)
            zup.append(float(np.max(-e[:, 2])) * 1000 if n else 0.0)
        worst = max(errs)
        n_main = sum(1 for st in s.painter.strokes[strokes0:] if st["sheet"] == "main" and st["inked"])
        key = (n_main != len(D), worst)
        if best is None or key < best[0]:
            best = (key, [c.copy() for c in corr])
        if not final:
            for k, d in enumerate(D):
                R = logs[k]; n = min(len(R), len(d)); e = d[:n] - R[:n]
                corr[k][:n] += ILC_GAIN * gaussian_filter1d(e, ILC_SIGMA, axis=0, mode="nearest")
                corr[k][:, 2] = np.clip(corr[k][:, 2], -ILC_ZCAP, ILC_ZCAP)
        hist.append({"pass": it, "p95_xy_err_mm_max": round(worst, 3), "p95_xy_err_mm_median": round(float(np.median(errs)), 3),
                     "z_above_target_mm_max": round(max(zup), 3), "main_strokes": n_main, "ik_fail": n_ik_fail})
        if verbose:
            print("ILC pass", it, hist[-1], flush=True)
    p["move_tip"]([s.geo.center[0], s.geo.center[1] + 0.25, paper_z + 0.16], q, speed=0.15, settle=10)
    return {"contacts": len(D), "ilc": hist}
