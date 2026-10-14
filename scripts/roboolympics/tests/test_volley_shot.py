"""volley-shot (v2: the official goal 11 m away, a real cross from 20 m, a goalkeeper dummy): the referee says no to
standing still (the cross lands), to a ball that only rebounds from a leg held in its path (the v1 exploit), to a
contact with another part, to a carried ball, to a shot wide of the goal or at the dummy, to a second touch, to waiting
at the kicker and to a ball that goes in without a volley; yes to a ball struck in the air by a foot, faster than it
came, into the goal.

The positive is an INJECTION: no kicking controller exists for the H1-2. Real: the cross really flies 20 m in air and
comes down on the right foot of the standing robot, before it touches the ground; the struck ball really flies 11 m
past the dummy into the goal. Injected: where the robot stands (teleported 0.3 m forward at t = 0, so that its foot is
under the ball) and the ball's velocity at that contact (what a swinging foot would have given it)."""
import numpy as np

from rfo.testing import hold, make, move_robot, verdict

FAMILY = "volley-shot"
STAND = dict(x=0.30, y=-0.10)          # here the cross comes down on the standing robot's right foot
SHOT = (17.0, 3.5, 3.0)                # 17.6 m/s, to the left of the dummy


def play(w, A, vel=None, stand=STAND, after=None):
    """The robot stands at `stand`; at the first contact of the ball with it the ball's velocity is set to `vel` (None:
    left alone). after(w): called once when the strike has been judged (the stage "volley")."""
    move_robot(w, **stand)
    typ, row = A.hold(w)
    hit = False
    while not w.done:
        w.step(A.to_raw(typ, row, w))
        if w.done:
            break
        if vel is not None and not hit and w.task.trackers["strike"].phase >= 1:
            hit = True
            w.put("ball", w.pos("ball"), vel=vel)
        if after is not None and w.ref.has("volley"):
            after(w)
            after = None


def main():
    w, A = make(FAMILY)
    p, g, m = w.task.p, w.task.geometry(), w.m
    # the official setting as built
    assert g["goal_x"] == 11.0 and p["goal_width_m"] == 7.32 and p["goal_height_m"] == 2.44
    assert abs(m.geom("goal_postL").pos[1] - 3.72) < 1e-9 and abs(m.geom("goal_postL").size[0] - 0.06) < 1e-9
    assert abs(w.d.geom_xpos[m.geom("goal_bar").id][2] - 2.50) < 1e-6
    assert abs(m.geom("ball").size[0] - 0.11) < 1e-9 and abs(m.body("ball").mass[0] - 0.43) < 1e-9
    assert abs(np.hypot(g["launch"][0], g["launch"][1]) - p["cross_distance_m"]) < 0.01
    ball = m.geom("ball").id
    assert m.geom_contype[ball] == 0 and m.geom_conaffinity[ball] == 0      # the waiting ball cannot be touched

    hold(w, A)                                                             # nop: the cross lands in front of the robot
    v = verdict(w)
    assert v["failed"] == "the ball touched the ground before the strike" and v["stages"] == [], v
    assert m.geom_contype[ball] == 1
    land = [e for e in w.ref.events if e["ev"] == "fail"][0]["t"] - p["launch_time_s"]
    assert 1.9 < land < 2.3 and abs(w.pos("ball")[0] - 0.5) < 0.3 and abs(w.pos("ball")[1] + 0.3) < 0.3, (land, w.pos("ball"))

    w.reset(); play(w, A, SHOT)                                            # positive (injection, see the docstring)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["volley", "goal"], v
    ev = {e["stage"]: e for e in w.ref.events if e["ev"] == "stage"}
    assert ev["volley"]["parts"] == ["right_foot"] and ev["volley"]["speed_out"] > ev["volley"]["speed_in"] > 11.0, ev
    sha, t_ok, sp = w.state_sha(), w.t, (ev["volley"]["speed_in"], ev["volley"]["speed_out"])
    w.reset(); play(w, A, SHOT)
    assert w.state_sha() == sha                                            # the same run again: the same state

    # the v1 exploit: the leg only stands in the ball's path. Wherever the robot stands, the ball leaves a still leg
    # slower than it came (measured over a 5 cm grid of standing places: at most 0.94 of its speed, some of them
    # deflected towards the goal at 6 m/s)
    worst = 0.0
    for stand in (STAND, dict(x=0.30, y=-0.05), dict(x=0.25, y=-0.15), dict(x=0.30, y=0.05), dict(x=0.25, y=-0.50)):
        w.reset(); play(w, A, None, stand=stand)
        v = verdict(w)
        assert v["failed"] == "the ball was not struck: it left the foot slower than it came" and v["stages"] == [], (stand, v)
        worst = max(worst, v["metrics"]["speed_out_m_s"] / v["metrics"]["speed_in_m_s"])
    assert worst < 0.97, worst

    w.reset(); play(w, A, None, stand=dict(x=0.62, y=0.15))               # the cross hits the body
    v = verdict(w)
    assert v["failed"] == "the ball was touched by something other than a foot" and v["stages"] == [], v

    w2, A2 = make(FAMILY, strike_max_s=0.002)                              # below a real contact's time: a carry
    play(w2, A2, SHOT)
    assert verdict(w2)["failed"] == "the ball was carried", verdict(w2)

    w.reset(); play(w, A, (17.0, 7.5, 3.0))                                # struck wide of the post
    v = verdict(w)
    assert v["failed"] == "the ball crossed the goal line outside the goal" and v["stages"] == ["volley"], v

    seen = {"dummy": False}
    keeper = w.ref.geoms(names=["keeper"])

    w.reset(); move_robot(w, **STAND)                                      # struck straight at the dummy: saved
    typ, row = A.hold(w)
    hit = False
    while not w.done:
        w.step(A.to_raw(typ, row, w))
        if not hit and w.task.trackers["strike"].phase >= 1:
            hit = True
            w.put("ball", w.pos("ball"), vel=(17.0, 0.5, 3.0))
        seen["dummy"] |= w.ref.touching(w.task.ball, keeper)
    v = verdict(w)
    assert not v["success"] and v["stages"] == ["volley"] and seen["dummy"] and v["failed"] == "time", (v, seen)

    def again(w):                                                          # the ball put back onto the foot
        foot = w.d.site_xpos[w.robot.foot_site["right"]]
        w.launch("ball", foot + [0.20, 0.0, 0.35], (0.0, 0.0, -2.0))

    w.reset(); play(w, A, (3.0, 3.0, 12.0), after=again)                   # a second touch after a valid strike
    v = verdict(w)
    assert v["failed"] == "second touch of the ball" and v["stages"] == ["volley"], v

    w.reset(); move_robot(w, x=6.0, y=11.0); hold(w, A, 0.2)               # waiting at the kicker
    assert verdict(w)["failed"] == "too close to the ball before the cross", verdict(w)

    w.reset(); hold(w, A, p["launch_time_s"] + 0.1)                        # into the goal without a volley
    w.launch("ball", (8.0, 1.5, 1.0), (15.0, 0.0, 0.0)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "the ball crossed the goal line without a volley" and v["stages"] == [], v

    w.reset(); hold(w, A, 0.2); move_robot(w, z=0.30); hold(w, A, 0.5)     # on the ground
    assert verdict(w)["failed"] == "fell", verdict(w)
    print(f"injection: ball in at {sp[0]} m/s, out at {sp[1]} m/s, goal at t = {t_ok:.2f} s; a still leg returns at most "
          f"{worst:.2f} of the ball's speed")
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
