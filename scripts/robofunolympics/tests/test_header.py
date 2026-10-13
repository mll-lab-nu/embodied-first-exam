"""header (v2: the official goal 5.5 m away, a real cross from 20 m, a goalkeeper dummy; the H1-2's head judged by
where the ball touches its trunk shell): the referee says no to standing still (the cross flies past), to a ball that
only rebounds from a head held in its path (the v1 exploit), to a ball on the chest or a hand, to a carried ball, to a
header wide of the goal, to a second touch, to waiting at the kicker and to a ball that goes in without a header; yes
to a ball met by the head before it bounces and sent on faster than it came, into the goal.

The positive is an INJECTION: no heading controller exists for the H1-2. Real: the cross really flies 20 m in air and
hits the head of the standing robot (the contact points are 0.70 m above the waist joint, above the neck at 0.53 m);
the headed ball really flies past the dummy into the goal. Injected: where the robot stands (teleported 0.46 m forward
at t = 0, so that its head is in the ball's path) and the ball's velocity at that contact (what a driven head would
have given it)."""
import numpy as np

from rfo.testing import hold, make, move_robot, verdict

FAMILY = "header"
STAND = dict(x=0.46)                   # here the cross hits the standing robot's head
HEADED = (12.0, -1.5, -2.5)            # 12.4 m/s, down and to the right of the dummy


def play(w, A, vel=None, stand=STAND, after=None):
    """The robot stands at `stand`; at the first contact of the ball with it the ball's velocity is set to `vel` (None:
    left alone). after(w): called once when the header has been judged (the stage "header")."""
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
        if after is not None and w.ref.has("header"):
            after(w)
            after = None


def main():
    w, A = make(FAMILY)
    p, g, m = w.task.p, w.task.geometry(), w.m
    # the official setting as built
    assert g["goal_x"] == 5.5 and p["goal_width_m"] == 7.32 and p["goal_height_m"] == 2.44
    assert abs(m.geom("goal_postL").pos[1] - 3.72) < 1e-9 and abs(m.geom("goal_postL").size[0] - 0.06) < 1e-9
    assert abs(w.d.geom_xpos[m.geom("goal_bar").id][2] - 2.50) < 1e-6
    assert abs(m.geom("ball").size[0] - 0.11) < 1e-9 and abs(m.body("ball").mass[0] - 0.43) < 1e-9
    assert abs(np.hypot(g["launch"][0], g["launch"][1]) - p["cross_distance_m"]) < 0.01
    assert "head" not in w.ref.part_names and "torso" in w.ref.part_names   # one shell: the head is judged by height
    # the neck on the model: the shell's narrowest section between the shoulders and the head
    sh = m.geom("torso_link_sc0")
    mid = int(sh.dataid[0])
    V = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]]
    import mujoco
    R = np.zeros(9); mujoco.mju_quat2Mat(R, sh.quat); V = V @ R.reshape(3, 3).T + sh.pos
    width = lambda z0, z1: float(np.ptp(V[(V[:, 2] >= z0) & (V[:, 2] < z1), 1]))    # noqa: E731
    assert width(0.50, 0.53) < 0.10 < 0.13 < width(0.65, 0.71) and width(0.44, 0.47) > 0.25, "the neck is at 0.50-0.53 m"
    assert abs(float(V[:, 2].max()) - 0.76) < 0.01 and p["head_z_m"] == 0.53
    ball = m.geom("ball").id
    assert m.geom_contype[ball] == 0 and m.geom_conaffinity[ball] == 0      # the waiting ball cannot be touched

    hold(w, A)                                                             # nop: the cross flies past, 0.6 m in front
    v = verdict(w)
    assert v["failed"] == "the ball touched the ground before the header" and v["stages"] == [], v

    w.reset(); play(w, A, HEADED)                                          # positive (injection, see the docstring)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["header", "goal"], v
    ev = {e["stage"]: e for e in w.ref.events if e["ev"] == "stage"}
    assert ev["header"]["height_on_trunk_m"] > p["head_z_m"] and ev["header"]["speed_out"] > ev["header"]["speed_in"] > 11.0, ev
    sha, t_ok, h = w.state_sha(), w.t, ev["header"]
    w.reset(); play(w, A, HEADED)
    assert w.state_sha() == sha                                            # the same run again: the same state

    # the v1 exploit: the head only stands in the ball's path. The ball leaves a still head at about 0.8 of its speed
    # (0.78 to 0.84 over the standing places 0.44 to 0.68 m; at 0.44 to 0.48 m it is deflected into the goal mouth)
    worst = 0.0
    for x in (0.44, 0.46, 0.52, 0.60, 0.68):
        w.reset(); play(w, A, None, stand=dict(x=x))
        v = verdict(w)
        assert v["failed"] == "the ball was not headed: it left the head slower than it came" and v["stages"] == [], (x, v)
        worst = max(worst, v["metrics"]["speed_out_m_s"] / v["metrics"]["speed_in_m_s"])
    assert worst < 0.9, worst

    after = p["launch_time_s"] + 0.1
    w.reset(); hold(w, A, after)                                           # chested (injected: the ball at the chest)
    w.launch("ball", (0.6, 0.0, 1.30), (-4.0, 0.0, 0.0)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "the ball touched the body below the head" and v["stages"] == [], v
    assert w.ref.events[-1]["height_on_trunk_m"] < p["head_z_m"], w.ref.events[-1]

    w.reset(); hold(w, A, after)                                           # handball (injected: the ball on the hand)
    palm = w.d.site_xpos[w.robot.palm["right"]].copy()
    w.launch("ball", palm + [0.0, 0.0, 0.30], (0.0, 0.0, -2.0)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "the ball was touched by something other than the head", v
    assert "right_hand" in w.ref.events[-1]["parts"], w.ref.events[-1]

    w2, A2 = make(FAMILY, strike_max_s=0.002)                              # below a real contact's time: a carry
    play(w2, A2, HEADED)
    assert verdict(w2)["failed"] == "the ball was carried", verdict(w2)

    w.reset(); play(w, A, (10.0, 8.5, -1.0))                               # headed wide of the post
    v = verdict(w)
    assert v["failed"] == "the ball crossed the goal line outside the goal" and v["stages"] == ["header"], v

    def again(w):                                                          # the ball dropped onto the head once more
        t = w.robot.torso
        top = w.d.xpos[t] + w.d.xmat[t].reshape(3, 3) @ np.array([0.03, 0.0, 0.76])
        w.launch("ball", top + [0.0, 0.0, 0.25], (0.0, 0.0, -2.0))

    w.reset(); play(w, A, HEADED, after=again)                             # a second touch after a valid header
    v = verdict(w)
    assert v["failed"] == "second touch of the ball" and v["stages"] == ["header"], v

    w.reset(); move_robot(w, x=3.0, y=11.5); hold(w, A, 0.2)               # waiting at the kicker
    assert verdict(w)["failed"] == "too close to the ball before the cross", verdict(w)

    w.reset(); hold(w, A, after)                                           # into the goal without a header
    w.launch("ball", (3.0, 1.5, 1.0), (15.0, 0.0, 0.0)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "the ball crossed the goal line without a header" and v["stages"] == [], v

    w.reset(); hold(w, A, 0.2); move_robot(w, z=0.30); hold(w, A, 0.5)     # on the ground
    assert verdict(w)["failed"] == "fell", verdict(w)
    print(f"injection: ball in at {h['speed_in']} m/s, out at {h['speed_out']} m/s, contact {h['height_on_trunk_m']} m "
          f"above the waist, goal at t = {t_ok:.2f} s; a still head returns at most {worst:.2f} of the ball's speed")
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
