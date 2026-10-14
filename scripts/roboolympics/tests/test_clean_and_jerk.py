"""clean-and-jerk: the referee says no to standing still, to a bar lifted in one hand, to a bar brought overhead without
having rested at the shoulders (a snatch, or a bar held out in front instead of racked), to letting go and to putting
the bar back down once it has passed knee height, to a finish with bent elbows, with bent knees or with the feet in a
split, to a part other than the feet on the platform (the robot bends down with the default joint gains and falls on
its hands: a real run), to the robot or the barbell off the platform; yes to a clean and jerk whose events really
happen.

The positive is an INJECTION (no controller of the H1-2 lifts a 45 kg barbell; its elbows give 18 N m where the rack
position asks 34). What the test does by hand, and what is physics:
- the robot is set into a deep hinge with its palms on the bar where it lies (`place`), and both grips are closed
  (`World.grab`: the task's own grip, a weld);
- a crane (`Assist`: a force and a levelling torque on the bar, renewed every physics step) carries the barbell's
  weight and steers its centre along a kinematic plan: off the platform, past the knees, to the shoulders, at rest
  there, up in front of the face, over the shoulders;
- a spotter (`Assist`: a horizontal force and a torque on the trunk) keeps the robot's balance; it carries no weight;
- the robot follows the same plan with `joints` rows: its legs really stand up from the squat and carry it, its hands
  stay on the bar, its arms fold and straighten;
- at the top the crane lets go: for the final two seconds the barbell's 45 kg are carried by the robot's own locked
  arms and straight legs (`lowcmd` rows at the largest gains), with only the spotter's balance.
So the lift-off in two hands, the bar at the shoulders with the legs straight, the bar overhead on locked elbows and
the motionless two seconds are real states of the simulation; how the bar got there, and the balance, are injected."""
import mujoco
import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict

MIRROR = np.array([1.0, -1.0, -1.0, 1.0, -1.0, 1.0, -1.0])        # a left arm's angles -> the right arm's
GRIP_P = np.array([0.040, 0.0, 0.045])      # the bar's axis in a wrist mount's frame: 4 cm off the palm point, palm side
GRIP_Y = 0.25                               # each hand's place on the bar, from its middle
ARM_SEED = np.array([-0.3, 0.1, 0.07, 1.0, -1.63, 0.06, -0.1])
# the left arm straight up with the hand's gripping axis along the bar and the grip GRIP_Y from the middle (solved offline)
TOP_ARM = np.array([-2.983, 0.601, -0.028, 1.551, -1.642, 0.078, 0.0])
G = 9.81
FINAL = ("both hands", "knees", "elbows", "feet on the platform", "feet in line", "motionless", "overhead")

# The plan's waypoints: (seconds, knee angle, trunk pitch, bar x, bar z, frame). The bar's axis is given in the world
# ("abs": x from where the pelvis started, z above the platform), from the shoulder joints ("sh"), or follows the arms
# as they straighten to TOP_ARM ("top").
GRIP = (0.0, 1.5, 1.20, 0.10, 0.225, "abs")                 # a deep hinge, the hands on the bar where it lies
PULL = [(1.5, 0.6, 1.30, 0.10, 0.27, "abs"),                # knees back, the bar just off the platform
        (2.5, 0.05, 0.0, 0.14, 0.82, "abs")]                # stand up: the bar in front of the thighs, above knee height
RACK = [(1.2, 0.05, 0.0, 0.10, 0.00, "sh"),                 # the bar to the shoulders
        (1.4, 0.05, 0.0, 0.10, 0.00, "sh")]                 # ... at rest: the clean's end
JERK = [(0.7, 0.05, 0.0, 0.22, 0.25, "sh"),                 # up in front of the face
        (0.7, 0.05, 0.0, 0.20, 0.52, "sh")]
TOP = [(0.8, 0.05, 0.0, None, None, "top"),                 # over the shoulders, the arms straight
       (3.0, 0.05, 0.0, None, None, "top")]                 # ... motionless until the down signal
LIFT = [GRIP] + PULL + RACK + JERK + TOP
# no clean: the bar held at rest 0.24 m in front of the shoulders (not at them), then taken overhead
NO_CLEAN = [GRIP] + PULL + [(1.2, 0.05, 0.0, 0.24, 0.0, "sh"), (1.4, 0.05, 0.0, 0.24, 0.0, "sh")] + JERK
# a finish that is no finish: overhead with bent elbows; then the arms straight but the knees bent
BAD_FINISH = [GRIP] + PULL + RACK + JERK + [(0.8, 0.05, 0.0, 0.02, 0.66, "sh"), (2.6, 0.05, 0.0, 0.02, 0.66, "sh"),
                                           (0.8, 0.30, 0.0, None, None, "top"), (2.6, 0.30, 0.0, None, None, "top")]


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


