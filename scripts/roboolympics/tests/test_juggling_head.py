"""juggling-head (headers in a row with a size-5 ball fed onto the G1's head): the referee says no to doing nothing, to
a ball that only bounces on a still head (each bounce slower: none counts), to touches that do not send the ball up a
ball's diameter, to the ball resting on the head, to an arm, a hand or the chest, to the ground, to leaving the grid
and to a fall; yes to a real header and to ten headers in a row.

Two positives:
- REAL CONTROLLER (through the action interface, no injection): a `lowcmd` squat timed to the falling ball (knees
  bent while it falls, stretched in the last tenth of a second so that the head meets it moving up) gives the first
  header: the ball leaves the head faster than it came. (It does not get ten: the head is round, and a contact a
  centimetre off its top sends the ball sideways; the family has no reference solution.)
- INJECTION for ten headers: the ball really falls onto the head and really touches it, nothing else touches it;
  each time it has come off the head its velocity is set to 3.5 m/s straight up (what a header would give it; more
  than it arrived with) and it is put back over the head's top."""
import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "juggling-head"
R = 0.11


def head_top(w):
    g = w.m.geom("torso_link_sc2").id
    return w.d.geom_xpos[g] + w.d.geom_xmat[g].reshape(3, 3) @ np.array([-0.0115, -0.0126, 0.103])


def bob(w, A, a=0.25, T_up=0.12, down=0.08):
    """The real controller: legs in a squat of depth a (hip and ankle -a, knee +2a from the stance) while the ball
    falls; stretched as the ball's predicted time to the head falls below T_up; down again after the touch."""
    r = w.robot
    q0 = np.r_[r.stance, r.rest[12:]]
    s = 0.0
    while not w.done:
        b, v = w.pos("ball"), w.vel("ball")
        fed = w.task.trackers["fed"] is not None
        h = b[2] - (head_top(w)[2] + R)
        disc = v[2] ** 2 + 2 * 9.81 * h
        tau = (v[2] + np.sqrt(disc)) / 9.81 if fed and disc > 0 else (10.0 if not fed else 0.0)
        if fed and v[2] > 0 and h < 0.15:
            s = min(1.0, s + down)
        else:
            tgt = float(np.clip(tau / T_up, 0.0, 1.0))
            s = min(1.0, s + down) if tgt >= s else tgt
        q = q0.copy()
        for o in (0, 6):
            q[o + 0] -= a * s
            q[o + 3] += 2 * a * s
            q[o + 4] -= a * s
        act(w, A, "lowcmd", np.r_[q, np.zeros(2 * r.L.NJ), r.kp0, r.kd0, 0, 0])


def juggle(w, A, n=10, up=3.5, last=(0.0, 0.0), recentre=True):
    """Stand still; after the feed, each time the ball has touched the head and come off again, set its velocity to
    `up` m/s straight up (None: keep its own velocity) and put it back over the head's top (recentre), for n touches
    (the n-th also gets the horizontal velocity `last`)."""
    rest = w.robot.rest[12:]
    k, spot = 0, None
    while not w.done:
        act(w, A, "stand", np.r_[rest, 0, 0])
        if w.done or w.task.trackers["fed"] is None:
            continue
        if spot is None:
            spot = head_top(w)[:2].copy()
        tr = w.task.trackers
        if tr["touch"].count > k and k < n and not w.ref.touching(w.task.ball, w.ref.robot_mask):
            k = tr["touch"].count                              # a touch has happened and the ball is off again
            v = w.vel("ball")
            vel = (v[0], v[1], v[2]) if up is None else ((last[0], last[1], up) if k >= n else (0.0, 0.0, up))
            if up is None and recentre:
                vel = (0.0, 0.0, v[2])
            w.put("ball", (spot[0], spot[1], w.pos("ball")[2]) if recentre else w.pos("ball"), vel=vel)


