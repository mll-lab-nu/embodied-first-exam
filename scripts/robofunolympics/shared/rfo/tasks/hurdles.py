"""50 m hurdles (World Athletics TR 22 at the indoor distance): four 1.067 m hurdles at 13.72 m + 9.14 m x i, 8.86 m to
the finish (owner, 2026-10-12: not the 110 m; the benchmark shows a capability, not the Olympic programme); every
hurdle is gone over, knocking one down with the legs is allowed, going beside it or under its top is not.

The hurdle is RoboOlympics' hinged hurdle (sports/athletics/track.py, branch athletics-v3, MIT) at the official size:
a body hinged at the bottom of its uprights that tips over forwards, its feet (the base, towards the runner) carrying
the counterweights that set the official toppling force at the top bar's centre. The lane rule, the "down" rule, the
leg-beside-the-hurdle rule (TR 22.6.1) and the finish timing are that referee's, ported."""
import math
import xml.etree.ElementTree as ET

import numpy as np

from rfo.referee import Crossing
from rfo.task import TaskBase

SIDES = ("left", "right")
TRACK = (0.72, 0.25, 0.18, 1)
H1_FOOT_FRONT = 0.158            # m: the front end of the standing H1-2's feet ahead of its pelvis (measured)
BAR_DEPTH = 0.02                 # m: the top bar's thickness (TR 22.4: 10 to 25 mm)
BAR_MASS, UPRIGHT_MASS = 1.0, 0.75
UPPER = ("hands", "forearms", "upper_arms", "torso", "pelvis")     # "hand or body" of TR 22.6.2
ORD = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth")


def hull_points(m, g, n=400) -> np.ndarray:
    """The support points of mesh geom g (geom frame) along n fixed directions (a Fibonacci sphere)."""
    mid = int(m.geom_dataid[g])
    v = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]].astype(float)
    i = np.arange(n) + 0.5
    phi, th = np.arccos(1 - 2 * i / n), math.pi * (1 + 5 ** 0.5) * i
    dirs = np.c_[np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)]
    return v[np.unique(np.argmax(v @ dirs.T, axis=0))]


def foot_mass(p) -> float:
    """The mass of each of the hurdle's two feet (the counterweights) for the toppling force of the rules: a
    horizontal force F at the top bar's centre tips the hurdle over its hinge when F h > g sum(m d) (d: each
    part's distance behind the hinge), as RoboOlympics' track.toppling_force()."""
    moment = p["toppling_force_kgf"] * p["hurdle_height_m"]              # kg m
    return (moment - (BAR_MASS + 2 * UPRIGHT_MASS) * BAR_DEPTH / 2) / p["base_length_m"]


