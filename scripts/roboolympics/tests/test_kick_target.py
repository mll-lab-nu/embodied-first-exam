"""kick-target (v2): the referee says yes to a clean kick on the band that gives the bag 20 N s and no to every cheap
exit; and the impulse meter is checked against a known impulse.

The positive is an INJECTION: the H1-2 has no kicking or one-leg balance controller, and a kick at 1.1 m is above its
hip joint. A "ghost kick": the robot is posed 4 cm above the floor with its right leg raised (the thigh above the
horizontal, the sole towards the bag's band, 3 cm from it), held stiff by its own joint servos, and is given a forward
velocity of 1.0 m/s; the foot's collision with the bag, the bag's swing and the referee's measurement are the
simulator's. 0.08 s later the robot is put back on its feet 0.4 m farther from the bag (the second injection), where
it really stands for the 2 s while the bag swings. The meter (the bag's angular momentum about its hook over the depth
of the hit) is checked against an injected force of 250 N for 0.10 s on the bag (25 N s: read within 2 %).
Negatives: do nothing; a slower ghost kick (too weak); a touch longer than the bound (a push: the same kick under
a bound of 0.03 s; a slow real press is in test_boxing.py, the same rule); the other leg; a kick
below the band; walking into the bag (hands first); standing where the bag swings back (touched again: real, the
robot stays where it was); a fall after the kick."""
import mujoco
import numpy as np

import rcb_rfo
from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

FAMILY = "kick-target"


