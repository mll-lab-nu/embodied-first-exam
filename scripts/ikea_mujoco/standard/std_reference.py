#!/usr/bin/env python3
"""Standard-mode reference of an IKEA MuJoCo task: the privileged twin's reference rows (solution/trajectory.npz), slowed
down to the joint-speed rule (rcb_ikea.JOINT_SPEED_LIMITS_RAD_S / GRIPPER_SPEED_LIMITS, the robots' real limits: each
target moves at most its limit per control step; rcb_ikea.Session applies the same clamp in both modes and in the replay).
The arm joints are retimed by one of the methods below; a gripper the table limits (none today) is then handled by --grip
(wait: each gripper event completes before the next row; inplace: slewed as Session.applied() would), so the clamp leaves
every row of the reference unchanged.

Four methods for the arm joints, each keeping every privileged row in order and every control step within the rule:
  track (default): a slew-limited tracker that dilates time only where it must: each control step every arm joint target
    moves toward the current row by at most the limit; the next row is taken once every joint is within --lag rad of it.
    Rows the limit allows are reproduced exactly. The gripper command is the current row's.
  dilate: --lag 0 in effect, on the straight line in joint space: a row farther than the limit from the previous one is
    reached over the ceil(jump / limit) control steps it needs, with its gripper command from the first of them.
  centred: timing-preserving (every row keeps its time): the mean of a forward and a backward slew-limited pass, so
    a move faster than the limit starts earlier and ends later, centred on the original.
  clamp: timing-preserving, exactly the clamp rcb_ikea.Session applies to any rows (a forward slew): the reference
    replays bit for bit as the original rows do under the clamp.
Before any, --despike replaces one- to few-tick target glitches (a joint target leaves and comes back within a few
control steps; the servos never followed them) by the running median. Optional --hold-tail S appends S s of the last row.
The service then executes the reference rows unchanged (meta n_clipped 0).

Run inside the IKEA MuJoCo image (needs the scene: /opt/ikea/scenes/<task>):
  python std_reference.py make --task lack --priv tasks/ikea-lack-i00-privileged/solution/trajectory.npz --out lack.npz
  python std_reference.py check --task lack --traj lack.npz       # the step rule on every control step (no physics)
The verdict is the grader's: python rcb_ikea.py replay --task lack --traj lack.npz (fresh process; final_check()).
Source: scripts/ikea_mujoco/standard/std_reference.py."""
from __future__ import annotations
import argparse, json, math, os, sys, time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
JOINT_STEP_LIMIT_RAD = 0.004      # --speed 1.6 (RoboARC's rule at the IKEA control step of 2.5 ms; not the IKEA rule)


def grip_columns(actuators) -> list:
    return [i for i, n in enumerate(actuators) if n.endswith(("actuator8", "_gripper"))]


def dilate(ctrl: np.ndarray, ctrl0: np.ndarray, grips: list, limit=JOINT_STEP_LIMIT_RAD) -> tuple[np.ndarray, dict]:
    ctrl = np.asarray(ctrl, dtype=np.float64)
    arm = np.array([j for j in range(ctrl.shape[1]) if j not in grips])
    prev = np.asarray(ctrl0, dtype=np.float64).copy()
    out, slowed, extra, worst = [], 0, 0, 0.0
    for row in ctrl:
        jump = float(np.max(np.abs(row[arm] - prev[arm]) / limit)) if len(arm) else 0.0      # in units of the limit
        worst = max(worst, jump)
        n = max(1, int(math.ceil(jump - 1e-9)))
        if n == 1:
            out.append(row.copy())
        else:
            slowed += 1; extra += n - 1
            for k in range(1, n + 1):
                a = row.copy()
                a[arm] = prev[arm] + (row[arm] - prev[arm]) * (k / n) if k < n else row[arm]
                out.append(a)
        prev = row
    return np.array(out), {"rows_in": int(len(ctrl)), "rows_out": int(len(out)), "rows_slowed": slowed, "steps_added": extra,
                           "max_jump_in_limits": round(worst, 3)}