class Kin:
    """Whole-body poses of the H1-2 with both feet flat where they stand, on a scratch copy of the simulator's data."""

    def __init__(self, w):
        self.w, self.m, self.r = w, w.m, w.robot
        self.d = mujoco.MjData(self.m)
        self.d.qpos[:] = w.d.qpos
        mujoco.mj_kinematics(self.m, self.d)
        self.foot0 = self.d.site_xpos[self.r.foot_site["left"]].copy()
        self.foot0[2] -= 0.014                               # the foot hulls come to rest that much lower
        J = {j[:-6]: i for i, j in enumerate(w.L.JOINTS)}
        self.leg_idx = [(J[f"{s}_hip_pitch"], J[f"{s}_knee"], J[f"{s}_ankle_pitch"]) for s in ("left", "right")]
        self.LA, self.RA = np.arange(13, 20), np.arange(20, 27)
        self.sh = self.m.body("left_shoulder_pitch_link").id
        self.q_stand = np.r_[self.r.stance, self.r.rest[12:]]

    def set(self, q, pitch):
        m, d, r = self.m, self.d, self.r
        d.qpos[r.qadr] = q
        d.qpos[r.fq:r.fq + 3] = 0.0
        d.qpos[r.fq + 3:r.fq + 7] = [np.cos(pitch / 2), 0.0, np.sin(pitch / 2), 0.0]
        mujoco.mj_kinematics(m, d)
        d.qpos[r.fq:r.fq + 3] += self.foot0 - d.site_xpos[r.foot_site["left"]]
        d.qpos[r.fq + 1] = 0.0
        mujoco.mj_kinematics(m, d)
        mujoco.mj_comPos(m, d)

    def legs(self, q, knee, pitch, com_x=0.02):
        """Leg angles for this knee angle and trunk pitch: feet flat, the robot's centre of mass over the feet."""
        q = q.copy()

        def put(h):
            for ih, ik, ia in self.leg_idx:
                q[ih], q[ik], q[ia] = h, knee, -(pitch + h + knee)
            self.set(q, pitch)
            return float(self.d.subtree_com[self.r.pelvis][0]) - com_x

        lo, hi = -3.1, 0.6
        flo = put(lo)
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            f = put(mid)
            if (f > 0) == (flo > 0):
                lo, flo = mid, f
            else:
                hi = mid
        put(0.5 * (lo + hi))
        return q

    def shoulder(self):
        return self.d.xpos[self.sh].copy()

    def grip_point(self):
        b = self.r.mount["left"]
        R = self.d.xmat[b].reshape(3, 3)
        return self.d.xpos[b] + R @ GRIP_P, R

    def arms(self, q, pitch, target, iters=30, lam=0.02, bend=0.05):
        """Arm angles (the right arm mirrors the left) that bring the left grip point to target with the hand's
        gripping axis along the bar: damped least squares from q's arms, the elbow bending forwards only and drawn (in
        the null space) towards a bent elbow and a straight wrist. Returns (q, the position error)."""
        m, d, r = self.m, self.d, self.r
        q = q.copy()
        lo, hi = r.lo[self.LA] + 1e-3, r.hi[self.LA] - 1e-3
        hi[3] = min(hi[3], np.pi / 2)
        va = r.vadr[self.LA]
        b = r.mount["left"]
        jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        for _ in range(iters):
            self.set(q, pitch)
            p, R = self.grip_point()
            mujoco.mj_jac(m, d, jp, jr, p, b)
            e = np.r_[np.asarray(target) - p, 0.3 * np.cross(R[:, 1], [0.0, -1.0, 0.0])[[0, 2]]]
            Jm = np.vstack([jp[:, va], 0.3 * jr[:, va][[0, 2]]])
            inv = Jm.T @ np.linalg.inv(Jm @ Jm.T + lam * np.eye(5))
            pull = np.zeros(7)
            pull[3] = bend * (0.9 - q[self.LA[3]])
            pull[5:] = -bend * q[self.LA[5:]]
            dq = inv @ e + (np.eye(7) - inv @ Jm) @ pull
            q[self.LA] = np.clip(q[self.LA] + np.clip(dq, -0.2, 0.2), lo, hi)
            q[self.RA] = q[self.LA] * MIRROR
        self.set(q, pitch)
        p, _ = self.grip_point()
        return q, float(np.linalg.norm(np.asarray(target) - p))


