"""javelin (v2, TR 38): the referee says yes to a valid throw and no to every cheap exit.

The positive is an INJECTION: no controller of the H1-2 throws the 800 g javelin 20 m (a straight-arm swing releases it
at about a third of the speed that needs, see the family's report). What is real: the robot keeps its balance on the
walking policy, raises the javelin above its shoulder, opens the grip there (the referee judges that release), waits,
then walks backwards off the runway behind the arc and stands. What is injected: at the release the javelin is given a
velocity of 15.5 m/s at 38 degrees from where the hand let it go (0.12 m above it, clear of the hand); its
flight in air, its landing head first and the
measurement are the simulator's. Negatives: do nothing; an underarm release (below the shoulder); the back turned to
the arc; walking over the arc; leaving the runway before the landing (to the side); a landing tail first, outside the
sector, short of the mark; the javelin touched after the release; leaving in front of the arc's ends after the
landing; a fall after the landing; a broken simulation."""
import math

import mujoco
import numpy as np

import rcb_rfo
from rfo.testing import act, hold, make, move_robot, verdict
from rfo.world import UNSTABLE

FAMILY = "javelin"


def main():
    inst = rcb_rfo.make_instance(FAMILY, 0)                                 # the texts quote every parameter
    w, A = make(FAMILY)
    text = " ".join([w.task.sentence, w.task.rules, w.task.venue, w.task.difficulty] + w.task.deviations)
    assert all("{" + k + "}" in text for k in w.task.p), [k for k in w.task.p if "{" + k + "}" not in text]
    assert inst["robot"] == "unitree_h1" and inst["rulebook"] and len(inst["deviations"]) >= 5
    p, g = w.task.p, w.task.geometry()
    assert abs(2 * math.degrees(g["half_sector"]) - 28.96) < 0.01           # TR 32.9, 32.12: the sector follows from the arc
    names = [j[:-6] for j in w.L.JOINTS[12:]]

    def row(cmd=(0, 0, 0), grip=1, **arm):
        r = A.current("walk", w)
        r[0:3] = cmd
        for k, v in arm.items():
            r[3 + names.index(k)] = v
        r[-2:] = [0, grip]
        return r

    def raise_arm(pitch=-2.6, n=150):
        for i in range(n):
            act(w, A, "walk", row(right_shoulder_pitch=pitch * min(1.0, (i + 1) / 100)))

    def inject(speed, elev_deg, attitude_deg, yaw=0.0, pos=None):
        """Let go (a real release), then give the javelin a velocity from where it is (the injection)."""
        act(w, A, "walk", row(grip=0))
        e, a = math.radians(elev_deg), math.radians(attitude_deg)
        q = np.zeros(4)
        mujoco.mju_mulQuat(q, np.array([math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]),
                           np.array([math.cos(a / 2), 0, -math.sin(a / 2), 0]))
        w.put("javelin", w.pos("javelin") + [0, 0, 0.12] if pos is None else pos, quat=q,     # (clear of the hand)
              vel=(speed * math.cos(e) * math.cos(yaw), speed * math.cos(e) * math.sin(yaw), speed * math.sin(e)))

    def until(cond, cmd=(0, 0, 0), limit=40.0):
        t0 = w.t
        while not w.done and not cond() and w.t - t0 < limit:
            act(w, A, "walk", row(cmd, 0, right_shoulder_pitch=0.0))

    def thrown(speed=15.5, elev=38.0, attitude=30.0, yaw=0.0, pos=None):
        w.reset()
        raise_arm()
        inject(speed, elev, attitude, yaw, pos)

    def positive():
        thrown()
        until(lambda: w.ref.has("landing"))
        assert w.ref.has("landing") and not w.done, verdict(w)
        until(lambda: w.ref.has("exit"), cmd=(-0.5, 0, 0))                  # real: walk backwards off the runway
        until(lambda: False)
        return verdict(w), w.state_sha()

    v, sha = positive()
    assert v["success"] and v["stages"] == ["release", "landing", "exit"], v
    assert v["metrics"]["distance_m"] >= p["qualifying_mark_m"] and v["metrics"]["head_first"] == 1.0, v
    assert v["metrics"]["release_height_m"] > 1.6, v                        # let go above the shoulder (1.47 m)
    v2, sha2 = positive()
    assert sha2 == sha, "the positive is not deterministic"

    w.reset(); hold(w, A)                                                   # nop
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)

    w.reset()                                                               # an underarm release (arm down)
    for _ in range(30):
        act(w, A, "walk", row())
    inject(16.0, 38.0, 30.0)
    assert verdict(w)["failed"] == "the javelin was let go below the shoulder", verdict(w)

    w.reset()                                                               # the back turned to the arc
    for _ in range(20):                                                     # (injection: the robot is turned round)
        act(w, A, "walk", row())
    move_robot(w, yaw=math.radians(150.0))
    act(w, A, "walk", row())
    assert verdict(w)["failed"] == "turned the back to the arc before the throw", verdict(w)

    w.reset()                                                               # walking over the arc with the javelin
    until_done = lambda cmd: [act(w, A, "walk", row(cmd)) for _ in iter(lambda: w.done, True)]  # noqa: E731
    until_done((0.6, 0, 0))
    assert verdict(w)["failed"] == "touched the arc or the ground beyond it", (verdict(w), w.pelvis())

    thrown()                                                                # off the runway while the javelin flies
    move_robot(w, y=2.6)                                                    # (injection: moved beside the runway)
    until(lambda: False, limit=1.0)
    assert verdict(w)["failed"] == "left the runway before the javelin had landed", verdict(w)

    thrown(8.0, 50.0, 85.0, pos=(0.5, 0.0, 2.6))                            # slow and nose high: down tail first
    until(lambda: False)
    assert verdict(w)["failed"] == "the javelin did not land head first", verdict(w)

    thrown(yaw=math.radians(25.0), pos=(0.5, 0.0, 2.2))                     # far to the side
    until(lambda: False)
    assert verdict(w)["failed"] == "the javelin landed outside the sector", verdict(w)

    thrown(11.0, 30.0, -15.0)                                               # a valid landing short of the mark
    until(lambda: False)
    v = verdict(w)
    assert v["failed"] == "the throw is short of the qualifying mark" and 5 < v["metrics"]["distance_m"] < 20, v

    w.reset(); raise_arm()                                                  # let go; it comes down on the robot
    act(w, A, "walk", row(grip=0))
    x, y = w.pelvis()[:2]
    w.put("javelin", (x + 0.05, y, 2.6), quat=(math.sqrt(0.5), 0, 0, math.sqrt(0.5)))
    until(lambda: False, limit=3.0)
    assert verdict(w)["failed"] == "the javelin was touched after the release", verdict(w)

    thrown(); until(lambda: w.ref.has("landing"))                           # after the landing: out in front of the
    move_robot(w, x=0.6, y=2.6)                                             # arc's end line (injection)
    until(lambda: False, limit=1.0)
    assert verdict(w)["failed"] == "touched the arc or the ground beyond it", verdict(w)

    thrown(); until(lambda: w.ref.has("landing"))                           # a valid throw, then a fall (injection:
    move_robot(w, z=0.40)                                                   # the robot is dropped on the runway)
    until(lambda: False, limit=2.0)
    assert verdict(w)["failed"] == "fell" and verdict(w)["stages"] == ["release", "landing"], verdict(w)

    w.reset(); raise_arm(n=20)                                              # the simulation blows up (injection)
    w.d.qvel[w.robot.fv] = 1e30
    act(w, A, "walk", row(), 3)
    assert verdict(w)["failed"] == UNSTABLE, verdict(w)
    print("PASS javelin")


if __name__ == "__main__":
    main()
