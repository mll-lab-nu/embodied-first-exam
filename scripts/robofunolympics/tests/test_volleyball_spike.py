"""volleyball-spike (v2: the official court and net, a set to position 4 that comes down 0.5 m from the 2.43 m net from
a 4.5 m apex): the referee says no to standing still (the set lands), to the two v1 exploits (in the air without a
jump, and a fist that is only held in the ball's path), to a strike from the floor, below the height of the net or
before the ball's highest point, to a ball that leaves upward, goes into the net, outside the antenna or out, to a
second touch, a held ball, a touched net, a foot beyond the centre line and a fall after the landing; yes to a ball
struck by a hand above the net's height in a real flight phase of a jump, downward and faster than it came, into the
opponent's court, and a landing on the feet.

The positive is an INJECTION: no jumping controller exists for the H1-2 (it reaches 2.24 m standing; the net is at
2.43 m). Real: the right arm is really held up (stand mode); the set really flies from the setter's place and comes
down on the robot's fist while the robot is in the air, 2.7 m above the floor; the struck ball really crosses the net
and lands in the opponent's court; the robot really comes down on its feet and stands. Injected: the jump (at 0.30 s
before the ball arrives the robot is moved so that its raised fist is under the ball's path, 0.5 m from the net, and
given 3.2 m/s upwards: a flight of 0.6 s that lifts the pelvis 0.5 m), the ball's velocity at the contact (12.4 m/s
forward and down: what a swinging arm would have given it; the ball is also moved 10 cm forward, off the fist), and a
softened touchdown (the robot's fall is slowed to 0.5 m/s just above the floor: no landing controller is scripted)."""
import numpy as np

from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

FAMILY = "volleyball-spike"
ARM_UP = np.r_[0.0, [0.0] * 7, [-2.7, -0.2, 0.0, 1.2, 0.0, 0.0, 0.0]]          # the right fist above the forehead
SPIKE = (12.0, 0.5, -3.0)
T_BALL = 1.256                         # s after the set: the ball is 2.8 m high, 2.5 m ahead, straight in front
BALL_XY = (2.49, -0.02)


def spike(w, A, vel=SPIKE, jump=3.2, lift=0.0, before=0.30, align=True, ball=None, after=None, soft=True, arm=ARM_UP):
    """Right arm up (1.5 s, stand mode). `before` seconds ahead of the ball's arrival: the robot is moved so that its
    right fist is under the ball's path (align), given `jump` m/s upwards and/or lifted by `lift` m. ball(w): called
    at that moment instead of waiting for the set (it places the ball). At the ball's first contact with the robot its
    velocity is set to `vel` (None: left alone). after(w): called once, 0.05 s after the spike was judged. soft: the
    robot's descent is slowed to 0.5 m/s once, just above the floor."""
    r, d = w.robot, w.d
    rest = r.rest[12:].copy()
    t_go = w.task.p["launch_time_s"] + T_BALL - before
    i, gone, hit, t_spike, landed = 0, False, False, None, not soft
    while not w.done:
        i += 1
        act(w, A, "stand", np.r_[rest + min(1.0, i * w.CONTROL_DT / 1.5) * (arm - rest), 0, 0])
        if w.done:
            break
        if not gone and w.t >= t_go - 1e-9:
            gone = True
            x, y, z, _ = w.pelvis()
            palm = d.site_xpos[r.palm["right"]]
            if align:
                move_robot(w, x=x + BALL_XY[0] - palm[0], y=y + BALL_XY[1] - palm[1])
            if lift:
                move_robot(w, z=z + lift)
                kick_robot(w, vel=(0.0, 0.0, 0.0))
            if jump:
                kick_robot(w, vel=(0.0, 0.0, jump))
            if ball is not None:
                ball(w)
            continue
        st = w.task.trackers["strike"]
        if vel is not None and not hit and st.phase >= 1:
            hit = True
            w.put("ball", w.pos("ball") + [0.10, 0.0, 0.02], vel=vel)       # off the fist, to its front
        if gone and not landed and d.qvel[r.fv + 2] < -0.5 and d.qpos[r.fq + 2] < r.stand_z + 0.03:
            landed = True
            d.qvel[r.fv + 2] = -0.5
        if after is not None and w.ref.has("spike"):
            t_spike = w.t if t_spike is None else t_spike
            if w.t - t_spike >= 0.05:
                after(w)
                after = None


