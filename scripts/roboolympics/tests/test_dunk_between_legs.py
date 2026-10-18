"""dunk-between-legs (v2, FIBA, the Unitree H1-2, no grip): the referee says yes to a dribble started from the two-palm
hold, one bounce of it through the leg gate (the triangle of the two soles and the crotch, below the knees), the ball
gathered between both palms, no step, and the squeezed ball going down through the official ring (3.05 m) with both
hands on it, then a landing held on the feet; no to a bounce beside the leg, a ball through the legs above the knees
(not counted), a ball rolled slowly through the legs, a ball that goes through and comes back, a gather before any
bounce between the legs, a ball at rest in one palm (carrying), two touches without the floor, a dunk without the
dribble, a touch of a leg, a ball that gets away, the ball on the floor while held (at the start, and after the
gather: a second dribble), the ball let go after the gather, travelling before the release and after the gather, a
shot during the dribble, a drop over the ring, a one-hand entry from the side, a ball up through the ring, a miss
after a release inside the ring, hanging on the ring, the ball out of bounds, a fall; and nop fails.

There is no grip: the ball is held only by the arms pressing the palms against it, and every hold in this test is
real (the start hold for the whole nop episode, the gather's squeeze, the raise overhead, the jump).

The positive is an INJECTION, not a solution. Real: the start hold, the release (the arms open, the ball falls and
bounces), the right arm swung behind the hip, the ball's touches of the right palm behind the robot, its flight down
through the gap between the H1-2's feet and the bounce there (no leg touched: the soles' inner edges are 0.27 m apart,
the ball 0.239 m), the closing of both arms on it in front, the squeeze that holds it, the raise overhead, the dunk
through the real ring with both palms on it, the stand. Injected (ball velocities set between control steps, nothing
crosses the leg gate by a teleport): the ball's path round the outside of the left leg to the right hand behind the
robot, the push of that hand (the velocity at its real touch: 1.5 m/s forwards, down to the floor in the gate), the
ball's rise from its bounce in front to an apex between the open palms, and, as in dunk-realgrasp's test, the ghost
jump (an upward force on every body of the robot, then a teleport of robot and ball together over the ring at the
apex) and the landing (put down upright 0.3 m above its standing height)."""
import mujoco
import numpy as np

from rfo.testing import act, hold, kick_robot, make, move_robot, verdict
import rfo.tasks.dunk_between_legs as M

G = 9.81
RB = M.BALL["radius"]
HOLDCMD = {k: M.HOLD.get(k, 0.0) + M.SQUEEZE.get(k, 0.0) for k in M.SETTLED}      # the start command (right arm)
OPEN = dict(HOLDCMD, shoulder_roll=-0.15, shoulder_yaw=-0.05)                       # the palms apart: a catch pose
OPEN_OUT = dict(OPEN, shoulder_roll=-0.35)
BEHIND = dict(shoulder_pitch=1.0, shoulder_roll=0.0, shoulder_yaw=0.0, elbow_pitch=0.8, elbow_roll=0.0,
              wrist_pitch=0.0, wrist_yaw=0.0)                                       # the right hand behind the hip
AROUND = dict(BEHIND, shoulder_roll=-0.35)                                          # ... swung there outside the hip
PALM_UP = dict(shoulder_pitch=0.0, shoulder_roll=-0.2, shoulder_yaw=0.0, elbow_pitch=0.0, elbow_roll=1.57,
               wrist_pitch=0.0, wrist_yaw=0.0)                                      # right forearm forwards, palm up
PALM_DOWN = dict(PALM_UP, elbow_roll=-1.57)                                         # ... palm down

TIME = "time"
TRAVEL0 = "travelling: the pivot foot left the floor before the ball left the hands"
FLOOR_HELD = "the ball touched the floor while in your hands"
TWICE = "a hand touched the ball twice without the ball touching the floor in between"
REST = "the ball came to rest in a hand: a touch lasted too long"
BODY = "the ball touched a part of you other than a hand"
AWAY = "the ball got away: it was further from you than the control distance"
NOT_YET = "the dribble ended before a bounce between the legs"
SHOT = "the ball went through the ring without a hand on it (a shot, not a dunk)"
LEFT = "the ball left your hands after the gather, before the dunk"
DOUBLE = "double dribble: the ball touched the floor after the gather"
NO_HANDS = "the ball went through the ring without both hands or a hand from above on it at the entry"
BELOW = "the ball came up through the ring from below"
OUT = "the ball did not go through the ring"
HANG = "hanging on the ring: the basket touched for more than the time allowed"
OUT_BALL = "out of bounds: the ball touched the floor on or outside a boundary line"


