"""Authoring-only IK + tracking helpers for the Marvin arm rig (arm_rig.py). Not shipped to tasks.

* ``ArmIK(model, side)``: damped-least-squares IK of one 7-DoF arm for a desired pose of a body below its flange
  (default: the hand mount body, whose frame is the old wrist-stage hand frame), with joint limits (clamped to the
  actuator control ranges with a margin) and a weak null-space pull toward a rest posture.
* ``StageFK(old_model)``: maps old floating wrist-stage targets (x, y, z, rx, ry, rz in that family's stage frame,
  whatever its stage origin / serial-joint convention) to the world pose of the hand root, by forward kinematics of
  the family's *old* compiled model (so no convention has to be re-derived by hand).
* ``track(session, targets_fn, ...)``: closed-loop conversion of an existing wrist-stage controller into arm rows.
  Each control step ``targets_fn(session, k)`` returns the old command (see ``track``); the desired hand pose is
  solved by IK from the measured arm state and a joint-space integral term removes the servo's gravity sag.
  Every executed row is returned (record it; replays are open loop).

Frames: the hand root body of the old scene (``right_hand_C_MC`` / ``left_hand_C_MC``, or the Wuji wrapper of the
same name) and the rig's mount body coincide by construction (the hand sits at identity under the mount), so a pose
of the old hand root is directly a pose of ``mount`` in the arm scene.
"""

from __future__ import annotations

import numpy as np
import mujoco

import arm_rig


def quat_to_mat(q):
    m = np.zeros(9)
    mujoco.mju_quat2Mat(m, np.asarray(q, dtype=float))
    return m.reshape(3, 3)


def mat_to_quat(R):
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.asarray(R, dtype=float).reshape(9))
    return q


def rot_error(R_target, R_now):
    """World-frame rotation vector taking R_now to R_target."""
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, (R_target @ R_now.T).reshape(9))
    v = np.zeros(3)
    mujoco.mju_quat2Vel(v, q, 1.0)
    return v


class ArmIK:
    """Damped-least-squares IK for one Marvin arm on a private MjData (the session's data is never touched)."""

    def __init__(self, model, side="right", body=None, rest=None, margin=0.02):
        self.model, self.side = model, side
        self.data = mujoco.MjData(model)
        self.body = model.body(body or arm_rig._mount_names(model)[arm_rig.SIDES.index(side)]).id
        joints = [model.joint(j).id for j in arm_rig.ARM_JOINTS[side]]
        self.qadr = np.array([model.jnt_qposadr[j] for j in joints])
        self.dadr = np.array([model.jnt_dofadr[j] for j in joints])
        acts = [model.actuator(j + "_target").id for j in arm_rig.ARM_JOINTS[side]]
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

    def solve(self, pos, R=None, q0=None, qpos=None, iters=200, tol_pos=2e-4, tol_rot=2e-3, w_rot=0.35,
              damping=2e-3, step=1.0, null_gain=0.02):
        """Joint vector (7,) reaching ``pos`` (and rotation matrix ``R`` if given); returns (q, pos_err, rot_err)."""
        m, d = self.model, self.data
        if qpos is not None:
            d.qpos[:] = qpos
        q = np.clip(np.asarray(q0 if q0 is not None else d.qpos[self.qadr], dtype=float), self.lo, self.hi)
        jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        ep = er = np.inf
        for _ in range(iters):
            p, Rn = self.fk(q)
            e = pos - p
            ep = float(np.linalg.norm(e))
            if R is not None:
                w = rot_error(np.asarray(R), Rn)
                er = float(np.linalg.norm(w))
                err = np.concatenate([e, w_rot * w])
            else:
                er = 0.0
                err = e
            if ep < tol_pos and er < tol_rot:
                break
            mujoco.mj_comPos(m, d)
            mujoco.mj_jacBody(m, d, jp, jr, self.body)
            J = jp[:, self.dadr] if R is None else np.vstack([jp[:, self.dadr], w_rot * jr[:, self.dadr]])
            JJt = J @ J.T + damping * np.eye(J.shape[0])
            dq = J.T @ np.linalg.solve(JJt, err)
            # Null-space pull toward the rest posture (does not disturb the task to first order).
            N = np.eye(7) - J.T @ np.linalg.solve(JJt, J)
            dq += null_gain * N @ (self.rest - q)
            q = np.clip(q + step * dq, self.lo, self.hi)
        return q, ep, er


    def elbow_z(self, q):
        """World height of the elbow (J4 axis origin) for joint vector ``q``."""
        self.fk(q)
        side = "r" if self.side == "right" else "l"
        return float(self.data.xpos[self.model.body(f"elbow_yaw_{side}_j4_link").id][2])

    def solve_best(self, pos, R=None, seeds=None, qpos=None, n_random=24, seed=0, tol_pos=2e-3, tol_rot=2e-2,
                   **kw):
        """Multi-start IK that prefers a natural posture: among solutions within tolerance, the lowest elbow
        (elbow down/out, not the raised 'chicken wing'), then the largest joint-limit margin. Returns
        (q, pos_err, rot_err) of the chosen start (best error if none is within tolerance)."""
        rng = np.random.default_rng(seed)
        starts = list(seeds if seeds is not None else NATURAL_SEEDS[self.side])
        starts += [rng.uniform(self.lo, self.hi) for _ in range(n_random)]
        found, fallback = [], None
        kw.setdefault("iters", 400)
        for q0 in starts:
            q, ep, er = self.solve(pos, R, q0=q0, qpos=qpos, **kw)
            if fallback is None or ep + 0.1 * er < fallback[1] + 0.1 * fallback[2]:
                fallback = (q, ep, er)
            if ep < tol_pos and er < tol_rot:
                margin = float(np.min(np.minimum(q - self.lo, self.hi - q)))
                found.append((self.elbow_z(q) - 0.2 * min(margin, 0.3), q, ep, er))
        if not found:
            return fallback
        _, q, ep, er = min(found, key=lambda item: item[0])
        return q, ep, er