def make_plan(w, waypoints, dt=0.01):
    """The kinematic plan, one entry per control step: (joint angles, the pelvis' pose, the bar's centre, at the top?).
    Between two waypoints the knee, the trunk and the bar's place as seen from the shoulders go smoothly from one to
    the other; the arms follow the bar. The arms must reach every place of the bar (asserted)."""
    K = Kin(w)
    H = w.task.p["platform_height_m"]
    q = K.q_stand.copy()
    q[K.LA], q[K.RA] = ARM_SEED, ARM_SEED * MIRROR

    def rel(wp, q):                                           # a waypoint's bar position as (x, z) from the shoulders
        if wp[5] == "sh":
            return np.array([wp[3], wp[4]])
        K.legs(q, wp[1], wp[2])
        s = K.shoulder()
        return np.array([wp[3] - s[0], wp[4] + H - s[2]])

    plan, prev = [], waypoints[0]
    for wp in waypoints:
        top = wp[5] == "top"
        if top:
            arm0 = q[K.LA].copy()
        else:
            a, b = rel(prev, q), rel(wp, q)
        n = max(1, int(round(wp[0] / dt)))
        for i in range(1, n + 1):
            u = smooth(i / n)
            knee, pitch = prev[1] + (wp[1] - prev[1]) * u, prev[2] + (wp[2] - prev[2]) * u
            q = K.legs(q, knee, pitch)
            if top:                                           # the arms straighten in joint space; the bar follows
                q[K.LA] = arm0 + (TOP_ARM - arm0) * u
                q[K.RA] = q[K.LA] * MIRROR
                q = K.legs(q, knee, pitch)
                g = K.grip_point()[0]
                x, z = g[0], g[2]
            else:
                s = K.shoulder()
                x, z = s[[0, 2]] + a + (b - a) * u
                q, err = K.arms(q, pitch, [x, GRIP_Y, z], iters=200 if not plan else 12)
                assert err < 0.008, (len(plan), err)
            plan.append((q.copy(), K.d.qpos[K.r.fq:K.r.fq + 7].copy(), np.array([x, 0.0, z]), top))
        prev = wp
    return plan


def place(w, q, pelvis):
    """Put the robot in a pose of the plan (an injection), at rest, its joint targets there."""
    r, d = w.robot, w.d
    d.qpos[r.fq:r.fq + 7] = pelvis
    d.qpos[r.qadr] = q
    d.qvel[r.fv:r.fv + 6] = 0.0
    d.qvel[r.vadr] = 0.0
    r.arb.q_a[:] = r.arb.q_b[:] = q
    mujoco.mj_forward(w.m, d)


class Assist:
    """The injections on the graded world, renewed at every physics step (it wraps the task's substep hook; forces
    held for a whole control step are unstable on the light links). The crane: a force on the bar that carries the
    barbell's weight and steers its centre to `bar`, and a torque that keeps it level and square. The spotter: a
    horizontal force and a torque on the trunk that keep the pelvis over `pelvis` (x, y) and the trunk at its
    attitude; it carries no weight, the legs do."""

    def __init__(self, w):
        self.w = w
        self.bar_id, self.torso = w.m.body("bar").id, w.robot.torso
        self.M = float(w.m.body_subtreemass[self.bar_id])
        self.off()
        inner = w.task.substep
        w.task.substep = lambda w_, ref: (self.apply(), inner(w_, ref))[1]

    def off(self):
        self.bar = self.pelvis = self.up_extra = self.t_release = None
        self.w.d.xfrc_applied[:] = 0.0

    def apply(self):
        m, d = self.w.m, self.w.d
        v = np.zeros(6)
        d.xfrc_applied[self.bar_id] = 0.0
        d.xfrc_applied[self.torso] = 0.0
        if self.bar is not None:
            b = self.bar_id
            mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, b, v, 0)
            f = np.clip(20000.0 * (self.bar - d.xpos[b]) - 1500.0 * v[3:], -600.0, 600.0)
            if self.up_extra is not None:                     # at the top: a bounded pull that keeps the arms taut
                f[2] = min(f[2], self.up_extra)
            f[2] += self.M * G
            axis = d.xmat[b].reshape(3, 3)[:, 1]
            d.xfrc_applied[b, :3] = f
            d.xfrc_applied[b, 3:] = 600.0 * np.cross(axis, [0.0, 1.0, 0.0]) - 40.0 * (v[:3] - (v[:3] @ axis) * axis)
        if self.pelvis is not None:
            b = self.torso
            mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, b, v, 0)
            qn, dq, rot = np.zeros(4), np.zeros(4), np.zeros(3)
            mujoco.mju_negQuat(qn, d.xquat[b])
            mujoco.mju_mulQuat(dq, np.asarray(self.pelvis[3:7], float), qn)   # the rotation still to make, in the world
            mujoco.mju_quat2Vel(rot, dq, 1.0)
            d.xfrc_applied[b, :2] = np.clip(8000.0 * (self.pelvis[:2] - d.xpos[b][:2]) - 800.0 * v[3:5], -400.0, 400.0)
            d.xfrc_applied[b, 3:] = np.clip(3000.0 * rot - 200.0 * v[:3], -400.0, 400.0)


