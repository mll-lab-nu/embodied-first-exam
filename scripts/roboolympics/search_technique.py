#!/usr/bin/env python3
"""Find a reference technique offline (RoboOlympics' method, kit/throwing/optimize.py by pingyue): CMA-ES over a few
key poses of the whole body, their times and the release time, each trial played in the family's frozen instance
(oracles/<family>/oracle.py `play`, the same code the reference solution runs) and scored from what the referee and
the implement do. The key poses are searched in synergies of the joints that keep both feet flat where they stand
(crouch, shift, sway and the pelvis' turn) plus the waist and the arms' joints by name; the rest stay where the start
has them.

    scripts/roboolympics/dev.sh /rfo/search_technique.py shot-put --gens 300 --workers 14 --out /out/shot.json
    RFO_RW=1 scripts/roboolympics/dev.sh /rfo/search_technique.py shot-put --embed /out/shot.json

The search is not run by CI or by make_oracles.py; its result is the TECHNIQUE literal of the oracle."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import multiprocessing as mp
import pathlib
import sys
import time

import mujoco
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
from rcb_rfo import Session  # noqa: E402

LEGS = ("crouch", "shift", "sway", "turn")
IK_STEPS = 6


def load_oracle(fam: str):
    spec = importlib.util.spec_from_file_location(f"oracle_{fam.replace('-', '_')}", HERE / "oracles" / fam / "oracle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Pose:
    """Joint positions from synergy values: the legs keep both feet flat and where they stand (crouch: the knees;
    shift: the pelvis sideways, the legs a parallelogram; sway: the pelvis forward (+) or back), the pelvis turned (+
    to the left) about the vertical through the middle of the feet by Gauss-Newton IK on the legs, the waist and the
    arms by name; every other joint as in `base`."""

    def __init__(self, world, upper: tuple[str, ...]):
        m = self.m = world.m
        self.d = mujoco.MjData(m)
        r = world.robot
        self.names = [j[:-6] for j in world.L.JOINTS]
        self.adr = r.qadr
        self.fq = r.fq
        self.upper = [self.names.index(n) for n in upper]
        st = r.stance
        self.lean = float(st[self.names.index("left_hip_pitch")] + st[self.names.index("left_knee")] / 2)
        self.legs = []
        for side in ("left", "right"):
            idx = [i for i, n in enumerate(self.names) if n.startswith(side) and n.split("_")[1] in ("hip", "knee", "ankle")]
            self.legs.append((m.jnt_bodyid[m.joint(f"{side}_ankle_roll_joint").id], idx,
                              [int(m.jnt_dofadr[m.joint(self.names[i] + "_joint").id]) for i in idx]))
        self.yaw = [self.names.index(f"{side}_hip_yaw") for side in ("left", "right")]

    def __call__(self, s, base) -> np.ndarray:
        q = np.asarray(base, float).copy()
        crouch, shift, sway, turn = s[:4]
        for side in ("left", "right"):
            ix = lambda j: self.names.index(f"{side}_{j}")  # noqa: E731
            q[ix("knee")] = crouch
            q[ix("hip_pitch")] = -crouch / 2 + self.lean + sway
            q[ix("ankle_pitch")] = -crouch / 2 - self.lean - sway
            q[ix("hip_roll")], q[ix("ankle_roll")] = shift, -shift
            q[ix("hip_yaw")] = 0.0
        q[self.upper] = s[4:]
        return self.turned(q, float(turn)) if abs(turn) > 1e-9 else q

    def feet(self, q):
        d = self.d
        d.qpos[:] = self.m.qpos0
        d.qpos[self.fq:self.fq + 7] = (0, 0, 0, 1, 0, 0, 0)
        d.qpos[self.adr] = q
        mujoco.mj_kinematics(self.m, d)
        mujoco.mj_comPos(self.m, d)
        return [(d.xpos[b].copy(), d.xmat[b].reshape(3, 3).copy()) for b, _, _ in self.legs]

    def turned(self, q, turn):
        c, s = math.cos(turn), math.sin(turn)
        R = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
        start = self.feet(q)
        mid = (start[0][0] + start[1][0]) / 2
        want = [(mid + R @ (p - mid), R @ M) for p, M in start]
        q = q.copy()
        q[self.yaw] = -turn
        jp, jr = np.zeros((3, self.m.nv)), np.zeros((3, self.m.nv))
        for _ in range(IK_STEPS):
            for (b, idx, dofs), (p, M), (wp, wM) in zip(self.legs, self.feet(q), want):
                E = wM @ M.T
                err = np.concatenate([wp - p, 0.5 * np.array([E[2, 1] - E[1, 2], E[0, 2] - E[2, 0], E[1, 0] - E[0, 1]])])
                mujoco.mj_jacBody(self.m, self.d, jp, jr, b)
                J = np.vstack([jp[:, dofs], jr[:, dofs]])
                q[idx] += J.T @ np.linalg.solve(J @ J.T + 1e-6 * np.eye(6), err)
        return q


# ------------------------------------------------------------------------------------------------ the families
class Spec:
    """A family's search: the joints named in a key (after the four leg synergies), the start keys (dicts by name:
    unnamed ones as at t = 0), times, release, the search step per synergy, and score(trial)."""
    upper: tuple = ()
    step_legs = np.array([0.3, 0.06, 0.06, 0.25])
    step_upper = 0.5
    keys: list = []
    times: tuple = ()
    release: float = 0.0
    hand = "right"
    prelude: list = []
    legs = None                                            # "walk": the walking policy has the legs (no leg synergies)
    n_extra = 0                                            # searched values of the walk before the keys

    def prelude_of(self, extra) -> list:
        return self.prelude
    recover_kw: dict = {}

    def track_reset(self, w, o) -> None:
        pass

    def track(self, w, o) -> None:
        pass

    def score(self, out: dict) -> float:
        raise NotImplementedError


def ballistic(p, v, z0=0.0, g=9.81) -> np.ndarray:
    """Where a point mass from p with velocity v comes down to height z0 (no drag)."""
    a, b, c = -0.5 * g, v[2], p[2] - z0
    disc = b * b - 4 * a * c
    t = (-b - math.sqrt(max(disc, 0.0))) / (2 * a)
    return np.array([p[0] + v[0] * t, p[1] + v[1] * t])


class Throw(Spec):
    """A throw measured from a circle (centre, radius) inside a sector: the score is the referee's distance (before
    the landing, the drag-free reach from the release) towards the sector's middle; a rule broken while holding it
    scores below every release, a fall or a foul after the release below every valid throw, a success above."""
    centre, radius, half_sector_deg = (0.0, 0.0), 1.0675, 17.46
    hold_fouls = ("not put", "below", "behind", "touched by", "turned the back")

    def score(self, o):
        ref = o["ref"]
        if o["release"] is None:                               # never let go: a fall or a rule broken while holding it
            return -100 + 40 * min(o["t_end"] / 2.0, 1.0) + 2 * o["vmax"]
        p, v = o["release"]
        land = ballistic(p, v) - np.asarray(self.centre)
        reach = math.hypot(*land) - self.radius
        head = abs(math.degrees(math.atan2(land[1], land[0])))
        aim = math.exp(-max(0.0, head - 0.8 * self.half_sector_deg) / 10.0)
        why = ref.failed or ""
        if any(k in why for k in self.hold_fouls):
            return -40 + 0.5 * reach * aim + 10 * o["metrics"].get("release_push_fraction", 0.0)
        dist = o["metrics"].get("distance_m", reach)
        if o["success"]:
            return dist * aim + 20
        if "short" in why or "outside the sector" in why:
            return dist * aim
        if "head first" in why:
            return dist * aim - 10
        return dist * aim - 15


class ShotPut(Throw):
    upper = ("torso", "right_shoulder_pitch", "right_shoulder_roll", "right_shoulder_yaw", "right_elbow_pitch",
             "right_elbow_roll", "right_wrist_pitch", "right_wrist_yaw", "left_shoulder_pitch", "left_shoulder_roll",
             "left_shoulder_yaw", "left_elbow_pitch")
    ARM0 = dict(right_shoulder_pitch=-0.155, right_shoulder_roll=-0.024, right_shoulder_yaw=0.278,
                right_elbow_pitch=-0.94, right_elbow_roll=-1.036, right_wrist_pitch=-0.46, right_wrist_yaw=-1.26)
    keys = [dict(crouch=0.75, sway=-0.04, turn=-0.3, torso=-0.7, left_shoulder_pitch=-1.3, **ARM0),
            dict(crouch=0.25, sway=0.02, turn=0.3, torso=0.6, right_shoulder_pitch=-2.0, right_shoulder_roll=-0.2,
                 right_shoulder_yaw=0.2, right_elbow_pitch=0.4, right_elbow_roll=-1.0, right_wrist_pitch=0.0,
                 right_wrist_yaw=-0.6, left_shoulder_pitch=0.3),
            dict(crouch=0.30, sway=0.0, turn=0.3, torso=0.8, right_shoulder_pitch=-2.2, right_elbow_pitch=1.3,
                 right_elbow_roll=-1.0, left_shoulder_pitch=0.3),
            dict(crouch=0.45, turn=0.1, torso=0.2, right_shoulder_pitch=-0.5, right_elbow_pitch=1.0)]
    times = (0.6, 0.95, 1.15, 2.2)
    release = 1.05


SIDE_ARM = ("torso", "right_shoulder_pitch", "right_shoulder_roll", "right_shoulder_yaw", "right_elbow_pitch",
            "right_elbow_roll", "right_wrist_pitch", "right_wrist_yaw", "left_shoulder_pitch", "left_shoulder_roll",
            "left_elbow_pitch")


class Discus(Throw):
    """A standing throw: the trunk wound far to the right with the arm out at the side, then unwound; the release
    as the hand passes the front."""
    centre, radius = (0.0, 0.0), 1.25
    upper = SIDE_ARM
    keys = [dict(crouch=0.65, turn=-0.35, torso=-1.9, right_shoulder_roll=-1.4, right_elbow_pitch=1.57,
                 left_shoulder_pitch=-1.0, left_shoulder_roll=0.4, left_elbow_pitch=1.0),
            dict(crouch=0.55, turn=-0.2, torso=-1.0, right_shoulder_roll=-1.4, right_elbow_pitch=1.57,
                 left_shoulder_pitch=-0.5, left_shoulder_roll=0.4),
            dict(crouch=0.45, turn=0.3, torso=0.4, right_shoulder_roll=-1.9, right_shoulder_pitch=-0.3,
                 right_elbow_pitch=1.57, left_shoulder_pitch=0.4, left_shoulder_roll=0.6),
            dict(crouch=0.45, turn=0.35, torso=1.2, right_shoulder_roll=-1.6, right_elbow_pitch=1.57),
            dict(crouch=0.45, turn=0.1, torso=0.2, right_shoulder_roll=-0.3, right_elbow_pitch=1.2)]
    times = (0.9, 1.25, 1.45, 1.65, 2.8)
    release = 1.42


class Javelin(Throw):
    """A standing throw: the trunk wound to the right, the arm raised at the side, the hand above the shoulder, then
    the trunk's turn (RoboOlympics' javelin technique for the G1); the release in front, above the shoulder."""
    centre, radius, half_sector_deg = (-8.0, 0.0), 8.0, 14.48
    upper = SIDE_ARM
    keys = [dict(crouch=0.6, turn=-0.35, torso=-1.5, right_shoulder_roll=-2.0, right_elbow_pitch=1.3,
                 left_shoulder_pitch=-1.0, left_shoulder_roll=0.4, left_elbow_pitch=1.0),
            dict(crouch=0.5, turn=-0.2, torso=-0.8, right_shoulder_roll=-2.0, right_elbow_pitch=1.3,
                 left_shoulder_pitch=-0.5, left_shoulder_roll=0.4),
            dict(crouch=0.45, turn=0.3, torso=0.3, right_shoulder_roll=-2.3, right_shoulder_pitch=-0.6,
                 right_elbow_pitch=1.4, left_shoulder_pitch=0.4, left_shoulder_roll=0.6),
            dict(crouch=0.45, turn=0.35, torso=1.0, right_shoulder_roll=-1.5, right_elbow_pitch=1.4),
            dict(crouch=0.45, turn=0.1, torso=0.2, right_shoulder_roll=-0.3, right_elbow_pitch=1.2)]
    times = (0.9, 1.25, 1.45, 1.65, 2.8)
    release = 1.4
    recover_kw = dict(vx=-0.4)


class Serve(Spec):
    """An underarm serve: the left fist tosses the ball a little, the right arm, straight, swings forward and up from
    behind with the trunk's turn and hits it in front of the hip. Scored on where the drag-free flight from just after
    the hit crosses the net and comes down, and on the referee's stages."""
    hand = "left"
    upper = ("torso", "right_shoulder_pitch", "right_shoulder_roll", "right_shoulder_yaw", "right_elbow_pitch",
             "left_shoulder_pitch", "left_shoulder_roll", "left_shoulder_yaw", "left_elbow_pitch")
    keys = [dict(crouch=0.5, torso=-0.5, right_shoulder_pitch=0.9, right_shoulder_roll=-0.1, right_elbow_pitch=1.57,
                 left_shoulder_yaw=-0.6),
            dict(crouch=0.5, torso=-0.6, right_shoulder_pitch=1.1, right_elbow_pitch=1.57, left_shoulder_pitch=-0.5,
                 left_shoulder_yaw=-0.6),
            dict(crouch=0.45, torso=0.3, right_shoulder_pitch=-0.8, right_shoulder_roll=0.2, right_elbow_pitch=1.57,
                 left_shoulder_pitch=-0.3),
            dict(crouch=0.4, torso=0.2, right_shoulder_pitch=-1.5, right_elbow_pitch=1.4),
            dict(crouch=0.4, torso=0.0, right_shoulder_pitch=0.0, right_elbow_pitch=1.2)]
    times = (0.7, 1.1, 1.45, 1.7, 2.6)
    release = 1.0
    recover_kw = dict(back_s=0.0)
    net_x, court = 9.5, (9.5, 18.5, 4.5)

    def track_reset(self, w, o):
        o.update(near=9.0, post=None, t_hit=None)
        self.palm = w.robot.palm["right"]

    def track(self, w, o):
        ref = w.ref
        if o["release"] is not None and not ref.has("hit"):
            o["near"] = min(o["near"], float(np.linalg.norm(w.pos("ball") - w.d.site_xpos[self.palm])))
        if ref.has("hit") and o["t_hit"] is None:
            o["t_hit"] = w.t
        if o["t_hit"] is not None and o["post"] is None and w.t - o["t_hit"] >= 0.05:
            o["post"] = (w.pos("ball").copy(), w.vel("ball").copy())

    def score(self, o):
        ref = o["ref"]
        if o["release"] is None:
            return -150 + 20 * min(o["t_end"] / 2.0, 1.0)
        if o["post"] is None:
            return -100 - 20 * min(o["near"], 2.0)
        p, v = o["post"]
        x0, x1, hw = self.court
        if v[0] <= 0.1:
            return -60 + v[0]
        t = (self.net_x - p[0]) / v[0]
        z_net = p[2] + v[2] * t - 4.905 * t * t
        land = ballistic(p, v)
        m_net = z_net - (2.43 + 0.105)
        m_land = min(land[0] - x0, x1 - land[0], hw - abs(land[1]))
        sc = -50 + 20 * float(np.clip(m_net, -2.0, 0.5)) + 5 * float(np.clip(m_land, -5.0, 2.0))
        sc += 30 * ref.has("over the net") + 50 * bool(o["success"])
        return sc


