"""The real hand: Unitree's Dex1-1 two-finger parallel gripper on a wrist mount, holding objects by contact and friction
only (no weld: what it holds can slip, twist and drop). Opt-in per side from a family's build():

    sc.real_hands["right"] = "dex1"            # and/or "left"; default: none (the palm pad and the weld grip)

The Dex1-1 (https://www.unitree.com/Dex1-1, product page 2026-10): 143 x 78 x 67 mm, 0.55 kg; stroke 90 mm; jaw length
80 mm; grip force 5-120 N (adjustable); speed 50-375 mm/s; full-stroke close 0.24 s; width 78 mm half open, 120 mm
fully open; friction-grasp load 5 kg; sold for the G1, the H2 and the R1 (not for the H1 / H1-2: on the H1-2 it is a
deviation, mounted where the Inspire hand's palm ends, on the same wrist mount as every other hand tool).

The model, in the wrist mount's frame (+z along the forearm away from the wrist; +x the palm's normal):
  housing   a box 78 (x) x 67 (y) x 63 (z) mm from the mount's origin outwards, 0.43 kg
  jaws      two fingers 80 mm long (z, from 63 to 143 mm), 15 mm thick (x), 34 mm wide (y), 0.06 kg each, on slide
            joints along x: jaw "a" on the palm side (+x), jaw "b" on the back of the hand (-x); the opening between
            their pads is 90 mm open, 0 closed; an equality couples the two (the rack and pinion: one DoF)
  pads      the inner face of each jaw is a rubber pad of 3 x 2 overlapping segments (2 mm proud, 80 x 34 mm in all) so
            a handle gets a contact patch, not one point: friction 1.0, torsional friction 5 mm (condim 4), priority 2
            (the pad's contact parameters win over the held object's), stiff (solref 0.004 1, solimp 0.99 0.999)
  friction  a world with a real hand gets elliptic friction cones and impratio 100 (unless the family set them): MuJoCo's
            friction is soft, and with its defaults a clamped handle creeps under a steady torque (IMPRATIO)
  centre    a site `<side>_jaw_centre` (also the hand's palm site) midway between the pads and along them, mount axes
The housing and the jaws are part `<side>_hand` for the referee, contype 4 / conaffinity 0 like the body's hulls (they
touch every prop, contype 1 / conaffinity 13 or 5, not the robot itself), plus explicit pairs with the hulls of the
rest of the body (the other arm, the trunk, the legs) like a hand tool, and between two grippers.

The controller (each 1 ms physics step; RAW_DIM unchanged): the sim row's `grip_<side>` is the closure command c in
[0, 1] (clipped): the commanded opening is 90 mm x (1 - c). A setpoint per jaw moves towards 45 mm x c at most
187.5 mm/s (the opening at 375 mm/s: full stroke in 0.24 s), and each jaw is a force-limited PD servo on it:
force = clip(KP (setpoint - q) - KV dq, -120 N, 120 N), KP = 20 000 N/m, KV = 80 N s/m. A command that opens starts
from where the jaws are (the setpoint of a clamp, which ran on past the object, comes back to the jaws at once): a
clamp eases or lets go within a physics step, then the jaws open at the speed limit. On an object the jaws stop on,
the clamp force is therefore min(120 N, 10 N per mm that the commanded opening is below the object's width): a fully
closed command (c = 1) clamps anything wider than 12 mm at the full 120 N; a command a few mm under the width clamps
lightly (and the object slips).

What the hand holds (`World.held[side]`): the body that touches both jaws now (by contact, at every physics step);
None otherwise. A family puts an object between the open jaws at reset and calls `w.close_on(side, name)`.

The speed limit is the setpoint's: the jaws themselves follow it a little faster when nothing holds them (about
0.39 m/s opening freely) and, for a few milliseconds, up to about 0.45 m/s when a clamp springs open (the pads'
stored compression).

Deviations from the device: one closure command per hand (the real one also takes a speed and a force setting: here
the speed is the maximum and the force follows from the commanded opening); no 5 N minimum force; two pads at
friction 1.0 and 120 N hold about 240 N of shear, some five times the device's rated 5 kg friction-grasp load; the
drive's inertia (ARMATURE) is an estimate; the gripper's 0.55 kg comes on top of the wrist link's own mass, which
keeps the hand it replaces (the G1's rubber fist: only its mesh goes; the H1-2's Inspire hand: its finger bodies,
about 0.05 kg per hand, go, its palm stays); on the H1-2 (for which Unitree does not sell it) the gripper sits where
the Inspire palm ends, which makes that forearm longer than a real installation would.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import numpy as np

import mujoco

KINDS = ("dex1",)
STROKE = 0.090                 # m: the opening between the pads, fully open
HALF = STROKE / 2              # m: one jaw's travel
JAW_LEN, JAW_THICK, JAW_WIDE = 0.080, 0.015, 0.034
HOUSING = (0.039, 0.0335, 0.0315)          # half sizes (x, y, z): 78 x 67 x 63 mm
PAD = 0.002                    # m: the pad's thickness (proud of the finger)
CENTRE_Z = 2 * HOUSING[2] + JAW_LEN / 2    # 0.103 m: the jaws' centre along the mount's z
F_MAX = 120.0                  # N: the grip force limit (per jaw: the clamp force)
SPEED = 0.375                  # m/s: the opening's speed limit (each jaw half of it)
KP, KV = 20000.0, 80.0         # N/m, N s/m: the jaw servo
MASS_HOUSING, MASS_JAW = 0.43, 0.06
ARMATURE = 0.05                # kg: the drive's reflected inertia on each jaw (an estimate)
PAD_FRICTION = (1.0, 0.005, 0.0001)
PAD_SOLREF, PAD_SOLIMP = "0.004 1", "0.99 0.999 0.0005"
IMPRATIO = 100.0               # a world with a real hand: elliptic friction cones and impratio 100. MuJoCo's friction is
#                                soft: with the default pyramidal cones a 120 N grasp let a 0.84 N m handle torque turn it
#                                34 deg in 3 s; elliptic + impratio 10: 0.5 deg/s; 100: 0.05 deg/s
JAWS = ("a", "b")              # a: the palm side (+x), b: the back (-x)
FREEZE_ARMATURE = 1e5          # kg (m^2): the rest of the world's inertia while close_on settles a grasp


def _f(v) -> str:
    return " ".join(f"{float(x):.6g}" for x in v)


def build(root: ET.Element, mount: ET.Element, side: str, robot: str) -> list[str]:
    """Mount a Dex1-1 on `mount` (an ElementTree body) and add its motors and coupling. Returns the collision geoms that
    get explicit pairs with the rest of the robot's body (housing and fingers)."""
    col = dict(contype="4", conaffinity="0")
    pre = f"{side}_hand"
    ET.SubElement(mount, "site", name=f"{side}_jaw_centre", pos=_f((0, 0, CENTRE_Z)), size="0.006", group="4")
    ET.SubElement(mount, "geom", name=f"{pre}_housing", type="box", pos=_f((0, 0, HOUSING[2])), size=_f(HOUSING),
                  mass=f"{MASS_HOUSING}", rgba="0.18 0.18 0.2 1", friction="0.8 0.005 0.0001", group="2", **col)
    out = [f"{pre}_housing"]
    for j, s in zip(JAWS, (1, -1)):
        x0 = s * (HALF + PAD + JAW_THICK / 2)
        b = ET.SubElement(mount, "body", name=f"{pre}_jaw_{j}", pos=_f((x0, 0, CENTRE_Z)))
        ET.SubElement(b, "joint", name=f"{pre}_jaw_{j}", type="slide", axis=_f((-s, 0, 0)), range=f"0 {HALF:.6g}",
                      armature=f"{ARMATURE}", damping="0", limited="true")
        ET.SubElement(b, "geom", name=f"{pre}_jaw_{j}", type="box", size=_f((JAW_THICK / 2, JAW_WIDE / 2, JAW_LEN / 2)),
                      mass=f"{MASS_JAW * 0.8:.6g}", rgba="0.75 0.76 0.8 1", friction="0.8 0.005 0.0001", group="2",
                      **col)
        out.append(f"{pre}_jaw_{j}")
        k = 0
        for iz in range(3):                       # the pad: 3 x 2 segments on the inner face (-s x side), overlapping
            #                                       by 1 mm (a gap between them would give a handle lying on it tilted
            #                                       edge normals that squeeze it sideways)
            for iy in range(2):
                pz = (iz - 1) * JAW_LEN / 3
                py = (iy - 0.5) * JAW_WIDE / 2
                ET.SubElement(b, "geom", name=f"{pre}_pad_{j}{k}", type="box",
                              pos=_f((-s * (JAW_THICK / 2 + PAD / 2), py, pz)),
                              size=_f((PAD / 2, JAW_WIDE / 4 + 0.0005, JAW_LEN / 6 + 0.0005)),
                              mass=f"{MASS_JAW * 0.2 / 6:.6g}", rgba="0.08 0.08 0.08 1", condim="4", priority="2",
                              friction=_f(PAD_FRICTION), solref=PAD_SOLREF, solimp=PAD_SOLIMP, group="2", **col)
                k += 1
    act = root.find("actuator")
    for j in JAWS:
        ET.SubElement(act, "general", name=f"{pre}_jaw_{j}", joint=f"{pre}_jaw_{j}", gaintype="fixed",
                      gainprm=f"{KP:g}", biastype="affine", biasprm=f"0 {-KP:g} {-KV:g}", ctrllimited="true",
                      ctrlrange=f"0 {HALF:.6g}", forcelimited="true", forcerange=f"{-F_MAX:g} {F_MAX:g}")
    ET.SubElement(root.find("equality"), "joint", name=f"{pre}_couple", joint1=f"{pre}_jaw_b", joint2=f"{pre}_jaw_a",
                  polycoef="0 1 0 0 0", solref="0.002 1", solimp="0.95 0.99 0.001")
    return out


