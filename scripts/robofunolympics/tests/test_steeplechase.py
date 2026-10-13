"""steeplechase (the H1-2 at the TR 23 water jump): the referee says no to standing still, to walking into the hurdle
(the fixed bar stops the hips and a foot goes on under it), to a body dragged under its bar, to walking round it, to flying over the track beside its end, to a
trail foot below the top beside the hurdle, to stepping out of the pit sideways, to lying beyond the pit.

The positives are INJECTIONS (no controller of this robot gets over a 0.914 m hurdle: its best open-loop squat jump
found here lifts its centre of mass 0.16 m, and its walking policy does not even climb the pit's 11.5 degree slope,
which test (B) shows): the standing robot is set down a little before the hurdle (rfo.testing.move_robot) and given a
velocity (kick_robot), so it really flies over the bar; just before it touches down the test removes its velocity (a
ghost landing: the `stand` action does not absorb a drop of a metre or more) and the platform's stance stands.
  (A) 5.5 m/s forward and up: over the hurdle and the whole water jump, down on the track beyond the pit, stands.
  (B) 1.5 m/s forward, 4.9 m/s up: over the hurdle, down in the pit's deepest part, where it really stands on the pit's
      floor 0.5 m below the track; the walking policy is then tried on the slope (it does not get out); a second
      injected hop (4.5 m/s forward, 4.0 m/s up) carries it out over the slope; it stands beyond the far edge.
  (C) set standing on the hurdle's top bar (its feet really stand on it for 0.3 s: legal, "in any manner"), then
      lifted off it and given 5.5 m/s forward and 2.5 m/s up: beyond the pit, stands."""
import numpy as np

from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

PRONE = [np.cos(np.pi / 4), 0.0, np.sin(np.pi / 4), 0.0]          # pitched 90 degrees forward: lying face down
NOT_OVER = "did not go over the hurdle"
SIDE = "stepped to the side of the water jump"


def ground_z(w, x):
    g = w.task.geo
    x0, x1 = g["pit_x"]
    if x < x0 or x > x1:
        return 0.0
    return -g["pit_depth"] * min(1.0, (x1 - x) / (x1 - g["slope_from_x"]))


def flight(w, A, vel, ghost=True, joints=None, stand=False):
    """Give the robot a velocity and step until it is down again; ghost: its velocity removed 4 cm above the ground."""
    r = w.robot
    kick_robot(w, vel=vel)
    t0 = w.t
    while not w.done and w.t - t0 < 3.0:
        if stand:
            act(w, A, "stand", np.r_[r.rest[12:], 0, 0])
        elif joints is None:
            hold(w, A, 0.01)
        else:
            act(w, A, "joints", np.r_[joints, 0, 0])
        low = float(w.robot_aabb()[0][2]) - ground_z(w, float(w.pelvis()[0]))
        if w.t - t0 > 0.15 and w.d.qvel[r.fv + 2] < 0 and low < 0.04:
            if ghost:
                w.d.qvel[r.fv:r.fv + 6] = 0.0
            return


def start_at(w, A, x, y=0.0):
    w.reset(); hold(w, A, 0.2); move_robot(w, x=x, y=y); hold(w, A, 0.1)