class Pass(Spec):
    """A ball that comes to the robot (bump, set): an optional walk first (the walking policy, `prelude`), then the
    key poses; no grip. Scored on how near a palm comes to the ball before the contact, then on the drag-free flight
    from just after it: its highest point against the height asked and where it comes down against the target."""
    hand = None
    legs = "walk"
    step_legs = np.zeros(4)
    first, need = "pass", 2.43 + 0.105
    upper = ("torso", "left_shoulder_pitch", "left_shoulder_roll", "left_shoulder_yaw", "left_elbow_pitch",
             "right_shoulder_pitch", "right_shoulder_roll", "right_shoulder_yaw", "right_elbow_pitch")
    recover_kw = dict(back_s=0.0)

    def track_reset(self, w, o):
        o.update(near=9.0, post=None, t_hit=None)
        self.palms = [w.robot.palm[s] for s in ("left", "right")]
        self.elbows = [w.m.body(f"{s}_elbow_roll_link").id for s in ("left", "right")]
        self.target = np.asarray(w.task.privileged(w)["target"]["centre"][:2], float)

    def track(self, w, o):
        ref = w.ref
        if not ref.has(self.first):
            b = w.pos("ball")
            pts = [w.d.site_xpos[i] for i in self.palms] + [(w.d.site_xpos[i] + w.d.xpos[e]) / 2
                                                             for i, e in zip(self.palms, self.elbows)]
            o["near"] = min(o["near"], min(float(np.linalg.norm(b - q)) for q in pts))
        elif o["t_hit"] is None:
            o["t_hit"] = w.t
        if o["t_hit"] is not None and o["post"] is None and w.t - o["t_hit"] >= 0.05:
            o["post"] = (w.pos("ball").copy(), w.vel("ball").copy())

    def score(self, o):
        """Every pass above every touch that is no pass, and that above no touch at all."""
        ref = o["ref"]
        if o["post"] is None:
            out = o["metrics"].get("speed_out_m_s")
            if out is not None:                                # touched, but not a pass / set: how fast it left
                return -200 + 3 * min(out, 10.0) - 20 * min(o["near"], 1.0)
            return -250 - 20 * min(o["near"], 2.0)
        p, v = o["post"]
        apex = p[2] + max(v[2], 0.0) ** 2 / 19.62
        land = ballistic(p, v)
        miss = float(np.linalg.norm(land - self.target))
        miss = o["metrics"].get("from_target_centre_m", miss)  # the referee's, once the ball is down
        apex = o["metrics"].get(f"{self.first}_apex_m") or apex
        sc = 15 * float(np.clip(apex - self.need, -3.0, 0.5)) - 5 * min(miss, 10.0)
        why = ref.failed or ""
        if why and not any(k in why for k in ("outside the target", "rise", "did not reach")):
            sc -= 25                                           # a foul after the contact (a second touch, a fall)
        return sc + 30 * (len(ref.stages) >= 2) + 60 * bool(o["success"])


