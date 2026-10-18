"""dunk-realgrasp (v2, FIBA, the Unitree H1-2, no grip): the referee says yes to the ball pressed between the two
bare palms going down through the official ring (3.05 m) with both hands on it at the entry, then a landing held on
the feet; no to a ball let go above the ring (a drop), to a ball let go over the rim to roll in, to a one-hand entry,
to a ball that comes up through the ring from below, to a ball that misses after it was let go inside the ring, to a
ball on the floor before the dunk, to travelling, to hanging on the ring, to a fall; and nop fails.

The hold is real in every run: no grip exists in this task; the ball is held only by the arms pressing the palms
against it (contact and friction), and the test checks that it stays held: under the start command for the whole
episode (nop), while the arms raise it overhead (`stand` mode, a squeeze path solved on a scratch copy of the model),
and through the jump's accelerations.

The positive is an INJECTION, not a solution; none exists: with both arms up and the ball pressed between the palms
its centre is about 2.2 m above the floor, and the robot has no jump. The robot really raises the ball overhead
(`stand` mode). Then a "ghost" jump: for 0.35 s every body of the robot (not the ball) gets an upward external force
of its weight plus 1.0 g (an acceleration field: the ball is carried only by the palms' friction, about 2 g on it),
which leaves the robot flying up at 3.45 m/s. At the apex robot and ball are teleported together over the ring (no
relative motion: the hold is untouched). From there physics: the body falls, the squeezed ball goes down through the
real ring with both palms on it (the arms pass inside the ring without touching it), the arms open once it is
through. The landing is a second injection (0.3 m above its standing height the falling robot is put down upright, legs
at the stance, at rest; without it the open-loop stance does not survive a 1.2 m drop: that fall is a negative below),
and the robot really stands for the second the referee asks.

Also printed (measurements for the task's notes): the start squeeze's palm forces and the extra load it holds."""
import mujoco
import numpy as np

from rfo.testing import act, hold, kick_robot, make, move_robot, verdict
import rfo.tasks.dunk_realgrasp as M

EARLY = "the ball left the hands before the dunk"
BELOW = "the ball came up through the ring from below"
NO_BOTH = "the ball went through the ring without both hands on it at the entry"
OUT = "the ball did not go through the ring"
FLOOR = "the ball touched the floor before the dunk"
THIRD = "travelling: a third step with the ball in the hand"
HANG = "hanging on the ring: the basket touched for more than the time allowed"
OVER = dict(shoulder_pitch=-2.6, shoulder_yaw=-0.25, elbow_pitch=1.0)   # both arms up, the palms on the ball's sides
SQUEEZE_UP = 0.16              # rad of shoulder roll beyond the touching pose overhead
VZ, PUSH_S = 3.45, 0.35        # the ghost jump's take-off speed and push


def upper(w, sp, sr, sy, ep, wy=0.0):
    """A `stand` row: both arms at (shoulder pitch, roll, yaw, elbow pitch, wrist yaw) of the right arm, the left
    mirrored."""
    up = w.robot.arb.target()[12:].copy()
    J = w.L.JOINTS
    for side in ("right", "left"):
        s = -1.0 if side == "left" else 1.0
        for jn, v in (("shoulder_pitch", sp), ("shoulder_roll", s * sr), ("shoulder_yaw", s * sy),
                      ("elbow_pitch", ep), ("elbow_roll", 0.0), ("wrist_pitch", 0.0), ("wrist_yaw", s * wy)):
            up[J.index(f"{side}_{jn}_joint") - 12] = v
    return np.r_[up, 0.0, 0.0]


