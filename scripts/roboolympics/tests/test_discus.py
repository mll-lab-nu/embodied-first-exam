"""discus (v2, TR 34): the referee says yes to a valid throw and no to every cheap exit.

The positive is an INJECTION: no controller of the H1-2 throws the 2 kg discus 15 m (a straight-arm swing releases it
at about a third of the speed that needs, see the family's report). What is real: the balance on the walking policy,
the release (the grip opens), the walk backwards out of the rear half of the circle over the rim, the stand. What is
injected: at the release the discus is given 13.5 m/s at 38 degrees, flat to its flight and spinning at 30 rad/s, from
0.4 m in front of and above where the hand let it go (clear of the leg); its flight in air, landing and measurement are
the simulator's. Negatives: do nothing; walking out of the circle with the discus (over the front rim); leaving before
the landing; a landing outside the sector or short of the mark; the discus touched after the release; leaving from the
front half; a fall after the landing."""
import math

import numpy as np

import rcb_rfo
from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "discus"
EARLY = "touched the rim's top or the ground outside the circle before the discus had landed"


def main():
    inst = rcb_rfo.make_instance(FAMILY, 0)
    w, A = make(FAMILY)
    text = " ".join([w.task.sentence, w.task.rules, w.task.venue, w.task.difficulty] + w.task.deviations)
    assert all("{" + k + "}" in text for k in w.task.p), [k for k in w.task.p if "{" + k + "}" not in text]
    assert inst["robot"] == "unitree_h1" and inst["rulebook"] and len(inst["deviations"]) >= 5
    p = w.task.p
    assert abs(w.m.body_subtreemass[w.m.body("discus").id] - 2.0) < 1e-9 and p["circle_diameter_m"] == 2.50
    names = [j[:-6] for j in w.L.JOINTS[12:]]

    def row(cmd=(0, 0, 0), grip=1, **arm):
        r = A.current("walk", w)
        r[0:3] = cmd
        for k, v in arm.items():
            r[3 + names.index(k)] = v
        r[-2:] = [0, grip]
        return r

    def steps(n, cmd=(0, 0, 0), grip=1, **arm):
        for _ in range(n):
            if w.done:
                return
            act(w, A, "walk", row(cmd, grip, **arm))

    def until(cond, cmd=(0, 0, 0), limit=40.0):
        t0 = w.t
        while not w.done and not cond() and w.t - t0 < limit:
            act(w, A, "walk", row(cmd, 0))

    def throw(speed=13.5, elev=38.0, yaw=0.0, spin=30.0):
        """A real release; then (the injection) the discus is given a velocity, an attitude and a spin."""
        w.reset()
        steps(30)
        steps(1, grip=0)
        e = math.radians(elev)
        q = np.array([math.cos(e / 2), 0.0, -math.sin(e / 2), 0.0])        # its plane along the flight path
        w.put("discus", w.pos("discus") + [0.4, 0.0, 0.4], quat=q, angvel=(0, 0, spin),
              vel=(speed * math.cos(e) * math.cos(yaw), speed * math.cos(e) * math.sin(yaw), speed * math.sin(e)))

    def positive():
        throw()
        until(lambda: w.ref.has("landing"))
        assert w.ref.has("landing") and not w.done, verdict(w)
        until(lambda: w.ref.has("exit"), cmd=(-0.5, 0, 0))                  # real: backwards over the rim, rear half
        until(lambda: False)
        return verdict(w), w.state_sha()

    v, sha = positive()
    assert v["success"] and v["stages"] == ["release", "landing", "exit"], v
    assert v["metrics"]["distance_m"] >= p["qualifying_mark_m"], v
    assert positive()[1] == sha, "the positive is not deterministic"

    w.reset(); hold(w, A)                                                   # nop
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)

    w.reset()                                                               # walking out with the discus (real)
    steps(2000, cmd=(0.6, 0, 0))
    assert verdict(w)["failed"] == EARLY, (verdict(w), w.pelvis())

    throw(); move_robot(w, x=-2.0, z=1.06)                                  # out of the circle while it flies
    until(lambda: False, limit=1.0)                                         # (injection: moved behind the circle)
    assert verdict(w)["failed"] == EARLY, verdict(w)

    throw(yaw=math.radians(30.0)); until(lambda: False)                     # outside the sector
    assert verdict(w)["failed"] == "the discus landed outside the sector", verdict(w)

    throw(speed=9.0); until(lambda: False)                                  # inside the sector, short of the mark
    v = verdict(w)
    assert v["failed"] == "the throw is short of the qualifying mark" and 4 < v["metrics"]["distance_m"] < 15, v

    w.reset(); steps(30); steps(1, grip=0)                                  # it comes down on the robot (injection)
    x, y = w.pelvis()[:2]
    w.put("discus", (x + 0.03, y, 2.2))
    until(lambda: False, limit=2.0)
    assert verdict(w)["failed"] == "the discus was touched after the release", verdict(w)

    throw(); until(lambda: w.ref.has("landing"))                            # after the landing: out through the
    move_robot(w, x=2.0, y=0.9, z=1.06)                                     # front half (injection)
    until(lambda: False, limit=1.0)
    assert verdict(w)["failed"] == "left the circle from its front half", verdict(w)

    throw(); until(lambda: w.ref.has("landing"))                            # a valid throw, then a fall (injection)
    move_robot(w, z=0.40)
    until(lambda: False, limit=2.0)
    assert verdict(w)["failed"] == "fell" and verdict(w)["stages"] == ["release", "landing"], verdict(w)
    print("PASS discus")


if __name__ == "__main__":
    main()