def despike(ctrl: np.ndarray, grips: list, width: int = 9, tol: float = 0.01) -> tuple[np.ndarray, int]:
    """One- or few-tick glitches of an arm joint target (the target leaves and comes back within a few control steps; the
    servos never follow them): replaced by the running median where the target is more than `tol` from it. Ramps and
    steps are unchanged (the median of a monotonic window is its centre)."""
    x = np.asarray(ctrl, dtype=np.float64).copy()
    arm = [j for j in range(x.shape[1]) if j not in grips]
    h = width // 2
    a = x[:, arm]
    pad = np.vstack([np.repeat(a[:1], h, 0), a, np.repeat(a[-1:], h, 0)])
    win = np.lib.stride_tricks.sliding_window_view(pad, width, axis=0)        # (N, joints, width)
    med = np.median(win, axis=2)
    bad = np.abs(a - med) > tol
    a[bad] = med[bad]
    x[:, arm] = a
    return x, int(bad.any(1).sum())


def track(ctrl: np.ndarray, ctrl0: np.ndarray, grips: list, lag: float, limit=JOINT_STEP_LIMIT_RAD) -> tuple[np.ndarray, dict]:
    """A slew-limited tracker of the rows that dilates time only where it has to: every control step each arm joint
    target moves toward the current row by at most `limit`; the next row is taken when every joint is within `lag` rad of
    the current one (else the current row is kept: a control step is inserted). Rows the limit allows are reproduced
    exactly; a fast segment is followed at most `lag` behind, and slowed where it would fall farther behind. The gripper
    command is the current row's. lag = 0 is pure dilation. At the end the last row is reached exactly."""
    x = np.asarray(ctrl, dtype=np.float64)
    arm = np.array([j for j in range(x.shape[1]) if j not in grips])
    y = np.asarray(ctrl0, dtype=np.float64)[arm].copy()
    out = []; i = 0; n = len(x); inserted = 0; worst = 0.0
    xa = x[:, arm]
    while i < n:
        tgt = xa[i]
        y = y + np.clip(tgt - y, -limit, limit)
        row = x[i].copy(); row[arm] = y
        out.append(row)
        dev = float(np.max(np.abs(tgt - y)))
        if dev <= lag + 1e-12:
            worst = max(worst, dev); i += 1
        else:
            inserted += 1
    while float(np.max(np.abs(xa[-1] - y))) > 0:
        y = y + np.clip(xa[-1] - y, -limit, limit)
        row = x[-1].copy(); row[arm] = y; out.append(row); inserted += 1
    out = np.array(out)
    return out, {"rows_in": int(n), "rows_out": int(len(out)), "method": "track", "lag_rad": lag, "steps_added": inserted,
                 "max_lag_rad": round(worst, 6)}


def clamp(ctrl: np.ndarray, ctrl0: np.ndarray, grips: list, limit=JOINT_STEP_LIMIT_RAD) -> tuple[np.ndarray, dict]:
    """Timing-preserving, exactly rcb_ikea.Session.applied() on the arm joints (the clamp both modes apply to any rows): an
    arm target more than its limit (+ 1e-9) from the previous control step's moves by the limit; every other target is
    the row's, bit for bit. So the reference replays exactly as the original rows do under the clamp."""
    x = np.asarray(ctrl, dtype=np.float64)
    arm = np.array([j for j in range(x.shape[1]) if j not in grips])
    lim = np.broadcast_to(np.asarray(limit, dtype=np.float64), (len(arm),))
    out = x.copy(); prev = np.asarray(ctrl0, dtype=np.float64)[arm].copy(); n = 0
    for row in out:
        d = row[arm] - prev
        over = np.abs(d) > lim + 1e-9
        if over.any():
            row[arm[over]] = prev[over] + np.sign(d[over]) * lim[over]; n += 1
        prev = row[arm].copy()
    dev = np.abs(out[:, arm] - x[:, arm]).max(1)
    return out, {"rows_in": int(len(x)), "rows_out": int(len(out)), "method": "clamp", "steps_added": 0, "rows_clamped": n,
                 "max_abs_dev_rad": round(float(dev.max()), 6)}