class Bump(Pass):
    """The walk to where the serve comes down first (forwards and to the left: speeds and length searched), then at
    rest until 2.7 s; then the platform of the referee test (both arms out and down, the elbows nearly straight: a
    still forearm already returns the serve above the net) turned and lifted a little by the keys."""
    prelude = [(0.375, 0.27, 0.0, 2.0), (0.0, 0.0, 0.0, 0.7)]
    n_extra = 3
    step_upper = 0.25
    keys = [dict(left_shoulder_pitch=-0.6, left_elbow_pitch=1.2, right_shoulder_pitch=-0.6, right_elbow_pitch=1.2),
            dict(torso=-0.15, left_shoulder_pitch=-0.6, left_elbow_pitch=1.2, right_shoulder_pitch=-0.6,
                 right_elbow_pitch=1.2),
            dict(torso=-0.15, left_shoulder_pitch=-0.8, left_elbow_pitch=1.2, right_shoulder_pitch=-0.8,
                 right_elbow_pitch=1.2),
            dict()]
    times = (0.8, 1.6, 1.9, 2.8)

    def prelude_of(self, e):
        vx, vy, secs = 0.375 + 0.1 * e[0], 0.27 + 0.1 * e[1], float(np.clip(2.0 + 0.3 * e[2], 0.5, 2.6))
        return [(vx, vy, 0.0, round(secs, 2)), (0.0, 0.0, 0.0, round(2.7 - secs, 2))]


