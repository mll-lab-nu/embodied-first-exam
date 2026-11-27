"""Inline speed slalom (World Skate Inline Freestyle, Speed Slalom): from the start box, 12 m of run-up, then on one
foot through a line of 20 cones 0.8 m apart, and over the end line 0.8 m beyond the last cone, against the clock,
+0.2 s for each kicked cone or missed interval.

The skates are real: a rigid boot on each foot (it holds the foot as a laced boot does: a weld of the boot to the
foot's link, the boot's collisions with that foot switched off), an aluminium frame, four urethane wheels in a line,
each on its own axle (a hinge joint, free to spin). Lateral grip, rolling and sliding are the wheels' friction on the
floor, so pushing, gliding and turning are physical. Sources: the skate is FR Skates' AXS junior skate in sizes 29-32
(a 192 mm aluminium frame, 64 mm outer and 62 mm inner wheels; the robot's foot is 0.19 m long); wheels 24 mm wide, 65 g with
bearings, the skate 1.0 kg (estimates: a 64 mm 85A wheel with its bearings, a junior skate); rolling resistance from
Giorgi, "Drag and friction coefficients in roller skating, an indirect determination" (ISBS 1998): F = k m v with
k = 0.0137 1/s, about 0.004 of the weight at 3 m/s; urethane on a smooth concrete sports floor: sliding friction 0.8.
The cones are World Skate's (3.10.1: 7.6-8.0 cm high, base 7.2-7.5 cm, top 2.4-2.7 cm), hard plastic cups of about 20 g
(an estimate), friction 0.4 on the floor."""
import math
import xml.etree.ElementTree as ET

import numpy as np

from rfo.scene import VISUAL, HITTABLE
from rfo.task import TaskBase

SOLE = (0.035, 0.0, -0.035)          # the G1's sole centre in its ankle-roll link's frame (the boot's footbed)


