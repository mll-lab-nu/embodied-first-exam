"""volleyball-set (v2: the setter at the net of the official court; a pass from the back court, one overhead contact of
the hands, at least 1 m above the 2.43 m net, into the outside hitter's 2 m target at position 4): the referee says no
to standing still (the pass lands), to a ball that only rebounds from raised fists (the v1 exploit), to a touch before
the ball's highest point, to a setter who left the front zone (the v1 walk to the launcher), to a contact that is not
overhead or not with the hands, to a set that leaves downward, stays too low or misses the target, to a held ball, to
a second touch, to touching the net and to a foot beyond the centre line; yes to one overhead contact that sends the
ball on faster than it came, over a metre above the net and into the target.

The positive is an INJECTION (the reference controller, oracles/volleyball-set, sets for real; this test does not
depend on it). Real: the pass really flies from the back
court and comes down on the fists of the robot, which really holds its arms up above its head (stand mode, where it
started); the set ball really rises above 3.43 m and lands in the target 5 m along the net. Injected: the ball's
velocity at that contact (what hands driven up through the ball would have given it; the ball is also moved 3 cm
along that velocity, out of the fists)."""
import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "volleyball-set"
UP = np.r_[0.0, [-2.7, 0.2, 0.0, 1.2, 0.0, 0.0, 0.0], [-2.7, -0.2, 0.0, 1.2, 0.0, 0.0, 0.0]]   # fists above the forehead
SET = (3.0, -0.25, 6.8)                # 7.4 m/s, up to about 4.5 m and 4.7 m along the net


def play(w, A, vel=None, pose=UP, stand=None, after=None, early=None, shift=None):
    """Arms to `pose` (1.5 s, stand mode); at the first contact of the ball with the robot the ball's velocity is set
    to `vel` (None: left alone). after(w): called once, 0.25 s after the set was judged. early(w): called once, 0.1 s
    after the toss."""
    if stand:
        move_robot(w, **stand)
    rest = w.robot.rest[12:].copy()
    i, hit, t_set = 0, False, None
    while not w.done:
        i += 1
        act(w, A, "stand", np.r_[rest + min(1.0, i * w.CONTROL_DT / 1.5) * (pose - rest), 0, 0])
        if w.done:
            break
        st = w.task.trackers["strike"]
        if early is not None and w.t >= w.task.p["launch_time_s"] + 0.1:
            early(w)
            early = None
        if vel is not None and not hit and st.phase >= 1:
            hit = True
            n = np.asarray(vel) / np.linalg.norm(vel)
            w.put("ball", w.pos("ball") + (0.03 * n if shift is None else np.asarray(shift)), vel=vel)
        if after is not None and w.ref.has("set"):
            t_set = w.t if t_set is None else t_set
            if w.t - t_set >= 0.25:
                after(w)
                after = None


