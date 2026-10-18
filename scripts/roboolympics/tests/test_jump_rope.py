"""jump-rope (one-minute rope skipping): the referee says no to standing still, to a jump with the rope lying behind,
to letting go of a handle, to a rope swung beside the body, to a rope that passes under one foot only, to a rope
that swings to and fro under the feet without going round (over the head), to a rope turned backwards, to a rope that
comes under the feet while they stand or while one foot is lifted (stepping over it), to a one-footed take-off, to
several hops on one turn of the rope (counted once), and to a fall; it counts a rope turned over the head and under
both airborne feet.

Two positives, both INJECTIONS, not solutions:
- the real rope: the rope is set by hand into a loop over the robot's head, turning forwards at 1.5 rev/s (its state
  only; then free, under its own physics); the robot's own arms (`stand` rows, joint targets from a kinematic table)
  keep turning it with the real grippers holding the handles; when the rope comes near the feet the robot is given a
  take-off velocity by hand (rfo.testing.kick_robot, 2 m/s up). The rope really comes down in front, passes under
  both airborne feet, and the robot lands on its feet: one counted jump (the family's count lowered to 1).
- the full count: the rope's segments are moved by hand along a loop turning forwards round the robot (its ties to the
  handles switched off, its segments placed and given their velocities at every control step), and the robot is
  kicked up 0.15 s before each pass; the rope really passes under the airborne feet and over the head 17 times, the
  robot really flies and lands: success after the 17th landing and 1 s of standing.
The negatives use the same scripted rope (or the real one) with the rule they break."""
import math

import numpy as np

import mujoco

from rfo.tasks.jump_rope import _chord_walk, _quat_from_x
from rfo.testing import act, hold, kick_robot, make, verdict

SIDES = ("left", "right")


def misses(w):
    return [e["why"] for e in w.ref.events if e["ev"] == "no count"]


# --------------------------------------------------------------------------- the scripted rope
class ScriptedRope:
    """The rope's segments moved by hand along a loop in the upright plane through the line y (sideways) at forward
    position cx and height cz, at angle theta(t) (from +x towards +z): node j sits at sideways position y0 + (y1 - y0) j
    / N and at distance rho_end + (rho - rho_end) sin(pi j / N) from the line. omega > 0 turns it forwards (the top
    moves towards +x). theta(t) may be any function (a pendulum swing)."""

    def __init__(self, w, theta, omega, y0=0.45, y1=-0.45, cx=0.0, cz=0.75, rho=0.72, rho_end=0.2, oy=0.0):
        self.w, self.theta, self.omega, self.oy = w, theta, omega, oy
        self.y0, self.y1, self.cx, self.cz, self.rho, self.rho_end = y0, y1, cx, cz, rho, rho_end
        m = w.m
        for i in range(m.neq):                       # the rope's ties to the handles and between its segments: off
            if m.equality(i).name.startswith("rope_tie"):
                w.d.eq_active[i] = 0

    def put(self, t):
        w = self.w
        N = int(w.task.p["n_seg"])
        th = self.theta(t)
        om = self.omega(t) if callable(self.omega) else self.omega
        j = np.arange(N + 1)
        ys = self.y0 + (self.y1 - self.y0) * j / N
        rr = self.rho_end + (self.rho - self.rho_end) * np.sin(np.pi * j / N)
        c = np.array([self.cx, self.oy, self.cz])
        P = c[None, :] + rr[:, None] * np.array([math.cos(th), 0.0, math.sin(th)])[None, :]
        P[:, 1] = self.oy + ys
        Rp = None
        for i in range(N):
            Q, Rp = _quat_from_x(P[i + 1] - P[i], Rp)
            r = P[i] - c
            r[1] = 0.0                                           # (the loop's axis is along y)
            w.put(f"rope{i}", P[i], Q, vel=om * np.cross([0.0, 1.0, 0.0], r), angvel=(0.0, om, 0.0))


