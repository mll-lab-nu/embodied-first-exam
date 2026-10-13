"""shot-put (v2, TR 33): the referee says yes to a valid put and no to every cheap exit.

The positive is an INJECTION: the H1-2's arm really pushes the 7.26 kg shot away from the neck (a real put: the
referee's "from the shoulder" judgement is made on it), but it leaves the hand at 2.6 m/s and lands at the rim. What
is real: the stance, the balance on the walking policy, the push, the release, the walk backwards out of the rear half
of the circle over the rim, the stand. What is injected: at the release the shot is given 8.3 m/s at 40 degrees from
where the hand let it go; its flight, landing and measurement are the simulator's. Negatives: do nothing (the open-loop
stance topples under the shot); the shot lowered; taken behind the shoulders; slung from a straight arm (not pushed);
supported by the other hand; leaving the circle before the landing; standing on the stop board; a landing outside the
sector or short of the mark; the shot touched after the release; leaving from the front half; a fall after the
landing."""
import math

import mujoco

import rcb_rfo
import rfo.tasks.shot_put as mod
from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "shot-put"
PUSH = dict(right_elbow_pitch=0.6, right_shoulder_pitch=-1.9, right_wrist_yaw=0.0, right_wrist_pitch=0.0)
LEFT_ON_SHOT = dict(left_shoulder_pitch=-1.866, left_shoulder_roll=0.358, left_shoulder_yaw=-1.067,
                    left_elbow_pitch=-0.572, left_elbow_roll=1.022, left_wrist_pitch=-0.113, left_wrist_yaw=0.355)