def centred(ctrl: np.ndarray, ctrl0: np.ndarray, grips: list, limit=JOINT_STEP_LIMIT_RAD) -> tuple[np.ndarray, dict]:
    """Timing-preserving: per arm joint the mean of a forward and a backward slew-limited pass (each within the limit, so
    their mean is too). A move faster than the limit starts earlier and ends later, centred on the original; every row
    keeps its time and the rows within the limit far from such a move are unchanged. Useful where only a few short
    segments are over the limit; the first row is reached from ctrl0 by dilation."""
    x = np.asarray(ctrl, dtype=np.float64)
    arm = np.array([j for j in range(x.shape[1]) if j not in grips])
    lim = np.broadcast_to(np.asarray(limit, dtype=np.float64), (len(arm),))
    head, _ = dilate(x[:1], ctrl0, grips, limit)
    xa = x[:, arm]
    f = xa.copy(); b = xa.copy()
    for i in range(1, len(xa)):
        f[i] = np.clip(xa[i], f[i - 1] - lim, f[i - 1] + lim)
    for i in range(len(xa) - 2, -1, -1):
        b[i] = np.clip(xa[i], b[i + 1] - lim, b[i + 1] + lim)
    b[0] = xa[0]
    for i in range(1, len(xa)):                 # pin the first row: keep the backward pass within the limit of it
        b[i] = np.clip(b[i], b[i - 1] - lim, b[i - 1] + lim)
    y = x.copy(); y[:, arm] = 0.5 * (f + b)
    out = np.vstack([head[:-1], y])
    dev = np.abs(y[:, arm] - xa).max(1)
    return out, {"rows_in": int(len(x)), "rows_out": int(len(out)), "method": "centred", "steps_added": int(len(head) - 1),
                 "max_abs_dev_rad": round(float(dev.max()), 6), "rows_dev_over_0.01": int((dev > 0.01).sum())}


def slew_grippers(ctrl: np.ndarray, ctrl0: np.ndarray, grips: list, step_limit: np.ndarray) -> tuple[np.ndarray, int]:
    """Time-preserving gripper slew, exactly rcb_ikea.Session.applied() on the gripper columns: a gripper command more than
    its step limit (+ SPEED_TOL) from the previous control step's moves by that step. Unlimited grippers (inf) unchanged."""
    out = np.asarray(ctrl, dtype=np.float64).copy()
    g = [j for j in grips if np.isfinite(step_limit[j])]
    if not g:
        return out, 0
    lim = step_limit[g]; prev = np.asarray(ctrl0, dtype=np.float64)[g].copy(); n = 0
    for row in out:
        d = row[g] - prev
        over = np.abs(d) > lim + 1e-9
        if over.any():
            row[np.array(g)[over]] = prev[over] + np.sign(d[over]) * lim[over]; n += 1
        prev = row[g].copy()
    return out, n


def grip_wait(ctrl: np.ndarray, ctrl0: np.ndarray, grips: list, step_limit: np.ndarray, glag: float = 0.0) -> tuple[np.ndarray, int]:
    """Gripper retiming that keeps the order of events: a row whose limited gripper command is more than its step limit
    from the previous control step's is held (its arm targets, already within their limits, reached on its first step)
    while the gripper slews toward it, until every limited gripper is within `glag` of the row's command; then the next
    row. So a grasp or a release completes before the arm moves on, as with the original instant command."""
    x = np.asarray(ctrl, dtype=np.float64)
    g = np.array([j for j in grips if np.isfinite(step_limit[j])], dtype=int)
    if not len(g):
        return x.copy(), 0
    lim = step_limit[g]; y = np.asarray(ctrl0, dtype=np.float64)[g].copy(); out = []; added = 0
    for row in x:
        first = True
        while True:
            d = row[g] - y
            y = np.where(np.abs(d) > lim + 1e-9, y + np.sign(d) * lim, row[g])
            r = row.copy(); r[g] = y; out.append(r)
            if not first:
                added += 1
            first = False
            if np.all(np.abs(row[g] - y) <= glag + 1e-12):
                break
    return np.array(out), added