def run_scripted(w, A, rope, seconds, kicks=(), before=None, row=None, vz=1.5):
    """Hold the robot (stand rows, grips closed) while the rope is scripted; kick it up at the given times."""
    typ, r0 = A.hold(w)
    kicks = sorted(kicks)
    n = int(round(seconds / w.CONTROL_DT))
    for k in range(n):
        if w.done:
            return
        t = w.t
        rope.put(t)
        if kicks and t >= (kicks[0][0] if isinstance(kicks[0], tuple) else kicks[0]) - 1e-9:
            k0 = kicks.pop(0)
            kick_robot(w, (0.0, 0.0, k0[1] if isinstance(k0, tuple) else vz))
        if before:
            before(t)
        if row is not None:
            w.step(A.to_raw(row[0], A.clip(row[0], row[1]), w))
        else:
            w.step(A.to_raw(typ, r0, w))


def still_rope(w, A, om, oy=0.0, yaw_rate=0.0):
    """The rope comes over the head and stops on the floor in front of the feet; the robot then jumps forwards over
    it (at sideways position oy, its heading turning at yaw_rate in the air)."""
    from rfo.testing import move_robot
    w.reset()
    if oy:
        move_robot(w, y=oy, held=True)
    th_stop = -1.309
    t_stop = (math.pi - th_stop) / om
    rope = ScriptedRope(w, lambda t: max(math.pi - om * t, th_stop), lambda t: om if t < t_stop else 0.0, oy=oy)
    typ, r0 = A.hold(w)
    kicked = False
    for k in range(int(round((t_stop + 1.2) / w.CONTROL_DT))):
        if w.done:
            break
        rope.put(w.t)
        if not kicked and w.t >= t_stop + 0.3:
            kick_robot(w, (1.4, 0.0, 1.7), (0.0, 0.0, yaw_rate))                # a jump forwards over it
            kicked = True
        w.step(A.to_raw(typ, r0, w))
    v = verdict(w)
    ms = [e for e in w.ref.events if e["ev"] == "no count"]
    assert v["metrics"]["count"] == 0 and any(e["why"].startswith("the rope was not turning") for e in ms), (v, ms)
    print("  over a still rope (y = %g, yaw rate %g):" % (oy, yaw_rate), [e.get("speeds") for e in ms])


def forward(omega, theta0=math.pi):
    return (lambda t: theta0 - omega * t), omega


def bottom_times(omega, theta0, n, t_min=0.0):
    """When a loop turning forwards from theta0 is at the bottom (theta = -pi/2 mod 2 pi)."""
    out, k = [], 0
    while len(out) < n:
        t = (theta0 + math.pi / 2 + 2 * math.pi * k) / omega
        if t > t_min:
            out.append(t)
        k += 1
    return out


# --------------------------------------------------------------------------- the real rope, turned by the arms
class GridIK:
    """(shoulder pitch, elbow) of one arm -> the jaw centre's (x, z), on a grid; inverse by the nearest grid point."""

    def __init__(self, w, side="left", sp=(-2.6, 1.2), el=(-1.0, 2.0), n=121):
        m, r = w.m, w.robot
        J = w.L.JOINTS
        self.ix = [J.index(f"{side}_{j}_joint") for j in ("shoulder_pitch", "elbow")]
        d2 = mujoco.MjData(m)
        d2.qpos[:] = w.d.qpos
        d2.qpos[r.qadr] = r.arb.target()
        site = m.site(f"{side}_jaw_centre").id
        self.S, self.E = np.linspace(*sp, n), np.linspace(*el, n)
        self.X = np.zeros((n, n, 2))
        for a, s in enumerate(self.S):
            for b, e in enumerate(self.E):
                d2.qpos[r.qadr[self.ix[0]]], d2.qpos[r.qadr[self.ix[1]]] = s, e
                mujoco.mj_kinematics(m, d2)
                self.X[a, b] = d2.site_xpos[site][[0, 2]]
        self.SS, self.EE = np.meshgrid(self.S, self.E, indexing="ij")

    def solve(self, target, prev=None):
        D = np.linalg.norm(self.X - np.asarray(target), axis=2)
        if prev is not None:
            D = D + 0.02 * (np.abs(self.SS - prev[0]) + np.abs(self.EE - prev[1]))
        a, b = np.unravel_index(np.argmin(D), D.shape)
        return np.array([self.S[a], self.E[b]])