def main():
    inst = rcb_rfo.make_instance(FAMILY, 0)
    w, A = make(FAMILY)
    text = " ".join([w.task.sentence, w.task.rules, w.task.venue, w.task.difficulty] + w.task.deviations)
    assert all("{" + k + "}" in text for k in w.task.p), [k for k in w.task.p if "{" + k + "}" not in text]
    assert inst["robot"] == "unitree_h1" and inst["rulebook"] and len(inst["deviations"]) >= 5
    p = w.task.p
    assert abs(w.m.body_subtreemass[w.m.body("shot").id] - 7.26) < 1e-6 and p["circle_diameter_m"] == 2.135
    up, fwd, neck = w.task.shot_in_trunk(w)                                 # the stance of t = 0 is TR 33.1's
    assert neck <= p["neck_reach_m"] and up > 0.05 and fwd > 0.05, (up, fwd, neck)
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

    def until(cond, cmd=(0, 0, 0), limit=40.0, **arm):
        t0 = w.t
        while not w.done and not cond() and w.t - t0 < limit:
            act(w, A, "walk", row(cmd, 0, **arm))

    def put(speed=8.3, elev=40.0, yaw=0.0, push_steps=22):
        """A real push and release; then (the injection) the shot is given a velocity from where it was let go."""
        w.reset()
        steps(30)
        steps(push_steps, **PUSH)
        steps(1, grip=0, **PUSH)
        if speed is not None and not w.done:
            e = math.radians(elev)
            w.put("shot", w.pos("shot") + [0.05, 0.0, 0.05],
                  vel=(speed * math.cos(e) * math.cos(yaw), speed * math.cos(e) * math.sin(yaw), speed * math.sin(e)))

    def positive():
        put()
        until(lambda: w.ref.has("landing"), right_shoulder_pitch=0.0, right_elbow_pitch=1.2)
        assert w.ref.has("landing") and not w.done, verdict(w)
        until(lambda: w.ref.has("exit"), cmd=(-0.5, 0, 0))                  # real: backwards over the rim, rear half
        until(lambda: False)
        return verdict(w), w.state_sha()

    v, sha = positive()
    assert v["success"] and v["stages"] == ["release", "landing", "exit"], v
    assert v["metrics"]["distance_m"] >= p["qualifying_mark_m"], v
    assert v["metrics"]["release_push_fraction"] >= 0.9, v                  # the real push is a put
    assert positive()[1] == sha, "the positive is not deterministic"

    put(speed=None)                                                         # the real put, nothing injected: valid,
    until(lambda: False, right_shoulder_pitch=0.0, right_elbow_pitch=1.2)   # and far short of the mark
    v = verdict(w)
    assert v["failed"] in ("the put is short of the qualifying mark", "the shot landed outside the sector"), v
    assert v["metrics"]["distance_m"] < 1.5 and v["metrics"]["release_speed_m_s"] < 3.5, v
    print("real put: release %.2f m/s, %.2f m" % (v["metrics"]["release_speed_m_s"], v["metrics"]["distance_m"]))

    w.reset(); hold(w, A)                                                   # nop: the open-loop stance topples
    assert verdict(w)["failed"] == "fell" and verdict(w)["stages"] == [], verdict(w)

    w.reset(); steps(20); steps(150, right_shoulder_pitch=0.3, right_elbow_pitch=1.5)      # the shot lowered
    assert verdict(w)["failed"] == "the shot dropped below the line of the shoulders", verdict(w)

    w.reset(); steps(20); steps(150, right_shoulder_yaw=-1.5, right_shoulder_roll=-1.2)    # taken behind
    assert verdict(w)["failed"] == "the shot went behind the line of the shoulders", verdict(w)

    put(speed=9.0, push_steps=34)                                           # let go late, from the straight arm's
    v = verdict(w)                                                          # swing: a sling, not a put
    assert v["failed"] == "the shot was not put from the shoulder" and v["metrics"]["release_push_fraction"] < 0.5, v

    w.reset()                                                               # the other hand on the shot (injection:
    mod.set_arm(w, **LEFT_ON_SHOT)                                          # the left arm is put across to it)
    steps(3)
    v = verdict(w)
    assert v["failed"] == "the shot was touched by something other than the putting hand", v

    put(); move_robot(w, x=-1.8, z=1.06)                                    # out of the circle while the shot flies
    until(lambda: False, limit=1.0)                                         # (injection: moved behind the circle)
    assert verdict(w)["failed"] == "touched the rim's top or the ground outside the circle before the shot had landed", verdict(w)

    w.reset(); steps(10)                                                    # the toes on the stop board (injection:
    move_robot(w, x=w.task.R - 0.10, y=0.0)                                 # the robot is moved to the front)
    steps(5)
    assert verdict(w)["failed"] == "touched the stop board other than its inner side", verdict(w)

    w.reset(); steps(10)                                                    # ... but the toes against its inner side
    x0 = w.pelvis()[0]                                                      # are legal (injection: moved forward

    def depth(x):                                                           # until they are 1 to 3 mm into it)
        w.d.qpos[w.free["shot"][0]] += x - w.pelvis()[0]                    # (the shot moves with the robot)
        move_robot(w, x=x)
        mujoco.mj_forward(w.m, w.d)
        ds = [c.dist for c in w.d.contact[:w.d.ncon]
              if "stop" in w.m.geom(c.geom[0]).name or "stop" in w.m.geom(c.geom[1]).name]
        return -min(ds) if ds else 0.0
    lo, hi = x0, x0 + 1.4
    for _ in range(30):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if depth(mid) > 0.002 else (mid, hi)
    assert 0.0 < depth(hi) < 0.004, depth(hi)
    act(w, A, "walk", row())
    assert w.ref.touching(w.task.robot, w.task.stop) and not w.done, verdict(w)

    put(yaw=math.radians(30.0)); until(lambda: False)                       # outside the sector
    assert verdict(w)["failed"] == "the shot landed outside the sector", verdict(w)

    put(speed=6.0); until(lambda: False)                                    # inside the sector, short of the mark
    v = verdict(w)
    assert v["failed"] == "the put is short of the qualifying mark" and 2 < v["metrics"]["distance_m"] < 6, v

    put(speed=0.0)                                                          # it comes down on the robot (injection)
    x, y = w.pelvis()[:2]
    w.put("shot", (x + 0.03, y, 2.2))
    until(lambda: False, limit=2.0)
    assert verdict(w)["failed"] == "the shot was touched after the release", verdict(w)

    put(); until(lambda: w.ref.has("landing"))                              # after the landing: out through the
    move_robot(w, x=1.9, y=0.9, z=1.06)                                     # front half (injection)
    until(lambda: False, limit=1.0)
    assert verdict(w)["failed"] == "left the circle from its front half", verdict(w)

    put(); until(lambda: w.ref.has("landing"))                              # a valid put, then a fall (injection)
    move_robot(w, z=0.40)
    until(lambda: False, limit=2.0)
    assert verdict(w)["failed"] == "fell" and verdict(w)["stages"] == ["release", "landing"], verdict(w)
    print("PASS shot-put")


if __name__ == "__main__":
    main()