class Set(Pass):
    """At rest on the walking policy until just before the toss comes down, then the fists of the referee test held
    above the forehead with the elbows bent, driven up and a little forward through the ball."""
    first, need = "set", 2.43 + 1.0 + 0.105
    prelude = [(0.0, 0.0, 0.0, 3.0)]
    step_upper = 0.25
    keys = [dict(left_shoulder_pitch=-2.7, left_shoulder_roll=0.2, left_elbow_pitch=0.6,
                 right_shoulder_pitch=-2.7, right_shoulder_roll=-0.2, right_elbow_pitch=0.6),
            dict(left_shoulder_pitch=-2.7, left_shoulder_roll=0.2, left_elbow_pitch=0.6,
                 right_shoulder_pitch=-2.7, right_shoulder_roll=-0.2, right_elbow_pitch=0.6),
            dict(left_shoulder_pitch=-2.6, left_shoulder_roll=0.2, left_elbow_pitch=1.5,
                 right_shoulder_pitch=-2.6, right_shoulder_roll=-0.2, right_elbow_pitch=1.5),
            dict()]
    times = (0.8, 1.30, 1.45, 2.4)


SPECS = {"shot-put": ShotPut, "discus": Discus, "javelin": Javelin, "volleyball-serve": Serve, "volleyball-bump": Bump,
         "volleyball-set": Set}


