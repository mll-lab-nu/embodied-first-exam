"""The real hand (rfo/realhand.py: Unitree's Dex1-1 two-finger gripper) on both robots, with a tennis-racket-like rod
(0.30 kg, a 32 mm handle, its centre of mass 0.335 m from the butt) held across the jaws 5 cm from the butt. No family:
a small test task declares the gripper on the right hand. Everything happens in physics through the action interface
(`stand` rows; the jaws are closed on the rod at reset by World.close_on), except the ball of the impact case, which
is launched (w.launch) at the racket head.

Shown, per robot:
  hold      at full force (closure 1, 120 N) the rod stays in the hand through a 1.6 s shoulder swing and back
  slip      at a light grip (about 8 N) the rod twists in the jaws under its own weight
  drop      opening the jaws (closure 0) lets it fall
  impact    a 30 m/s tennis ball on the head of a held racket: the rod turns in the grip (reported; not rigid)
  replay    the rows of the hold case replayed in a fresh World give the same state hash (and twice the same)
  api       continuous grip in the sim row, proprio layout, w.grab refused on a real hand, the referee's part names
  static    clamping a static box (the world body) holds nothing: w.held None, airborne() False
"""
from __future__ import annotations

import sys

import numpy as np

import mujoco

from rfo import realhand as RH
from rfo.scene import HITTABLE
from rfo.task import TaskBase
from rfo.world import World, Actions

ROD_W = 0.032


class RodTask(TaskBase):
    name = "real-hand-test"
    title = "real hand test"
    time_limit_s = 60.0
    start = (0.0, 0.0, 0.0)
    stages = ["never"]

    def __init__(self, robot, closure=1.0, ball=False):
        super().__init__()
        self.robot, self.closure, self.with_ball = robot, closure, ball
        self.grasp = None

    def build(self, sc):
        sc.real_hands["right"] = "dex1"
        b = sc.body("rod", (1.0, 2.0, 0.2), free=True)
        sc.geom(b, "rod_handle", type="capsule", fromto=(0, 0, 0, 0.20, 0, 0), size=(ROD_W / 2,), mass=0.12, **HITTABLE)
        sc.geom(b, "rod_shaft", type="capsule", fromto=(0.20, 0, 0, 0.40, 0, 0), size=(0.008,), mass=0.03, **HITTABLE)
        # the head: its contact wins over the ball's soft bounce spring (priority 2, stiff), else a 30 m/s ball passes
        # through a thin head between two physics steps
        sc.geom(b, "rod_head", type="ellipsoid", pos=(0.53, 0, 0), size=(0.13, 0.10, 0.02), mass=0.15, priority=2,
                solref="0.002 0.4", **HITTABLE)
        if self.with_ball:
            sc.ball("ball", "tennis", (3.0, 3.0, 0.04))
        sc.camera("venue", (2.5, -2.0, 1.6), (0.0, 0.0, 1.0))

    def reset(self, w):
        p, R = w.jaw_frame("right")
        # the rod horizontal, perpendicular to the closing axis, its face normal (local z) along the closing axis: on
        # the G1 at rest (forearm down) across the jaws pointing outwards, butt 5 cm beyond the centre; on the H1-2
        # (forearm forward, the jaws' cross axis vertical) along the fingers, butt 2 cm behind the centre (its round end
        # clear of the housing)
        ax, back = min(((-R[:, 1], 0.05), (R[:, 2], 0.02)), key=lambda c: abs(c[0][2]))
        Rq = np.c_[ax, np.cross(R[:, 0], ax), R[:, 0]]
        q = np.zeros(4)
        mujoco.mju_mat2Quat(q, Rq.ravel())
        w.put("rod", p - ax * back, q)
        self.grasp = w.close_on("right", "rod", self.closure)


class StaticBoxTask(TaskBase):
    """A static box (part of the world body, not a prop) between the open jaws: the hand clamps it but holds nothing."""
    name = "real-hand-static-test"
    time_limit_s = 60.0
    start = (0.0, 0.0, 0.0)
    stages = ["never"]

    def __init__(self, robot, pos, R):
        super().__init__()
        self.robot, self.pos, self.R = robot, pos, R

    def build(self, sc):
        sc.real_hands["right"] = "dex1"
        q = np.zeros(4)
        mujoco.mju_mat2Quat(q, np.ascontiguousarray(self.R).ravel())
        sc.geom(sc.wb, "static_box", type="box", pos=tuple(self.pos), quat=tuple(q), size=(0.015, 0.012, 0.012),
                **HITTABLE)
        sc.camera("venue", (2.5, -2.0, 1.6), (0.0, 0.0, 1.0))


