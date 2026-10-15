"""Authoring-only: drive a Marvin arm-rig Session with a family's old floating-wrist-stage controller.

``StageProxy`` presents the old session interface (old model, old action layout, old ``data`` layout) to an unchanged
old controller:

* ``step(old_row)``: the old stage targets of each active side are mapped to the desired world pose of the hand root
  by forward kinematics of the old (floating) model; damped-least-squares IK of the Marvin arm gives the joint targets
  (warm started, null-space pull to a rest posture, a bounded joint-space integral term removes the servo's gravity
  sag); the finger targets are copied by joint name; the inactive arm is held at its park pose. The new full row is
  sent to the arm session and recorded (``rows``), so the deliverable is plain open-loop motor targets.
* ``data``: a kinematic mirror of the physical arm-rig state in the OLD model layout (object joints copied by name,
  finger joints by name, stage joints solved so that the old hand root has the arm's actual hand pose), so that old
  controllers reading ``s.data.qpos[...]`` / ``xpos`` / ``geom_xpos`` / ``site_xpos`` keep working.
* everything else (``status()``, ``features``, ``checker``, ``done``, ...) is forwarded to the arm session.
"""

from __future__ import annotations

import numpy as np
import mujoco


def rot_error(R_target, R_now):
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, (R_target @ R_now.T).reshape(9))
    v = np.zeros(3)
    mujoco.mju_quat2Vel(v, q, 1.0)
    return v


class ArmIK:
    """DLS IK of one Marvin arm for the pose of ``body`` (private MjData)."""

    def __init__(self, model, joints, body, rest=None, margin=0.02):
        self.model = model
        self.data = mujoco.MjData(model)
        self.body = model.body(body).id
        jids = [model.joint(j).id for j in joints]
        self.qadr = np.array([model.jnt_qposadr[j] for j in jids])
        self.dadr = np.array([model.jnt_dofadr[j] for j in jids])
        acts = [model.actuator(j + "_target").id for j in joints]
        lo, hi = model.actuator_ctrlrange[acts].T
        self.lo, self.hi = lo + margin, hi - margin
        self.rest = np.asarray(rest if rest is not None else 0.5 * (lo + hi), dtype=float)

    def fk(self, q, qpos=None):
        d = self.data
        if qpos is not None:
            d.qpos[:] = qpos
        d.qpos[self.qadr] = q
        mujoco.mj_kinematics(self.model, d)
        return d.xpos[self.body].copy(), d.xmat[self.body].reshape(3, 3).copy()

    def solve(self, pos, R, q0, qpos, iters=100, tol_pos=1e-4, tol_rot=1e-3, w_rot=0.35, damping=2e-3,
              null_gain=0.02):
        m, d = self.model, self.data
        d.qpos[:] = qpos
        q = np.clip(np.asarray(q0, dtype=float), self.lo, self.hi)
        jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        ep = er = np.inf
        for _ in range(iters):
            p, Rn = self.fk(q)
            e = pos - p
            w = rot_error(R, Rn)
            ep, er = float(np.linalg.norm(e)), float(np.linalg.norm(w))
            if ep < tol_pos and er < tol_rot:
                break
            mujoco.mj_comPos(m, d)
            mujoco.mj_jacBody(m, d, jp, jr, self.body)
            J = np.vstack([jp[:, self.dadr], w_rot * jr[:, self.dadr]])
            JJt = J @ J.T + damping * np.eye(6)
            dq = J.T @ np.linalg.solve(JJt, np.concatenate([e, w_rot * w]))
            N = np.eye(len(q)) - J.T @ np.linalg.solve(JJt, J)
            dq += null_gain * N @ (self.rest - q)
            q = np.clip(q + dq, self.lo, self.hi)
        return q, ep, er


class StageFK:
    """Old stage targets (6) -> world pose of the old hand root body (old model kinematics)."""

    def __init__(self, old_model, stage_joints, root_body):
        self.model = old_model
        self.data = mujoco.MjData(old_model)
        jids = [old_model.joint(j).id for j in stage_joints]
        self.qadr = np.array([old_model.jnt_qposadr[j] for j in jids])
        self.dadr = np.array([old_model.jnt_dofadr[j] for j in jids])
        self.body = old_model.body(root_body).id

    def __call__(self, wrist6):
        self.data.qpos[self.qadr] = np.asarray(wrist6, dtype=float)[:6]
        mujoco.mj_kinematics(self.model, self.data)
        return self.data.xpos[self.body].copy(), self.data.xmat[self.body].reshape(3, 3).copy()


