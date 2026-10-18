"""High jump (World Athletics TR 26-27): a 4.00 m bar on its supports between uprights 4.02 m apart, the 6 m x 4 m x
0.7 m landing mat behind it; a take-off from one foot, over the bar, and the bar stays on."""
import numpy as np

from rfo.referee import Flights
from rfo.task import TaskBase

SIDES = ("left", "right")
STEEL = (0.3, 0.3, 0.33, 1)


def official_bar(sc, name, x, height, p):
    """The crossbar and its uprights (TR 26.3-26.7): a round bar (30 mm) with flat-bottomed end pieces, resting on two
    flat supports (4 cm wide, 6 cm long) that face each other from the uprights, its ends 1 cm clear of the uprights.
    `height` is the bar's upper side. It can fall forwards or backwards off the supports."""
    r, L, gap = p["bar_diameter_m"] / 2, p["bar_length_m"], p["upright_gap_m"]
    sw, sl, st = p["support_width_m"] / 2, p["support_length_m"] / 2, 0.004
    for s, tag in ((1, "L"), (-1, "R")):
        sc.geom(sc.wb, f"{name}_upright{tag}", type="box", pos=(x, s * (gap / 2 + 0.02), (height + 0.15) / 2),
                size=(0.02, 0.02, (height + 0.15) / 2), rgba=STEEL, contype="1", conaffinity="13")
        sc.geom(sc.wb, f"{name}_support{tag}", type="box", pos=(x, s * (gap / 2 - sl), height - 2 * r - st),
                size=(sw, sl, st), rgba=STEEL, friction=(0.6, 0.005, 0.0001), contype="1", conaffinity="13")
    b = sc.body(name, (x, 0.0, height - r), free=True)
    end = 0.075                                          # half the length of an end piece (TR 26.4: 15-20 cm)
    m_end = 0.10
    sc.geom(b, name, type="capsule", fromto=(0, -L / 2 + r, 0, 0, L / 2 - r, 0), size=(r,),
            mass=p["bar_mass_kg"] - 2 * m_end, rgba=(0.95, 0.2, 0.2, 1), friction=(0.6, 0.005, 0.0001),
            contype="1", conaffinity="13")
    for s, tag in ((1, "L"), (-1, "R")):                 # the end pieces: flat undersides, so the bar does not roll
        sc.geom(b, f"{name}_end{tag}", type="box", pos=(0, s * (L / 2 - end), 0), size=(r, end, r), mass=m_end,
                rgba=(0.95, 0.95, 0.95, 1), friction=(0.6, 0.005, 0.0001), contype="1", conaffinity="13")
    return dict(x=x, height=height, rest_z=height - r, plane_x=x - r, half_gap=gap / 2)