def main():
    inst = rcb_rfo.make_instance(FAMILY, 0)
    w, A = make(FAMILY)
    T, p = w.task, w.task.p
    m, d, r = w.m, w.d, w.robot
    text = " ".join([T.sentence, T.rules, T.venue, T.difficulty] + T.deviations)
    assert all("{" + k + "}" in text for k in p), [k for k in p if "{" + k + "}" not in text]
    assert inst["robot"] == "unitree_h1" and len(inst["deviations"]) >= 4
    assert abs(m.body_subtreemass[T.meter.body] - 30.0) < 1e-9 and abs(T.hook_z - 2.25) < 1e-9
    names = [j[:-6] for j in w.L.JOINTS]
    NJ = w.L.NJ
    rest = np.r_[r.rest[12:], 0.0, 0.0]

    def ghost_kick(v=1.0, leg="right", hip=-2.05, knee=0.3, t_back=0.08, back=-0.4, restore=True, gap=0.03):
        w.reset()
        hold(w, A, 0.3)
        saved = (d.qpos.copy(), d.qvel.copy(), d.act.copy())
        d.qpos[r.qadr[names.index(f"{leg}_hip_pitch")]] = hip
        d.qpos[r.qadr[names.index(f"{leg}_knee")]] = knee
        d.qvel[:] = 0.0
        mujoco.mj_forward(m, d)
        g = m.geom(f"{leg}_foot_strike").id
        front = float(d.geom_xpos[g][0] + np.abs(d.geom_xmat[g].reshape(3, 3)[0]) @ m.geom_size[g])
        d.qpos[r.fq] += (p["bag_distance_m"] - p["bag_diameter_m"] / 2 - gap) - front
        d.qpos[r.fq + 1] -= float(d.geom_xpos[g][1])          # the kicking foot on the bag's centre line
        d.qpos[r.fq + 2] += 0.04
        kick_robot(w, vel=(v, 0.0, 0.0))
        stiff = np.r_[d.qpos[r.qadr], np.zeros(2 * NJ), r.kp0, r.kd0, 0.0, 0.0]
        t0 = w.t
        while not w.done and w.t - t0 < t_back - 1e-9:
            act(w, A, "lowcmd", stiff)
        if restore and not w.done:                            # the robot is put back on its feet, farther back
            bq, bv = int(m.joint("bag").qposadr[0]), T.meter.dof
            keep = (d.qpos[bq:bq + 4].copy(), d.qvel[bv:bv + 3].copy())
            d.qpos[:], d.qvel[:], d.act[:] = saved
            d.qpos[bq:bq + 4], d.qvel[bv:bv + 3] = keep
            r.arb.reset(d)
            w._hold_legs()
            d.qpos[r.fq] += back
        return stiff

    def stand():
        while not w.done:
            act(w, A, "stand", rest)
        return verdict(w)

    ghost_kick(); v = stand(); sha = w.state_sha()                          # the positive
    assert v["success"] and v["stages"] == ["strike", "stand"], v
    mm = v["metrics"]
    assert mm["impulse_n_s"] >= p["min_impulse_n_s"] and mm["contact_s"] <= p["max_contact_s"], v
    assert p["zone_low_m"] <= mm["hit_height_m"] <= p["zone_high_m"], v
    assert abs(mm["impulse_n_s"] - mm["contact_impulse_n_s"]) < 0.15 * mm["impulse_n_s"], v   # (friction's share)
    print("ghost kick: %.2f N s (normal contact force integral %.2f N s), touch %.3f s, at %.2f m"
          % (mm["impulse_n_s"], mm["contact_impulse_n_s"], mm["contact_s"], mm["hit_height_m"]))
    ghost_kick(); stand()
    assert w.state_sha() == sha, "the positive is not deterministic"

    # the meter against an injected known impulse: 250 N for 0.10 s on the bag at the band's middle
    w.reset()
    z = 0.5 * (p["zone_low_m"] + p["zone_high_m"])
    point = np.array([p["bag_distance_m"] - p["bag_diameter_m"] / 2, 0.0, z])
    F = np.array([250.0, 0.0, 0.0])
    b = T.meter.body
    for _ in range(10):
        d.xfrc_applied[b, :3] = F
        d.xfrc_applied[b, 3:] = np.cross(point - d.xipos[b], F)
        act(w, A, "stand", rest)
    d.xfrc_applied[b] = 0.0
    L = T.meter.momentum(w)
    J = float(np.hypot(L[0], L[1])) / (T.hook_z - z)
    assert abs(J - 25.0) < 0.02 * 25.0, J
    print("meter: an injected 25.00 N s reads %.2f N s" % J)

    w.reset(); hold(w, A)                                                   # nop
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)

    ghost_kick(v=0.3); v = stand()                                          # a slower ghost kick: too weak
    assert v["failed"] == "the kick was too weak" and 5.0 < v["metrics"]["impulse_n_s"] < 20.0, v

    p["max_contact_s"] = 0.03                                               # the bound on the touch: the same ghost
    ghost_kick(); v = stand()                                               # kick (a touch of 0.054 s) under a bound
    p["max_contact_s"] = 0.15                                               # of 0.03 s is a push
    assert v["failed"] == "the bag was pushed, not struck" and v["stages"] == [], v

    ghost_kick(leg="left"); v = stand()                                     # the other leg
    assert v["failed"] == "the bag was touched by something other than the right foot or shin", v
    assert "left_foot" in w.ref.events[-1]["parts"], w.ref.events[-1]

    ghost_kick(hip=-1.6, knee=0.2); v = stand()                             # a kick at hip height: below the band
    assert v["failed"] == "the kick landed outside the marked band" and v["metrics"]["hit_height_m"] < p["zone_low_m"], v

    w.reset()                                                               # walking into the bag: the hands first
    while not w.done:
        act(w, A, "walk", np.r_[0.6, 0.0, 0.0, rest])
    assert verdict(w)["failed"] == "the bag was touched by something other than the right foot or shin", verdict(w)

    ghost_kick(back=0.0); v = stand()                                       # put back where it stood at the start:
    assert v["failed"] == "the bag was touched again after the kick" and v["stages"] == ["strike"], v   # the bag swings back

    ghost_kick(); act(w, A, "stand", rest, 50); move_robot(w, z=0.40)       # a fall after the kick (injection)
    v = stand()
    assert v["failed"] == "fell" and v["stages"] == ["strike"], v
    print("PASS kick-target")


if __name__ == "__main__":
    main()