# ------------------------------------------------------------------------------------------------ one trial
class Trial:
    def __init__(self, fam: str):
        self.fam, self.spec = fam, SPECS[fam]()
        self.oracle = load_oracle(fam)
        self.s = Session(str(HERE / "instances" / f"{fam}-i00.json"))
        w = self.s.world
        self.pose = Pose(w, self.spec.upper)
        self.q0 = w.d.qpos[w.robot.qadr].copy()
        self.base = self.q0.copy()
        names = list(LEGS) + list(self.spec.upper)
        self.k0 = np.array([[k.get(n, self._start(n)) for n in names] for k in self.spec.keys])
        self.step = np.r_[self.spec.step_legs, np.full(len(self.spec.upper), self.spec.step_upper)]
        self.nk = len(self.spec.keys)
        self.size = self.k0.size + self.nk + self.spec.n_extra + 1

    def _start(self, n):
        i = self.pose.names.index
        st = self.q0
        return {"crouch": st[i("left_knee")], "shift": 0.0, "sway": 0.0, "turn": 0.0}.get(n) if n in LEGS else st[i(n)]

    def technique(self, x) -> dict:
        s = self.k0 + x[:self.k0.size].reshape(self.k0.shape) * self.step
        dt = np.diff(np.r_[0.0, self.spec.times]) * np.exp(0.3 * np.clip(x[self.k0.size:self.k0.size + self.nk], -2, 2))
        extra = x[self.k0.size + self.nk:self.k0.size + self.nk + self.spec.n_extra]
        times = np.cumsum(dt)
        release = float(np.clip(self.spec.release + 0.1 * x[-1], 0.05, times[-1]))
        r = self.s.world.robot
        keys = [np.clip(self.pose(k, self.base), r.lo, r.hi) for k in s]
        tech = {"keys": [[round(float(v), 4) for v in k] for k in keys], "times": [round(float(t), 4) for t in times],
                "release_s": round(release, 4), "hand": self.spec.hand}
        if self.spec.legs:
            tech["legs"] = self.spec.legs
        prelude = self.spec.prelude_of(extra)
        if prelude:
            tech["prelude"] = [[round(float(v), 4) for v in p] for p in prelude]
        return tech

    def run(self, tech, full: bool = True) -> dict:
        s = self.s
        s.reset()
        w = s.world
        o = {"release": None, "vmax": 0.0}
        self.spec.track_reset(w, o)
        name = next((n for n in w.held.values() if n), None)

        def watch(s):
            self.spec.track(w, o)
            if o["release"] is None and name is not None:
                if w.holder(name):
                    o["vmax"] = max(o["vmax"], float(np.linalg.norm(w.vel(name))))
                else:
                    o["release"] = (w.pos(name).copy(), w.vel(name).copy())
            if not full and w.ref.has("landing"):
                raise StopIteration
        try:
            if not self.oracle.play(s, tech, watch=watch):
                self.oracle.recover(s, watch=watch, **self.spec.recover_kw)
        except StopIteration:
            pass
        st = w.ref
        o.update(ref=st, metrics=dict(st.metrics), success=bool(st.success), t_end=w.t)
        return o

    def score(self, x) -> tuple[float, bool, dict]:
        tech = self.technique(x)
        o = self.run(tech)
        return self.spec.score(o), bool(o["success"]), {"failed": o["ref"].failed, **o["metrics"], "t": round(o["t_end"], 2)}