class OldMirror:
    """Kinematic copy of the arm-rig state in the old model layout."""

    def __init__(self, old_model, new_model, stage, rename):
        """``stage``: {side: (six old stage joint names, old root body, new root body)};
        ``rename(old_joint_name) -> new joint name`` for every other old joint (objects keep their names)."""
        self.om, self.nm = old_model, new_model
        self.data = mujoco.MjData(old_model)
        stage_names = {n for joints, _, _ in stage.values() for n in joints}
        self.pairs = []
        for j in range(old_model.njnt):
            name = old_model.joint(j).name
            if name in stage_names:
                continue
            new = new_model.joint(rename(name)).id
            nq = {0: 7, 1: 4, 2: 1, 3: 1}[int(old_model.jnt_type[j])]
            nv = {0: 6, 1: 3, 2: 1, 3: 1}[int(old_model.jnt_type[j])]
            self.pairs.append((int(old_model.jnt_qposadr[j]), int(new_model.jnt_qposadr[new]), nq,
                               int(old_model.jnt_dofadr[j]), int(new_model.jnt_dofadr[new]), nv))
        self.sides = {}
        for side, (joints, old_root, new_root) in stage.items():
            fk = StageFK(old_model, joints, old_root)
            self.sides[side] = dict(fk=fk, q=np.zeros(6), new_root=new_model.body(new_root).id)

    def stage_ik(self, side, pos, R, iters=30):
        s = self.sides[side]
        fk = s["fk"]
        q = s["q"].copy()
        m, d = fk.model, fk.data
        jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        for _ in range(iters):
            p, Rn = fk(q)
            e, w = pos - p, rot_error(R, Rn)
            if np.linalg.norm(e) < 1e-7 and np.linalg.norm(w) < 1e-6:
                break
            mujoco.mj_comPos(m, d)
            mujoco.mj_jacBody(m, d, jp, jr, fk.body)
            J = np.vstack([jp[:, fk.dadr], jr[:, fk.dadr]])
            q = q + np.linalg.lstsq(J, np.concatenate([e, w]), rcond=None)[0]
        s["q"] = q
        return q

    def sync(self, new_data):
        od = self.data
        for oq, nq_, n, ov, nv_, k in self.pairs:
            od.qpos[oq:oq + n] = new_data.qpos[nq_:nq_ + n]
            od.qvel[ov:ov + k] = new_data.qvel[nv_:nv_ + k]
        for side, s in self.sides.items():
            b = s["new_root"]
            q = self.stage_ik(side, new_data.xpos[b].copy(), new_data.xmat[b].reshape(3, 3).copy())
            od.qpos[s["fk"].qadr] = q
        od.time = new_data.time
        mujoco.mj_kinematics(self.om, od)
        mujoco.mj_comPos(self.om, od)


