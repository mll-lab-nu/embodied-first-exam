"""volleyball-serve (v2: FIVB Rule 12 on the official court, from behind the end line over the 2.43 m net 9 m away):
the referee says no to holding the ball for 8 s, to dropping it, to a thrown ball that brushes the fist (the v1
exploit), to a ball hit out of the hand or carried on it, to a ball that only bounces off a raised fist, to a hit with
the head, to a serve into the net, outside the antennas or beyond the court, to a foot on the court at the hit, to a
held ball and to a second touch; yes to toss, hit, over the net between the antennas, into the opponent's court.

The positive is an INJECTION (the family's reference controller, oracles/volleyball-serve, serves for real; this test
does not depend on it). Real: the left hand really lets go of the ball
(the toss), the right fist is really held up (stand mode), the ball really falls onto it, then really flies 9 m in air
over the net and lands in the opponent's court. Injected: 0.15 s after the toss the ball is put 0.3 m above the right
fist, falling at 1.5 m/s (a toss to there), and at the contact its velocity is set to 13.9 m/s forward and upward
(what a swinging arm would have given it; the ball is also moved 3 cm along that velocity, off the fist)."""
import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "volleyball-serve"
RIGHT_UP = np.r_[0.0, [0.0] * 7, [-2.7, -0.2, 0.0, 1.2, 0.0, 0.0, 0.0]]        # the right fist above the forehead
SERVE = (13.0, 0.0, 5.0)


def serve(w, A, vel=SERVE, toss_at=2.5, delay=0.15, place=None, place_vel=(0.0, 0.0, -1.5), after=None, on_fist=False):
    """Right arm up (1.5 s), let go at toss_at (real). `delay` seconds later the ball is put at place(w) (default:
    0.3 m above the right fist) with place_vel; at its first contact with the robot after that its velocity is set to
    `vel` (None: left alone). after(w): once, 0.25 s after the hit was judged. on_fist: instead, the left forearm is
    held upright; with "rest" the ball is first set down on the fist (re-gripped in contact with it), so that it lies
    there when the grip opens; nothing else is injected."""
    r, d = w.robot, w.d
    rest = r.rest[12:].copy()
    pose = RIGHT_UP.copy()
    if on_fist:
        pose[1:8] = [-0.63, 0.0, 0.0, -0.95, 0.0, 0.0, 0.0]
    i, placed, hit, t_hit = 0, False, False, None
    while not w.done:
        i += 1
        act(w, A, "stand", np.r_[rest + min(1.0, i * w.CONTROL_DT / 1.5) * (pose - rest), float(w.t < toss_at), 0])
        tr = w.task.trackers
        if on_fist == "rest" and abs(w.t - (toss_at - 0.5)) < 1e-6:
            R = d.xmat[r.mount["left"]].reshape(3, 3)
            w.put("ball", d.xpos[r.mount["left"]] + R @ np.array([0.0, 0.0, 0.100 + 0.105 - 0.001]))
            w.grab("left", "ball", event=False)
        if w.done or tr["released"] is None:
            continue
        if on_fist:
            continue
        if not placed and w.ref.time - tr["released"] >= delay - 1e-9:
            placed = True
            pos = d.site_xpos[r.palm["right"]] + [0.03, 0.0, 0.30] if place is None else place(w)
            w.put("ball", pos, vel=place_vel)
            continue
        st = tr["strike"]
        if placed and vel is not None and not hit and st is not None and st.phase >= 1:
            hit = True
            n = np.asarray(vel) / np.linalg.norm(vel)
            w.put("ball", w.pos("ball") + 0.03 * n, vel=vel)
        if after is not None and w.ref.has("hit"):
            t_hit = w.t if t_hit is None else t_hit
            if w.t - t_hit >= 0.25:
                after(w)
                after = None