class Task(TaskBase):
    name = "hurdles"
    title = "50 m hurdles"
    category = "track-and-jumps"
    robot = "unitree_h1"
    rulebook = ("World Athletics Competition and Technical Rules, 2024 edition: TR 22 (22.1-22.3 distances and "
                "heights: the men's hurdle 1.067 m high, 13.72 m to the first, 9.14 m between; at the indoor "
                "distance of 50 m that is four hurdles and 8.86 m from the last to the finish; 22.4-22.5 the hurdle: 1.18 to 1.20 m wide, a top bar 70 mm high, a base at most 0.70 m "
                "long, at least 10 kg, a toppling force of 3.6 to 4.0 kg at the centre of the top bar's top edge; "
                "22.6 each hurdle is gone over in the athlete's own lane; 22.6.1 a foot or leg beside the hurdle "
                "below the plane of its top; 22.6.2 knocking a hurdle down by hand or body; 22.7 knocking hurdles "
                "down otherwise is no offence), TR 17.3 (lanes), TR 18.2 and TR 19 (the finish)")
    deviations = [
        "TR 16 (the start): no starter's commands, no blocks and no reaction time: the robot stands with the front "
        "ends of its feet {toe_gap_m} m behind the start line and the clock runs from t = 0",
        "TR 22.6 ('goes over each hurdle') is judged geometrically at the plane of the hurdle's top bar: the pelvis "
        "must pass above the height of the hurdle's top, each foot (its ankle joint) above the lower edge of the "
        "top bar (a foot that strikes the bar knocks the hurdle down, which is allowed; a foot below the bar goes "
        "under), all three between the bar's ends",
        "TR 22.6.2 (knocking down or displacing a hurdle by hand, body or the upper side of the lead leg): intent "
        "and the side of the leg cannot be judged: a hurdle tipped more than {displaced_deg} degrees within "
        "{upper_touch_s} s of a touch by a hand, an arm, the trunk or the pelvis is a failure; the legs may knock "
        "it down",
        "TR 17.3 (lanes): the lane is judged by the pelvis (its centre more than half a lane width from the "
        "lane's centre line); TR 22.6.1 is judged on the centres of the legs' collision bodies within "
        "{beside_m} m of the hurdle's plane",
        "TR 17 (a fallen athlete): a robot whose pelvis is below {down_z_m} m is down; it may get up and go on, "
        "but {down_limit_s} s down in a row end the race (did not finish)",
        "TR 19 (photo finish): the time is the instant the leading point of the torso link's collision mesh "
        "reaches the finish line's plane, interpolated between 1 ms physics steps (the H1-2's trunk and head are "
        "one link, so its torso includes the head); no wind; the robot alone on a straight of three lanes",
        "the hurdle touches only the robot (its hinge's stop is the ground), and tips forwards only, like "
        "RoboOlympics'; the distance is the indoor 50 m with its four hurdles, on an outdoor straight, not the "
        "110 m; the time limit, {time_limit_s} s, is this benchmark's (FAMILIES.md)",
    ]
    time_limit_s = 140.0
    start = (-(0.05 + 0.02 + H1_FOOT_FRONT), 0.0, 0.0)
    stages = [f"hurdle {i + 1}" for i in range(4)] + ["finish"]
    fall_rule = False                # the race's own: a fallen runner may get up (the "down" rule)
    params = dict(distance_m=50.0, hurdles=4, first_hurdle_m=13.72, spacing_m=9.14, hurdle_height_m=1.067,
                  hurdle_width_m=1.19, bar_height_m=0.07, base_length_m=0.70, toppling_force_kgf=3.8,
                  lane_width_m=1.22, start_line_m=0.05, toe_gap_m=0.02, knocked_deg=45.0, displaced_deg=10.0,
                  upper_touch_s=0.5, beside_m=0.10, down_z_m=0.40, down_limit_s=10.0)

    sentence = ("Run the 50 m hurdles: go over all four hurdles in your lane, never beside one or under its top, and "
                "bring your torso to the finish line.")
    rules = ("World Athletics rules for the hurdles, at the indoor distance of 50 m. The lane runs along +x, {lane_width_m} m wide, centred "
             "on y = 0; the start line ({start_line_m} m wide) has its far edge at x = 0, the finish line is "
             "x = {distance_m} m. {hurdles} hurdles "
             "stand across the lane, the first {first_hurdle_m} m from the start line and one every {spacing_m} m "
             "after it (the last 8.86 m before the finish). A hurdle is {hurdle_height_m} m high and "
             "{hurdle_width_m} m wide with a top bar {bar_height_m} m high; its two base feet, {base_length_m} m "
             "long, lie on the track on your side of it. It is hinged at the foot of its uprights and tips over "
             "forwards when a horizontal force of more than {toppling_force_kgf} kg pushes the middle of its top "
             "bar; let go before it has gone too far, it swings back. The clock starts at t = 0. You go over a "
             "hurdle when your pelvis and both your feet (the ankle joints) have crossed the plane of its top bar "
             "towards +x, each between the bar's two ends, the pelvis higher than the hurdle's top "
             "({hurdle_height_m} m above the track) and each foot higher than the lower edge of its top bar "
             "({hurdle_height_m} m less {bar_height_m} m), whether the hurdle still stands or not; a pelvis or a "
             "foot that comes back over the plane has not crossed it and must cross it again. The hurdles "
             "are gone over in order. Knocking a hurdle down with your legs is allowed (a hurdle tipped more than "
             "{knocked_deg} degrees is counted as down, without a fault). You finish at the moment "
             "the leading point of your torso (the trunk and head hull; not the arms, legs or feet) reaches the "
             "finish line, with all hurdles gone over. You succeed with a finish within {time_limit_s} s of robot time. A fall "
             "does not end the race: you are down while your pelvis is below {down_z_m} m, you may get up and go "
             "on, but {down_limit_s} s down in a row end it. You fail if your pelvis or a foot crosses the next "
             "hurdle's plane beside the hurdle, or lower than said above (going under its top); if a part of one "
             "of your legs is beside the next hurdle (beyond the bar's ends, within {beside_m} m of its plane) "
             "lower than the hurdle's top; if a hurdle is tipped more than {displaced_deg} degrees within "
             "{upper_touch_s} s of being touched, while it was not yet tipped that far, by a hand, an arm, your "
             "trunk or your pelvis (knocked by hand or body; only hurdles within 3 m of your pelvis are judged); "
             "if your pelvis is more than half the lane's width from y = 0; if your torso reaches the "
             "finish line before every hurdle is gone over; when down for {down_limit_s} s; or after "
             "{time_limit_s} s.")
    venue = ("You stand in your lane facing the finish (+x), the front ends of your feet {toe_gap_m} m behind the "
             "start line, your pelvis 0.23 m behind it. The lane lines are white on a red track; the hurdles' "
             "top bars are white with black stripes; two white posts stand beside the finish line. In your rest "
             "pose your forearms point forward at about the height of a hurdle's top.")
    difficulty = ("A hurdle's top is higher than the robot's hip joints: each of the four has to be jumped or "
                  "stepped over with the whole pelvis above 1.067 m and each foot lifted a metre, on a body of "
                  "67 kg whose only built-in gait walks at 0.7 m/s and drifts in heading. Walking alone takes "
                  "half the time limit for the distance.")

    # ------------------------------------------------------------------ the venue
    def hurdle_x(self):
        p = self.p
        return [round(p["first_hurdle_m"] + i * p["spacing_m"], 2) for i in range(int(p["hurdles"]))]

    def toppling_force_n(self) -> float:
        """The horizontal force at the top bar's centre that just tips a hurdle over (N), from its masses."""
        p = self.p
        moment = (BAR_MASS + 2 * UPRIGHT_MASS) * BAR_DEPTH / 2 + 2 * foot_mass(p) * p["base_length_m"] / 2
        return 9.80665 * moment / p["hurdle_height_m"]

    def _hurdle(self, sc, name, x):
        p = self.p
        H, bw, bh, bd, L = p["hurdle_height_m"], p["hurdle_width_m"], p["bar_height_m"], BAR_DEPTH, p["base_length_m"]
        b = sc.body(name, (x + bd, 0.0, 0.0))            # the bar's take-off-side face is at the hurdle's mark
        ET.SubElement(b, "joint", name=name, type="hinge", axis="0 1 0", range=f"0 {math.pi / 2:.6g}", damping="0.05",
                      armature="0.001")
        kw = dict(contype="0", conaffinity="12", condim="3", friction=(0.6, 0.005, 0.0001))
        sc.geom(b, f"{name}_bar", type="box", pos=(-bd / 2, 0, H - bh / 2), size=(bd / 2, bw / 2, bh / 2),
                mass=BAR_MASS, rgba=(0.97, 0.97, 0.97, 1), **kw)
        for i, yy in enumerate((-0.4, 0.0, 0.4)):        # the stripes (visual only)
            sc.geom(b, f"{name}_stripe{i}", type="box", pos=(-bd - 0.0005, yy, H - bh / 2),
                    size=(0.0005, 0.1, bh / 2 - 0.002), rgba=(0.08, 0.08, 0.08, 1), contype="0", conaffinity="0", mass=0)
        up_h, fy = (H - bh) / 2, bw / 2 - 0.015
        for s, tag in ((1, "L"), (-1, "R")):
            sc.geom(b, f"{name}_up{tag}", type="box", pos=(-bd / 2, s * fy, up_h), size=(0.015, 0.015, up_h),
                    mass=UPRIGHT_MASS, rgba=(0.3, 0.3, 0.32, 1), **kw)
            sc.geom(b, f"{name}_foot{tag}", type="box", pos=(-L / 2, s * fy, 0.01), size=(L / 2, 0.015, 0.01),
                    mass=foot_mass(p), rgba=(0.3, 0.3, 0.32, 1), **kw)

    def build(self, sc):
        p = self.p
        D, W, S = p["distance_m"], p["lane_width_m"], p["start_line_m"]
        floor = next(g for g in sc.wb.iter("geom") if g.get("name") == "floor")
        floor.set("pos", f"{D / 2:g} 0 0")               # the grass is drawn around the whole straight
        floor.set("size", f"{D / 2 + 40:g} 30 0.05")
        x0, x1 = -12.0, D + 25.0
        sc.box("track", ((x0 + x1) / 2, 0, 0.0003), ((x1 - x0) / 2, W * 1.5 + 0.3, 0.0003), rgba=TRACK)
        for i, y in enumerate((-1.5 * W, -0.5 * W, 0.5 * W, 1.5 * W)):
            sc.line(f"lane{i}", (x0, y), (x1, y))
        sc.line("start_line", (-S / 2, -1.5 * W), (-S / 2, 1.5 * W), width=S, z=0.0009)
        sc.line("finish_line", (D + S / 2, -1.5 * W), (D + S / 2, 1.5 * W), width=S, z=0.0009)
        for s, tag in ((1, "L"), (-1, "R")):
            sc.box(f"finish_post{tag}", (D, s * (1.5 * W + 0.5), 1.0), (0.05, 0.05, 1.0))
        for i, x in enumerate(self.hurdle_x()):
            self._hurdle(sc, f"hurdle{i + 1}", x)
        sc.camera("venue", (D / 2, -(6.0 + 0.36 * D), 3.0 + 0.14 * D), (D / 2, 0.0, 0.0), fovy=62)
        sc.camera("first_hurdle", (6.0, -5.5, 2.2), (11.5, 0.0, 0.8), fovy=55)

    def reset(self, w):
        for i in range(int(self.p["hurdles"])):
            j = w.m.joint(f"hurdle{i + 1}")
            w.d.qpos[int(j.qposadr[0])] = 0.0
            w.d.qvel[int(j.dofadr[0])] = 0.0

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        m = w.m
        xs = self.hurdle_x()
        self.n_hurdles = len(xs)
        self.hinge = [int(m.jnt_qposadr[m.joint(f"hurdle{i + 1}").id]) for i in range(self.n_hurdles)]
        self.hurdle_mask = [ref.geoms(body=f"hurdle{i + 1}") for i in range(self.n_hurdles)]
        self.points = {"pelvis": w.robot.pelvis, "left foot": m.body("left_ankle_roll_link").id,
                       "right foot": m.body("right_ankle_roll_link").id}
        self.leg_ids = np.flatnonzero(ref.part("legs"))
        self.upper = ref.part(*UPPER)
        self.torso_geom = next(g for g in range(m.ngeom) if m.body(int(m.geom_bodyid[g])).name == "torso_link"
                               and m.geom_contype[g] and int(m.geom_dataid[g]) >= 0
                               and m.mesh(int(m.geom_dataid[g])).name.endswith("torso_link"))
        self.torso_pts = hull_points(m, self.torso_geom)
        # over: who (pelvis, left foot, right foot) is over the next hurdle; upper_t: when each hurdle was last
        # touched by a hand, an arm or the trunk; down: the hurdles that have been knocked down; front: the torso's
        # leading x one physics step ago; down_k: since when the robot is down
        self.trackers = {"over": [], "upper_t": [None] * self.n_hurdles, "down": [], "front": None, "down_k": None}
        for i, x in enumerate(xs):
            for k in self.points:
                self.trackers[f"bar{i + 1} {k}"] = Crossing((1, 0, 0), x + BAR_DEPTH / 2, direction=1)

    def torso_front(self, w) -> float:
        g = self.torso_geom
        R = w.d.geom_xmat[g].reshape(3, 3)
        return float(w.d.geom_xpos[g][0] + np.max(self.torso_pts @ R[0]))

    def tilt_deg(self, w, i) -> float:
        return math.degrees(float(w.d.qpos[self.hinge[i]]))

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        half, H, D = p["hurdle_width_m"] / 2, p["hurdle_height_m"], p["distance_m"]
        n = len(ref.stages)                              # hurdles gone over so far
        xs = self.hurdle_x()
        for i in range(self.n_hurdles):
            for k, b in self.points.items():
                x = tr[f"bar{i + 1} {k}"].update(w.d.xpos[b])
                if x is None or i != n:                  # only the next hurdle counts
                    continue
                y, z = float(x[1]), float(x[2])
                if abs(y) >= half:
                    return ref.fail(f"went beside the {ORD[i]} hurdle", what=k, y=round(y, 3))
                low = H if k == "pelvis" else H - p["bar_height_m"]
                if z <= low:
                    return ref.fail(f"went under the top of the {ORD[i]} hurdle", what=k, z=round(z, 3),
                                    must_be_above=round(low, 3))
                if k not in tr["over"]:
                    tr["over"] = sorted(tr["over"] + [k])
            if i == n and tr["over"]:                    # a point that comes back has not gone over the hurdle
                back = [k for k in tr["over"] if float(w.d.xpos[self.points[k]][0]) < xs[i] + BAR_DEPTH / 2]
                if back:
                    tr["over"] = [k for k in tr["over"] if k not in back]
            if i == n and len(tr["over"]) == len(self.points):
                ref.stage(f"hurdle {i + 1}", tilt_deg=round(self.tilt_deg(w, i), 1))
                tr["over"] = []
                n += 1
        if n < self.n_hurdles:                           # TR 22.6.1: a leg beside the next hurdle below its top
            c = w.d.geom_xpos[self.leg_ids]
            bad = (np.abs(c[:, 0] - (xs[n] + BAR_DEPTH / 2)) < p["beside_m"]) & (np.abs(c[:, 1]) > half) & (c[:, 2] < H)
            if bool(np.any(bad)):
                g = int(self.leg_ids[np.flatnonzero(bad)[0]])
                return ref.fail(f"a leg beside the {ORD[n]} hurdle below its top",
                                part=ref.part_names[int(ref.part_code[g])], y=round(float(w.d.geom_xpos[g][1]), 3))
        px = float(w.d.xpos[w.robot.pelvis][0])
        for i in range(self.n_hurdles):                  # TR 22.6.2: by hand or body
            if abs(px - xs[i]) > 3.0:
                continue
            tilt = self.tilt_deg(w, i)
            if tilt <= p["displaced_deg"] and ref.touching(self.upper, self.hurdle_mask[i]):
                tr["upper_t"][i] = ref.time               # a touch of a hurdle that still stands
            if tilt > p["knocked_deg"] and i not in tr["down"]:
                tr["down"] = tr["down"] + [i]
                ref.event("hurdle_down", hurdle=i + 1)
                ref.metrics["hurdles_down"] = len(tr["down"])
            t = tr["upper_t"][i]
            if tilt > p["displaced_deg"] and t is not None and ref.time - t <= p["upper_touch_s"]:
                return ref.fail(f"knocked the {ORD[i]} hurdle with a hand, an arm or the trunk",
                                tilt_deg=round(tilt, 1), parts=sorted(ref.parts_touching(self.hurdle_mask[i])))
        f0, f1 = tr["front"], self.torso_front(w)        # MuJoCo's positions after a step are one physics step old
        tr["front"] = f1
        if f0 is not None and f0 < D <= f1:
            if n < self.n_hurdles:
                return ref.fail("reached the finish line before going over every hurdle", hurdles=n)
            dt = w.m.opt.timestep
            t = ref.time - 2 * dt + (D - f0) / (f1 - f0) * dt
            ref.metrics["time_s"] = round(t, 3)
            if ref.stage("finish", time_s=round(t, 3)):
                ref.succeed()

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        x, y, z, _ = (float(v) for v in w.pelvis())
        ref.metrics["hurdles_cleared"] = min(len(ref.stages), self.n_hurdles)
        ref.metrics["distance_m"] = round(max(ref.metrics.get("distance_m", 0.0), min(x, p["distance_m"])), 2)
        if abs(y) > p["lane_width_m"] / 2:
            return ref.fail("left the lane", y=round(y, 3))
        if z < p["down_z_m"]:
            if tr["down_k"] is None:
                tr["down_k"] = w.k
                ref.event("down")
            elif (w.k - tr["down_k"]) * w.CONTROL_DT >= p["down_limit_s"]:
                return ref.fail("did not finish: down for too long", down_s=p["down_limit_s"])
        elif tr["down_k"] is not None:
            tr["down_k"] = None
            ref.event("up")

    def privileged(self, w):
        n = min(len(w.ref.stages), self.n_hurdles)
        return {"pelvis": w.pelvis().tolist(), "hurdle_x": self.hurdle_x(), "next_hurdle": n + 1,
                "hurdle_tilt_deg": [round(self.tilt_deg(w, i), 2) for i in range(self.n_hurdles)],
                "hurdle_top_m": self.p["hurdle_height_m"], "torso_front_x": self.torso_front(w)}