def step_stats(ctrl: np.ndarray, ctrl0: np.ndarray, grips: list, limit=JOINT_STEP_LIMIT_RAD) -> dict:
    arm = [j for j in range(ctrl.shape[1]) if j not in grips]
    full = np.vstack([np.asarray(ctrl0, dtype=np.float64)[None], ctrl])
    d = np.abs(np.diff(full[:, arm], axis=0))
    lim = np.broadcast_to(np.asarray(limit, dtype=np.float64), d.shape[1:])
    return {"rows": int(len(ctrl)), "max_step_rad": float(d.max()), "steps_over_limit": int((d > lim + 1e-9).any(1).sum()),
            "max_step_in_limits": round(float((d / lim).max()), 6)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make"); mk.add_argument("--task", required=True); mk.add_argument("--priv", required=True)
    mk.add_argument("--out", required=True); mk.add_argument("--hold-tail", type=float, default=0.0)
    mk.add_argument("--method", choices=("dilate", "track", "centred", "clamp"), default="track")
    mk.add_argument("--speed", default="robot", help="arm joint speed limit: 'robot' (rcb_ikea.JOINT_SPEED_LIMITS_RAD_S, "
                                                     "the rule) or one rad/s value for every arm joint (a study)")
    mk.add_argument("--grip", choices=("wait", "inplace"), default="wait",
                    help="the Panda hand's slew: wait (a gripper event completes before the next row) or inplace (slewed "
                         "in place, time-preserving, as Session.applied would do to the original rows)")
    mk.add_argument("--grip-lag", type=float, default=0.0, help="wait: how close (command units) the hand must get first")
    mk.add_argument("--lag", type=float, default=0.02, help="track: how far (rad) the targets may follow behind the rows")
    mk.add_argument("--despike", type=float, default=0.01, help="replace target glitches farther than this from the running "
                                                                "median (0: off)")
    ck = sub.add_parser("check"); ck.add_argument("--task", required=True); ck.add_argument("--traj", required=True)
    ck.add_argument("--speed", default="robot")
    for p in (mk, ck):
        p.add_argument("--rcb-ikea", default=os.path.join(HERE, "..", "shared"))
    a = ap.parse_args()
    sys.path.insert(0, os.path.abspath(a.rcb_ikea))
    import rcb_ikea as R
    s = R.Session(a.task)
    ctrl0 = s.data.ctrl.copy(); grips = grip_columns(s.actuators)
    arm = [j for j in range(s.nu) if j not in grips]
    if a.speed == "robot":
        limit = np.asarray(s.step_limit, dtype=np.float64)[arm]          # rad per control step, per arm joint
    else:
        limit = JOINT_STEP_LIMIT_RAD if a.speed == "1.6" else float(a.speed) * s.control_dt
    if a.cmd == "check":
        c = R.load_trajectory(a.traj, s.nu, s.timestep)
        print(json.dumps({"task": a.task, **step_stats(c, ctrl0, grips, limit),
                          "gripper_steps_over_limit": slew_grippers(c, ctrl0, grips, s.step_limit)[1]}))
        return 0
    c = R.load_trajectory(a.priv, s.nu, s.timestep)
    nspk = 0
    if a.despike > 0:
        c, nspk = despike(c, grips, tol=a.despike)
    if a.method == "track":
        out, info = track(c, ctrl0, grips, a.lag, limit)
    else:
        out, info = {"dilate": dilate, "centred": centred, "clamp": clamp}[a.method](c, ctrl0, grips, limit)
    info["despiked_rows"] = nspk
    if a.hold_tail > 0:
        n = int(round(a.hold_tail / s.control_dt))
        out = np.vstack([out, np.repeat(out[-1:], n, axis=0)]); info["hold_tail_rows"] = n
    info["speed"] = a.speed
    info["grip"] = a.grip
    if a.grip == "wait":
        out, info["gripper_wait_steps"] = grip_wait(out, ctrl0, grips, s.step_limit, a.grip_lag)
    out, info["gripper_slewed_steps"] = slew_grippers(out, ctrl0, grips, s.step_limit)
    s.save_trajectory(out, a.out)
    print(json.dumps({"task": a.task, **info, **step_stats(out, ctrl0, grips, limit), "sim_time_s": round(len(out) * s.control_dt, 3),
                      "out": a.out, "t": time.strftime("%H:%M:%S")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
