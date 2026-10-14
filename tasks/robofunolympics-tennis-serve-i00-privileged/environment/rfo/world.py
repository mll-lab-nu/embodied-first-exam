"""The RoboFunOlympics world: one RoboOlympics Unitree G1 (the robot library's g1-4: Menagerie's 29-joint G1, its real
joint, speed and torque limits, its motor torque-speed curves, its self-collision) in a sports venue, the action
layer every task shares, the hands' grip, and the stepping that the referee (referee.py) watches.

One control step is 10 ms = 10 physics steps of 1 ms (the robot library's). Everything that changes the world happens
in World.step(row): the row is a "sim row" (RAW_DIM floats), the action in the simulator's own space, and the list of
sim rows replays an episode bit-exactly in a fresh process. The agent's action types (ACTION_TYPES) are views of it.

Who drives the joints (row[0], the mode):
  stand     the platform holds the legs in the stance (the walking policy's default leg angles on the stand gains with
            gravity support); the row's 17 waist and arm targets drive the upper body
  walk      Unitree's own walking policy drives the legs from the row's velocity command (vx, vy, wz; RoboOlympics'
            joint-group arbiter, the handover to the policy included); the row's waist and arm targets drive the rest
  run       RoboOlympics' athletics running policy drives all 29 joints from the velocity command
  run_arms  the running policy drives the legs and the waist; the row's 14 arm targets drive the arms
  joints    the row drives all 29 joints: position targets, velocity targets, feed-forward torques and PD gains
            (Unitree's LowCmd: tau = kp (q - q_meas) + kd (dq - dq_meas) + tau_ff), at 1 kHz
Every joint target is clipped into the joint's range and moves at most the joint's speed limit per step; every motor
torque goes through the robot library's output stage (torque-speed curve, torque limit).
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import sys
import xml.etree.ElementTree as ET

import numpy as np

import mujoco

SIM_DIR = os.environ.get("RFO_SIM_DIR", "/opt/roboolympics")
for _p in (os.path.join(SIM_DIR, "athletics"), SIM_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from bodies import load_body  # noqa: E402
from bodies.control.arbiter import Arbiter  # noqa: E402
from bodies.unitree_g1 import body as G1B  # noqa: E402
import run_policy as RP  # noqa: E402
from bodies.unitree_g1.agile import Agile  # noqa: E402
from bodies.unitree_g1.falcon import Falcon  # noqa: E402

from . import looks  # noqa: E402
from .referee import Referee  # noqa: E402
from .scene import Scene  # noqa: E402

# The robots of the library a task may use (Task.robot): the Unitree G1 (1.32 m, 33 kg, 29 joints; a walking and a running
# policy) and the Unitree H1-2 (1.78 m, 67 kg, 27 joints; a walking policy), each with its real limits and motor curves.
ROBOTS = {
    "unitree_g1": dict(title="Unitree G1", height_m=1.32, run=True, walkers=True,
                       source="MuJoCo Menagerie's unitree_g1 with Unitree's joint, speed and torque limits and motor "
                              "torque-speed curves"),
    "unitree_h1": dict(title="Unitree H1-2", height_m=1.78, run=False, walkers=False,
                       source="Unitree's own h1_2 model with its joint, speed and torque limits; its motor "
                              "torque-speed curves are estimates"),
}
BODY = load_body("unitree_g1")
ROBOT_REVISION = BODY.revision
CONTROL_DT = float(BODY.dt)                    # 10 ms (both robots)
SUB = int(BODY.substeps)                       # 10 physics steps of 1 ms
PHYS_DT = CONTROL_DT / SUB
HEAD_PITCH_RAD = 0.35                          # the head camera's tilt below the horizon
JOINTS = list(G1B.LEGS) + list(G1B.TORSO) + [f"left_{j}_joint" for j in G1B.ARM] + [f"right_{j}_joint" for j in G1B.ARM]
NJ = len(JOINTS)                               # 29, the Unitree SDK order
LEGS, WAIST, ARMS, UPPER = slice(0, 12), slice(12, 15), slice(15, 29), slice(12, 29)
GROUP_NAMES = ("legs", "waist", "arms")
SIDES = ("left", "right")

# ------------------------------------------------------------------------------------------------ the sim row
MODES = ("stand", "walk", "run", "run_arms", "joints", "walk_falcon", "walk_agile")
STAND, WALK, RUN, RUN_ARMS, JOINT, WALK_FALCON, WALK_AGILE = range(7)
WALKERS = (WALK_FALCON, WALK_AGILE)            # the G1's optional walking policies (FALCON, AGILE), from the robot library
R_MODE, R_CMD, R_Q, R_DQ, R_TAU, R_KP, R_KD, R_GRIP = (0, slice(1, 4), slice(4, 33), slice(33, 62), slice(62, 91),
                                                        slice(91, 120), slice(120, 149), slice(149, 151))
RAW_DIM = 151                                  # the G1's (the module-level layout names are the G1's; a world has its own: Layout)


class Layout:
    """A robot's joint groups and its sim row: [mode, vx, vy, wz, q, dq, tau, kp, kd (nj each), grip_left, grip_right].
    The joints are in the robot's SDK order: left leg 6, right leg 6, waist (the G1: yaw, roll, pitch; the H1-2: one
    torso yaw), left arm 7, right arm 7."""

    def __init__(self, joints: list[str], n_waist: int):
        nj = len(joints)
        self.JOINTS, self.NJ, self.NW, self.NU = list(joints), nj, n_waist, nj - 12
        self.LEGS, self.WAIST = slice(0, 12), slice(12, 12 + n_waist)
        self.ARMS, self.UPPER = slice(12 + n_waist, nj), slice(12, nj)
        self.R_Q, self.R_DQ, self.R_TAU, self.R_KP, self.R_KD = (slice(4 + i * nj, 4 + (i + 1) * nj) for i in range(5))
        self.R_GRIP = slice(4 + 5 * nj, 6 + 5 * nj)
        self.RAW_DIM = 6 + 5 * nj


RUN_CMD = np.array([[0.0, 5.0], [-0.12, 0.12], [-0.5, 0.5]])      # the running policy's command ranges
STAND_RATE = 1.5                               # rad/s: how fast `stand` brings the legs to the stance
GRIP_REACH = 0.035                             # m: a hand grips an object whose surface is this close to its palm
GRIP_SPEED = 6.0                               # m/s: ... and that moves no faster than this relative to the palm
FALL_Z = 0.35                                  # m: the pelvis below this is down (tasks that allow it say so)
UNSTABLE = "the simulation became unstable"    # the referee's reason when the physics diverges (an attempt's failure)
MAX_SPEED = 150.0                              # m/s: the robot or a prop faster than this is a divergence too
GRIPS = ["grip_left", "grip_right"]
VEL = ["vx", "vy", "wz"]


def walker_cmd(pol, cmd_max) -> tuple[np.ndarray, np.ndarray]:
    """The command range of an optional walking policy: its training range (FALCON: +-command_max; AGILE: command_min
    to command_max) within the robot's own walking limits (cmd_max, [limits.walk])."""
    cmd_max = np.asarray(cmd_max, float)
    lo = getattr(pol, "cmd_min", -pol.cmd_max)
    return np.maximum(np.asarray(lo, float)[:3], -cmd_max), np.minimum(np.asarray(pol.cmd_max, float)[:3], cmd_max)


