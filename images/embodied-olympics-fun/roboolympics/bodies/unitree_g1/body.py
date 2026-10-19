"""The Unitree G1 body (body.toml): MJCF assembly, the walking policy, the waist/arm servo, the kick, the controlled
vector u.

    from bodies import load_body
    B = load_body("unitree_g1")
    B.mount(scene_root, prefix="A_", pos=(0, -1.6, -0.76), yaw=pi / 2, hand="paddle")   # into a scene's XML tree
    rig = B.rig(model, prefix="A_", hand="paddle")      # after compiling (walker="falcon" / "agile": optional policies)
    rig.begin_step(d, u)                                # every 10 ms control step (the policy runs every 20 ms)
    rig.apply(d, u_prev, u, j, u_prev2)                 # every physics substep
    rig.kick(d, foot="right", speed=3.0)                # a kick (kick.py); the walking policy resumes after it

The controlled vector u (body.toml [dof]): [walk_vx, walk_vy, walk_wz, waist_pitch, waist_yaw, arm_0 .. arm_6].
walk_*: the walking policy's velocity command in the robot's body frame; the legs are the policy's (or the kick
controller's) and are not in u. Rig.qadr / vadr / M / joint_targets cover the upper body (waist yaw, roll, pitch,
the hand arm, the other arm), as the wheeled humanoid's Rig, so the whole-body planner works on both bodies; the
legs have their own addresses (lqadr, lvadr, laid).
The same Rig drives a fixed-base copy (robot_only_xml(fixed_base=True): the pelvis welded at the origin) and a planar
copy (fixed_base="planar": no legs, the pelvis on two slides and a hinge at the standing height; the whole-body
planner's model and twin): there u[0:3] are the pelvis position (x, y, yaw), as the wheeled humanoid's base, a
stand-in for where walking puts the pelvis; neither copy has legs or a policy.
"""
from __future__ import annotations

import copy
import math
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from .. import selfcollision as SC
from .. import servo as SV

HERE = Path(__file__).resolve().parent
HANDS = HERE.parent / "hands"
NAME_ATTRS = ("name", "joint", "body", "body1", "body2", "geom", "geom1", "geom2", "site", "mesh", "material",
              "class", "childclass", "target", "texture", "tendon", "actuator")
LEGS = [f"{s}_{j}_joint" for s in ("left", "right") for j in ("hip_pitch", "hip_roll", "hip_yaw", "knee",
                                                              "ankle_pitch", "ankle_roll")]
ARM = ["shoulder_pitch", "shoulder_roll", "shoulder_yaw", "elbow", "wrist_roll", "wrist_pitch", "wrist_yaw"]
TORSO = ["waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint"]
STAND_Z = 0.793                                    # the pelvis above the floor at the policy's default stance
PLAN_Z = 0.778                                     # ... where it settles standing or walking (the planar copy's height)
PLANAR = ["base_x", "base_y", "base_yaw"]


def short(j):
    """'left_hip_pitch_joint' -> 'hip_pitch', 'waist_yaw_joint' -> 'waist_yaw' (body.toml [motors.assign] keys)."""
    s = j[:-len("_joint")] if j.endswith("_joint") else j
    for side in ("left_", "right_"):
        if s.startswith(side):
            return s[len(side):]
    return s


def _toml(p):
    return tomllib.loads(Path(p).read_text())


def _fmt(v):
    return " ".join(repr(float(x)) for x in v)


def quat_z(yaw):
    return (math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2))


