"""badminton-serve (v2, the BWF court, a free 85 g racket in the G1's right Dex1-1 gripper, the shuttle pinched in the
left one): the referee's test.

The shuttle's flight is checked first against the published numbers it is built on (terminal velocity 6.80 m/s,
Peastrel et al. 1980; the quadratic-drag speed decay of a fast level shuttle) and Law 3's speed test is reported.

The positive is REAL: the reference solution (oracles/badminton-serve/oracle.py, stand rows through the action
interface): the left gripper opens and drops the shuttle into a forehand swing of the racket that the right gripper
holds by friction; the hit, base first at 0.48 m, sends it over the net into the receiver's service court. It is run
twice (the same state hash).

A second positive by INJECTION exercises a faster swing and is the base of most negatives:
* real: the robot stands in its service court, both grippers holding by friction; the right arm swings the racket
  forward through stand rows (a shoulder-pitch swing with the elbow and the wrist set, the racket head at about
  8-9 m/s), the left gripper opens and the shuttle falls out of it;
* injected: 20 ms before the racket head gets there, the falling shuttle is put (cork towards the strings, falling at
  1.5 m/s) on the head's path, about 0.65 m in front of the robot and 0.5 m up; the hit, the shuttle's flight over the
  net and its landing in the receiver's service court are real.

Negatives, each with its exact reason: nop (time); the shuttle let fall (missed); the racket let go (dropped); the
racket thrown at the shuttle; the racket teleported onto the held shuttle; the shuttle let go and caught again;
the shuttle on the right gripper; a still racket; a feint (a forward swing that stops); the feathers first; a hit
above 1.15 m; a thrown shuttle; a hit that does not speed the shuttle up; a feet off the floor, a foot moved, a foot on
the short service line / on the centre line; a double hit; a carry; a downward flight; the served shuttle on the
robot; a flat hit into the net (real: it lands on the own side); under the net; outside the posts; a post; out of
the court (real: a swing whose face points right); the lines (in / out by 1 cm on the short service line, the centre
line, the back line, the side line); the net cord that lands in is good; the shuttle thrown over the net unstruck; the
robot in the net; the racket on the net; a fall. Determinism: the positive twice gives the same state hash."""
import importlib.util
import math
import pathlib

import mujoco
import numpy as np

from rfo.testing import act, hold, kick_robot, make, move_robot, verdict
from rfo.tasks import badminton_serve as B

FAMILY = "badminton-serve"
CFG = (0.3, 0.9, 0.0, 0.0, -0.6)        # the right arm in the swing: elbow, wrist pitch, shoulder roll, yaw, wrist yaw
OUT_CFG = (0.3, 0.9, -0.3, -0.6, 0.0)   # a swing whose face looks to the right
ORACLE = pathlib.Path(__file__).resolve().parent.parent / "oracles" / FAMILY / "oracle.py"
OUT = "the service landed outside the receiver's service court"
TOUCHED = "the shuttle touched you after you let it go"


def axis_quat(u):
    """The quaternion that turns the shuttle's +z (from the skirt to the cork) onto u."""
    u = np.asarray(u, float) / np.linalg.norm(u)
    z = np.array([0.0, 0.0, 1.0])
    c, ax = float(z @ u), np.cross(z, u)
    s = float(np.linalg.norm(ax))
    if s < 1e-9:
        return np.array([1.0, 0, 0, 0]) if c > 0 else np.array([0.0, 1, 0, 0])
    a = math.atan2(s, c)
    return np.r_[math.cos(a / 2), ax / s * math.sin(a / 2)]


def put_cork(w, c, u, vel=(0.0, 0.0, 0.0)):
    """Put the shuttle with its cork's centre at c and its axis (from the skirt to the cork) along u."""
    u = np.asarray(u, float) / np.linalg.norm(u)
    w.put("shuttle", np.asarray(c, float) - u * B.z_of(B.CORK_R), axis_quat(u), vel=vel)


