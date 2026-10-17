"""Authoring controller (closed loop on Session state) that records the Sharpa Wave oracle rows.

Top-down pinch of the brush back (thumb on the near long face, index/middle/ring on the far face), lift, four
centre-out strokes over the upward sole (forefoot +y, forefoot -y, heel +y, heel -y), withdraw and hold.
Every row is a plain actuator-target vector; the recorded rows are replayed open loop by replay.py.

Witnesses (DEXHAND_ASSET_DIR set; append 150 copies of the last executed row for slack):
  sharpa: python tools/author_oracle.py --out sharpa.npz                         (success at control 1178)
  wuji:   python tools/author_oracle.py --hand wuji --tipz -0.002 --thumbz 0.010 \
              --squeeze 0.018 --grip-clear -1 --out wuji.npz                     (success at control 1186)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import mujoco
import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from runtime import Session  # noqa: E402

TIPS = {
    "sharpa": {f: f"right_{f}_fingertip_collision" for f in ("thumb", "index", "middle", "ring", "pinky")},
    "wuji": {"thumb": "r_wuji_r_thumb_tip_sensor_frame_collision1",
             **{f: f"r_wuji_r_{f}_finger_tip_sensor_frame_collision1" for f in ("index", "middle", "ring")},
             "pinky": "r_wuji_r_pinky_tip_sensor_frame_collision1"},
}
PAD = {"sharpa": (0.0094, 0.0081), "wuji": (0.0095, 0.0080)}  # (thumb, finger) contact radius of the tip geoms


class Author:
    def __init__(self, session):
        self.s = session
        self.m = session.model
        self.scratch = mujoco.MjData(self.m)
        self.rows = []
        self.log = []
        m = self.m
        self.hand_bodies = set()
        root = m.body("wrist_stage").id
        for b in range(m.nbody):
            if b == root or int(m.body_parentid[b]) in self.hand_bodies:
                self.hand_bodies.add(b)
        self.hand_geoms = [g for g in range(m.ngeom) if m.geom_bodyid[g] in self.hand_bodies and m.geom_contype[g]]
        self.tip_ids = {f: m.geom(n).id for f, n in TIPS[session.hand].items()}
        self.wrist_reg = 0.3
        self.counter = m.geom("counter").id

    # ------------------------------------------------------------------ IK
    def fk(self, q):
        m, d = self.m, self.scratch
        d.qpos[:] = self.s.data.qpos
        d.qpos[self.s.qadr] = q
        mujoco.mj_kinematics(m, d)
        mujoco.mj_collision(m, d) if False else None
        return d

    def solve(self, q0, targets, variable, avoid=(), weight_reg=0.01, clearance=0.002):
        """Least squares on actuator targets ``variable`` so tip geoms reach ``targets`` {finger: xyz}."""
        m, d = self.m, self.scratch
        q = q0.copy()
        lo, hi = self.s.lo[variable], self.s.hi[variable]
        init = np.clip(q0[variable], lo + 1e-6, hi - 1e-6)
        others = [g for g in self.hand_geoms if g not in self.tip_ids.values()]

        def residual(x):
            q[variable] = x
            self.fk(q)
            err = []
            for f, t in targets.items():
                err.extend((d.geom_xpos[self.tip_ids[f]] - t) * 100)
            for ob, clear in avoid:
                for g in (others if ob != self.counter else self.hand_geoms):
                    dist = mujoco.mj_geomDistance(m, d, g, ob, 0.05, None)
                    err.append(min(0.0, dist - clear) * 300)
            err.extend((x - init) * weight_reg)
            for i, v in enumerate(variable):
                if 3 <= v < 6:
                    err.append(q[v] * self.wrist_reg)
            return np.asarray(err)

        fit = least_squares(residual, init, bounds=(lo, hi), max_nfev=300)
        q[variable] = fit.x
        residual(fit.x)
        return q.copy(), fit.cost

    # ------------------------------------------------------------------ execution
    def step(self, q, phase):
        q = np.clip(q, self.s.lo, self.s.hi)
        self.rows.append(q.copy())
        st = self.s.step(q)
        if len(self.rows) % 25 == 0 or st["done"]:
            f = st["features"]
            self.log.append(dict(row=len(self.rows), phase=phase, stage=st["stage"], reason=st["reason"],
                                 in_tray=st["clods_in_tray"], brushed=st["clods_brushed"],
                                 pad_boot=f.get("pad_on_boot"), hand_brush=f.get("hand_on_brush")))
            print(self.log[-1], flush=True)
        return st

    def move(self, q_from, q_to, n, phase):
        st = None
        for k in range(1, n + 1):
            u = k / n
            u = u * u * (3 - 2 * u)
            st = self.step(q_from + (q_to - q_from) * u, phase)
            if st["done"]:
                break
        return st

    def hold(self, q, n, phase):
        st = None
        for _ in range(n):
            st = self.step(q, phase)
            if st["done"]:
                break
        return st

    def pad(self):
        return self.s.data.geom_xpos[self.m.geom("brush_bristle_pad").id].copy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--hand", default="sharpa", choices=["sharpa", "wuji"])
    ap.add_argument("--press", type=float, default=0.001)
    ap.add_argument("--stroke", type=float, default=0.06)
    ap.add_argument("--squeeze", type=float, default=0.018)
    ap.add_argument("--tipz", type=float, default=-0.002)
    ap.add_argument("--thumbz", type=float, default=0.004)
    ap.add_argument("--floor-clear", type=float, default=0.016)
    ap.add_argument("--grip-clear", type=float, default=0.010)
    ap.add_argument("--stop-after", type=int, default=0)
    args = ap.parse_args()
    s = Session(hand=args.hand)
    a = Author(s)
    m, d = s.model, s.data
    q = s.initial_targets.copy()
    brush = d.xpos[m.body("brush").id].copy()
    print("brush at", brush.round(4), "boot", d.xpos[m.body("boot").id].round(4))
    fingers = list(range(6, s.action_dim))
    # pre-grasp: thumb on the near (-y) face, three fingers on the far (+y) face, tips at the back's mid height
    half_w = 0.018
    def targets(clear):
        rt, r = PAD[s.hand]
        t = {
            "thumb": brush + [0.0, -(half_w + rt + clear), args.thumbz],
            "index": brush + [-0.024, half_w + r + clear, args.tipz],
            "middle": brush + [0.0, half_w + r + clear, args.tipz],
            "ring": brush + [0.024, half_w + r + clear, args.tipz],
        }
        return t
    avoid = [(m.geom("brush_back").id, 0.002), (m.geom("counter").id, args.floor_clear)]
    seeds = [q.copy()]
    if s.hand == "wuji":
        for flex in (0.4, 0.7, 1.0):
            seed = q.copy()
            for base in (10, 14, 18):  # index, middle, ring: J0 (MCP), J2, J3 flexion
                seed[base], seed[base + 2], seed[base + 3] = flex, flex, 0.5 * flex
            seed[6], seed[8] = 0.6, 0.5
            seeds.append(np.clip(seed, s.lo, s.hi))
    best = None
    for seed in seeds:
        q_try, c_try = a.solve(seed, targets(0.012), list(range(0, 6)) + fingers, avoid=avoid)
        print("  seed cost", round(c_try, 6))
        if best is None or c_try < best[1]:
            best = (q_try, c_try)
    q_pre, cost = best
    print("pre-grasp cost", cost, q_pre.round(3).tolist())
    a.fk(q_pre)
    for f, g in a.tip_ids.items():
        print("  pre", f, a.scratch.geom_xpos[g].round(4), targets(0.012).get(f))
    grip_avoid = [(m.geom("counter").id, args.floor_clear - 0.002 if s.hand == "sharpa" else args.grip_clear)]
    q_grip, cost = a.solve(q_pre, targets(-args.squeeze), fingers, avoid=grip_avoid)
    a.fk(q_grip)
    for f, g in a.tip_ids.items():
        print("  grip", f, a.scratch.geom_xpos[g].round(4), targets(-args.squeeze).get(f))
    print("grip cost", cost)
    q_above = q_pre.copy()
    q_above[2] += 0.10
    st = a.move(q, q_above, 50, "approach")
    st = a.move(q_above, q_pre, 50, "descend")
    st = a.hold(q_pre, 10, "settle")
    st = a.move(q_pre, q_grip, 30, "close")
    st = a.hold(q_grip, 20, "grip")
    for c in d.contact[: d.ncon]:
        n1, n2 = m.geom(c.geom1).name, m.geom(c.geom2).name
        if "brush" in n1 + n2:
            fr = np.zeros(6); mujoco.mj_contactForce(m, d, list(d.contact).index(c) if False else 0, fr)
            print("  contact", n1, n2, round(float(c.dist), 4))
    print("q_grip", q_grip.round(3).tolist())
    # lift so the pad clears the sole + clods
    boot_z = d.xpos[m.body("boot").id][2]
    q_lift = q_grip.copy()
    q_lift[2] += (boot_z + 0.05) - a.pad()[2] + 0.010
    st = a.move(q_grip, q_lift, 100, "lift")
    st = a.hold(q_lift, 15, "lift-hold")
    print("pad after lift", a.pad().round(4), "brush", d.xpos[m.body("brush").id].round(4))
    boot = d.xpos[m.body("boot").id].copy()
    strokes = [(boot[0] - 0.066, +1), (boot[0] - 0.066, -1), (boot[0] + 0.060, +1), (boot[0] + 0.060, -1)]
    q_cur = q_lift.copy()
    for k, (cx, sign) in enumerate(strokes):
        pad = a.pad()
        q_over = q_cur.copy()
        q_over[0] += cx - pad[0]
        q_over[1] += boot[1] - pad[1]
        st = a.move(q_cur, q_over, 60, f"stroke{k}-over")
        if st["done"]:
            break
        # lower until the pad touches the boot, then press slightly
        q_low = q_over.copy()
        target = d.xpos[m.body("boot").id][2] + 0.0115 + 0.0  # pad half height above the sole plane
        q_low[2] += target - a.pad()[2]
        st = a.move(q_over, q_low, 40, f"stroke{k}-lower")
        for _ in range(40):
            if st["features"].get("pad_on_boot"):
                break
            q_low[2] -= 0.0007
            st = a.step(q_low, f"stroke{k}-probe")
        q_low[2] -= args.press
        st = a.hold(q_low, 10, f"stroke{k}-press")
        q_end = q_low.copy()
        q_end[1] += sign * args.stroke
        st = a.move(q_low, q_end, 75, f"stroke{k}-sweep")
        if st["done"]:
            break
        q_up = q_end.copy()
        q_up[2] += 0.035
        st = a.move(q_end, q_up, 30, f"stroke{k}-up")
        q_cur = q_up
        if st["done"]:
            break
    if not s.done:
        q_away = q_cur.copy()
        q_away[2] += 0.06
        q_away[1] -= 0.10
        st = a.move(q_cur, q_away, 60, "withdraw")
        st = a.hold(q_away, 200, "hold")
    print("final", {k: v for k, v in st.items() if k != "features"})
    print("features", st["features"])
    rows = np.asarray(a.rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.out, actions=rows, hand=np.array(s.hand), task=np.array("boot_sole_brush"))
    Path(args.out).with_suffix(".log.json").write_text(json.dumps(a.log, indent=1))


if __name__ == "__main__":
    main()
