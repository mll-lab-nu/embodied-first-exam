"""pitch-target (v2, Official Baseball Rules): the referee calls a strike for a pitch through the zone and refuses
every cheap exit.

The positive is an INJECTION: no controller of the H1-2 throws a baseball 18.44 m (it needs at least 14 m/s on a high
arc; a straight-arm swing releases it at about half of that, see the family's report). What is real: the robot stands on the
mound with its feet on the pitcher's plate and opens the grip (the referee judges the feet at that release). What is
injected: at the release the ball is given 22 m/s at 9.5 degrees from 0.14 m in front of and above where the hand let it
go; its flight in air down to the plate (it arrives at 20 m/s) and the call are the simulator's. Negatives: do nothing
(the pitch timer); a release with no foot on the plate; a pitch that bounces; a ball high; a ball wide; the ball
touched after the release; a fall before the call. A lob at 14.5 m/s that drops through the zone is also a strike."""
import math

import rcb_rfo
from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "pitch-target"
BALL = "a ball: it crossed the plate outside the strike zone"


def main():
    inst = rcb_rfo.make_instance(FAMILY, 0)
    w, A = make(FAMILY)
    text = " ".join([w.task.sentence, w.task.rules, w.task.venue, w.task.difficulty] + w.task.deviations)
    assert all("{" + k + "}" in text for k in w.task.p), [k for k in w.task.p if "{" + k + "}" not in text]
    assert inst["robot"] == "unitree_h1" and inst["rulebook"] and len(inst["deviations"]) >= 4
    p, g = w.task.p, w.task.geometry()
    assert p["plate_distance_m"] == 18.44 and p["mound_height_m"] == 0.254 and abs(g["zone_x"] - 18.008) < 1e-9
    rest = A.current("stand", w)
    free = rest.copy()
    free[-1] = 0.0

    def pitch(speed=22.0, elev=9.5, yaw=math.radians(0.55), move=None):
        """A real release on the plate; then (the injection) the ball is given a velocity."""
        w.reset()
        act(w, A, "stand", rest, 20)
        if move is not None:
            move_robot(w, **move)
            act(w, A, "stand", rest, 2)
        act(w, A, "stand", free)
        if speed is not None and not w.done:
            e = math.radians(elev)
            w.put("ball", w.pos("ball") + [0.1, 0.0, 0.1],
                  vel=(speed * math.cos(e) * math.cos(yaw), speed * math.cos(e) * math.sin(yaw), speed * math.sin(e)))

    def run(seconds=None):
        hold(w, A, seconds, grips=[0, 0])
        return verdict(w)

    pitch(); v = run(); sha = w.state_sha()                                 # the positive
    assert v["success"] and v["stages"] == ["release", "strike"], v
    assert abs(v["metrics"]["cross_y_m"]) <= 0.216 and 0.46 <= v["metrics"]["cross_z_m"] <= 1.07, v
    assert 19.0 < v["metrics"]["cross_speed_m_s"] < 21.0, v                 # the air took a tenth of its speed
    assert sorted(w.ref.events[1]["pivot_foot"]) == ["left", "right"], w.ref.events
    pitch(); run()
    assert w.state_sha() == sha, "the positive is not deterministic"
    pitch(14.5, 29.0); v = run()                                            # a lob that drops through the zone
    assert v["success"], v

    w.reset(); hold(w, A); v = verdict(w)                                   # nop: the pitch timer
    assert v["failed"] == "the ball was not delivered within the pitch timer" and v["stages"] == [], v

    pitch(move=dict(x=-0.50)); v = run()                                    # let go from behind the plate (injection:
    assert v["failed"] == "no foot was on the pitcher's plate at the release", v      # the robot is moved back)
    pitch(move=dict(x=0.25, z=1.26)); v = run()                             # ... and from in front of it, down the mound
    assert v["failed"] == "no foot was on the pitcher's plate at the release", v

    pitch(12.0, 5.0); v = run()                                             # it bounces before the plate
    assert v["failed"] == "the ball touched the ground before home plate", v
    pitch(22.0, 13.0); v = run()                                            # high
    assert v["failed"] == BALL and v["metrics"]["cross_z_m"] > 1.07, v
    pitch(22.0, 9.5, yaw=math.radians(2.0)); v = run()                      # wide
    assert v["failed"] == BALL and abs(v["metrics"]["cross_y_m"]) > 0.216, v

    pitch(speed=None)                                                       # it comes down on the robot (injection)
    x, y, z = w.pelvis()[:3]
    w.put("ball", (x + 0.03, y, z + 1.2))
    v = run(2.0)
    assert v["failed"] == "the ball was touched after the release", v

    pitch(14.5, 29.0); move_robot(w, z=0.70)                                # a fall while the ball is in the air
    v = run()                                                               # (injection: the robot is dropped)
    assert v["failed"] == "fell" and v["stages"] == ["release"], v
    print("PASS pitch-target")


if __name__ == "__main__":
    main()