def lift(w, A, As, plan, steps=None, grips=(1, 1), release_after=150):
    """Reset, set the robot onto the bar, close the grips and run the plan (all of it, or its first `steps`) with the
    crane and the spotter. `release_after` control steps into the plan's top part (0.8 s of straightening, then the
    hold) the crane lets go and the robot holds the barbell itself (None: the crane stays)."""
    w.reset()
    As.off()
    hold(w, A, 0.2)
    q, pel, bar, _ = plan[0]
    place(w, q, pel)
    for side, g in zip(("left", "right"), grips):
        if g:
            w.grab(side, "bar")
    As.bar, As.pelvis = bar, pel
    act(w, A, "joints", np.r_[q, grips], 50)
    follow(w, A, As, plan if steps is None else plan[:steps], grips, release_after)


def follow(w, A, As, plan, grips=(1, 1), release_after=None):
    r, n, at_top = w.robot, w.L.NJ, 0
    for q, pel, bar, top in plan:
        if w.done:
            return
        at_top = at_top + 1 if top else 0
        As.pelvis = pel
        if top and release_after is not None and at_top > release_after:
            if As.bar is not None:
                As.bar, As.t_release = None, w.t              # the crane lets go: the largest gains hold the lock-out
            act(w, A, "lowcmd", np.r_[q, np.zeros(n), np.zeros(n), r.kp_max, r.kd_max, grips])
        else:
            As.bar, As.up_extra = (bar + [0.0, 0.0, 0.03], 150.0) if top else (bar, None)
            act(w, A, "joints", np.r_[q, grips])


def unmet(w):
    ok = w.task.final_checks(w, w.ref)
    return {k for k in FINAL if not ok[k]}


def bend_down(w, A):
    """A real run through the action interface: from the standing start to the grip squat by `joints` rows (the default
    gains, no balance feedback)."""
    K = Kin(w)
    q = K.q_stand.copy()
    arm0, arm1 = q[K.LA].copy(), make_plan(w, [GRIP])[0][0][K.LA]
    for i in range(1, 301):
        u = smooth(i / 300)
        q[K.LA] = arm0 + (arm1 - arm0) * u
        q[K.RA] = q[K.LA] * MIRROR
        q = K.legs(q, 0.36 + (1.5 - 0.36) * u, 1.2 * u)
        if w.done:
            return
        act(w, A, "joints", np.r_[q, 0, 0])
    hold(w, A)


