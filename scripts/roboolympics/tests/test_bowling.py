"""bowling (v2, USBC): the referee says yes to a strike and no to every cheap exit.

The positive is an INJECTION: no controller of the H1-2 bowls a strike (the pocket is 3 cm wide after 18 m, and a
straight-arm swing releases the 6 lb ball at about 3 m/s, see the family's report). What is real: the robot stands on
the approach behind the foul line and opens the grip. What is injected: the ball is then laid on the lane 0.35 m beyond
the foul line (RoboOlympics' lay-down point), rolling at 8 m/s on a line 1.2 degrees across the lane into the pocket;
its roll over the oil and the dry boards (it arrives at 7.3 m/s), the pin action and the count are the simulator's.
Negatives: do nothing; walking over the foul line with the ball; a gutter ball; a hit on the head pin that leaves pins
standing; the ball touched after the release; a foul after the delivery; a fall before the count."""
import math

import numpy as np

import rcb_rfo
from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "bowling"
FOUL = "foul: touched the lane on or beyond the foul line"


def main():
    inst = rcb_rfo.make_instance(FAMILY, 0)
    w, A = make(FAMILY)
    T = w.task
    text = " ".join([T.sentence, T.rules, T.venue, T.difficulty] + T.deviations)
    assert all("{" + k + "}" in text for k in T.p), [k for k in T.p if "{" + k + "}" not in text]
    assert inst["robot"] == "unitree_h1" and inst["rulebook"] and len(inst["deviations"]) >= 4
    p = T.p
    H, R = w.d.xpos[T.pin_ids[0]][2], p["ball_diameter_m"] / 2
    for b in T.pin_ids:                                                     # USBC: 1.53 kg, the centre of gravity
        assert abs(w.m.body_mass[b] - 1.53) < 1e-9 and abs(w.m.body_ipos[b][2] - 0.147) < 1e-9      # 5 13/16 in up
    assert abs(w.m.body_subtreemass[w.m.body("ball").id] - 2.72) < 1e-9
    spots = T.pin_spots()
    assert len(spots) == 10 and abs(spots[0][0] - 18.288) < 1e-9 and abs(spots[6][1] - 0.4572) < 1e-9
    rest = A.current("stand", w)
    free = rest.copy()
    free[-1] = 0.0

    def roll(y_entry=-0.04, angle_deg=1.2, speed=8.0):
        """A real release behind the line; then (the injection) the ball is laid on the lane, rolling."""
        w.reset()
        act(w, A, "stand", rest, 5)
        act(w, A, "stand", free)
        a, x0 = math.radians(angle_deg), 0.35
        y0 = y_entry - math.tan(a) * (p["lane_length_m"] - x0)
        w.put("ball", (x0, y0, H + R), vel=(speed * math.cos(a), speed * math.sin(a), 0.0),
              angvel=(-speed / R * math.sin(a), speed / R * math.cos(a), 0.0))

    def run(seconds=None):
        hold(w, A, seconds, grips=[0, 0])
        return verdict(w)

    assert sum(T.pins_down(w)) == 0
    roll(); v = run(); sha = w.state_sha()                                  # the positive: a strike
    assert v["success"] and v["stages"] == ["delivery", "pins", "strike"] and v["metrics"]["pins_down"] == 10, v
    assert 6.5 < v["metrics"]["entry_speed_m_s"] < 8.0 and abs(v["metrics"]["entry_angle_deg"] - 1.2) < 0.6, v
    roll(); run()
    assert w.state_sha() == sha, "the positive is not deterministic"

    w.reset(); hold(w, A); v = verdict(w)                                   # nop: the pins stay up
    assert v["failed"] == "time" and v["stages"] == [] and v["metrics"]["pins_down"] == 0, v

    w.reset()                                                               # walking over the foul line with the ball
    while not w.done:
        act(w, A, "walk", np.r_[0.6, 0.0, 0.0, rest])
    assert verdict(w)["failed"] == FOUL, (verdict(w), w.pelvis())

    roll(y_entry=0.90, angle_deg=3.0); v = run()                            # into the gutter half-way down the lane
    assert v["failed"] == "a gutter ball" and v["stages"] == ["delivery"], v

    roll(y_entry=0.0, angle_deg=1.2); v = run()                             # full on the head pin: pins left standing
    assert v["failed"] == "not a strike" and 0 < v["metrics"]["pins_down"] < 10 and v["stages"] == ["delivery", "pins"], v

    w.reset(); act(w, A, "stand", rest, 5); act(w, A, "stand", free)       # it comes down on the robot (injection)
    x, y, z = w.pelvis()[:3]
    w.put("ball", (x + 0.03, y, z + 1.2))
    v = run(2.0)
    assert v["failed"] == "the ball was touched after the release", v

    roll(); run(1.0); move_robot(w, x=0.5); v = run()                       # over the line after the delivery
    assert v["failed"] == FOUL and v["stages"] == ["delivery"], v           # (injection: the robot is moved there)

    roll(); run(1.0); move_robot(w, z=0.45); v = run()                      # a fall before the count (injection)
    assert v["failed"] == "fell", v
    print("PASS bowling")


if __name__ == "__main__":
    main()