def closure_for(force_n: float, width: float = ROD_W) -> float:
    """The closure command that clamps an object of this width with this force (realhand.py's servo)."""
    return (RH.STROKE - width + 2 * force_n / RH.KP) / RH.STROKE


def rel_pose(w):
    m, d = w.m, w.d
    b, mt = m.body("rod").id, w.robot.mount["right"]
    R = d.xmat[mt].reshape(3, 3)
    return R.T @ d.xmat[b].reshape(3, 3), R.T @ (d.xpos[b] - d.xpos[mt])


def drift(w, ref):
    R1, p1 = rel_pose(w)
    R0, p0 = ref
    ang = np.degrees(np.arccos(np.clip((np.trace(R0.T @ R1) - 1) / 2, -1, 1)))
    return float(np.linalg.norm(p1 - p0)), float(ang)


def swing(w, A, rows, seconds=1.6, amp=-0.9):
    """`stand` rows: the right shoulder pitches forward by amp and back (a cosine), then 0.4 s still."""
    typ, row0 = A.hold(w)
    assert typ == "stand"
    j = A.types["stand"]["layout"].index("right_shoulder_pitch")
    n = int(round(seconds / w.CONTROL_DT))
    worst = (0.0, 0.0)
    ref = rel_pose(w)
    for k in range(n + 40):
        row = row0.copy()
        if k < n:
            row[j] += amp * 0.5 * (1 - np.cos(2 * np.pi * k / n))
        raw = A.to_raw("stand", A.clip("stand", row), w)
        rows.append(raw)
        w.step(raw)
        assert w.held["right"] == "rod", f"dropped at t={w.t:.2f}"
        dm, da = drift(w, ref)
        worst = (max(worst[0], dm), max(worst[1], da))
    return worst


def case_hold(robot):
    t = RodTask(robot)
    w = World(t)
    A = Actions(w.robot)
    g = t.grasp
    assert abs(g["force_n"] - RH.F_MAX) < 1e-6 and abs(g["opening_m"] - ROD_W) < 0.002, g
    sha0 = w.state_sha()
    rows = []
    worst = swing(w, A, rows)
    print(f"  {robot} hold: grasp {g['opening_m'] * 1000:.1f} mm at {g['force_n']:.0f} N (settle moved it "
          f"{g['moved_m'] * 1000:.1f} mm); through the swing the rod moved at most {worst[0] * 1000:.1f} mm and "
          f"{worst[1]:.2f} deg in the hand")
    assert worst[0] < 0.01 and worst[1] < 5.0, worst
    return w, A, rows, sha0


def case_slip(robot):
    c = closure_for(8.0)
    t = RodTask(robot)
    w = World(t)
    A = Actions(w.robot)
    ref = rel_pose(w)
    typ, row = A.hold(w)
    assert row[-1] == 1.0, row[-2:]
    row[-1] = c                                   # the grip eased to about 8 N
    f = []
    for _ in range(200):
        w.step(A.to_raw(typ, row, w))
        f.append(w.hands.force("right"))
    dm, da = drift(w, ref)
    print(f"  {robot} slip: eased to closure {c:.3f} (clamp {np.median(f[50:]):.1f} N): in 2 s the rod turned {da:.1f} deg "
          f"and moved {dm * 1000:.0f} mm in the hand (held: {w.held['right']}, z {w.pos('rod')[2]:.2f} m)")
    assert da > 20.0, da
    return da


def case_drop(w, A):
    typ, row = A.hold(w)
    row[-1] = 0.0
    z0, t0 = float(w.pos("rod")[2]), w.t
    t_free = None
    for _ in range(60):
        w.step(A.to_raw(typ, row, w))
        if t_free is None and w.held["right"] is None:
            t_free = w.t - t0
    z1 = float(w.pos("rod")[2])
    print(f"  {w.robot.name} drop: open command -> let go after {t_free:.2f} s; the rod fell {z0 - z1:.2f} m in 0.6 s; "
          f"opening {w.hands.opening('right') * 1000:.0f} mm")
    assert t_free is not None and t_free < 0.03 and z0 - z1 > 0.3      # no wind-up: it lets go at once


