"""Stroke-program painter for the RoboPaint oil tasks (solution/ only; generation time). A stroke program is a list of strokes
{"color": well name, "points_mm": [[X, Y], ...] (control points on the main sheet, paper mm), "press_mm": [..] (press depth at each
control point), "speed_mm_s": v}; each is executed as: dip in its colour's well (a fresh brush), travel at the hover height above the
paper, descend to the first press at the first point, follow the Catmull-Rom curve through the points at v with the press
interpolated, lift, and at the end the arm parks. Commands: one IK solve per control step for the desired tip 0.125 s ahead (PD lag
feed-forward). Per stroke (optional): travel_m_s, descend_m_s, settle, lift_m_s, dip. Per program (optional `motion`, the keys of
MOTION): the hover height between strokes, the dip's speeds and settle, the hold after a stroke; a program without `motion` moves
exactly as before (20 mm hover, slow dips, 8 hold steps). The robot's execution of the program is the reference painting."""
from __future__ import annotations
import math
import numpy as np

LAG_S, V_TRAVEL, Z_TRAVEL, HZ, CTRL = 0.125, 0.12, 0.020, 100, 20
MOTION = {"hover_m": Z_TRAVEL, "dip_travel_m_s": V_TRAVEL, "dip_down_m_s": 0.03, "dip_up_m_s": 0.05, "dip_settle": 2, "hold_end": 8}


def catmull_rom(P: np.ndarray, n_per: int = 16) -> np.ndarray:
    P = np.asarray(P, np.float64)
    if len(P) == 1:
        return P.copy()
    Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    t = np.linspace(0, 1, n_per, endpoint=False)[:, None]
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1:])
    return np.vstack(out)


def stroke_samples(s, st: dict) -> np.ndarray:
    """Desired 100 Hz tip samples (world xyz) of one stroke: vertical descent to the first press, the curve, vertical lift."""
    P = np.asarray(st["points_mm"], np.float64); pr = np.asarray(st["press_mm"], np.float64) / 1000.0
    C = catmull_rom(np.c_[P, pr], 16)
    x, y = s.geo.mm_to_world(C[:, 0], C[:, 1])
    W = np.stack([x, y, s.geo.z - C[:, 2]], 1)
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(W[:, :2], axis=0), axis=1))]
    step = float(st["speed_mm_s"]) / 1000.0 / HZ
    n = max(2, int(math.ceil(d[-1] / step)) + 1)
    s_ = np.linspace(0, d[-1], n)
    body = np.stack([np.interp(s_, d, W[:, k]) for k in range(3)], 1)
    above = 0.004
    n_v = max(2, int(round((above + pr[0]) / (0.02 / HZ))))
    down = np.array([[body[0, 0], body[0, 1], s.geo.z + above - (above + pr[0]) * a] for a in np.linspace(0, 1, n_v)])
    n_u = max(2, int(round((above + pr[-1]) / (0.02 / HZ))))
    up = np.array([[body[-1, 0], body[-1, 1], s.geo.z - pr[-1] + (above + pr[-1]) * a] for a in np.linspace(0, 1, n_u)[1:]])
    return np.vstack([down, body, up])


def paint(s, p, program: list, verbose: bool = False, motion: dict | None = None) -> dict:
    m = {**MOTION, **(motion or {})}
    wells = {w["name"]: w for w in s.wells()}
    last = None
    for k, st in enumerate(program):
        w = wells[st["color"]]
        (wx, wy), wz = w["center_xy"], w["surface_z"]
        if st.get("dip", True) or last != st["color"]:                         # a fresh load when the program asks (default: every stroke)
            p["move_tip"]([wx, wy, wz + 0.02], speed=float(m["dip_travel_m_s"]))
            p["move_tip"]([wx, wy, wz - 0.003], speed=float(m["dip_down_m_s"]), settle=int(m["dip_settle"]))
            p["move_tip"]([wx, wy, wz + 0.02], speed=float(m["dip_up_m_s"]))
            last = st["color"]
        D = stroke_samples(s, st)
        p["move_tip"]([D[0, 0], D[0, 1], s.geo.z + float(m["hover_m"])], speed=float(st.get("travel_m_s", V_TRAVEL)))
        p["move_tip"](D[0], speed=float(st.get("descend_m_s", 0.03)), settle=int(st.get("settle", 10)))
        n_ctrl = int(math.ceil(len(D) / (HZ / CTRL)))
        for j in range(1, n_ctrl + 1):
            i = min(len(D) - 1, int(round(j * (HZ / CTRL) + LAG_S * HZ)))
            q, ok, _ = s.ik(D[i])
            s.step(q if ok else s.hold_action())
        for _ in range(int(m["hold_end"])):
            s.step(s.hold_action())
        p["move_tip"]([D[-1, 0], D[-1, 1], s.geo.z + float(m["hover_m"])], speed=float(st.get("lift_m_s", 0.05)))
        if verbose:
            print(f"stroke {k + 1}/{len(program)} {st['color']} done", flush=True)
    p["move_tip"]([s.geo.center[0], s.geo.center[1] + 0.27, s.geo.z + 0.16], speed=0.15, settle=10)
    return {"strokes": len(program)}
