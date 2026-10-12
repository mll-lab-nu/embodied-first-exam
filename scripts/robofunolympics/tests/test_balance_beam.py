"""balance-beam (FIG beam, 5 m x 0.10 m x 1.25 m): the referee says no to standing still in the tandem start (the
robot stays up for the whole episode: "time"), to the `stand` action and to the walking policy (both put the feet
beside the beam: the robot falls off), to stopping short of the far end, to going on past the end, to lying on the
beam at the far end, to standing on the floor under the far end.

The positive is an INJECTION (no controller of this robot walks a 0.10 m beam): the test slides the robot along the
beam in its tandem pose (rfo.testing.move_robot, 4 mm per control step while its joints hold the pose), so its feet
really are on the beam's top all the way and really stand in the far end zone for the 2 s; nothing else is touched."""
import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict

PRONE = [np.cos(np.pi / 4), 0.0, np.sin(np.pi / 4), 0.0]


def slide(w, A, to_x, step=0.004):
    """Slide the standing robot along the beam until its pelvis is at to_x, then hold to the end."""
    hold(w, A, 0.5)
    while not w.done and w.pelvis()[0] < to_x:
        move_robot(w, x=float(w.pelvis()[0]) + step)
        hold(w, A, 0.01)
    hold(w, A)


def main():
    w, A = make("balance-beam")
    p, r = w.task.p, w.robot
    L, zone = p["length_m"], p["end_zone_m"]
    assert (L, p["width_m"], p["height_m"]) == (5.0, 0.10, 1.25)                              # the FIG beam
    assert A.hold(w)[0] == "lowcmd" and w.ref.parts_touching(w.ref.ground) == set()           # t = 0: a joint hold
    hold(w, A, 3.0)                                                                           # the tandem start stands
    lo, hi = w.task.feet_span(w.ref)
    assert 0.0 < lo < hi < 0.6 and abs(w.pelvis()[1]) < 0.01 and w.upright() > 0.999, (lo, hi, w.pelvis())
    assert abs(w.d.site_xpos[r.foot_site["left"]][1]) < 0.01 and abs(w.d.site_xpos[r.foot_site["right"]][1]) < 0.01
    hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)          # nop: stands, no walk

    w.reset(); slide(w, A, L - 0.30)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["half way", "far end", "stand"], v                # positive (injection)
    assert v["metrics"]["distance_m"] >= L - zone, v
    sha = w.state_sha()
    w.reset(); slide(w, A, L - 0.30)
    assert w.state_sha() == sha                                                               # deterministic

    w.reset()                                                                                 # the `stand` action:
    while not w.done:                                                                         # the stance is wider
        act(w, A, "stand", np.r_[r.rest[12:], 0, 0])                                          # than the beam
    assert verdict(w)["failed"] == "touched the floor" and w.t < 5.0, (verdict(w), w.t)
    w.reset()                                                                                 # the walking policy
    while not w.done:
        act(w, A, "walk", np.r_[0.3, 0, 0, r.rest[12:], 0, 0])
    assert verdict(w)["failed"] == "fell on the beam" and w.t < 5.0, (verdict(w), w.t)        # (a shin hits it)
    assert verdict(w)["stages"] == [], verdict(w)

    w.reset(); slide(w, A, L - zone - 0.02)                                                   # stops short: the rear
    v = verdict(w)                                                                            # foot is not in the zone
    assert v["failed"] == "time" and v["stages"] == ["half way"], v
    w.reset(); slide(w, A, L + 0.5)                                                           # goes on past the end:
    v = verdict(w)                                                                            # a foot drops off, the
    assert v["failed"] == "fell on the beam" and v["stages"] == ["half way", "far end"], v    # shin lands on the edge
    w.reset(); hold(w, A, 0.2)                                                                # lying on the beam at
    move_robot(w, x=L - 0.9, z=p["height_m"] + 0.25)                                          # the far end
    w.d.qpos[r.fq + 3:r.fq + 7] = PRONE
    hold(w, A, 2.0)
    assert verdict(w)["failed"] == "fell on the beam" and verdict(w)["stages"] == [], verdict(w)
    w.reset(); hold(w, A, 0.2)                                                                # on the floor beside
    move_robot(w, x=L - 0.3, y=0.6, z=0.80); hold(w, A, 2.0)                                  # the far end
    assert verdict(w)["failed"] == "touched the floor" and verdict(w)["stages"] == [], verdict(w)
    print("PASS balance-beam")


if __name__ == "__main__":
    main()
