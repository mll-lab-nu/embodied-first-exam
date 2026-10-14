"""crawl (wires 0.45 m above the ground over 10 m): the referee says no to standing still, to walking into the wires
upright, to a robot dragged under them on hands and knees (0.46 m high: it touches), to being beside the lane, to
standing between two wires, to being beyond the last wire without having passed under, to stopping under the wires.

The positive is an INJECTION (no crawling controller of this robot exists here): the robot is laid face down in front
of the first wire (rfo.testing.move_robot and the pelvis' orientation set by hand; it lies 0.27 m high), and a
horizontal force on its pelvis (the test writes w.d.xfrc_applied, at most 700 N, regulated to 0.8 m/s) drags it over
the ground under all 21 wires: its body really passes below every wire without touching one and comes out wholly
beyond the last."""
import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict
from rfo.world import JOINTS

PRONE = [np.cos(np.pi / 4), 0.0, np.sin(np.pi / 4), 0.0]          # pitched 90 degrees forward: the trunk horizontal
J = {j[:-6]: i for i, j in enumerate(JOINTS)}


def all_fours():
    q = np.zeros(len(JOINTS))
    for s, sg in (("left", 1), ("right", -1)):
        q[J[f"{s}_hip_pitch"]], q[J[f"{s}_knee"]], q[J[f"{s}_ankle_pitch"]] = -1.5, 1.6, 0.4
        q[J[f"{s}_shoulder_pitch"]], q[J[f"{s}_elbow"]], q[J[f"{s}_shoulder_roll"]] = -1.3, 0.2, 0.15 * sg
    return q


def dragged(w, A, stop_x=None, pose=None, z=0.22):
    r = w.robot
    hold(w, A, 0.2)
    move_robot(w, x=-0.75, z=z)
    w.d.qpos[r.fq + 3:r.fq + 7] = PRONE
    if pose is not None:
        w.d.qpos[r.qadr] = pose
        r.arb.q_a[:] = r.arb.q_b[:] = pose
    top = 0.0
    step = (lambda: act(w, A, "joints", np.r_[pose, 0, 0])) if pose is not None else (lambda: hold(w, A, 0.01))
    for _ in range(80):
        step()
    while not w.done:
        x, y, _, _ = w.pelvis()
        vx, vy = w.d.qvel[r.fv], w.d.qvel[r.fv + 1]
        w.d.xfrc_applied[r.pelvis, :] = 0.0
        if stop_x is None or x < stop_x:
            w.d.xfrc_applied[r.pelvis, 0] = float(np.clip(1500 * (0.8 - vx), 0, 700))
            w.d.xfrc_applied[r.pelvis, 1] = float(np.clip(-800 * y - 200 * vy, -200, 200))
        step()
        top = max(top, float(w.robot_aabb()[1][2]))
    w.d.xfrc_applied[r.pelvis, :] = 0.0
    return top


def main():
    w, A = make("crawl")
    p, c = w.task.p, w.task.course
    x0, x1, H = c["x0"], c["x1"], p["wire_height_m"]
    assert (H, x1 - x0, len(c["wires"]), x0) == (0.45, 10.0, 21, 1.0), c                      # the stated course
    up = w.robot.rest[12:]
    hold(w, A, 20.0)
    assert not w.done and verdict(w)["stages"] == [], verdict(w)                              # nop: stands there
    hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)
    w.reset(); top = dragged(w, A)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["under the first wire", "half way", "through"], v # positive (injection)
    assert v["metrics"]["rear_x_m"] > x1 and top < H - 0.004, (v, top)                        # ... below the wires
    sha = w.state_sha()
    w.reset(); dragged(w, A)
    assert w.state_sha() == sha                                                               # deterministic
    w.reset()                                                                                 # walking at it upright
    while not w.done:
        act(w, A, "walk", np.r_[0.5, 0, 0, up, 0, 0])
    assert verdict(w)["failed"] == "touched a wire" and verdict(w)["stages"] == [], verdict(w)
    w.reset(); dragged(w, A, pose=all_fours(), z=0.42)                                        # on hands and knees:
    assert verdict(w)["failed"] == "touched a wire", verdict(w)                               # too tall
    w.reset(); hold(w, A, 0.2)                                                                # beside the lane
    move_robot(w, x=x0 + 0.75, y=p["lane_width_m"] / 2 + 0.5); hold(w, A, 0.5)
    assert verdict(w)["failed"] == "went round the wires", verdict(w)
    w.reset(); hold(w, A, 0.2)                                                                # standing between two
    move_robot(w, x=x0 + 0.24); hold(w, A, 0.05)                                              # wires
    assert verdict(w)["failed"] == "went over the wires", verdict(w)
    w.reset(); hold(w, A, 0.2)                                                                # held high above them
    move_robot(w, x=x0 + 2.0, z=2.0); hold(w, A, 0.02)
    assert verdict(w)["failed"] == "went over the wires", verdict(w)
    w.reset(); hold(w, A, 0.2)                                                                # beyond the last wire,
    move_robot(w, x=x1 + 0.6); hold(w, A, 0.5)                                                # never under
    assert verdict(w)["failed"] == "did not pass under the wires" and verdict(w)["stages"] == [], verdict(w)
    w.reset(); dragged(w, A, stop_x=x0 + 6.0)                                                 # stops under the wires
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == ["under the first wire", "half way"], v
    print("PASS crawl")


if __name__ == "__main__":
    main()