def _yaw(quat) -> float:
    w, x, y, z = quat
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


class Robot:
    """The mounted G1: the library rig and arbiter, addresses, limits, the body parts' geoms."""

    def __init__(self, m, name: str = "unitree_g1"):
        self.m, self.name, self.info = m, name, ROBOTS[name]
        self.B = load_body(name)
        self.bm = importlib.import_module(f"bodies.{name}.body")
        self.stand_z = float(self.bm.STAND_Z)
        self.rig = self.B.rig(m, "", hand=None)
        self.arb = Arbiter(self.rig)
        a = self.arb
        self.L = Layout(list(a.JOINTS), len(a.GROUPS["waist"]))
        self.has_run = bool(self.info["run"])
        self.modes = {STAND, WALK, JOINT} | ({RUN, RUN_ARMS} if self.has_run else set())
        # The G1's two optional walking policies (bodies/unitree_g1/falcon.py, agile.py: numpy ports of the released
        # FALCON and WBC-AGILE G1 policies), stepped like the running policy: 50 Hz, their 12 leg targets on their
        # own leg gains; the waist and the arms stay the row's, on the default gains. FALCON also gives its wrist
        # residual (as torque on the wrists, as the library's rig does).
        self.walkers = {}
        if self.info.get("walkers"):
            self.walkers = {WALK_FALCON: Falcon(self.B.decl), WALK_AGILE: Agile(self.B.decl)}
            self.modes |= set(WALKERS)
        self.qadr, self.vadr = a.qadr, a.vadr
        self.fq, self.fv = self.rig.fqadr, self.rig.fvadr
        self.lo, self.hi, self.speed, self.tau_max = a.lo.copy(), a.hi.copy(), a.speed.copy(), a.tau_max.copy()
        self.kp_max, self.kd_max = a.kp_max.copy(), a.kd_max.copy()
        self.stance = a.rest[:12].copy()                     # the walking policy's default leg angles
        self.rest = a.rest.copy()                            # ... and the rest pose of the waist and the arms
        # default gains of a `joints` row: the stand gains on the legs, the servo gains on the waist and the arms
        self.kp0 = np.r_[a.stand_kp, a.servo_kp[12:]]
        self.kd0 = np.r_[a.stand_kd, a.servo_kd[12:]]
        if self.has_run:
            self.run_kp, self.run_kd = np.minimum(RP.KP, a.kp_max), np.minimum(RP.KD, a.kd_max)
        sid = lambda n: int(m.sensor_adr[m.sensor(n).id])  # noqa: E731
        self.sens = {k: sid(k) for k in ("orientation_pelvis", "gyro_pelvis", "accelerometer_pelvis",
                                         "orientation_torso", "gyro_torso", "accelerometer_torso")}
        self.pelvis = m.body("pelvis").id
        self.torso = m.body("torso_link").id
        self.bodies = sorted(a.robot_bodies)
        self.mount = {s: m.body(f"{s}_mount").id for s in SIDES}
        self.palm = {s: m.site(f"{s}_palm").id for s in SIDES}
        self.foot_site = {s: m.site(f"{s}_foot").id for s in SIDES}
        self.head_site = m.site("head_center").id
        self.mass = float(m.body_subtreemass[self.pelvis])


