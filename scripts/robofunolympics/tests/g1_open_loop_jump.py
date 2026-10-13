"""A real, open-loop jump of the Unitree G1 through the action interface, for the standing-jump referee tests: a
crouch that is balanced by kinematics (`joints` rows), then both legs extended at once (`lowcmd` rows, raised gains).
It is no solution: nothing balances the flight or the landing. It shows that the referees accept a real two-foot
push-off (the feet rise onto their toes and leave together; the body leans ahead of them)."""
import mujoco
import numpy as np

# the right arm in its highest pose (the standing reach of vertical-jump is measured in it)
ARM_UP = {"shoulder_pitch_joint": -3.089, "shoulder_roll_joint": -0.442, "shoulder_yaw_joint": -1.125,
          "elbow_joint": 1.379, "wrist_roll_joint": 0.218, "wrist_pitch_joint": 0.159, "wrist_yaw_joint": -0.223}


def upper_pose(w, arm_up: bool) -> np.ndarray:
    up = w.robot.rest[12:].copy()
    if arm_up:
        for j, v in ARM_UP.items():
            up[w.L.JOINTS.index("right_" + j) - 12] = v
    return up


def _com_ahead(w, legs, upper) -> float:
    """How far the centre of mass is ahead of the soles' centre in this pose with the soles flat (kinematics)."""
    m, r = w.m, w.robot
    d2 = mujoco.MjData(m)
    d2.qpos[:] = w.d.qpos
    h, k, a = legs
    for s in (0, 6):
        d2.qpos[r.qadr[s + 0]], d2.qpos[r.qadr[s + 3]], d2.qpos[r.qadr[s + 4]] = h, k, a
    d2.qpos[r.qadr[12:]] = upper
    th = -(h + k + a)                                # the pelvis pitch that keeps the soles flat
    d2.qpos[r.fq + 3:r.fq + 7] = [np.cos(th / 2), 0, np.sin(th / 2), 0]
    mujoco.mj_kinematics(m, d2)
    mujoco.mj_comPos(m, d2)
    feet = [g for g in range(m.ngeom) if "ankle_roll_link_sc" in m.geom(g).name]
    return float(d2.subtree_com[r.pelvis][0]) - float(np.mean(d2.geom_xpos[feet][:, 0]))


def balanced_crouch(w, knee: float, upper, bias: float):
    """(hip pitch, knee, ankle pitch) with the centre of mass `bias` m ahead of the soles' centre, the trunk as
    upright as that allows."""
    best = None
    for a in np.linspace(-0.85, 0.2, 43):
        lo, hi = -2.4, 0.3
        for _ in range(40):
            h = (lo + hi) / 2
            lo, hi = (h, hi) if _com_ahead(w, (h, knee, a), upper) - bias > 0 else (lo, h)
        if abs(_com_ahead(w, (h, knee, a), upper) - bias) < 0.004 and (best is None or abs(h + knee + a) < best[0]):
            best = (abs(h + knee + a), (float(h), knee, float(a)))
    return best[1]


def jump(w, A, act, knee=1.3, bias=0.0, lean=0.0, arm_up=False, ext=(-0.25, 0.15, 0.35), absorb=(-0.6, 1.2, -0.55)):
    """Crouch (1.5 s, held 0.5 s), extend (the hip `lean` rad further forward), legs bent again for the landing."""
    r, NJ = w.robot, w.L.NJ
    up = upper_pose(w, arm_up)
    q0 = r.arb.target().copy()

    def pose(h, k, a):
        q = q0.copy()
        for s in (0, 6):
            q[s], q[s + 3], q[s + 4] = h, k, a
        q[12:] = up
        return q

    qc = pose(*balanced_crouch(w, knee, up, bias))
    for k in range(200):
        f = 0.5 - 0.5 * np.cos(np.pi * min(1.0, k / 150))
        act(w, A, "joints", np.r_[q0 + f * (qc - q0), 0, 0])
    q = pose(ext[0] + lean, ext[1], ext[2])
    kp = np.minimum(r.kp0 * 1.4, r.kp_max)
    air0 = landed = None
    for _ in range(400):
        if w.done:
            return
        act(w, A, "lowcmd", np.r_[q, np.zeros(NJ), np.zeros(NJ), kp if landed is None else r.kp0, r.kd0, 0, 0])
        air = w.ref.airborne()
        if air and air0 is None:
            air0 = w.t
        if air0 is not None and landed is None:
            if air and w.t - air0 > 0.05:
                q = pose(*absorb)
            elif not air and w.t - air0 > 0.08:
                landed = w.t
        if landed is not None and w.t - landed > 0.3:
            break
    while not w.done:
        act(w, A, "walk", np.r_[0, 0, 0, r.rest[12:], 0, 0])