class G1Body:
    kind = "legged"
    walkers = ("unitree", "falcon", "agile")     # rig(..., walker=): Unitree's policy (the default), FALCON (falcon.py)
                                                 # or AGILE (agile.py)

    def __init__(self):
        self.decl = _toml(HERE / "body.toml")
        self.hands = _toml(HANDS / "hands.toml")
        self.name = self.decl["body"]["name"]
        self.revision = self.decl["body"]["revision"]
        self.dof = list(self.decl["dof"]["names"])
        W = self.decl["walk"]
        P = W["planning"]                                       # the planner's base tracker (the planar copy): what
        self.base_speed, self.base_accel = float(P["speed_m_s"]), float(P["accel_m_s2"])   # walking really achieves
        self.yaw_rate, self.yaw_accel = float(P["yaw_rate_rad_s"]), float(P["yaw_accel_rad_s2"])
        self.plan_z = PLAN_Z
        C = self.decl["controller"]["step"]
        self.dt = C["control_dt_s"]
        self.substeps = int(round(self.dt / C["physics_dt_s"]))

    # ------------------------------------------------------------------ the template, renamed
    def _hand(self, hand, tag="hand"):
        h = self.hands[hand]
        body = copy.deepcopy(ET.parse(HANDS / h["file"]).getroot().find("worldbody").find("body"))
        contact = set(h.get("contact", []))
        for el in body.iter():
            if el.tag == "body" and el.get("name") == "hand":
                el.set("name", tag)
            elif el.get("name") is not None:
                if el.tag == "geom":
                    c = el.get("name") in contact
                    el.set("contype", "1" if c else "4")
                    el.set("conaffinity", "1" if c else "0")
                el.set("name", f"{tag}_" + el.get("name"))
            elif el.tag == "geom":
                el.set("contype", "4"); el.set("conaffinity", "0")
        return body

    def _template(self, prefix, hand, arm, lod, accent, head_pitch, fixed_base=False):
        root = ET.parse(HERE / self.decl["body"]["model"]).getroot()
        meshdir = HERE / self.decl["body"]["meshes"][lod]
        if lod == "fine" and not meshdir.is_dir():          # the fine meshes are not in git (tools/make_model.py)
            meshdir, lod = HERE / self.decl["body"]["meshes"]["standard"], "standard"
        for m in root.find("asset").findall("mesh"):
            stem = Path(m.get("file")).stem
            m.set("file", str(meshdir / (stem + (".STL" if lod == "fine" else ".stl"))))
        if head_pitch is None:
            head_pitch = self.decl["mounts"]["head_pitch_rad"]
        for b in root.iter("body"):
            if b.get("name") == "head_cam":
                b.set("quat", _fmt((math.cos(head_pitch / 2), 0.0, math.sin(head_pitch / 2), 0.0)))
            if b.get("name") == "torso_link" and accent is not None:
                for g in b.findall("geom"):
                    if g.get("mesh") == "g1_torso_link" and g.get("class") == "g1_visual":
                        g.set("rgba", _fmt(accent))
        if hand:
            mount = next(b for b in root.iter("body") if b.get("name") == f"{arm}_mount")
            mount.append(self._hand(hand))
        if fixed_base:
            pelvis = root.find("worldbody").find("body")
            for j in pelvis.findall("freejoint"):
                pelvis.remove(j)
            for b in list(pelvis):                    # the legs go: the pelvis is welded (or planar)
                if b.tag == "body" and "hip" in (b.get("name") or ""):
                    pelvis.remove(b)
            if fixed_base == "planar":
                for i, (n, typ, ax) in enumerate((("base_x", "slide", "1 0 0"), ("base_y", "slide", "0 1 0"),
                                                  ("base_yaw", "hinge", "0 0 1"))):
                    pelvis.insert(i, ET.Element("joint", name=n, type=typ, axis=ax, damping="0", armature="0.1"))
        for el in root.iter():
            for a in NAME_ATTRS:
                v = el.get(a)
                if v is not None:
                    el.set(a, prefix + v)
        return root

    def joints(self, arm, fixed_base=False):
        other = "left" if arm == "right" else "right"
        upper = ["waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint"] + \
            [f"{arm}_{j}_joint" for j in ARM] + [f"{other}_{j}_joint" for j in ARM]
        return (PLANAR if fixed_base == "planar" else [] if fixed_base else LEGS) + upper

    def _effort(self, j):
        L = self.decl["limits"]
        if j in PLANAR:                               # the planar copy's stand-in for walking
            return 5000.0
        if j.startswith("waist"):
            return L["waist"]["torque_nm"][["waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint"].index(j)]
        for i, a in enumerate(ARM):
            if j.endswith(f"_{a}_joint"):
                return L["arm"]["torque_nm"][i]
        return L["leg"]["torque_nm"][LEGS.index(j) % 6]

    def mount(self, scene: ET.Element, prefix: str, pos, yaw: float, hand: str | None = "paddle", arm: str = "right",
              lod: str = "standard", accent=None, head_pitch=None, fixed_base: bool = False,
              self_collision: bool = True, **_) -> dict:
        """Add one G1 to a scene's XML tree. pos: the point on the floor under the pelvis; yaw: its facing (the robot's
        forward axis = world x rotated by yaw). The pelvis starts at the policy's stand height."""
        t = self._template(prefix, hand, arm, lod, accent, head_pitch, fixed_base)
        sc = SC.plan(t, self.decl["self_collision"], prefix=prefix) if self_collision else None   # selfcollision.py
        for sec in ("default", "asset"):
            dst = scene.find(sec)
            if dst is None:
                dst = ET.SubElement(scene, sec)
            for el in t.find(sec):
                dst.append(el)
        pelvis = t.find("worldbody").find("body")
        z = PLAN_Z if fixed_base == "planar" else 0.0 if fixed_base else STAND_Z
        p = np.asarray(pos, float) + np.array([0.0, 0.0, z])
        pelvis.set("pos", _fmt(p))
        pelvis.set("quat", _fmt(quat_z(yaw)))
        scene.find("worldbody").append(pelvis)
        if sc is not None:                        # the robot's self-collision pairs (body.toml [self_collision])
            SC.add_pairs(scene, sc)
        act = scene.find("actuator")
        if act is None:
            act = ET.SubElement(scene, "actuator")
        for j in self.joints(arm, fixed_base):
            lim = self._effort(j)
            ET.SubElement(act, "motor", name=f"{prefix}m_{j}", joint=prefix + j, ctrlrange=f"{-lim!r} {lim!r}")
        return {**SC.info(sc), "prefix": prefix, "base": prefix + "pelvis", "hand": prefix + "hand" if hand else None,
                "tool_site": prefix + "hand_" + self.hands[hand]["site"] if hand else None,
                "contact_geoms": [prefix + "hand_" + g for g in self.hands[hand].get("contact", [])] if hand else [],
                "feet": [prefix + "left_foot_strike", prefix + "right_foot_strike"], "arm": arm,
                "cameras": [prefix + c for c in self.decl["mounts"]["cameras"]]}

    @staticmethod
    def guard_root(arm):
        """The forearm's link: the planner keeps it and everything below it out of a sport's keep-out boxes."""
        return f"{arm}_elbow_link"

    def robot_only_xml(self, hand="paddle", arm="right", lod="standard", meshdir: str | None = None,
                       option: dict | None = None, header: str = "", fixed_base="planar",
                       self_collision: bool = True) -> str:
        """The robot alone: by default the planar copy (the planner's model, a low-level player's model)."""
        root = ET.Element("mujoco", model=f"{self.name}_{hand}_robot_only")
        if header:
            root.append(ET.Comment(header))
        ET.SubElement(root, "compiler", angle="radian", autolimits="true", **({"meshdir": meshdir} if meshdir else {}))
        ET.SubElement(root, "option", **(option or {"timestep": "0.001", "integrator": "implicitfast"}))
        for sec in ("default", "asset", "worldbody"):
            ET.SubElement(root, sec)
        self.mount(root, "", (0.0, 0.0, 0.0), 0.0, hand=hand, arm=arm, lod=lod, fixed_base=fixed_base,
                   self_collision=self_collision)
        if meshdir:
            for m in root.find("asset").findall("mesh"):
                m.set("file", Path(m.get("file")).name)
        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode") + "\n"

    def rig(self, model, prefix="", arm="right", hand="paddle", rest=None, walker="unitree"):
        return G1Rig(self, model, prefix, arm, hand, rest, walker)


