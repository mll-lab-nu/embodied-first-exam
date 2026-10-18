"""hurdles-freestanding (50 m, four official 1.067 m hurdles standing free on the track, the H1-2).

The hurdle: its toppling force is measured in physics (a horizontal force at the centre of the top bar's top edge,
increased slowly, tips it at 3.6-4.0 kgf; held at 3.6 kgf it stands, at 4.0 kgf it falls; it does not slide first),
and the four hurdles stand still for the whole episode (no creep, no jitter). The referee says no to standing still,
to walking into the first hurdle (the forearms and the trunk push it over), to standing on its top bar (climbing
it), to pushing it along the track with a foot (bulldozing) or sideways out of the lane before going over it, to a
hurdle moved by anything else, to knocking it down in the air and going through below its top, to a step over a
hurdle already gone (the pelvis crossing with the feet on the track), to the feet passing under the bar, to a foot or
a leg beside the hurdle, to leaving the lane and to lying on the track; it says yes to a hurdle that a foot knocks down on the way over (the hurdle really falls and lies on the track), also when an arm
brushed it shortly before.

The positive is an INJECTION, not a solution: at each hurdle the robot is put 1.1 m before it by hand, stands there
on its own, and is given a velocity by hand (rfo.testing.kick_robot: 2.0 m/s forward, 5.5 m/s up) so that it really
flies over the standing hurdle (pelvis and feet above the bar, nothing touched) and really comes down behind it;
just above the track its velocity is taken away by hand. Between the hurdles it is moved by hand; the last metre to
the finish line it really walks (the walking policy). The legal knock-down is the same injection, lower and closer,
with the lead leg tucked up by the robot's own motors in the air: the trailing foot really strikes the top bar and
the hurdle really tips over and falls (the robot, tripped, falls with it)."""
import mujoco
import numpy as np

from rfo.testing import act, hold, kick_robot, make, move_robot, verdict
from rfo.tasks.hurdles_freestanding import balance_deg

KGF = 9.80665


def ghost_jump(w, A, i, vel=(2.0, 0.0, 5.5), back=1.1, settle=1.0):
    """Injected: put `back` m before hurdle i, stand, fly with `vel`, be stopped just above the track, stand."""
    move_robot(w, x=w.task.hurdle_x()[i] - back, y=0.0, z=w.robot.stand_z, yaw=0.0)
    w.d.qvel[w.robot.fv:w.robot.fv + 6] = 0.0
    hold(w, A, 0.5)
    kick_robot(w, vel)
    while not w.done:
        hold(w, A, 0.01)
        if w.d.qvel[w.robot.fv + 2] < 0 and w.pelvis()[2] < w.robot.stand_z + 0.06:
            w.d.qvel[w.robot.fv:w.robot.fv + 6] = 0.0
            break
    hold(w, A, settle)


def trail_jump(w, A, i, vel=(2.5, 0.0, 4.6), back=0.9, settle=3.0, wait=0.5):
    """Injected like ghost_jump, but in the air the robot's own motors tuck the lead (left) leg up (hip pitch -1.2,
    knee 1.4 rad, `joints`), so that the trailing (right) foot is the lowest point going over the bar."""
    move_robot(w, x=w.task.hurdle_x()[i] - back, y=0.0, z=w.robot.stand_z, yaw=0.0)
    w.d.qvel[w.robot.fv:w.robot.fv + 6] = 0.0
    hold(w, A, wait)
    kick_robot(w, vel)
    q = np.r_[w.robot.rest, 0, 0].copy()
    q[1], q[3] = -1.2, 1.4
    while not w.done:
        act(w, A, "joints", q)
        if w.d.qvel[w.robot.fv + 2] < 0 and w.pelvis()[2] < w.robot.stand_z + 0.06:
            w.d.qvel[w.robot.fv:w.robot.fv + 6] = 0.0
            break
    hold(w, A, settle)


