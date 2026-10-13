"""vault (the H1-2 at the FIG men's vault table): the referee says no to standing still, to walking round the table,
to walking into it, to standing on it, to a jump over it without a hand on it, to a vault whose feet catch the table,
to one that comes down on the hands, to a feet-first landing that falls, to a landing beside the mat. The springboard
is shown to be a spring: the robot dropped on its high end presses it down 3 cm or more and it comes back.

The positive is an INJECTION (no controller of this robot vaults: it has no running policy and its best open-loop
squat jump found here lifts its centre of mass 0.16 m): the robot raises its arms overhead on the run-up (a real
`joints` action), is set 1 cm above the springboard (rfo.testing.move_robot) and given the velocity of a handspring
(kick_robot: 3.5 m/s forward, 5.3 m/s up, 6.15 rad/s of forward rotation). It then really flies up over the table
turning forward, both hands (and nothing else) really meet the table's top while it is upside down above it (the
contact slows its rotation), its pelvis passes the far edge 1 m above the top, and its feet come down first on the mat;
at that touch-down the test removes its velocity (a ghost: the `stand` action does not absorb a landing from 2.5 m with
6 rad/s of rotation) and the platform's stance stands on the mat."""
import numpy as np

from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

NOT_HANDS = "touched the table with something other than the hands"
NOT_OVER = "did not pass over the table"


def arms_up(w):
    r = w.robot
    q = np.r_[r.stance, r.rest[12:]].copy()
    q[13] = q[20] = -3.1                    # shoulder pitch: the arms straight up
    q[14], q[21] = 0.6, -0.6                # shoulder roll: the hands a shoulder's width apart
    q[16] = q[23] = 1.57                    # elbows straight
    return q


def over_board(w, x0):
    """The pelvis height that puts the standing robot's soles 1 cm above the springboard at x0."""
    g = w.task.geo
    return w.robot.stand_z + 0.05 + (x0 + 0.16 - g["board_x"][0]) * np.tan(g["board_angle_rad"])


def jump(w, A, x0, vx, vz, seconds=1.2):
    """An upright ghost jump from 1 cm above the springboard."""
    w.reset(); hold(w, A, 0.2)
    move_robot(w, x=x0, z=over_board(w, x0))
    kick_robot(w, vel=(vx, 0.0, vz))
    hold(w, A, seconds)


def handspring(w, A, vx=3.5, vz=5.3, wy=6.15, ghost=True, aside_after_table=None, seconds=6.0):
    r = w.robot
    up = r.rest[12:]
    w.reset(); move_robot(w, x=21.0)
    act(w, A, "joints", np.r_[arms_up(w), 0, 0], 80)
    x0 = 25.45 - vx * 0.52                  # the hands are over the table's first half at the top of the flight
    move_robot(w, x=x0, z=over_board(w, x0))
    kick_robot(w, vel=(vx, 0.0, vz), angvel=(0.0, wy, 0.0))
    landed = moved = False
    t0 = w.t
    while not w.done and w.t - t0 < seconds:
        if landed:
            act(w, A, "stand", np.r_[up, 0, 0])
        else:
            hold(w, A, 0.01)
        if aside_after_table is not None and not moved and w.ref.has("over the table"):
            move_robot(w, y=aside_after_table)
            moved = True
        if not landed and w.ref.has("landing"):
            landed = True
            if ghost:
                w.d.qvel[r.fv:r.fv + 6] = 0.0


def start_at(w, A, x, y=0.0, z=None):
    w.reset(); hold(w, A, 0.2); move_robot(w, x=x, y=y, z=z); hold(w, A, 0.1)