def main():
    w, A = make(FAMILY)
    p, m = w.task.p, w.m
    assert w.robot_name == "unitree_g1" and abs(m.geom("ball").size[0] - 0.11) < 1e-9
    assert abs(m.body("ball").mass[0] - 0.43) < 1e-9 and p["headers"] == 10 and abs(p["grid_m"] - 4.572) < 1e-9
    assert w.ref.part("head").any() and m.geom_contype[m.geom("ball").id] == 0     # the waiting ball: no contacts

    hold(w, A)                                                             # nop: one passive bounce, then the ground
    v = verdict(w)
    bounces = [e for e in w.ref.events if e["ev"] == "bounce"]
    assert v["failed"] == "the ball touched the ground" and v["stages"] == [] and bounces, (v, w.ref.events)
    passive = bounces[0]["speed_out"] / bounces[0]["speed_in"]
    assert passive < p["touch_gain"] - 0.05, bounces

    w.reset(); bob(w, A)                                                   # positive: a REAL header (lowcmd squat)
    v = verdict(w)
    hdr = [e for e in w.ref.events if e["ev"] == "stage"]
    assert v["stages"][:1] == ["header 1"] and hdr[0]["speed_out"] >= p["touch_gain"] * hdr[0]["speed_in"], (v, hdr)
    real = (hdr[0]["speed_in"], hdr[0]["speed_out"], v["failed"], v["metrics"]["headers"])
    sha_real = w.state_sha()
    w.reset(); bob(w, A)
    assert w.state_sha() == sha_real                                      # deterministic

    w.reset(); juggle(w, A)                                                # positive: ten headers (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == [f"header {i + 1}" for i in range(10)], v
    sha, t_ok = w.state_sha(), w.t
    w.reset(); juggle(w, A)
    assert w.state_sha() == sha                                           # the same run again: the same state

    w.reset(); juggle(w, A, up=None)                                       # a still head, the ball kept over it
    v = verdict(w)
    nb = len([e for e in w.ref.events if e["ev"] == "bounce"])
    assert not v["success"] and v["metrics"]["headers"] == 0 and nb >= 2, (v, w.ref.events)
    assert v["failed"] in ("the ball was touched again before it had risen enough", "the ball was carried"), v
    still_end = v["failed"]

    w.reset(); juggle(w, A, n=9, last=(2.0, 0.0))                          # nine headers, the ninth sent off forwards
    v = verdict(w)
    assert v["failed"] == "the ball touched the ground" and v["stages"] == [f"header {i + 1}" for i in range(9)], v

    w.reset(); juggle(w, A, up=1.5)                                        # touches that send the ball up 11 cm
    v = verdict(w)
    assert v["failed"] == "the ball was touched again before it had risen enough" and v["stages"] == [], v

    w.reset(); hold(w, A, 1.1)                                             # the ball laid on the head: balanced
    w.put("ball", head_top(w) + [0.0, 0.0, R - 0.001]); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "the ball was carried" and v["stages"] == [], v

    w.reset(); hold(w, A, 1.02)                                            # onto the left hand
    w.launch("ball", w.d.site_xpos[w.robot.palm["left"]] + [0.0, 0.60, 0.25], (0.0, -2.5, 0.0)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "the ball was touched by a part other than the head", v
    assert "left_hand" in w.ref.events[-1]["parts"], w.ref.events[-1]

    w.reset(); hold(w, A, 1.02)                                            # onto the chest
    w.launch("ball", w.pos("torso_link") + [0.60, 0.0, 0.12], (-3.5, 0.0, 0.5)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "the ball was touched by a part other than the head", v
    assert "torso" in w.ref.events[-1]["parts"], w.ref.events[-1]

    w.reset(); hold(w, A, 1.02)                                            # onto a shoulder, from above
    sh = w.pos("left_shoulder_roll_link")
    w.launch("ball", sh + [0.0, 0.03, 0.45], (0.0, 0.0, -2.0)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "the ball was touched by a part other than the head", v
    assert set(w.ref.events[-1]["parts"]) & {"left_upper_arm", "torso"}, w.ref.events[-1]

    w.reset(); hold(w, A, 0.2); move_robot(w, x=2.40); hold(w, A, 0.3)     # out of the grid
    assert verdict(w)["failed"] == "stepped out of the grid", verdict(w)

    w.reset(); hold(w, A, 0.2); move_robot(w, z=0.30); hold(w, A, 0.5)     # on the ground
    assert verdict(w)["failed"] == "fell", verdict(w)

    print(f"still head: the fed ball leaves at {passive:.2f} of its speed (not a header); kept over a still head it "
          f"bounces {nb} times uncounted, then: {still_end}")
    print(f"real controller (lowcmd squat): header 1 at {real[0]:.2f} -> {real[1]:.2f} m/s; it then ends with "
          f"'{real[2]}' after {real[3]} header(s)")
    print(f"injection: ten headers at t = {t_ok:.2f} s")
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