def touching_roll(w, scratch, sp, sy, ep, wy=0.0) -> float:
    """The right shoulder roll at which both pads touch a ball centred between them (the left arm mirrored): forward
    kinematics on a scratch MjData, the world is not touched."""
    r, J = w.robot, w.L.JOINTS
    lo, hi = -1.2, 0.38
    for _ in range(40):
        sr = (lo + hi) / 2
        scratch.qpos[:] = w.d.qpos
        for side in ("right", "left"):
            s = -1.0 if side == "left" else 1.0
            for jn, v in (("shoulder_pitch", sp), ("shoulder_roll", s * sr), ("shoulder_yaw", s * sy),
                          ("elbow_pitch", ep), ("elbow_roll", 0.0), ("wrist_pitch", 0.0), ("wrist_yaw", s * wy)):
                scratch.qpos[r.qadr[J.index(f"{side}_{jn}_joint")]] = v
        mujoco.mj_kinematics(w.m, scratch)
        b = r.mount["right"]
        R = scratch.xmat[b].reshape(3, 3)
        c = scratch.xpos[b] + R @ [M.PAD_HALF, 0.0, M.PAD_Z] + M.BALL["radius"] * R[:, 0]
        if c[1] - scratch.qpos[r.fq + 1] > 0:
            hi = sr
        else:
            lo = sr
    return sr


def raise_overhead(w, A, n=150, settle=1.5):
    """From the start hold to OVER in n control steps, the squeeze kept on the shoulder roll all the way. Returns the
    overhead (sp, roll, sy, ep) with the squeeze."""
    scratch = mujoco.MjData(w.m)
    sp0, sy0, ep0 = M.HOLD["shoulder_pitch"], M.HOLD["shoulder_yaw"], M.HOLD["elbow_pitch"]
    hold(w, A, 0.5)
    for k in range(n + 1):
        f = k / n
        sp, sy, ep, wy = (sp0 + (OVER["shoulder_pitch"] - sp0) * f, sy0 + (OVER["shoulder_yaw"] - sy0) * f,
                          ep0 + (OVER["elbow_pitch"] - ep0) * f, OVER.get("wrist_yaw", 0.0) * f)
        sr = touching_roll(w, scratch, sp, sy, ep, wy)
        act(w, A, "stand", upper(w, sp, sr + 0.05 + (SQUEEZE_UP - 0.05) * f, sy + 0.06 * (1 - f), ep, wy))
    pose = (sp, sr + SQUEEZE_UP, sy, ep, wy)
    for _ in range(int(settle * 100)):
        act(w, A, "stand", upper(w, *pose))
    return pose


def shift(w, dx, dy, dz=0.0):
    """Injection: teleport the robot and the ball between its palms together (velocities kept)."""
    d, tr = w.d, w.task.trackers
    b = w.pos("ball")
    qa, va = w.free["ball"]
    quat, vb, wb = d.qpos[qa + 3:qa + 7].copy(), w.vel("ball"), d.qvel[va + 3:va + 6].copy()
    pel = w.pelvis()
    move_robot(w, x=pel[0] + dx, y=pel[1] + dy, z=float(d.qpos[w.robot.fq + 2]) + dz)
    tv = tr["travel"]                                    # (the teleport is not a slide of the feet)
    tv.anchor = {k: (None if v is None else [v[0] + dx, v[1] + dy]) for k, v in tv.anchor.items()}
    w.put("ball", b + [dx, dy, dz], quat=quat, vel=vb, angvel=wb)


LEFT_OPEN_DZ = 0.12
ONE_HAND_SQUEEZE = 0.03
OPEN = 0.15                    # rad: an arm that lets go rolls out this far beyond the touching pose