def case_impact(robot):
    t = RodTask(robot, ball=True)
    w = World(t)
    A = Actions(w.robot)
    m, d = w.m, w.d
    mujoco.mj_kinematics(m, d)
    b = m.body("rod").id
    R = d.xmat[b].reshape(3, 3)
    head = d.xpos[b] + R[:, 0] * 0.53
    n = R[:, 2]                                       # the face normal (= the closing axis)
    w.launch("ball", head + n * 0.10, -n * 30.0)
    ref = rel_pose(w)
    typ, row = A.hold(w)
    peak_w, out = 0.0, None
    for k in range(30):
        w.step(A.to_raw(typ, row, w))
        _, va = w.free["rod"]
        wm = np.linalg.norm(d.qvel[va + 3:va + 6] - 0.0)
        peak_w = max(peak_w, float(wm))
        if k == 9:
            out = drift(w, ref)
    vb = np.linalg.norm(w.vel("ball"))
    late = drift(w, ref)
    print(f"  {robot} impact: a 30 m/s ball on the head; the rod's spin peaked at {peak_w:.1f} rad/s; 0.1 s later it had "
          f"turned {out[1]:.1f} deg in the grip ({late[1]:.1f} deg at 0.3 s), slid {late[0] * 1000:.0f} mm; ball out at "
          f"{vb:.1f} m/s; still held: {w.held['right'] == 'rod'}")
    assert out[1] > 0.5, "the grip is perfectly rigid"
    return out


def case_replay(robot, rows, sha0, sha_end):
    w = World(RodTask(robot))
    assert w.state_sha() == sha0, "t0 differs in a fresh world"
    for k, raw in enumerate(rows):
        w.step(raw)
        if k % 7 == 0:
            w.jaw_frame("right")                      # reading the frame between steps changes nothing
            w.hands.state()
            w.proprio()
    assert w.state_sha() == sha_end, "replay differs"
    print(f"  {robot} replay: {len(rows)} rows in a fresh world give the same state hash (reading the jaw frame, the "
          "hands' state and the proprioception between steps)")


def case_static(robot):
    """Clamping a static body (the world's) is not holding: w.held stays None and the referee does not count the box
    as held (airborne() stays False: the robot touches the world)."""
    def settled(pos, R):                          # the robot after 1 s in `stand`, jaws open (its arms sag at first)
        w = World(StaticBoxTask(robot, pos, R))
        A = Actions(w.robot)
        typ, row = A.hold(w)
        row[-1] = 0.0
        for _ in range(100):
            w.step(A.to_raw(typ, row, w))
        return w, A, typ, row
    w0, *_ = settled((10.0, 10.0, 0.5), np.eye(3))
    p, R = w0.jaw_frame("right")
    w0.close()
    w, A, typ, row = settled(p, R)                 # the same motion: the box now sits between the open jaws
    row[-1] = 1.0
    both = 0
    for _ in range(60):
        w.step(A.to_raw(typ, row, w))
        ref = w.ref
        box = ref.geoms(names=["static_box"])
        jaws = [ref.geoms(body=f"right_hand_jaw_{j}") for j in "ab"]
        both += all(ref.touching(j, box) for j in jaws)
        assert w.held["right"] is None, w.held
        assert not ref.held_mask().any()
        if ref.parts_touching(ref.ground):         # (the robot settles onto its feet in the first 30 ms)
            assert not ref.airborne(), "standing, yet airborne: the world counted as held"
    print(f"  {robot} static: clamped a static box ({w.hands.force('right'):.0f} N, both jaws on it {both}/60 steps): "
          "held None, airborne() False")
    assert both > 30


def case_api(robot, w, A):
    L = w.L
    assert L.RAW_DIM == len(w.last_raw)
    typ, row = A.hold(w)
    row[-1] = 0.37
    raw = A.to_raw(typ, row, w)
    assert raw[L.R_GRIP.start + 1] == 0.37 and raw[L.R_GRIP.start] in (0.0, 1.0)
    row[-1] = 1.7
    assert A.to_raw(typ, A.clip(typ, row), w)[L.R_GRIP.start + 1] == 1.0
    lay = w.proprio_layout
    assert lay[-3:] == ["jaw_opening_right", "jaw_speed_right", "jaw_force_right"] and len(lay) == len(w.proprio())
    try:
        w.grab("right", "rod")
        raise AssertionError("a weld on a real hand")
    except ValueError:
        pass
    ref = w.ref
    hands = ref.part("hands")
    for nm in ("right_hand_housing", "right_hand_jaw_a", "right_hand_pad_b3"):
        assert hands[w.m.geom(nm).id], nm
    assert "right_hand" in ref.parts_touching(ref.geoms(body="rod"))
    sp = A.spec()
    assert all("closure command" in t["meaning"] for t in sp.values())
    print(f"  {robot} api: grip continuous, proprio +3, no weld, part right_hand: ok")


def main():
    for robot in ("unitree_g1", "unitree_h1"):
        w, A, rows, sha0 = case_hold(robot)
        sha_end = w.state_sha()
        case_api(robot, w, A)
        w2, A2, rows2, _ = case_hold(robot)
        assert w2.state_sha() == sha_end, "the same rows twice: different state"
        case_replay(robot, rows, sha0, sha_end)
        case_drop(w, A)
        case_slip(robot)
        case_impact(robot)
        case_static(robot)
    print("PASS real-hand")


if __name__ == "__main__":
    sys.exit(main())