class Task(TaskBase):
    name = "high-jump"
    title = "High jump"
    category = "track-and-jumps"
    robot = "unitree_h1"
    rulebook = ("World Athletics Competition and Technical Rules, 2024 edition: TR 26 (26.3-26.7 the uprights 4.00 to "
                "4.04 m apart, the 4.00 m bar of at most 2 kg and 30 mm diameter on flat supports 4 cm wide and 6 cm "
                "long, 1 cm clear of the uprights), TR 27.1 (the take-off from one foot), TR 27.2 (failures: the bar "
                "does not remain on the supports; touching the ground or the landing area beyond the plane of the "
                "bar's nearer edge without first clearing the bar), TR 27.3 (a runway of at least 15 m), TR 27.10 "
                "(a landing area of at least 6 m x 4 m x 0.7 m), TR 25.17 (one minute for a trial)")
    deviations = [
        "TR 27.1 (one foot) is judged by a number: in the last {single_support_s} s before the lift-off of the "
        "jump's flight only one foot touches the ground, and nothing else does",
        "TR 27.2(b) is judged geometrically: before the jump's flight nothing of the robot may touch the ground or "
        "the mat beyond the plane; the robot's pelvis and feet (the ankle joints) must pass the plane between the "
        "uprights and above the height of the bar's upper side; the bar is cleared when every part of the robot is "
        "beyond the plane",
        "TR 27.2(a): the bar is judged {bar_wait_s} s after the clearance and the landing; it is off its supports "
        "when its centre is more than {bar_drop_m} m below its resting height",
        "TR 27.10 (the landing area): the mat is a box with a soft, overdamped contact (time constant "
        "{mat_timeconst_s} s, full stiffness only {mat_give_m} m deep), not a foam body; it is {mat_gap_m} m "
        "behind the bar's plane",
        "the bar is rigid (no sag); no wind; the athlete alone, one trial at one height, {bar_height_m} m "
        "(FAMILIES.md: a school competition's opening height; the men's world record is 2.45 m)",
        "TR 27 does not define a jump; here its flight lasts at least {min_air_s} s and raises the pelvis at least "
        "{rise_min_m} m above its height at lift-off",
        "the bar is rigid and its supports are fixed, so unlike a real bar it would carry a body: touching it is "
        "allowed, as in the rules, but contact with it for more than {bar_touch_max_s} s in all is a failure (a real "
        "bar sags and falls under any weight); a pelvis or a foot that comes back over the plane has not passed it",
    ]
    time_limit_s = 60.0
    start = (-8.0, 0.0, 0.0)
    stages = ["take-off", "clearance", "bar stays"]
    fall_rule = False                # no rule of the event says a fall is a failure; the contacts below judge it
    params = dict(bar_height_m=1.00, bar_length_m=4.00, bar_diameter_m=0.030, bar_mass_kg=2.0, upright_gap_m=4.02,
                  support_width_m=0.04, support_length_m=0.06, mat_length_m=4.0, mat_width_m=6.0, mat_height_m=0.70,
                  mat_gap_m=0.10, mat_timeconst_s=0.08, mat_give_m=0.10, runway_m=15.0, single_support_s=0.05,
                  min_air_s=0.05, rise_min_m=0.05, bar_drop_m=0.05, bar_wait_s=2.0, bar_touch_max_s=0.3)

    sentence = ("Do a high jump: approach the bar, take off from one foot, go over the bar between the uprights "
                "without knocking it off its supports, and come down on the landing mat.")
    rules = ("World Athletics rules for the high jump. The bar ({bar_length_m} m long, {bar_diameter_m} m thick, "
             "{bar_mass_kg} kg) rests with its upper side {bar_height_m} m above the ground on two flat supports "
             "({support_width_m} m wide, {support_length_m} m long) that face each other from two uprights "
             "{upright_gap_m} m apart; pushed more than half a support's width forwards or backwards, or lifted, "
             "it falls. The bar lies across y in the plane x = 0; the plane the rules mean is that of its nearer "
             "edge, x = -{bar_diameter_m}/2. Behind it lies the landing mat: {mat_width_m} m wide, {mat_length_m} m "
             "deep, {mat_height_m} m high, soft, beginning {mat_gap_m} m behind that plane. The approach is free "
             "(any direction, any distance on the {runway_m} m of level runway). A flight is a time of at least "
             "{min_air_s} s in which nothing of you touches anything but the bar. Your jump is the flight in which "
             "your pelvis crosses the bar's plane or which ends with your first contact beyond the plane. Its "
             "take-off must be from one foot: in the last {single_support_s} s before lift-off only one foot "
             "touches the ground and nothing else of you does; and in it your pelvis must rise at least "
             "{rise_min_m} m above its height at lift-off. Before your jump nothing of you may touch the ground or "
             "the mat beyond the plane. Your pelvis and both feet (the ankle joints) must cross the plane between "
             "the uprights and higher than the bar's upper side; one that comes back over the plane has not passed "
             "it and must pass it again. You have cleared the bar when every part of you "
             "is beyond the plane; from the landing until then nothing of you may touch the ground on the take-off "
             "side. You may touch the bar, for at most {bar_touch_max_s} s in all (it does not carry you), and you "
             "may land on any part of your body, on the mat or not. You "
             "succeed when you have cleared the bar and landed, and {bar_wait_s} s later the bar is still on its "
             "supports. A fall is not a failure by itself. You fail if the bar drops more than {bar_drop_m} m at "
             "any time; if you are in contact with the bar for more than {bar_touch_max_s} s in all; if you touch the "
             "ground or the mat beyond the plane without a jump; if the take-off is not "
             "from one foot; if the flight is not a jump; if your pelvis or a foot passes the plane outside the "
             "uprights or not higher than the bar; if you touch the ground on the take-off side after the "
             "landing before you have cleared the bar; or after {time_limit_s} s (the time allowed for a trial).")
    venue = ("You stand on the runway facing the bar (+x), your pelvis 8 m before it, opposite its middle. The bar "
             "is red with white ends, the uprights grey, the mat blue; the runway is level and goes on 15 m before "
             "the bar and to both sides.")
    difficulty = ("The bar is at the height of the robot's hip joints: the whole 67 kg body has to be thrown over "
                  "it from one leg. The robot has no running or jumping gait at all; its walking gait reaches "
                  "0.7 m/s.")

    # ------------------------------------------------------------------ the venue
    def build(self, sc):
        p = self.p
        R = p["runway_m"]
        sc.box("runway", (-R / 2, 0, 0.0003), (R / 2, 8.0, 0.0003), rgba=(0.72, 0.25, 0.18, 1))
        self.bar = official_bar(sc, "bar", 0.0, p["bar_height_m"], p)
        hx, hy, hz = p["mat_length_m"] / 2, p["mat_width_m"] / 2, p["mat_height_m"] / 2
        x0 = self.bar["plane_x"] + p["mat_gap_m"]
        sc.box("mat", (x0 + hx, 0.0, hz), (hx, hy, hz), rgba=(0.15, 0.35, 0.75, 1), solid="stand",
               friction=(1.0, 0.005, 0.0001), solref=(p["mat_timeconst_s"], 1.0),
               solimp=(0.3, 0.9, p["mat_give_m"], 0.5, 2), priority=1)
        sc.ground.append("mat")
        sc.camera("venue", (-12.0, -6.0, 3.2), (-2.5, 0.0, 0.7), fovy=50)
        sc.camera("bar", (-4.5, -6.5, 2.6), (0.3, 0.0, 0.7), fovy=58)

    def reset(self, w):
        w.put("bar", (self.bar["x"], 0.0, self.bar["rest_z"]))

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        m = w.m
        self.sole = {s: ref.part(f"{s}_foot") for s in SIDES}
        self.points = {"left foot": m.body("left_ankle_roll_link").id, "right foot": m.body("right_ankle_roll_link").id,
                       "pelvis": w.robot.pelvis}
        self.bar_mask = ref.geoms(body="bar")
        self.robot = ref.part("robot")
        # phase: approach -> jump (its take-off judged) ; crossed: who has passed the plane; prev: the points one
        # physics step ago; last_on / at_t0: the feet's last ground contact (now / at the start of the current flight)
        self.trackers = {"flights": Flights(ref, min_air=self.p["min_air_s"], also_allowed=self.bar_mask),
                         "phase": "approach", "crossed": [], "prev": None, "last_on": {"left": -1.0, "right": -1.0},
                         "other_on": -1.0, "at_t0": None, "t_land": None, "t_clear": None, "bar_z0": None, "bar_s": 0.0}

    def _takeoff(self, w, ref) -> bool:
        """Judge the take-off of the jump's flight (TR 27.1: one foot). False: the attempt has failed."""
        tr, p = self.trackers, self.p
        t0 = tr["at_t0"]
        foot = max(SIDES, key=lambda s: t0[s])
        other = "right" if foot == "left" else "left"
        if t0[foot] - max(t0[other], t0["other"]) < p["single_support_s"]:
            ref.fail("the take-off was not from one foot", feet_left_apart_s=round(t0[foot] - t0[other], 3),
                     other_part_s=round(t0[foot] - t0["other"], 3))
            return False
        tr["phase"] = "jump"
        ref.stage("take-off", foot=foot)
        return True

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        fl = tr["flights"]
        plane, half, H = self.bar["plane_x"], self.bar["half_gap"], p["bar_height_m"]
        if tr["bar_z0"] is None:
            tr["bar_z0"] = float(w.pos("bar")[2])
        if float(w.pos("bar")[2]) < tr["bar_z0"] - p["bar_drop_m"]:
            return ref.fail("the bar did not stay on its supports")
        if ref.has("clearance") and tr["t_land"] is not None:
            return
        if ref.touching(self.robot, self.bar_mask):      # the rigid bar would carry a body: a real one would not
            tr["bar_s"] += w.m.opt.timestep
            if tr["bar_s"] > p["bar_touch_max_s"]:
                return ref.fail("rested on the bar", bar_contact_s=round(tr["bar_s"], 3))
        was_air = fl.air
        done = fl.update()                               # a flight of at least min_air_s that lands now, or None
        if fl.air and not was_air:
            tr["at_t0"] = {**tr["last_on"], "other": tr["other_on"]}
        for s in SIDES:
            if ref.touching(self.sole[s], ref.ground):
                tr["last_on"][s] = ref.time
        if ref.parts_touching(~ref.robot_mask & ~self.bar_mask) - {"left_foot", "right_foot"}:
            tr["other_on"] = ref.time
        pts = {k: [float(x) for x in w.d.xpos[b]] for k, b in self.points.items()}
        prev, tr["prev"] = tr["prev"], pts
        in_flight = fl.air and ref.time - fl.cur["t0"] >= p["min_air_s"]
        for k, (x1, y1, z1) in pts.items():              # the pelvis or an ankle through the plane: where?
            if prev is None:
                continue
            x0, y0, z0 = prev[k]
            if x1 < plane <= x0 and k in tr["crossed"] and not ref.has("clearance"):
                tr["crossed"] = [c for c in tr["crossed"] if c != k]       # came back: it has not passed the bar
                continue
            if k in tr["crossed"] or not x0 < plane <= x1:
                continue
            f = (plane - x0) / (x1 - x0)
            y, z = y0 + (y1 - y0) * f, z0 + (z1 - z0) * f
            if abs(y) >= half:
                return ref.fail("went round the bar", what=k, y=round(y, 3))
            if z <= H:
                return ref.fail("passed under the bar", what=k, z=round(z, 3))
            tr["crossed"] = sorted(tr["crossed"] + [k])
            if k == "pelvis" and tr["phase"] == "approach" and in_flight and not self._takeoff(w, ref):
                return
        cp = ref.contact_points(self.robot, ref.ground)
        beyond = len(cp) and bool(np.any(cp[:, 0] > plane))
        if tr["t_land"] is None and beyond:              # the first contact beyond the plane
            if tr["phase"] == "approach":
                if done is None:
                    return ref.fail("touched the ground or the mat beyond the bar's plane without a jump",
                                    parts=sorted(ref.parts_touching(ref.ground)))
                if not self._takeoff(w, ref):
                    return
            if done is not None:                         # the jump's flight has ended: was it a jump?
                rise = done["apex_z"] - done["pelvis0"][2]
                ref.metrics["air_s"], ref.metrics["rise_m"] = done["air_s"], round(rise, 3)
                if rise < p["rise_min_m"]:
                    return ref.fail("the flight was not a jump", rise_m=round(rise, 3))
            tr["t_land"] = ref.time
            ref.event("landing", parts=sorted(ref.parts_touching(ref.ground)),
                      on_the_mat=bool(ref.touching(self.robot, ref.geoms(names=["mat"]))))
        elif tr["t_land"] is not None and len(cp) and bool(np.any(cp[:, 0] <= plane)):
            return ref.fail("touched the ground on the take-off side before clearing the bar",
                            parts=sorted(ref.parts_touching(ref.ground)))
        if tr["phase"] == "jump" and len(tr["crossed"]) == 3 and ref.robot_span((1.0, 0.0, 0.0))[0] > plane:
            tr["t_clear"] = ref.time
            ref.stage("clearance")

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        if ref.has("clearance") and tr["t_land"] is not None:
            if ref.time - max(tr["t_clear"], tr["t_land"]) >= p["bar_wait_s"]:
                if ref.stage("bar stays"):
                    ref.succeed()

    def privileged(self, w):
        tr = self.trackers
        return {"pelvis": w.pelvis().tolist(), "bar": w.pos("bar").tolist(), "bar_top_m": self.p["bar_height_m"],
                "plane_x": self.bar["plane_x"], "phase": tr["phase"], "crossed": list(tr["crossed"]),
                "landed": tr["t_land"] is not None}