def jump(w, A, over=(0.0, 0.0), under=False, release="dunked", soft=True, after=None, hang=False, steps=400):
    """Raise the ball overhead, ghost-jump, at the apex teleport so that the ball is `over` (dx, dy) from the ring's
    axis (under: teleport before the take-off so that the ball rises through the ring), and let go: "dunked" (open
    both arms once the ball is through), "apex" (open both at the apex: a drop), "left" (the left arm put out at once
    when the ball's centre is LEFT_OPEN_DZ above the ring, the right one kept on the ball with a light squeeze: one
    hand at the entry), "entered" (open both once its centre is inside
    the ring); after(w) is called once the referee has seen the hands leave the ball. soft: the injected landing.
    hang: once the ball's centre is inside the ring the fall stops and the robot is held up (an external force of its
    weight) and pushed towards the backboard (2 m/s^2): its arms rest on the ring."""
    r, d, m, tr, h = w.robot, w.d, w.m, w.task.trackers, w.task.hoop
    sp, sr, sy, ep, wy = raise_overhead(w, A)
    if under:
        b = w.pos("ball")
        shift(w, h["x"] - b[0], h["y"] - b[1])
    a = VZ / PUSH_S + 9.81
    open_l = open_r = shifted = landed = called = hung = False
    for k in range(1, steps):
        if w.done:
            return
        d.xfrc_applied[:] = 0.0
        if k <= PUSH_S * 100:
            for b in r.bodies:
                d.xfrc_applied[b, 2] = m.body_mass[b] * a
        elif hang and (hung or tr["hoop"].entered):
            if not hung:
                d.qvel[r.fv:r.fv + 6] = 0.0                  # injection: the fall stops at the dunk
                hung = True
            for b in r.bodies:
                d.xfrc_applied[b, :3] = m.body_mass[b] * np.array([2.0, 0.0, 9.81])
        apex = k > PUSH_S * 100 and d.qvel[r.fv + 2] < 0
        if apex and not shifted and not under:
            b = w.pos("ball")
            shift(w, h["x"] + over[0] - b[0], h["y"] + over[1] - b[1])
            shifted = True
        bz = w.pos("ball")[2]
        if release == "dunked" and tr["dunked"] is not None or release == "apex" and apex \
                or release == "entered" and tr["hoop"].entered:
            open_l = open_r = True
        if release == "left" and shifted and bz < h["z"] + LEFT_OPEN_DZ and not open_l:
            open_l = True                                # injection: the left arm is put 0.3 rad further out at once
            j = w.L.JOINTS.index("left_shoulder_roll_joint")
            d.qpos[r.qadr[j]] += 0.3
            d.qvel[r.vadr[j]] = 0.0
        if after is not None and not called and tr["released"] is not None:
            after(w)
            called = True
        row = upper(w, sp, sr, sy, ep, wy)
        i = {s: w.L.JOINTS.index(f"{s}_shoulder_roll_joint") - 12 for s in ("left", "right")}
        if open_l and not open_r:                        # one hand: the right one keeps touching without a squeeze
            row[i["right"]] = sr - SQUEEZE_UP + ONE_HAND_SQUEEZE
        for side, op in (("left", open_l), ("right", open_r)):
            if op:                                       # that arm rolls out: the palm leaves the ball
                row[i[side]] = (sr - SQUEEZE_UP - OPEN) * (-1.0 if side == "left" else 1.0)
        act(w, A, "stand", row)
        falling = shifted and w.pelvis()[2] < r.stand_z + 0.30 and d.qvel[r.fv + 2] < -1.0
        if soft and not hang and not landed and falling:
            move_robot(w, z=r.stand_z + 0.03, yaw=0.0)  # injection: put down upright, legs at the stance, at rest
            d.qpos[r.qadr[:12]] = r.stance
            d.qvel[r.fv:r.fv + 6] = 0.0
            d.qvel[r.vadr] = 0.0
            landed = True
    hold(w, A)


def palm_forces(w):
    out = {}
    f6 = np.zeros(6)
    for s in ("left", "right"):
        n = t = 0.0
        H, B = w.task.hands[s], w.task.ball
        for i in range(w.d.ncon):
            c = w.d.contact[i]
            if (H[c.geom1] and B[c.geom2]) or (H[c.geom2] and B[c.geom1]):
                mujoco.mj_contactForce(w.m, w.d, i, f6)
                n, t = n + f6[0], t + float(np.linalg.norm(f6[1:3]))
        out[s] = (round(n, 1), round(t, 1))
    return out


def hold_capacity(w, A) -> float:
    """After 1.5 s of the start command: a downward force on the ball, ramped at 10 N/s, until the ball has slipped
    5 mm along the right palm. Returns that force in units of the ball's weight (an extra acceleration in g)."""
    hold(w, A, 1.5)
    bid = w.m.body("ball").id

    def rel():
        f, _ = M.pad_face(w, "right")
        return w.d.xmat[w.robot.mount["right"]].reshape(3, 3).T @ (w.pos("ball") - f)
    r0, F = rel(), 0.0
    while not w.done and F < 200 and np.linalg.norm(rel() - r0) <= 0.005:
        F += 0.1
        w.d.xfrc_applied[bid, 2] = -F
        hold(w, A, 0.01)
    w.d.xfrc_applied[:] = 0.0
    return F / (M.BALL["mass"] * 9.81)