def on_fist(dz=0.25, v=(0.0, 0.0, -3.0), dx=0.03):
    """A ball put above the right fist (injected), coming down on it."""
    def place(w):
        w.put("ball", w.d.site_xpos[w.robot.palm["right"]] + [dx, 0.0, dz] + np.array([0.0, 0.0, 0.0]), vel=v)
    return place


def main():
    w, A = make(FAMILY)
    p, g, m = w.task.p, w.task.geometry(), w.m
    # the official court as built: the net 3 m ahead with its top at 2.43 m, the left side line and antenna 1 m to the left
    mesh = m.geom("net_mesh")
    assert abs(w.d.geom_xpos[mesh.id][2] + mesh.size[2] - 2.43) < 1e-6 and abs(w.d.geom_xpos[mesh.id][0] - 3.0) < 1e-6
    assert abs(w.d.geom_xpos[m.geom("net_antennaL").id][1] - 1.0) < 1e-6
    assert abs(m.geom("ball").size[0] - 0.105) < 1e-9 and abs(m.body("ball").mass[0] - 0.27) < 1e-9
    ball = m.geom("ball").id
    assert m.geom_contype[ball] == 0 and m.geom_conaffinity[ball] == 0      # the waiting ball cannot be touched

    typ, row = A.hold(w)                                                   # nop: the set comes down near the net
    apex, low = 0.0, None
    while not w.done:
        w.step(A.to_raw(typ, row, w))
        b = w.pos("ball")
        apex = max(apex, float(b[2]))
        if low is None and w.t > p["launch_time_s"] + 0.7 and b[2] < 2.8:
            low = (w.t - p["launch_time_s"], float(g["centre"][0] - b[0]), float(b[1]))
    v = verdict(w)
    assert v["failed"] == "the ball touched the floor before the spike" and v["stages"] == [], v
    assert abs(apex - 4.5) < 0.03 and abs(low[1] - p["set_off_net_m"]) < 0.03 and abs(low[0] - T_BALL) < 0.02, (apex, low)

    w.reset(); spike(w, A)                                                 # positive (injection, see the docstring)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["spike", "over the net", "in the court", "landing"], v
    ev = {e["stage"]: e for e in w.ref.events if e["ev"] == "stage"}
    assert ev["spike"]["parts"] == ["right_hand"] and ev["spike"]["contact_z"] > p["net_height_m"], ev
    assert ev["spike"]["speed_out"] > ev["spike"]["speed_in"] and v["metrics"]["jump_rise_m"] >= p["jump_rise_m"], (ev, v)
    sha, t_ok, sp, mt = w.state_sha(), w.t, ev["spike"], v["metrics"]
    w.reset(); spike(w, A)
    assert w.state_sha() == sha                                            # the same run again: the same state

    # v1 exploit 1, "a flight without a jump": the robot is in the air (lifted 0.6 m and let go: its pelvis never
    # rises above where the flight began) and strikes the real set above the net, well
    w.reset(); spike(w, A, jump=0.0, lift=0.60, before=0.10)
    v = verdict(w)
    assert v["failed"] == "the strike was not made in a jump" and v["stages"][0] == "spike", v
    assert w.ref.events[-1]["pelvis_rise_m"] < 0.01, w.ref.events[-1]

    # ... and as v1 had it: the legs drawn up from a stand (joint targets, real), a ball dropped on the raised fist
    w.reset()
    rest, t_tuck = w.robot.rest[12:].copy(), p["launch_time_s"] + 0.9
    tuck = np.array([0.0, -1.3, 0.0, 2.0, -0.7, 0.0] * 2)
    i, air, placed = 0, 0, False
    while not w.done:
        i += 1
        up = rest + min(1.0, i * w.CONTROL_DT / 1.5) * (ARM_UP - rest)
        if w.t < t_tuck:
            act(w, A, "stand", np.r_[up, 0, 0])
        else:
            act(w, A, "joints", np.r_[tuck, up, 0, 0])
        air += int(w.t > t_tuck and w.task.trackers["flights"].air)
        if not placed and air >= 2:                         # in the "flight": a ball 3 m/s faster down than the fist
            placed = True
            vr = w.d.qvel[w.robot.fv:w.robot.fv + 3]
            on_fist(dz=0.20, v=(vr[0], vr[1], vr[2] - 3.0))(w)
    v = verdict(w)
    assert air >= 2 and v["failed"] == "the ball was struck below the height of the net" and v["stages"] == [], (air, v)

    # v1 exploit 2: a real flight (the injected jump), but the fist is only held in the ball's path
    w.reset(); spike(w, A, vel=None)
    v = verdict(w)
    assert v["failed"] == "the ball was not spiked: it left the hand upward or slower than it came" and v["stages"] == [], v
    passive = v["metrics"]["speed_out_m_s"] / v["metrics"]["speed_in_m_s"]

    w.reset(); spike(w, A, jump=0.0, align=False, ball=on_fist())          # the same strike with both feet on the floor
    v = verdict(w)
    assert v["failed"] == "the ball was struck from the floor" and v["stages"] == [], v

    w.reset(); spike(w, A, jump=1.7, align=False, before=0.0, ball=on_fist(dz=0.45))   # a hop: the fist below the net's top
    v = verdict(w)
    assert v["failed"] == "the ball was struck below the height of the net" and v["stages"] == [], v
    assert 2.2 < w.ref.events[-1]["contact_z"] <= p["net_height_m"], w.ref.events[-1]

    w.reset(); spike(w, A, jump=0.0, align=False, before=T_BALL - 0.10,    # the ball met on its way up
                     ball=on_fist(dz=-0.25, v=(-3.0, 0.0, 2.5), dx=0.35))
    v = verdict(w)
    assert v["failed"] == "the ball was touched before it had passed its highest point" and v["stages"] == [], v

    w.reset(); spike(w, A, vel=(8.0, 0.5, 3.0))                            # faster than it came, but upward
    v = verdict(w)
    assert v["failed"] == "the ball was not spiked: it left the hand upward or slower than it came" and v["stages"] == [], v

    w.reset(); spike(w, A, vel=(6.0, -5.0, -12.0))                         # down into the net
    v = verdict(w)
    assert v["failed"] == "the ball landed outside the opponent's court" and v["stages"] == ["spike"], v
    assert v["metrics"]["landing_x_m"] < g["centre"][0], v

    w.reset(); spike(w, A, vel=(19.5, 0.5, -0.3))                          # over the net and out at the back
    v = verdict(w)
    assert v["failed"] == "the ball landed outside the opponent's court" and v["stages"] == ["spike", "over the net"], v

    w.reset(); spike(w, A, vel=(5.0, 13.0, -1.0))                          # into the antenna
    v = verdict(w)
    assert v["failed"] == "the ball touched an antenna" and v["stages"] == ["spike"], v

    w.reset(); spike(w, A, vel=(3.0, 12.0, -1.0))                          # past the net outside the antenna
    v = verdict(w)
    assert v["failed"] == "the ball did not cross above the net between the antennas" and v["stages"] == ["spike"], v

    w.reset(); spike(w, A, after=on_fist(dz=0.30, v=(0.0, 0.0, -1.0)))     # a second touch
    v = verdict(w)
    assert v["failed"] == "second touch of the ball" and v["stages"][0] == "spike", v

    w2, A2 = make(FAMILY, strike_max_s=0.0005)                             # below a real contact's time: held
    spike(w2, A2, vel=None)
    assert verdict(w2)["failed"] == "the ball was held", verdict(w2)

    w.reset(); spike(w, A, after=lambda w: move_robot(w, x=g["centre"][0] - 0.08))   # a good spike, then into the net
    v = verdict(w)
    assert v["failed"] == "the robot touched the net" and v["stages"][0] == "spike", v

    w.reset(); spike(w, A, after=lambda w: move_robot(w, x=g["centre"][0] + 0.8))    # ... or down beyond the centre line
    v = verdict(w)
    assert v["failed"] == "a foot wholly beyond the centre line" and v["stages"][0] == "spike", v

    w.reset(); spike(w, A, soft=False, after=lambda w: move_robot(w, z=0.30))        # ... or down on the floor
    v = verdict(w)
    assert v["failed"] == "fell" and v["stages"][0] == "spike", v
    print(f"injection: contact {sp['contact_z']} m high, ball in at {sp['speed_in']} m/s, out at {sp['speed_out']} m/s, "
          f"pelvis rise {mt['jump_rise_m']} m, flight {mt['air_s']} s, lands at x = {mt['landing_x_m']} m, standing at "
          f"t = {t_ok:.2f} s; a still fist in a jump returns {passive:.2f} of the ball's speed")
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