class WalkPolicy:
    """Unitree's walking policy (body.toml [walk]) for one robot: the observation, the LSTM memory, the leg targets. The
    network (LSTM 47 -> 64, Linear 64 -> 32, ELU, Linear 32 -> 12) runs in numpy (float64) from policy/motion.npz
    (tools/export_policy.py: the weights of Unitree's motion.pt, unchanged)."""

    def __init__(self, decl):
        W = decl["walk"]
        z = np.load(HERE / W["weights"])
        self.w_ih, self.w_hh = z["w_ih"].astype(float), z["w_hh"].astype(float)
        self.b = z["b_ih"].astype(float) + z["b_hh"].astype(float)
        self.w0, self.b0 = z["w0"].astype(float), z["b0"].astype(float)
        self.w2, self.b2 = z["w2"].astype(float), z["b2"].astype(float)
        self.nh = self.w_hh.shape[1]
        self.default = np.array(W["default_angles"], float)
        self.scale = float(W["action_scale"])
        S = W["obs_scales"]
        self.s_ang, self.s_pos, self.s_vel = S["ang_vel"], S["dof_pos"], S["dof_vel"]
        self.s_cmd = np.array(S["cmd"], float)
        self.period = float(W["gait_period_s"])
        self.reset()

    def reset(self):
        self.h = np.zeros(self.nh)
        self.c = np.zeros(self.nh)
        self.action = np.zeros(12)
        self.targets = self.default.copy()

    def net(self, x):
        g = self.w_ih @ x + self.w_hh @ self.h + self.b
        n = self.nh
        sig = lambda v: 1.0 / (1.0 + np.exp(-v))
        i, f, gg, o = sig(g[0:n]), sig(g[n:2 * n]), np.tanh(g[2 * n:3 * n]), sig(g[3 * n:4 * n])
        self.c = f * self.c + i * gg
        self.h = o * np.tanh(self.c)
        y = self.w0 @ self.h + self.b0
        y = np.where(y > 0, y, np.expm1(np.minimum(y, 0.0)))          # ELU
        return self.w2 @ y + self.b2

    def step(self, quat, omega, q, qd, cmd, t):
        w, x, y, z = quat
        g = np.array([2 * (-z * x + w * y), -2 * (z * y + w * x), 1 - 2 * (w * w + z * z)])
        ph = (t % self.period) / self.period
        obs = np.concatenate([omega * self.s_ang, g, np.asarray(cmd) * self.s_cmd, (q - self.default) * self.s_pos,
                              qd * self.s_vel, self.action, [math.sin(2 * math.pi * ph), math.cos(2 * math.pi * ph)]])
        self.action = self.net(obs)
        self.targets = self.action * self.scale + self.default
        return self.targets

    def state(self):
        """The policy's memory (LSTM state, last action): for hashing and copying."""
        return np.concatenate([self.h, self.c, self.action])


