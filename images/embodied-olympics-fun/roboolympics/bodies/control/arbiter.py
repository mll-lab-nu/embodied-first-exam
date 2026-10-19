"""Joint-group arbitration for the library's legged robots (optional control library, bodies/README.md; from the G1
two-mode pilot of 2026-10-08): who controls which joint group, the low-level plan interface (rows of joint targets),
the handovers, the real limits. Works on any rig of bodies/unitree_g1 and bodies/unitree_h1 (the joint groups come
from the body: its LEGS, TORSO and ARM); the kick skill only where the body has one (the G1's kick.py).

    from bodies.control.arbiter import Arbiter
    arb = Arbiter(rig)              # rig: a floating-base legged rig (body.rig(model, prefix, hand=None); the G1's
                                    # walker="falcon" / "agile" too, see FALCON and AGILE below)
    arb.reset(d)                    # after placing the robot: legs to the walking policy, waist and arms held
    arb.walk(d, (vx, vy, wz))       # the walking policy tool (the rig's policy): a velocity command; if the legs are
                                    # not the policy's, a handover starts (stand, confirm stable, re-initialise)
    arb.plan(d, "legs", Q, QD=None, TAU=None, kp=None, kd=None)   # the low-level interface: rows of joint targets for
                                    # the next control steps, executed by the body's PD; None (accepted) or the reason
    arb.release(d, "legs")          # give a group back: legs -> the walking policy (handover), waist / arms -> hold
    arb.kick(d, **kw)               # the high-level kick skill (kick.py): only when the toolkit provides it
    arb.begin_step(d); for j in 1..10: arb.apply(d, j); mj_step   # every 10 ms control step, 1 ms physics
    arb.memory()                    # the arbiter's state for a state hash

Joint groups and owners. The joints in the body's order: legs (left 6, right 6), waist / torso (the G1's
yaw, roll, pitch; the H1-2's one torso yaw), arms (left 7, right 7): 29 on the G1, 27 on the H1-2. Each group has exactly one owner at every control step:
  walk      the walking policy (legs only; 50 Hz, its own PD gains)
  plan      the agent's plan (rows of targets, optional velocities and feed-forward torques, the agent's gains within
            [lowlevel] kp_max / kd_max); each row is held for its 10 ms step (zero-order hold, as Unitree's LowCmd:
            tau = kp (q_row - q) + kd (qd_row - qd) + tau_row, qd_row = 0 unless given); when the rows run out the
            group holds the last row (event plan_exhausted)
  skill     a platform skill (the kick; legs)
  handover  the body hands the legs back to the walking policy: targets blended to the policy's stance at the stand
            gains with gravity support (0.3 s; none after the kick skill, which ends in the stance), then the policy,
            re-initialised (memory, last action, gait phase), takes the legs (owner walk) and holds a zero command
            until the robot is confirmed stable ([lowlevel.handover]: pelvis tilt, angular rate and CoM speed under
            bounds for 0.4 s); the agent's walking command applies from then on (not confirmed within 2 s: event
            stable_timeout, the command applies anyway: the policy is the body's best balance controller)
  hold      the body holds the group's current target (waist / arms by default: the servo with gravity compensation)
Every control step the owners are logged (owner_log) and every change is an event (events): the controlling source
of every joint at every step is on record.

FALCON (the G1's optional walking policy, rig(..., walker="falcon"), bodies/unitree_g1/falcon.py): the same groups,
owners, plans and handovers. As on the rig, FALCON reads all 29 joints and this step's arm targets and waist yaw target
(held or planned) and drives the legs on its own gains ([walk.falcon]); its waist output is not used. While it has
the legs, its wrist residual (falcon.py wrist_torque: at most 0.05 rad x the wrists' kp) is added to the wrists'
torque, held or planned, as on the rig (without it the standing robot slides 6.4 m in 10 s). A handover blends to its
stance and re-initialises it (observation history, last action, heading target).

AGILE (the G1's other optional walking policy, rig(..., walker="agile"), bodies/unitree_g1/agile.py): the same code
path as FALCON (it reads all 29 joints' measured state; it ignores the arm and waist targets), on its own gains
([walk.agile]), with no residual: it has no arm output (standing 60 s with the arms held: 4.5 cm drift, almost all in
the first 5 s). A handover blends to its stance and re-initialises it (term histories, last action).

Parameters (user decisions 2026-10-08, D3 / D4; body.toml [lowlevel]): one plan per 20 ms, rows held for their 10 ms
step (zero-order hold), at most 300 rows, gain caps (estimates); the kick skill hands the legs back without a blend,
a plan after a 0.3 s blend; a handover not confirmed stable within 2 s releases the agent's walking command (logged),
it is not refused. A sport's action layer uses this for any mix of groups: e.g. table tennis on a legged robot keeps
the legs on the walking policy (walk) while the agent plans the waist and the arms (plan(d, ["waist", "arms"], Q)).

Limits kept in every mode (B0): plan rows inside the joint ranges and the joints' speed limits (row to row, and the
first row against where the group is now: the continuity check); walking commands clipped to Unitree's deployment
joystick range and rate-limited ([limits.walk]); every motor torque through bodies/servo.py's output stage: its
torque-speed curve where the body declares [motors] (Unitree's actuator model; the G1) and the URDF effort.
"""
from __future__ import annotations

