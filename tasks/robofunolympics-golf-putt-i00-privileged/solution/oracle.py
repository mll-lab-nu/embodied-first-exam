"""Reference solution of golf-putt (v2): a real one-armed putt in `stand` mode, side-on to the line as a golfer stands.

The posture at impact comes from inverse kinematics on the simulator's model (privileged: the model and the joint
angles): the putter's face square to the line of play behind the ball, the toe 10 degrees down (the shaft then is
nearly vertical, which is where this short robot can hold an adult's putter), and the wrist's pitch joint at zero, so
that the forearm is at right angles to the line and the wrist's roll joint alone swings the club along it like a
pendulum. The sequence: the arm out to the side (the club's butt clear of the hip), to its place with the club still
out to the right, the club down to the address just behind the ball; there, three times, the arm's servos' sag under
the club is learnt (an integrator on the joint targets) and the posture is solved again for how the body really
stands; then the take-back, a pause, and one swing of the roll joint through the ball."""
import math
import mujoco
import numpy as np


class Arm:
    """Kinematics of the right arm with the putter, on a private copy of the simulator's data: damped least squares
    on the putter face's pose (centre, and the frame heel-to-toe / normal / sole normal)."""

    def __init__(self, w):
        self.m, self.r = w.m, w.robot
        self.d = mujoco.MjData(w.m)
        self.d.qpos[:] = w.d.qpos
        self.use = np.arange(w.L.NJ - 7, w.L.NJ)                # the right arm's joints
        self.adr, self.vadr = self.r.qadr[self.use], self.r.vadr[self.use]
        self.lo, self.hi = self.r.lo[self.use] + 0.03, self.r.hi[self.use] - 0.03
        self.face = w.m.geom("putter_face").id
        self.body = int(w.m.geom_bodyid[self.face])

    def fk(self, q):
        self.d.qpos[self.adr] = q
        mujoco.mj_kinematics(self.m, self.d)
        mujoco.mj_comPos(self.m, self.d)
        return self.d.geom_xpos[self.face].copy(), self.d.geom_xmat[self.face].reshape(3, 3).copy()

    def ik(self, q0, pos, Rt, iters=60, w_rot=0.2, free=(0, 1, 2, 3, 4, 6)):
        """Joint angles that put the face's centre at pos with the frame Rt (columns: heel-to-toe, normal, sole
        normal). Returns (q, position error m, orientation error rad)."""
        q = np.clip(np.asarray(q0, float), self.lo, self.hi)
        free = np.array(free)
        jp, jr = np.zeros((3, self.m.nv)), np.zeros((3, self.m.nv))
        for _ in range(iters):
            p, R = self.fk(q)
            Re = Rt @ R.T
            quat = np.zeros(4)
            mujoco.mju_mat2Quat(quat, Re.ravel())
            rv = np.zeros(3)
            mujoco.mju_quat2Vel(rv, quat, 1.0)
            e = np.r_[pos - p, w_rot * rv]
            mujoco.mj_jac(self.m, self.d, jp, jr, p, self.body)
            J = np.vstack([jp[:, self.vadr[free]], w_rot * jr[:, self.vadr[free]]])
            step = J.T @ np.linalg.solve(J @ J.T + 1e-5 * np.eye(6), e)
            n = np.max(np.abs(step))
            q[free] = np.clip(q[free] + step * min(1.0, 0.3 / max(n, 1e-9)), self.lo[free], self.hi[free])
        p, R = self.fk(q)
        quat = np.zeros(4); rv = np.zeros(3)
        mujoco.mju_mat2Quat(quat, (Rt @ R.T).ravel()); mujoco.mju_quat2Vel(rv, quat, 1.0)
        return q, float(np.linalg.norm(pos - p)), float(np.linalg.norm(rv))

    def collides(self, q) -> bool:
        """Does the arm or the putter touch the body or the green in this posture."""
        self.fk(q)
        mujoco.mj_collision(self.m, self.d)
        for c in self.d.contact[:self.d.ncon]:
            names = {self.m.geom(int(g)).name for g in c.geom}
            if c.dist < 0 and not any("ankle" in n for n in names) and "ball" not in names:
                return True
        return False

    def search(self, pos, Rt, seeds, n_random=24, seed=0, wrist_pitch=0.0):
        """Solutions with the wrist's pitch joint fixed (at 0 the forearm is at right angles to the face's normal:
        the wrist's roll joint then swings the club like a pendulum along the line of play), best margin first."""
        rng = np.random.default_rng(seed)
        cands = list(seeds) + [self.lo + rng.uniform(0, 1, 7) * (self.hi - self.lo) for _ in range(n_random)]
        out = []
        for q0 in cands:
            q0 = np.array(q0, float)
            q0[5] = wrist_pitch
            q, ep, er = self.ik(q0, pos, Rt, iters=150)
            if ep < 1e-3 and er < 5e-3 and not self.collides(q):
                margin = float(np.min(np.minimum(q - self.lo, self.hi - q)))
                out.append((margin, q))
        return sorted(out, key=lambda a: -a[0])