# Hand-picked starts per side (left = right with the signs of J1, J3, J5, J6, J7 flipped, a guess; random starts
# complete the search either way).
NATURAL_SEEDS = {
    "right": [np.array(s, dtype=float) for s in (
        [-0.6, -0.9, 0.0, -1.4, 0.0, 0.0, 0.0], [-1.0, -1.2, 0.5, -1.0, 0.5, 0.0, 0.0],
        [0.0, -1.5, -0.5, -1.8, 0.0, 0.0, 0.0], [-1.5, -0.6, 0.8, -1.2, -0.8, 0.3, 0.3],
        [-0.3, -0.5, 0.3, -1.6, 0.3, 0.0, 0.0], [-1.2, -1.0, -0.4, -1.5, 0.9, 0.2, -0.2],
        [-1.2, -1.4, 1.2, -1.6, -1.2, 0.0, 0.0], [-0.9, -1.5, 1.5, -1.9, -1.5, 0.0, 0.0])],
    "left": [np.array(s, dtype=float) for s in (
        [0.6, -0.9, 0.0, -1.4, 0.0, 0.0, 0.0], [1.0, -1.2, -0.5, -1.0, -0.5, 0.0, 0.0],
        [0.0, -1.5, 0.5, -1.8, 0.0, 0.0, 0.0], [1.5, -0.6, -0.8, -1.2, 0.8, -0.3, -0.3],
        [0.3, -0.5, -0.3, -1.6, -0.3, 0.0, 0.0], [1.2, -1.0, 0.4, -1.5, -0.9, -0.2, 0.2],
        [1.2, -1.4, -1.2, -1.6, 1.2, 0.0, 0.0], [0.9, -1.5, -1.5, -1.9, 1.5, 0.0, 0.0])],
}


class StageFK:
    """Old wrist-stage targets -> world pose of the hand root body, via the family's old compiled model."""

    def __init__(self, old_model, stage_joints=None, hand_body=None):
        self.model = old_model
        self.data = mujoco.MjData(old_model)
        if stage_joints is None:   # the first six actuators of a floating DexHand scene drive the stage
            stage_joints = [int(old_model.actuator_trnid[i, 0]) for i in range(6)]
        else:
            stage_joints = [old_model.joint(j).id if isinstance(j, str) else int(j) for j in stage_joints]
        self.qadr = np.array([old_model.jnt_qposadr[j] for j in stage_joints])
        if hand_body is None:
            for name in ("right_hand_C_MC", "left_hand_C_MC"):
                try:
                    hand_body = old_model.body(name).id
                    break
                except KeyError:
                    continue
        self.body = old_model.body(hand_body).id if isinstance(hand_body, str) else int(hand_body)

    def __call__(self, wrist6):
        self.data.qpos[self.qadr] = np.asarray(wrist6, dtype=float)[:6]
        mujoco.mj_kinematics(self.model, self.data)
        return self.data.xpos[self.body].copy(), self.data.xmat[self.body].reshape(3, 3).copy()


def _target_pose(target, fk):
    """(pos, R, fingers) from one target spec of ``track``."""
    if isinstance(target, dict) and "pos" in target:
        R = target.get("R")
        if R is None and target.get("quat") is not None:
            R = quat_to_mat(target["quat"])
        return np.asarray(target["pos"], dtype=float), R, target.get("fingers")
    if isinstance(target, dict):
        wrist, fingers = target["wrist"], target.get("fingers")
    else:
        target = np.asarray(target, dtype=float)
        wrist, fingers = target[:6], target[6:]
    if fk is None:
        raise ValueError("stage targets need stage_fk (StageFK of the old model)")
    pos, R = fk(wrist)
    return pos, R, fingers


