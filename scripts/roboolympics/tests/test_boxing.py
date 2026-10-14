"""boxing (v2): the referee says yes to a real punch (the reference solution, through the action interface: 15.7 N s
on the 30 kg bag) and no to every cheap exit; and the impulse meter is checked against a known impulse.

The meter: the referee measures the blow as the change of the bag's angular momentum about its hook during the touch,
divided by the depth of the hit below the hook. Checked here (1) against an INJECTED known impulse: a force of 150 N
for 0.10 s (15 N s) applied to the hanging bag at the band's middle reads 15 N s within 2 %; (2) against the contact
force between fist and bag integrated over the reference punch's touch: within 5 %. Negatives, all real motions
unless marked: do nothing; a slow extension of the arm (a push); the arm's punch without the trunk (too weak); a
punch whose fist arrives side-on (not the knuckle part); the other fist; a jab below the band; walking into the bag;
the reference punch without the walking policy afterwards (the robot topples: a fall after the strike); the arm left
out after the punch (no guard); the bag touched again (injection: the robot is moved into the swinging bag)."""
import importlib.util
import json
import os
import tempfile

import numpy as np

import rcb_rfo
from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "boxing"
OTHER = "the bag was touched by something other than the knuckle part of the right fist"


def session(**params):
    inst = rcb_rfo.make_instance(FAMILY, 0, params or None)
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(inst, f)
    return rcb_rfo.Session(path)


