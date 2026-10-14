"""Run the Wuji thumb-drag controller on essential_cube_layer and save the rows (authoring only).

The thumb pad presses on the top face of the passive layer and drags it about the layer axis. The contact angle
`alpha` (object frame) is driven by an integral law on the layer angle error; when the pad reaches the end of its
reachable arc it lifts, moves back and lands again (a ratchet), so several strokes can add up to a quarter turn.
Only the 20 finger targets change; the six wrist targets stay at the locked pose (Session.hold_action()).

Usage: run_turn.py --out <dir> [--radius R] [--phi0 DEG] [--pressure P] ...
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from rcb_dexhand import Session
from thumb_turn import ThumbIK, face_point

STAGE_TARGETS = [math.pi / 2, 0.0, math.pi / 2]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--radius", type=float, default=0.024)
    ap.add_argument("--phi0", type=float, default=135.0, help="object-frame angle (deg) where the pad lands first")
    ap.add_argument("--pressure", type=float, default=0.0005)
    ap.add_argument("--hold-pressure", type=float, default=None)
    ap.add_argument("--rate", type=float, default=0.03, help="max change of a thumb target per control (rad)")
    ap.add_argument("--approach", type=int, default=60)
    ap.add_argument("--descend", type=int, default=30)
    ap.add_argument("--lift", type=float, default=0.012, help="first approach height above the face (m)")
    ap.add_argument("--rlift", type=float, default=0.005, help="ratchet lift height (m)")
    ap.add_argument("--rsteps", type=int, nargs=3, default=[10, 20, 12], help="ratchet lift, move, land controls")
    ap.add_argument("--tol", type=float, default=0.03)
    ap.add_argument("--overshoot", type=float, default=0.0, help="aim beyond the stage centre (rad, toward motion)")
    ap.add_argument("--seed", type=float, nargs=4, default=[1.0, -1.19, 0.95, 1.2])
    ap.add_argument("--steps", type=int, default=1500)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--clearance", type=float, default=0.0015)
    ap.add_argument("--ki", type=float, default=0.3)
    ap.add_argument("--alpha-rate", type=float, default=0.012)
    ap.add_argument("--alpha-range", type=float, nargs=2, default=[132.0, 208.0])
    ap.add_argument("--pressure-back", type=float, default=None, help="pad pressure while returning to zero")
    ap.add_argument("--alpha-rate-back", type=float, default=None)
    ap.add_argument("--alpha-range-back", type=float, nargs=2, default=None)
    ap.add_argument("--move-clearance", type=float, default=None, help="clearance while the pad is lifted")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    hold_p = a.pressure if a.hold_pressure is None else a.hold_pressure
    lo, hi = (math.radians(v) for v in a.alpha_range)

    s = Session("essential_cube_layer", hand="wuji")
    ik = ThumbIK(s)
    base = s.hold_action().copy()
    rows, hist, phases = [], [], []
    state = {"last": None}

    def step(row, phase):
        st = s.step(row)
        rows.append(np.asarray(row, float).copy())
        phases.append(phase)
        f = s.features()
        hist.append({k: f[k] for k in ("top_turn", "base_contacts", "mechanism_contacts", "speed", "force",
                                       "body_drift", "body_rotation", "support", "palm_drift")} | {
            "stage": st["stage"], "reason": st["reason"]})
        return st

    def thumb_row(q):
        row = base.copy()
        row[ik.idx] = ik.ctrl(q)
        return row

    def pad_step(alpha, pressure, phase):
        p, n = face_point(s, alpha, a.radius)
        lifted = pressure <= -0.003
        clear = a.move_clearance if (lifted and a.move_clearance is not None) else a.clearance
        q, e = ik.solve(p, n, pressure=pressure, avoid_top="all" if lifted else True, clearance=clear)
        last = state["last"]
        if last is not None:
            q = np.clip(q, last - a.rate, last + a.rate)
        state["last"] = q
        return step(thumb_row(q), phase), e

    phi0 = math.radians(a.phi0)
    ik.q = np.array(a.seed)
    for _ in range(3):
        p, n = face_point(s, phi0, a.radius)
        q_pre, _ = ik.solve(p, n, pressure=-a.lift, avoid_top="all", clearance=a.clearance, nfev=100)
    q0 = s.data.qpos[ik.qa].copy()
    st = s.status()
    for i in range(a.approach):
        w = 0.5 - 0.5 * math.cos(math.pi * (i + 1) / a.approach)
        st = step(thumb_row(q0 + w * (q_pre - q0)), "approach")
        if st["done"]:
            break
    state["last"] = q_pre.copy()
    ik.q = q_pre.copy()
    for i in range(a.descend):
        if st["done"]:
            break
        st, e = pad_step(phi0, -a.lift + (a.pressure + a.lift) * (i + 1) / a.descend, "land")

    alpha = phi0
    count = 0
    e = 0.0
    while count < a.steps and not st["done"]:
        count += 1
        f = s.features()
        stage = st["stage"]
        theta = f["top_turn"]
        target = STAGE_TARGETS[min(stage, 2)]
        prev_target = 0.0 if stage == 0 else STAGE_TARGETS[min(stage, 3) - 1]
        direction = 1 if (stage >= 3 or target > prev_target) else -1
        aim = target + (direction * a.overshoot if stage < 3 else 0.0)
        err = aim - theta
        back = direction < 0
        press = a.pressure_back if (back and a.pressure_back is not None) else a.pressure
        rate_a = a.alpha_rate_back if (back and a.alpha_rate_back is not None) else a.alpha_rate
        lo, hi = (math.radians(v) for v in (a.alpha_range_back if (back and a.alpha_range_back) else a.alpha_range))
        if abs(err) < a.tol:
            st, e = pad_step(alpha, hold_p, f"hold{stage}")
        else:
            want = 1 if err > 0 else -1
            at_end = (want > 0 and alpha >= hi - 1e-9) or (want < 0 and alpha <= lo + 1e-9)
            if at_end:
                # ratchet: lift, move back to the other end of the arc, land again
                n_lift, n_move, n_land = a.rsteps
                start = alpha
                goal = lo if want > 0 else hi
                for i in range(n_lift):
                    st, e = pad_step(start, press - (press + a.rlift) * (i + 1) / n_lift, "lift")
                    if st["done"]:
                        break
                for i in range(n_move):
                    if st["done"]:
                        break
                    w = 0.5 - 0.5 * math.cos(math.pi * (i + 1) / n_move)
                    st, e = pad_step(start + w * (goal - start), -a.rlift, "move")
                for i in range(n_land):
                    if st["done"]:
                        break
                    st, e = pad_step(goal, -a.rlift + (press + a.rlift) * (i + 1) / n_land, "land")
                alpha = goal
                continue
            alpha += float(np.clip(a.ki * err, -rate_a, rate_a))
            alpha = float(np.clip(alpha, lo, hi))
            st, e = pad_step(alpha, press, f"drag{stage}")
        if not a.quiet and count % 25 == 0:
            h = hist[-1]
            print(len(rows), "stage", st["stage"], "turn %.3f" % h["top_turn"], "base", h["base_contacts"],
                  "mech", h["mechanism_contacts"], "drift %.4f rot %.3f force %.2f speed %.3f" % (
                      h["body_drift"], h["body_rotation"], h["force"], h["speed"]), "ik %.4f" % e,
                  "alpha %.1f" % math.degrees(alpha), flush=True)
    st = s.status()
    summary = {"status": {k: st[k] for k in ("success", "done", "reason", "steps", "stage", "state_sha")},
               "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(a).items()},
               "max": {k: max(h[k] for h in hist) for k in ("body_drift", "body_rotation", "force", "speed", "palm_drift")},
               "max_turn": max(h["top_turn"] for h in hist), "rows": len(rows)}
    print(json.dumps(summary))
    np.save(a.out / "rows.npy", np.array(rows))
    s.save_trajectory(np.array(rows), a.out / "trajectory.npz")
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1))
    (a.out / "history.json").write_text(json.dumps(hist))
    (a.out / "phases.json").write_text(json.dumps(phases))
    return summary


if __name__ == "__main__":
    main()