class Play:
    """A scripted server: the arms' targets (stand rows; `walk` at zero command after the hit), the grippers'
    closures."""

    def __init__(self, w, A):
        self.w, self.A = w, A
        self.m, self.d = w.m, w.d
        self.hs = w.m.site("racket_head").id
        self.new()

    def new(self, cfg=CFG):
        w = self.w
        w.reset()
        self.cfg = cfg
        self.up0 = w.robot.arb.target()[12:].copy()
        self.up = self.up0.copy()
        self.gl, self.gr, self.typ = B.SHUTTLE_CLOSURE, B.RACKET_CLOSURE, "stand"
        return self

    def arm(self, sp):
        c = self.cfg
        q = self.up0.copy()
        q[10:17] = [sp, c[2], c[3], c[0], 0.0, c[1], c[4]]
        return q

    def keep(self, n=1, until=None):
        w = self.w
        for _ in range(n):
            if w.done or (until is not None and until()):
                return
            if self.typ == "stand":
                act(w, self.A, "stand", np.r_[self.up, self.gl, self.gr])
            else:
                act(w, self.A, "walk", np.r_[0.0, 0.0, 0.0, self.up, self.gl, self.gr])

    def move(self, up, n):
        u0 = self.up.copy()
        for i in range(1, n + 1):
            self.up = u0 + (up - u0) * i / n
            self.keep()

    def ready(self, back=0.6):
        """The racket back (shoulder pitch `back`), still for 0.5 s."""
        self.move(self.arm(back), 100)
        self.keep(50)
        return self

    def head(self):
        v = np.zeros(6)
        mujoco.mj_objectVelocity(self.m, self.d, mujoco.mjtObj.mjOBJ_SITE, self.hs, v, 0)
        R = self.d.xmat[self.m.body("racket").id].reshape(3, 3)
        n = R[:, 0] if R[0, 0] > 0 else -R[:, 0]                  # the strings' normal that faces forward
        return self.d.site_xpos[self.hs].copy(), v[3:].copy(), n

    def swing(self, target=0.65, lead=0.02, stop=-0.6, release=True, axis=-1, vel=(0.0, 0.0, -1.5), when=None,
              hook=None):
        """Release (8 control steps before the swing), swing towards `stop`, and put the shuttle on the head's path
        `lead` s ahead once the head is about to pass x = target (or `when(head, v)`), cork towards the strings
        (axis -1; +1: skirt first), with the velocity `vel`. hook(self) runs every control step of the swing."""
        w = self.w
        if release:
            self.gl = 0.0
            self.keep(8)
        self.up = self.arm(stop)
        placed = False
        for _ in range(60):
            self.keep()
            if w.done:
                return verdict(w)
            h, v, n = self.head()
            if not placed and (when(h, v) if when else h[0] + v[0] * lead > target):
                w.put("shuttle", h + v * lead, axis_quat(axis * n), vel=vel)
                placed = True
            if hook is not None:
                hook(self)
            if placed and w.task.trackers["phase"] not in ("hold", "free"):
                break
        return verdict(w)

    def finish(self):
        self.typ = "walk"
        self.keep(n=10 ** 6)
        return verdict(self.w)


def flight_checks(w):
    """The shuttle alone in the air (a copy of the world's data, the robot far from it)."""
    m = w.m
    d = mujoco.MjData(m)
    qa, va = w.free["shuttle"]
    qr, _ = w.free["racket"]

    def launch(pos, vel, axis):
        mujoco.mj_resetData(m, d)
        d.qpos[qr:qr + 3] = (-30.0, -15.0, 0.5)
        d.qpos[qa:qa + 3], d.qpos[qa + 3:qa + 7], d.qvel[va:va + 3] = pos, axis_quat(axis), vel
        mujoco.mj_forward(m, d)

    launch((20.0, 10.0, 200.0), (0, 0, 0), (0, 0, -1))              # the fall from rest, cork down
    for _ in range(6000):
        mujoco.mj_step(m, d)
    vt = -float(d.qvel[va + 2])
    assert abs(vt - B.V_TERMINAL) < 0.03, vt                          # Peastrel et al.: 6.80 m/s
    L = B.V_TERMINAL ** 2 / 9.81
    launch((0.0, 10.0, 100.0), (30.0, 0, 0), (1, 0, 0))               # a fast level shuttle: speed ~ v0 exp(-x / L)
    for _ in range(100):
        mujoco.mj_step(m, d)
    x, v = float(d.qpos[qa]), float(np.linalg.norm(d.qvel[va:va + 3]))
    assert abs(v - 30.0 * math.exp(-x / L)) < 0.03 * v, (x, v)
    launch((0.0, 10.0, 100.0), (15.0, 0, 0), (-0.87, 0, 0.5))        # skirt first, 30 degrees off: it turns over
    for _ in range(300):
        mujoco.mj_step(m, d)
    u = d.xmat[m.body("shuttle").id].reshape(3, 3)[:, 2]
    vel = d.qvel[va:va + 3] / np.linalg.norm(d.qvel[va:va + 3])
    assert float(u @ vel) > 0.9, (u, vel)                             # cork first along its path
    law3 = {}                                                         # Law 3: lands 530-990 mm short of the far line
    for th in (30, 45):
        good = []
        for v0 in range(40, 90, 2):
            c, s = math.cos(math.radians(th)), math.sin(math.radians(th))
            launch((0.0, 10.0, 1.0), (v0 * c, 0, v0 * s), (c, 0, s))
            while d.qpos[qa + 2] > 0.05 and d.time < 10:
                mujoco.mj_step(m, d)
            if 13.40 - 0.99 <= d.qpos[qa] <= 13.40 - 0.53:
                good.append(v0)
        law3[th] = (min(good), max(good)) if good else None
    return vt, law3


