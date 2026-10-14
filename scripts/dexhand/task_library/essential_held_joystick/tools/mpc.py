"""Wuji Hand 2.2 lookahead authoring controller for essential_held_joystick (authoring only).

Rows sent to the simulator are only the 26 Wuji actuator targets (wrist targets locked). Thumb joint targets are
chosen by short physics rollouts from a snapshot of the live authoring session (finite-difference Jacobian of the
measured gimbal angles + candidate perturbations), then committed for a few control steps. Middle/ring keep a light
curl from the approach prefix; index and pinky stay neutral.
"""
from __future__ import annotations

import argparse, json, time
from pathlib import Path

import numpy as np

from rcb_dexhand import Session
from snap import snapshot, restore

TH = np.arange(6, 10)
GOALS = [(-0.3, 0.0), (0.0, 0.3), (0.3, 0.0), (0.0, -0.3), (0.0, 0.0), (0.0, 0.0)]


def rollout(s, row, H):
    worst_rot = worst_drift = 0.0
    st = None
    for _ in range(H):
        st = s.step(row)
        f = s.features()
        worst_rot = max(worst_rot, f["body_rotation"]); worst_drift = max(worst_drift, f["body_drift"])
        if st["done"]:
            break
    return st, s.features(), worst_rot, worst_drift


def cost(st, f, rot, drift, k0, goal, a):
    if st["failed"]:
        return 1e9
    c = 0.0
    if st["success"]:
        return -1e7
    c -= 1e4 * (st["stage_index"] - k0)
    k = st["stage_index"]
    g = np.array(GOALS[min(k, 5)])
    c += ((f["joystick_x"] - g[0]) ** 2 + (f["joystick_y"] - g[1]) ** 2) / 0.05 ** 2
    c += 400 * max(rot - a.rot_soft, 0) ** 2 / 0.01 ** 2 * 0.01
    c += 400 * max(drift - 0.010, 0) ** 2 / 0.002 ** 2 * 0.01
    if f["base_contacts"] < 1:
        c += 50
    if k >= 5:  # terminal: low speed
        c += 50 * max(f["speed"] - 0.08, 0) / 0.04
    c -= 3 * st["stage_hold"] + 3 * st["terminal_hold"]
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="runs/b1/actions.npy")
    ap.add_argument("--prefix-rows", type=int, default=60)
    ap.add_argument("--out", default="runs/m1")
    ap.add_argument("--H", type=int, default=12)
    ap.add_argument("--K", type=int, default=4)
    ap.add_argument("--delta", type=float, default=0.05)
    ap.add_argument("--maxstep", type=float, default=0.08)
    ap.add_argument("--rot-soft", type=float, default=0.10)
    ap.add_argument("--max", type=int, default=1500)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    s = Session("essential_held_joystick", hand="wuji")
    lo, hi = s.model.actuator_ctrlrange.T
    prefix = np.load(a.prefix)[: a.prefix_rows]
    for row in prefix:
        s.step(row)
    row = prefix[-1].copy()
    actions = [r.copy() for r in prefix]
    log = []
    t0 = time.time()
    while len(actions) < a.max and not s.status()["done"]:
        sn = snapshot(s)
        st0 = s.status(); k0 = st0["stage_index"]
        g = np.array(GOALS[min(k0, 5)])
        f0 = s.features(); j0 = np.array([f0["joystick_x"], f0["joystick_y"]])
        cands = [row.copy()]
        J = np.zeros((2, 4)); results = {}
        for i, j in enumerate(TH):
            for sgn in (-1, 1):
                r = row.copy(); r[j] = np.clip(r[j] + sgn * a.delta, lo[j], hi[j])
                restore(s, sn)
                res = rollout(s, r, a.H)
                results[(i, sgn)] = (r, res)
            fp = results[(i, 1)][1][1]; fm = results[(i, -1)][1][1]
            dq = results[(i, 1)][0][j] - results[(i, -1)][0][j]
            if dq > 1e-6:
                J[:, i] = (np.array([fp["joystick_x"], fp["joystick_y"]]) - np.array([fm["joystick_x"], fm["joystick_y"]])) / dq
        # baseline (hold) rollout for the predicted drift of the current target
        restore(s, sn); base_res = rollout(s, row, a.H)
        jb = np.array([base_res[1]["joystick_x"], base_res[1]["joystick_y"]])
        err = g - jb
        lam = 0.5
        step = J.T @ np.linalg.solve(J @ J.T + lam * np.eye(2), err)
        for scale in (0.5, 1.0):
            d = np.clip(step * scale, -a.maxstep, a.maxstep)
            r = row.copy(); r[TH] = np.clip(r[TH] + d, lo[TH], hi[TH]); cands.append(r)
        scored = [(cost(*base_res, k0, g, a), 0, row.copy())]
        for (i, sgn), (r, res) in results.items():
            scored.append((cost(*res, k0, g, a), 1, r))
        for r in cands[1:]:
            restore(s, sn); res = rollout(s, r, a.H)
            scored.append((cost(*res, k0, g, a), 2, r))
        scored.sort(key=lambda x: x[0])
        best = scored[0][2]
        restore(s, sn)
        for _ in range(a.K):
            st = s.step(best); actions.append(best.copy())
            if st["done"]:
                break
        row = best
        f = s.features()
        log.append(dict(t=len(actions), stage=st["stage_index"], hold=st["stage_hold"], th=st["terminal_hold"], jx=f["joystick_x"], jy=f["joystick_y"],
                        rot=f["body_rotation"], drift=f["body_drift"], base=f["base_contacts"], cost=scored[0][0], kind=scored[0][1]))
        print("t %4d stage %d hold %d term %d jx %+.3f jy %+.3f rot %.3f drift %.4f base %d mech %d speed %.3f cost %.1f kind %d thumb %s %.0fs" % (
            len(actions), st["stage_index"], st["stage_hold"], st["terminal_hold"], f["joystick_x"], f["joystick_y"], f["body_rotation"], f["body_drift"],
            f["base_contacts"], f["mechanism_contacts"], f["speed"], scored[0][0], scored[0][1], np.round(row[TH], 3), time.time() - t0), st["failure"] or "", flush=True)
    st = s.status()
    print("final", st)
    A = np.array(actions)
    np.save(out / "actions.npy", A)
    s.save_trajectory(A, out / "trajectory.npz")
    (out / "log.json").write_text(json.dumps(dict(status=st, args=vars(a), log=log), default=float))


if __name__ == "__main__":
    main()