class G1Rig:
    """One mounted G1 in a compiled model: upper-body addresses, limits and servo (as the wheeled humanoid's Rig), plus
    the legs: the walking policy, the kick, their PD."""

    def __init__(self, body: G1Body, model, prefix="", arm="right", hand="paddle", rest=None, walker="unitree"):
        import mujoco as mj
        if walker not in body.walkers:
            raise ValueError(f"unknown walker {walker!r}; one of {list(body.walkers)}")
        self.mj, self.B, self.m, self.prefix, self.arm, self.walker = mj, body, model, prefix, arm, walker
        D = body.decl
        jid = lambda n: mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, prefix + n)
        self.fixed_base = jid("left_hip_pitch_joint") < 0
        self.planar = jid("base_x") >= 0
        upper = (PLANAR if self.planar else []) + body.joints(arm, fixed_base=True)
        o = 3 if self.planar else 0               # the planar copy's base joints come first
        ids = [jid(j) for j in upper]
        if min(ids) < 0:
            raise ValueError(f"robot {prefix!r} not in the model")
        self.joints = upper
        self.qadr = np.array([model.jnt_qposadr[i] for i in ids])
        self.vadr = np.array([model.jnt_dofadr[i] for i in ids])
        self.aid = np.array([mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, f"{prefix}m_{j}") for j in upper])
        self.tau_lim = model.actuator_ctrlrange[self.aid, 1].copy()
        # u -> upper-body joint targets: [waist yaw, roll, pitch, arm x 7, other arm x 7] = M @ u + c
        self.M = np.zeros((17 + o, 12))
        for k in range(o):
            self.M[k, k] = 1.0
        self.M[o + 0, 4] = 1.0                   # waist yaw
        self.M[o + 2, 3] = 1.0                   # waist pitch
        for i in range(7):
            self.M[o + 3 + i, 5 + i] = 1.0
        R = D["rest"]
        self.c = np.zeros(17 + o)
        self.c[o + 10:o + 17] = R["other_arm"]
        C, L = D["controller"], D["limits"]
        Pl = D["walk"]["planning"]
        base_kp, base_kd = (Pl["base_kp"], Pl["base_kd"]) if o else ([], [])
        self.kp = np.r_[base_kp, C["kp"]["waist"], C["kp"]["arm"], C["kp"]["arm"]]
        self.kd = np.r_[base_kd, C["kd"]["waist"], C["kd"]["arm"], C["kd"]["arm"]]
        self.o = o
        jr = model.jnt_range[ids[o:]]
        W = D["walk"]
        self.LO = np.r_[-np.array(L["walk"]["command_max"]), jr[2, 0], jr[0, 0], jr[3:10, 0]]
        self.HI = np.r_[np.array(L["walk"]["command_max"]), jr[2, 1], jr[0, 1], jr[3:10, 1]]
        self.VEL = np.r_[L["walk"]["command_accel"], L["waist"]["speed_rad_s"][2], L["waist"]["speed_rad_s"][0],
                         L["arm"]["speed_rad_s"]]
        if self.planar:                           # the planar copy: u[0:3] = the pelvis position, as a mobile base
            self.LO[0:3], self.HI[0:3] = -np.inf, np.inf
            self.VEL[0:3] = body.base_speed, body.base_speed, body.yaw_rate
        self.STEP = self.VEL * body.dt             # the walk command: its change per step; the joints: their speed
        self.rest = np.r_[0.0, 0.0, 0.0, R["waist"], R["arm"]]
        if rest is not None:
            self.rest[3:] = rest
        self.dt, self.substeps = body.dt, body.substeps
        self.tool_site = mj.mj_name2id(model, mj.mjtObj.mjOBJ_SITE, prefix + "hand_" + body.hands[hand]["site"]) \
            if hand else -1
        self.base_body = mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, prefix + "pelvis")
        self.cmd = np.zeros(3)
        self.mode = "walk"
        self.kicker = None
        self.k = 0
        self.farms = None
        self.residual = False                     # FALCON's wrist residual (falcon.py); AGILE has none
        if not self.fixed_base:
            lids = [jid(j) for j in LEGS]
            self.lqadr = np.array([model.jnt_qposadr[i] for i in lids])
            self.lvadr = np.array([model.jnt_dofadr[i] for i in lids])
            self.laid = np.array([mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, f"{prefix}m_{j}") for j in LEGS])
            self.ltau = model.actuator_ctrlrange[self.laid, 1].copy()
            fj = next(j for j in range(model.njnt) if model.jnt_bodyid[j] == self.base_body)
            self.fqadr, self.fvadr = int(model.jnt_qposadr[fj]), int(model.jnt_dofadr[fj])
            if walker != "unitree":               # the optional FALCON / AGILE policy (falcon.py, agile.py; body.toml
                if walker == "falcon":            # [walk.falcon], [walk.agile]): they read all 29 joints
                    from .falcon import Falcon as Policy
                else:
                    from .agile import Agile as Policy
                self.policy = Policy(D)
                self.lkp, self.lkd = self.policy.kp, self.policy.kd
                fids = [jid(j) for j in LEGS + TORSO + [f"{s}_{a}_joint" for s in ("left", "right") for a in ARM]]
                self.fq, self.fv = model.jnt_qposadr[fids], model.jnt_dofadr[fids]
                self.farms = [upper.index(f"{s}_{a}_joint") for s in ("left", "right") for a in ARM]
                self.residual = walker == "falcon"
            else:
                self.policy = WalkPolicy(D)
                self.lkp, self.lkd = np.array(W["kp"], float), np.array(W["kd"], float)
            self.leg_targets = self.policy.default.copy()
        # the servos (bodies/servo.py): the upper body's commanded joints (setpoints at the speed limits, the motor
        # curves at the output), the legs' output stage (the motor curves), the walking command (the real joystick
        # range, rate-limited)
        upper_keys = ([None] * 3 if self.planar else []) + [short(j) for j in body.joints(arm, fixed_base=True)]
        leg_keys = [] if self.fixed_base else [short(j) for j in LEGS]
        self.servo, self.legs_act, self.ACC = SV.legged_layout(model, self, D, body.dt / body.substeps, upper_keys,
                                                               leg_keys, Pl if self.planar else None)
        self.walk = SV.WalkCommand(L["walk"], body.dt)
        self.selfcol = SC.Monitor(model, prefix + "selfcol", D["self_collision"].get("warn_force_n"))   # recorded only

    # u <-> joints
    def joint_targets(self, u):
        return self.M @ np.asarray(u, float) + self.c

    def u_of(self, d):
        q, o = d.qpos[self.qadr], self.o
        return np.r_[q[0:3] if o else self.cmd, q[o + 2], q[o], q[o + 3:o + 10]]

    def ud_of(self, d):
        v, o = d.qvel[self.vadr], self.o
        return np.r_[v[0:3] if o else np.zeros(3), v[o + 2], v[o], v[o + 3:o + 10]]

    def base_pose(self, d):
        """The pelvis on the floor: (x, y, yaw) in the world (the yaw of its forward axis)."""
        R = d.xmat[self.base_body].reshape(3, 3)
        p = d.xpos[self.base_body]
        return np.array([p[0], p[1], math.atan2(R[1, 0], R[0, 0])])

    def pelvis(self, d):
        """(position, rotation matrix) of the pelvis in the world."""
        return d.xpos[self.base_body].copy(), d.xmat[self.base_body].reshape(3, 3).copy()

    def place(self, d, u, pos=None, yaw=None):
        """Teleport to standing at the mount (or at pos / yaw) with the upper body at u; the policy's memory reset."""
        d.qpos[self.qadr] = self.joint_targets(u)
        d.qvel[self.vadr] = 0.0
        if not self.fixed_base:
            m = self.m
            j = self.fqadr
            p0 = m.body_pos[self.base_body] if pos is None else np.asarray(pos, float)
            q0 = m.body_quat[self.base_body] if yaw is None else np.array(quat_z(yaw))
            d.qpos[j:j + 3] = p0
            d.qpos[j + 3:j + 7] = q0
            d.qvel[self.fvadr:self.fvadr + 6] = 0.0
            d.qpos[self.lqadr] = self.policy.default
            d.qvel[self.lvadr] = 0.0
            self.policy.reset()
            self.walk.reset()
            self.legs_act.reset()
            self.leg_targets = self.policy.default.copy()
            self.mode, self.kicker, self.cmd, self.k = "walk", None, np.zeros(3), 0
        self.sync(d)

    def sync(self, d):
        """The servo's setpoint generator to the upper body's measured state (after a teleport or a state copy)."""
        x, xd = self.u_of(d), self.ud_of(d)
        if not self.planar:
            x[0:3], xd[0:3] = 0.0, 0.0                    # the walking command is not a position
        self.servo.reset(x, xd)

    # the control step
    def begin_step(self, d, u):
        """Once per 10 ms control step, before its substeps: the walking command from u, the policy every 20 ms
        (or the kick's leg targets)."""
        if self.fixed_base:
            return
        self.cmd = self.walk(u[0:3]).copy()        # the real joystick range, rate-limited (bodies/servo.py)
        if self.mode == "kick":
            self.leg_targets = self.kicker.step(d)
            if self.kicker.done:
                self.mode, self.kicker = "walk", None
                self.policy.reset()
                self.k = 0
        if self.mode == "walk" and self.k % 2 == 0:
            j, v = self.fqadr, self.fvadr
            if self.walker != "unitree":          # all 29 joints, u's arm targets and waist yaw (falcon.py; agile.py
                                                  # reads the joints only)
                up = self.joint_targets(u)
                self.leg_targets = self.policy.step(d.qpos[j + 3:j + 7], d.qvel[v + 3:v + 6], d.qpos[self.fq],
                                                    d.qvel[self.fv], self.cmd, up[self.farms], up[0])[:12]
            else:
                self.leg_targets = self.policy.step(d.qpos[j + 3:j + 7], d.qvel[v + 3:v + 6], d.qpos[self.lqadr],
                                                    d.qvel[self.lvadr], self.cmd, self.k * self.dt)
        self.k += 1

    def apply(self, d, u_prev, u_next, j, u_prev2=None):
        """Physics substep j: the upper body through its servo (bodies/servo.py: setpoints within the limits, PD +
        bias + inertia feed-forward, the motor curves) and the legs' PD through their output stage (the motor
        curves). u_prev2 is accepted for the old signature."""
        self.selfcol.update(d)                    # self-collision contacts of the last physics step (recorded)
        if not self.servo.ready:
            self.sync(d)
        a, b = np.asarray(u_prev, float), np.asarray(u_next, float)
        extra = None                              # FALCON's balance residual of the wrists, as a target offset
        if self.residual and self.mode == "walk":
            extra = np.zeros(len(self.kp))
            extra[self.farms] = self.policy.wrist_torque(self.kp[self.farms])
        self.servo.track(d, a + (b - a) * (j / self.substeps), (b - a) / self.dt, extra)
        if not self.fixed_base:
            kp, kd = (self.kicker.kp, self.kicker.kd) if self.mode == "kick" else (self.lkp, self.lkd)
            lt = kp * (self.leg_targets - d.qpos[self.lqadr]) - kd * d.qvel[self.lvadr]
            if self.mode == "kick":
                lt = lt + self.kicker.ff
            self.legs_act.write(d, lt)

    def self_collisions(self) -> dict:
        """The self-collision record since the rig was built or reset (bodies/selfcollision.py Monitor.summary):
        events, warnings, time in contact, peak force, impulse, the worst pairs. For the match record."""
        return self.selfcol.summary()

    def check(self, u, u_prev, u_prev2=None):
        """A target row against the limits (bodies/servo.py check_row): ranges (the walking command within the real
        joystick range), per-step changes (joint speeds, the walking command's rate); with u_prev2 the planar copy's
        base acceleration. None or the reason."""
        return SV.check_row(u, u_prev, u_prev2, self.LO, self.HI, self.VEL, self.ACC, self.dt,
                            self.servo.base.lim if self.servo.base is not None else None)

    def tool(self, d):
        return d.site_xpos[self.tool_site].copy(), d.site_xmat[self.tool_site].reshape(3, 3).copy()

    def kick(self, d, foot="right", speed=2.5, height=0.10, reach=0.22, target=None, direction=None):
        """Start a kick (kick.py): the legs leave the policy until it ends. target: the world point the foot's strike
        box passes through at `speed` (m/s; e.g. a little below and behind the ball's centre); direction: the swing's
        world direction (default the robot's forward axis); without a target the foot strikes `reach` beyond the
        support foot's toe line, `height` above the ground."""
        if self.fixed_base or self.mode == "kick":
            return False
        from .kick import Kick
        self.kicker = Kick(self, d, foot, speed, height, reach, target, direction)
        self.mode = "kick"
        return True

    def memory(self):
        return self.policy.state() if not self.fixed_base else np.zeros(0)


_BODY: dict = {}


def load() -> G1Body:
    if "g1" not in _BODY:
        _BODY["g1"] = G1Body()
    return _BODY["g1"]