def mirror(pose):
    return {k: (-v if k in M.MIRROR else v) for k, v in pose.items()}


def upper(w, right=None, left=None):
    """A `stand` row: the current targets with the right / left arm poses given (the left one mirrored)."""
    up = w.robot.arb.target()[12:].copy()
    J = w.L.JOINTS
    for side, pose in (("right", right), ("left", None if left is None else mirror(left))):
        for jn, v in (pose or {}).items():
            up[J.index(f"{side}_{jn}_joint") - 12] = v
    return np.r_[up, 0.0, 0.0]


def aim(w, target, T):
    """Injection: the ball's velocity set so that it flies (ballistic) to `target` in T seconds."""
    b = w.pos("ball")
    v = (np.asarray(target, float) - b) / T
    v[2] += 0.5 * G * T
    w.put("ball", b, vel=v)


def run(w, A, right, left, n, until=None) -> bool:
    for _ in range(n):
        if w.done:
            return False
        act(w, A, "stand", upper(w, right, left))
        if until is not None and until():
            return True
    return False


def catch_point(w):
    return (M.pad_face(w, "right")[0] + M.pad_face(w, "left")[0]) / 2


def release(w, A):
    """The start hold for 1 s, then both palms open: the ball falls and bounces. Returns the open palms' middle."""
    hold(w, A, 1.0)
    run(w, A, OPEN, OPEN, 15)
    return catch_point(w)


def to_the_back(w, A):
    """From the release: the ball (injected) round the outside of the left leg into the right palm behind the hip."""
    tr = w.task.trackers
    run(w, A, AROUND, OPEN, 300, lambda: w.ref.has("dribble") and w.vel("ball")[2] < 0)
    aim(w, (0.25, 0.65, 0.55), 0.25)
    run(w, A, AROUND, OPEN, 25)
    aim(w, (-0.45, 0.45, 0.80), 0.30)
    run(w, A, AROUND, OPEN, 5)
    run(w, A, BEHIND, OPEN, 25)
    pp, n = M.pad_face(w, "right")
    aim(w, pp + n * (RB - 0.01), 0.25)
    n0 = tr["hand"].count
    assert run(w, A, BEHIND, OPEN, 60, lambda: tr["hand"].count > n0), (verdict(w), w.ref.events)


def push(w, dy=0.0, vx=1.5, dx=-0.01):
    """Injection, the push of the hand behind: the ball sent forwards at vx, down to the floor dx in front of the
    middle between the feet (dy to the side of it)."""
    L, R, _ = M.gate(w)
    mid = (L + R) / 2
    b = w.pos("ball")
    tgt = np.array([mid[0] + dx, mid[1] + dy, RB + 0.005])
    aim(w, tgt, (tgt[0] - b[0]) / vx)


def in_front(w):
    return w.pos("ball")[0] > 0.30 and w.vel("ball")[2] > 0


def gather(w, A, c, lead=0.03):
    """Injection: the ball, rising in front, put under the open palms (still in front of the leg gate) and sent up to
    its apex between them; the arms close
    on it (the start command) `lead` seconds before the apex, and keep the squeeze for 1 s."""
    tr = w.task.trackers
    b = np.array([c[0], c[1], w.pos("ball")[2]])         # (put under the palms: in front of the gate, as it was)
    vz = np.sqrt(2 * G * max(c[2] - b[2], 0.05))
    T = vz / G
    w.put("ball", b, vel=(0.0, 0.0, vz))
    run(w, A, OPEN, OPEN, int(round((T - lead) * 100)))
    run(w, A, HOLDCMD, HOLDCMD, 30, lambda: tr["phase"] == "held")
    run(w, A, HOLDCMD, HOLDCMD, 100)


