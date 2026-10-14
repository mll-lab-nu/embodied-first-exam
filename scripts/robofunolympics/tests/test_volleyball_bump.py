"""volleyball-bump (v2: serve receive on the official court; a 14 m/s float serve over the 2.43 m net, one forearm
contact, above net height, into the setter's 2 m target at the net): the referee says no to standing still (the serve
lands), to a serve that hits the body, to a pass that stays below the net's height, to one that comes down outside the
target (a real, passive forearm rebound among them), to a held ball, to a second touch, to reaching under the net for
the serve, to touching the net and to a foot beyond the centre line; yes to one forearm contact that rises above the
net and comes down in the target.

The positive is an INJECTION (the reference controller, oracles/volleyball-bump, passes for real; this test does
not depend on it). Real: the serve really flies 15 m in air
over the net and comes down on the left forearm of the robot, which really holds its arms out as a platform (stand
mode); the passed ball really rises above the net's height and lands in the target. Injected: where the robot stands
(teleported at t = 0 to where the serve comes down) and the ball's velocity as it comes off the forearm (the direction
a well-angled platform would have given it; the speed is about what the still forearm really gives)."""
import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "volleyball-bump"
PLATFORM = np.r_[0.0, [-0.6, 0.0, 0.0, 1.2, 0.0, 0.0, 0.0], [-0.6, 0.0, 0.0, 1.2, 0.0, 0.0, 0.0]]   # arms out and down
STAND = dict(x=0.75, y=0.54)           # here the serve comes down on the left forearm
PASS = (2.75, -1.60, 6.4)              # up to about 3.2 m and to the target


def receive(w, A, vel=None, stand=STAND, pose=PLATFORM, after=None):
    """The robot stands at `stand` with its arms in `pose`; when the ball comes off it after the first contact its
    velocity is set to `vel` (None: left alone). after(w): called once, 0.25 s after the pass was judged."""
    move_robot(w, **stand)
    rest = w.robot.rest[12:].copy()
    i, hit, t_pass = 0, False, None
    while not w.done:
        i += 1
        act(w, A, "stand", np.r_[rest + min(1.0, i * w.CONTROL_DT / 1.5) * (pose - rest), 0, 0])
        if w.done:
            break
        st = w.task.trackers["strike"]
        if vel is not None and not hit and st.phase >= 1 and not w.ref.touching(w.task.ball, w.ref.robot_mask):
            hit = True
            w.put("ball", w.pos("ball"), vel=vel)
        if after is not None and w.ref.has("pass"):
            t_pass = w.t if t_pass is None else t_pass
            if w.t - t_pass >= 0.25:
                after(w)
                after = None