class World:
    CONTROL_DT, PHYS_DT, SUB = CONTROL_DT, PHYS_DT, SUB

    def __init__(self, task, instance: dict | None = None):
        """task: a rfo.task.TaskBase (the family's rules and venue). instance: the frozen instance (its parameters
        override the task's defaults; None: the defaults)."""
        self.task = task
        if instance is not None:
            task.configure(instance.get("params", {}))
        self.robot_name = getattr(task, "robot", "unitree_g1")
        if self.robot_name not in ROBOTS:
            raise ValueError(f"unknown robot {self.robot_name!r}; one of {list(ROBOTS)}")
        sc = Scene()
        task.build(sc)
        looks.dress(sc)                              # lights, materials: looks only (looks.py)
        self.scene = sc
        self.xml = self._assemble(sc)
        self.m = mujoco.MjModel.from_xml_string(self.xml)
        looks.paint(self.m)
        # MuJoCo would reset the data by itself when the physics diverges (a bad acceleration); the referee's record
        # and the grips would then belong to another world. No auto-reset: the step loop ends the attempt instead.
        self.m.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_AUTORESET)
        self.d = mujoco.MjData(self.m)
        m = self.m
        self.robot = Robot(m, self.robot_name)
        self.L = self.robot.L
        self.runp = RP.RunPolicy()
        self.grippables = {n: dict(v, body=m.body(n).id) for n, v in sc.grippables.items()}
        self.welds = {(s, n): m.equality(f"grip_{s}_{n}").id for s in SIDES for n in self.grippables}
        self.free = {}                              # free bodies by name: (qpos adr, dof adr)
        for j in range(m.njnt):
            if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE and m.jnt_bodyid[j] != self.robot.pelvis:
                self.free[m.body(int(m.jnt_bodyid[j])).name] = (int(m.jnt_qposadr[j]), int(m.jnt_dofadr[j]))
        self._lin_dofs = np.array([self.robot.fv + i for i in range(3)]
                                  + [va + i for _, va in self.free.values() for i in range(3)])
        self.cameras = ["head_left", "head_right"] + list(sc.cameras)
        self._eq_data0 = m.eq_data.copy()           # a grip writes its weld's pose into the model: reset restores it
        self.tool_hands = set(sc.hand_tools)        # a hand that carries a tool has no fist to grip with
        self._renderers: dict = {}
        self.ref = Referee(self)
        self.reset()

    # ------------------------------------------------------------------ the model
    def _assemble(self, sc: Scene) -> str:
        root = sc.root
        x, y, yaw = self.task.start
        load_body(self.robot_name).mount(root, "", (x, y, 0.0), yaw, hand=None, lod="standard",
                                         head_pitch=HEAD_PITCH_RAD)
        if self.robot_name == "unitree_h1":         # the H1-2's sole is one convex hull: on a box or a mesh it would get
            opt = root.find("option")               # a single contact point and sink; multi-point contacts for it
            if not any(f.get("multiccd") for f in opt.findall("flag")):
                ET.SubElement(opt, "flag", multiccd="enable")
        sens = root.find("sensor")
        sites = {e.get("name") for e in root.iter("site")}
        for where in ("pelvis", "torso"):
            s = f"imu_in_{where}"
            if s not in sites:                      # the H1-2 has one IMU site, "imu", in its torso
                if where == "torso" and "imu" in sites:
                    s = "imu"
                else:
                    link = next(b for b in root.iter("body") if b.get("name") == ("pelvis" if where == "pelvis" else "torso_link"))
                    ET.SubElement(link, "site", name=s, pos="0 0 0", size="0.01", group="5")
            ET.SubElement(sens, "framequat", name=f"orientation_{where}", objtype="site", objname=s)
            ET.SubElement(sens, "gyro", name=f"gyro_{where}", site=s)
            ET.SubElement(sens, "accelerometer", name=f"accelerometer_{where}", site=s)
        tools: list[tuple[str, str]] = []
        for side in SIDES:                          # the hands: a palm pad (or the task's tool) on each wrist mount
            mount = next(b for b in root.iter("body") if b.get("name") == f"{side}_mount")
            ET.SubElement(mount, "site", name=f"{side}_palm", pos="0 0 0.045", size="0.008", group="4")
            frag = sc.hand_tools.get(side)
            if frag:
                for i, el in enumerate(ET.fromstring(f"<x>{frag}</x>")):
                    if el.tag == "geom" and el.get("name") is None:
                        el.set("name", f"{side}_tool_g{i}")
                    mount.append(el)
                    if el.tag == "geom" and el.get("contype", "1") != "0":
                        tools.append((side, el.get("name")))
            else:
                ET.SubElement(mount, "geom", name=f"{side}_palm_pad", type="box", pos="0 0 0.05", size="0.022 0.04 0.05",
                              contype="4", conaffinity="0", mass="0", group="3", rgba="0.15 0.15 0.17 1",
                              friction="1.2 0.005 0.0001")
            for name in sc.grippables:
                sc.grip_weld(side, name)
        # A tool is part of the robot (contype 4, conaffinity 0), so like the body hulls it would pass through the
        # robot itself: explicit pairs make it collide with every hull but those of the arm that carries it (the
        # robot library's self-collision does the same for the bare hands).
        contact = root.find("contact")
        hulls = [(b.get("name"), g.get("name")) for b in root.iter("body") for g in b.findall("geom")
                 if g.get("name") and "_sc" in g.get("name")]
        for side, tool in tools:
            own = (f"{side}_shoulder", f"{side}_elbow", f"{side}_wrist")
            for body, hull in hulls:
                if not body.startswith(own):
                    ET.SubElement(contact, "pair", name=f"toolcol_{tool}_{hull}", geom1=tool, geom2=hull, condim="3")
        return ET.tostring(root, encoding="unicode")

    # ------------------------------------------------------------------ episode
    def reset(self) -> None:
        m, d, r = self.m, self.d, self.robot
        mujoco.mj_resetData(m, d)
        x, y, yaw = self.task.start
        r.rig.place(d, r.rig.rest, pos=(x, y, r.stand_z), yaw=yaw)
        r.arb.reset(d)
        self._hold_legs()
        self.runp.reset()
        self.k = 0                                  # control steps done
        self.refused = 0                            # joint plans the arbiter refused (the targets then stay)
        self.unstable = False
        self.mode = STAND
        self.run_k = 0
        self.run_tgt = r.arb.target()
        for pol in r.walkers.values():
            pol.reset()
        self.walk_k = 0
        self.walk_tgt = r.stance.copy()
        self.wrist_ff = np.zeros(14)
        self.cmd = np.zeros(3)
        self.held = {s: None for s in SIDES}        # side -> the name of the body its hand grips
        self.grip_req = {s: False for s in SIDES}
        d.eq_active[:] = m.eq_active0
        m.eq_data[:] = self._eq_data0
        self.last_raw: np.ndarray | None = None     # the sim row in force (the last one executed)
        self.pins: dict[str, np.ndarray] = {}       # free bodies a task holds in place (a ball on a launcher)
        self.task.reset(self)
        d.time = 0.0
        d.act[:] = 0
        d.ctrl[:] = 0
        d.qacc_warmstart[:] = 0
        mujoco.mj_forward(m, d)
        self.ref.reset()

    def _hold_legs(self) -> None:
        """The legs on the arbiter's hold (stand gains, gravity support) at the stance: how the robot stands at t = 0."""
        a, d = self.robot.arb, self.d
        L = a.GROUPS["legs"]
        a.plans.pop("legs", None)
        a.ho = a.settle = None
        a.kicker = None
        a.cmd_req = np.zeros(3)
        a.cmd = np.zeros(3)
        a.q_a[L] = a.q_b[L] = d.qpos[a.qadr[L]]
        a._set_owner("legs", "hold", "stand")

    @property
    def t(self) -> float:
        """Seconds of the episode."""
        return self.k * CONTROL_DT

    @property
    def done(self) -> bool:
        return self.ref.done

    @property
    def success(self) -> bool:
        return self.ref.success

    # ------------------------------------------------------------------ one control step
    def step(self, raw) -> bool:
        """One control step of a sim row. Returns True when the episode is over."""
        if self.ref.done:
            raise RuntimeError("the episode is over")
        raw = np.asarray(raw, dtype=np.float64)
        L = self.L
        if raw.shape != (L.RAW_DIM,) or not np.all(np.isfinite(raw)):
            raise ValueError(f"a sim row is {L.RAW_DIM} finite floats")
        if raw[R_MODE] not in self.robot.modes:     # checked before anything changes
            raise ValueError(f"a sim row's first value is the mode, one of {sorted(self.robot.modes)} "
                             f"({', '.join(MODES[i] for i in sorted(self.robot.modes))})")
        m, d, a = self.m, self.d, self.robot.arb
        for name, pose in self.pins.items():        # a pinned body stays where the task put it
            qa, va = self.free[name]
            d.qpos[qa:qa + 7] = pose
            d.qvel[va:va + 6] = 0.0
        self.task.before_step(self)
        self._grips(raw[L.R_GRIP] >= 0.5)
        self._control(raw)
        a.begin_step(d)
        won = self.ref.success
        for j in range(1, SUB + 1):
            a.apply(d, j)
            mujoco.mj_step(m, d)
            if (d.warning[mujoco.mjtWarning.mjWARN_BADQACC].number or not np.all(np.isfinite(d.qpos))
                    or float(np.abs(d.qvel[self._lin_dofs]).max()) > MAX_SPEED):
                self.unstable = True                # the physics diverged: the attempt ends here, as a failure
                break
            self.ref.substep()
        self.k += 1
        self.last_raw = raw.copy()
        if self.unstable:
            self.ref.void(UNSTABLE, keep_success=won)   # (also a success latched earlier in this control step)
            self.ref.done = True
        else:
            self.ref.step()
        return self.ref.done

    def _plan(self, groups, Q, QD=None, TAU=None, kp=None, kd=None, rate=None) -> None:
        """One row of joint targets for `groups` through the arbiter's plan: clipped into the ranges and to one step
        of the speed limits from where each group's target is (its measured position when it is taken over)."""
        r, a, d = self.robot, self.robot.arb, self.d
        ix = np.concatenate([a.GROUPS[g] for g in groups])
        ref = a.q_b[ix].copy()
        for g in groups:
            if a.owner[g] not in ("plan", "hold"):
                sel = np.isin(ix, a.GROUPS[g])
                ref[sel] = d.qpos[a.qadr[ix[sel]]]
        step = (r.speed[ix] if rate is None else np.minimum(r.speed[ix], rate)) * CONTROL_DT * 0.999
        q = np.clip(np.asarray(Q, float), r.lo[ix] + 1e-6, r.hi[ix] - 1e-6)
        q = np.clip(ref + np.clip(q - ref, -step, step), r.lo[ix] + 1e-6, r.hi[ix] - 1e-6)   # (a joint the load pushed
        #                                             a little past its range comes back in at once)
        a.last_plan_step = -10 ** 9                 # the arbiter's one-plan-per-20-ms rule is for remote players
        why = a.plan(d, list(groups), q[None, :], None if QD is None else np.asarray(QD, float)[None, :],
                     None if TAU is None else np.asarray(TAU, float)[None, :], kp, kd)
        if why:                                     # refused (a joint driven far past its range): nothing changes
            self.refused += 1

    def _control(self, raw) -> None:
        r, a, d, L = self.robot, self.robot.arb, self.d, self.L
        mode = int(raw[R_MODE])
        if mode in (RUN, RUN_ARMS) and self.mode not in (RUN, RUN_ARMS):
            self.runp.reset()
            self.run_k = 0
        if mode in WALKERS and self.mode != mode:   # a walker takes over: its memory starts afresh
            r.walkers[mode].reset()
            self.walk_k = 0
        self.mode = mode
        q = raw[L.R_Q]
        if mode == WALK:
            self.cmd = np.clip(raw[R_CMD], -a.cmd_max, a.cmd_max)
            a.walk(d, self.cmd)
            self._plan(["waist", "arms"], q[L.UPPER])
        elif mode == STAND:
            self.cmd = np.zeros(3)
            ff = np.clip(a._support_ff(d), -r.tau_max[L.LEGS], r.tau_max[L.LEGS])
            self._plan(["legs", "waist", "arms"], np.r_[r.stance, q[L.UPPER]], TAU=np.r_[ff, np.zeros(L.NU)],
                       kp=r.kp0, kd=r.kd0, rate=np.r_[np.full(12, STAND_RATE), np.full(L.NU, np.inf)])
        elif mode in WALKERS:
            pol = r.walkers[mode]
            lo, hi = walker_cmd(pol, a.cmd_max)
            self.cmd = np.clip(raw[R_CMD], lo, hi)
            up = np.clip(q[L.UPPER], r.lo[L.UPPER], r.hi[L.UPPER])
            if self.walk_k % 2 == 0:                # the policies run at 50 Hz
                self.walk_tgt = np.asarray(pol.step(d.qpos[r.fq + 3:r.fq + 7], d.qvel[r.fv + 3:r.fv + 6],
                                                    d.qpos[r.qadr], d.qvel[r.vadr], self.cmd,
                                                    up[L.ARMS.start - 12:], float(up[0])), float)[:12]
                self.wrist_ff = (pol.wrist_torque(r.kp0[L.ARMS]) if mode == WALK_FALCON else np.zeros(14))
            self.walk_k += 1
            self._plan(["legs", "waist", "arms"], np.r_[self.walk_tgt, up],
                       TAU=np.r_[np.zeros(12 + L.NW), np.clip(self.wrist_ff, -r.tau_max[L.ARMS], r.tau_max[L.ARMS])],
                       kp=np.r_[np.minimum(pol.kp, r.kp_max[:12]), r.kp0[L.UPPER]],
                       kd=np.r_[np.minimum(pol.kd, r.kd_max[:12]), r.kd0[L.UPPER]])
        elif mode in (RUN, RUN_ARMS):
            self.cmd = np.clip(raw[R_CMD], RUN_CMD[:, 0], RUN_CMD[:, 1])
            if self.run_k % 2 == 0:                 # the policy runs at 50 Hz
                sd = d.sensordata
                s = r.sens
                self.run_tgt = self.runp.step(sd[s["orientation_pelvis"]:s["orientation_pelvis"] + 4],
                                              sd[s["gyro_pelvis"]:s["gyro_pelvis"] + 3], d.qpos[r.qadr],
                                              d.qvel[r.vadr], self.cmd)
            self.run_k += 1
            if mode == RUN:
                self._plan(["legs", "waist", "arms"], self.run_tgt, kp=r.run_kp, kd=r.run_kd)
            else:
                self._plan(["legs", "waist", "arms"], np.r_[self.run_tgt[:L.ARMS.start], q[L.ARMS]],
                           kp=np.r_[r.run_kp[:L.ARMS.start], r.kp0[L.ARMS]],
                           kd=np.r_[r.run_kd[:L.ARMS.start], r.kd0[L.ARMS]])
        else:
            self.cmd = np.zeros(3)
            self._plan(["legs", "waist", "arms"], q, QD=np.clip(raw[L.R_DQ], -r.speed, r.speed),
                       TAU=np.clip(raw[L.R_TAU], -r.tau_max, r.tau_max), kp=np.clip(raw[L.R_KP], 0.0, r.kp_max),
                       kd=np.clip(raw[L.R_KD], 0.0, r.kd_max))

    # ------------------------------------------------------------------ the hands' grip
    def _grip_gap(self, side: str, name: str) -> tuple[float, float]:
        """(distance from the palm to the object's surface, their relative speed)."""
        m, d, g = self.m, self.d, self.grippables[name]
        p = d.site_xpos[self.robot.palm[side]]
        b = g["body"]
        c = d.xpos[b]
        if g.get("half_length"):                    # a rod: its axis is the body's local `axis`, +- half_length
            ax = d.xmat[b].reshape(3, 3)[:, "xyz".index(g.get("axis", "x"))]
            s = float(np.clip((p - c) @ ax, -g["half_length"], g["half_length"]))
            c = c + s * ax
        gap = float(np.linalg.norm(p - c)) - g["radius"]
        vo = np.zeros(6)
        vh = np.zeros(6)
        mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, b, vo, 0)
        mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_SITE, self.robot.palm[side], vh, 0)
        return gap, float(np.linalg.norm(vo[3:] - vh[3:]))

    def _grips(self, req) -> None:
        m, d = self.m, self.d
        if self.grippables:
            mujoco.mj_kinematics(m, d)              # positions and velocities as they are now (a task may just
            mujoco.mj_comPos(m, d)                  # have placed or launched a prop: the speed test below must
            mujoco.mj_comVel(m, d)                  # not read the step before)
        for i, side in enumerate(SIDES):
            want = bool(req[i])
            self.grip_req[side] = want
            if not self.grippables:
                continue
            if self.held[side] is not None and not want:
                name = self.held[side]
                d.eq_active[self.welds[(side, name)]] = 0
                self.held[side] = None
                self.ref.event("release", hand=side, object=name)
            elif self.held[side] is None and want and side not in self.tool_hands:
                best = None
                for name in self.grippables:
                    if name in self.pins or not self.task.may_grip(self, side, name):
                        continue
                    gap, speed = self._grip_gap(side, name)
                    if gap <= GRIP_REACH and speed <= GRIP_SPEED and (best is None or gap < best[0]):
                        best = (gap, name)
                if best is not None:
                    self.grab(side, best[1])

    def grab(self, side: str, name: str, event: bool = True) -> None:
        """Weld the object to the hand as they are now (the grip; also how a task puts an object in a hand at t = 0)."""
        m, d = self.m, self.d
        eq = self.welds[(side, name)]
        b1, b2 = self.robot.mount[side], self.grippables[name]["body"]
        mujoco.mj_kinematics(m, d)
        R1 = d.xmat[b1].reshape(3, 3)
        rel_p = R1.T @ (d.xpos[b2] - d.xpos[b1])
        q1n, rel_q = np.zeros(4), np.zeros(4)
        mujoco.mju_negQuat(q1n, d.xquat[b1])
        mujoco.mju_mulQuat(rel_q, q1n, d.xquat[b2])
        m.eq_data[eq, 0:3] = 0.0                    # the weld's anchor: the object's origin
        m.eq_data[eq, 3:6] = rel_p
        m.eq_data[eq, 6:10] = rel_q
        m.eq_data[eq, 10] = 1.0
        d.eq_active[eq] = 1
        self.held[side] = name
        self.grip_req[side] = True
        if event:
            self.ref.event("grip", hand=side, object=name)

    def holder(self, name: str) -> list[str]:
        """The hands that grip the object."""
        return [s for s in SIDES if self.held[s] == name]

    # ------------------------------------------------------------------ free bodies (a task's props)
    def put(self, name: str, pos, quat=(1, 0, 0, 0), vel=(0, 0, 0), angvel=(0, 0, 0)) -> None:
        """Place a free body (and set its velocity): resets, launches."""
        qa, va = self.free[name]
        self.d.qpos[qa:qa + 3] = pos
        self.d.qpos[qa + 3:qa + 7] = quat
        self.d.qvel[va:va + 3] = vel
        self.d.qvel[va + 3:va + 6] = angvel

    def pin(self, name: str, pos=None, quat=(1, 0, 0, 0)) -> None:
        """Hold a free body in place until unpin() / launch() (re-placed at the start of every control step)."""
        if pos is not None:
            self.put(name, pos, quat)
        qa, _ = self.free[name]
        self.pins[name] = self.d.qpos[qa:qa + 7].copy()

    def unpin(self, name: str) -> None:
        self.pins.pop(name, None)

    def launch(self, name: str, pos, vel, angvel=(0, 0, 0)) -> None:
        self.pins.pop(name, None)
        self.put(name, pos, vel=vel, angvel=angvel)

    def pos(self, name: str) -> np.ndarray:
        return self.d.xpos[self.m.body(name).id].copy()

    def vel(self, name: str) -> np.ndarray:
        """A free body's linear velocity in the world."""
        _, va = self.free[name]
        return self.d.qvel[va:va + 3].copy()

    # ------------------------------------------------------------------ the robot's state (privileged)
    def pelvis(self) -> np.ndarray:
        """x, y, z, yaw of the pelvis."""
        d, r = self.d, self.robot
        return np.r_[d.qpos[r.fq:r.fq + 3], _yaw(d.qpos[r.fq + 3:r.fq + 7])]

    def com(self) -> np.ndarray:
        return self.d.subtree_com[self.robot.pelvis].copy()

    def upright(self) -> float:
        """The cosine of the torso's tilt from vertical (1 upright)."""
        return float(self.d.xmat[self.robot.torso].reshape(3, 3)[2, 2])

    def robot_aabb(self) -> tuple[np.ndarray, np.ndarray]:
        """The lower and upper corners of the robot's collision geometry (bounding spheres of its geoms, tight for the
        small links): what "the whole body past a plane" is measured on."""
        return self.ref.robot_extent()

    # ------------------------------------------------------------------ what a real G1 senses
    @property
    def proprio_layout(self) -> list[str]:
        J = [j[:-6] for j in self.L.JOINTS]
        return ([f"{j}_pos" for j in J] + [f"{j}_vel" for j in J] + [f"{j}_torque" for j in J] + [f"{j}_target" for j in J]
                + [f"imu_pelvis_{k}" for k in ("qw", "qx", "qy", "qz", "gx", "gy", "gz", "ax", "ay", "az")]
                + [f"imu_torso_{k}" for k in ("qw", "qx", "qy", "qz", "gx", "gy", "gz", "ax", "ay", "az")]
                + ["holding_left", "holding_right", "mode", "cmd_vx", "cmd_vy", "cmd_wz", "time_s"])

    def proprio(self) -> np.ndarray:
        d, r, a = self.d, self.robot, self.robot.arb
        sd, s = d.sensordata, r.sens
        imu = lambda w: np.r_[sd[s[f"orientation_{w}"]:s[f"orientation_{w}"] + 4], sd[s[f"gyro_{w}"]:s[f"gyro_{w}"] + 3],  # noqa: E731
                              sd[s[f"accelerometer_{w}"]:s[f"accelerometer_{w}"] + 3]]
        return np.r_[d.qpos[r.qadr], d.qvel[r.vadr], d.ctrl[a.aid], a.target(), imu("pelvis"), imu("torso"),
                     [float(self.held["left"] is not None), float(self.held["right"] is not None), float(self.mode)],
                     self.cmd, [self.t]].astype(np.float32)

    def render(self, camera: str, width: int = 480, height: int = 270, depth: bool = False) -> np.ndarray:
        key = (width, height)
        if key not in self._renderers:
            self._renderers[key] = mujoco.Renderer(self.m, height, width)
        R = self._renderers[key]
        if depth:
            R.enable_depth_rendering()
        R.update_scene(self.d, camera=camera)
        out = R.render().copy()
        if depth:
            R.disable_depth_rendering()
        return out

    def close(self) -> None:
        for R in self._renderers.values():
            try:
                R.close()
            except Exception:  # noqa: BLE001
                pass
        self._renderers = {}

    # ------------------------------------------------------------------ identity
    def state_sha(self) -> str:
        """The simulator's state, the controllers' memory, the grips and the referee's record."""
        d, m, a = self.d, self.m, self.robot.arb
        h = hashlib.sha256()
        ho, st = a.ho or {}, a.settle or {}
        extra = [np.r_[ho.get("i", -1), ho.get("n", -1)], ho.get("q_from", np.zeros(0)), ho.get("kp_from", np.zeros(0)),
                 ho.get("kd_from", np.zeros(0)), np.r_[st.get("i", -1)], np.asarray(st.get("w", []), float).ravel(),
                 np.zeros(0) if self.last_raw is None else self.last_raw, *[self.pins[k] for k in sorted(self.pins)]]
        for arr in (d.qpos, d.qvel, d.ctrl, d.act, d.eq_active, m.eq_data, d.qacc_warmstart, a.memory(),
                    *self.runp.memory(), self.run_tgt, self.cmd, *extra,
                    *[self.robot.walkers[k].state() for k in sorted(self.robot.walkers)], self.walk_tgt, self.wrist_ff):
            h.update(np.nan_to_num(np.ascontiguousarray(arr, dtype=np.float64), nan=1e300, posinf=1e301,
                                   neginf=-1e301).tobytes())
        h.update(json.dumps([self.k, self.mode, self.run_k, self.walk_k, self.refused, self.unstable, self.held, self.grip_req, sorted(self.pins), self.ref.digest()],
                            sort_keys=True, default=_jd).encode())
        return h.hexdigest()


