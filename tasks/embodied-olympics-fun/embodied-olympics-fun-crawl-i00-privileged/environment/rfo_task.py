"""Crawl: the low-wire obstacle: get from standing in front of it to wholly beyond it under wires strung 0.45 m above
the ground over 10 m, without touching a wire."""
from rfo.scene import HITTABLE
from rfo.task import TaskBase


class Task(TaskBase):
    name = "crawl"
    title = "Low-wire crawl"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("No federation rule book: the low-wire crawl of military obstacle courses and obstacle-course racing "
                "(wires strung about 18 in, 0.45 m, above the ground; the athlete passes under all of them and may "
                "not go round or over). The layout is this benchmark's: wires every 0.5 m over 10 m")
    deviations = [
        "the wires: each wire is a rigid, fixed bar 8 mm thick between two posts, not a slack (barbed) wire, because "
        "the simulator has rigid bodies only; touching one fails the attempt, as a judge's fault for a snagged wire",
        "the ground: level and rigid with a friction coefficient of 1.0, not sand or mud, because the simulator's "
        "ground is rigid",
    ]
    time_limit_s = 120.0
    start = (0.0, 0.0, 0.0)
    fall_rule = False                # the body is meant to be on the ground here: the family's own rules judge it
    stages = ["under the first wire", "half way", "through"]
    params = dict(wire_height_m=0.45, course_length_m=10.0, wire_spacing_m=0.5, lane_width_m=2.0,
                  start_distance_m=1.0, wire_diameter_m=0.008)

    sentence = ("Get under the low wires in front of you and crawl the whole course until your whole body is beyond "
                "the last wire, without touching a wire.")
    rules = ("The obstacle is a lane along +x, {lane_width_m} m wide between two rows of posts, centred on y = 0. "
             "Horizontal wires cross it every {wire_spacing_m} m over {course_length_m} m: the first is "
             "{start_distance_m} m ahead of where your pelvis starts, the last {course_length_m} m further on. Each "
             "wire is {wire_diameter_m} m thick with its centre {wire_height_m} m above the ground. You succeed when "
             "your whole body (every part of you) is beyond the last wire, having passed under all of them. There is "
             "no fall rule: any part of you may touch the ground, and you need not stand up at the end. You fail the "
             "moment any part of you touches a wire; if your pelvis, while it is between the first and the last "
             "wire, is higher than {wire_height_m} m (going over) or outside the lane (going round, beyond a row of "
             "posts); if your whole body is beyond the last wire without your pelvis having passed under the wires; "
             "or after {time_limit_s} s. The posts may be touched.")
    venue = ("You stand upright on level ground facing the obstacle (+x), on its centre line, your pelvis "
             "{start_distance_m} m before the first wire. You are 1.32 m tall and your pelvis is 0.79 m high when you "
             "stand: the wires are lower than your hips. The posts stand at the two ends of every wire, "
             "{lane_width_m} m apart; the ground under the wires is the same level, rigid ground. The last wire is "
             "painted yellow.")
    difficulty = ("Neither built-in gait works below {wire_height_m} m, and on hands and knees this robot is about "
                  "0.46 m high, just too tall: it has to get down from standing and move {course_length_m} m and its "
                  "own length flat on the ground with joint commands of its own, never lifting any part into a wire.")

    def build(self, sc):
        p = self.p
        H, L, S, W, D = (p["wire_height_m"], p["course_length_m"], p["wire_spacing_m"], p["lane_width_m"],
                         p["start_distance_m"])
        r = p["wire_diameter_m"] / 2
        n = int(round(L / S)) + 1
        self.course = dict(x0=D, x1=D + L, half_width=W / 2, height=H, wires=[D + i * S for i in range(n)])
        for i, x in enumerate(self.course["wires"]):
            last = i == n - 1
            sc.geom(sc.wb, f"wire{i:02d}", type="capsule", fromto=(x, -W / 2, H, x, W / 2, H), size=(r,),
                    rgba=(0.95, 0.85, 0.2, 1) if last else (0.75, 0.75, 0.78, 1), **HITTABLE)
            for s, tag in ((1, "L"), (-1, "R")):
                sc.geom(sc.wb, f"post{i:02d}{tag}", type="cylinder", pos=(x, s * (W / 2 + 0.02), (H + 0.05) / 2),
                        size=(0.02, (H + 0.05) / 2), rgba=(0.35, 0.28, 0.20, 1), **HITTABLE)
        sc.line("start_line", (D, -W / 2), (D, W / 2))
        sc.line("end_line", (D + L, -W / 2), (D + L, W / 2), rgba=(0.95, 0.85, 0.2, 1))
        sc.camera("venue", (D + L / 2 - 2.0, -7.5, 3.2), (D + L / 2 - 0.5, 0.0, 0.2), fovy=55)
        sc.camera("entrance", (-1.6, -1.6, 0.9), (D + 1.0, 0.0, 0.35), fovy=50)

    def referee_reset(self, w, ref):
        self.wires = ref.geoms(prefix="wire")
        self.robot = ref.part("robot")
        self.trackers = {"under": False}

    def substep(self, w, ref):
        if ref.touching(self.robot, self.wires):
            ref.fail("touched a wire", parts=sorted(ref.parts_touching(self.wires)))

    def step(self, w, ref):
        c, tr = self.course, self.trackers
        if ref.failed:
            return
        x, y, z, _ = w.pelvis()
        lo, hi = ref.robot_span((1.0, 0.0, 0.0))
        ref.metrics["rear_x_m"] = round(float(lo), 3)
        at = [round(float(v), 3) for v in (x, y, z)]
        if c["x0"] <= x <= c["x1"]:
            if abs(y) > c["half_width"]:
                return ref.fail("went round the wires", pelvis=at)
            if z > c["height"]:
                return ref.fail("went over the wires", pelvis=at)
            tr["under"] = True
            if lo > c["x0"]:
                ref.stage("under the first wire")
            if x >= (c["x0"] + c["x1"]) / 2:
                ref.stage("half way")
        if lo > c["x1"]:
            if not tr["under"] or not ref.has("half way"):
                return ref.fail("did not pass under the wires", pelvis=at)
            if ref.stage("through"):
                ref.metrics["time_s"] = round(w.t, 2)
                ref.succeed()

    def privileged(self, w):
        return {"pelvis": w.pelvis().tolist(), "course": self.course,
                "top_z": float(w.robot_aabb()[1][2]), "rear_x": float(w.ref.robot_span((1.0, 0.0, 0.0))[0])}
