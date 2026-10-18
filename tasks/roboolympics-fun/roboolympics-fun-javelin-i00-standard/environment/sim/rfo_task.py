"""Javelin throw (World Athletics TR 32 and 38): from the runway, throw the men's javelin over the shoulder from behind
the arc so that its head strikes the ground first, inside the sector, at least the qualifying mark away; then leave the
runway behind the arc. Official runway, arc, sector and implement; the Unitree H1-2."""
import math

import mujoco
import numpy as np

from rfo.scene import HITTABLE, VISUAL
from rfo.task import TaskBase

# The implement's model (the numbers of TR 38 that are ranges are fixed inside their range):
SHAFT_R, TIP_R = 0.0125, 0.006               # collision radii: the shaft (25 mm; TR 38: 25-30 mm at its thickest), the head
I_AXIAL, I_TRANSVERSE = 6.3e-5, 0.42         # kg m^2 about the centre of gravity (transverse: Hubbard and Rust 1984)
# Flight in air: MuJoCo's ellipsoid fluid model on one ellipsoid of the javelin's length whose centre, the centre of
# pressure, lies CP_BEHIND_CG behind the centre of gravity. Coefficients (blunt drag, slender drag, angular drag, Kutta
# lift, Magnus lift) chosen so that at 25 m/s the drag along the shaft is 0.3 N, the drag at an angle of attack 1.6 N
# and the lift at 10 degrees 3.4 N: the order of the published wind-tunnel data for the men's javelin; a 30 m/s release
# at 35 degrees then flies 78 m, a 14 m/s release at 40 degrees 23 m (measured in this model).
CP_BEHIND_CG = 0.25
FLUID = (0.04, 0.008, 1.5, 0.5, 1.0)
LINE_W, ARC_W = 0.05, 0.07                   # TR 32.9: side lines 50 mm, the arc and its end lines 70 mm
RUNWAY = (0.72, 0.25, 0.18, 1)


def set_arm(w, **angles) -> None:
    """Put arm joints (names without "_joint") at angles for t = 0, and their held targets with them."""
    r, d = w.robot, w.d
    for name, v in angles.items():
        i = w.L.JOINTS.index(name + "_joint")
        d.qpos[r.qadr[i]] = v
        r.arb.q_a[i] = r.arb.q_b[i] = v
    mujoco.mj_kinematics(w.m, d)