def main():
    w, A = make("dunk-realgrasp")
    p, h = w.task.p, w.task.hoop
    tr = lambda: w.task.trackers                                             # noqa: E731
    assert p["ring_height_m"] == 3.05 and p["ring_inner_diameter_m"] == 0.45 and p["start_to_ring_m"] == 1.25
    assert not w.grippables, "no grip in this task"
    assert w.m.opt.cone == mujoco.mjtCone.mjCONE_ELLIPTIC

    b0 = w.pos("ball")                                                        # nop: the start hold lasts
    hold(w, A, 3.0)
    assert all(w.task.on_ball(w.ref).values()) and np.linalg.norm(w.pos("ball") - b0) < 0.05, w.pos("ball")
    print("start hold: ball", np.round(b0, 3), "after 3 s", np.round(w.pos("ball"), 3), "palm (normal, friction) N",
          palm_forces(w))
    hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)
    assert all(w.task.on_ball(w.ref).values()), "the nop agent still holds the ball at the time limit"

    w.reset()
    print("start squeeze holds an extra", round(hold_capacity(w, A), 2), "g on the ball")

    w.reset(); jump(w, A)                                                     # positive (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["dunk", "stand"], (v, w.ref.events)
    assert tr()["entry_hands"] == ["left", "right"] and tr()["released"] > tr()["dunked"], tr()
    assert v["metrics"]["basket_touch_s"] == 0.0 and w.t < 8.0, (v, w.t)
    sha = w.state_sha()
    w.reset(); jump(w, A)
    assert w.state_sha() == sha                                               # deterministic

    w.reset(); jump(w, A, soft=False)                                         # the same dunk with its real landing
    v = verdict(w)
    assert v["failed"] == "fell" and v["stages"] == ["dunk"], v

    w.reset(); jump(w, A, release="apex")                                     # let go above the ring: a drop
    assert verdict(w)["failed"] == EARLY, verdict(w)

    w.reset(); jump(w, A, over=(-0.22, 0.0), release="apex")                  # let go over the front rim: it would
    assert verdict(w)["failed"] == EARLY, verdict(w)                          # roll in

    w.reset(); jump(w, A, release="left")                                     # one hand at the entry
    assert verdict(w)["failed"] == NO_BOTH and tr()["entry_hands"] == ["right"], (verdict(w), tr()["entry_hands"])

    w.reset(); jump(w, A, under=True)                                         # straight up under the ring
    assert verdict(w)["failed"] == BELOW and verdict(w)["stages"] == [], verdict(w)

    def throw_out(w):                                                         # injection: let go inside the ring,
        w.put("ball", (h["x"] - 0.8, h["y"], h["z"] + 0.2), vel=(-1.0, 0, 0))  # the ball is put outside it
    w.reset(); jump(w, A, release="entered", after=throw_out)
    assert verdict(w)["failed"] == OUT and verdict(w)["stages"] == [], verdict(w)

    w.reset(); hold(w, A, 1.0)                                                # injection: the ball on the floor
    w.put("ball", (0.45, 0.0, M.BALL["radius"] - 0.002))                      # while the hands' last touch is fresh
    hold(w, A, 0.01)
    assert verdict(w)["failed"] == FLOOR, verdict(w)

    w.reset(); hold(w, A, 0.5); typ, row = A.hold(w)                          # walking with the ball in the hands
    while not w.done:
        act(w, A, "walk", np.r_[0.4, 0.0, 0.0, row])
    assert verdict(w)["failed"] == THIRD and all(w.task.on_ball(w.ref).values()), verdict(w)

    w.reset(); jump(w, A, hang=True)                                          # hanging on the ring
    assert verdict(w)["failed"] == HANG, (verdict(w), w.ref.events)
    w.d.xfrc_applied[:] = 0.0

    w.reset(); hold(w, A, 0.2); kick_robot(w, vel=(0.0, 3.0, 0.0)); hold(w, A)   # a fall
    assert verdict(w)["failed"] == "fell", verdict(w)
    print("PASS dunk-realgrasp")


if __name__ == "__main__":
    main()