def main():
    w, A = make("vault")
    p, g, r = w.task.p, w.task.geo, w.robot
    up = r.rest[12:]
    assert w.robot_name == "unitree_h1" and g["table_x"] == (25.0, 26.2) and g["table_top"] == 1.35
    assert g["mat_x"] == (26.2, 32.2) and g["board_x"] == (23.3, 24.5) and abs(w.task.board_height(w) - 0.22) < 0.001
    hold(w, A)
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [] and abs(w.pelvis()[0]) < 0.1, v        # nop (stands 80 s)
    rest = w.task.board_height(w)
    assert abs(rest - 0.22) < 0.003, rest                                                     # (20 kg on the spring)

    handspring(w, A)                                                                          # positive (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["hands on the table", "over the table", "landing", "stand"], v
    ev = {e["stage"]: e for e in w.ref.events if e["ev"] == "stage"}
    assert ev["hands on the table"]["hands"] == ["left_hand", "right_hand"], ev
    assert ev["over the table"]["pelvis_z"] > p["table_height_m"] + 0.5, ev
    assert g["mat_x"][0] + 0.5 < w.pelvis()[0] < g["mat_x"][1] and abs(w.pelvis()[1]) < 0.5, w.pelvis()
    sha = w.state_sha()
    handspring(w, A)
    assert w.state_sha() == sha                                                               # deterministic

    w.reset(); hold(w, A, 0.2)                                                                # the springboard: the
    board = w.ref.geoms(names=["springboard"])                                                # robot dropped 0.3 m on
    move_robot(w, x=g["board_x"][1] - 0.25, z=r.stand_z + rest + 0.30); w.d.qvel[:] = 0.0     # its high end
    low, on = rest, False
    for _ in range(60):
        hold(w, A, 0.01)
        low = min(low, w.task.board_height(w))
        on = on or w.ref.parts_touching(board) == {"left_foot", "right_foot"}
    assert on and rest - 0.10 < low < rest - 0.03 and w.task.board_height(w) > low + 0.02, (rest, low)
    move_robot(w, x=20.0, z=r.stand_z + 0.02); hold(w, A, 0.5)
    assert abs(w.task.board_height(w) - rest) < 0.002 and not w.done, w.task.board_height(w)  # it comes back
    print(f"  springboard: high end at {rest:.3f} m, pressed down to {low:.3f} m by the robot dropped from 0.3 m")

    start_at(w, A, 24.4, y=1.2)                                                               # walking round the table
    while not w.done and w.t < 6.0:
        act(w, A, "walk", np.r_[0.8, 0, 0, up, 0, 0])
    v, e = verdict(w), w.ref.events[-1]
    assert v["failed"] == NOT_OVER and abs(e["pelvis"][1]) > g["table_half_width"] and v["stages"] == [], (v, e)

    start_at(w, A, 24.75)                                                                     # walking into it
    while not w.done and w.t < 8.0:
        act(w, A, "walk", np.r_[0.8, 0, 0, up, 0, 0])
    v, e = verdict(w), w.ref.events[-1]                                                       # (a forearm meets its
    assert v["failed"] == NOT_HANDS and v["stages"] == [] and e["parts"][0].endswith("_forearm"), (v, e)   # side)

    w.reset(); hold(w, A, 0.2)                                                                # set standing on it
    move_robot(w, x=25.4, z=r.stand_z + p["table_height_m"] + 0.002); hold(w, A, 0.3)
    v, e = verdict(w), w.ref.events[-1]
    assert v["failed"] == NOT_HANDS and set(e["parts"]) <= {"left_foot", "right_foot"}, (v, e)

    jump(w, A, 23.5, 4.0, 6.2)                                                                # a jump clean over
    v = verdict(w)                                                                            # it, no hand on it
    assert v["failed"] == "passed the table without a hand on it" and v["stages"] == [], v

    jump(w, A, 24.2, 3.0, 4.6)                                                                # a jump too low: the
    v, e = verdict(w), w.ref.events[-1]                                                       # feet catch the table
    assert v["failed"] == NOT_HANDS and v["stages"] == [] and set(e["parts"]) <= {"left_foot", "right_foot"}, (v, e)

    handspring(w, A, vz=5.4, wy=7.0)                                                          # over-rotated: down on
    v, e = verdict(w), w.ref.events[-1]                                                       # the hands
    assert v["failed"] == "did not land on the feet" and v["stages"] == ["hands on the table", "over the table"], (v, e)
    assert not set(e["parts"]) & {"left_foot", "right_foot"}, e

    handspring(w, A, ghost=False)                                                             # feet first, but the
    v, e = verdict(w), w.ref.events[-1]                                                       # landing is not held
    assert v["failed"] == "did not land on the feet" and v["stages"][-1] == "landing", (v, e)

    handspring(w, A, aside_after_table=2.2)                                                   # comes down beside the
    v = verdict(w)                                                                            # mat (moved in the air)
    assert v["failed"] == "landed off the mat" and v["stages"] == ["hands on the table", "over the table"], v
    print("PASS vault")


if __name__ == "__main__":
    main()