def dribble(w, A, dy=0.0, vx=1.5, dx=-0.01, after_cross=None, high=None):
    """The whole dribble: release, round to the back, the push through the gate (or beside it; high: thrown straight
    through the gate's plane at that height, to bounce in front), the gather."""
    release(w, A)
    to_the_back(w, A)
    if high is None:
        push(w, dy, vx, dx)
    else:
        L, R, _ = M.gate(w)
        b = w.pos("ball")
        x0 = (L[0] + R[0]) / 2
        T = (x0 - b[0]) / 2.0                                             # 2 m/s forwards, level at the gate
        w.put("ball", b, vel=(2.0, ((L[1] + R[1]) / 2 - b[1]) / T, (high - b[2]) / T + 0.5 * G * T))
    run(w, A, AROUND, OPEN, 10)                                           # the right hand back to the front
    if after_cross is not None:
        run(w, A, AROUND, OPEN, 120, lambda: in_front(w))
        if after_cross(w, A):
            return
    run(w, A, OPEN_OUT, OPEN, 20)
    run(w, A, OPEN, OPEN, 120, lambda: in_front(w))
    gather(w, A, catch_point(w))


# ---- the dunk (dunk-realgrasp's test: raise overhead with the squeeze, ghost jump, teleport over the ring) ----
OVER = dict(shoulder_pitch=-2.6, shoulder_yaw=-0.25, elbow_pitch=1.0)   # both arms up, the palms on the ball's sides
SQUEEZE_UP = 0.16              # rad of shoulder roll beyond the touching pose overhead
VZ, PUSH_S = 3.45, 0.35        # the ghost jump's take-off speed and push
LEFT_OPEN_DZ = 0.12
ONE_HAND_SQUEEZE = 0.03
OPEN_ROLL = 0.15               # rad: an arm that lets go rolls out this far beyond the touching pose