class CMA:
    """Hansen's CMA-ES (maximising), seeded (as RoboOlympics' kit/throwing/optimize.py)."""

    def __init__(self, x0, sigma, lam, seed=0):
        n = len(x0)
        self.n, self.lam, self.mu = n, lam, lam // 2
        w = np.log(self.mu + 0.5) - np.log(np.arange(1, self.mu + 1))
        self.w = w / w.sum()
        self.mueff = 1 / (self.w ** 2).sum()
        self.cc = (4 + self.mueff / n) / (n + 4 + 2 * self.mueff / n)
        self.cs = (self.mueff + 2) / (n + self.mueff + 5)
        self.c1 = 2 / ((n + 1.3) ** 2 + self.mueff)
        self.cmu = min(1 - self.c1, 2 * (self.mueff - 2 + 1 / self.mueff) / ((n + 2) ** 2 + self.mueff))
        self.damps = 1 + 2 * max(0.0, math.sqrt((self.mueff - 1) / (n + 1)) - 1) + self.cs
        self.chin = math.sqrt(n) * (1 - 1 / (4 * n) + 1 / (21 * n * n))
        self.m, self.sigma = np.array(x0, float), sigma
        self.pc, self.ps = np.zeros(n), np.zeros(n)
        self.B, self.D, self.C = np.eye(n), np.ones(n), np.eye(n)
        self.rng, self.gen = np.random.default_rng(seed), 0

    def ask(self):
        self.z = self.rng.standard_normal((self.lam, self.n))
        self.y = self.z * self.D @ self.B.T
        return self.m + self.sigma * self.y

    def tell(self, f):
        idx = np.argsort(-np.asarray(f))[:self.mu]
        yw, zw = self.w @ self.y[idx], self.w @ self.z[idx]
        self.m = self.m + self.sigma * yw
        self.ps = (1 - self.cs) * self.ps + math.sqrt(self.cs * (2 - self.cs) * self.mueff) * (self.B @ zw)
        self.gen += 1
        hs = np.linalg.norm(self.ps) / math.sqrt(1 - (1 - self.cs) ** (2 * self.gen)) / self.chin < 1.4 + 2 / (self.n + 1)
        self.pc = (1 - self.cc) * self.pc + hs * math.sqrt(self.cc * (2 - self.cc) * self.mueff) * yw
        Y = self.y[idx]
        self.C = ((1 - self.c1 - self.cmu) * self.C
                  + self.c1 * (np.outer(self.pc, self.pc) + (1 - hs) * self.cc * (2 - self.cc) * self.C)
                  + self.cmu * (Y.T * self.w) @ Y)
        self.sigma *= math.exp((self.cs / self.damps) * (np.linalg.norm(self.ps) / self.chin - 1))
        self.C = np.triu(self.C) + np.triu(self.C, 1).T
        d2, self.B = np.linalg.eigh(self.C)
        self.D = np.sqrt(np.maximum(d2, 1e-20))