def main():
    w, A = make("steeplechase")
    p, g, r = w.task.p, w.task.geo, w.robot
    up = r.rest[12:]
    far = g["pit_x"][1]
    assert w.robot_name == "unitree_h1" and (g["top"], g["half_width"] * 2, far - g["pit_x"][0]) == (0.914, 3.66, 3.66)
    assert abs(g["slope_deg"] - 11.49) < 0.01
    hold(w, A)
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [] and abs(w.pelvis()[0]) < 0.1, v        # nop (stands 60 s)

    def a():
        start_at(w, A, 8.6); flight(w, A, (5.5, 0.0, 5.5)); hold(w, A)
    a()
    v = verdict(w)
    assert v["success"] and v["stages"] == ["hurdle", "out of the water jump", "stand"], v    # positive (A)
    over = [e for e in w.ref.events if e["ev"] == "over the hurdle"]
    assert sorted(e["point"] for e in over) == ["left_foot", "pelvis", "right_foot"], over
    assert all(e["z"] > g["top"] + 0.1 for e in over) and v["metrics"]["rear_x_m"] > far, (over, v)
    sha = w.state_sha()
    a()
    assert w.state_sha() == sha                                                               # deterministic

    start_at(w, A, 9.39); flight(w, A, (1.5, 0.0, 4.9)); hold(w, A, 1.0)                      # positive (B)
    v = verdict(w)
    assert not w.done and v["stages"] == ["hurdle"], v
    x, _, z, _ = w.pelvis()
    assert g["hurdle_x"][1] < x < g["slope_from_x"] and abs(z - (r.stand_z - p["pit_depth_m"])) < 0.05, w.pelvis()
    assert w.ref.parts_touching(w.ref.geoms(names=["floor"])) == {"left_foot", "right_foot"}  # stands in the pit
    t0 = w.t
    while w.t - t0 < 8.0 and not w.done:                                                      # the walking policy on
        x, y, _, yaw = w.pelvis()                                                             # the slope: no way out
        act(w, A, "walk", np.r_[0.8, np.clip(-y, -0.3, 0.3), np.clip(-2 * yaw - y, -1, 1), up, 0, 0])
    assert not w.done and w.ref.robot_span((1.0, 0.0, 0.0))[0] < far - 1.0, (verdict(w), w.pelvis())
    print(f"  the walking policy on the 11.5 degree slope: pelvis at x = {w.pelvis()[0]:.2f} after 8 s "
          f"(the slope starts at {g['slope_from_x']:.2f}, the far edge is at {far:.2f})")
    act(w, A, "walk", np.r_[0, 0, 0, up, 0, 0], 100)
    x = float(w.pelvis()[0])
    assert w.upright() > 0.99 and abs(w.pelvis()[3]) < 0.3, w.pelvis()
    flight(w, A, ((far + 0.6 - x) / 0.66, 0.0, 4.0), stand=True)                              # (the stance from the
    while not w.done:                                                                         # take-off on)
        act(w, A, "stand", np.r_[up, 0, 0])
    v = verdict(w)
    assert v["success"] and v["stages"] == ["hurdle", "out of the water jump", "stand"], v

    w.reset(); hold(w, A, 0.2)                                                                # positive (C)
    move_robot(w, x=g["plane_x"] - 0.03, z=r.stand_z + g["top"] + 0.002); hold(w, A, 0.3)
    bar = w.ref.geoms(names=["hurdle_bar"])
    assert w.ref.parts_touching(bar) == {"left_foot", "right_foot"} and not w.done, verdict(w)   # on the bar
    assert not any(w.task.trackers["over"].values())
    kick_robot(w, vel=(0.0, 0.0, 2.7)); hold(w, A, 0.02)                                      # up off the bar first
    assert w.ref.airborne()                                                                   # (no scrape along it)
    flight(w, A, (5.5, 0.0, 2.5)); hold(w, A)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["hurdle", "out of the water jump", "stand"], v

    start_at(w, A, 9.3)                                                                       # walking into the hurdle:
    while w.t < 8.0 and not w.done:                                                           # the bar stops the hips,
        act(w, A, "walk", np.r_[0.8, 0, 0, up, 0, 0])                                         # a foot goes on under it
    v, e = verdict(w), w.ref.events[-1]
    assert v["failed"] == NOT_OVER and e["how"] == "below its top" and e["point"].endswith("_foot"), (v, e)
    assert v["stages"] == [] and w.pelvis()[0] < g["hurdle_x"][0] and e["z"] < 0.3, (v, e, w.pelvis())

    w.reset(); hold(w, A, 0.2)                                                                # under the bar: laid
    move_robot(w, x=8.6, z=0.25); w.d.qpos[r.fq + 3:r.fq + 7] = PRONE; hold(w, A, 0.6)        # face down, dragged
    while not w.done and w.t < 8.0:                                                           # by a force
        w.d.xfrc_applied[r.pelvis, 0] = float(np.clip(1500 * (1.0 - w.d.qvel[r.fv]), 0, 900))
        hold(w, A, 0.01)
    w.d.xfrc_applied[:] = 0.0
    v, e = verdict(w), w.ref.events[-1]
    assert v["failed"] == NOT_OVER and e["how"] == "below its top" and e["z"] < 0.5, (v, e)

    start_at(w, A, 9.5, y=2.6)                                                                # walking round it
    while not w.done and w.t < 8.0:
        act(w, A, "walk", np.r_[0.8, 0, 0, up, 0, 0])
    v, e = verdict(w), w.ref.events[-1]
    assert v["failed"] == NOT_OVER and abs(e["y"]) > g["half_width"], (v, e)

    start_at(w, A, 8.6, y=2.2); flight(w, A, (5.5, 0.0, 5.5)); hold(w, A, 0.5)                # flying past its end,
    v, e = verdict(w), w.ref.events[-1]                                                       # higher than the bar
    assert v["failed"] == NOT_OVER and e["how"] == "outside its width" and e["point"] == "pelvis" and e["z"] > 1.5, (v, e)

    start_at(w, A, 8.63, y=1.70)                                                              # the pelvis over the
    q = w.d.qpos[r.qadr].copy()                                                               # bar's end, the right leg
    q[7], q[9] = -1.7, 2.0                                                                    # tucked over it, the left
    flight(w, A, (4.0, 0.0, 3.5), joints=q); hold(w, A, 0.3)                                  # leg trailing beside the
    v, e = verdict(w), w.ref.events[-1]                                                       # hurdle below its top
    ok = [x["point"] for x in w.ref.events if x["ev"] == "over the hurdle"]
    assert v["failed"] == NOT_OVER and e["how"] == "below its top" and e["point"] == "left_foot", (v, e)
    assert "pelvis" in ok and abs(e["y"]) > g["half_width"], (ok, e)

    start_at(w, A, 9.39); flight(w, A, (1.5, 0.0, 4.9)); hold(w, A, 0.5)                      # in the pit, then out
    assert not w.done and verdict(w)["stages"] == ["hurdle"], verdict(w)                      # of it sideways (set
    move_robot(w, y=2.6, z=r.stand_z + 0.01); hold(w, A, 0.3)                                 # on the track beside it)
    assert verdict(w)["failed"] == SIDE, verdict(w)

    start_at(w, A, 9.39, y=1.55); flight(w, A, (1.5, 0.3, 4.9)); hold(w, A, 3.0)              # over the hurdle near
    v, e = verdict(w), w.ref.events[-1]                                                       # its end, drifting: the
    assert v["failed"] == SIDE and v["stages"] == ["hurdle"] and e["pelvis_y"] > 1.82, (v, e)   # pelvis past the side

    start_at(w, A, 8.6); flight(w, A, (5.5, 0.0, 5.5), ghost=False); hold(w, A)               # beyond the pit, but the
    v = verdict(w)                                                                            # landing is a crash
    assert v["failed"] == "time" and v["stages"] == ["hurdle", "out of the water jump"], v
    print("PASS steeplechase")


if __name__ == "__main__":
    main()