def both(w, sp, sr, sy, ep, wy=0.0):
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
    kinematics on a scratch MjData, the world is not touched. (dunk-realgrasp's, centred in the torso's frame.)"""
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
        c = scratch.xpos[b] + R @ [M.PAD_HALF, 0.0, M.PAD_Z] + RB * R[:, 0]
        T = scratch.xmat[r.torso].reshape(3, 3)          # (in the torso's frame: the robot may have turned a little)
        if (T.T @ (c - scratch.xpos[r.torso]))[1] > 0:
            hi = sr
        else:
            lo = sr
    return sr


def raise_overhead(w, A, n=150, settle=1.5):
    """From the hold to OVER in n control steps, the squeeze kept on the shoulder roll all the way."""
    scratch = mujoco.MjData(w.m)
    sp0, sy0, ep0 = M.HOLD["shoulder_pitch"], M.HOLD["shoulder_yaw"], M.HOLD["elbow_pitch"]
    hold(w, A, 0.5)
    for k in range(n + 1):
        f = k / n
        sp, sy, ep, wy = (sp0 + (OVER["shoulder_pitch"] - sp0) * f, sy0 + (OVER["shoulder_yaw"] - sy0) * f,
                          ep0 + (OVER["elbow_pitch"] - ep0) * f, OVER.get("wrist_yaw", 0.0) * f)
        sr = touching_roll(w, scratch, sp, sy, ep, wy)
        act(w, A, "stand", both(w, sp, sr + 0.05 + (SQUEEZE_UP - 0.05) * f, sy + 0.06 * (1 - f), ep, wy))
    pose = (sp, sr + SQUEEZE_UP, sy, ep, wy)
    for _ in range(int(settle * 100)):
        act(w, A, "stand", both(w, *pose))
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
    tr["gate_b"] = None                                  # (nor a pass of the ball through the leg gate)


def jump(w, A, over=(0.0, 0.0), under=False, release="dunked", soft=True, after=None, hang=False, steps=400):
    """dunk-realgrasp's ghost jump (see its test): raise overhead, jump, teleport over the ring at the apex (`over`
    off its axis; under: before the take-off, under the ring), let go "dunked" / "apex" / "left" (the left arm out
    just above the ring, the right one kept on the side of the ball) / "entered"; after(w) once the hands have left
    the ball; soft: the injected landing; hang: held up at the ring and pushed to the backboard."""
    r, d, m, tr, h = w.robot, w.d, w.m, w.task.trackers, w.task.hoop
    sp, sr, sy, ep, wy = raise_overhead(w, A)
    if under:
        b = w.pos("ball")
        shift(w, h["x"] - b[0], h["y"] - b[1])
    a = VZ / PUSH_S + G
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
                d.qvel[r.fv:r.fv + 6] = 0.0
                hung = True
            for b in r.bodies:
                d.xfrc_applied[b, :3] = m.body_mass[b] * np.array([2.0, 0.0, G])
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
            open_l = True
            j = w.L.JOINTS.index("left_shoulder_roll_joint")
            d.qpos[r.qadr[j]] += 0.3
            d.qvel[r.vadr[j]] = 0.0
        if after is not None and not called and tr["let_go"] is not None:
            after(w)
            called = True
        row = both(w, sp, sr, sy, ep, wy)
        i = {s: w.L.JOINTS.index(f"{s}_shoulder_roll_joint") - 12 for s in ("left", "right")}
        if open_l and not open_r:
            row[i["right"]] = sr - SQUEEZE_UP + ONE_HAND_SQUEEZE
        for side, op in (("left", open_l), ("right", open_r)):
            if op:
                row[i[side]] = (sr - SQUEEZE_UP - OPEN_ROLL) * (-1.0 if side == "left" else 1.0)
        act(w, A, "stand", row)
        falling = shifted and w.pelvis()[2] < r.stand_z + 0.30 and d.qvel[r.fv + 2] < -1.0
        if soft and not hang and not landed and falling:
            move_robot(w, z=r.stand_z + 0.03, yaw=0.0)
            d.qpos[r.qadr[:12]] = r.stance
            d.qvel[r.fv:r.fv + 6] = 0.0
            d.qvel[r.vadr] = 0.0
            landed = True
    hold(w, A)
# ---- end of the dunk ----


def failed(w, reason, stages=None):
    v = verdict(w)
    assert v["failed"] == reason, (reason, v, w.ref.events[-4:])
    if stages is not None:
        assert v["stages"] == stages, (stages, v)


def main():
    w, A = make("dunk-between-legs")
    p, h, t = w.task.p, w.task.hoop, w.task
    tr = lambda: w.task.trackers                                             # noqa: E731
    assert p["ring_height_m"] == 3.05 and p["ring_inner_diameter_m"] == 0.45 and not w.grippables
    assert abs(h["x"] - h["free_throw_line_x"] - (p["free_throw_line_m"] - 1.575)) < 1e-9
    assert abs(h["free_throw_line_x"] - p["start_behind_free_throw_line_m"]) < 1e-9     # the line's edge on our side
    assert w.m.opt.cone == mujoco.mjtCone.mjCONE_ELLIPTIC
    L, R, C = M.gate(w)
    print("leg gate at t=0: feet", np.round(L, 3), np.round(R, 3), "crotch", np.round(C, 3))

    b0 = w.pos("ball")                                                        # nop: the start hold lasts
    hold(w, A)
    failed(w, TIME, [])
    assert all(t.on_ball(w.ref).values()) and np.linalg.norm(w.pos("ball") - b0) < 0.06, w.pos("ball")

    w.reset(); dribble(w, A); jump(w, A)                                      # positive (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == t.stages, (v, w.ref.events)
    cross = next(e for e in w.ref.events if e.get("stage") == "between the legs")["cross"]
    assert cross["inside"] and cross["speed"] >= p["cross_speed_min_m_s"] and v["metrics"]["between_the_legs"] == 1
    assert tr()["entry_hands"]["on"] == ["left", "right"] and tr()["travel"].steps == [], tr()
    print("positive:", v["metrics"], "cross", cross, "t", w.t)
    sha = w.state_sha()
    w.reset(); dribble(w, A); jump(w, A)
    assert w.state_sha() == sha                                               # deterministic

    w.reset(); dribble(w, A); jump(w, A, soft=False)                          # the same with its real landing
    failed(w, "fell", t.stages[:4])

    w.reset(); dribble(w, A, dy=0.55, dx=0.0)                                 # a bounce beside the left leg
    failed(w, NOT_YET, ["dribble"])

    w.reset(); dribble(w, A, high=0.62, after_cross=lambda w, A: True)       # through the legs above the knees
    c = tr()["cross"]                                                         # (between the thighs' collision
    assert c and not c["inside"] and c["z"] > M.knee_height(w) and not w.ref.failed, (c, verdict(w))   # capsules)

    w.reset(); release(w, A)                                                  # the robot rocks forwards over a
    run(w, A, OPEN, OPEN, 300, lambda: w.ref.has("dribble"))                  # ball lying still between its soles
    L, R, _ = M.gate(w)
    nh = np.asarray(tr()["gate_n"]) * [1, 1, 0]
    w.put("ball", (L + R) / 2 * [1, 1, 0] + [0, 0, RB] - nh / np.linalg.norm(nh) * 0.03)
    tr()["gate_b"] = None
    kick_robot(w, vel=(1.3, 0.0, 0.0), angvel=(0.0, 1.3, 0.0))               # (about the ankles)
    run(w, A, OPEN, OPEN, 60, lambda: tr()["cross"] is not None)
    c = tr()["cross"]
    assert c and c["inside"] and abs(c["speed"]) < 0.1 < p["cross_speed_min_m_s"], (c, verdict(w))
    print("rock over a still ball:", c)

    w.reset(); dribble(w, A, vx=0.7)                                          # rolled slowly through the legs
    failed(w, NOT_YET, ["dribble"])

    def back(w, A):                                                           # through, and back through again
        push(w, vx=-1.5, dx=0.01)
        run(w, A, AROUND, OPEN, 10)
        run(w, A, BEHIND, OPEN, 100, lambda: w.pos("ball")[0] < -0.25 and w.vel("ball")[2] > 0)
        pp, n = M.pad_face(w, "right")
        aim(w, pp + n * (RB - 0.01), 0.20)                                    # into the right palm behind again
        run(w, A, BEHIND, OPEN, 60, lambda: tr()["hand"].count > 1 or w.ref.failed is not None)
        return True
    w.reset(); dribble(w, A, after_cross=back)
    assert tr()["hand"].count == 2 and w.ref.stages == ["dribble"] and not w.ref.failed, (verdict(w), w.ref.events)
    print("through and back:", tr()["cross"], verdict(w)["metrics"])

    w.reset(); c = release(w, A)                                              # gathered at once
    run(w, A, OPEN, OPEN, 300, lambda: w.ref.has("dribble") and w.vel("ball")[2] > 0)
    gather(w, A, c)
    failed(w, NOT_YET, ["dribble"])

    w.reset(); release(w, A)                                                  # carrying: on the upturned palm
    run(w, A, PALM_UP, OPEN, 300, lambda: w.ref.has("dribble") and w.vel("ball")[2] < 0)
    run(w, A, PALM_UP, OPEN, 30)
    pp, n = M.pad_face(w, "right")
    w.put("ball", pp + n * (RB + 0.005))
    run(w, A, PALM_UP, OPEN, 100)
    failed(w, REST, ["dribble"])
    assert not tr()["top"]["right"]                                           # (a palm under it: not from above)

    w.reset(); release(w, A)                                                  # a touch before the floor
    run(w, A, PALM_UP, OPEN, 8)
    pp, n = M.pad_face(w, "right")
    w.put("ball", pp + n * (RB + 0.005))
    run(w, A, PALM_UP, OPEN, 30)
    failed(w, TWICE, [])

    w.reset(); release(w, A)                                                  # a palm on top of the ball: "from above"
    run(w, A, PALM_DOWN, OPEN, 300, lambda: w.ref.has("dribble") and w.vel("ball")[2] < 0)
    run(w, A, PALM_DOWN, OPEN, 30)
    pp, n = M.pad_face(w, "right")
    assert n[2] < -0.9, n
    w.put("ball", pp + n * (RB + 0.01), vel=(0.0, 0.0, 0.5))
    run(w, A, PALM_DOWN, OPEN, 10, lambda: tr()["hand"].count >= 1)
    assert tr()["top"]["right"] and tr()["hand"].count == 1 and not w.ref.failed, (tr()["top"], verdict(w))

    w.reset(); release(w, A); to_the_back(w, A)                               # pushed at the left shin
    L, R, C = M.gate(w)
    aim(w, (L[0], L[1], 0.35), 0.2)
    run(w, A, BEHIND, OPEN, 60)
    failed(w, BODY)
    assert {"left_shin", "left_foot", "left_thigh"} & set(w.ref.events[-1]["parts"]), w.ref.events[-1]

    w.reset(); release(w, A)                                                  # thrown away
    w.put("ball", w.pos("ball"), vel=(5.0, 0.0, 3.0))
    run(w, A, OPEN, OPEN, 100)
    failed(w, AWAY)

    w.reset(); hold(w, A, 1.0)                                                # injection: on the floor while held
    w.put("ball", (0.45, 0.0, RB - 0.002))
    hold(w, A, 0.01)
    failed(w, FLOOR_HELD, [])

    w.reset(); hold(w, A, 0.5); typ, row = A.hold(w)                          # walking with the ball in the hands
    while not w.done:
        act(w, A, "walk", np.r_[0.4, 0.0, 0.0, row])
    failed(w, TRAVEL0, [])

    w.reset(); dribble(w, A); typ, row = A.hold(w)                            # walking after the gather
    while not w.done:
        act(w, A, "walk", np.r_[0.4, 0.0, 0.0, row])
    v = verdict(w)
    assert v["failed"].startswith("travelling") and v["stages"] == t.stages[:3], v

    w.reset(); dribble(w, A); run(w, A, OPEN, OPEN, 100)                      # let go after the gather
    failed(w, LEFT, t.stages[:3])

    w.reset(); dribble(w, A)                                                  # injection: the held ball on the floor
    w.put("ball", w.pos("ball") * [1, 1, 0] + [0, 0, RB - 0.002])
    hold(w, A, 0.01)
    failed(w, DOUBLE, t.stages[:3])

    w.reset(); release(w, A)                                                  # a shot during the dribble: the ball
    run(w, A, OPEN, OPEN, 300, lambda: w.ref.has("dribble"))                  # put above the ring, falling
    move_robot(w, x=h["x"] - 1.0)                                             # (dribbled up to the basket)
    w.put("ball", (h["x"], h["y"], h["z"] + 0.6), vel=(0, 0, 0))
    tr()["gate_b"] = None
    run(w, A, OPEN, OPEN, 60)
    failed(w, SHOT, ["dribble"])

    w.reset(); jump(w, A)                                                     # dunk-realgrasp's dunk, no dribble:
    failed(w, TRAVEL0, [])                                                    # the take-off is a travel

    w.reset(); dribble(w, A); jump(w, A, release="apex")                      # let go above the ring: a drop
    failed(w, LEFT, t.stages[:3])

    w.reset(); dribble(w, A); jump(w, A, release="left")                      # one hand, on the side, at the entry
    failed(w, NO_HANDS, t.stages[:3])
    assert tr()["entry_hands"]["on"] == ["right"] and tr()["entry_hands"]["from_above"] == [], tr()["entry_hands"]

    w.reset(); dribble(w, A); jump(w, A, under=True)                          # straight up under the ring
    failed(w, BELOW, t.stages[:3])

    def throw_out(w):                                                         # injection: let go inside the ring,
        w.put("ball", (h["x"] - 0.8, h["y"], h["z"] + 0.2), vel=(-1.0, 0, 0))  # the ball is put outside it
    w.reset(); dribble(w, A); jump(w, A, release="entered", after=throw_out)
    failed(w, OUT, t.stages[:3])

    w.reset(); dribble(w, A); jump(w, A, hang=True)                           # hanging on the ring
    failed(w, HANG)
    w.d.xfrc_applied[:] = 0.0

    w.reset(); release(w, A)                                                  # injection: the dribble near the end
    run(w, A, OPEN, OPEN, 300, lambda: w.ref.has("dribble"))                  # line, the ball bounces beyond it
    move_robot(w, x=t.x_end - 1.0)
    w.put("ball", (t.x_end + 0.3, 0.0, 0.5), vel=(0, 0, -2.0))
    tr()["gate_b"] = None
    run(w, A, OPEN, OPEN, 50)
    failed(w, OUT_BALL, ["dribble"])

    w.reset(); release(w, A); kick_robot(w, vel=(0.0, 3.0, 0.0)); hold(w, A)  # a fall during the dribble
    failed(w, "fell")
    print("PASS dunk-between-legs")


if __name__ == "__main__":
    main()