def face_frame(line_yaw, loft_rad, toe_up_rad=0.0):
    """The face's frame for a stroke along line_yaw with a flat sole (toe_up_rad tilts the toe up): columns
    heel-to-toe, the face's normal (tilted up by the loft), the sole's normal."""
    u = np.array([math.cos(line_yaw), math.sin(line_yaw), 0.0])
    up = np.array([0.0, 0.0, 1.0])
    h0 = np.cross(u, up)                                    # to the right of the line: the toe points away from the robot
    h = math.cos(toe_up_rad) * h0 + math.sin(toe_up_rad) * up
    n0 = np.cross(h, u)
    f = math.cos(loft_rad) * u + math.sin(loft_rad) * n0
    n = np.cross(h, f)
    return np.column_stack([h, f, n])


# omega: the swing's commanded speed at the ball (rad/s; the soft wrist follows late: the head meets the ball at about
# 1.75 m/s); face_deg: how far the face is closed about the shaft for the swing, which is what the wrist's twist under
# the head's inertia opens it by at impact. Both are calibrated on the simulator (the ball leaves within 0.2 degrees
# of the line and reaches the hole at about 1 m/s); the putt is holed with each of them, and the take-back, the hover,
# the strike point and the pauses, moved by a few per cent.
SWING = dict(omega=3.4, back_rad=0.45, through_rad=0.30, face_deg=4.35, address_rad=0.05, park_rad=1.0, hover_m=0.006,
             high_m=0.03, toe_down_deg=10.0, toe_side_m=0.025, aim_deg=0.0, clear_s=0.8, raise_s=2.5, lower_s=1.5,
             settle_s=1.0, takeback_s=1.0, pause_s=0.6, ki=0.03)
ROLL = 4                                                    # the wrist's roll joint among the arm's seven


