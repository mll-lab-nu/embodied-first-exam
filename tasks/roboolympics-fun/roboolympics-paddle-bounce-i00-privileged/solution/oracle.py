"""Reference solution of paddle-bounce (privileged: the ball's state). The standing robot holds the blade level under
the drop point; from the drop on, every control step it puts the blade's centre under where the ball will come down,
moves the blade up against the falling ball (a mirror law: the blade's height mirrors a fraction of the ball's, the
fraction set from the ball's energy so that it keeps rising to `apex_m` above the blade: higher than the height the
ball was dropped from, which every bounce must reach) and tilts it a little so that
the ball comes back towards the drop point. The arm sags a little under its own weight (plain PD joints), so the
blade's measured centre and tilt are fed back slowly (an integral term) into the commanded ones."""
import mujoco
import numpy as np

GAINS = dict(blade_z_m=0.87, apex_m=0.38, mirror=0.07, mirror_gain=1.5, home_gain=0.6, tilt_max=0.12, restitution=0.90,
             reach_m=0.10, integral=0.03)
HALF_T = 0.0075                                                     # half the blade's thickness
G = 9.81


class Arm:
    """The right arm's inverse kinematics: the blade's centre at a point, its upper face along a normal."""

    def __init__(self, w):
        self.w, self.m, self.r = w, w.m, w.robot
        self.d2 = mujoco.MjData(w.m)
        self.geom = w.m.geom("paddle_blade").id
        self.mount = w.robot.mount["right"]
        self.q = np.array(w.robot.rest[12:29], float)
        self.idx = np.arange(10, 17)
        self.q_ref = None

    def solve(self, pos, normal, iters=4):
        m, r, d2 = self.m, self.r, self.d2
        lo, hi = r.lo[12:29], r.hi[12:29]
        dofs = r.vadr[12:29][self.idx]
        n = np.asarray(normal, float) / np.linalg.norm(normal)
        for _ in range(iters):
            d2.qpos[:] = self.w.d.qpos
            d2.qpos[r.qadr[12:29]] = self.q
            mujoco.mj_kinematics(m, d2)
            mujoco.mj_comPos(m, d2)
            c = d2.geom_xpos[self.geom].copy()
            up = -d2.xmat[self.mount].reshape(3, 3)[:, 0]          # the blade's upper face looks along the mount's -x
            jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
            mujoco.mj_jac(m, d2, jp, jr, c, self.mount)
            e = np.r_[np.asarray(pos, float) - c, 0.3 * np.cross(up, n)]
            J = np.vstack([jp[:, dofs], 0.3 * jr[:, dofs]])
            Ji = J.T @ np.linalg.inv(J @ J.T + 1e-4 * np.eye(6))
            dq = Ji @ e
            if self.q_ref is not None:                               # stay near the holding posture (null space)
                dq += (np.eye(7) - Ji @ J) @ (0.1 * (self.q_ref - self.q[self.idx]))
            self.q[self.idx] = np.clip(self.q[self.idx] + np.clip(dq, -0.15, 0.15), lo[self.idx] + 0.01,
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
    for i in range(1, 101):                                         # 1 s: raise the paddle
        s.step("stand", np.r_[q0 + (hold_q - q0) * i / 100, 0, 0])
    T_f = 2.0 * np.sqrt(2.0 * k["apex_m"] / G)                      # a flight's duration at the wanted apex
    bias_p, bias_n = np.zeros(3), np.zeros(2)
    want_p, want_n = np.r_[home, k["blade_z_m"]], np.zeros(2)
    while not s.done:
        t = s.state()["task"]
        if not t["dropped"]:
            s.step("stand", np.r_[hold_q, 0, 0])
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
        s.step("stand", np.r_[q, 0, 0])