_T = None


def _init(fam):
    global _T
    _T = Trial(fam)


def _score(x):
    return _T.score(x)


def search(a) -> None:
    t0 = time.time()
    _init(a.family)
    x0 = np.zeros(_T.size)
    if a.start:
        x0 = np.asarray(json.loads(pathlib.Path(a.start).read_text())["x"], float)
    es = CMA(x0, a.sigma, a.lam, a.seed)
    best = None
    with mp.Pool(a.workers, initializer=_init, initargs=(a.family,)) as pool:
        f0 = pool.apply(_score, (x0,))
        print("start:", round(f0[0], 2), f0[2], flush=True)
        best = (f0[0], f0[1], x0, f0[2])
        for g in range(a.gens):
            X = es.ask()
            F = pool.map(_score, X)
            es.tell([f for f, _, _ in F])
            for (f, ok, info), x in zip(F, X):
                if f > best[0]:
                    best = (f, ok, x.copy(), info)
            if g % 5 == 0 or g == a.gens - 1:
                print(f"gen {g} ({time.time() - t0:.0f} s): best {best[0]:.2f} success={best[1]} {best[3]} | "
                      f"gen top {max(f for f, _, _ in F):.2f} | succ {sum(ok for _, ok, _ in F)}/{len(F)} | "
                      f"sigma {es.sigma:.3f}", flush=True)
                pathlib.Path(a.out).write_text(json.dumps({"family": a.family, "score": best[0], "success": best[1],
                                                           "info": best[3], "x": best[2].tolist(),
                                                           "technique": _T.technique(best[2])}) + "\n")
            if best[1] and a.stop_on_success and best[0] >= a.stop_score:
                break