def _smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def solve(s, **swing):
    k = {**SWING, **swing}
    w = s.world
    L = w.L
    dt = w.CONTROL_DT
    st = s.state()["task"]
    ball, hole = np.array(st["ball"]), np.array(st["hole"])
    R = float(ball[2])                                      # the ball lies on the green: its centre is one radius up
    yaw = math.atan2(hole[1] - ball[1], hole[0] - ball[0]) + math.radians(k["aim_deg"])
    u = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    toe = math.radians(k["toe_down_deg"])
    Rt = face_frame(yaw, math.radians(w.task.p["putter_loft_deg"]), -toe)
    z = 0.0125 * math.cos(toe) + 0.055 * math.sin(toe) + k["hover_m"]      # the toe's lower corner hovers over the green
    arm = Arm(w)
    rest = np.array(w.robot.rest[12:L.NJ], float)
    # the face at impact: square to the line, its front on the ball's back, the ball toe_side_m towards the toe
    impact = (np.r_[ball[:2], z] - u * (R + 0.0015) - np.r_[Rt[:2, 0], 0.0] * k["toe_side_m"])
    up = np.array([0.0, 0.0, k["high_m"]])
    sols = arm.search(impact + up, Rt, [rest[-7:], [0.3, -0.1, 0.0, 0.3, 1.2, 0.0, 0.75]])
    if not sols:
        raise RuntimeError("the putter cannot reach the ball")
    q_imp = sols[0][1]
    e = np.zeros(7)
    e[ROLL] = 1.0
    sign = 1.0 if (arm.fk(q_imp + 0.05 * e)[0] - arm.fk(q_imp)[0]) @ u > 0 else -1.0

    twist = np.zeros(7)                                     # the face closed about the shaft (the wrist's pitch joint)

    def pose(theta):                                        # the club swung by theta about the forearm (forwards > 0)
        return np.clip(q_imp + sign * theta * e + twist, arm.lo, arm.hi)

    p5 = np.zeros(7)
    p5[5] = 0.05
    n0, n1 = arm.fk(q_imp)[1][:, 1], arm.fk(q_imp + p5)[1][:, 1]
    sign_pitch = 1.0 if (n0[0] * n1[1] - n0[1] * n1[0]) > 0 else -1.0     # the pitch direction that turns the face to the left
    bias = np.zeros(7)                                      # what the arm's servos sag under the club: added to the targets
    qadr = w.robot.qadr[-7:]

    def step(q, learn=False):
        if s.done:
            return
        if learn:
            bias[:] = np.clip(bias + k["ki"] * (q - w.d.qpos[qadr]), -0.15, 0.15)
        s.step("stand", np.r_[rest[:-7], q + bias, 0.0, 0.0])

    def move(qa, qb, seconds, learn=False):
        steps = int(round(seconds / dt))
        for i in range(1, steps + 1):
            step(qa + (qb - qa) * _smooth(i / steps), learn)

    clear = rest[-7:].copy()
    clear[1] -= 0.6                                         # the arm out to the side first: the club's butt clear of the hip
    move(rest[-7:], clear, k["clear_s"])
    move(clear, pose(-k["park_rad"]), k["raise_s"])                    # the arm to its place, the club still out to the side
    move(pose(-k["park_rad"]), pose(-k["address_rad"]), k["lower_s"])  # the club down behind the ball, a little high
    address = pose(-k["address_rad"])
    for target in (impact + up, impact, impact, impact):    # the address, corrected for how the body really stands
        move(address, address, k["settle_s"], learn=True)
        arm.d.qpos[:] = w.d.qpos
        q_new, ep, er = arm.ik(q_imp, target, Rt, iters=60)
        if ep > 2e-3:
            raise RuntimeError(f"the putter cannot reach the ball (error {ep:.4f} m)")
        q_imp = q_new
        move(address, pose(-k["address_rad"]), 0.4)
        address = pose(-k["address_rad"])
    move(address, address, k["settle_s"], learn=True)
    twist[5] = sign_pitch * math.radians(k["face_deg"])       # (set for the swing: the dynamic twist of the soft wrist)
    move(address, pose(-k["back_rad"]), k["takeback_s"])
    move(pose(-k["back_rad"]), pose(-k["back_rad"]), k["pause_s"])
    # the stroke: the commanded swing angle speeds up smoothly to omega at the ball and stops smoothly after it
    om, back, thr = k["omega"], k["back_rad"], k["through_rad"]
    t_acc, t_dec = 2.0 * back / om, 2.0 * thr / om           # (a smoothstep in speed covers omega t / 2)
    t = 0.0
    while not s.done and t < t_acc + t_dec:
        t += dt
        if t <= t_acc:                                      # the integral of omega * smoothstep(t / t_acc)
            x = t / t_acc
            theta = -back + om * t_acc * (x ** 3 - x ** 4 / 2.0)
        else:
            x = min((t - t_acc) / t_dec, 1.0)
            theta = om * t_dec * (x - x ** 3 + x ** 4 / 2.0)
        step(pose(theta))
    while not s.done:
        step(pose(thr))
