"""long-jump (TR 29-30, the pit 1 m beyond the take-off line): the referee says no to standing still, to running and
to walking across the line, to a foot over the line at the take-off, to a jump that comes down on the runway before
the pit or beside the pit, to a take-off from beside the runway, to a "flight" made by pulling the feet up at speed,
to getting into the sand without a flight, and to coming back out of the pit behind the mark.

The positive is an INJECTION, not a solution: the robot is put at the board by hand (the run-up left out), stands
there on its own, and is then given a take-off velocity by hand (rfo.testing.kick_robot: 3.6 m/s forward, 2.5 m/s up)
so that it really leaves the ground behind the line, really flies 0.5 s over the metre of runway and really lands
in the sand 1.5 m beyond the line (where it falls over, which the rules allow)."""
import numpy as np

from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

BOARD = -0.25                    # the pelvis at the take-off place: the feet's front ends 0.136 m behind the line


def jump(w, A, vel, x_from=BOARD, y=0.0, angvel=(0.0, 0.0, 0.0), seconds=None):
    """Injected jump: put at the take-off place, stand, get the velocity, hold the stance."""
    w.reset(); hold(w, A, 0.1); move_robot(w, x=x_from, y=y); hold(w, A, 0.5)
    if not w.done:
        kick_robot(w, vel, angvel)
        hold(w, A, seconds)


def main():
    w, A = make("long-jump")
    p = w.task.p
    assert (p["runway_m"], p["board_to_pit_m"], p["pit_length_m"], p["pit_width_m"]) == (40.0, 1.0, 9.0, 2.75)
    sand = w.m.geom("sand").id
    assert abs(w.d.geom_xpos[sand][2] + w.m.geom_size[sand][2]) < 1e-9 and abs(w.d.geom_xpos[sand][0] - 5.5) < 1e-9
    hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [] and abs(w.pelvis()[2] - 0.786) < 0.01, verdict(w)   # nop
    jump(w, A, (3.6, 0.0, 2.5))                                                               # positive (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["take-off", "landing"] and v["metrics"]["mark_m"] >= 1.0, v
    assert v["metrics"]["air_s"] > 0.45 and v["metrics"]["takeoff_x_m"] < 0.0, v
    print("  injected jump:", v["metrics"])
    sha = w.state_sha()
    jump(w, A, (3.6, 0.0, 2.5))
    assert w.state_sha() == sha                                                               # determinism
    w.reset()                                                            # the running policy across the line: no jump
    while not w.done:
        _, y, _, yaw = w.pelvis()
        act(w, A, "run", [4.0, 0.0, float(np.clip(-1.5 * yaw - 1.0 * y, -0.5, 0.5)), 0, 0])
    v = verdict(w)
    assert v["failed"] == "touched the ground beyond the take-off line outside the sand" and v["stages"] == [], v
    print("  running across:", v["failed"], w.ref.events[-1])
    w.reset(); hold(w, A, 0.1); move_robot(w, x=-0.6)                    # walking across the line
    while not w.done:
        act(w, A, "walk", np.r_[0.5, 0, 0, w.robot.rest[12:], 0, 0])
    assert verdict(w)["failed"] == "a foot on or over the take-off line" and verdict(w)["stages"] == [], verdict(w)
    jump(w, A, (3.6, 0.0, 2.5), x_from=-0.105)                           # the toes 1 cm over the line
    assert verdict(w)["failed"] == "a foot on or over the take-off line" and verdict(w)["stages"] == [], verdict(w)
    jump(w, A, (3.6, 0.0, 2.5), x_from=-0.125)                           # 1 cm behind it: no foul
    assert verdict(w)["success"], verdict(w)
    jump(w, A, (2.0, 0.0, 2.3))                                          # down on the runway before the pit
    v = verdict(w)
    assert v["failed"] == "touched the ground beyond the take-off line outside the sand" and v["stages"] == [], v
    assert 0.0 < w.ref.events[-1]["at"][0] < 1.0, w.ref.events[-1]
    jump(w, A, (3.6, 3.4, 2.5))                                          # down beside the pit
    v = verdict(w)
    assert v["failed"] == "touched the ground beyond the take-off line outside the sand" and v["stages"] == [], v
    assert abs(w.ref.events[-1]["at"][1]) > 1.375, w.ref.events[-1]
    jump(w, A, (3.6, -1.6, 2.5), y=0.95)                                 # a take-off from beside the runway
    assert verdict(w)["failed"] == "took off outside the board's ends" and verdict(w)["stages"] == [], verdict(w)
    w.reset(); hold(w, A, 0.1); move_robot(w, x=BOARD); hold(w, A, 0.5)  # the feet pulled up at a run-up's speed
    q = w.robot.arb.target().copy()
    for s in (0, 6):
        q[s], q[s + 3] = -1.6, 2.4
    w.d.qvel[w.robot.fv] = 7.0
    while not w.done:
        act(w, A, "joints", np.r_[q, 0, 0])
    v = verdict(w)
    assert v["failed"] == "the flight was not a jump" and v["stages"] == [] and v["metrics"]["rise_m"] < 0.05, v
    print("  feet pulled up at 7 m/s:", v["metrics"])
    w.reset(); hold(w, A, 0.1); move_robot(w, x=2.0); hold(w, A, 0.2)    # put into the sand by hand: no flight
    assert verdict(w)["failed"] == "into the sand without a flight" and verdict(w)["stages"] == [], verdict(w)
    jump(w, A, (3.6, 0.0, 2.5), seconds=0.0)                             # a good jump, then back out behind the mark
    while not w.done and not w.ref.has("take-off"):
        hold(w, A, 0.01)
    hold(w, A, 0.3); move_robot(w, x=0.5, z=0.4); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "touched the ground outside the pit nearer the take-off line than the mark", v
    assert v["stages"] == ["take-off"], v
    jump(w, A, (5.0, 0.0, 2.5), seconds=0.0)                             # a long jump, then falling back in the sand
    while not w.done and not w.ref.has("take-off"):
        hold(w, A, 0.01)
    x_land = w.pelvis()[0]
    hold(w, A, 0.3); move_robot(w, x=x_land - 0.8, z=0.4); hold(w, A)
    v = verdict(w)
    assert v["success"] and 1.0 <= v["metrics"]["mark_m"] < x_land - 0.6, (v, x_land)       # ... shortens it
    print("PASS long-jump")


if __name__ == "__main__":
    main()