def all_four(w, A):
    hold(w, A, 0.1)
    for i in range(4):
        ghost_jump(w, A, i)
    D = w.task.p["distance_m"]
    move_robot(w, x=D - 1.2, y=0.0, z=w.robot.stand_z, yaw=0.0); hold(w, A, 0.5)
    walk_on(w, A)


def walk_on(w, A, vx=0.6):
    up = w.robot.rest[12:]
    while not w.done:                                                    # a real walk, straight along the lane
        _, y, _, yaw = w.pelvis()
        act(w, A, "walk", np.r_[vx, np.clip(-2 * y, -0.3, 0.3), np.clip(-2 * yaw, -1, 1), up, 0, 0])


def push_top_bar(w, i, kgf, seconds, until=None):
    """Physics only (the referee would end the episode once the hurdle has moved): a horizontal force towards +x at
    the centre of hurdle i's top bar's top edge, applied at every physics step for `seconds`; kgf a number or a
    function of the time pushed; stops early when until() is true. Returns the force at the end."""
    T, p = w.task, w.task.p
    bar, body = T.bar_geom[i], T.hbody[i]
    up = np.array([0.0, 0.0, p["bar_height_m"] / 2])
    f = kgf
    for k in range(int(round(seconds / w.PHYS_DT))):
        f = kgf(k * w.PHYS_DT) if callable(kgf) else kgf
        w.d.qfrc_applied[:] = 0
        top = w.d.geom_xpos[bar] + w.d.geom_xmat[bar].reshape(3, 3) @ up
        mujoco.mj_applyFT(w.m, w.d, np.array([f * KGF, 0, 0]), np.zeros(3), top, body, w.d.qfrc_applied)
        mujoco.mj_step(w.m, w.d)
        if until is not None and until():
            break
    w.d.qfrc_applied[:] = 0
    return f


def toppling_force(w):
    """The force (kgf) at which a slowly increasing push (0.01 kgf/s from 3.5 kgf) tips the first hurdle (its rear
    feet lift: 0.2 degrees), and how far its front feet have slid by then (m)."""
    T = w.task
    w.reset()
    qa, _ = w.free["hurdle1"]
    x0 = float(w.d.qpos[qa])
    F = push_top_bar(w, 0, lambda t: 3.5 + 0.01 * t, 60.0, until=lambda: T.tilt_deg(w, 0) >= 0.2)
    return F, float(w.d.qpos[qa]) - x0