def main():
    w, A = make("clean-and-jerk")
    T, p = w.task, w.task.p
    As = Assist(w)
    K0 = Kin(w)                                               # the plans are made from the world as it is at t = 0
    plan, no_clean, bad = make_plan(w, LIFT), make_plan(w, NO_CLEAN), make_plan(w, BAD_FINISH)
    assert abs(float(w.m.body_subtreemass[w.m.body("bar").id]) - p["total_mass_kg"]) < 1e-6          # 45 kg
    assert abs(float(w.d.xpos[w.m.body("bar").id][2]) - (p["platform_height_m"] + 0.225)) < 1e-6      # on its discs
    assert abs(T.elbow_flex_deg(w, "left") - 90.0) < 0.5 and abs(T.knee_flex_deg(w, "right") - 20.6) < 0.5   # the rest pose
    hold(w, A)                                                                                # nop: the bar stays down
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [] and v["metrics"]["bar_max_height_m"] < 0.23, v

    lift(w, A, As, plan)                                                                      # positive (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["lift-off", "clean", "overhead", "down signal"], v
    assert v["metrics"]["elbow_flex_deg"] < 5 and v["metrics"]["knee_flex_deg"] < 5 and w.t < 0.5 * T.time_limit_s, (v, w.t)
    assert As.bar is None and float(np.abs(w.d.xfrc_applied[As.bar_id]).max()) == 0.0         # the crane had let go
    ev = {e.get("stage", e["ev"]): e["t"] for e in w.ref.events}
    assert ev["lift-off"] < ev["attempt"] < ev["clean"] < ev["overhead"] < ev["down signal"], ev
    held = ev["down signal"] - As.t_release                   # the whole final hold was after the crane had let go
    assert ev["overhead"] < As.t_release and p["hold_s"] <= held < p["hold_s"] + 0.3, (ev, As.t_release)
    sha = w.state_sha()
    lift(w, A, As, plan)
    assert w.state_sha() == sha                                                               # deterministic

    lift(w, A, As, plan, grips=(1, 0))                                                        # lifted in one hand
    v = verdict(w)
    assert v["failed"] == "the bar left the platform without both hands on it" and v["stages"] == [], v

    lift(w, A, As, plan, steps=400)                                                           # up to the thighs ...
    assert not w.done and T.trackers["attempt"] and verdict(w)["stages"] == ["lift-off"], verdict(w)
    hold(w, A, 0.1, grips=[1, 0])                                                             # ... and one hand opens
    assert verdict(w)["failed"] == "let go of the bar", verdict(w)

    lift(w, A, As, plan, steps=400)                                                           # up to the thighs, and
    follow(w, A, As, plan[400::-1])                                                           # back down in both hands
    v = verdict(w)
    assert v["failed"] == "the bar came down before the down signal" and v["stages"] == ["lift-off"], v

    lift(w, A, As, plan, steps=140)                                                           # off the platform but
    assert not w.done and not T.trackers["attempt"] and verdict(w)["stages"] == ["lift-off"]  # below knee height:
    follow(w, A, As, plan[140::-1])                                                           # put down again, let go:
    As.off(); hold(w, A, 0.3, grips=[0, 0])                                                   # no attempt, no fault
    assert not w.done and w.holder("bar") == [], verdict(w)

    lift(w, A, As, no_clean)                                                                  # never at the shoulders
    v = verdict(w)
    assert v["failed"] == "the bar went overhead without a clean" and v["stages"] == ["lift-off"], v

    n1 = len(bad) - 340
    lift(w, A, As, bad, steps=n1, release_after=None)                                         # overhead, elbows bent
    assert not w.done and verdict(w)["stages"] == ["lift-off", "clean"] and unmet(w) == {"elbows"}, (verdict(w), unmet(w))
    follow(w, A, As, bad[n1:])                                                                # arms straight, knees bent
    assert not w.done and verdict(w)["stages"] == ["lift-off", "clean", "overhead"] and unmet(w) == {"knees"}, (verdict(w), unmet(w))
    r, d = w.robot, w.d                                                                       # knees straight, but the
    q = bad[-1][0].copy()                                                                     # feet in a split (set by
    for (ih, ik, ia), a in zip(K0.leg_idx, (-0.12, 0.12)):                                    # hand: an injection)
        q[ih], q[ik], q[ia] = a, 0.05, -a - 0.05
    K0.set(q, 0.0)
    dz = float(K0.d.qpos[r.fq + 2] - bad[-1][1][2])
    d.qpos[r.fq + 2] += dz
    d.qpos[r.qadr[:12]] = q[:12]
    r.arb.q_a[:12] = r.arb.q_b[:12] = q[:12]
    pel = np.r_[d.qpos[r.fq:r.fq + 2], bad[-1][1][2:]]
    follow(w, A, As, [(q, pel, bad[-1][2] + [0.0, 0.0, dz], True)] * 260)
    assert not w.done and unmet(w) == {"feet in line"}, (verdict(w), unmet(w))
    while not w.done:
        follow(w, A, As, [(q, pel, bad[-1][2] + [0.0, 0.0, dz], True)])
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == ["lift-off", "clean", "overhead"], v      # no down signal

    w.reset(); As.off(); bend_down(w, A)                                                      # a real run: bending down
    v = verdict(w)                                                                            # on the default gains
    assert v["failed"] == "touched the platform with a part other than the feet" and v["stages"] == [], v
    w.reset(); hold(w, A, 0.2)                                                                # set down beyond the edge
    move_robot(w, x=p["platform_size_m"] / 2 + 0.4); hold(w, A, 1.0)
    assert verdict(w)["failed"] == "left the platform", verdict(w)
    w.reset(); hold(w, A, 0.2)                                                                # the barbell off the edge
    w.put("bar", [p["platform_size_m"] / 2 + 0.4, 0.0, T.rest_z]); hold(w, A, 1.0)
    assert verdict(w)["failed"] == "the barbell left the platform", verdict(w)
    print("PASS clean-and-jerk")


if __name__ == "__main__":
    main()