class Task(TaskBase):
    name = "inline-slalom"
    title = "Inline speed slalom"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("World Skate Inline Freestyle Regulation (update of October 2025): 3.10 official cones (7.6-8.0 cm "
                "high, base 7.2-7.5 cm, top 2.4-2.7 cm); 4.2 the cone lines and their marking stickers (7.7 cm, a "
                "0.7 cm centre point); 7 Speed Slalom (on one foot, as fast as possible): 7.1.1 20 cones 80 cm "
                "apart, 7.1.3 the start box (two start lines 40 cm apart), 7.1.5 the first cone 12 m from the start "
                "line and the end line 80 cm beyond the last cone, 7.3.1.1 the free start of the time trials (time "
                "starts when any part of the body crosses the gate beam, 40 cm above the ground), 7.3.2 the cone line "
                "entered on one foot, 7.3.3 the end line crossed by the supporting foot with a wheel on the ground, "
                "7.4.2 first-cone penalties, 7.4.3 the free foot and changing foot, 7.4.4 end-line penalties, 7.4.5 "
                "+0.2 s per kicked cone or missed interval, more than 4 cone penalties void the run")
    deviations = [
        "7.3.1.1 the start: \"Ready\" is t = 0 with the robot standing in the start box on both skates; it has "
        "{start_window_s} s to break the gate beam; a false start's warning and restart are not modelled (one run)",
        "7.1.1-7.1.4 one cone line, without the second line and the divider (one skater, one time-trial run)",
        "7.4.5.2 a kicked cone (its marking centre revealed) is judged at the finish: the cone's base centre more "
        "than {kick_move_m} m (the base's radius less the centre point's) from its mark, or the cone tilted more than {cone_tilt_deg} "
        "degrees",
        "the missed interval and the side of each cone are judged on the supporting skate's centre: the side of "
        "the cone line it is on when it passes each cone; two consecutive cones on the same side are one missed "
        "interval",
        "the finish gate (20 cm above the ground) is the supporting skate's front wheel reaching the end line",
        "the skates are rigid bodies held to the feet by a rigid boot (no ankle flex in the boot); the wheels are "
        "ellipsoids (their rounded profile) on frictionless axles",
        "success is a valid run within {time_limit_s} s, the family's own round number for this robot: the "
        "rule book only ranks times",
    ]
    sentence = ("Skate the speed slalom: from the start box, skate on one foot through the 20 cones, passing them "
                "alternately left and right, and over the end line.")
    rules = ("You wear inline skates (rigid boots on your feet, four wheels in a line on each, the outer ones "
             "{wheel_d_outer_m} m and the inner ones {wheel_d_inner_m} m in diameter, {axle_pitch_m} m apart). The "
             "course runs along +x on a level sports floor: the start line at x = 0 and a second line {box_depth_m} m "
             "behind it (the start box), {n_cones} cones on the line y = 0 every {cone_spacing_m} m from x = "
             "{runup_m} m, the end line {end_after_m} m beyond the last cone. The cones are free plastic cups "
             "{cone_height_m} m high, {cone_base_d_m} m across the base, {cone_mass_kg} kg, standing on marking "
             "stickers. Time starts when any part of your body crosses the start line at the gate beam's height, "
             "{start_beam_m} m above the ground; you must do that within {start_window_s} s of t = 0. The cone line "
             "begins at the front edge of the first cone: enter it on one foot (one skate's wheels on the ground, "
             "the other skate in the air), or the first cone counts as missed (a penalty); not being on one foot "
             "when your skate passes the second cone voids the run. From then on the free skate must not touch the "
             "ground until the end line (that voids the run; so does changing feet). Pass the cones alternately on "
             "the left and the right with the supporting skate: two consecutive cones on the same side are a missed "
             "interval. A cone whose marking centre is uncovered at the finish (its base centre moved more than "
             "{kick_move_m} m (the base's radius less the centre point's), or tilted more than {cone_tilt_deg} degrees) is kicked. Each "
             "kicked cone or missed interval adds {penalty_s} s; more than {max_penalties} penalties void the run. "
             "The run ends when the front wheel of your supporting skate crosses the end line with a wheel of that "
             "skate on the ground (crossing first with the free skate, or in the air, voids it); every cone must "
             "have been passed. Your time is the time from the beam to the end line plus the penalties. You succeed "
             "with a valid run that ends within {time_limit_s} s of t = 0. You also fail if any part of you touches "
             "the ground (the skates' wheels and frames may) or your pelvis drops below {fall_z_m} m (a fall).")
    venue = ("You stand at the start facing +x on both skates, side by side, your pelvis at x = -0.25 m on the cone "
             "line's axis y = 0, the skates inside the start box (between x = -{box_depth_m} m and x = 0). The first "
             "cone is {runup_m} m ahead of the start line; the line of cones runs straight ahead. The floor is a "
             "level, smooth sports floor.")
    difficulty = ("Skating is pushing against wheels that only grip sideways: the robot has no skating gait and no "
                  "balance on one foot, and on one skate it stands on a line of wheels, so it can only stay up by "
                  "steering the skate under its weight while weaving through cones 0.8 m apart.")
    time_limit_s = 60.0
    start = (-0.25, 0.0, 0.0)
    stages = ["start", "cone line", "cone 5", "cone 10", "cone 15", "cone 20", "finish"]
    fall_rule = True
    fall_z = 0.45
    params = dict(
        runup_m=12.0, n_cones=20, cone_spacing_m=0.8, end_after_m=0.8, box_depth_m=0.40, box_width_m=2.0,
        cone_height_m=0.078, cone_base_d_m=0.074, cone_top_d_m=0.0255, cone_mass_kg=0.02, mark_d_m=0.077,
        centre_d_m=0.007, cone_friction=0.4,
        wheel_d_outer_m=0.064, wheel_d_inner_m=0.062, wheel_width_m=0.024, axle_pitch_m=0.064, wheel_mass_kg=0.065,
        sole_to_axle_m=0.045, skate_mass_kg=1.0, wheel_friction=0.8, wheel_crr=0.004,
        penalty_s=0.2, max_penalties=4, start_window_s=5.0, start_beam_m=0.40, cone_tilt_deg=30.0, fall_z_m=0.45, kick_move_m=0.0335,
    )

    def build(self, sc):
        p = self.p
        x0, y0, _ = self.start
        # the skates: a boot (footbed plate and shell), a frame, four wheels on axles, held to the foot by the boot
        for side in ("left", "right"):
            self._skate(sc, side)
        sc.box("rink", (14.0, 0.0, 0.0003), (18.0, 4.0, 0.0003), rgba=(0.42, 0.45, 0.50, 1))
        bw = p["box_width_m"] / 2
        sc.line("start_front", (0.0, -bw), (0.0, bw), width=0.05, rgba=(0.96, 0.96, 0.96, 1), z=0.0009)
        sc.line("start_back", (-p["box_depth_m"], -bw), (-p["box_depth_m"], bw), width=0.05, rgba=(0.96, 0.96, 0.96, 1), z=0.0009)
        sc.line("end_line", (self.end_x(), -bw), (self.end_x(), bw), width=0.05, rgba=(0.96, 0.96, 0.96, 1), z=0.0009)
        rb, rt, hc = p["cone_base_d_m"] / 2, p["cone_top_d_m"] / 2, p["cone_height_m"]
        n = 16
        verts = []
        for z, rr in ((0.0, rb), (hc, rt)):
            for i in range(n):
                a = 2 * math.pi * i / n
                verts += [rr * math.cos(a), rr * math.sin(a), z]
        ET.SubElement(sc.root.find("asset"), "mesh", name="slalom_cone", vertex=" ".join(f"{v:.5g}" for v in verts))
        for i, cx in enumerate(self.cone_xs()):
            sc.disc(f"mark{i}", (cx, 0.0), p["mark_d_m"] / 2, rgba=(0.98, 0.85, 0.1, 1), z=0.0007)
            sc.disc(f"mark{i}_centre", (cx, 0.0), p["centre_d_m"] / 2, rgba=(0.1, 0.1, 0.1, 1), z=0.0009)
            b = sc.body(f"cone{i}", (cx, 0.0, 0.0), free=True)
            sc.geom(b, f"cone{i}", type="mesh", mesh="slalom_cone", mass=p["cone_mass_kg"], rgba=(0.98, 0.35, 0.05, 1),
                    friction=(p["cone_friction"], 0.005, 0.0001), **HITTABLE)
        sc.camera("venue", (8.0, -9.0, 4.0), (10.0, 0.0, 0.3), fovy=60)
        sc.camera("side", (x0 + 0.5, -2.0, 0.7), (x0 + 0.5, 0.0, 0.4), fovy=50)

    def cone_xs(self):
        p = self.p
        return [p["runup_m"] + i * p["cone_spacing_m"] for i in range(int(p["n_cones"]))]

    def end_x(self):
        p = self.p
        return self.cone_xs()[-1] + p["end_after_m"]

    def _skate(self, sc, side):
        p = self.p
        H = p["sole_to_axle_m"]
        b = sc.body(f"skate_{side}", (0, 0, 0), free=True)
        plate_m = p["skate_mass_kg"] - 4 * p["wheel_mass_kg"]
        kw = dict(contype=1, conaffinity=1, condim=3, friction=(0.6, 0.005, 0.0001))
        sc.geom(b, f"skate_{side}_plate", type="box", pos=(0, 0, -0.005), size=(0.125, 0.04, 0.005), mass=plate_m * 0.6,
                rgba=(0.1, 0.1, 0.12, 1), **kw)
        for sy in (1, -1):
            sc.geom(b, f"skate_{side}_rail{'L' if sy > 0 else 'R'}", type="box", pos=(0, sy * 0.016, -0.026),
                    size=(0.13, 0.003, 0.016), mass=plate_m * 0.2, rgba=(0.75, 0.75, 0.78, 1), **kw)
        sc.geom(b, f"skate_{side}_shell", type="capsule", fromto=(-0.06, 0, 0.03, 0.09, 0, 0.03), size=(0.045,),
                rgba=(0.12, 0.12, 0.14, 1), **VISUAL)
        sc.geom(b, f"skate_{side}_cuff", type="cylinder", fromto=(-0.05, 0, 0.02, -0.05, 0, 0.20), size=(0.05,),
                rgba=(0.12, 0.12, 0.14, 1), **VISUAL)
        pitch = p["axle_pitch_m"]
        mu_r = p["wheel_crr"]
        for i, xw in enumerate((-1.5, -0.5, 0.5, 1.5)):
            r = (p["wheel_d_outer_m"] if i in (0, 3) else p["wheel_d_inner_m"]) / 2
            wb = ET.SubElement(b, "body", name=f"skate_{side}_w{i}", pos=f"{xw * pitch:.6g} 0 {-H:.6g}")
            ET.SubElement(wb, "joint", name=f"skate_{side}_w{i}", type="hinge", axis="0 1 0", damping="0", armature="0")
            sc.geom(wb, f"skate_{side}_w{i}", type="ellipsoid", size=(r, r, p["wheel_width_m"] / 2),
                    quat=(math.cos(math.pi / 4), math.sin(math.pi / 4), 0, 0), mass=p["wheel_mass_kg"],
                    rgba=(0.95, 0.75, 0.15, 1), condim=6, priority=2,
                    friction=(p["wheel_friction"], 0.0005, mu_r * r), contype=1, conaffinity=1)
        con, eq = sc.root.find("contact"), sc.root.find("equality")
        foot = f"{side}_ankle_roll_link"
        ET.SubElement(con, "exclude", body1=foot, body2=f"skate_{side}")
        for i in range(4):
            ET.SubElement(con, "exclude", body1=foot, body2=f"skate_{side}_w{i}")
        ET.SubElement(eq, "weld", name=f"boot_{side}", body1=foot, body2=f"skate_{side}",
                      relpose=f"{SOLE[0]:g} {SOLE[1]:g} {SOLE[2]:g} 1 0 0 0", solref="0.004 1", solimp="0.95 0.99 0.001")

    def reset(self, w):
        import mujoco
        p = self.p
        lift = p["sole_to_axle_m"] + p["wheel_d_outer_m"] / 2 + 0.001
        w.d.qpos[w.robot.fq + 2] += lift
        mujoco.mj_kinematics(w.m, w.d)
        for side in ("left", "right"):
            f = w.m.body(f"{side}_ankle_roll_link").id
            R = w.d.xmat[f].reshape(3, 3)
            pos = w.d.xpos[f] + R @ np.array(SOLE)
            q = np.zeros(4)
            mujoco.mju_mat2Quat(q, R.ravel())
            w.put(f"skate_{side}", pos, quat=q)

    def referee_reset(self, w, ref):
        self.floor = ref.geoms(names=["floor"])
        self.skate_g = {sd: ref.geoms(body=f"skate_{sd}") for sd in ("left", "right")}
        self.robot = ref.part("robot")
        self.cones = ref.geoms(prefix="cone")
        self.sk_id = {sd: w.m.body(f"skate_{sd}").id for sd in ("left", "right")}
        self.reach = 1.5 * self.p["axle_pitch_m"] + self.p["wheel_d_outer_m"] / 2     # the skate's front wheel's front
        self.gate_geoms = [int(g) for g in np.flatnonzero(self.robot) if w.m.geom_contype[g] or w.m.geom_conaffinity[g]]
        # t_start: the start (the gate beam broken); entered: the cone line entered; support: the skate on the ground
        # since then; sides: per cone passed, the side (+1 left of the line, -1 right) of the supporting skate;
        # pen: penalties so far (the first cone's, the missed intervals); prev: per skate, its front point last step
        self.trackers = {"t_start": None, "entered": False, "support": None, "sides": [], "pen_first": 0,
                         "prev_front": None, "prev_gate": None, "t_end": None, "time_s": None}

    def _down(self, ref, sd) -> bool:
        return ref.touching(self.skate_g[sd], self.floor)

    def _front(self, w, sd) -> np.ndarray:
        """The front of the skate's front wheel (its frame's x axis), and its centre (x, y)."""
        R = w.d.xmat[self.sk_id[sd]].reshape(3, 3)
        c = w.d.xpos[self.sk_id[sd]]
        return c + R[:, 0] * self.reach

    def _gate_x(self, w) -> float:
        """The front of the robot's body at the start gate's beam height: the largest x of any of its collision
        geoms' bounding boxes that reach that height."""
        m, d = w.m, w.d
        h = self.p["start_beam_m"]
        best = -9.0
        for g in self.gate_geoms:
            R = d.geom_xmat[g].reshape(3, 3)
            c = d.geom_xpos[g] + R @ m.geom_aabb[g, :3]
            ext = np.abs(R) @ m.geom_aabb[g, 3:]
            if c[2] - ext[2] <= h <= c[2] + ext[2]:
                best = max(best, float(c[0] + ext[0]))
        return best

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        down = {sd: self._down(ref, sd) for sd in ("left", "right")}
        if tr["t_start"] is None:
            gx = self._gate_x(w)
            if gx >= 0.0:
                tr["t_start"] = round(ref.time, 4)
                ref.stage("start", t=tr["t_start"])
            return
        fronts = {sd: self._front(w, sd) for sd in ("left", "right")}
        x_entry = self.cone_xs()[0] - p["cone_base_d_m"] / 2
        if not tr["entered"]:
            if max(f[0] for f in fronts.values()) >= x_entry:
                tr["entered"] = True
                on = [sd for sd in ("left", "right") if down[sd]]
                if len(on) == 1:
                    tr["support"] = on[0]
                else:                                       # 7.4.2.1: not on one foot at the entry
                    tr["pen_first"] = 1
                    ref.event("first cone penalty", on=on)
                ref.stage("cone line")
            return
        if tr["support"] is None:                           # still on two feet (or none) after the entry
            on = [sd for sd in ("left", "right") if down[sd]]
            if len(on) == 1:
                tr["support"] = on[0]
        sup = tr["support"]
        if sup is not None:
            free = "right" if sup == "left" else "left"
            if down[free]:
                return ref.fail("the free foot touched the ground", free=free)      # 7.4.3.1 (also a change of foot)
        # the cones passed: the supporting skate's centre reaching each cone's x (before one foot: the skates' mean)
        c = (w.d.xpos[self.sk_id[sup]] if sup else 0.5 * (w.d.xpos[self.sk_id["left"]] + w.d.xpos[self.sk_id["right"]]))
        xs = self.cone_xs()
        while len(tr["sides"]) < len(xs) and c[0] >= xs[len(tr["sides"])]:
            i = len(tr["sides"])
            if i == 1 and sup is None:
                return ref.fail("not on one foot at the second cone")                # 7.4.2.2
            tr["sides"].append(1 if c[1] > 0 else -1)
            for k, name in ((5, "cone 5"), (10, "cone 10"), (15, "cone 15"), (20, "cone 20")):
                if i + 1 == k:
                    ref.stage(name)
        # the end line: crossed first by the supporting skate, a wheel on the ground
        ex = self.end_x()
        prev, tr["prev_front"] = tr["prev_front"], {sd: float(f[0]) for sd, f in fronts.items()}
        if prev is None:
            return
        for sd in ("left", "right"):
            if prev[sd] < ex <= fronts[sd][0]:
                if sd != sup:
                    return ref.fail("the end line was not crossed first by the supporting foot")  # 7.4.4.1
                if not down[sd]:
                    return ref.fail("jumped over the end line")                                      # 7.4.4.2
                self._finish(w, ref)
                return

    def penalties(self, w) -> dict:
        p, tr = self.p, self.trackers
        kicked = []
        lim = p["kick_move_m"]
        for i, cx in enumerate(self.cone_xs()):
            b = w.m.body(f"cone{i}").id
            pos = w.d.xpos[b]
            tilt = float(w.d.xmat[b][8])
            if math.hypot(pos[0] - cx, pos[1]) > lim or tilt < math.cos(math.radians(p["cone_tilt_deg"])):
                kicked.append(i + 1)
        sides = tr["sides"]
        missed = [i + 1 for i in range(1, len(sides)) if sides[i] == sides[i - 1]]
        first = tr["pen_first"] and 1 not in kicked                 # (a kicked first cone is penalised once)
        return {"kicked": kicked, "missed_intervals": missed, "first_cone": int(first),
                "total": len(kicked) + len(missed) + int(first)}

    def _finish(self, w, ref):
        p, tr = self.p, self.trackers
        pen = self.penalties(w)
        raw = ref.time - tr["t_start"]
        tr["t_end"] = round(ref.time, 4)
        ref.metrics.update(raw_time_s=round(raw, 3), penalties=pen["total"], kicked=len(pen["kicked"]),
                           missed_intervals=len(pen["missed_intervals"]))
        if len(tr["sides"]) < int(p["n_cones"]):
            return ref.fail("did not pass every cone", passed=len(tr["sides"]))
        if pen["total"] > p["max_penalties"]:
            return ref.fail("more than {:g} cone penalties: the run is void".format(p["max_penalties"]), **pen)
        tr["time_s"] = round(raw + p["penalty_s"] * pen["total"], 3)
        ref.metrics["time_s"] = tr["time_s"]
        if ref.stage("finish", time_s=tr["time_s"], **pen):
            ref.succeed()

    def step(self, w, ref):
        p, tr = self.p, self.trackers
        if tr["t_start"] is None and w.t > p["start_window_s"]:
            ref.fail("did not start within {:g} s of the start command".format(p["start_window_s"]))

    def privileged(self, w):
        tr = self.trackers
        return {"pelvis": w.pelvis().tolist(),
                "skates": {sd: {"pos": w.d.xpos[w.m.body(f"skate_{sd}").id].tolist(),
                                "vel": w.vel(f"skate_{sd}").tolist()} for sd in ("left", "right")},
                "cones": [w.pos(f"cone{i}").tolist() for i in range(int(self.p["n_cones"]))],
                "supporting_skate": tr.get("support"), "sides": list(tr.get("sides", []))}