def embed(a) -> None:
    res = json.loads(pathlib.Path(a.embed).read_text())
    tech = res["technique"]
    tech.setdefault("hand", SPECS[a.family].hand)              # (results written before the technique carried them)
    if SPECS[a.family].prelude:
        tech.setdefault("prelude", [list(x) for x in SPECS[a.family].prelude])
    src_path = HERE / "oracles" / a.family / "oracle.py"
    src = src_path.read_text()
    keys = ",\n".join("        [" + ", ".join(f"{v:g}" for v in k) + "]" for k in tech["keys"])
    extra = "".join(f", {json.dumps(k)}: {tech[k]!r}" for k in ("hand", "legs", "prelude") if k in tech)
    lit = (f"TECHNIQUE = {{\"times\": {tech['times']}, \"release_s\": {tech['release_s']}{extra}, \"keys\": [\n{keys}]}}")
    import re
    new, n = re.subn(r"^TECHNIQUE = (None|\{.*?\]\]\})[^\n]*", lambda _: lit, src, count=1, flags=re.S | re.M)
    assert n == 1, "no TECHNIQUE literal"
    src_path.write_text(new)
    print("embedded", a.family, res["score"], res["info"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("family")
    ap.add_argument("--gens", type=int, default=200)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--lam", type=int, default=48)
    ap.add_argument("--sigma", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="/out/technique.json")
    ap.add_argument("--start", help="a previous --out file to start from")
    ap.add_argument("--stop-on-success", action="store_true")
    ap.add_argument("--stop-score", type=float, default=0.0)
    ap.add_argument("--embed", help="write this --out file's technique into the oracle")
    ap.add_argument("--video", help="with --try: a video of the trial")
    ap.add_argument("--camera", default=None)
    ap.add_argument("--try", dest="try_", action="store_true", help="one trial of the start technique, verbose")
    a = ap.parse_args()
    if a.embed:
        return embed(a)
    if a.try_:
        _init(a.family)
        x = np.zeros(_T.size)
        if a.start:
            x = np.asarray(json.loads(pathlib.Path(a.start).read_text())["x"], float)
        t = time.time()
        print(_T.score(x), f"{time.time() - t:.1f} s")
        if a.video:
            from rcb_rfo import replay
            print(replay(_T.s.instance, np.asarray(_T.s.rows), video=a.video, camera=a.camera))
        return
    search(a)


if __name__ == "__main__":
    main()