def track(session, targets_fn, *, side="right", stage_fk=None, max_steps=None, ki=0.2, bias_limit=0.25,
          other_arm=None, other_fingers=None, ik_kwargs=None, on_step=None):
    """Drive ``session`` (an arm-rig Session: ``model``, ``data``, ``step(row)``, ``done``) with an old controller.

    One arm (``side="right"`` or ``"left"``): ``targets_fn(session, k)`` returns, for control step ``k``, one of
      * ``None``: stop;
      * a dict ``{"wrist": (6,), "fingers": (n,)}``: old stage targets (requires ``stage_fk``);
      * a dict ``{"pos": (3,), "R": (3, 3) or "quat": (4,), "fingers": (n,)}``: desired world pose of the hand root;
      * an old full row ``(6 + n,)`` (wrist targets first, then the hand's fingers; requires ``stage_fk``).
    Both arms (``side=("left", "right")``): ``targets_fn`` returns ``None`` or ``{"left": spec, "right": spec}``
    (each spec as above; ``stage_fk`` may then be ``{"left": StageFK(...), "right": StageFK(...)}``).
    ``other_arm`` / ``other_fingers``: targets held on the inactive side (one-arm mode; default: the current ctrl).
    Returns ``(rows, log)``: the executed (T, nu) float64 rows and per-step tracking errors (m, rad; the worst arm,
    with per-arm values under ``"sides"`` in two-arm mode).
    """
    m, d = session.model, session.data
    lay = arm_rig.layout(m)
    sides = (side,) if isinstance(side, str) else tuple(side)
    ik_args = {} if ik_kwargs is None else {k: v for k, v in ik_kwargs.items() if k in ("rest",)}
    iks = {s: ArmIK(m, s, **ik_args) for s in sides}
    solve_kw = {k: v for k, v in (ik_kwargs or {}).items() if k != "rest"}
    fks = stage_fk if isinstance(stage_fk, dict) else {s: stage_fk for s in sides}
    row = np.array(d.ctrl, dtype=float)
    if len(sides) == 1:
        other = "left" if side == "right" else "right"
        if other_arm is not None:
            row[lay["arm"][other]] = other_arm
        if other_fingers is not None:
            row[lay["fingers"][other]] = other_fingers
    lo, hi = m.actuator_ctrlrange.T
    bias = {s: np.zeros(7) for s in sides}
    q_cmd_prev = {s: row[lay["arm"][s]].copy() for s in sides}
    rows, log = [], []
    k = 0
    while not session.done and (max_steps is None or k < max_steps):
        target = targets_fn(session, k)
        if target is None:
            break
        specs = {sides[0]: target} if len(sides) == 1 else target
        goals = {}
        for s in sides:
            ik = iks[s]
            pos, R, fingers = _target_pose(specs[s], fks.get(s))
            q_meas = d.qpos[ik.qadr].copy()
            q_star, ep, er = ik.solve(pos, R, q0=q_cmd_prev[s] - bias[s], qpos=d.qpos, **solve_kw)
            bias[s] = np.clip(bias[s] + ki * (q_star - q_meas), -bias_limit, bias_limit)
            q_cmd = np.clip(q_star + bias[s], lo[lay["arm"][s]], hi[lay["arm"][s]])
            row[lay["arm"][s]] = q_cmd
            if fingers is not None and len(fingers):
                row[lay["fingers"][s]] = fingers
            q_cmd_prev[s] = q_cmd
            goals[s] = (pos, R, ep, er)
        row = np.clip(row, lo, hi)
        session.step(row.copy())
        rows.append(row.copy())
        per = {}
        for s in sides:
            ik = iks[s]
            pos, R, ep, er = goals[s]
            p_now, R_now = ik.fk(d.qpos[ik.qadr], qpos=d.qpos)
            per[s] = {"ik_pos_err": ep, "ik_rot_err": er, "pos_err": float(np.linalg.norm(pos - p_now)),
                      "rot_err": float(np.linalg.norm(rot_error(R, R_now))) if R is not None else 0.0}
        entry = {"k": k, **{key: max(v[key] for v in per.values()) for key in next(iter(per.values()))}}
        if len(sides) > 1:
            entry["sides"] = per
        log.append(entry)
        if on_step is not None:
            on_step(session, k, log[-1])
        k += 1
    return np.array(rows), log


def place_base_for(points, *, side="right", base_z=0.0, yaw=0.0, reach=0.62):
    """Rough helper: the stand x such that every ``points`` entry (world xyz of the palm) lies within ``reach`` m of
    the ``side`` shoulder, for a robot facing +x at ``yaw`` 0. Returns the largest feasible x (stand as far back as
    possible) or None. Confirm with ``ArmIK`` (orientation matters as much as distance)."""
    pts = np.asarray(points, dtype=float).reshape(-1, 3)
    sx, sy, sz = arm_rig.SHOULDER[side]
    best = None
    for bx in np.arange(1.0, -1.0, -0.01):
        shoulder = np.array([bx + sx, sy, base_z + sz])
        if np.all(np.linalg.norm(pts - shoulder, axis=1) <= reach):
            best = bx
    return best