def oracle():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "oracles", FAMILY, "oracle.py")
    spec = importlib.util.spec_from_file_location("oracle_" + FAMILY, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    orc = oracle()
    s = session()
    w = s.world
    T, p = w.task, w.task.p
    text = " ".join([T.sentence, T.rules, T.venue, T.difficulty] + T.deviations)
    assert all("{" + k + "}" in text for k in p), [k for k in p if "{" + k + "}" not in text]
    assert s.instance["robot"] == "unitree_h1" and len(s.instance["deviations"]) >= 4
    assert abs(w.m.body_subtreemass[T.meter.body] - 30.0) < 1e-9 and abs(T.hook_z - 2.25) < 1e-9

    orc.solve(s)                                                            # positive: the reference punch
    st = s.status()
    assert st["success"] and st["stages"] == ["strike", "guard"], st
    m = st["metrics"]
    assert m["impulse_n_s"] >= p["min_impulse_n_s"] and m["contact_s"] <= p["max_contact_s"], st
    assert p["zone_low_m"] <= m["hit_height_m"] <= p["zone_high_m"], st
    assert abs(m["impulse_n_s"] - m["contact_impulse_n_s"]) < 0.05 * m["impulse_n_s"], st   # the meter, check (2)
    print("reference punch: %.2f N s (contact force integral %.2f N s), touch %.3f s, at %.2f m"
          % (m["impulse_n_s"], m["contact_impulse_n_s"], m["contact_s"], m["hit_height_m"]))
    sha, rows = st["state_sha"], np.array(s.rows)
    assert s.replay()["success"]                                            # ... and its rows replayed in a fresh world
    s.reset(); orc.solve(s)
    assert s.status()["state_sha"] == sha and np.array_equal(np.array(s.rows), rows)    # determinism
    for kw in (dict(turn=1.05), dict(wind=-0.43), dict(settle=90)):         # not on a knife edge
        s.reset(); orc.solve(s, **kw)
        assert s.status()["success"], (kw, s.status())

    s.reset(); orc.solve(s, recover="stand")                                # the same punch, no walking policy after
    st = s.status()                                                         # it: the robot topples
    assert st["failed"] == "fell" and st["stages"] == ["strike"], st
    s.reset(); orc.solve(s, wind=0.0, turn=0.0)                             # the arm alone, no trunk turn: too weak
    st = s.status()
    assert st["failed"] == "the punch was too weak" and 2.0 < st["metrics"]["impulse_n_s"] < 9.0, st
    print("arm-only punch: %.2f N s" % st["metrics"]["impulse_n_s"])
    s.reset(); orc.solve(s, wind=-0.35, n=9)                                # a punch that arrives side-on
    assert s.status()["failed"] == OTHER, s.status()
    s.reset(); orc.solve(s, fist="left")                                    # the other fist
    st = s.status()
    assert st["failed"] == OTHER and "left_hand" in st["events"][-1]["parts"], st

    w, A = make(FAMILY)
    T = w.task
    names = [j[:-6] for j in w.L.JOINTS[12:]]

    def row(typ="stand", cmd=(0, 0, 0), **arm):
        r = A.current(typ, w)
        off = 3 if typ == "walk" else 0
        if typ == "walk":
            r[0:3] = cmd
        for k, v in arm.items():
            r[off + names.index(k)] = v
        return r

    # the meter against an injected known impulse: 150 N for 0.10 s on the bag at the band's middle (check (1))
    z = 0.5 * (p["zone_low_m"] + p["zone_high_m"])
    point = np.array([p["bag_distance_m"] - p["bag_diameter_m"] / 2, 0.0, z])
    F = np.array([150.0, 0.0, 0.0])
    b = T.meter.body
    for _ in range(10):
        w.d.xfrc_applied[b, :3] = F
        w.d.xfrc_applied[b, 3:] = np.cross(point - w.d.xipos[b], F)
        act(w, A, "stand", row())
    w.d.xfrc_applied[b] = 0.0
    L = T.meter.momentum(w)
    J = float(np.hypot(L[0], L[1])) / (T.hook_z - z)
    assert abs(J - 15.0) < 0.02 * 15.0, J
    print("meter: an injected 15.00 N s reads %.2f N s" % J)

    w.reset(); hold(w, A)                                                   # nop
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)

    w.reset()                                                               # a slow extension from the guard: a push
    for i in range(80):
        act(w, A, "stand", row(right_elbow_pitch=-0.94 * min(1.0, (i + 1) / 50)))
    i = 0
    while not w.done:
        f = min(1.0, (i + 1) / 150)
        act(w, A, "stand", row(right_shoulder_pitch=-1.45 * f, right_elbow_pitch=-0.94 + 2.39 * f))
        i += 1
    v = verdict(w)
    assert v["failed"] == "the bag was pushed, not struck" and v["stages"] == [], v

    w.reset()                                                               # a jab with the forearm level: below
    i = 0                                                                   # the band
    while not w.done and i < 200:
        th = min(1.3, 0.09 * (i + 1))
        act(w, A, "stand", row(right_shoulder_pitch=-th, right_elbow_pitch=th))
        i += 1
    v = verdict(w)
    assert v["failed"] == "the punch landed outside the marked band" and v["metrics"]["hit_height_m"] < p["zone_low_m"], v

    w.reset()                                                               # walking into the bag, the arms back
    while not w.done:
        act(w, A, "walk", row("walk", cmd=(0.6, 0, 0), right_elbow_pitch=1.5, left_elbow_pitch=1.5,
                              right_shoulder_pitch=0.8, left_shoulder_pitch=0.8, right_shoulder_roll=-0.3,
                              left_shoulder_roll=0.3))
    assert verdict(w)["failed"] == OTHER, verdict(w)

    s.reset()                                                               # the reference punch, then the arm is
    step, tgt = s.step, {}                                                  # put out again and left there: no guard

    def no_guard(typ, r):
        if s.world.ref.has("strike") and typ == "walk":
            if not tgt:
                tgt["t"] = s.world.t
            if s.world.t - tgt["t"] > 1.5:                                  # (once the bag has swung back)
                r = np.array(r, dtype=float)
                r[3 + names.index("right_shoulder_pitch")], r[3 + names.index("right_elbow_pitch")] = 0.3, 1.5
        return step(typ, r)
    s.step = no_guard
    orc.solve(s)
    st = s.status()
    assert st["failed"] == "time" and st["stages"] == ["strike"], st

    s = session(); orc_done = []                                            # the reference punch, then the robot is
    step = s.step                                                           # moved into the swinging bag (injection)

    def into_bag(typ, r):
        out = step(typ, r)
        if s.world.ref.has("strike") and not orc_done:
            orc_done.append(move_robot(s.world, x=0.45))
        return out
    s.step = into_bag
    orc.solve(s)
    st = s.status()
    assert st["failed"] == "the bag was touched again after the punch" and st["stages"] == ["strike"], st
    print("PASS boxing")


if __name__ == "__main__":
    main()