class Task(TaskBase):
    name = "javelin"
    title = "Athletics: javelin throw"
    category = "throwing-catching-striking"
    robot = "unitree_h1"
    rulebook = ("World Athletics Competition and Technical Rules 2024: TR 32.9 (the javelin runway and its arc), TR "
                "32.12 (the sector), TR 32.14, 32.16, 32.17 and 32.20 (throwing events: failures, the landing, leaving "
                "the runway, the measurement), TR 38.1 (the throw), TR 38.3-38.6 (the men's javelin)")
    deviations = [
        "TR 38.1(a) (the cord grip): the hand holds the javelin at its cord, round its centre of gravity, by a "
        "grip switched on and off, not by fingers; it is released when the grip is switched off. \"Over the shoulder "
        "or upper part of the throwing arm\" is judged at the release: the grip's centre must then be at least "
        "{release_above_shoulder_m} m higher than the throwing shoulder's joint.",
        "TR 38.1(c): \"turned completely around\" is judged as the chest's heading more than {back_turn_deg} degrees "
        "away from the throwing direction at any time before the release.",
        "TR 38.3-38.6: the javelin is one rigid body (no bending or vibration) whose head does not stick in the ground; "
        "the mark is the point where the head first touches the ground.",
        "Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model with coefficients of the order of the "
        "published wind-tunnel data, the centre of pressure " + f"{CP_BEHIND_CG} m behind the centre of gravity), "
        "still air, no wind. The model's drag does not grow with the angle of attack as a real javelin's does: a "
        "javelin released nose-high flies up to a fifth farther here than it would.",
        "TR 32.15 (interrupting a trial, laying the implement down): not modelled; the first release is the throw, "
        "and the javelin cannot be gripped again.",
        "TR 32.14 names no fall: here a fall ends the trial as a failure, as in every task of this benchmark; the "
        "trial ends when the robot has left the runway correctly and stands.",
        "TR 25.17 (one minute for a trial): the whole trial, leaving the runway included, has {time_limit_s} s.",
        "The qualifying mark of {qualifying_mark_m} m is this benchmark's (a boys' school standard for the 800 g "
        "javelin); the rule book only measures.",
    ]
    time_limit_s = 60.0
    start = (-2.0, 0.0, 0.0)
    stages = ["release", "landing", "exit"]
    fall_z = 0.50
    params = dict(javelin_mass_kg=0.800, javelin_length_m=2.65, javelin_cg_from_tip_m=0.98, javelin_head_m=0.29,
                  runway_width_m=4.0, runway_length_m=30.0, arc_radius_m=8.0, exit_line_m=4.0,
                  qualifying_mark_m=20.0, release_above_shoulder_m=0.0, back_turn_deg=135.0, retouch_grace_s=0.20,
                  stand_s=1.0, fall_pelvis_m=0.50)

    sentence = ("Throw the javelin in your right hand over the shoulder from behind the arc so that its head strikes "
                "the ground first, inside the sector, at least {qualifying_mark_m} m from the arc, then leave the "
                "runway behind the arc and stand.")
    rules = ("The men's javelin ({javelin_mass_kg} kg, {javelin_length_m} m long, its centre of gravity "
             "{javelin_cg_from_tip_m} m from the tip, a metal head of {javelin_head_m} m) is gripped at its cord, at "
             "the centre of gravity, by your right hand. The runway is {runway_width_m} m wide between the inner "
             "edges of its side lines and {runway_length_m} m long; it ends at the arc, a white strip whose inner edge "
             "is a circle of {arc_radius_m} m radius round a point on the runway's centre line; short white lines run "
             "outwards from the arc's two ends at right angles to the side lines. The sector is bounded by the two "
             "lines from the arc's centre through the arc's ends (28.96 degrees between them). The throw: you let go "
             "of the javelin (once: it cannot be gripped again) while the grip's centre is at least "
             "{release_above_shoulder_m} m higher than your right shoulder joint. It is valid only if the head touches "
             "the ground before any other part of the javelin, at a point inside the sector lines (on a line is out). "
             "It is measured from that point to the inner edge of the arc along the line through the arc's centre. "
             "You succeed when a valid throw measures at least {qualifying_mark_m} m and you have then left the "
             "runway correctly and stood for {stand_s} s. Leaving correctly: after the javelin has landed, your first "
             "touch of a side line or of the ground outside the runway is behind the arc's end lines, or you touch "
             "the ground {exit_line_m} m or more behind the arc's ends. Standing: only your feet on the ground, the "
             "torso within about 20 degrees of upright, the pelvis slower than 0.35 m/s. You fail if, at any time "
             "before that, any part of you touches the arc, its end lines or the ground beyond them; if you touch a "
             "side line or the ground outside the runway (also behind its rear end) before the javelin has landed; if "
             "your chest is turned more than {back_turn_deg} degrees away from the throwing direction before the "
             "release (your back to the arc); if the javelin is let go lower than the shoulder; if it does not land "
             "head first, lands outside the sector or short of {qualifying_mark_m} m; if any part of you touches it "
             "after the release (your throwing arm may still brush it during the first {retouch_grace_s} s); if you "
             "fall (your pelvis lower than {fall_pelvis_m} m above the ground, or any part of you other than your "
             "feet on the ground); or after {time_limit_s} s. Where you touch the ground is judged on the points of "
             "contact.")
    venue = ("You stand on the runway's centre line facing the sector (+x), your pelvis 2.0 m behind the middle of "
             "the arc; the arc's centre is 6.0 m behind you, its ends are 0.25 m behind its middle and "
             "2.0 m to either side, and the runway reaches 28 m behind you. Your right arm hangs straight down, the "
             "javelin level in its hand, pointing forwards (the tip {javelin_cg_from_tip_m} m ahead of the hand). "
             "Still air. The javelin is released when the hand's grip is switched off.")
    difficulty = ("{qualifying_mark_m} m asks for a release at about 14 m/s near 35 to 40 degrees with the javelin "
                  "pointing along its flight, or it will not come down head first; the H1-2 has no running policy "
                  "and its arm motors give 40 N m at the shoulder. The throw must come from above the shoulder on "
                  "a body that has to stay on its feet behind the arc.")

    # ------------------------------------------------------------------ geometry
    def geometry(self):
        p = self.p
        R, hw = p["arc_radius_m"], p["runway_width_m"] / 2
        xe = -R + math.sqrt(R * R - hw * hw)                 # the arc's ends (the arc's middle is the origin)
        return dict(R=R, hw=hw, cx=-R, x_end=xe, x_rear=xe - p["runway_length_m"], half_sector=math.asin(hw / R))

    def build(self, sc):
        p, g = self.p, self.geometry()
        self.fall_z = p["fall_pelvis_m"]
        R, hw, cx, xe, xr = g["R"], g["hw"], g["cx"], g["x_end"], g["x_rear"]
        sc.box("runway", ((xr + xe) / 2, 0, 0.0003), ((xe - xr) / 2, hw, 0.0003), rgba=RUNWAY)
        k = 16
        for i in range(k):                                   # ... and the segment between the arc's chord and the arc
            y = -hw + (i + 0.5) * 2 * hw / k
            xa = cx + math.sqrt(R * R - y * y)
            sc.box(f"runway_cap{i}", ((xe + xa) / 2, y, 0.0003), ((xa - xe) / 2, hw / k, 0.0003), rgba=RUNWAY)
        for s, tag in ((1, "L"), (-1, "R")):
            sc.line(f"side_line{tag}", (xr, s * (hw + LINE_W / 2)), (xe, s * (hw + LINE_W / 2)), width=LINE_W)
            sc.line(f"arc_end_line{tag}", (xe + ARC_W / 2, s * hw), (xe + ARC_W / 2, s * (hw + 0.75)), width=ARC_W)
            far = 45.0                                       # the sector lines: 50 mm wide, outside the sector
            a = s * g["half_sector"]
            n = (-math.sin(a) * s, math.cos(a) * s)
            p0 = (cx + R * math.cos(a) + n[0] * LINE_W / 2, R * math.sin(a) + n[1] * LINE_W / 2)
            p1 = (cx + (R + far) * math.cos(a) + n[0] * LINE_W / 2, (R + far) * math.sin(a) + n[1] * LINE_W / 2)
            sc.line(f"sector_line{tag}", p0, p1, width=LINE_W, z=0.0012)
        n = 24
        for i in range(n):                                   # the arc: 70 mm wide, its inner edge at the radius
            a0 = -g["half_sector"] + 2 * g["half_sector"] * i / n
            a1 = -g["half_sector"] + 2 * g["half_sector"] * (i + 1) / n
            rr = R + ARC_W / 2
            sc.line(f"arc{i}", (cx + rr * math.cos(a0), rr * math.sin(a0)), (cx + rr * math.cos(a1), rr * math.sin(a1)),
                    width=ARC_W, z=0.0012)
        D = p["qualifying_mark_m"]
        m = 12
        for i in range(m):                                   # the qualifying mark: an arc across the sector
            a0 = -g["half_sector"] + 2 * g["half_sector"] * i / m
            a1 = -g["half_sector"] + 2 * g["half_sector"] * (i + 1) / m
            sc.line(f"mark{i}", (cx + (R + D) * math.cos(a0), (R + D) * math.sin(a0)),
                    (cx + (R + D) * math.cos(a1), (R + D) * math.sin(a1)), width=0.05, rgba=(0.95, 0.85, 0.2, 1))
        L, cg, head = p["javelin_length_m"], p["javelin_cg_from_tip_m"], p["javelin_head_m"]
        b = sc.body("javelin", (-2.0, -0.3, 0.75), free=True)   # the body's origin: the centre of gravity; +x: the tip
        b.insert(1, b.makeelement("inertial", dict(pos="0 0 0", mass=f"{p['javelin_mass_kg']!r}",
                                                    diaginertia=f"{I_AXIAL} {I_TRANSVERSE} {I_TRANSVERSE}")))
        col = dict(friction=(0.8, 0.005, 0.0001), condim=4, mass=0, **HITTABLE)
        sc.geom(b, "javelin_head", type="capsule", fromto=(cg - head, 0, 0, cg - TIP_R, 0, 0), size=(TIP_R,),
                rgba=(0.75, 0.76, 0.8, 1), **col)
        sc.geom(b, "javelin_shaft", type="capsule", fromto=(cg - L + SHAFT_R, 0, 0, cg - head, 0, 0), size=(SHAFT_R,),
                rgba=(0.85, 0.75, 0.2, 1), **col)
        sc.geom(b, "javelin_cord", type="cylinder", fromto=(-0.08, 0, 0, 0.08, 0, 0), size=(SHAFT_R + 0.002,),
                rgba=(0.2, 0.3, 0.7, 1), mass=0, **VISUAL)
        sc.geom(b, "javelin_air", type="ellipsoid", pos=(-CP_BEHIND_CG, 0, 0),
                size=(L / 2, SHAFT_R, SHAFT_R), rgba=(0, 0, 0, 0), mass=0, fluidshape="ellipsoid", fluidcoef=FLUID,
                **VISUAL)
        sc.grippables["javelin"] = {"radius": SHAFT_R, "half_length": 0.08, "axis": "x"}
        sc.camera("venue", (-8.5, -7.5, 4.5), (4.0, 0.5, 0.3), fovy=55)
        sc.camera("sector", (-3.0, 0.0, 14.0), (12.0, 0.0, 0.0), fovy=70)

    def reset(self, w):
        # the right arm straight down, a little away from the leg; the javelin level in the hand, along the thumb
        set_arm(w, right_elbow_pitch=1.57, right_shoulder_roll=-0.15)
        d = w.d
        b = w.robot.mount["right"]
        R = d.xmat[b].reshape(3, 3)
        Rb = np.column_stack([R[:, 1], R[:, 2], R[:, 0]])     # the javelin's axis: the mount's y (forwards)
        q = np.zeros(4)
        mujoco.mju_mat2Quat(q, Rb.reshape(-1))
        w.put("javelin", d.xpos[b] + R @ np.array([0.022 + SHAFT_R + 0.003, 0.0, 0.045]), quat=q)
        w.grab("right", "javelin", event=False)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        self.jav = ref.geoms(body="javelin")
        self.head = ref.geoms(names=["javelin_head"])
        self.shaft = ref.geoms(names=["javelin_shaft"])
        self.robot = ref.part("robot")
        self.arm = ref.part("right_arm")
        self.not_arm = self.robot & ~self.arm
        self.jav_id = w.m.body("javelin").id
        self.shoulder = w.m.body("right_shoulder_roll_link").id
        self.trackers = {"released": None, "landed": None, "exit": False}

    def may_grip(self, w, side, name):
        return False                                          # held from t = 0; once let go it cannot be gripped again

    def _marks(self, w, ref):
        """Where the robot touches the ground now: None, or (in front of the arc or its end lines?, outside the
        runway behind them?, at or behind the exit line?)."""
        pts = ref.contact_points(self.robot, ref.ground)
        if not len(pts):
            return None
        g, p = self.geometry(), self.p
        x, y = pts[:, 0], pts[:, 1]
        inside = np.abs(y) < g["hw"]
        front = (inside & (np.hypot(x - g["cx"], y) >= g["R"])) | (~inside & (x >= g["x_end"]))
        out = (~inside & (x < g["x_end"])) | (x < g["x_rear"])
        back = x <= g["x_end"] - p["exit_line_m"]
        return bool(front.any()), bool(out.any()), bool(back.any())

    def substep(self, w, ref):
        tr, p, g = self.trackers, self.p, self.geometry()
        mk = self._marks(w, ref)
        if mk is not None:
            if mk[0]:
                return ref.fail("touched the arc or the ground beyond it")
            if tr["landed"] is None and mk[1]:
                return ref.fail("left the runway before the javelin had landed")
            if tr["landed"] is not None and (mk[1] or mk[2]) and not tr["exit"]:
                tr["exit"] = True
                ref.stage("exit")
        if tr["landed"] is not None:
            return
        held = bool(w.holder("javelin"))
        if tr["released"] is None:
            if held:
                return
            tr["released"] = ref.time
            c = w.pos("javelin")
            v = w.vel("javelin")
            ax = w.d.xmat[self.jav_id].reshape(3, 3)[:, 0]
            above = float(c[2] - w.d.xpos[self.shoulder][2])
            ref.metrics["release_speed_m_s"] = round(float(np.linalg.norm(v)), 2)
            ref.metrics["release_height_m"] = round(float(c[2]), 3)
            ref.metrics["release_elevation_deg"] = round(math.degrees(math.atan2(v[2], math.hypot(v[0], v[1]))), 1)
            ref.metrics["release_attitude_deg"] = round(math.degrees(math.asin(max(-1.0, min(1.0, float(ax[2]))))), 1)
            if above < p["release_above_shoulder_m"]:
                return ref.fail("the javelin was let go below the shoulder", above_shoulder_m=round(above, 3))
            ref.stage("release")
        elif (ref.touching(self.jav, self.not_arm)
              or (ref.time - tr["released"] > p["retouch_grace_s"] and ref.touching(self.jav, self.arm))):
            return ref.fail("the javelin was touched after the release", parts=sorted(ref.parts_touching(self.jav)))
        if not ref.touching(self.jav, ref.ground):
            return
        head = ref.contact_points(self.head, ref.ground)       # the landing: the first touch of the ground
        tip_first = len(head) > 0 and not ref.touching(self.shaft, ref.ground)
        pt = head[0] if len(head) else ref.contact_points(self.jav, ref.ground)[0]
        dx, dy = float(pt[0]) - g["cx"], float(pt[1])
        dist = math.hypot(dx, dy) - g["R"]
        tr["landed"] = [round(float(pt[0]), 4), round(dy, 4)]
        ref.metrics["distance_m"] = round(dist, 3)
        ref.metrics["head_first"] = float(tip_first)
        if not tip_first:
            ref.fail("the javelin did not land head first")
        elif dist <= 0 or abs(math.atan2(dy, dx)) >= g["half_sector"]:
            ref.fail("the javelin landed outside the sector", x=round(float(pt[0]), 3), y=round(dy, 3))
        elif dist < p["qualifying_mark_m"]:
            ref.fail("the throw is short of the qualifying mark", distance_m=round(dist, 3))
        else:
            ref.stage("landing", distance_m=round(dist, 3))

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        if tr["released"] is None:
            fwd = w.d.xmat[w.robot.torso].reshape(3, 3)[:, 0]
            turn = abs(math.degrees(math.atan2(float(fwd[1]), float(fwd[0]))))
            if turn > p["back_turn_deg"]:
                return ref.fail("turned the back to the arc before the throw", turn_deg=round(turn, 1))
        if ref.has("exit") and ref.hold("stand", ref.standing(), p["stand_s"]):
            ref.succeed()

    def privileged(self, w):
        g = self.geometry()
        return {"javelin": w.pos("javelin").tolist(), "javelin_velocity": w.vel("javelin").tolist(),
                "javelin_axis": w.d.xmat[self.jav_id].reshape(3, 3)[:, 0].tolist(), "held": bool(w.holder("javelin")),
                "arc_centre": [g["cx"], 0.0], "arc_radius": g["R"], "arc_ends_x": g["x_end"],
                "sector_half_angle_deg": math.degrees(g["half_sector"])}