def _jd(o):
    """JSON for the state hash: arrays as lists, trackers by their state(); anything else is a bug (its repr would put
    a memory address into the hash)."""
    if hasattr(o, "tolist"):
        return o.tolist()
    if hasattr(o, "state"):
        return o.state()
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    raise TypeError(f"{type(o).__name__} in the referee's record has no state(): the state hash cannot cover it")


# ------------------------------------------------------------------------------------------------ the action types


class Actions:
    """The agent's action types: each a view of the sim row. One row is one control step (10 ms) unless a chunk's dt
    spreads it over several (hold, or a straight line from the previous command)."""

    def __init__(self, robot: Robot):
        r = self.r = robot
        a = robot.arb
        L = self.L = robot.L
        _names = lambda sl: [j[:-6] for j in L.JOINTS[sl]]  # noqa: E731
        g01 = (np.zeros(2), np.ones(2))
        q = (r.lo, r.hi)
        walk = (-a.cmd_max, a.cmd_max)
        run = (RUN_CMD[:, 0], RUN_CMD[:, 1])
        cat = lambda *b: (np.concatenate([x[0] for x in b]), np.concatenate([x[1] for x in b]))  # noqa: E731
        sub = lambda sl: (r.lo[sl], r.hi[sl])  # noqa: E731
        self.types = {
            "stand": dict(layout=_names(L.UPPER) + GRIPS, bounds=cat(sub(L.UPPER), g01),
                          meaning=f"the platform holds the legs in the stance; you give the waist's {L.NW} and the arms' 14 "
                                  "joint targets (rad)"),
            "walk": dict(layout=VEL + _names(L.UPPER) + GRIPS, bounds=cat(walk, sub(L.UPPER), g01),
                         meaning="Unitree's walking policy drives the legs from the velocity command (vx forward, vy to "
                                 "the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and "
                                 "arm joint targets"),
            "run": dict(layout=VEL + GRIPS, bounds=cat(run, g01),
                        meaning=f"the running policy drives all {L.NJ} joints from the velocity command (it swings the arms)"),
            "run_arms": dict(layout=VEL + _names(L.ARMS) + GRIPS, bounds=cat(run, sub(L.ARMS), g01),
                             meaning="the running policy drives the legs and the waist; you give the 14 arm joint targets"),
            "joints": dict(layout=_names(slice(0, L.NJ)) + GRIPS, bounds=cat(q, g01),
                           meaning=f"you give all {L.NJ} joint targets (rad); the default PD gains, no feed-forward"),
            "lowcmd": dict(layout=[f"{n}_{k}" for k in ("q", "dq", "tau", "kp", "kd") for n in _names(slice(0, L.NJ))] + GRIPS,
                           bounds=cat(q, (-r.speed, r.speed), (-r.tau_max, r.tau_max), (np.zeros(L.NJ), r.kp_max),
                                      (np.zeros(L.NJ), r.kd_max), g01),
                           meaning=f"Unitree's LowCmd for all {L.NJ} joints: position targets (rad), velocity targets "
                                   "(rad/s), feed-forward torques (N m), kp, kd; the motor torque is "
                                   "kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz"),
        }
        if not r.has_run:                            # a robot without a running policy
            del self.types["run"], self.types["run_arms"]
        for mode, name, who in ((WALK_FALCON, "walk_falcon", "FALCON's walking policy (LeCAR-Lab, trained with arm motions "
                                 "and forces on the hands; it also nudges the wrists)"),
                                (WALK_AGILE, "walk_agile", "AGILE's velocity-height walking policy (NVIDIA WBC-AGILE, "
                                 "trained while the arms and the waist moved)")):
            if mode in r.walkers:
                self.types[name] = dict(layout=VEL + _names(L.UPPER) + GRIPS,
                                        bounds=cat(walker_cmd(r.walkers[mode], a.cmd_max), sub(L.UPPER), g01),
                                        meaning=f"{who} drives the legs from the velocity command (vx forward, vy to "
                                                "the left, m/s; wz turning left, rad/s; the robot's own frame); you "
                                                "give the waist and arm joint targets")
        for t in self.types.values():
            t["dim"] = len(t["layout"])
            assert len(t["bounds"][0]) == t["dim"]

    def clip(self, typ: str, rows) -> np.ndarray:
        lo, hi = self.types[typ]["bounds"]
        return np.clip(np.asarray(rows, dtype=np.float64), lo, hi)

    def to_raw(self, typ: str, row, world: "World") -> np.ndarray:
        """An agent row -> the sim row. Joints the row does not name keep their current targets."""
        r, L = self.r, self.L
        row = np.asarray(row, dtype=np.float64)
        raw = np.zeros(L.RAW_DIM)
        raw[L.R_Q] = r.arb.target()
        raw[L.R_KP], raw[L.R_KD] = r.kp0, r.kd0
        raw[L.R_GRIP] = (row[-2:] >= 0.5).astype(float)
        if typ == "stand":
            raw[R_MODE] = STAND
            raw[L.R_Q][L.UPPER] = row[0:L.NU]
        elif typ in ("walk", "walk_falcon", "walk_agile"):
            raw[R_MODE] = {"walk": WALK, "walk_falcon": WALK_FALCON, "walk_agile": WALK_AGILE}[typ]
            raw[R_CMD] = row[0:3]
            raw[L.R_Q][L.UPPER] = row[3:3 + L.NU]
        elif typ == "run":
            raw[R_MODE] = RUN
            raw[R_CMD] = row[0:3]
        elif typ == "run_arms":
            raw[R_MODE] = RUN_ARMS
            raw[R_CMD] = row[0:3]
            raw[L.R_Q][L.ARMS] = row[3:17]
        elif typ == "joints":
            raw[R_MODE] = JOINT
            raw[L.R_Q] = row[0:L.NJ]
        elif typ == "lowcmd":
            raw[R_MODE] = JOINT
            n = L.NJ
            raw[L.R_Q], raw[L.R_DQ], raw[L.R_TAU] = row[0:n], row[n:2 * n], row[2 * n:3 * n]
            raw[L.R_KP], raw[L.R_KD] = row[3 * n:4 * n], row[4 * n:5 * n]
        else:
            raise ValueError(f"unknown action type {typ!r}; one of {list(self.types)}")
        return raw

    def current(self, typ: str, world: "World") -> np.ndarray:
        """The command in force as a row of this type: where a chunk's first row is interpolated from. It is read from
        the sim row in force (World.last_raw, part of the state: a replayed episode has it too): the values that row
        gave for what this type names when it was of this type's mode; otherwise the robot's current targets with zero
        velocity command, velocities and torques and the default gains."""
        r, L = self.r, self.L
        tgt = r.arb.target()
        raw = world.last_raw
        mode = {"stand": STAND, "walk": WALK, "run": RUN, "run_arms": RUN_ARMS, "joints": JOINT, "lowcmd": JOINT,
                "walk_falcon": WALK_FALCON, "walk_agile": WALK_AGILE}[typ]
        same = raw is not None and int(raw[R_MODE]) == mode
        grip = raw[L.R_GRIP].copy() if raw is not None else np.array([float(world.grip_req[s]) for s in SIDES])
        q = raw[L.R_Q] if same else tgt
        cmd = raw[R_CMD] if same else np.zeros(3)
        if typ == "stand":
            return np.r_[q[L.UPPER], grip]
        if typ in ("walk", "walk_falcon", "walk_agile"):
            return np.r_[cmd, q[L.UPPER], grip]
        if typ == "run":
            return np.r_[cmd, grip]
        if typ == "run_arms":
            return np.r_[cmd, q[L.ARMS], grip]
        if typ == "joints":
            return np.r_[q, grip]
        if same:
            return np.r_[q, raw[L.R_DQ], raw[L.R_TAU], raw[L.R_KP], raw[L.R_KD], grip]
        return np.r_[tgt, np.zeros(L.NJ), np.zeros(L.NJ), r.kp0, r.kd0, grip]

    def hold(self, world: "World") -> tuple[str, np.ndarray]:
        """Keep the command in force with no velocity: a walking robot stops and keeps its balance on the walking
        policy, a running one is slowed by the running policy, joint targets (with their gains and feed-forward
        torques, as a `lowcmd` row) stay as they are with zero target velocities."""
        typ = {STAND: "stand", WALK: "walk", RUN: "run", RUN_ARMS: "run_arms", JOINT: "lowcmd",
               WALK_FALCON: "walk_falcon", WALK_AGILE: "walk_agile"}[world.mode]
        row = self.current(typ, world)
        if typ in ("walk", "run", "run_arms", "walk_falcon", "walk_agile"):
            row[0:3] = 0.0
        elif typ == "lowcmd":
            row[self.L.NJ:2 * self.L.NJ] = 0.0
        return typ, row

    def spec(self) -> dict:
        out = {}
        for name, t in self.types.items():
            lo, hi = t["bounds"]
            out[name] = {"dim": t["dim"], "layout": t["layout"], "lower": [round(float(x), 4) for x in lo],
                         "upper": [round(float(x), 4) for x in hi], "meaning": t["meaning"]}
        return out
