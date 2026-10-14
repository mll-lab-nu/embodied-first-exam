"""balance-board (a rigid 0.76 m x 0.38 m deck loose on a free roller of 0.085 m radius): the referee says no to
standing still (the board runs out from under the robot in under 3 s), to the walking policy, to resting a deck end
on the floor, to stepping off, to lying on the deck, to leaving the board, to balancing for 20 s and then no more.

Two positives. (a) An INJECTION: while the robot holds its stance, the test pushes its torso sideways with a force
(w.d.xfrc_applied, a spring-damper of 3000 N/m and 300 N s/m on the distance between the robot's centre of mass and
the roller, at most 300 N) that keeps the centre of mass over the roller: a helper's hand. Deck and roller are free
bodies in real contact the whole time: the robot really stands on the deck for 30 s and no deck end touches the floor.
A sideways shove (60 N for 0.2 s) in one run shows that the deck really tilts and the roller really rolls.
(b) A REAL ride through the action interface (`joints` rows, no force): a linear feedback from the board's state to
the legs' sideways sway (gains from a least-squares model of simulated rides and a discrete LQR, one gain raised by
hand) rides the full 30 s from the task's own start with the deck within 2 degrees. It is not shipped as the
reference solution: started 1 mm off the equilibrium it falls after 14 to 28 s (a slowly growing oscillation)."""
import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict

PRONE = [np.cos(np.pi / 4), 0.0, np.sin(np.pi / 4), 0.0]


def helped(w, A, until=None, push=0.0, lean=0.0, kp=3000.0, kd=300.0):
    r, prev = w.robot, None
    roller_y = []
    while not w.done and (until is None or w.t < until):
        b = w.task.board(w)
        e = float(w.com()[1]) - b["roller_y"] - lean * min(1.0, w.t)
        ev = 0.0 if prev is None else (e - prev) / w.CONTROL_DT
        prev = e
        w.d.xfrc_applied[r.torso, :] = 0.0
        w.d.xfrc_applied[r.torso, 1] = float(np.clip(-kp * e - kd * ev, -300, 300)) + (push if 5.0 <= w.t < 5.2 else 0.0)
        hold(w, A, 0.01)
        roller_y.append(b["roller_y"])
    w.d.xfrc_applied[r.torso, :] = 0.0
    return np.array(roller_y)


# tilt (rad), roller y (m), com y - roller y (m), tilt rate, roller speed, rate of (com - roller), hip-roll sway (rad),
# its rate, the last command (rad)
GAIN = np.array([1.2989, -9.7131, -75.0, -0.0214, 0.9019, -0.918, -4.8028, -0.1319, 3.8755])


def ride(w, A, gain=GAIN):
    """The legs sway the body sideways (both hip rolls +b, both ankle rolls -b: the feet stay flat on the deck)."""
    r, dt = w.robot, w.CONTROL_DT
    stance = np.r_[r.stance, r.rest[12:]]
    prev, b = None, 0.0
    while not w.done:
        bd = w.task.board(w)
        e = float(w.com()[1]) - bd["roller_y"]
        ev = 0.0 if prev is None else (e - prev) / dt
        prev = e
        q, dq = w.d.qpos[r.qadr], w.d.qvel[r.vadr]
        x = np.array([bd["tilt_rad"], bd["roller_y"], e, bd["tilt_rate_rad_s"], bd["roller_vy"], ev,
                      0.5 * (q[1] + q[7]), 0.5 * (dq[1] + dq[7]), b])
        b = float(np.clip(-gain @ x, -0.25, 0.25))
        row = stance.copy()
        row[[1, 7]] += b
        row[[5, 11]] -= b
        act(w, A, "joints", np.r_[row, 0, 0])


def main():
    w, A = make("balance-board")
    p, m = w.task.p, w.m
    assert (p["deck_length_m"], p["deck_width_m"], p["roller_radius_m"], p["duration_s"]) == (0.76, 0.38, 0.085, 30.0)
    assert {"deck", "roller"} <= set(w.free) and not np.any(m.jnt_stiffness) and m.neq == 0   # free bodies, no spring,
    b = w.task.board(w)                                                                       # nothing welded
    assert b["tilt_rad"] == 0.0 and b["roller_under_deck_m"] == 0.0 and abs(w.com()[1] - b["roller_y"]) < 1e-3
    hold(w, A)                                                               # nop: the stance does not balance it
    v = verdict(w)
    assert v["failed"] == "the deck touched the floor" and v["stages"] == [] and 1.0 < w.t < 5.0, (v, w.t)

    w.reset(); helped(w, A)                                                  # positive (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["10 s", "20 s", "30 s"] and v["metrics"]["max_tilt_deg"] < 1.0, v
    sha = w.state_sha()
    w.reset(); helped(w, A)
    assert w.state_sha() == sha                                              # the same run again: the same state
    w.reset(); ry = helped(w, A, push=60.0)                                  # shoved at 5 s: the deck tilts, the
    v = verdict(w)                                                           # roller rolls, the helper recovers
    assert v["success"] and v["metrics"]["max_tilt_deg"] > 1.0 and np.ptp(ry) > 0.005, (v, np.ptp(ry))

    w.reset(); ride(w, A)                                                    # positive (b): a real ride
    v = verdict(w)
    assert v["success"] and v["metrics"]["max_tilt_deg"] < 5.0, v

    w.reset()                                                                # the walking policy does not balance it
    while not w.done:
        act(w, A, "walk", np.r_[0, 0, 0, w.robot.rest[12:], 0, 0])
    assert verdict(w)["failed"] == "the deck touched the floor" and w.t < 5.0, (verdict(w), w.t)
    w.reset(); helped(w, A, lean=0.12)                                       # the weight over one end: the deck
    v = verdict(w)                                                           # comes down on it
    assert v["failed"] == "the deck touched the floor" and "30 s" not in v["stages"], v
    w.reset(); helped(w, A, until=20.5); hold(w, A)                          # balanced for 20 s, then left alone
    v = verdict(w)
    assert v["failed"] == "the deck touched the floor" and v["stages"] == ["10 s", "20 s"] and w.t < 26.0, (v, w.t)
    w.reset(); hold(w, A, 0.2); move_robot(w, y=1.2); hold(w, A, 1.0)        # stepping off (teleported beside it)
    assert verdict(w)["failed"] == "touched the floor", verdict(w)
    w.reset(); hold(w, A, 0.2)                                               # held in the air above the board
    while not w.done:
        move_robot(w, z=2.0); w.d.qvel[w.robot.fv:w.robot.fv + 6] = 0.0; hold(w, A, 0.01)
    assert verdict(w)["failed"] == "left the board" and 1.0 < w.t < 1.5, (verdict(w), w.t)
    w.reset(); hold(w, A, 0.1)                                               # lying on the deck
    move_robot(w, x=-0.25, z=0.188 + 0.20)
    w.d.qpos[w.robot.fq + 3:w.robot.fq + 7] = PRONE
    hold(w, A, 2.0)
    assert verdict(w)["failed"] in ("fell on the board", "touched the floor", "the deck touched the floor"), verdict(w)
    assert any(e.get("reason") for e in w.ref.events)
    print("PASS balance-board")


if __name__ == "__main__":
    main()
