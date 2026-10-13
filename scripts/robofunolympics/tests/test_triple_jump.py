"""triple-jump (TR 31, the pit 7 m beyond the take-off line): the referee says no to standing still, to walking over
the line, to a hop from both feet, to a hop that lands on both feet, to a "step" that lands on the hop's foot again,
to the other ("sleeping") foot touching the ground after the hop, to a jump that comes down before the pit, to one long jump from the
line into a (nearer) pit, to coming back out of the pit behind the mark, and to travelling on the landing foot between
two phases (the foot down again half a metre on, as after a hop too short to be a flight).

The positive is an INJECTION, not a solution: the robot is put at the board by hand, really lifts its left foot with
its own motors (`joints` rows) and stands on the right one; then it is given a velocity by hand three times
(rfo.testing.kick_robot: about 5 m/s forward and 3 m/s up), so that it really leaves the ground from one foot, really
flies 0.6 s and 3 m, and really comes down on the foot the rules ask for (the right again after the hop; the left
after the step, the legs changed over in the air by its own motors; the sand after the jump). At the hop's and the
step's touch-down its velocity is taken away by hand, and the next velocity is given 0.05 s later."""
import numpy as np

from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

BOARD = -0.25                    # the pelvis at the take-off place: the feet's front ends 0.136 m behind the line
LEG = {"left": 0, "right": 6}    # the first joint of each leg (hip pitch; the knee is 3 further)


def one_leg(w, lifted):
    """Joint targets of the stance with one leg drawn up (None: both down)."""
    q = np.r_[w.robot.stance, w.robot.rest[12:]].copy()
    if lifted:
        q[LEG[lifted]], q[LEG[lifted] + 3] = -1.2, 1.9
    return q


def to_pose(w, A, q, steps):
    q0 = w.robot.arb.target().copy()
    for k in range(steps):
        if w.done:
            return
        f = min(1.0, (k + 1) / (steps * 0.75))
        act(w, A, "joints", np.r_[q0 + f * (q - q0), 0, 0])


def fly(w, A, vel, q, stop=True):
    """Injected flight: the robot gets `vel`, flies holding the joint targets q, and comes down."""
    if w.done:
        return
    kick_robot(w, vel)
    k = 0
    while not w.done and not w.ref.airborne() and k < 10:
        act(w, A, "joints", np.r_[q, 0, 0]); k += 1
    while not w.done and w.ref.airborne():
        act(w, A, "joints", np.r_[q, 0, 0])
    if stop and not w.done:
        w.d.qvel[w.robot.fv:w.robot.fv + 6] = 0.0


def at_board(w, A, lifted="left", x=BOARD):
    w.reset(); hold(w, A, 0.1); move_robot(w, x=x); hold(w, A, 0.5)
    to_pose(w, A, one_leg(w, lifted), 40)


def triple(w, A, v=((4.9, 0, 3.0), (4.9, 0, 3.0), (4.5, 0, 3.0)), hop_lifted="left", step_lifted="right", stance=5):
    """Hop from the right foot onto it, step onto the left, jump into the sand."""
    at_board(w, A, hop_lifted)
    fly(w, A, v[0], one_leg(w, hop_lifted))
    act(w, A, "joints", np.r_[one_leg(w, hop_lifted), 0, 0], stance)
    fly(w, A, v[1], one_leg(w, step_lifted))
    act(w, A, "joints", np.r_[one_leg(w, step_lifted), 0, 0], stance)
    fly(w, A, v[2], one_leg(w, step_lifted), stop=False)
    if not w.done:
        hold(w, A)