def main():
    w, A = make(FAMILY)
    p, g, m = w.task.p, w.task.geometry(), w.m
    # the official court as built: the end line 0.5 m ahead, the net 9 m beyond it, its top at 2.43 m
    mesh = m.geom("net_mesh")
    assert abs(w.d.geom_xpos[mesh.id][2] + mesh.size[2] - 2.43) < 1e-6 and abs(w.d.geom_xpos[mesh.id][0] - 9.5) < 1e-6
    assert abs(w.d.geom_xpos[m.geom("end_line-1").id][0] - (0.5 + 0.025)) < 1e-6
    assert abs(w.d.geom_xpos[m.geom("net_antennaL").id][1] - 4.5) < 1e-6
    assert abs(m.geom("ball").size[0] - 0.105) < 1e-9 and abs(m.body("ball").mass[0] - 0.27) < 1e-9
    assert w.held["left"] == "ball" and p["service_time_s"] == 8.0

    hold(w, A, grips=[1, 0])                                               # nop: the ball stays in the hand for 8 s
    v = verdict(w)
    assert v["failed"] == "the serve was not hit in time" and v["stages"] == [] and abs(w.t - 8.0) < 0.011, (v, w.t)

    w.reset(); serve(w, A)                                                 # positive (injection, see the docstring)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["toss", "hit", "over the net", "in the court"], v
    ev = {e["stage"]: e for e in w.ref.events if e["ev"] == "stage"}
    assert ev["hit"]["parts"] == ["right_hand"] and ev["hit"]["free_s"] >= p["toss_free_s"], ev
    assert ev["hit"]["speed_in"] <= p["toss_max_speed_m_s"] < ev["hit"]["speed_out"] and ev["over the net"]["z"] > 2.43 + 0.105, ev
    sha, t_ok, land, hit = w.state_sha(), w.t, v["metrics"]["landing_x_m"], ev["hit"]
    w.reset(); serve(w, A)
    assert w.state_sha() == sha                                            # the same run again: the same state

    # the v1 exploit: a thrown ball (12 m/s, on its way over the net) that brushes the raised fist
    w.reset(); serve(w, A, None, place=lambda w: w.d.site_xpos[w.robot.palm["right"]] + [-0.30, 0.0, 0.07],
                     place_vel=(12.0, 0.0, 1.0))
    v = verdict(w)
    assert v["failed"] == "the ball was thrown, not tossed" and v["stages"] == ["toss"], v
    assert w.ref.events[-1]["speed_before_hit_m_s"] > 11.5, w.ref.events[-1]

    w.reset(); serve(w, A, None, place=lambda w: w.d.site_xpos[w.robot.palm["right"]] + [-0.30, 0.0, 0.30],
                     place_vel=(12.5, 0.0, 5.0))                           # a throw over the net that touches nothing
    v = verdict(w)
    assert v["failed"] == "the ball crossed the net without a hit" and v["stages"] == ["toss"], v

    w.reset(); serve(w, A, delay=0.0, place=lambda w: w.d.site_xpos[w.robot.palm["right"]] + [0.03, 0.0, 0.17])
    v = verdict(w)                                                         # on the fist 0.02 s after the release
    assert v["failed"] == "the ball was hit out of the hand" and v["stages"] == ["toss"], v

    w.reset(); serve(w, A, on_fist=True)                                   # real: the forearm upright, the grip opened:
    v = verdict(w)                                                         # the ball drops 5 mm back onto the fist,
    assert v["failed"] == "the ball was hit out of the hand" and v["stages"] == ["toss"], v   # still bouncing after 0.1 s

    w3, A3 = make(FAMILY, release_grace_s=0.0)                             # the ball lying on the fist when the grip opens
    serve(w3, A3, on_fist="rest")                                          # (without the 0.1 s the hand has to let go)
    v = verdict(w3)
    assert v["failed"] == "the ball was not tossed: it stayed on the hand" and v["stages"] == ["toss"], v

    w.reset(); serve(w, A, None)                                           # real: the ball only bounces off the fist
    v = verdict(w)
    assert v["failed"] == "the hit did not add speed" and v["stages"] == ["toss"], v
    passive = v["metrics"]["speed_out_m_s"] / v["metrics"]["speed_in_m_s"]

    def head(w):
        t = w.robot.torso
        return w.d.xpos[t] + w.d.xmat[t].reshape(3, 3) @ np.array([-0.08, 0.02, 0.76]) + [0.0, 0.0, 0.30]

    w.reset(); serve(w, A, None, place=head)                               # onto the head
    v = verdict(w)
    assert v["failed"] == "the ball was not hit with one hand or arm" and v["stages"] == ["toss"], v

    w.reset(); serve(w, A, (11.0, 0.0, 1.0))                               # too low: down before the net
    v = verdict(w)
    assert v["failed"] == "the ball landed outside the opponent's court" and v["stages"] == ["toss", "hit"], v
    assert v["metrics"]["landing_x_m"] < g["centre"][0], v

    w.reset(); serve(w, A, (10.5, 5.4, 6.5))                               # over, but outside the antenna
    v = verdict(w)
    assert v["failed"] == "the ball did not cross above the net between the antennas" and v["stages"] == ["toss", "hit"], v
    assert abs(w.ref.events[-1]["y"]) > 4.5 and w.ref.events[-1]["z"] > 2.43, w.ref.events[-1]

    w.reset(); serve(w, A, (17.5, 0.0, 5.0))                               # over the net and beyond the end line
    v = verdict(w)
    assert v["failed"] == "the ball landed outside the opponent's court" and v["stages"] == ["toss", "hit", "over the net"], v
    assert v["metrics"]["landing_x_m"] > g["centre"][0] + 9.0, v

    w.reset(); move_robot(w, x=0.55); w.d.qpos[w.free["ball"][0]] += 0.55   # standing on the court at the hit
    serve(w, A)                                                            # (the robot and its ball moved 0.55 m forward)
    v = verdict(w)
    assert v["failed"] == "foot fault" and v["stages"] == ["toss"], v

    def again(w):                                                          # the ball dropped onto the fist again
        w.launch("ball", w.d.site_xpos[w.robot.palm["right"]] + [0.03, 0.0, 0.30], (0.0, 0.0, -1.0))

    w.reset(); serve(w, A, (3.0, 0.0, 9.0), after=again)
    v = verdict(w)
    assert v["failed"] == "second touch of the ball" and v["stages"] == ["toss", "hit"], v

    w2, A2 = make(FAMILY, strike_max_s=0.0005)                             # below a real contact's time: held
    serve(w2, A2, None)
    assert verdict(w2)["failed"] == "the ball was held", verdict(w2)

    w.reset(); hold(w, A, 1.0, grips=[1, 0]); hold(w, A, grips=[0, 0])     # dropped
    v = verdict(w)
    assert v["failed"] == "the ball touched the floor before the hit" and v["stages"] == ["toss"], v

    w.reset(); hold(w, A, 1.0, grips=[1, 0]); hold(w, A, 0.05, grips=[0, 0])   # one toss: no second grip
    w.put("ball", w.d.site_xpos[w.robot.palm["left"]] + [0.0, 0.0, 0.0]); hold(w, A, 0.02, grips=[1, 0])
    assert w.held["left"] is None, w.held

    w.reset(); hold(w, A, 0.2, grips=[1, 0]); move_robot(w, z=0.30); hold(w, A, 0.5, grips=[1, 0])   # on the floor
    assert verdict(w)["failed"] == "fell", verdict(w)
    print(f"injection: hit {hit['free_s']} s after the ball left the hand, in at {hit['speed_in']} m/s, out at "
          f"{hit['speed_out']} m/s, lands at x = {land:.2f} m (t = {t_ok:.2f} s); a still fist returns {passive:.2f} of the ball's speed")
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
