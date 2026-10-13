"""trap-ball (v2: a ground pass from 15 m at 8 m/s, half a metre to the side; first touch a foot, the ball at rest within
1 m inside 3 s): the referee says no to standing still (the pass goes by), to a ball that bounces off a planted foot
(the passive case), to a first touch with another part, to a handball, to a ball brought to rest too far away and to
waiting at the passer; yes to a ball taken with a foot and dead within a metre in time.

The positive is an INJECTION: no trapping controller exists for the H1-2. Real: the pass really rolls 15 m and arrives
at 6 m/s at the right foot of the standing robot. Injected: where the robot stands (teleported 0.34 m to the right at
t = 0, so that its right foot is in the ball's path) and the ball's velocity as it comes off the foot (0.3 m/s: what a
cushioning foot would have left it)."""
import numpy as np

from rfo.testing import hold, make, move_robot, verdict

FAMILY = "trap-ball"
FOOT_Y = 0.163                        # the H1-2's foot is this far beside its pelvis


def play(w, A, vel=None, y=None):
    """The robot stands with its right foot in the ball's path; when the ball comes off the foot after the first touch
    its velocity is set to `vel` (None: left alone)."""
    p = w.task.p
    move_robot(w, y=-p["pass_side_m"] + FOOT_Y if y is None else y)
    typ, row = A.hold(w)
    hit = False
    while not w.done:
        w.step(A.to_raw(typ, row, w))
        if w.done:
            break
        if vel is not None and not hit and w.task.trackers["touch_t"] is not None and not w.task.trackers["on"]:
            hit = True
            w.put("ball", w.pos("ball"), vel=vel)


def main():
    w, A = make(FAMILY)
    p, g, m = w.task.p, w.task.geometry(), w.m
    assert g["launch"][0] == 15.0 and g["vel"][0] == -8.0 and g["launch"][1] == -0.5
    assert abs(m.geom("ball").size[0] - 0.11) < 1e-9 and abs(m.body("ball").mass[0] - 0.43) < 1e-9
    ball = m.geom("ball").id
    assert m.geom_contype[ball] == 0 and m.geom_conaffinity[ball] == 0      # the waiting ball cannot be touched

    typ, row = A.hold(w)                                                   # nop: the pass goes by on the right
    passed = None
    while not w.done:
        w.step(A.to_raw(typ, row, w))
        if passed is None and w.pos("ball")[0] <= 0.0:
            passed = (w.t - p["launch_time_s"], float(np.linalg.norm(w.vel("ball"))), float(w.pos("ball")[1]))
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [] and v["metrics"]["touches"] == 0, v
    assert 2.0 < passed[0] < 2.3 and 5.8 < passed[1] < 6.3 and abs(passed[2] + 0.5) < 0.02, passed   # as the venue says

    w.reset(); play(w, A, (0.3, 0.0, 0.0))                                 # positive (injection, see the docstring)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["first touch", "control"], v
    ev = {e["stage"]: e for e in w.ref.events if e["ev"] == "stage"}
    assert ev["first touch"]["parts"] == ["right_foot"], ev
    assert v["metrics"]["ball_from_pelvis_m"] <= p["control_m"] and v["metrics"]["control_after_s"] <= p["control_s"], v
    sha, t_ok, after = w.state_sha(), w.t, v["metrics"]["control_after_s"]
    w.reset(); play(w, A, (0.3, 0.0, 0.0))
    assert w.state_sha() == sha                                            # the same run again: the same state

    w.reset(); play(w, A, None)                                            # the passive case: a planted foot
    v = verdict(w)
    assert v["failed"] == "the ball was not under control in time" and v["stages"] == ["first touch"], v
    bounce = v["metrics"]["ball_from_pelvis_m"]
    assert bounce > 3.0, v                                                 # it bounced metres away

    w.reset(); play(w, A, (2.0, 0.0, 0.0))                                 # slowed, but it rolls away out of the metre
    v = verdict(w)
    assert v["failed"] == "the ball was not under control in time" and v["metrics"]["ball_from_pelvis_m"] > p["control_m"], v

    after_launch = p["launch_time_s"] + 0.1
    w.reset(); hold(w, A, after_launch)                                    # first touch with the shin (injected ball)
    knee = w.pos("right_knee_link")
    w.launch("ball", knee + [0.6, 0.0, -0.12], (-4.0, 0.0, 0.0)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "the first touch was not with a foot" and v["stages"] == [], v
    assert "right_shin" in w.ref.events[-1]["parts"], w.ref.events[-1]

    w.reset(); hold(w, A, after_launch)                                    # handball (injected ball)
    palm = w.d.site_xpos[w.robot.palm["right"]].copy()
    w.launch("ball", palm + [0.0, 0.0, 0.30], (0.0, 0.0, -2.0)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "handball" and "right_hand" in w.ref.events[-1]["parts"], (v, w.ref.events[-1])

    w.reset(); move_robot(w, x=7.0); hold(w, A, 0.2)                       # waiting at the passer
    assert verdict(w)["failed"] == "too close to the ball before the pass", verdict(w)

    w.reset(); hold(w, A, 0.2); move_robot(w, z=0.30); hold(w, A, 0.5)     # on the ground
    assert verdict(w)["failed"] == "fell", verdict(w)
    print(f"the pass arrives {passed[0]:.2f} s after it is played at {passed[1]:.2f} m/s; injection: under control "
          f"{after:.2f} s after the touch (t = {t_ok:.2f} s); off a planted foot the ball is {bounce:.1f} m away after 3 s")
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
