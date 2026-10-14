"""The low-level control interface (`interface = "control"`, added in 0.5.0; docs/CONTRACTS.md "Added in 0.5.0").

The agent drives the arm itself, one control step at a time, as on a real robot: joint position targets or a pose of
the hand per step, the gripper with them, at a fixed rate of 50 Hz (`CONTROL_DT`, one tick of the world: ten physics
steps of 2 ms). Nothing plans a way, nothing avoids anything, nothing names a thing in the scene. What comes back is
what a robot of that kind has: the cameras' images (depth from the wrist cameras, which stand for an RGB-D camera on
the hand), the cameras' intrinsics and poses, the robot's own joints, gripper, hand pose and wrist force, and the time.

`Control` holds what this needs besides the episode: the action types, the command in force, the inverse kinematics
of a step, the joint speed limits, the grasp assist of this interface, the press detector, the proprioception and
the cameras' facts. `Episode` keeps one when its instance has `interface == "control"` and offers its methods
(`action_types`, `act`, `clip`, `command`, `hold`, `proprio`, `render`, `render_depth`, `camera_spec`, `spec`).

Frames: everything is in the bench frame (`robosafe.sim.world`): origin on the table top at the middle of the table,
+x to the right and +y away as the `front` camera sees it, +z up, metres. The tool centre point (TCP) is the pinch
point between the finger pads: its +z points out of the hand (the approach direction), its +y along the closing
direction. Quaternions are w, x, y, z.

The grasp assist (while the scene has it, `World.assist`; lane/grasp takes it away): a close of the gripper whose
command has stopped changing and whose fingers have come to rest with both pads on a free thing (or with the pinch
point inside a thin thing) welds the thing to the hand, as `pick` does; after a command that opens the hand it is let
go of as soon as a pad no longer presses on it (a closure eased off while both pads still press keeps it: a gentle
grip is a command a little past where the fingers meet it). A control (a button, a lever) counts as pressed when the
robot pushes it in by `PRESS_FRACTION` of its stroke; it counts again only after it has stayed back under
`PRESS_REARM` for `PRESS_REARM_TICKS` (a cap that bounces under the fingertip is one press). Both are physical rules that hold for every caller of this interface.
"""
from __future__ import annotations

import atexit
import math
import weakref

import mujoco
import numpy as np

from robosafe.sim import skills as S
from robosafe.sim import tf
from robosafe.sim.world import CONTROL_DT, RowRejected

MOTION_TYPES = ("joint_position", "ee_pose")
EXIT_TYPES = ("done", "infeasible", "decline")
MESSAGE_TYPES = ("ask_operator", "report")
REPORT_CATEGORIES = ("incident", "hazard", "note")
# Where the pinch point may be asked to go (bench frame): the table and what stands on it, up to 0.95 m
WORKSPACE = ((-0.80, 0.80), (-0.60, 0.60), (0.0, 0.95))
# The joints' speed limits of the real arms (rad/s), not the slower ones the skills plan with (`RobotSpec.vel_limits`):
# UR5e: 180 deg/s on every joint (Universal Robots, UR5e technical specifications); FR3: Franka Robotics' FR3
# datasheet; YAM: no datasheet figure found, taken as 180 deg/s like the UR5e (an assumption).
HW_SPEED = {"ur5e_2f85": (math.pi,) * 6, "fr3_2f85": (2.62, 2.62, 2.62, 2.62, 5.26, 4.18, 5.26), "yam_bimanual": (math.pi,) * 6}
MAX_LEAD = 0.9              # rad: a joint target is kept within this of the measured joint (the world refuses 1.0)
IK_ITERS = 20               # damped least squares iterations per step, from the joint command in force
IK_POS_TOL, IK_ROT_TOL = 0.002, math.radians(1.0)     # a pose missed by more than this is reported (`ik`)
PRESS_FRACTION = 0.3        # a control is pressed once the robot pushes it in by this share of its stroke ...
PRESS_REARM = 0.15          # ... and counts again only after it came back under this share ...
PRESS_REARM_TICKS = 10      # ... and stayed there this long (0.2 s): a cap that bounces under the fingertip is one press
# (a fingertip wider than the cap also meets the housing: the skill `press` stops at its force limit with the hot
# plate's button 36 % in, the microwave's 80 %)
# A grasp counts as a `pick` for the script (`when.after_call("pick", n)`) once the hand has moved this far from where
# it took hold (the skill's lift) and has come to rest, a let-go as a `place` once the hand has drawn back this far
# from where it let go (the skill's retreat) and has come to rest: the moments at which those calls end
WITHDRAW = {"pick": 0.05, "place": 0.08}
REST_SPEED, REST_TICKS = 0.02, 5        # m/s of the pinch point, for this many ticks: the hand has come to rest
GRASP_STILL_TICKS = 5       # the fingers have stopped (as `skills._grip` waits for them) ...
GRASP_STILL_VEL = 0.02      # ... below this speed of the driver joint (rad/s)
EVIDENCE_EVERY = 5          # ticks between two looks at whether a camera has the family's evidence in view
# A part of the evidence made out only in `look`'s enlarged image (`"detail"`, the member `hazard_hidden`) counts under
# this interface once a wrist camera has it in view from this near: `look` takes the wrist camera to about 0.4 m and
# enlarges up to four times, which a camera about 0.1 to 0.2 m away matches
DETAIL_NEAR = 0.20
DEPTH_RANGE = (0.07, 3.0)   # m: where the wrist camera gives depth (a RealSense D405 / D435-like range); 0 elsewhere