def main():
    w, A = make("hurdles-freestanding")
    T, p = w.task, w.task.p
    xs = T.hurdle_x()
    assert xs[0] == 13.72 and xs[3] == 41.14 and abs(p["distance_m"] - xs[3] - 8.86) < 1e-9 and len(xs) == 4
    assert (p["hurdle_height_m"], p["bar_height_m"], p["base_length_m"]) == (1.067, 0.07, 0.70)
    assert 1.18 <= p["hurdle_width_m"] <= 1.20
    m, d = w.m, w.d
    bar, body = T.bar_geom[0], T.hbody[0]
    assert abs(d.geom_xpos[bar][2] + p["bar_height_m"] / 2 - 1.067) < 1e-4                # the top edge
    assert abs(d.geom_xpos[bar][0] - m.geom_size[bar][0] - xs[0]) < 1e-4                   # its face on the mark
    lo = np.min([d.geom_xpos[g][0] - np.max(np.abs(d.geom_xmat[g].reshape(3, 3)) @ m.geom_size[g])
                 for g in range(m.ngeom) if m.geom_bodyid[g] == body and m.geom_type[g] == mujoco.mjtGeom.mjGEOM_BOX])
    assert xs[0] + 0.05 - lo <= 0.70 + 1e-6, xs[0] + 0.05 - lo                              # the base at most 0.70 m
    assert abs(m.body_subtreemass[body] - p["hurdle_mass_kg"]) < 1e-6 and m.body_subtreemass[body] >= 10.0
    assert abs(T.toppling_force_kgf() - p["toppling_force_kgf"]) < 1e-9 and 3.6 <= p["toppling_force_kgf"] <= 4.0
    assert abs(balance_deg(p) - p["balance_deg"]) < 1.0
    # the toppling force, in physics: a slowly increasing push tips it within the rule book's 3.6-4.0 kgf, before it
    # slides; held at 3.6 kgf it stands, at 4.0 kgf it goes over and falls
    F, slid = toppling_force(w)
    assert 3.6 <= F <= 4.0 and abs(F - p["toppling_force_kgf"]) < 0.05 and abs(slid) < 0.002, (F, slid)
    print(f"  toppling force in physics: {F:.3f} kgf (statics {p['toppling_force_kgf']} kgf), slid {slid * 1e3:.2f} mm")
    for kgf, falls in ((3.6, False), (4.0, True)):                       # held 3 s, then let go for 2 s
        w.reset()
        tilt = []
        push_top_bar(w, 0, kgf, 3.0, until=lambda: tilt.append(T.tilt_deg(w, 0)) and False)
        push_top_bar(w, 0, 0.0, 2.0)
        assert (T.tilt_deg(w, 0) > 80.0) == falls and (falls or max(tilt) < 0.5), (kgf, max(tilt), T.tilt_deg(w, 0))
    print("  held at 3.6 kgf it stands, at 4.0 kgf it falls; it falls on by itself past", p["balance_deg"], "degrees")
    w.reset(); hold(w, A)                                                 # nop; the hurdles stand still meanwhile
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [] and w.t == 140.0, (v, w.t)
    creep = max(T.displacement(w, i) for i in range(4))
    jitter = max(float(np.abs(w.d.qvel[w.free[f"hurdle{i + 1}"][1]:][:6]).max()) for i in range(4))
    assert creep < 1e-4 and jitter < 1e-6, (creep, jitter)
    print(f"  140 s standing: the hurdles moved at most {creep * 1e6:.1f} um, speed {jitter:.1e} m/s at the end")
    w.reset(); all_four(w, A)                                             # positive (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == T.stages and "hurdles_down" not in v["metrics"], v
    assert max(T.displacement(w, i) for i in range(4)) < 1e-3                               # no hurdle touched
    print("  four injected clearances:", v["metrics"])
    sha = w.state_sha()
    w.reset(); all_four(w, A)
    assert w.state_sha() == sha                                                             # determinism
    # the trailing foot strikes the top bar in the air: the hurdle really tips over and falls (the robot with it);
    # allowed (TR 22.7)
    w.reset(); hold(w, A, 0.1); trail_jump(w, A, 0)
    v = verdict(w)
    knock = next(e for e in w.ref.events if e["ev"] == "hurdle_knocked")
    assert v["stages"] == ["hurdle 1"] and v["failed"] is None and v["metrics"]["hurdles_down"] == 1, v
    assert T.tilt_deg(w, 0) > 80.0 and knock["last_touch"][1] == ["right_foot"], (T.tilt_deg(w, 0), knock)
    print("  the trailing foot knocks the first hurdle down:", knock, "lying at", round(T.tilt_deg(w, 0), 1), "deg")
    sha = w.state_sha()
    w.reset(); hold(w, A, 0.1); trail_jump(w, A, 0)
    assert w.state_sha() == sha                                                             # determinism (a knock)
    # an arm brushes the hurdle (it stays), then, 0.34 s later, the lead foot knocks it in the air: the latest touch
    # was the foot, so no fault for the hand
    w.reset(); hold(w, A, 0.1)
    move_robot(w, x=xs[0] - 0.45); hold(w, A, 0.05)
    assert T.trackers["upper_t"][0] is not None and T.displacement(w, 0) < p["displaced_m"]
    move_robot(w, x=xs[0] - 0.85, y=0.0, z=w.robot.stand_z, yaw=0.0)
    w.d.qvel[w.robot.fv:w.robot.fv + 6] = 0.0
    trail_jump(w, A, 0, back=0.85, settle=1.0, wait=0.0)
    v = verdict(w)
    knock = next(e for e in w.ref.events if e["ev"] == "hurdle_knocked")
    assert v["failed"] is None and v["stages"] == ["hurdle 1"] and knock["last_touch"][1] == ["left_foot"], (v, knock)
    assert knock["t"] - T.trackers["upper_t"][0] < p["touch_window_s"], knock
    # climbing: standing on the top bar (the hurdle carries the robot), then down beyond it
    w.reset(); hold(w, A, 0.1)
    move_robot(w, x=T.planes[0] - 0.018, z=p["hurdle_height_m"] + w.robot.stand_z + 0.005)
    w.d.qvel[w.robot.fv:w.robot.fv + 6] = 0.0
    hold(w, A, 1.0)
    v = verdict(w)
    assert v["failed"] == "climbed on the first hurdle" and v["stages"] == [], (v, w.ref.events[-1])
    print("  standing on the top bar:", w.ref.events[-1])
    # cheap exits
    w.reset(); hold(w, A, 0.1); move_robot(w, x=10.5); hold(w, A, 0.5)   # walking on into the first hurdle
    walk_on(w, A, 0.8)
    v = verdict(w)
    assert v["failed"] == "knocked the first hurdle with a hand, an arm or the trunk" and v["stages"] == [], v
    print("  walking into the first hurdle:", w.ref.events[-1])
    # ... also a hurdle already gone over: over the first one, then turned round and walked back into it
    w.reset(); hold(w, A, 0.1); ghost_jump(w, A, 0); assert verdict(w)["stages"] == ["hurdle 1"]
    move_robot(w, x=xs[0] + 2.0, y=0.0, yaw=np.pi); hold(w, A, 0.5)
    up = w.robot.rest[12:]
    while not w.done and w.t < 30.0:
        _, y, _, yaw = w.pelvis()
        turn = np.clip(2 * np.angle(np.exp(1j * (np.pi - yaw))), -1, 1)       # facing -x: body y is -y
        act(w, A, "walk", np.r_[0.8, np.clip(2 * y, -0.3, 0.3), turn, up, 0, 0])
    v = verdict(w)
    assert v["failed"] == "knocked the first hurdle with a hand, an arm or the trunk" and v["stages"] == ["hurdle 1"], v
    # bulldozing: a foot pushes the hurdle along the track by its base (the robot moved on by hand, 0.5 m/s)
    w.reset(); hold(w, A, 0.1)
    move_robot(w, x=xs[0] - 0.84, y=0.38); hold(w, A, 0.3)                # the left foot 3 cm behind the left base
    while not w.done and w.t < 6.0:
        move_robot(w, x=float(w.pelvis()[0]) + 0.005); hold(w, A, 0.01)
    v = verdict(w)
    assert v["failed"] == "displaced the first hurdle before going over it", (v, w.ref.events[-1])
    assert w.ref.events[-1]["last_touch"][1] == ["left_foot"], w.ref.events[-1]
    print("  a foot shoves the first hurdle along the track:", w.ref.events[-1])
    # ... or sideways, out of the lane (the robot moved across by hand into the base's side)
    w.reset(); hold(w, A, 0.1)
    move_robot(w, x=xs[0] - 0.55, y=0.30); hold(w, A, 0.3)                # the left foot inside the left base
    while not w.done and w.t < 6.0:
        move_robot(w, y=float(w.pelvis()[1]) + 0.005); hold(w, A, 0.01)
    v = verdict(w)
    assert v["failed"] == "displaced the first hurdle before going over it", (v, w.ref.events[-1])
    assert w.ref.events[-1]["last_touch"][1] == ["left_foot"], w.ref.events[-1]
    print("  a foot pushes the first hurdle out of the lane:", w.ref.events[-1])
    # moved by something else (as if another hurdle were shoved into it): put 0.2 m on by hand
    w.reset(); hold(w, A, 0.1)
    qa, _ = w.free["hurdle2"]
    w.d.qpos[qa] += 0.2; hold(w, A, 0.05)
    assert verdict(w)["failed"] == "displaced the second hurdle before going over it", verdict(w)
    # knocked down in the air (legal), but a foot goes through below the top of the bar
    w.reset(); hold(w, A, 0.1); ghost_jump(w, A, 0, vel=(2.0, 0.0, 4.4), back=0.95, settle=1.0)
    v = verdict(w)
    assert v["failed"] == "went under the top of the first hurdle" and [e["ev"] for e in w.ref.events][-2:] == \
        ["hurdle_knocked", "fail"], w.ref.events[-3:]
    print("  knocked down in the air, through below the top:", w.ref.events[-1])
    # a step over a hurdle already gone from its mark, the feet on the track: the first hurdle put 1.5 m on by hand
    # and taken as a legal knock (injected), then the robot moved over the hurdle's plane by hand, standing on its
    # feet (its ankles stand behind its pelvis: the pelvis crosses first)
    w.reset(); hold(w, A, 0.1)
    qa, _ = w.free["hurdle1"]
    T.trackers["leg_t"][0] = w.ref.time
    w.d.qpos[qa] += 1.5; hold(w, A, 0.05)
    assert T.trackers["moved"] == [0] and verdict(w)["failed"] is None, (T.trackers["moved"], verdict(w))
    move_robot(w, x=T.planes[0] - 0.1); hold(w, A, 0.3)
    while not w.done and w.t < 3.0:
        move_robot(w, x=float(w.pelvis()[0]) + 0.005); hold(w, A, 0.01)
    v = verdict(w)
    assert v["failed"] == "went over the first hurdle without a jump" and v["stages"] == [], (v, w.ref.events[-1])
    assert {"left_foot", "right_foot"} & set(w.ref.events[-1]["parts"]), w.ref.events[-1]
    print("  stepping over a hurdle already down, feet on the track:", w.ref.events[-1])
    # the pelvis high enough (lifted by hand), the feet under the bar
    w.reset(); hold(w, A, 0.1)
    move_robot(w, x=xs[0] - 0.4, z=1.5); hold(w, A, 0.01); move_robot(w, x=xs[0] + 0.4, z=1.5); hold(w, A, 0.05)
    v = verdict(w)
    assert v["failed"] == "went under the top of the first hurdle" and "foot" in w.ref.events[-1]["what"], \
        (v, w.ref.events[-1])
    # high enough, but the left foot outside the bar's end
    w.reset(); hold(w, A, 0.1)
    move_robot(w, x=xs[0] - 0.4, y=0.45, z=2.3); hold(w, A, 0.01)
    move_robot(w, x=xs[0] + 0.4, y=0.45, z=2.3); hold(w, A, 0.05)
    v = verdict(w)
    assert v["failed"] == "went beside the first hurdle" and w.ref.events[-1]["what"] == "left foot", \
        (v, w.ref.events[-1])
    # a leg beside the hurdle below its top while the body goes over (TR 22.6.1)
    w.reset(); hold(w, A, 0.1); ghost_jump(w, A, 0); assert verdict(w)["stages"] == ["hurdle 1"]
    move_robot(w, x=T.planes[1] - 0.06, y=0.85, z=w.robot.stand_z); hold(w, A, 0.05)
    v = verdict(w)
    assert v["failed"] == "a leg beside the second hurdle below its top" and v["stages"] == ["hurdle 1"], v
    w.reset(); hold(w, A, 0.2); move_robot(w, y=0.7); hold(w, A, 0.05)                    # out of the lane
    assert verdict(w)["failed"] == "left the lane", verdict(w)
    w.reset(); hold(w, A, 0.5); move_robot(w, x=5.0, z=0.30)             # lying on the track, face down along the lane
    w.d.qpos[w.robot.fq + 3:w.robot.fq + 7] = [np.cos(np.pi / 4), 0.0, np.sin(np.pi / 4), 0.0]
    hold(w, A)
    assert verdict(w)["failed"] == "did not finish: down for too long" and w.t < 20.0, (verdict(w), w.t)
    print("PASS hurdles-freestanding")


if __name__ == "__main__":
    main()