def inject_loop(w, theta, omega, centre_xz):
    """The real rope set by hand into a loop between the two swivels, bowed out at angle theta round the line
    through centre_xz along y, turning rigidly about it at omega (> 0: forwards). Its ties stay on."""
    t, m, d = w.task, w.m, w.d
    S = d.site_xpos[m.site("swivel_left").id].copy()
    E = d.site_xpos[m.site("swivel_right").id].copy()
    N, l = int(t.p["n_seg"]), t.seg_len()
    nv = np.array([math.cos(theta), 0.0, math.sin(theta)])

    def dense(h):
        u = np.linspace(0, 1, 800)[:, None]
        return S[None] + (E - S)[None] * u + nv[None] * h * np.sin(np.pi * u) ** 0.8

    lo, hi = 0.0, 1.5
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _chord_walk(dense(mid), N, l)[1] > 0 else (lo, mid)
    pts, _ = _chord_walk(dense((lo + hi) / 2), N, l)
    pts = np.r_[pts[:-1], E[None]]
    c = np.array([centre_xz[0], 0.0, centre_xz[1]])
    Rp = None
    for i in range(N):
        Q, Rp = _quat_from_x(pts[i + 1] - pts[i], Rp)
        w.put(f"rope{i}", pts[i], Q, vel=omega * np.cross([0.0, 1.0, 0.0], pts[i] - c), angvel=(0.0, omega, 0.0))
    mujoco.mj_forward(m, d)


def turn_real(w, A, seconds, freq=1.5, lead=math.radians(45), xc=0.1, zc=0.72, R=0.08, kd=0.45, kz=0.3, vz=2.0):
    """Both arms turn the real rope (stand rows: jaw centres on circles, `lead` ahead of the rope); the rope is set
    turning at t = 1 s; the robot is kicked up when the rope comes within kd in front of the feet and below kz."""
    r, task = w.robot, w.task
    J = w.L.JOINTS
    G = GridIK(w)
    ix = {s: [J.index(f"{s}_{j}_joint") for j in ("shoulder_pitch", "elbow")] for s in SIDES}
    table, prev = [], None
    for i in range(73):
        ph = -2 * math.pi * i / 72
        prev = G.solve(np.array([xc + R * math.cos(ph), zc + R * math.sin(ph)]), prev)
        table.append(prev)
    table = np.array(table)

    def arm(ph):
        u = (-ph / (2 * math.pi)) % 1.0 * 72
        i = int(u)
        return table[i] * (1 - (u - i)) + table[i + 1] * (u - i)

    q0 = r.arb.target().copy()
    omega, theta0, t_inj, last = 2 * math.pi * freq, math.pi / 2, 1.0, -9.0
    for k in range(int(round(seconds / w.CONTROL_DT))):
        if w.done:
            return
        t = w.t
        q = q0.copy()
        if t < t_inj:
            f = 0.5 - 0.5 * math.cos(math.pi * t / t_inj)
            for s in SIDES:
                q[ix[s]] = q0[ix[s]] + f * (arm(theta0 - lead) - q0[ix[s]])
        else:
            for s in SIDES:
                q[ix[s]] = arm(theta0 - lead - omega * (t - t_inj))
        if k == int(round(t_inj / w.CONTROL_DT)):
            inject_loop(w, theta0, omega, (xc, zc))
        if t > t_inj and t - last > 0.45 and task.trackers["state"] == "under":
            (o, fwd, left), lm = task.landmarks(w)
            qr = task.rope_at(task.rope_points(w), o, fwd, left, lm["right"][1])
            if qr is not None and w.ref.touching(task._robot, w.ref.ground) and 0 < qr[0] - lm["right"][0] < kd \
                    and qr[1] < kz:
                kick_robot(w, (0.0, 0.0, vz))
                last = t
        act(w, A, "stand", np.r_[q[12:], 1.0, 1.0])


