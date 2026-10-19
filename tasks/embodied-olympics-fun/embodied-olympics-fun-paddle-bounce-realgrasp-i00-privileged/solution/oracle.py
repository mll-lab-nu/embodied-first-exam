"""Reference solution of paddle-bounce-realgrasp (privileged: the ball's state, the paddle's pose). paddle-bounce's
solution, ported to a paddle held by friction in the right Dex1-1 gripper: the standing robot holds the blade level
under the drop point; from the drop on, every control step it puts the blade's centre under where the ball will come
down, moves the blade up against the falling ball (a mirror law: the blade's height mirrors a fraction of the ball's,
the fraction set from the ball's energy so that it keeps rising to `apex_m` above the blade: higher than the height the
ball was dropped from, which every bounce must reach) and tilts it a little so that the ball comes back towards the
drop point. The gripper's closure command stays 1 (120 N) throughout.

What changed from paddle-bounce's: the blade is not part of the hand, so the arm's inverse kinematics takes where the
blade is in the hand from the simulator at every step (the paddle's pose relative to the wrist mount: if it turned in
the jaws, the arm follows it) instead of from the model; the blade is 0.068 m further from the wrist (the gripper's
length). The arm sags a little under its own weight (plain PD joints), so the blade's measured centre and tilt are fed
back slowly (an integral term) into the commanded ones, as in paddle-bounce."""
import mujoco
import numpy as np

GAINS = dict(blade_z_m=0.87, apex_m=0.38, mirror=0.07, mirror_gain=1.5, home_gain=0.6, tilt_max=0.12, restitution=0.90,
             reach_m=0.10, integral=0.03)
HALF_T = 0.0075                                                     # half the blade's thickness
G = 9.81
CLOSED = 1.0                                                        # the right gripper's closure command
# the inverse kinematics' starting posture of the right arm (shoulder pitch, roll, yaw, elbow, wrist roll, pitch, yaw):
# the arm out to the side and forwards, the forearm turned so that the blade lies level in front (from rest the solver
# finds postures that sweep the paddle through the thigh on the way up, or none for some targets)
SEED = (0.22, -0.82, 0.09, 0.71, 1.13, -0.70, 1.26)
# the solver's damping (paddle-bounce's 1e-4 let the arm jump between postures near the wrist's limits when the blade
# is 0.07 m further out: the gripper; it flung the paddle) and its largest joint step per iteration (rad)
DAMP, STEP = 1e-3, 0.15
OUT = 0.6                                                           # rad: how far the arm swings out first


class Arm:
    """The right arm's inverse kinematics: the blade's centre at a point, its upper face along a normal. The blade's
    pose in the wrist mount's frame is read from the live simulator at each solve (the paddle is a free body in the
    gripper's jaws)."""

    def __init__(self, w):
        self.w, self.m, self.r = w, w.m, w.robot
        self.d2 = mujoco.MjData(w.m)
        self.geom = w.m.geom("paddle_blade").id
        self.mount = w.robot.mount["right"]
        self.q = np.array(w.robot.rest[12:29], float)
        self.idx = np.arange(10, 17)
        self.q[self.idx] = SEED
        self.q_ref = None

    def in_hand(self):
        """The blade's centre and its frame in the mount's frame, now."""
        d = self.w.d
        Rm = d.xmat[self.mount].reshape(3, 3)
        Rg = d.geom_xmat[self.geom].reshape(3, 3)
        return Rm.T @ (d.geom_xpos[self.geom] - d.xpos[self.mount]), Rm.T @ Rg

    def solve(self, pos, normal, iters=4):
        m, r, d2 = self.m, self.r, self.d2
        lo, hi = r.lo[12:29], r.hi[12:29]
        dofs = r.vadr[12:29][self.idx]
        n = np.asarray(normal, float) / np.linalg.norm(normal)
        off, Rrel = self.in_hand()
        # the upper face: the blade's normal on the side of the mount's -x (paddle-bounce's convention)
        up_local = Rrel[:, 0] * (-1.0 if Rrel[0, 0] > 0 else 1.0)
        for _ in range(iters):
            d2.qpos[:] = self.w.d.qpos
            d2.qpos[r.qadr[12:29]] = self.q
            mujoco.mj_kinematics(m, d2)
            mujoco.mj_comPos(m, d2)
            Rm = d2.xmat[self.mount].reshape(3, 3)
            c = d2.xpos[self.mount] + Rm @ off
            up = Rm @ up_local
            jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
            mujoco.mj_jac(m, d2, jp, jr, c, self.mount)
            e = np.r_[np.asarray(pos, float) - c, 0.3 * np.cross(up, n)]
            J = np.vstack([jp[:, dofs], 0.3 * jr[:, dofs]])
            Ji = J.T @ np.linalg.inv(J @ J.T + DAMP * np.eye(6))
            dq = Ji @ e
            if self.q_ref is not None:                               # stay near the holding posture (null space)
                dq += (np.eye(7) - Ji @ J) @ (0.1 * (self.q_ref - self.q[self.idx]))
            self.q[self.idx] = np.clip(self.q[self.idx] + np.clip(dq, -STEP, STEP), lo[self.idx] + 0.01,
                                       hi[self.idx] - 0.01)
        return self.q.copy()