class StageProxy:
    """The old floating-stage session interface on top of an arm-rig session (see module docstring)."""

    def __init__(self, session, old_model, sides, rename, old_initial_row, arm_joints, park, *, active=None,
                 rest=None, ki=0.0, bias_limit=0.03, gravity_ff=True, ik_kwargs=None, extra=None):
        """``sides``: {side: dict(stage_joints=[6 old joint names], old_root=..., new_root=<new mount body>)}
        (``side`` in "left"/"right"); ``arm_joints[side]``: the 7 Marvin joint names; ``park[side]``: park pose;
        ``active``: sides driven through IK (default: all of ``sides``)."""
        self.s = session
        self.old_model = old_model
        self.model = old_model
        m, nm = old_model, session.model
        self.old_names = [m.actuator(i).name for i in range(m.nu)]
        self.actuator_names = self.old_names
        self.action_dim = m.nu
        self.ctrl_lo, self.ctrl_hi = m.actuator_ctrlrange.T.copy()
        self.active = tuple(active or sides)
        self.fk, self.ik, self.stage_idx = {}, {}, {}
        old_joint_of_act = [m.joint(int(m.actuator_trnid[i, 0])).name for i in range(m.nu)]
        for side, spec in sides.items():
            self.fk[side] = StageFK(m, spec["stage_joints"], spec["old_root"])
            self.stage_idx[side] = [old_joint_of_act.index(j) for j in spec["stage_joints"]]
            self.ik[side] = ArmIK(nm, arm_joints[side], spec["new_root"], rest=(rest or {}).get(side))
        stage_cols = {i for idx in self.stage_idx.values() for i in idx}
        new_act_of_joint = {nm.joint(int(nm.actuator_trnid[i, 0])).name: i for i in range(nm.nu)}
        self.finger_map = [(i, new_act_of_joint[rename(old_joint_of_act[i])]) for i in range(m.nu)
                           if i not in stage_cols]
        self.arm_cols = {side: [new_act_of_joint[j] for j in arm_joints[side]] for side in arm_joints}
        self.park = park
        self.mirror = OldMirror(m, nm, {k: (v["stage_joints"], v["old_root"], v["new_root"]) for k, v in sides.items()},
                                rename)
        self.ki, self.bias_limit, self.gravity_ff = ki, bias_limit, gravity_ff
        self.kp = {side: session.model.actuator_gainprm[self.arm_cols[side], 0].copy() for side in arm_joints}
        self.arm_dadr = {side: np.array([session.model.jnt_dofadr[session.model.joint(j).id] for j in arm_joints[side]])
                         for side in arm_joints}
        self.ik_kwargs = ik_kwargs or {}
        self.old_initial_row = np.asarray(old_initial_row, dtype=float)
        self.extra = extra or {}
        self.reset_tracking()

    # ------------------------------------------------------------------ tracking state
    def reset_tracking(self):
        nm, d = self.s.model, self.s.data
        self.row = np.asarray(self.s.hold_action(), dtype=float).copy()
        self.last_old = self.old_initial_row.copy()
        self.bias = {side: np.zeros(7) for side in self.active}
        self.q_prev = {side: self.row[self.arm_cols[side]].copy() for side in self.ik}
        self.rows, self.log = [], []
        self.mirror.sync(d)

    @property
    def data(self):
        return self.mirror.data

    def hold_action(self):
        return self.last_old.copy()

    def solve_row(self, old_row):
        """The new full row for ``old_row`` (IK from the measured arm state); does not step."""
        old_row = np.clip(np.asarray(old_row, dtype=float), self.ctrl_lo, self.ctrl_hi)
        d = self.s.data
        row = self.row.copy()
        info = {}
        for side in self.ik:
            cols = self.arm_cols[side]
            if side not in self.active:
                row[cols] = self.park[side]
                continue
            pos, R = self.fk[side](old_row[self.stage_idx[side]])
            ik = self.ik[side]
            q_meas = d.qpos[ik.qadr].copy()
            q_star, ep, er = ik.solve(pos, R, q0=self.q_prev[side], qpos=d.qpos, **self.ik_kwargs)
            gated = self.__dict__.get("active_ki")  # optional: integral only on these sides
            ki = self.ki if gated is None or side in gated else 0.0
            self.bias[side] = np.clip(self.bias[side] + ki * (q_star - q_meas), -self.bias_limit, self.bias_limit)
            q_cmd = q_star + self.bias[side]
            if self.gravity_ff:
                # Position-servo gravity feed-forward (q_cmd - q = tau_gravity / kp at rest); never integrates contact
                # loads, so a squeeze commanded as a position offset stays a bounded force.
                q_cmd = q_cmd + d.qfrc_bias[self.arm_dadr[side]] / self.kp[side]
            q_cmd = np.clip(q_cmd, *self.s.model.actuator_ctrlrange[cols].T)
            row[cols] = q_cmd
            self.q_prev[side] = q_star  # warm start of the next solve (the IK solution, not the offset command)
            p_now = d.xpos[ik.body]
            info[side] = (ep, er, float(np.linalg.norm(pos - p_now)),
                          float(np.linalg.norm(rot_error(R, d.xmat[ik.body].reshape(3, 3)))))
        for i_old, i_new in self.finger_map:
            row[i_new] = old_row[i_old]
        lo, hi = self.s.model.actuator_ctrlrange.T
        return np.clip(row, lo, hi), info

    def step(self, old_row):
        if self.s.done:
            return self.status()
        row, info = self.solve_row(old_row)
        self.last_old = np.clip(np.asarray(old_row, dtype=float), self.ctrl_lo, self.ctrl_hi)
        self.row = row
        out = self.s.step(row)
        self.rows.append(row.copy())
        self.log.append(info)
        self.mirror.sync(self.s.data)
        return self.status() if not isinstance(out, dict) else out

    # ------------------------------------------------------------------ forwarding
    def __getattr__(self, name):
        if name in ("s", "extra"):
            raise AttributeError(name)
        if name in self.extra:
            return self.extra[name]
        return getattr(self.s, name)