def strip_hand(root: ET.Element, side: str, robot: str) -> None:
    """The robot's own hand on that side goes where the gripper replaces it: the G1's rubber fist (a visual mesh) and
    the H1-2's Inspire fingers (visual-only bodies). The hand's collision shell of the H1-2 (part of the wrist link's
    hull and of the robot's self-collision) stays."""
    wl = next(b for b in root.iter("body") if b.get("name") == f"{side}_wrist_yaw_link")
    for g in list(wl.findall("geom")):
        if "rubber_hand" in (g.get("mesh") or ""):
            wl.remove(g)
    for b in list(wl.findall("body")):
        if (b.get("name") or "")[:2] in ("L_", "R_"):
            wl.remove(b)


class RealHands:
    """The grippers of one world: addresses, the servo's setpoints, the contacts that say what each holds."""

    def __init__(self, w, sides: dict):
        m = w.m
        self.w, self.sides = w, [s for s in ("left", "right") if s in sides]
        self.kind = {s: sides[s] for s in self.sides}
        self.jq = {s: np.array([int(m.jnt_qposadr[m.joint(f"{s}_hand_jaw_{j}").id]) for j in JAWS]) for s in self.sides}
        self.jv = {s: np.array([int(m.jnt_dofadr[m.joint(f"{s}_hand_jaw_{j}").id]) for j in JAWS]) for s in self.sides}
        self.act = {s: np.array([m.actuator(f"{s}_hand_jaw_{j}").id for j in JAWS]) for s in self.sides}
        self.centre = {s: m.site(f"{s}_jaw_centre").id for s in self.sides}
        # geom -> code: 0 not a jaw, 1 + 2 i + k for side i, jaw k (the finger and its pads)
        code = np.zeros(m.ngeom, dtype=np.int64)
        for i, s in enumerate(self.sides):
            for k, j in enumerate(JAWS):
                b = m.body(f"{s}_hand_jaw_{j}").id
                code[m.geom_bodyid == b] = 1 + 2 * i + k
        self.jaw_code = code
        self.robot_body = np.zeros(m.nbody, dtype=bool)
        self.robot_body[list(w.robot.bodies)] = True
        # what a hand can hold: a body that moves, i.e. hangs under a free joint (a prop, a racket, a rope's link),
        # never the world body, a static body or the robot itself
        free_root = np.zeros(m.nbody, dtype=bool)
        for j in range(m.njnt):
            if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE:
                free_root[int(m.jnt_bodyid[j])] = True
        movable = np.zeros(m.nbody, dtype=bool)
        for b in range(1, m.nbody):
            p = b
            while p > 0 and not free_root[p]:
                p = int(m.body_parentid[p])
            movable[b] = p > 0
        self.holdable = movable & ~self.robot_body
        self._scratch = None
        self.reset()

    def reset(self) -> None:
        self.cmd = {s: 0.0 for s in self.sides}          # the closure command in force (0 open .. 1 closed)
        self.setpoint = {s: 0.0 for s in self.sides}     # each jaw's servo setpoint (m of travel from open)

    # ------------------------------------------------------------------ control
    def command(self, grips) -> None:
        """The sim row's grip values (left, right): the closure command of each real hand."""
        for i, s in enumerate(("left", "right")):
            if s in self.cmd:
                self.cmd[s] = float(np.clip(grips[i], 0.0, 1.0))

    def substep(self) -> None:
        """Before each physics step: the setpoints one step on (rate limited), into the jaw servos."""
        d = self.w.d
        step = SPEED / 2 * self.w.m.opt.timestep
        for s in self.sides:
            tgt = HALF * self.cmd[s]
            sp = self.setpoint[s]
            if tgt < sp:                          # opening: from where the jaws are (no wind-up of a blocked clamp,
                q = float(d.qpos[self.jq[s]].mean())      # whose setpoint ran on past the object)
                sp = max(tgt, min(sp, q))
            sp = sp + min(max(tgt - sp, -step), step)
            self.setpoint[s] = sp
            d.ctrl[self.act[s]] = sp

    def write_ctrl(self) -> None:
        """The setpoints in force into the servos (after a reset cleared the controls)."""
        for s in self.sides:
            self.w.d.ctrl[self.act[s]] = self.setpoint[s]

    def update_held(self) -> None:
        """After each physics step: what each hand holds (a movable body, under a free joint, touching both jaws),
        into World.held."""
        w, d, m = self.w, self.w.d, self.w.m
        n = d.ncon
        touch = {}
        if n:
            g = d.contact.geom[:n]
            keep = d.contact.dist[:n] <= 0.0
            g1, g2 = g[keep, 0], g[keep, 1]
            c1, c2 = self.jaw_code[g1], self.jaw_code[g2]
            b1, b2 = m.geom_bodyid[g1], m.geom_bodyid[g2]
            for ca, ob in ((c1, b2), (c2, b1)):
                sel = (ca > 0) & self.holdable[ob]
                for c, b in zip(ca[sel], ob[sel]):
                    touch.setdefault(int(b), set()).add(int(c))
        for i, s in enumerate(self.sides):
            both = sorted(b for b, cs in touch.items() if {1 + 2 * i, 2 + 2 * i} <= cs)
            names = [m.body(b).name for b in both]
            if w.held[s] in names:                # several between the jaws: the one already held, else the lowest id
                continue
            w.held[s] = names[0] if names else None

    # ------------------------------------------------------------------ what it senses
    def opening(self, s: str) -> float:
        return float(STROKE - self.w.d.qpos[self.jq[s]].sum())

    def opening_speed(self, s: str) -> float:
        return float(-self.w.d.qvel[self.jv[s]].sum())

    def force(self, s: str) -> float:
        """The clamp force (N): the mean of the two jaw servos' forces, positive closing."""
        return float(self.w.d.actuator_force[self.act[s]].mean())

    def layout(self) -> list[str]:
        return [f"{k}_{s}" for s in self.sides for k in ("jaw_opening", "jaw_speed", "jaw_force")]

    def proprio(self) -> list[float]:
        return [v for s in self.sides for v in (self.opening(s), self.opening_speed(s), self.force(s))]

    def state(self) -> dict:
        """For privileged tooling: per real hand the command, the opening (m), its speed (m/s), the clamp force (N),
        what it holds, the jaw centre's position and axes (world)."""
        d = self.w.d
        out = {}
        for s in self.sides:
            R = d.site_xmat[self.centre[s]].reshape(3, 3)
            out[s] = {"kind": self.kind[s], "command": self.cmd[s], "opening_m": self.opening(s),
                      "opening_speed_m_s": self.opening_speed(s), "force_n": self.force(s), "holding": self.w.held[s],
                      "centre": d.site_xpos[self.centre[s]].tolist(), "closing_axis": R[:, 0].tolist(),
                      "finger_axis": R[:, 2].tolist()}
        return out

    def facts(self) -> dict:
        """The grippers' description for the task texts and spec()["robot_facts"]: the device, the controller, the
        start (closure command and what each holds at t = 0)."""
        return {"kind": "dex1", "model": "Unitree Dex1-1 two-finger parallel gripper (modelled: 0.55 kg, jaws 80 mm "
                "long, 90 mm stroke, rubber pads)", "sides": list(self.sides), "stroke_m": STROKE,
                "jaw_length_m": JAW_LEN, "force_limit_n": F_MAX, "setpoint_opening_speed_m_s": SPEED,
                "jaw_speed_note": "the limit is the servo setpoint's; the jaws can move briefly up to about 0.45 m/s "
                                  "when a clamp springs open",
                "servo": {"kp_n_per_m": KP, "kd_n_s_per_m": KV, "rule": "each jaw: a setpoint moves towards 45 mm x "
                          "closure at most half setpoint_opening_speed_m_s (opening, it starts from the jaws' position); force = clip(kp (setpoint - q) - kd dq, "
                          "-force_limit_n, force_limit_n); the clamp on an object is min(force_limit_n, 10 N per mm "
                          "that the commanded opening 90 mm x (1 - closure) is below the object's width)"},
                "pad": {"friction": list(PAD_FRICTION), "condim": 4},
                "start": {s: {"closure": round(self.cmd[s], 4), "holding": self.w.held[s]} for s in self.sides}}

    def memory(self) -> np.ndarray:
        return np.array([v for s in self.sides for v in (self.cmd[s], self.setpoint[s])], float)

    # ------------------------------------------------------------------ the start
    def jaw_frame(self, s: str) -> tuple[np.ndarray, np.ndarray]:
        """(position, 3 x 3 rotation) of the jaw centre in the world: columns x = the closing axis (towards jaw a, the
        palm side), y = across the jaws, z = along the fingers away from the wrist."""
        m, d = self.w.m, self.w.d
        if self._scratch is None:               # the kinematics on a scratch copy: reading the frame between control
            self._scratch = mujoco.MjData(m)    # steps must not change the live data (the next step reads it)
        k = self._scratch
        k.qpos[:] = d.qpos
        k.mocap_pos[:], k.mocap_quat[:] = d.mocap_pos, d.mocap_quat
        mujoco.mj_kinematics(m, k)
        return k.site_xpos[self.centre[s]].copy(), k.site_xmat[self.centre[s]].reshape(3, 3).copy()

    def close_on(self, s: str, name: str, closure: float = 1.0, settle_s: float = 0.3) -> dict:
        """At reset: close this hand's jaws on the free body `name` (already placed between the open jaws) and settle
        the grasp, with the rest of the world held still: the jaws close at their speed limit with the body held in
        place until both jaws touch it, then the body is let go and the grasp settles under gravity for settle_s.
        The closure command then stays in force (the start row's grip value). Deterministic (a function of the state).
        Raises if the body is not held at the end. Returns the grasp: opening, force, how far the body moved."""
        w = self.w
        m, d = w.m, w.d
        if name not in w.free:
            raise KeyError(f"{name!r} is not a free body")
        qa, va = w.free[name]
        closure = float(np.clip(closure, 0.0, 1.0))
        keep_q = np.ones(m.nq, dtype=bool)
        keep_v = np.ones(m.nv, dtype=bool)
        keep_q[self.jq[s]] = keep_v[self.jv[s]] = False
        mujoco.mj_forward(m, d)
        q0, v0 = d.qpos.copy(), d.qvel.copy()
        v0[~keep_v] = 0.0
        v0[va:va + 6] = 0.0
        p_start = d.qpos[qa:qa + 3].copy()
        self.cmd[s] = closure
        i = 1 + 2 * self.sides.index(s)
        dt = m.opt.timestep
        n_close = int(math.ceil((HALF / (SPEED / 2) + 0.05) / dt))
        n_settle = int(round(settle_s / dt))
        # the rest of the world held still: put back after every step, and inert within it (a huge armature on its
        # degrees of freedom: an arm left to fall under gravity during the step would drag the body down the jaws)
        arm0 = m.dof_armature.copy()
        m.dof_armature[keep_v] = FREEZE_ARMATURE
        m.dof_armature[va:va + 6] = arm0[va:va + 6]
        try:
            self._settle(s, name, closure, keep_q, keep_v, q0, v0, i, n_close, n_settle, qa, va)
        finally:
            m.dof_armature[:] = arm0
        free = self._free
        d.qvel[self.jv[s]] = 0.0
        d.qvel[va:va + 6] = 0.0
        mujoco.mj_forward(m, d)
        self.update_held()
        if w.held[s] != name:
            raise RuntimeError(f"close_on({s!r}, {name!r}): the jaws do not hold it (opening {self.opening(s):.4f} m, "
                               f"{'both jaws touched it' if free else 'the jaws never touched it on both sides'})")
        return {"opening_m": self.opening(s), "force_n": self.force(s),
                "moved_m": float(np.linalg.norm(d.qpos[qa:qa + 3] - p_start))}

    def _settle(self, s, name, closure, keep_q, keep_v, q0, v0, i, n_close, n_settle, qa, va) -> None:
        m, d = self.w.m, self.w.d
        free, settled = False, 0
        for _ in range(n_close + n_settle):
            self.substep()
            mujoco.mj_step(m, d)
            d.qpos[keep_q] = q0[keep_q]
            d.qvel[keep_v] = v0[keep_v]
            if not free:
                d.qpos[qa:qa + 7] = q0[qa:qa + 7]
                d.qvel[va:va + 6] = 0.0
                n = d.ncon
                g = d.contact.geom[:n]
                body = m.body(name).id
                on = set()
                for a, b in zip(g[:, 0], g[:, 1]):
                    if m.geom_bodyid[b] == body:
                        on.add(int(self.jaw_code[a]))
                    elif m.geom_bodyid[a] == body:
                        on.add(int(self.jaw_code[b]))
                if {i, i + 1} <= on and abs(self.setpoint[s] - HALF * closure) < 1e-12:
                    free = True                   # both jaws on it and the servo at its command: the full clamp
                    keep_q[qa:qa + 7] = False
                    keep_v[va:va + 6] = False
            else:
                settled += 1
                if settled >= n_settle:
                    break
        self._free = free
