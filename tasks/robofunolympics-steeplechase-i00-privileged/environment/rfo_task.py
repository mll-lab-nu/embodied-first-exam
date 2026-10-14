"""Steeplechase: the water jump (World Athletics TR 23). Over the fixed 0.914 m hurdle, over or through the 3.66 m
water pit behind it, and out beyond its far edge on the feet."""
import math
import xml.etree.ElementTree as ET

from rfo.referee import Crossing
from rfo.scene import STANDABLE, VISUAL, quat_z
from rfo.task import TaskBase

TRACK = (0.62, 0.25, 0.20, 1)
SIDES = ("left", "right")


class Task(TaskBase):
    name = "steeplechase"
    title = "Steeplechase: the water jump"
    category = "parkour-apparatus-balance"
    robot = "unitree_h1"
    rulebook = ("World Athletics Competition and Technical Rules 2024, Technical Rule 23 (steeplechase races): the "
                "men's hurdle 0.914 m high with a top bar 0.127 m square; the hurdle at the water jump 3.66 m wide and "
                "fixed; the water jump 3.66 m long including the hurdle, the pit 3.66 m wide, 0.50 m deep at the "
                "hurdle for about 1.20 m, then a uniform slope up to the level of the track at the far end; each "
                "athlete shall go over each hurdle (in any manner) and over or through the water, and is disqualified "
                "for stepping to one side of the water jump or trailing a foot or leg below the horizontal plane of "
                "the top of the hurdle at the instant of clearance")
    deviations = [
        "TR 23 (the race): one water jump from a {approach_m} m approach instead of a 3000 m race with 28 hurdle and "
        "7 water jumps (a single action; the family is the water jump)",
        "TR 23 (the water jump): the water itself is not simulated; the pit is dry and its floor is the hard, "
        "sloping bottom (the simulator has no free-surface water; what remains is the pit's real geometry)",
        "TR 23 (clearance): \"foot or leg below the top of the hurdle\" is judged on the centres of the two feet and "
        "the pelvis where each crosses the vertical plane through the middle of the hurdle's top bar (three points "
        "a referee can measure on a robot)",
        "the finish: with no race to run on to, the attempt ends when the whole body is beyond the pit's far edge "
        "and the robot has stood on its feet for {stand_s} s",
    ]
    time_limit_s = 60.0
    start = (0.0, 0.0, 0.0)
    stages = ["hurdle", "out of the water jump", "stand"]
    fall_rule = False                # a runner who falls in the water gets up: the family's own rules judge the ground
    params = dict(approach_m=10.0, hurdle_height_m=0.914, hurdle_width_m=3.66, bar_m=0.127, water_jump_length_m=3.66,
                  pit_width_m=3.66, pit_depth_m=0.50, pit_deep_length_m=1.20, side_top_tol_m=0.05, stand_s=1.0,
                  stand_tilt_deg=20.0, still_m_s=0.35)

    sentence = ("Go over the steeplechase hurdle in front of you and over or through the water pit behind it, get out "
                "beyond the pit's far edge and stand on your feet.")
    rules = ("The hurdle is fixed (it does not move or topple): its top bar is {bar_m} m square, {hurdle_width_m} m "
             "wide, with its top {hurdle_height_m} m above the track, on a post at each end. Its near face is "
             "{approach_m} m ahead of where your pelvis starts. The water jump is {water_jump_length_m} m long "
             "measured from the hurdle's near face, and {pit_width_m} m wide, centred on your line: the pit is "
             "{pit_depth_m} m deep for the first {pit_deep_length_m} m and then slopes up evenly to the track's level "
             "at its far edge. There is no water in it. You must go over the hurdle: every time your pelvis or the "
             "centre of either foot crosses, going forward, the vertical plane through the middle of the top bar, "
             "that point must be higher than the bar's top ({hurdle_height_m} m), and your pelvis must also be "
             "between the two ends of the bar; otherwise you fail. You may go over the hurdle in any manner: your "
             "hands and feet may touch it or stand on it. Once your pelvis is beyond that plane and until your "
             "whole body is beyond the pit's far edge, you fail if your pelvis is outside the pit's width or if any "
             "part of you touches the track's surface beside the pit (a contact less than {side_top_tol_m} m below "
             "the track's level; the pit's side walls below that may be touched). You may land in the pit or beyond it, and any part of "
             "you may touch the pit's floor and walls and the track before and beyond the pit: there is no fall "
             "rule. You succeed when your whole body is beyond the pit's far edge and you then stand for {stand_s} s "
             "without a break: only your feet on the ground, your torso within {stand_tilt_deg} degrees of vertical, "
             "your pelvis moving no faster than {still_m_s} m/s. The attempt ends after {time_limit_s} s of robot time.")
    venue = ("You stand on the track facing the hurdle (+x), on the centre line of the water jump. The hurdle's near "
             "face is {approach_m} m ahead; its bar is as high as your hip joints. Directly behind the bar the pit "
             "drops {pit_depth_m} m; its far edge is {water_jump_length_m} m beyond the hurdle's near face. The track "
             "continues level beyond the pit and on both sides of it.")
    difficulty = ("The bar is at hip height and the walking policy lifts its feet a few centimetres: the hurdle has "
                  "to be jumped or climbed with whole-body joint control by a 67 kg robot whose best standing jump "
                  "raises it far less than {hurdle_height_m} m. Behind the bar the ground is {pit_depth_m} m lower "
                  "than the track, so the landing is a drop of up to 1.4 m, and the way out is a slope.")

    def build(self, sc):
        p = self.p
        A, H, W, B = p["approach_m"], p["hurdle_height_m"], p["hurdle_width_m"], p["bar_m"]
        Lw, PW, Dp, Ld = p["water_jump_length_m"], p["pit_width_m"], p["pit_depth_m"], p["pit_deep_length_m"]
        x0, x1, hw = A, A + Lw, PW / 2
        self.geo = dict(hurdle_x=(x0, x0 + B), plane_x=x0 + B / 2, top=H, half_width=W / 2, pit_x=(x0, x1),
                        pit_half_width=hw, pit_depth=Dp, slope_from_x=x0 + Ld)
        # The H1-2's sole is one convex hull: on a box (unlike the floor plane) MuJoCo gives a convex pair a single
        # contact point unless multiccd is on, and a foot on one point does not stand. The track here is boxes.
        ET.SubElement(sc.root.find("option"), "flag", multiccd="enable")
        # the scene's floor becomes the pit's bottom; the track is built around the hole at z = 0
        floor = sc.wb.find("geom[@name='floor']")
        floor.set("pos", f"0 0 {-Dp:g}")
        floor.set("rgba", "0.35 0.45 0.60 1")
        t = Dp + 0.10                                    # the blocks reach 0.10 m below the pit's bottom
        blocks = {"track_approach": ((-8.0, x0), (-9.0, 9.0)), "track_beyond": ((x1, x1 + 14.0), (-9.0, 9.0)),
                  "track_side_left": ((x0, x1), (hw, 9.0)), "track_side_right": ((x0, x1), (-9.0, -hw))}
        for name, ((xa, xb), (ya, yb)) in blocks.items():
            sc.box(name, ((xa + xb) / 2, (ya + yb) / 2, -t / 2), ((xb - xa) / 2, (yb - ya) / 2, t / 2), rgba=TRACK,
                   solid="stand", friction=(1.0, 0.005, 0.0001))
            sc.ground.append(name)
        # the sloping bottom: a slab whose top face runs from the deep part's end, at the bottom, to the far edge
        xs = x0 + Ld
        run = x1 - xs
        ang = math.atan2(Dp, run)
        length, th = math.hypot(run, Dp), 0.20
        cx, cz = (xs + x1) / 2 + math.sin(ang) * th / 2, -Dp / 2 - math.cos(ang) * th / 2
        sc.geom(sc.wb, "pit_slope", type="box", pos=(cx, 0.0, cz), size=(length / 2, hw, th / 2),
                quat=(math.cos(-ang / 2), 0.0, math.sin(-ang / 2), 0.0), rgba=(0.35, 0.45, 0.60, 1),
                friction=(1.0, 0.005, 0.0001), **STANDABLE)
        sc.ground.append("pit_slope")
        self.geo["slope_deg"] = math.degrees(ang)
        # the hurdle: the top bar on two posts that stand in the pit's corners (fixed)
        grey = (0.92, 0.92, 0.92, 1)
        sc.geom(sc.wb, "hurdle_bar", type="box", pos=(x0 + B / 2, 0.0, H - B / 2), size=(B / 2, W / 2, B / 2), rgba=grey,
                friction=(1.0, 0.005, 0.0001), **STANDABLE)
        for s, tag in ((1, "L"), (-1, "R")):
            zc = (H - B - Dp) / 2
            sc.geom(sc.wb, f"hurdle_post{tag}", type="box", pos=(x0 + B / 2, s * (W / 2 - B / 2), zc),
                    size=(B / 2, B / 2, (H - B + Dp) / 2), rgba=(0.15, 0.15, 0.15, 1), **STANDABLE)
        # where the water would be (visual only)
        sc.geom(sc.wb, "water", type="box", pos=((x0 + x1) / 2, 0.0, -Dp / 2 - 0.01), size=(Lw / 2, hw, Dp / 2),
                rgba=(0.25, 0.55, 0.85, 0.18), **VISUAL)
        sc.line("lane_left", (-2.0, hw), (x0, hw))
        sc.line("lane_right", (-2.0, -hw), (x0, -hw))
        sc.camera("venue", (x1 / 2 - 1.0, -11.0, 4.2), (x1 / 2, 0.0, 0.3), fovy=62)        # the start to the far edge
        sc.camera("water_jump", (x0 - 3.2, -6.5, 2.6), (x0 + 1.4, 0.0, 0.2), fovy=50)

    def referee_reset(self, w, ref):
        g = self.geo
        self.sides_g = ref.geoms(names=["track_side_left", "track_side_right"])
        self.robot = ref.part("robot")
        self.points = {"pelvis": lambda: w.d.xpos[w.robot.pelvis],
                       "left_foot": lambda: w.d.site_xpos[w.robot.foot_site["left"]],
                       "right_foot": lambda: w.d.site_xpos[w.robot.foot_site["right"]]}
        self.trackers = {"cross": {k: Crossing((1.0, 0.0, 0.0), g["plane_x"], direction=1) for k in self.points},
                         "over": {k: False for k in self.points}}

    def substep(self, w, ref):
        g, tr = self.geo, self.trackers
        if ref.has("out of the water jump"):
            return
        for k, get in self.points.items():
            x = tr["cross"][k].update(get())
            if x is None:
                continue
            at = dict(point=k, y=round(float(x[1]), 3), z=round(float(x[2]), 3))
            if x[2] <= g["top"]:
                return ref.fail("did not go over the hurdle", how="below its top", **at)
            if k == "pelvis" and abs(x[1]) > g["half_width"]:
                return ref.fail("did not go over the hurdle", how="outside its width", **at)
            tr["over"][k] = True
            ref.event("over the hurdle", **at)
        px, py = (float(v) for v in w.d.xpos[w.robot.pelvis][:2])
        if px > g["plane_x"]:
            if abs(py) > g["pit_half_width"]:
                return ref.fail("stepped to the side of the water jump", pelvis_y=round(py, 3))
            pts = ref.contact_points(self.robot, self.sides_g)
            if len(pts) and float(pts[:, 2].max()) > -self.p["side_top_tol_m"]:
                return ref.fail("stepped to the side of the water jump", parts=sorted(ref.parts_touching(self.sides_g)))

    def step(self, w, ref):
        g, p, tr = self.geo, self.p, self.trackers
        if ref.failed:
            return
        rear = ref.robot_span((1.0, 0.0, 0.0))[0]
        ref.metrics["rear_x_m"] = round(float(rear), 3)
        if all(tr["over"].values()) and rear > g["hurdle_x"][1]:
            ref.stage("hurdle")
        out = rear > g["pit_x"][1]
        if out:
            ref.stage("out of the water jump")
        standing = ref.standing(max_speed=p["still_m_s"], min_upright=math.cos(math.radians(p["stand_tilt_deg"])))
        if ref.has("out of the water jump") and ref.hold("stand", out and standing, p["stand_s"]):
            if ref.stage("stand"):
                ref.metrics["time_s"] = round(w.t, 2)
                ref.succeed()

    def privileged(self, w):
        return {"pelvis": w.pelvis().tolist(), **{k: (list(v) if isinstance(v, tuple) else v) for k, v in self.geo.items()},
                "over": dict(self.trackers.get("over", {}))}