def main():
    w, A = make(FAMILY)
    p, g, m = w.task.p, w.task.geometry(), w.m
    # the official court as built: net top 2.43 m, 9 m to each end line, 9 m wide, antennas above the side lines
    mesh = m.geom("net_mesh")
    assert abs(w.d.geom_xpos[mesh.id][2] + mesh.size[2] - 2.43) < 1e-6 and abs(w.d.geom_xpos[mesh.id][0] - 6.0) < 1e-6
    assert abs(w.d.geom_xpos[m.geom("net_antennaL").id][1] - 4.5) < 1e-6
    assert abs(w.d.geom_xpos[m.geom("net_antennaL").id][2] + m.geom("net_antennaL").size[1] - (2.43 + 0.80)) < 1e-6
    assert abs(w.d.geom_xpos[m.geom("end_line1").id][0] - (6.0 + 9.0 - 0.025)) < 1e-6
    assert abs(m.geom("ball").size[0] - 0.105) < 1e-9 and abs(m.body("ball").mass[0] - 0.27) < 1e-9
    assert g["launch"][0] > 6.0 + 9.0 and abs(np.linalg.norm(g["vel"]) - 14.0) < 0.05   # from behind the far end line
    ball = m.geom("ball").id
    assert m.geom_contype[ball] == 0 and m.geom_conaffinity[ball] == 0      # the waiting ball cannot be touched

    typ, row = A.hold(w)                                                   # nop: the serve lands beside the robot
    over = None
    while not w.done:
        w.step(A.to_raw(typ, row, w))
        b = w.pos("ball")
        if over is None and b[0] <= 6.0:
            over = float(b[2])
    v = verdict(w)
    assert v["failed"] == "the ball touched the floor before the pass" and v["stages"] == [], v
    b = w.pos("ball")
    assert over > 2.43 + 1.0 and abs(b[0]) < 0.3 and 0.4 < b[1] < 0.9, (over, b)   # over the net, down in the robot's zone

    w.reset(); receive(w, A, PASS)                                         # positive (injection, see the docstring)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["pass", "above the net height", "in the target"], v
    ev = {e["stage"]: e for e in w.ref.events if e["ev"] == "stage"}
    assert set(ev["pass"]["parts"]) <= {"left_forearm", "left_hand"} and "left_forearm" in ev["pass"]["parts"], ev
    assert v["metrics"]["pass_apex_m"] > p["net_height_m"] and v["metrics"]["from_target_centre_m"] < p["target_radius_m"], v
    sha, t_ok, off, apex = w.state_sha(), w.t, v["metrics"]["from_target_centre_m"], v["metrics"]["pass_apex_m"]
    w.reset(); receive(w, A, PASS)
    assert w.state_sha() == sha                                            # the same run again: the same state

    w.reset(); receive(w, A, None)                                         # real and passive: the still forearm's rebound
    v = verdict(w)                                                         # rises above the net but misses the target
    assert v["failed"] == "the pass came down outside the target" and v["stages"] == ["pass", "above the net height"], v
    passive = (v["metrics"]["pass_apex_m"], v["metrics"]["from_target_centre_m"], v["metrics"]["speed_out_m_s"])

    w.reset(); receive(w, A, (4.6, -2.6, 3.0))                             # a flat pass to the target: below the net
    v = verdict(w)
    assert v["failed"] == "the pass did not rise above the height of the net" and v["stages"] == ["pass"], v

    w.reset(); receive(w, A, None, stand=dict(x=0.95, y=0.70), pose=w.robot.rest[12:].copy())   # the serve on the body
    v = verdict(w)
    assert v["failed"] == "the ball was touched by something other than a forearm or a hand" and v["stages"] == [], v

    def again(w):                                                          # the ball dropped onto the left hand again
        w.launch("ball", w.d.site_xpos[w.robot.palm["left"]] + [0.03, 0.0, 0.30], (0.0, 0.0, -1.0))

    w.reset(); receive(w, A, PASS, after=again)
    v = verdict(w)
    assert v["failed"] == "second touch of the ball" and v["stages"][0] == "pass", v

    w2, A2 = make(FAMILY, strike_max_s=0.002)                              # below a real contact's time: held
    receive(w2, A2, PASS)
    assert verdict(w2)["failed"] == "the ball was held", verdict(w2)

    # reaching under the net: the robot at the net with its hands through under it, the ball dropped on them there
    w.reset(); move_robot(w, x=g["centre"][0] - 0.40); hold(w, A, p["launch_time_s"] + 0.05)
    palm = w.d.site_xpos[w.robot.palm["left"]].copy()
    assert palm[0] > g["centre"][0] and not w.done, (palm, verdict(w))
    w.launch("ball", palm + [0.02, 0.0, 0.25], (0.0, 0.0, -1.0)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "the serve was touched before it had crossed the net" and v["stages"] == [], v

    w.reset(); hold(w, A, 0.2); move_robot(w, x=g["centre"][0] - 0.08); hold(w, A, 0.3)   # standing in the net
    assert verdict(w)["failed"] == "the robot touched the net", verdict(w)

    w.reset(); hold(w, A, 0.2); move_robot(w, x=g["centre"][0] + 1.0); hold(w, A, 0.3)    # in the opponent's court
    assert verdict(w)["failed"] == "a foot wholly beyond the centre line", verdict(w)

    w.reset(); hold(w, A, 0.2); move_robot(w, z=0.30); hold(w, A, 0.5)     # on the floor
    assert verdict(w)["failed"] == "fell", verdict(w)
    print(f"injection: the pass rises to {apex:.2f} m and lands {off:.2f} m from the target's centre (t = {t_ok:.2f} s); "
          f"the still forearm's own rebound: {passive[2]} m/s, apex {passive[0]:.2f} m, {passive[1]:.2f} m from the centre")
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