import importlib
import math

import numpy as np

from .. import servo as SV

OWNERS = ("hold", "walk", "plan", "skill", "handover")
CODE = {o: i for i, o in enumerate(OWNERS)}


def minjerk(s):
    s = min(max(s, 0.0), 1.0)
    return 10 * s ** 3 - 15 * s ** 4 + 6 * s ** 5


def layout(body):
    """(JOINTS, GROUPS, module) of a legged body: legs, waist / torso, left arm, right arm in the body's order."""
    bm = importlib.import_module(type(body).__module__)
    joints = list(bm.LEGS) + list(bm.TORSO) + [f"left_{j}_joint" for j in bm.ARM] + \
        [f"right_{j}_joint" for j in bm.ARM]
    nl, nt = len(bm.LEGS), len(bm.TORSO)
    groups = {"legs": np.arange(0, nl), "waist": np.arange(nl, nl + nt), "arms": np.arange(nl + nt, len(joints))}
    return joints, groups, bm


class Arbiter:
    def __init__(self, rig):
        import mujoco as mj
        if rig.fixed_base:
            raise ValueError("the arbiter needs a floating-base legged robot (with legs)")
        self.mj, self.rig, self.m = mj, rig, rig.m
        D = rig.B.decl
        self.D = D
        JOINTS, GROUPS, self.bm = layout(rig.B)
        self.JOINTS, self.GROUPS = JOINTS, GROUPS
        self.n = n = len(JOINTS)
        m, pre = rig.m, rig.prefix
        jid = [mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, pre + j) for j in JOINTS]
        self.qadr = np.array([m.jnt_qposadr[i] for i in jid])
        self.vadr = np.array([m.jnt_dofadr[i] for i in jid])
        self.aid = np.array([mj.mj_name2id(m, mj.mjtObj.mjOBJ_ACTUATOR, f"{pre}m_{j}") for j in JOINTS])
        self.lo, self.hi = m.jnt_range[jid, 0].copy(), m.jnt_range[jid, 1].copy()
        self.tau_max = m.actuator_ctrlrange[self.aid, 1].copy()          # the URDF effort
        L = D["limits"]
        G = GROUPS
        nl = len(G["legs"])
        self.speed = np.r_[[L["leg"]["speed_rad_s"][i % 6] for i in range(nl)], L["waist"]["speed_rad_s"][:len(G["waist"])],
                           L["arm"]["speed_rad_s"], L["arm"]["speed_rad_s"]].astype(float)
        self.dt, self.substeps = rig.dt, rig.substeps
        keys = [self.bm.short(j) for j in JOINTS]
        self.act = SV.Actuators(m, self.aid, self.vadr, self.tau_max, self.dt / self.substeps,
                                envelope=SV.unitree_envelope(D, keys))
        self._env = self.act.env
        LL = D["lowlevel"]
        self.max_rows = int(LL["max_rows"])
        self.min_plan = int(LL["min_plan_interval_steps"])          # one plan per 20 ms (D3, 2026-10-08)
        self.kp_max = np.zeros(n)
        self.kd_max = np.zeros(n)
        for g, ix in G.items():
            self.kp_max[ix], self.kd_max[ix] = LL["kp_max"][g], LL["kd_max"][g]
        H = LL["handover"]
        self.H = H
        self.stand_kp = np.array(H["stand_kp"] * 2, float)
        self.stand_kd = np.array(H["stand_kd"] * 2, float)
        walker = getattr(rig, "walker", "unitree")      # the G1's optional FALCON / AGILE (falcon.py, agile.py)
        self.whole_body = walker != "unitree"           # the walker reads all the joints (and the arm / waist targets)
        self.residual = walker == "falcon"              # FALCON's wrist residual (AGILE has none)
        self.walk_kp, self.walk_kd = rig.lkp, rig.lkd       # the walking policy's PD ([walk], [walk.falcon], ...)
        self.cmd_max = np.array(L["walk"]["command_max"], float)
        self.cmd_step = np.array(L["walk"]["command_accel"], float) * self.dt
        C = D["controller"]
        self.servo_kp = np.r_[np.zeros(nl), C["kp"]["waist"], C["kp"]["arm"], C["kp"]["arm"]]
        self.servo_kd = np.r_[np.zeros(nl), C["kd"]["waist"], C["kd"]["arm"], C["kd"]["arm"]]
        # the rest pose (waist, both arms) in this order: the rig's upper-body targets at its rest u, by joint name
        up = dict(zip(rig.joints[rig.o:], rig.joint_targets(rig.rest)[rig.o:]))
        self.rest = np.r_[rig.policy.default, [up.get(j, 0.0) for j in JOINTS[nl:]]].astype(float)
        lsite = lambda nm: mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, pre + nm)
        self.foot_site = {"left": lsite("left_foot"), "right": lsite("right_foot")}
        self.foot_body = {s: int(m.site_bodyid[self.foot_site[s]]) for s in ("left", "right")}
        self.robot_bodies = self._subtree(rig.base_body)
        self.use_envelope = True         # False: only the URDF effort (for measuring what the curves change)
        self.reset_state()

    # ------------------------------------------------------------------ bookkeeping
    def _subtree(self, root):
        m = self.m
        out = {root}
        for b in range(m.nbody):
            p = b
            while p > 0 and p not in out:
                p = int(m.body_parentid[p])
            if p in out:
                out.add(b)
        return out

    def reset_state(self):
        self.owner = {"legs": "walk", "waist": "hold", "arms": "hold"}
        self.plans = {}                  # group -> dict(Q, QD, TAU, i, kp, kd)
        self.q_a = self.rest.copy()      # this step's targets: from q_a to q_b over the substeps
        self.q_b = self.rest.copy()
        self.qd_des = np.zeros(self.n)
        self.ff = np.zeros(self.n)
        self.wrist_ff = np.zeros(self.n)  # FALCON's wrist residual as torque, while it has the legs (falcon.py)
        self.kp = np.r_[self.walk_kp, self.servo_kp[12:]]
        self.kd = np.r_[self.walk_kd, self.servo_kd[12:]]
        self.bias_mask = np.r_[np.zeros(len(self.GROUPS['legs']), bool), np.ones(self.n - len(self.GROUPS['legs']), bool)]
        self.cmd = np.zeros(3)
        self.cmd_req = np.zeros(3)
        self.kicker = None
        self.k_walk = 0
        self.step_i = 0
        self.ho = None                   # the handover's state (the blend)
        self.settle = None               # after a handover: the policy holds still until the robot is stable
        self.owner_log = []              # per control step: (legs, waist, arms) owner codes
        self.events = []                 # (step, group, what, detail)
        self.last_plan_step = -10 ** 9

    def reset(self, d):
        """After the robot was placed standing (rig.place): the legs to a fresh walking policy, the rest held."""
        self.reset_state()
        self.rig.policy.reset()
        self.q_a[:] = self.q_b[:] = np.r_[self.rig.policy.default, d.qpos[self.qadr[12:]]]
        self.events.append((0, "legs", "walk_init", ""))

    def _event(self, group, what, detail=""):
        self.events.append((self.step_i, group, what, detail))

    def _set_owner(self, group, owner, why=""):
        if self.owner[group] != owner:
            self._event(group, f"{self.owner[group]}->{owner}", why)
            self.owner[group] = owner

    def q(self, d):
        return d.qpos[self.qadr].copy()

    def qd(self, d):
        return d.qvel[self.vadr].copy()

    def target(self):
        """The commanded targets at the end of the current step (what a new plan's first row must continue)."""
        return self.q_b.copy()

    # ------------------------------------------------------------------ requests
    def walk(self, d, cmd):
        """The walking policy tool: a body-frame velocity command, clipped to the real joystick range. If the legs are
        planned or held, the body starts handing them back to the policy (the command applies once it walks)."""
        c = np.asarray(cmd, float).reshape(3)
        if not np.all(np.isfinite(c)):
            return "the walking command must be 3 finite numbers"
        self.cmd_req = np.clip(c, -self.cmd_max, self.cmd_max)
        if self.owner["legs"] in ("plan", "hold"):
            self._start_handover(d, "walk requested")
        return None

    def release(self, d, group):
        if group not in self.GROUPS:
            return f"unknown group {group!r}"
        self.plans.pop(group, None)
        if group == "legs":
            if self.owner["legs"] in ("plan", "hold"):
                self.cmd_req = np.zeros(3)
                self._start_handover(d, "released")
            return None
        ix = self.GROUPS[group]
        self.kp[ix], self.kd[ix] = self.servo_kp[ix], self.servo_kd[ix]
        self.bias_mask[ix] = True
        self.ff[ix] = 0.0
        self.q_a[ix] = self.q_b[ix]
        self._set_owner(group, "hold", "released")
        return None

    def kick(self, d, **kw):
        """The high-level kick skill (kick.py) on the legs: only from walking."""
        if self.owner["legs"] != "walk" or self.settle is not None:
            return f"the legs are not walking (owner {self.owner['legs']}{', settling' if self.settle else ''})"
        try:
            Kick = importlib.import_module(self.bm.__name__.rsplit(".", 1)[0] + ".kick").Kick
        except ModuleNotFoundError:
            return f"no kick skill for {self.rig.B.name}"
        self.kicker = Kick(self.rig, d, **kw)
        self._set_owner("legs", "skill", "kick")
        return None

    def plan(self, d, groups, Q, QD=None, TAU=None, kp=None, kd=None):
        """Rows of joint targets (one per future control step, the first for the next step) for one or more groups
        (their joints side by side, in the body's order). Checked against the joint ranges, the speed limits (row to row and
        the first row against the group's current target, or its measured position when it is taken over from the
        walking policy, a skill or a handover), the torque limits (TAU) and the gain caps; accepted plans replace any
        previous plan of those groups from the next step. Returns None or the reason the plan was refused."""
        if isinstance(groups, str):
            groups = [groups]
        if self.step_i - self.last_plan_step < self.min_plan:
            return (f"one plan per {self.min_plan} control steps ({self.min_plan * self.dt * 1000:.0f} ms; "
                    "[lowlevel] min_plan_interval_steps)")
        if not groups or any(g not in self.GROUPS for g in groups) or len(set(groups)) != len(groups):
            return f"groups must be some of {list(self.GROUPS)}"
        ix = np.concatenate([self.GROUPS[g] for g in sorted(groups, key=list(self.GROUPS).index)])
        if list(groups) != sorted(groups, key=list(self.GROUPS).index):
            return "groups must be in order (legs, waist, arms)"
        Q = np.atleast_2d(np.asarray(Q, float))
        n = Q.shape[0]
        if Q.shape[1] != len(ix):
            return f"Q needs {len(ix)} columns (got {Q.shape[1]})"
        if not 1 <= n <= self.max_rows:
            return f"a plan has 1..{self.max_rows} rows"
        if not np.all(np.isfinite(Q)):
            return "Q must be finite"
        tol = 1e-9
        bad = (Q < self.lo[ix] - tol) | (Q > self.hi[ix] + tol)
        if bad.any():
            r, c = np.argwhere(bad)[0]
            return f"row {r}: {self.JOINTS[ix[c]]} = {Q[r, c]:.4f} outside its range [{self.lo[ix[c]]:.4f}, {self.hi[ix[c]]:.4f}]"
        step = self.speed[ix] * self.dt * (1 + 1e-6) + 1e-12
        if n > 1:
            dq = np.abs(np.diff(Q, axis=0))
            if (dq > step).any():
                r, c = np.argwhere(dq > step)[0]
                return (f"rows {r}->{r + 1}: {self.JOINTS[ix[c]]} moves {dq[r, c]:.4f} rad in one step (limit "
                        f"{self.speed[ix[c]]:g} rad/s x {self.dt:g} s)")
        take = [g for g in groups if self.owner[g] not in ("plan", "hold")]
        ref = self.q_b[ix].copy()
        for g in take:                                      # taken over: continue from where the joints are
            sel = np.isin(ix, self.GROUPS[g])
            ref[sel] = d.qpos[self.qadr[ix[sel]]]
        d0 = np.abs(Q[0] - ref)
        if (d0 > step).any():
            c = int(np.argmax(d0 - step))
            return (f"continuity: the first row moves {self.JOINTS[ix[c]]} {d0[c]:.4f} rad from where it is "
                    f"({ref[c]:.4f}); at most {step[c]:.4f} per step")
        if QD is not None:
            QD = np.atleast_2d(np.asarray(QD, float))
            if QD.shape != Q.shape or not np.all(np.isfinite(QD)):
                return "QD must have Q's shape and be finite"
            if (np.abs(QD) > self.speed[ix] * (1 + 1e-6)).any():
                return "QD above a joint's speed limit"
        if TAU is not None:
            TAU = np.atleast_2d(np.asarray(TAU, float))
            if TAU.shape != Q.shape or not np.all(np.isfinite(TAU)):
                return "TAU must have Q's shape and be finite"
            if (np.abs(TAU) > self.tau_max[ix] + 1e-9).any():
                return "TAU above a motor's torque limit"
        kpv = self._gains(kp, ix, self.kp_max, "kp")
        if isinstance(kpv, str):
            return kpv
        kdv = self._gains(kd, ix, self.kd_max, "kd")
        if isinstance(kdv, str):
            return kdv
        if "legs" in groups:
            self.ho = self.settle = None
        if "legs" in groups and self.owner["legs"] == "skill":
            self.kicker = None
        for g in groups:
            sel = np.isin(ix, self.GROUPS[g])
            gi = self.GROUPS[g]
            self.plans[g] = dict(Q=Q[:, sel], QD=None if QD is None else QD[:, sel],
                                 TAU=None if TAU is None else TAU[:, sel], i=0,
                                 kp=kpv[sel] if kpv is not None else (self.walk_kp if g == "legs" else self.servo_kp[gi]),
                                 kd=kdv[sel] if kdv is not None else (self.walk_kd if g == "legs" else self.servo_kd[gi]))
            if g in take:
                self.q_b[gi] = d.qpos[self.qadr[gi]]      # the interpolation starts where the joints are
            self._set_owner(g, "plan", "plan accepted")
        self.last_plan_step = self.step_i
        return None

    def _gains(self, v, ix, cap, name):
        if v is None:
            return None
        a = np.broadcast_to(np.asarray(v, float), (len(ix),)).copy() if np.ndim(v) <= 1 else None
        if a is None or not np.all(np.isfinite(a)):
            return f"{name} must be a number or one per joint"
        if (a < 0).any() or (a > cap[ix] + 1e-9).any():
            return f"{name} outside [0, {name}_max] (body.toml [lowlevel])"
        return a

    # ------------------------------------------------------------------ the handover to the walking policy
    def _start_handover(self, d, why):
        self.plans.pop("legs", None)
        self.settle = None
        self.kicker = None
        L = self.GROUPS["legs"]
        n = int(self.H["blend_steps_after_skill"] if why == "kick done" else self.H["blend_steps"])
        self.ho = dict(i=0, n=n, q_from=d.qpos[self.qadr[L]].copy(), kp_from=self.kp[L].copy(),
                       kd_from=self.kd[L].copy(), why=why)
        self._set_owner("legs", "handover", why)

    def stability(self, d):
        """(pelvis tilt rad, pelvis angular rate rad/s, CoM horizontal speed m/s)."""
        rig = self.rig
        R = d.xmat[rig.base_body].reshape(3, 3)
        tilt = math.acos(max(-1.0, min(1.0, R[2, 2])))
        om = float(np.linalg.norm(d.qvel[rig.fvadr + 3:rig.fvadr + 6]))
        self.mj.mj_subtreeVel(self.m, d)
        vcom = float(np.linalg.norm(d.subtree_linvel[rig.base_body][:2]))
        return tilt, om, vcom

    def _support_ff(self, d):
        """Leg torques that carry the weight on both feet (shared by where the CoM is between them): bias - J^T F."""
        mj, m, rig = self.mj, self.m, self.rig
        com = d.subtree_com[rig.base_body]
        W = float(m.body_subtreemass[rig.base_body]) * 9.81
        pl, pr = d.site_xpos[self.foot_site["left"]], d.site_xpos[self.foot_site["right"]]
        ax = pl[:2] - pr[:2]
        t = float(np.clip((com[:2] - pr[:2]) @ ax / max(ax @ ax, 1e-9), 0.0, 1.0))
        gen = np.zeros(m.nv)
        jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        for side, w in (("left", t), ("right", 1.0 - t)):
            if w <= 0:
                continue
            p = d.site_xpos[self.foot_site[side]]
            F = np.array([0.0, 0.0, w * W])
            r = np.array([com[0] - p[0], com[1] - p[1], 0.0])
            mj.mj_jacSite(m, d, jp, jr, self.foot_site[side])
            gen += jp.T @ F + jr.T @ np.cross(r, F)
        L = self.vadr[self.GROUPS["legs"]]
        return d.qfrc_bias[L] - gen[L]

    def _handover_step(self, d):
        """The blend: leg targets from where the legs are to the policy's stance at the stand gains with gravity
        support; then the policy, re-initialised, takes the legs (with a zero command until the robot is confirmed
        stable: _settle_check)."""
        L, H, ho = self.GROUPS["legs"], self.H, self.ho
        stand = self.rig.policy.default
        n = ho["n"]
        if ho["i"] < n:
            k = minjerk((ho["i"] + 1) / n)
            self.q_a[L] = self.q_b[L]
            self.q_b[L] = ho["q_from"] + (stand - ho["q_from"]) * k
            self.qd_des[L] = 0.0
            self.kp[L] = ho["kp_from"] + (self.stand_kp - ho["kp_from"]) * k
            self.kd[L] = ho["kd_from"] + (self.stand_kd - ho["kd_from"]) * k
            self.ff[L] = self._support_ff(d)
            ho["i"] += 1
            return
        self.ho = None
        self.rig.policy.reset()                           # re-initialised: memory, last action, gait phase
        self.k_walk = 0
        self.cmd = np.zeros(3)
        self.settle = dict(i=0, w=[])
        self._event("legs", "walk_reinit", ho["why"])
        self._set_owner("legs", "walk", "policy re-initialised")
        self.kp[L], self.kd[L], self.ff[L] = self.walk_kp, self.walk_kd, 0.0
        self._walk_targets(d)

    def _settle_check(self, d):
        """After a handover the policy holds a zero command until the robot is confirmed stable: over the last
        stable_window steps (half a gait period) the pelvis tilt, its angular rate and the CoM speed stayed under
        [lowlevel.handover]'s bounds (the policy marches in place at a zero command: the bounds sit above that sway,
        measured 0.07 rad, 1.4 rad/s, 0.13 m/s). The agent's walking command applies from then on. Not confirmed within
        timeout_steps: logged (stable_timeout) and the command let through anyway (the policy is the body's best
        balance controller)."""
        st, H = self.settle, self.H
        st["w"].append(self.stability(d))
        st["i"] += 1
        w = int(H["stable_window"])
        if len(st["w"]) >= w:
            a = np.array(st["w"][-w:]).max(0)
            if a[0] < H["stable_tilt_rad"] and a[1] < H["stable_omega_rad_s"] and a[2] < H["stable_com_speed_m_s"]:
                self._event("legs", "stable_confirmed", f"{st['i']} steps after the policy took over")
                self.settle = None
                return
        if st["i"] >= int(H["timeout_steps"]):
            self._event("legs", "stable_timeout", f"not confirmed in {st['i']} steps")
            self.settle = None

    def _walk_targets(self, d):
        rig, L = self.rig, self.GROUPS["legs"]
        if self.settle is not None:
            self._settle_check(d)
        req = np.zeros(3) if self.settle is not None else self.cmd_req
        self.cmd = self.cmd + np.clip(req - self.cmd, -self.cmd_step, self.cmd_step)
        if self.k_walk % 2 == 0:
            j, v = rig.fqadr, rig.fvadr
            if self.whole_body:                 # all 29 joints, this step's arm targets and waist yaw (falcon.py;
                                                # agile.py reads the joints only)
                G = self.GROUPS
                t = rig.policy.step(d.qpos[j + 3:j + 7], d.qvel[v + 3:v + 6], d.qpos[self.qadr], d.qvel[self.vadr],
                                    self.cmd, self.q_b[G["arms"]], self.q_b[G["waist"][0]])[:12]
            else:
                t = rig.policy.step(d.qpos[j + 3:j + 7], d.qvel[v + 3:v + 6], d.qpos[rig.lqadr], d.qvel[rig.lvadr],
                                    self.cmd, self.k_walk * self.dt)
            self.q_b[L] = t
        self.q_a[L] = self.q_b[L]
        self.qd_des[L] = 0.0
        self.k_walk += 1

    # ------------------------------------------------------------------ the control step
    def begin_step(self, d):
        # the planned and held groups' targets first (FALCON reads this step's arm and waist targets), then the legs'
        for g, ix in self.GROUPS.items():
            if self.owner[g] != "plan":
                if g != "legs":
                    self.q_a[ix] = self.q_b[ix]
                    self.qd_des[ix] = 0.0
                continue
            P = self.plans[g]
            self.kp[ix], self.kd[ix] = P["kp"], P["kd"]
            self.bias_mask[ix] = False
            if P["i"] < len(P["Q"]):
                i = P["i"]
                self.q_b[ix] = P["Q"][i]
                self.q_a[ix] = self.q_b[ix]                # zero-order hold over the step (as Unitree's LowCmd)
                self.qd_des[ix] = P["QD"][i] if P["QD"] is not None else 0.0
                self.ff[ix] = P["TAU"][i] if P["TAU"] is not None else 0.0
                P["i"] += 1
                if P["i"] == len(P["Q"]):
                    self._event(g, "plan_exhausted", f"{len(P['Q'])} rows done; holding the last")
            else:
                self.q_a[ix] = self.q_b[ix]
                self.qd_des[ix] = 0.0
        L = self.GROUPS["legs"]
        o = self.owner["legs"]
        if o == "walk":
            self.kp[L], self.kd[L], self.ff[L] = self.walk_kp, self.walk_kd, 0.0
            self._walk_targets(d)
        elif o == "skill":
            t = self.kicker.step(d)
            self.q_a[L] = self.q_b[L]
            self.q_b[L] = t
            self.q_a[L] = t                                # as G1Rig: the kick's targets held over the step
            self.qd_des[L] = 0.0
            self.kp[L], self.kd[L], self.ff[L] = self.kicker.kp, self.kicker.kd, self.kicker.ff
            if self.kicker.done:
                self._event("legs", "skill_done", "kick")
                self._start_handover(d, "kick done")
        elif o == "handover":
            self._handover_step(d)
        elif o == "hold":
            self.q_a[L] = self.q_b[L]
            self.qd_des[L] = 0.0
            self.kp[L], self.kd[L] = self.stand_kp, self.stand_kd
            self.ff[L] = self._support_ff(d)
        if self.residual:                       # FALCON's wrist residual while it has the legs, as on the rig
            A = self.GROUPS["arms"]
            self.wrist_ff[A] = self.rig.policy.wrist_torque(self.kp[A]) if self.owner["legs"] == "walk" else 0.0
        self.owner_log.append((CODE[self.owner["legs"]], CODE[self.owner["waist"]], CODE[self.owner["arms"]]))
        self.step_i += 1

    def envelope(self, tau, qd):
        """The motors' limits at joint speeds qd (bodies/servo.py Actuators.limit: the torque-speed curve where
        declared, the URDF effort) applied to tau (for analysis; apply() goes through Actuators.write)."""
        along, against = self.act.limit(qd)
        lim = np.where(np.asarray(tau) * qd > 0, along, against)
        return np.clip(tau, -lim, lim)

    def apply(self, d, j):
        q, qd = d.qpos[self.qadr], d.qvel[self.vadr]
        s = j / self.substeps
        q_des = self.q_a + (self.q_b - self.q_a) * s
        tau = self.kp * (q_des - q) + self.kd * (self.qd_des - qd) + self.ff + self.wrist_ff
        tau = tau + np.where(self.bias_mask, d.qfrc_bias[self.vadr], 0.0)
        self.act.env = self._env if self.use_envelope else None
        self.act.write(d, tau)

    # ------------------------------------------------------------------ the record
    def memory(self):
        """The arbiter's state for a state hash: the walking policy's memory, the owners, the command and the targets,
        gains and feed-forward torques in force (FALCON's wrist residual included)."""
        return np.r_[self.rig.memory(), [CODE[self.owner[g]] for g in self.GROUPS], self.cmd, self.cmd_req, self.q_a,
                     self.q_b, self.qd_des, self.kp, self.kd, self.ff, self.wrist_ff, self.step_i, self.k_walk]

    def switches(self):
        """Changes of the legs' controlling source (handover counted with the source it hands to)."""
        seq = [OWNERS[c[0]] for c in self.owner_log]
        seq = [("walk" if o == "handover" else o) for o in seq]
        return sum(1 for a, b in zip(seq, seq[1:]) if a != b)