def main():
    w, A = make("triple-jump")
    p = w.task.p
    assert (p["runway_m"], p["board_to_pit_m"], p["pit_length_m"], p["pit_width_m"]) == (40.0, 7.0, 9.0, 2.75)
    hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)          # nop
    triple(w, A)                                                                              # positive (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["hop", "step", "jump", "landing"] and v["metrics"]["mark_m"] >= 7.0, v
    ev = {e["stage"]: e for e in w.ref.events if e["ev"] == "stage"}
    assert ev["hop"]["foot"] == "right" and ev["step"]["foot"] == "left", ev
    print("  injected hop, step and jump:", v["metrics"])
    sha = w.state_sha()
    triple(w, A)
    assert w.state_sha() == sha                                                               # determinism
    w.reset(); hold(w, A, 0.1); move_robot(w, x=-0.6)                    # walking over the line
    while not w.done:
        act(w, A, "walk", np.r_[0.5, 0, 0, w.robot.rest[12:], 0, 0])
    assert verdict(w)["failed"] == "a foot on or over the take-off line" and verdict(w)["stages"] == [], verdict(w)
    at_board(w, A, None); fly(w, A, (4.9, 0, 3.0), one_leg(w, None))     # a hop from both feet
    assert verdict(w)["failed"] == "the hop was taken off from both feet" and verdict(w)["stages"] == [], verdict(w)
    at_board(w, A, "left"); fly(w, A, (4.9, 0, 3.0), one_leg(w, None))   # from the right foot, down on both
    v = verdict(w)
    assert v["failed"] == "the hop did not land on the take-off foot on the runway" and v["stages"] == [], v
    triple(w, A, step_lifted="left")                                     # the "step" comes down on the right foot again
    v = verdict(w)
    assert v["failed"] == "the step did not land on the other foot on the runway" and v["stages"] == ["hop"], v
    at_board(w, A, "left")                                               # the "sleeping" left leg half down in the hop:
    half = one_leg(w, "left")                                            # the right foot lands first, the left touches next
    half[0], half[3], half[4] = -0.35, 0.75, -0.4
    fly(w, A, (4.9, 0, 3.0), half, stop=False); hold(w, A, 1.0)
    v = verdict(w)
    assert v["failed"] == "another part than the landing foot touched the ground before the step", v
    assert v["stages"] == ["hop"] and "left_foot" in w.ref.events[-1]["parts"], (v, w.ref.events[-1])
    triple(w, A, v=((4.9, 0, 3.0), (4.9, 0, 3.0), (1.0, 0, 2.0)))        # the jump comes down on the runway
    v = verdict(w)
    assert v["failed"] == "the jump did not come down in the sand" and v["stages"] == ["hop", "step"], v
    at_board(w, A, "left"); fly(w, A, (5.0, 0.0, 3.0), one_leg(w, "left"), stop=False)
    hold(w, A, 0.2); move_robot(w, x=-1.0, z=0.4); hold(w, A)            # a hop, then back behind the line: no step
    assert verdict(w)["failed"] == "another part than the landing foot touched the ground before the step", verdict(w)
    assert verdict(w)["stages"] == ["hop"], verdict(w)
    for n in (1, 2):                                                     # after the hop (the step): the landing foot
        at_board(w, A, "left")                                           # down again half a metre further on
        fly(w, A, (4.9, 0, 3.0), one_leg(w, "left"))
        act(w, A, "joints", np.r_[one_leg(w, "left"), 0, 0], 5)
        if n == 2:
            fly(w, A, (4.9, 0, 3.0), one_leg(w, "right"))
            act(w, A, "joints", np.r_[one_leg(w, "right"), 0, 0], 1)
        lifted = "left" if n == 1 else "right"
        assert w.task.trackers["anchor"] is not None, w.task.trackers
        move_robot(w, x=float(w.pelvis()[0]) + 0.5)
        act(w, A, "joints", np.r_[one_leg(w, lifted), 0, 0], 20)
        v = verdict(w)
        assert v["failed"] == f"the landing foot moved along the ground before the {('step', 'jump')[n - 1]}", v
        assert len(v["stages"]) == n and 0.45 < w.ref.events[-1]["moved_m"] < 0.60, (v, w.ref.events[-1])
    w.close()
    w, A = make("triple-jump", board_to_pit_m=1.0)                       # one long jump from the line into a nearer pit
    at_board(w, A, "left"); fly(w, A, (3.6, 0, 2.5), one_leg(w, "left"), stop=False)
    v = verdict(w)
    assert v["failed"] == "the hop did not land on the take-off foot on the runway" and v["stages"] == [], v
    assert w.ref.events[-1]["in_the_sand"], w.ref.events[-1]
    print("PASS triple-jump")


if __name__ == "__main__":
    main()