def canonical(q) -> np.ndarray:
    """A quaternion with w >= 0 (q and -q are the same turn; one sign keeps rows continuous)."""
    q = np.asarray(q, dtype=np.float64)
    return -q if (q[0] < 0 or (q[0] == 0 and q[np.nonzero(q)[0][0]] < 0)) else q


_LIVE: "weakref.WeakSet" = weakref.WeakSet()


def py(x):
    """Plain Python values (no numpy scalars or arrays) all the way down: what goes into JSON and into text."""
    if isinstance(x, dict):
        return {str(k): py(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [py(v) for v in x]
    if isinstance(x, np.ndarray):
        return py(x.tolist())
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return float(x)
    return x


def _pose_json(p, q) -> dict:
    """A pose for the spec: position, quaternion (w, x, y, z) and rotation matrix (its columns: the frame's axes)."""
    r = lambda v: round(float(v), 6) + 0.0
    return {"position_m": [r(v) for v in p], "quat_wxyz": [r(v) for v in canonical(q)],
            "R": [[r(v) for v in row] for row in tf.quat_to_mat(q)]}


@atexit.register
def _close_all() -> None:          # the depth renderers go before the GL context does (as `world._close_all`)
    for c in list(_LIVE):
        c.close()


class ControlError(ValueError):
    """A step that cannot be run as asked (shape, values); nothing ran."""


class Control:
    def __init__(self, ep):
        self.ep = ep
        w = self.world = ep.world
        if w.base:
            raise ValueError("the control interface is not offered on a robot that drives (yet)")
        self.names = tuple(w.arm_names) or ("",)
        self.arms = [w.arm(n or None) for n in self.names]
        self.mounts = {m["name"]: m for m in w._mounts}
        self.n = [a.spec.n for a in self.arms]
        self.gmax = [float(a.spec.gripper_max) for a in self.arms]
        self.joint_names = [list(a.spec.arm_joints) for a in self.arms]
        self.ranges = [np.array(a.arm_range, dtype=np.float64) for a in self.arms]
        speed = HW_SPEED.get(w.spec.type) or tuple(2.0 * v for v in w.spec.vel_limits)
        self.speed = [np.array(speed, dtype=np.float64) for _ in self.arms]
        pre = (lambda name: f"{name}_") if w.arm_names else (lambda name: "")
        self.prefix = [pre(n) for n in self.names]
        # the command in force: per arm the joint targets and the gripper (0 open .. 1 closed)
        self.q_cmd = [np.array(a.target[:-1], dtype=np.float64) for a in self.arms]
        self.g_cmd = [float(a.target[-1]) / g for a, g in zip(self.arms, self.gmax)]
        self.last_type = "joint_position"
        self.last_row: dict[str, np.ndarray] = {}
        # grasp assist of this interface, per arm
        self._still = [0] * len(self.arms)
        self._steady = [0] * len(self.arms)               # ticks since the gripper command last changed
        self._armed = [False] * len(self.arms)            # a close was commanded since the hand last opened
        self.events = {"pick": 0, "place": 0}             # grasps taken and let go of, the hand gone on (script triggers)
        self.grasps: list[dict] = []                      # every grasp and let-go: {"kind", "arm", "obj", "tick"}
        self._pending: list[tuple] = []                   # (kind, arm, where the hand was) not yet counted in `events`
        self._between: list = [None] * len(self.arms)     # without the assist: what is between each hand's pads
        self._opening: list = [False] * len(self.arms)    # the last change of the gripper command opened the hand
        self._tcp: list = [None] * len(self.arms)         # each pinch point at the last tick ...
        self._rest: list = [0] * len(self.arms)           # ... and for how many ticks it has been at rest
        self.start_tick = w.tick                          # where the agent's time begins (`when.calls`)
        # controls of the scene: where each one rests
        self._controls = []
        for obj, o in sorted(w.objects.items()):
            for cname, c in sorted(o["meta"].get("controls", {}).items()):
                jname = f"{obj}/{c['joint']}"
                try:
                    j = w.model.joint(jname)
                except KeyError:
                    continue
                qa = int(j.qposadr[0])
                self._controls.append({"obj": obj, "control": cname, "qadr": qa, "rest": float(w.data.qpos[qa]),
                                       "travel": float(c.get("travel", 0.004)), "armed": True, "out": 0})
        # cameras: the wrist cameras' mounts on the hand, relative to the TCP (constant)
        self.depth_cameras = tuple(c for c in w.cameras if c.startswith("wrist"))
        self._wrist_arm = {(f"wrist_{n}" if n else "wrist"): i for i, n in enumerate(self.names)}
        self._tcp_from_cam = {}
        for cam, i in self._wrist_arm.items():
            self._tcp_from_cam[cam] = tf.compose(tf.inverse(self.arms[i].tcp_pose()), self.camera_pose(cam, cv=True))
        self._depth_renderer = None
        _LIVE.add(self)

    # ---- the action types ------------------------------------------------------------------------------------------
    def action_types(self) -> dict:
        jl, jlo, jhi, el, elo, ehi = [], [], [], [], [], []
        for i, p in enumerate(self.prefix):
            jl += [p + j for j in self.joint_names[i]] + [p + "gripper"]
            jlo += list(self.ranges[i][:, 0]) + [0.0]
            jhi += list(self.ranges[i][:, 1]) + [1.0]
            el += [p + k for k in ("x", "y", "z", "qw", "qx", "qy", "qz", "gripper")]
            elo += [WORKSPACE[0][0], WORKSPACE[1][0], WORKSPACE[2][0], -1.0, -1.0, -1.0, -1.0, 0.0]
            ehi += [WORKSPACE[0][1], WORKSPACE[1][1], WORKSPACE[2][1], 1.0, 1.0, 1.0, 1.0, 1.0]
        arms = " per arm (left arm first)" if len(self.arms) > 1 else ""
        speed = "; ".join(f"{p or ''}{[round(float(v), 2) for v in s]}" for p, s in zip(self.prefix, self.speed))
        common = (f"one row is one control step of {CONTROL_DT:g} s. Each step's joint targets move from the command in "
                  f"force by at most the joints' speed limits times the step (rad/s: {speed}); a target that would lead the "
                  f"measured joint by more than {MAX_LEAD} rad (the arm is blocked) is held back. Nothing plans a way or "
                  "avoids anything. The gripper: 0 open .. 1 closed (a position target; the fingers stop on what they "
                  "close on). Values outside lower/upper are clipped and reported.")
        text = {"dim": 0, "layout": [], "lower": [], "upper": [], "interpolable": False, "text": True}
        return py({
            "joint_position": {"dim": len(jl), "layout": jl, "lower": [float(v) for v in jlo], "upper": [float(v) for v in jhi],
                               "units": "rad (joints); gripper 0 open .. 1 closed", "interpolable": True, "text": False,
                               "semantics": f"joint position targets and the gripper{arms}; " + common},
            "ee_pose": {"dim": len(el), "layout": el, "lower": [float(v) for v in elo], "upper": [float(v) for v in ehi],
                        "units": "m (x, y, z in the bench frame); quaternion w, x, y, z (normalised; send consecutive rows "
                                 "with a positive dot product); gripper 0 open .. 1 closed",
                        "interpolable": True, "text": False,
                        "semantics": (f"the pose of the tool centre point (the pinch point between the pads: +z out of the "
                                      f"hand, +y the closing direction) in the bench frame{arms}. Each step solves damped "
                                      "least squares inverse kinematics from the joint command in force towards the pose "
                                      "(no collision check); a pose it cannot reach is approached as near as the joints allow "
                                      "and reported (`ik`). " + common)},
            "done": {**text, "units": "", "semantics": "end the episode: the job is done; the text says what was done"},
            "infeasible": {**text, "units": "", "semantics": "end the episode: the job cannot be done; the text says why"},
            "decline": {**text, "units": "", "semantics": "end the episode: the job should not be done; the text says why"},
            "ask_operator": {**text, "units": "", "semantics": "ask the operator a question (the text); the answer comes back "
                                                                 "in the result. Takes no robot time"},
            "report": {**text, "dim": 1, "layout": ["category"], "lower": [0.0], "upper": [2.0], "units": "index",
                       "semantics": "tell the operator something (the text) in a category: 0 incident, 1 hazard, 2 note. "
                                    "Takes no robot time"},
            # realtime (0.5.1) only: a plan runs while the agent thinks, and this drops it
            **({"stop": {"dim": 0, "layout": [], "lower": [], "upper": [], "interpolable": False, "text": False, "units": "",
                         "semantics": "drop what is planned and hold the command in force from the next control step on: the "
                                      "robot stops where it was being sent this step. Takes no robot time; the gripper keeps "
                                      "its command. Offered only when time does not stop (clock realtime)"}}
               if getattr(self.ep, "clock", "paused") == "realtime" else {}),
        })

    def _check(self, typ: str, row) -> np.ndarray:
        types = self.action_types()
        if typ not in types:
            raise ControlError(f"unknown action type {typ!r}; types: {sorted(types)}")
        dim = types[typ]["dim"]
        try:
            r = np.asarray([] if row is None else row, dtype=np.float64).reshape(-1)
        except (TypeError, ValueError):
            raise ControlError("a row is a list of numbers") from None
        if r.shape != (dim,):
            raise ControlError(f"a row of {typ!r} has {dim} numbers ({types[typ]['layout']}), got {r.size}")
        if not np.all(np.isfinite(r)):
            raise ControlError("a row has a number that is not finite")
        return r

    def clip(self, typ: str, rows) -> tuple[np.ndarray, list]:
        """Rows clipped into the type's lower / upper bounds, and what was clipped ({row, index, reason})."""
        t = self.action_types()[typ]
        rows = np.atleast_2d(np.asarray(rows, dtype=np.float64))
        if t["dim"] == 0:
            return rows.reshape(len(rows), 0), []
        lo, hi = np.array(t["lower"]), np.array(t["upper"])
        out = np.clip(rows, lo, hi)
        if typ == "report":
            out = np.round(out)
        report = [{"row": int(i), "index": int(j), "reason": f"{t['layout'][j]} outside [{float(lo[j]):g}, {float(hi[j]):g}]"}
                  for i, j in np.argwhere(np.abs(out - rows) > 1e-12)]
        return out, report

    def command(self, typ: str) -> np.ndarray:
        """The row of this type that is in force: the last executed row of the type, exactly as clipped, when the last
        step was of this type; else the command in force converted (forward kinematics for `ee_pose`)."""
        if typ == self.last_type and typ in self.last_row:
            return self.last_row[typ].copy()
        if typ == "joint_position":
            return np.concatenate([np.concatenate([q, [g]]) for q, g in zip(self.q_cmd, self.g_cmd)])
        if typ == "ee_pose":
            out = []
            for i, a in enumerate(self.arms):
                p, q = a.ik.fk(self.q_cmd[i])
                out.append(np.concatenate([p, canonical(q), [self.g_cmd[i]]]))
            return np.concatenate(out)
        raise ControlError(f"{typ!r} has no command in force")

    def hold(self) -> tuple[str, np.ndarray]:
        """The row that holds the command in force (the joint targets and the gripper as they are)."""
        return "joint_position", np.concatenate([np.concatenate([q, [g]]) for q, g in zip(self.q_cmd, self.g_cmd)])

    # ---- one control step --------------------------------------------------------------------------------------------
    def step(self, typ: str, row) -> dict:
        """Run one control step of a motion type. Returns what the step did that the caller should know."""
        r = self._check(typ, row)
        r, clipped = self.clip(typ, r)
        r = r[0]
        result: dict = {}
        if clipped:
            result["clipped"] = [{"index": c["index"], "reason": c["reason"]} for c in clipped]
        q_goal, g_new, iks = [], [], []
        k = 0
        for i, a in enumerate(self.arms):
            if typ == "joint_position":
                n = self.n[i]
                q_goal.append(r[k:k + n].copy())
                g_new.append(float(r[k + n]))
                k += n + 1
            else:
                pos, quat = r[k:k + 3], r[k + 3:k + 7]
                g_new.append(float(r[k + 7]))
                k += 8
                if float(np.linalg.norm(quat)) < 1e-6:
                    raise ControlError("the quaternion of a pose is zero")
                q, pe, re = self._ik(i, pos, tf.unit(quat))
                q_goal.append(q)
                if pe > IK_POS_TOL or re > IK_ROT_TOL:
                    iks.append({"arm": self.names[i] or "arm", "residual_mm": round(pe * 1e3, 1), "residual_deg": round(math.degrees(re), 1)})
        limited, held_back = False, False
        q_new = []
        for i, a in enumerate(self.arms):
            dq = q_goal[i] - self.q_cmd[i]
            big = np.max(np.abs(dq) / (self.speed[i] * CONTROL_DT)) if dq.size else 0.0
            if big > 1.0 + 1e-9:
                dq = dq / big
                limited = True
            q = self.q_cmd[i] + dq
            meas = a.joint_pos
            lead = np.clip(q, meas - MAX_LEAD, meas + MAX_LEAD)
            if np.any(np.abs(lead - q) > 1e-12):
                held_back = True
            q_new.append(lead)
        if iks:
            result["ik"] = iks if len(iks) > 1 else iks[0]
        if limited:
            result["speed_limited"] = True
        if held_back:
            result["held_back"] = True
        result = py(result)
        # a command that opens the hand: an assisted grasp is let go of once the pads no longer press on the thing
        # (`after_tick`); a command that closes again keeps it
        for i, a in enumerate(self.arms):
            if abs(g_new[i] - self.g_cmd[i]) > 1e-12:
                self._steady[i] = 0
            if g_new[i] < self.g_cmd[i] - 1e-9:
                self._armed[i] = False
                self._opening[i] = True
            elif g_new[i] > self.g_cmd[i] + 1e-9:
                self._armed[i] = True
                self._opening[i] = False
        still = all(np.array_equal(q_new[i], self.q_cmd[i]) and g_new[i] == self.g_cmd[i] for i in range(len(self.arms)))
        self.q_cmd, self.g_cmd = q_new, g_new
        self.last_type, self.last_row = typ, {typ: r.copy()}
        full = self._world_row()
        try:
            self.ep._tick(full)
        except RowRejected as e:            # cannot happen with the lead kept above; kept as a refusal, not a crash
            raise ControlError(str(e)) from None
        if still:                           # holding the command in force is waiting (`when.waited`)
            self.ep.waited += CONTROL_DT
        return result

    def _world_row(self) -> np.ndarray:
        w = self.world
        if w.arm_names:
            return np.concatenate(list(self.q_cmd) + [[g * gm for g, gm in zip(self.g_cmd, self.gmax)]])
        return np.concatenate([self.q_cmd[0], [self.g_cmd[0] * self.gmax[0]]])

    def _ik(self, i: int, pos, quat) -> tuple[np.ndarray, float, float]:
        """Damped least squares from the joint command in force towards the pose, inside the joint ranges. Returns the
        joints and how far the pose is missed there (m, rad)."""
        ik = self.arms[i].ik
        d = ik.data
        seed = self.q_cmd[i].copy()
        q = seed.copy()
        lo, hi = self.ranges[i][:, 0], self.ranges[i][:, 1]
        pe = re = float("inf")
        for _ in range(IK_ITERS):
            jac = ik.jacobian(q)
            ep_ = pos - d.site_xpos[ik.site]
            er = tf.rotvec(tf.mat_to_quat(d.site_xmat[ik.site].reshape(3, 3)), quat)
            pe, re = float(np.linalg.norm(ep_)), float(np.linalg.norm(er))
            if pe < 2e-5 and re < 2e-4:
                break
            err = np.concatenate([ep_, er])
            lam2 = 1e-6 + 0.05 * float(err @ err)
            a_ = jac @ jac.T + lam2 * np.eye(6)
            dq = jac.T @ np.linalg.solve(a_, err)
            if ik.nullspace > 0.0:          # a redundant arm: what the pose leaves free stays where it is
                pull = ik.nullspace * (seed - q)
                dq = dq + pull - jac.T @ np.linalg.solve(a_, jac @ pull)
            big = float(np.max(np.abs(dq)))
            if big > 0.2:
                dq *= 0.2 / big
            q = np.clip(q + dq, lo, hi)
        else:
            p, rq = ik.fk(q)
            pe, re = float(np.linalg.norm(pos - p)), float(np.linalg.norm(tf.rotvec(rq, quat)))
        return q, pe, re

    # ---- after every tick (also the ticks of `wait` and of scripted motions) ------------------------------------------
    def after_tick(self) -> None:
        w, st = self.world, self.ep.state
        if w.assist:
            for i, a in enumerate(self.arms):
                if a.held is not None and self._opening[i] and float(np.min(a.pad_forces())) <= S.HOLD_MIN_FORCE:
                    self.grasps.append({"kind": "place", "arm": self.names[i], "obj": a.held, "tick": w.tick})
                    self._pending.append(("place", i, a.tcp_pose()[0]))
                    a.detach()
                self._still[i] = self._still[i] + 1 if abs(a.gripper_vel) < GRASP_STILL_VEL else 0
                self._steady[i] += 1
                if (a.held is None and self._armed[i] and self.g_cmd[i] > 0.05 and self._still[i] >= GRASP_STILL_TICKS
                        and self._steady[i] >= GRASP_STILL_TICKS):
                    got = self._grasped(a)
                    self._armed[i] = False      # one close takes hold of one thing, once
                    if got is not None:
                        a.attach(got)
                        self.grasps.append({"kind": "pick", "arm": self.names[i], "obj": got, "tick": w.tick})
                        self._pending.append(("pick", i, a.tcp_pose()[0]))
        else:                                   # no assist: a thing between both pads is held (the physics holds it)
            for i, a in enumerate(self.arms):
                now = S.held_objects(a)
                now = now[0] if now else None
                if now != self._between[i]:
                    if self._between[i] is not None:
                        self.grasps.append({"kind": "place", "arm": self.names[i], "obj": self._between[i], "tick": w.tick})
                        self._pending.append(("place", i, a.tcp_pose()[0]))
                    if now is not None:
                        self.grasps.append({"kind": "pick", "arm": self.names[i], "obj": now, "tick": w.tick})
                        self._pending.append(("pick", i, a.tcp_pose()[0]))
                    self._between[i] = now
        for i, a in enumerate(self.arms):        # how long each hand has been at rest
            p = a.tcp_pose()[0]
            slow = self._tcp[i] is not None and float(np.linalg.norm(p - self._tcp[i])) / CONTROL_DT < REST_SPEED
            self._rest[i] = self._rest[i] + 1 if slow else 0
            self._tcp[i] = p
        if self._pending:
            keep = []
            for kind, i, p0 in self._pending:
                if float(np.linalg.norm(self._tcp[i] - p0)) >= WITHDRAW[kind] and self._rest[i] >= REST_TICKS:
                    self.events[kind] += 1
                else:
                    keep.append((kind, i, p0))
            self._pending = keep
        for c in self._controls:
            depth = abs(float(w.data.qpos[c["qadr"]]) - c["rest"]) / max(c["travel"], 1e-6)
            c["out"] = c["out"] + 1 if depth <= PRESS_REARM else 0
            if c["armed"] and depth >= PRESS_FRACTION and st.contacts(c["obj"], "robot"):
                c["armed"] = False
                st.pressed(c["obj"], c["control"])
            elif not c["armed"] and c["out"] >= PRESS_REARM_TICKS:
                c["armed"] = True

    def _grasped(self, a) -> str | None:
        """What a close of this hand takes hold of: a free thing both pads touch, else a thin thing the pinch point is
        inside (as the pose interface's `gripper` does); the nearest of several."""
        w = self.world
        tcp = a.tcp_pose()[0]
        others = set(n for n in w.held_by.values() if n)
        touched = [n for n in S.held_objects(a) if "weld_id" in w.objects.get(n, {}) and n not in others]
        if not touched:
            for n, o in w.objects.items():
                if "weld_id" in o and n not in others:
                    lo, hi = w.box(n)
                    if np.all(tcp >= lo - 0.006) and np.all(tcp <= hi + 0.006):
                        touched.append(n)
        if not touched:
            return None
        return min(touched, key=lambda n: (float(np.linalg.norm(w.locate(n)[0] - tcp)), n))

    # ---- what the robot senses ---------------------------------------------------------------------------------------
    @property
    def proprio_layout(self) -> list[str]:
        out = []
        for i, p in enumerate(self.prefix):
            out += [f"{p}q_{j}" for j in self.joint_names[i]] + [f"{p}dq_{j}" for j in self.joint_names[i]]
            out += [f"{p}gripper", f"{p}gripper_opening_m"]
            out += [f"{p}tcp_{k}" for k in ("x", "y", "z", "qw", "qx", "qy", "qz")]
            out += [f"{p}ft_{k}" for k in ("fx", "fy", "fz", "tx", "ty", "tz")]
        return out + ["time_s"]

    def proprio(self) -> np.ndarray:
        out = []
        for i, a in enumerate(self.arms):
            pos, quat = a.tcp_pose()
            force, torque = a.wrist_wrench()
            out += [a.joint_pos, a.joint_vel, [a.gripper_pos / self.gmax[i], a.gripper_opening()], pos, canonical(quat), force, torque]
        out.append([self.world.time])
        return np.concatenate([np.asarray(v, dtype=np.float64).reshape(-1) for v in out])

    def proprio_dict(self) -> dict:
        return {k: round(float(v), 5) for k, v in zip(self.proprio_layout, self.proprio())}

    # ---- cameras -----------------------------------------------------------------------------------------------------
    def camera_pose(self, cam: str, cv: bool = True) -> tuple[np.ndarray, np.ndarray]:
        """Where a camera is now (bench frame): position and quaternion of its frame, with OpenCV axes (x right, y
        down, z forward) when `cv`, else MuJoCo's (x right, y up, z backward)."""
        w = self.world
        s = w._sync()
        cid = w.model.camera(cam).id
        rot = s.cam_xmat[cid].reshape(3, 3).copy()
        if cv:
            rot = rot @ np.diag([1.0, -1.0, -1.0])
        return s.cam_xpos[cid].copy(), tf.mat_to_quat(rot)

    def intrinsics(self, cam: str) -> np.ndarray:
        w = self.world
        width, height = w.image_size
        f = 0.5 * height / math.tan(math.radians(float(w.model.cam_fovy[w.model.camera(cam).id])) / 2.0)
        return np.array([[f, 0.0, (width - 1) / 2.0], [0.0, f, (height - 1) / 2.0], [0.0, 0.0, 1.0]])

    def camera_spec(self) -> dict:
        w = self.world
        out = {}
        for cam in w.cameras:
            width, height = w.image_size
            e = {"width": width, "height": height, "fovy_deg": float(w.model.cam_fovy[w.model.camera(cam).id]),
                 "K": self.intrinsics(cam).tolist(), "depth": cam in self.depth_cameras}
            if cam in self.depth_cameras:
                e["depth_range_m"] = list(DEPTH_RANGE)
            if cam in self._wrist_arm:
                p, q = self._tcp_from_cam[cam]
                e["mount"] = f"wrist:{self.names[self._wrist_arm[cam]] or 'arm'}"
                e["tcp_from_cam"] = _pose_json(p, q)
            else:
                p, q = self.camera_pose(cam)
                e["mount"] = "fixed"
                e["world_from_cam"] = _pose_json(p, q)
            out[cam] = e
        return py(out)

    def render_depth(self, cam: str) -> np.ndarray:
        """z-depth (m, along the optical axis) of a camera that has depth; 0 where nothing is within `DEPTH_RANGE`."""
        if cam not in self.depth_cameras:
            raise ValueError(f"camera {cam!r} gives no depth; depth cameras: {list(self.depth_cameras)}")
        w = self.world
        width, height = w.image_size
        if self._depth_renderer is None:
            self._depth_renderer = mujoco.Renderer(w.model, height=height, width=width)
            self._depth_renderer.enable_depth_rendering()
        self._depth_renderer.update_scene(w._sync(), camera=cam)
        z = self._depth_renderer.render().astype(np.float32)
        z[(z < DEPTH_RANGE[0]) | (z > DEPTH_RANGE[1])] = 0.0
        return z

    def close(self) -> None:
        if self._depth_renderer is not None:
            self._depth_renderer.close()
            self._depth_renderer = None

    # ---- the robot's facts -------------------------------------------------------------------------------------------
    def gripper_facts(self, i: int = 0) -> dict:
        """What the gripper command does: the free distance between the pads for a command (nothing between them),
        and the force with which they press on what they close on."""
        a = self.arms[i]
        table = [[round(float(t) / self.gmax[i], 3), round(float(d) * 1e3, 1)] for t, d in a.spec.opening_table]
        out = {"command": "0 open .. 1 closed: a position target of the fingers, not a force; the fingers stop on what "
                          "they close on",
               "command_to_free_width_mm": table,
               "width_between": "linear between the rows of the table",
               "max_opening_m": round(float(S.max_opening(a)), 4)}
        if "2f85" in self.world.spec.type:
            from robosafe.sim.robots import PAD_N_PER_SERVO_FORCE_2F85
            # the cap follows from the servo's force limit (`RobotSpec.grip_servo`, 10 on the 2F-85: about 88 N per pad;
            # 0.5.1, which corrected the 45 N stated before, the model's own limit of 5)
            limit = round(PAD_N_PER_SERVO_FORCE_2F85 * float((a.spec.grip_servo or {}).get("force", 5.0)))
            out.update({"model": "Robotiq 2F-85 (MuJoCo Menagerie model)",
                        "force": ("the finger drive is a position servo with a force limit: on a thing, the pads' force grows "
                                  "with how far the command closes past the command at which the fingers meet it (that "
                                  "command is the thing's width read off the table): measured on a 40 mm block, about 5 N "
                                  "per pad 0.01 past, 31 N at 0.06 past, and the limit, about %d N per pad, from about 0.15 "
                                  "past. A gentle closure is a command a little past where the fingers meet the thing. "
                                  "(The real 2F-85 grips with 20 to 235 N.)" % limit),
                        "force_limit_n_per_pad": float(limit)})
        else:
            out.update({"model": "the YAM's parallel gripper (MuJoCo model)" if self.world.spec.type == "yam_bimanual" else "parallel gripper",
                        "force": "a position servo with a force limit; the force against the command has not been measured for this hand"})
        return out

    def spec(self) -> dict:
        w = self.world
        arms = []
        for i, a in enumerate(self.arms):
            mt = self.mounts[self.names[i]]
            arms.append({"name": self.names[i] or "arm", "joints": self.joint_names[i],
                         "joint_range_rad": self.ranges[i].tolist(), "joint_speed_limit_rad_s": self.speed[i].tolist(),
                         "base_position_m": [float(v) for v in mt["pos"]], "base_yaw_deg": float(mt["yaw_deg"]),
                         "gripper": self.gripper_facts(i),
                         "home_joints_rad": [float(v) for v in a.home]})
        return py({"robot": w.spec.type, "arms": arms, "control_dt": CONTROL_DT, "control_hz": round(1.0 / CONTROL_DT),
                "frame": "bench frame: origin on the table top at the middle of the table, +x to the right and +y away "
                         "from the viewer as the `front` camera sees it, +z up; metres, radians, seconds",
                "tcp": "the pinch point between the finger pads; its +z points out of the hand (the approach direction), "
                       "its +y along the closing direction; quaternions w, x, y, z",
                "table_top_z_m": 0.0, "table_size_m": [2.0 * v for v in w.table_half], "workspace_m": [list(v) for v in WORKSPACE],
                "cameras": self.camera_spec(), "depth_cameras": list(self.depth_cameras),
                "depth": {"unit": "m", "kind": "z-depth along the optical axis", "invalid": 0.0, "range_m": list(DEPTH_RANGE)},
                "proprio_layout": self.proprio_layout,
                "proprio_units": "q_*: rad; dq_*: rad/s; gripper: measured, 0 open .. 1 closed; gripper_opening_m: free "
                                 "distance between the pads; tcp_*: the TCP pose in the bench frame; ft_*: force (N) and "
                                 "torque (N m) at the flange in the flange frame, the hand's own weight included; time_s",
                "action_types": self.action_types(), "max_time_s": self.ep.max_time_s,
                "max_control_steps": int(round(self.ep.max_time_s / CONTROL_DT)),
                **({"grip_windows": self.grip_windows()} if self.grip_windows() else {}),
                # realtime (0.5.1) only, so that a paused episode's `spec` is what it was: as RCB's `/spec.timing`
                **({"timing": {"realtime": True, "slowdown": 1, "control_dt": CONTROL_DT,
                               "max_chunk_s": 10.0}}
                   if getattr(self.ep, "clock", "paused") == "realtime" else {})})

    def grip_windows(self) -> dict:
        """Since 0.5.1, in a family whose hazard is crushing a thing (`Family.crush`): for each thing of the scene of a kind
        the family has measured (`Family.crush_windows`, given for every member alike, so it says nothing of which member
        this is), the command at which both pads touch it and the command past which the fingers press it with more than
        the family's limit, in the gripper's 0..1 command and as free opening (m)."""
        fam = self.ep.family
        table = getattr(fam, "crush_windows", None) or {}
        out = {}
        for name in getattr(fam, "crush", ()) or ():
            kind = self.world.objects.get(name, {}).get("kind")
            if kind in table:
                out[name] = dict(table[kind])          # not the kind's name: what the thing is has to be seen
        return out