def main():
    w, A = make(FAMILY)
    p, g, m = w.task.p, w.task.geometry(), w.m
    # the official court as built: the net 1 m to the robot's right, its top at 2.43 m; the attack line 3 m from it
    mesh = m.geom("net_mesh")
    assert abs(w.d.geom_xpos[mesh.id][2] + mesh.size[2] - 2.43) < 1e-6 and abs(w.d.geom_xpos[mesh.id][1] + 1.0) < 1e-6
    assert abs(w.d.geom_xpos[m.geom("attack_line-1").id][1] - (2.0 - 0.025)) < 1e-6, w.d.geom_xpos[m.geom("attack_line-1").id]
    assert g["target"] == (5.0, 0.0) and abs(m.geom("ball").size[0] - 0.105) < 1e-9 and abs(m.body("ball").mass[0] - 0.27) < 1e-9
    assert g["launch"][1] - g["centre"][1] > p["attack_line_m"]             # the pass comes from the back court
    assert abs(w.task.head_top(w) - 1.795) < 0.03
    ball = m.geom("ball").id
    assert m.geom_contype[ball] == 0 and m.geom_conaffinity[ball] == 0      # the waiting ball cannot be touched

    typ, row = A.hold(w)                                                   # nop: the pass comes down in front of the head
    apex = 0.0
    while not w.done:
        w.step(A.to_raw(typ, row, w))
        apex = max(apex, float(w.pos("ball")[2]))
    v = verdict(w)
    assert v["failed"] == "the ball touched the floor before the set" and v["stages"] == [] and 3.6 < apex < 4.0, (v, apex)

    w.reset(); play(w, A, SET)                                             # positive (injection, see the docstring)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["set", "above the net", "in the target"], v
    ev = {e["stage"]: e for e in w.ref.events if e["ev"] == "stage"}
    assert set(ev["set"]["parts"]) <= {"left_hand", "right_hand"} and ev["set"]["speed_out"] >= ev["set"]["speed_in"], ev
    assert v["metrics"]["set_apex_m"] >= p["net_height_m"] + p["rise_above_net_m"], v
    sha, t_ok, s_in, s_out = w.state_sha(), w.t, ev["set"]["speed_in"], ev["set"]["speed_out"]
    off, top = v["metrics"]["from_target_centre_m"], v["metrics"]["set_apex_m"]
    w.reset(); play(w, A, SET)
    assert w.state_sha() == sha                                            # the same run again: the same state

    w.reset(); play(w, A, None)                                            # the v1 exploit: the ball only rebounds from
    v = verdict(w)                                                         # raised fists (real, nothing injected)
    assert v["failed"] == "the ball was not set: it left the hands downward or slower than it came" and v["stages"] == [], v
    passive = v["metrics"]["speed_out_m_s"] / v["metrics"]["speed_in_m_s"]
    assert passive < 0.85, v

    def rising(w):                                                         # the ball sent up into the fists from in front
        w.put("ball", w.d.site_xpos[w.robot.palm["left"]] + [0.35, 0.03, -0.25], vel=(-3.0, 0.0, 2.5))

    w.reset(); play(w, A, None, early=rising)                              # touched before its highest point
    v = verdict(w)
    assert v["failed"] == "the ball was touched before it had passed its highest point" and v["stages"] == [], v

    w.reset(); move_robot(w, y=g["centre"][1] + p["attack_line_m"] + 0.3); hold(w, A, 0.2)   # the walk to the launcher
    assert verdict(w)["failed"] == "the setter left the front zone before the set", verdict(w)

    w.reset(); hold(w, A, p["launch_time_s"] + 1.0)                        # onto a hand of arms at rest: not overhead
    w.put("ball", w.d.site_xpos[w.robot.palm["right"]] + [0.0, 0.0, 0.40], vel=(0.0, 0.0, -1.0)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "the ball was not played overhead" and v["stages"] == [], v

    w.reset(); hold(w, A, p["launch_time_s"] + 1.0)                        # onto a forearm
    w.put("ball", w.pos("right_elbow_roll_link") + [-0.03, 0.0, 0.40], vel=(0.0, 0.0, -1.0)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "the ball was touched by something other than a hand" and v["stages"] == [], v

    w.reset(); play(w, A, (5.0, -0.2, -5.0), shift=(0.20, 0.0, 0.0))        # faster than it came, but downward
    v = verdict(w)
    assert v["failed"] == "the ball was not set: it left the hands downward or slower than it came" and v["stages"] == [], v

    w.reset(); play(w, A, (6.3, -0.3, 3.3))                                # a flat set: not 1 m above the net
    v = verdict(w)
    assert v["failed"] == "the set did not rise high enough above the net" and v["stages"] == ["set"], v

    w.reset(); play(w, A, (1.2, -0.2, 7.4))                                # high enough, but short of the target
    v = verdict(w)
    assert v["failed"] == "the set came down outside the target" and v["stages"] == ["set", "above the net"], v

    def again(w):                                                          # the ball dropped onto the fists again
        w.launch("ball", w.d.site_xpos[w.robot.palm["left"]] + [0.03, 0.03, 0.35], (0.0, 0.0, -1.0))

    w.reset(); play(w, A, SET, after=again)
    v = verdict(w)
    assert v["failed"] == "second touch of the ball" and v["stages"][0] == "set", v

    w2, A2 = make(FAMILY, strike_max_s=0.0005)                             # below a real contact's time: held
    play(w2, A2, None)
    assert verdict(w2)["failed"] == "the ball was held", verdict(w2)

    w.reset(); hold(w, A, 0.2); move_robot(w, y=g["centre"][1] + 0.08); hold(w, A, 0.3)   # standing in the net
    assert verdict(w)["failed"] == "the robot touched the net", verdict(w)

    w.reset(); hold(w, A, 0.2); move_robot(w, y=g["centre"][1] - 1.0); hold(w, A, 0.3)    # in the opponent's court
    assert verdict(w)["failed"] == "a foot wholly beyond the centre line", verdict(w)

    w.reset(); hold(w, A, 0.2); move_robot(w, z=0.30); hold(w, A, 0.5)     # on the floor
    assert verdict(w)["failed"] == "fell", verdict(w)
    print(f"injection: ball in at {s_in} m/s, out at {s_out} m/s, apex {top:.2f} m, {off:.2f} m from the target's centre "
          f"(t = {t_ok:.2f} s); still raised fists return {passive:.2f} of the ball's speed")
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