def main():
    w, A = make(FAMILY)
    task, p = w.task, w.task.p
    nx, cy = p["net_x_m"], p["centre_y_m"]
    (sx0, sx1, sy0, sy1), (tx0, tx1, ty0, ty1) = task.courts()
    assert (w.robot.name, task.robot) == ("unitree_g1", "unitree_g1") and task.rulebook and len(task.deviations) >= 5
    for text in (task.sentence, task.rules, task.venue, task.difficulty, *task.deviations):
        text.format(**p, time_limit_s=task.time_limit_s)                # every number quoted is a parameter
    m = w.m
    assert abs(m.body_mass[m.body("shuttle").id] - 0.0051) < 1e-9 and 0.00474 <= B.SHUTTLE_M <= 0.0055   # Law 2
    assert abs(m.body_mass[m.body("racket").id] - 0.085) < 1e-9                                         # Law 4
    assert B.RACKET["length_m"] <= 0.68 and 2 * (B.HEAD_B + 0.005) <= 0.23 + 1e-9
    assert 2 * B.STRINGS_A <= 0.28 and 2 * B.STRINGS_B <= 0.22
    assert abs(tx1 - tx0 - (6.70 - 1.98)) < 1e-9 and abs(ty1 - ty0 - 2.61) < 1e-9
    assert sx1 > 0.3 and sy1 > 0.3                                    # the server starts in the right service court
    vt, law3 = flight_checks(w)
    print("shuttle: terminal velocity", round(vt, 3), "m/s; Law 3 speeds (m/s) at 30 / 45 degrees:", law3)
    assert w.held == {"left": "shuttle", "right": "racket"}
    P = Play(w, A)

    # ---- nop, and the cheapest things
    hold(w, A)
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [] and w.held == {"left": "shuttle", "right": "racket"}, v
    P.new().keep(50); P.gl = 0.0; P.keep(200)                         # let fall
    assert verdict(w)["failed"] == "you missed the shuttle: it reached the floor without a hit", verdict(w)
    P.new().keep(20); P.gr = 0.0; P.keep(200)                         # the racket let go
    assert verdict(w)["failed"] == "the racket left your right hand", verdict(w)

    # ---- the real positive: the reference solution through the action interface
    spec = importlib.util.spec_from_file_location("badminton_serve_oracle", ORACLE)
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)

    class Steps:                                                      # what the oracle uses of rcb_rfo.Session
        world = w

        @property
        def done(self):
            return w.done

        def step(self, typ, row):
            w.step(A.to_raw(typ, A.clip(typ, row), w))
            return w.done
    w.reset(); oracle.solve(Steps())
    v = verdict(w)
    assert v["success"] and v["stages"] == ["release", "hit", "over the net", "in"], v
    print("real positive (oracle):", v["metrics"], "at", round(w.t, 2), "s")
    sha = w.state_sha()
    w.reset(); oracle.solve(Steps())
    assert w.state_sha() == sha

    # ---- the positive by injection (see the docstring)
    v = P.new().ready().swing()
    assert v["stages"] == ["release", "hit"] and not w.done, v
    v = P.finish()
    assert v["success"] and v["stages"] == ["release", "hit", "over the net", "in"], v
    mt = v["metrics"]
    assert tx0 <= mt["landing_x_m"] <= tx1 and ty0 <= mt["landing_y_m"] <= ty1 and mt["hit_height_m"] < 1.15, mt
    e = next(e for e in w.ref.events if e.get("stage") == "hit")
    print("positive:", mt, "head", e["head_forward_m_s"], "m/s forward at the hit")
    sha = w.state_sha()
    P.new().ready().swing(); P.finish()
    assert w.state_sha() == sha                                       # the same run again: the same state

    # ---- the release and the shuttle before the hit
    P.new().keep(20)                                                  # the racket teleported onto the held shuttle
    s = w.pos("shuttle")
    w.put("racket", s + np.array([-0.0175, 0.0, -0.50]), axis_quat((0, 0, 1)))
    P.keep(5)
    assert verdict(w)["failed"] == "the racket touched the shuttle before you let it go", verdict(w)
    P.new().keep(20); P.gl = 0.0; P.keep(5); P.gl = 1.0; P.keep(30)  # let go, caught again
    assert verdict(w)["failed"] == TOUCHED and w.ref.stages == ["release"], verdict(w)
    P.new().ready(); P.gl = 0.0; P.keep(8)                            # the shuttle on the right gripper's jaw
    P.up = P.arm(-0.6); P.keep(5)
    c, R = w.jaw_frame("right")
    put_cork(w, c + R[:, 0] * 0.040, -R[:, 0]); P.keep(3)
    assert verdict(w)["failed"] == TOUCHED and "right_hand" in w.ref.events[-1]["parts"], verdict(w)

    # ---- the hit (Law 9.1)
    P.new().keep(100); P.gl = 0.0; P.keep(8)                          # a still racket: the shuttle dropped on it
    h, _, n = P.head()
    put_cork(w, h + n * 0.03 + [0, 0, 0.03], -n, vel=(0.0, 0.0, -1.0)); P.keep(40)
    assert verdict(w)["failed"] == "the racket head was not moving forwards at the hit", verdict(w)
    P.new().ready(); P.gl = 0.0; P.keep(8)                            # a feint: forward, stop, (forward again)
    P.move(P.arm(0.2), 20); P.keep(40)
    assert verdict(w)["failed"] == "the racket's forward movement stopped before the hit", verdict(w)
    v = P.new().ready().swing(axis=+1)                                # skirt towards the strings
    assert v["failed"] == "the racket hit the feathers first, not the base of the shuttle", v
    v = P.new().ready().swing(stop=-1.4, when=lambda h, v: h[2] + v[2] * 0.02 > 1.20)     # high
    assert v["failed"] == "the shuttle was not wholly below the service height at the hit", v
    assert w.ref.events[-1]["shuttle_top_m"] >= 1.15, w.ref.events[-1]
    v = P.new().ready().swing(vel=(-6.0, 0.0, 0.0))                   # thrown at the racket
    assert v["failed"] == "the shuttle was thrown, not let go", v

    def let_go(play):                                                 # the racket let go (thrown) as the swing starts
        play.gr = 0.0
    v = P.new().ready().swing(hook=let_go)
    assert v["failed"] == "the racket left your right hand" and w.ref.stages == ["release"], v
    w2, A2 = make(FAMILY, drop_max_speed_m_s=99.0)                    # a slow racket and a fast shuttle: no speed
    P2 = Play(w2, A2); P2.ready(); P2.gl = 0.0; P2.keep(8)            # added (the hit does not count)
    for i in range(80):
        P2.up = P2.arm(0.6 - 0.6 * i / 80); P2.keep()
        h, vv, n = P2.head()
        if i == 20:
            w2.put("shuttle", h + n * 0.05, axis_quat(-n), vel=-n * 10.0)
        if w2.done or w2.task.trackers["phase"] == "served" and w2.task.trackers["sped_up"] is not None:
            break
    v = verdict(w2)
    assert v["failed"] == "the racket did not speed the shuttle up", v
    w2.close()

    # ---- the feet (Law 9.1)
    def hop(play):
        if not play.hopped:
            kick_robot(play.w, vel=(0.0, 0.0, 0.8)); play.hopped = True
    P.new().ready(); P.hopped = False
    v = P.swing(hook=hop)
    assert v["failed"].startswith("foot fault: a foot was off the floor"), v

    def slide(play):
        if not play.slid:
            move_robot(play.w, x=float(play.w.d.qpos[play.w.robot.fq]) - 0.05, held=True); play.slid = True
    P.new().ready(); P.slid = False
    v = P.swing(hook=slide)
    assert v["failed"] == "foot fault: a foot moved during the service", v
    for x, y in ((0.40, None), (None, 0.40)):                         # on the short service line / the centre line
        P.new(); move_robot(w, x=x, y=y, held=True); P.ready()
        v = P.swing()
        assert v["failed"].startswith("foot fault: a foot was off the floor or outside"), (x, y, v)

    # ---- after the hit
    def struck():
        return w.task.trackers["phase"] == "served"
    P.new().ready().swing(); P.keep(4)                                # hit twice
    P.up = P.arm(-1.2)
    for i in range(20):
        P.keep()
        h, vv, n = P.head()
        if w.done:
            break
        if i == 2:
            w.put("shuttle", h + vv * 0.01, axis_quat(-n), vel=(0, 0, 0))
    assert verdict(w)["failed"] == "the racket hit the shuttle twice", verdict(w)
    P.new().ready().swing()                                           # carried
    while not w.done:
        h, vv, n = P.head()
        w.put("shuttle", h + n * (B.CORK_R + B.STRINGS_HALF + B.z_of(B.CORK_R) - 0.001), axis_quat(-n), vel=vv)
        P.keep()
    assert verdict(w)["failed"] == "the shuttle was carried on the racket", verdict(w)
    P.new().ready().swing()                                           # downwards
    w.put("shuttle", w.pos("shuttle") + [0.05, 0, 0.05], vel=(12.0, 0.0, -2.0)); P.keep(6)
    assert verdict(w)["failed"] == "the shuttle's flight from the racket was not upwards", verdict(w)
    P.new().ready().swing(); P.keep(4)                                # back onto the robot
    put_cork(w, w.d.xpos[w.robot.torso] + [0.35, 0.0, 0.1], (-1, 0, 0), vel=(-6.0, 0.0, 0.0)); P.keep(15)
    assert verdict(w)["failed"] == "the served shuttle touched you", verdict(w)
    v = P.new().ready().swing(target=0.55); P.finish()                # real: too flat, into the net
    v = verdict(w)
    assert v["failed"] == "the service landed on your own side" and v["stages"] == ["release", "hit"], v
    P.new(cfg=OUT_CFG).ready().swing(target=0.75); v = P.finish()     # real: a face that looks right: out
    assert v["failed"] == OUT and v["metrics"]["landing_y_m"] < ty0, v
    for pos, why in (((nx - 0.3, cy + 1.0, 0.5), "the service did not pass over the net"),     # under
                     ((nx - 0.3, cy + 3.3, 1.8), "the service did not pass over the net"),     # outside the posts
                     ((nx - 0.2, cy + B.POST_Y + B.POST_R + B.NET_HALF_THICK, 1.0), "the service touched a post")):
        P.new().ready().swing(); P.keep(4)
        w.put("shuttle", pos, axis_quat((1, 0, 0)), vel=(10.0, 0.0, 0.0)); P.keep(30)
        assert verdict(w)["failed"] == why, (pos, verdict(w))
    for (bx, by), good in (((tx0 + 0.005, cy + 1.0), True), ((tx0 - 0.01, cy + 1.0), False),
                           ((nx + 4.0, ty0 + 0.005), True), ((nx + 4.0, ty0 - 0.01), False),
                           ((tx1 - 0.005, cy + 1.0), True), ((tx1 + 0.01, cy + 1.0), False),
                           ((nx + 4.0, ty1 - 0.005), True), ((nx + 4.0, ty1 + 0.01), False)):
        P.new().ready().swing(); P.keep(4)                            # the lines are in (the cork's floor contact)
        w.put("shuttle", (nx + 2.0, cy + 1.0, 3.0), axis_quat((0, 0, -1))); P.keep(1)
        w.put("shuttle", (bx, by, 0.3), axis_quat((0, 0, -1)), vel=(0.0, 0.0, -5.0)); P.keep(30)
        v = verdict(w)
        assert (v["success"] if good else v["failed"] == OUT), (bx, by, v)
    P.new().ready().swing(); P.keep(4)                                # a net cord that falls over: good
    w.put("shuttle", (nx - 0.05, cy + 1.5, B.net_top(1.5) + 0.010), axis_quat((1, 0, 0)), vel=(6.0, 0.0, 1.0))
    P.keep(300)
    v = verdict(w)
    assert v["success"] and v["metrics"].get("net_touched") == 1.0, v
    P.new().keep(20); P.gl = 0.0; P.keep(8)                           # thrown over unstruck
    w.put("shuttle", (nx - 0.5, cy + 1.0, 1.8), axis_quat((1, 0, 0)), vel=(8.0, 0.0, 1.0)); P.keep(50)
    assert verdict(w)["failed"] == "the shuttle passed the net without a hit", verdict(w)

    # ---- the robot and the racket
    P.new().keep(10); move_robot(w, x=nx - 0.10, y=cy, held=True); P.keep(30)
    assert verdict(w)["failed"] == "you touched the net or a post", verdict(w)
    P.new().keep(10); w.put("racket", (nx - 0.02, cy + 1.0, 1.0), axis_quat((0, 1, 0))); P.keep(5)
    assert verdict(w)["failed"] == "the racket touched the net or a post", verdict(w)
    P.new().move(P.arm(-1.6), 60); P.keep(30)                         # (the racket held high: a fall, not a drop)
    move_robot(w, z=0.30, held=True); P.keep(30)
    assert verdict(w)["failed"] == "fell", verdict(w)
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
