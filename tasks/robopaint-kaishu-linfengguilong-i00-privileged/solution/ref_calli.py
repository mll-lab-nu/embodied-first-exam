"""Reference writer for the RoboPaint kaishu oracle, step 2 (solution/ only, never in the agent image; runs at generation
time on the graders' full instance). Input: per-stroke handle plans from the robot-free optimiser (opt_calli.py: K control points
(x, y, press z) per stroke, in the exemplar's stroke order). Execution on the robot:
  - before every stroke: dip in the ink stone (restores the brush), travel 15 mm above the paper to 4 mm behind the stroke start,
    settle, then the stroke segment = the same approach / touch-down / body / lift the optimiser simulated (StrokeOpt.path), with
    the samples spaced for 2 cm/s (plans.json "entry" / "exit": how the brush meets and leaves the paper, opt_calli.stroke_path);
  - tracking: ManiSkill's pd_joint_pos (stiffness 1e3, damping 1e2, targets held for the 5 physics steps of a 20 Hz control step)
    lags a moving target by about D/K + half a control period = 0.125 s; each control step commands IK(desired tip at t + 0.125 s)
    (feed-forward), then iterative learning control: the realized tip path (the painter's 100 Hz samples) is compared with the
    desired one and the commanded path is corrected by the error, a few passes from the frozen start state;
  - finally the arm parks beyond the ink plate (out of the cameras' view of the sheet).
paint(s, p, plans) records into the Session; the actions are what solution/oracle_qpos.npy freezes."""
from __future__ import annotations
import math
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from opt_calli import stroke_path  # noqa: E402

LAG_S = 0.125
V_WRITE = 0.02           # m/s along the stroke
V_TRAVEL = 0.12          # m/s in the air
Z_TRAVEL = 0.015         # m above the paper
HZ, CTRL = 100, 20


def stroke_segment(P: np.ndarray, paper_z: float, entry: str = "vertical", exit: str | None = None) -> np.ndarray:
    """Desired tip samples at 100 Hz for one stroke plan: the path the optimiser simulated (opt_calli.stroke_path), spaced for 2 cm/s."""
    return stroke_path(P, paper_z, V_WRITE / HZ, entry, exit)


class _TipLog:
    """Wraps the painter's sample() to record the realized tip at every physics step."""
    def __init__(self, painter):
        self.painter, self.orig, self.log = painter, painter.sample, []
        painter.sample = self._sample

    def _sample(self, p, R):
        self.log.append(np.asarray(p, np.float64).copy())
        self.orig(p, R)

    def close(self):
        self.painter.sample = self.orig


def _dip(s, p, well: dict) -> None:
    (x, y), zs = well["center_xy"], well["surface_z"]
    p["move_tip"]([x, y, zs + 0.015], speed=V_TRAVEL)
    p["move_tip"]([x, y, zs - 0.003], speed=0.03, settle=3)
    p["move_tip"]([x, y, zs + 0.015], speed=0.04)


def _run_segment(s, D: np.ndarray, corr: np.ndarray) -> tuple[int, int]:
    """Stream one desired 100 Hz tip segment D (N, 3) with correction corr (N, 3): each control step commands IK(D + corr at
    t + LAG_S); then holds the last target 10 control steps. Returns (first physics sample index, n control steps)."""
    C = D + corr
    n_ctrl = int(math.ceil(len(D) / (HZ / CTRL)))
    for k in range(1, n_ctrl + 1):
        i = min(len(C) - 1, int(round(k * (HZ / CTRL) + LAG_S * HZ)))
        q, ok, _ = s.ik(C[i])
        s.step(q if ok else s.hold_action())
    for _ in range(10):
        s.step(s.hold_action())
    return n_ctrl + 10


def paint(s, p, plans: list, ilc_passes: int = 3, verbose: bool = True, entry: str = "vertical", exit: str | None = None) -> dict:
    """Write the character: plans = per-stroke (K, 3) control points in stroke order. Iterative learning control over the whole
    episode (reset between passes), then the final pass is the recording (the caller's record_start/record_stop wraps this call:
    everything before the final pass is erased by reset())."""
    paper_z = s.geo.z
    well = s.wells()[0]
    D = [stroke_segment(np.asarray(P, np.float64), paper_z, entry, exit) for P in plans]
    corr = [np.zeros_like(d) for d in D]
    hist = []
    recording = s._recording is not None               # run-oracle records; reset() stops a recording, so restart it for the final pass
    for it in range(ilc_passes + 1):
        final = it == ilc_passes
        if it > 0:
            s.reset()
        if final and recording:
            s._recording = []                          # the recorded trajectory = the final pass from the frozen start state
        logs = []
        for k, d in enumerate(D):
            _dip(s, p, well)
            x0 = d[0]
            p["move_tip"]([x0[0], x0[1], paper_z + Z_TRAVEL], speed=V_TRAVEL)
            p["move_tip"](x0, speed=0.03, settle=12)
            tl = _TipLog(s.painter)
            i0 = len(tl.log)
            _run_segment(s, d, corr[k])
            tl.close()
            R = np.asarray(tl.log)                     # realized tip at 100 Hz from the first control step of the segment
            logs.append(R)
        errs = []
        for k, d in enumerate(D):
            R = logs[k]
            n = min(len(R), len(d))
            e = d[:n] - R[:n]
            errs.append(float(np.percentile(np.linalg.norm(e[:, :2], axis=1), 95)) * 1000)
            if not final:
                corr[k][:n] += e
        hist.append({"pass": it, "p95_xy_err_mm_per_stroke": [round(v, 3) for v in errs]})
        if verbose:
            print("ILC pass", it, "p95 tracking error (mm):", [round(v, 3) for v in errs], flush=True)
    # park beyond the ink plate
    p["move_tip"]([s.geo.center[0], s.geo.center[1] + 0.25, paper_z + 0.16], speed=0.15, settle=10)
    return {"strokes": len(plans), "ilc": hist}