# --------------------------------------------------------------------------- the test
def main():
    import os
    fast = bool(os.environ.get("RFO_FAST"))           # (development: skip the nop and the positives)
    w, A = make("jump-rope")
    p = w.task.p
    assert p["count"] == 17 and abs(p["rope_length_m"] - 2.13) < 1e-9 and w.task.time_limit_s == 60.0
    assert all(w.held[s] == f"handle_{s}" for s in SIDES), w.held
    P = w.task.rope_points(w)
    assert P[:, 2].min() < 0.01 and P[len(P) // 2][0] < -0.2, P[len(P) // 2]           # the rope lies behind the heels
    if fast:
        om = 2 * math.pi * 1.5
        return negatives(w, A, om)
    hold(w, A)                                                                           # nop: the full minute
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [] and v["metrics"]["count"] == 0, v
    assert all(w.held[s] == f"handle_{s}" for s in SIDES), w.held                        # (the grippers hold on)
    print("  nop:", v)

    # positive 1: the real rope, turned by the arms (injected start, kicked take-off): one counted jump
    w1, A1 = make("jump-rope", count=1)
    turn_real(w1, A1, 4.0)
    v = verdict(w1)
    assert v["success"] and v["stages"] == ["jump 1", "stand"], (v, w1.ref.events[-6:])
    ev = next(e for e in w1.ref.events if e["ev"] == "stage")
    assert all(x["airborne"] and x["rope_below_m"] > 0.02 for x in ev["passes"].values()), ev
    print("  real rope, one jump:", ev["passes"], v["metrics"])
    sha = w1.state_sha()
    w1.reset()
    turn_real(w1, A1, 4.0)
    assert w1.state_sha() == sha                                                         # determinism
    w1.close()

    # positive 2: the scripted rope, 17 jumps
    om = 2 * math.pi * 1.5
    w.reset()
    rope = ScriptedRope(w, *forward(om))
    run_scripted(w, A, rope, 14.0, kicks=[t - 0.15 for t in bottom_times(om, math.pi, 17)])
    v = verdict(w)
    assert v["success"] and len(v["stages"]) == 18 and v["metrics"]["count"] == 17, (v, misses(w))
    assert misses(w) == [], misses(w)
    print("  scripted rope, 17 jumps:", v["metrics"], "at", round(w.t, 2), "s")

    negatives(w, A, om)


def negatives(w, A, om):
    w.reset()                                                                            # a jump, the rope lying behind
    hold(w, A, 0.5)
    kick_robot(w, (0.0, 0.0, 1.8))
    hold(w, A, 1.5)
    v = verdict(w)
    assert v["failed"] is None and v["metrics"]["count"] == 0 and misses(w) == [], (v, misses(w))

    w.reset()                                                                            # letting go of a handle
    hold(w, A, 0.3)
    typ, row = A.hold(w)
    row[-2] = 0.0
    for _ in range(100):
        if w.done:
            break
        w.step(A.to_raw(typ, row, w))
    assert verdict(w)["failed"] == "let go of a handle" and w.ref.events[-1]["hand"] == "left", w.ref.events[-1]

    bt = bottom_times(om, math.pi, 3)
    kicks = [t - 0.15 for t in bt]
    w.reset()                                                                            # the rope beside the body
    rope = ScriptedRope(w, *forward(om), y0=-0.30, y1=-0.80)
    run_scripted(w, A, rope, bt[-1] + 0.3, kicks=kicks)
    v = verdict(w)
    assert v["failed"] is None and v["metrics"]["count"] == 0 and misses(w) == [], (v, misses(w))

    w.reset()                                                                            # under one foot only
    rope = ScriptedRope(w, *forward(om), y0=0.08, y1=-0.45, rho_end=0.62)
    run_scripted(w, A, rope, bt[-1] + 0.3, kicks=kicks)
    v = verdict(w)
    assert v["metrics"]["count"] == 0 and "the rope did not pass under both feet" in misses(w), (v, misses(w))

    w.reset()                                                                            # to and fro, never over the head
    swing = (lambda t: -math.pi / 2 + 1.0 * math.sin(om * t)), (lambda t: -1.0 * om * math.cos(om * t))
    rope = ScriptedRope(w, *swing)
    run_scripted(w, A, rope, 2.0, kicks=[0.45, 1.5])                                     # front -> back at t = 2 pi k / om
    v = verdict(w)
    assert v["metrics"]["count"] == 0 and \
        "the rope passed under the feet without going over the head first" in misses(w), (v, misses(w))

    w.reset()                                                                            # turned backwards
    rope = ScriptedRope(w, lambda t: t * om, -om)                                        # from the front, under, up behind
    tb = [(1.5 * math.pi + 2 * math.pi * k) / om for k in range(3)]
    run_scripted(w, A, rope, tb[-1] + 0.3, kicks=[t - 0.15 for t in tb])
    v = verdict(w)
    assert v["metrics"]["count"] == 0 and "the rope passed under the feet backwards" in misses(w), (v, misses(w))

    w.reset()                                                                            # under the standing feet
    rope = ScriptedRope(w, *forward(om), rho=0.75)
    run_scripted(w, A, rope, bt[-1] + 0.3)
    v = verdict(w)                                     # (the soles' strike boxes reach the floor: the rope rides
    assert v["metrics"]["count"] == 0 and v["stages"] == [], (v, misses(w))   # over the toes, never under them)
    why = "a foot or another part of the robot was on the ground as the rope passed"

    w.reset()                                                                            # stepping over: one foot lifted
    hold(w, A, 0.2)
    q = w.robot.arb.target().copy()
    q[0], q[3] = -1.0, 1.6                                                               # the left hip and knee
    rope = ScriptedRope(w, *forward(om), rho=0.75)
    run_scripted(w, A, rope, bt[0] + 0.1, row=("joints", np.r_[q, 1.0, 1.0]))
    v = verdict(w)
    assert v["metrics"]["count"] == 0 and misses(w) and set(misses(w)) <= {why, "the rope did not pass under both feet"}, \
        (v, misses(w), w.ref.events[-3:])
    print("  stepping over:", misses(w))

    w.reset()                                                                            # a one-footed take-off
    hold(w, A, 0.2)
    rope = ScriptedRope(w, *forward(om))
    run_scripted(w, A, rope, bt[0] + 0.4, kicks=[bt[0] - 0.15], row=("joints", np.r_[q, 1.0, 1.0]))
    v = verdict(w)                                                       # (the left foot up all along, the right
    assert v["metrics"]["count"] == 0 and any(m.startswith("not a two-foot take-off") for m in misses(w)), \
        (v, misses(w))                                                   # leaves at the kick)

    w.reset()                                                                            # several hops, one turn each
    hops = sorted([(t - 0.15, 1.6) for t in bt] + [(t + 0.2, 1.0) for t in bt[:2]])     # a small hop between turns
    rope = ScriptedRope(w, *forward(om))
    run_scripted(w, A, rope, bt[-1] + 0.4, kicks=hops)
    v = verdict(w)
    assert v["metrics"]["count"] == 3 and v["stages"] == ["jump 1", "jump 2", "jump 3"], (v, misses(w))

    still_rope(w, A, om)                                                                 # over a still rope
    still_rope(w, A, om, oy=8.0, yaw_rate=-0.2)          # ... far from the origin, turning a little in the air

    w.reset()                                                                            # a fall
    rope = ScriptedRope(w, *forward(om))
    hold(w, A, 0.3)
    kick_robot(w, (0.0, 0.0, 1.5), (0.0, 6.0, 0.0))
    run_scripted(w, A, rope, 2.0)
    assert verdict(w)["failed"] == "fell", verdict(w)
    w.close()

    w, A = make("jump-rope", count=1)                                    # the last jump lands, then topples
    rope = ScriptedRope(w, *forward(om))
    t0 = bottom_times(om, math.pi, 1)[0]
    run_scripted(w, A, rope, t0 + 0.05, kicks=[t0 - 0.15])                # the jump counts (the rope is under)
    w.d.qvel[w.robot.fv + 3:w.robot.fv + 6] = (0.0, 3.0, 0.0)          # then it pitches forwards in the air
    run_scripted(w, A, rope, 3.0)
    v = verdict(w)
    assert v["stages"] == ["jump 1"] and not v["success"] and v["failed"] in ("fell", "the landing was not on the feet"), \
        (v, misses(w))
    print("  the last jump does not end standing:", v["failed"])
    w.close()
    print("PASS jump-rope")


if __name__ == "__main__":
    main()