def solve(s, **gains):
    k = {**GAINS, **gains}
    w = s.world
    p = w.task.p
    rb = 0.020                                                      # the ball's radius
    home = np.array([p["drop_x_m"], p["drop_y_m"]])
    arm = Arm(w)
    hold_q = arm.solve(np.r_[home, k["blade_z_m"]], (0, 0, 1), iters=300)
    arm.q_ref = hold_q[arm.idx].copy()
    q0 = np.array(w.robot.rest[12:29], float)
    out = q0.copy()
    out[11] -= OUT                                                  # the arm out to the side first: the paddle,
    for i in range(1, 41):                                          # hanging from the hand, clear of the thigh
        s.step("stand", np.r_[q0 + (out - q0) * i / 40, 0, CLOSED])
    for i in range(1, 81):                                          # then up to the holding posture (1.2 s in all)
        s.step("stand", np.r_[out + (hold_q - out) * i / 80, 0, CLOSED])
    T_f = 2.0 * np.sqrt(2.0 * k["apex_m"] / G)                      # a flight's duration at the wanted apex
    bias_p, bias_n = np.zeros(3), np.zeros(2)
    want_p, want_n = np.r_[home, k["blade_z_m"]], np.zeros(2)
    while not s.done:
        t = s.state()["task"]
        if not t["dropped"]:
            hold_q = arm.solve(np.r_[home, k["blade_z_m"]], (0, 0, 1))
            s.step("stand", np.r_[hold_q, 0, CLOSED])
            continue
        b, v = np.array(t["ball"]), np.array(t["ball_velocity"])
        bias_p += k["integral"] * (want_p - np.array(t["blade_centre"]))      # what the arm did not reach last step
        bias_n += k["integral"] * (want_n - np.array(t["blade_normal"])[:2])
        z0 = k["blade_z_m"]
        zc = z0 + HALF_T + rb                                       # the ball's centre when it sits on the level blade
        h = max(b[2] - zc, 0.0)
        t_imp = (v[2] + np.sqrt(v[2] ** 2 + 2 * G * h)) / G         # time to come down to the blade
        vz_imp = np.sqrt(v[2] ** 2 + 2 * G * h)
        xy_imp = b[:2] + v[:2] * t_imp
        apex = h + v[2] ** 2 / (2 * G)
        kappa = float(np.clip(k["mirror"] + k["mirror_gain"] * (k["apex_m"] - apex), 0.0, 0.5))
        want = k["home_gain"] * (home - xy_imp) / T_f               # the horizontal speed to leave the blade with
        tilt = (want - v[:2]) / ((1.0 + k["restitution"]) * max(vz_imp, 0.5))
        nt = np.linalg.norm(tilt)
        if nt > k["tilt_max"]:
            tilt *= k["tilt_max"] / nt
        off = xy_imp - home
        no = np.linalg.norm(off)
        if no > k["reach_m"]:
            off *= k["reach_m"] / no
        want_p, want_n = np.r_[home + off, z0 - kappa * h], tilt / np.sqrt(1.0 + tilt @ tilt)
        q = arm.solve(want_p + bias_p, np.r_[want_n + bias_n, 1.0])
        s.step("stand", np.r_[q, 0, CLOSED])
