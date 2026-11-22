"""Balance beam: on the FIG beam (5 m long, 0.10 m wide, 1.25 m high), walk from the end the robot stands on to the
other end and stand there; nothing may touch the floor.

The beam is narrower than the robot's stance (its feet are 0.24 m apart, each 0.07 m wide at the sole), so it starts in
a tandem stance, one foot in front of the other on the centre line, held by its joints (not by the `stand` action,
whose stance would put both feet beside the beam)."""
import math

import numpy as np

from rfo.task import TaskBase

# The tandem stance of the G1 (solved by inverse kinematics for both soles flat on one line, the left foot's centre
# 0.24 m ahead of the right foot's, the centre of mass over the middle between them): leg joints in the SDK order
# (hip pitch, roll, yaw, knee, ankle pitch, roll), left then right.
TANDEM_LEGS = np.array([-0.3999, -0.2068, 0.0, 0.3505, 0.0593, 0.1732,
                        -0.0607, 0.2140, 0.0, 0.4657, -0.3997, -0.2080])
TANDEM_COM = (0.0192, 0.0003)        # the centre of mass ahead / left of the pelvis in that pose (m)
TANDEM_SOLE = 0.755                  # the pelvis above the soles in that pose (m)
FOOT_SEP = 0.24                      # the feet centres' distance along the beam
JOINT_MODE = 4                       # rfo.world.JOINT: the robot's joints hold their targets (no platform stance)


class Task(TaskBase):
    name = "balance-beam"
    title = "Balance beam"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("FIG Apparatus Norms (Fédération Internationale de Gymnastique), women's artistic gymnastics, balance "
                "beam: length 5.00 m, width of the top 0.10 m, depth of the beam body 0.16 m, top 1.25 m above the "
                "floor; FIG Code of Points, women's artistic gymnastics: a beam exercise lasts at most 1 min 30 s")
    deviations = [
        "FIG Apparatus Norms, balance beam (padding): the beam is rigid with a friction coefficient of 1.0, without "
        "the norm's thin elastic padding and suede cover, because the simulator has rigid bodies only",
        "FIG Apparatus Norms, landing mats: there are no 0.20 m mats round the beam; the floor is 1.25 m below the "
        "top, because anything touching the floor ends the attempt anyway",
        "FIG Code of Points (a routine is scored, a fall costs 1.00): one pass along the beam is judged pass or fail, "
        "because the task is a single action; a hand or any part other than a foot on the beam counts as a fall here",
    ]
    time_limit_s = 90.0                # the Code of Points' longest beam exercise
    start = (0.25, 0.0, 0.0)
    fall_rule = False                 # the family's own rule: only the feet on the beam, nothing on the floor
    stages = ["half way", "far end", "stand"]
    params = dict(length_m=5.00, width_m=0.10, height_m=1.25, depth_m=0.16, end_zone_m=0.50, stand_s=2.0,
                  stand_tilt_deg=20.0, still_m_s=0.35)

    sentence = ("Walk along the balance beam from the end you stand on to the other end and stand there, without "
                "anything touching the floor.")
    rules = ("The beam is a competition balance beam: {length_m} m long, {width_m} m wide on top and {depth_m} m "
             "deep, its top {height_m} m above the floor; it runs along +x from x = 0 to x = {length_m} m, centred on y = 0, on two "
             "supports. You must get from the end you start on to the far end on your feet. The far end is the last "
             "{end_zone_m} m of the beam. You succeed when both feet are on the beam with every point at which they "
             "touch it inside the far end, and you then stand there for {stand_s} s without a break: only your feet "
             "touch the beam, your torso is within {stand_tilt_deg} degrees of vertical and your pelvis moves slower "
             "than {still_m_s} m/s. You fail the moment any part of you touches the floor or the beam's supports "
             "(a fall from the beam), the moment any part of you other than a foot touches the beam (a fall on the "
             "beam: no hands, knees or sitting), or after {time_limit_s} s. Leaving the beam with both feet (a hop) "
             "is allowed as long as you come down on it on your feet.")
    venue = ("At t = 0 you stand on the beam's near end, facing along it (+x), in a tandem stance: the left foot in "
             "front of the right, both on the beam's centre line, the feet's centres 0.15 m and 0.39 m from the near "
             "end (the soles reach from 0.09 m to 0.52 m); your pelvis is 0.25 m from the near end and 0.75 m above "
             "the beam's top, so your soles are {height_m} m above the floor. The beam is narrower than your normal "
             "stance (your feet are normally 0.24 m apart; each sole is 0.07 m wide), so here the robot does NOT "
             "start in `stand` mode: it starts with all its joints holding the tandem pose on the default gains, as "
             "after a `joints` row, and the hold command at t = 0 is a `lowcmd` row that keeps those targets (left "
             "alone, the robot stays standing like that). A `stand` row would move the legs to the normal stance and "
             "a `walk` row would start the normal gait: both put the feet beside the beam. The beam and its two "
             "supports (0.9 m from each end) are fixed; the far end is marked yellow.")
    difficulty = ("The beam is {width_m} m wide and the robot's built-in stance and gait keep the feet 0.24 m "
                  "apart, so neither can be used: every step is a single-leg balance on a sole 0.07 m wide, "
                  "{height_m} m above the floor, for {length_m} m.")

    def build(self, sc):
        p = self.p
        L, W, H, D = p["length_m"], p["width_m"], p["height_m"], p["depth_m"]
        grey = (0.30, 0.30, 0.33, 1)
        sc.box("beam", (L / 2, 0.0, H - D / 2), (L / 2, W / 2, D / 2), rgba=(0.80, 0.68, 0.50, 1), solid="stand",
               friction=(1.0, 0.005, 0.0001))
        for i, x in enumerate((0.9, L - 0.9)):                 # the two supports: a column on a floor base
            sc.box(f"beam_leg{i}", (x, 0.0, (H - D) / 2), (0.04, 0.04, (H - D) / 2), rgba=grey, solid="stand")
            sc.box(f"beam_base{i}", (x, 0.0, 0.02), (0.05, 0.45, 0.02), rgba=grey, solid="stand")
        z = H + 0.0004
        sc.box("far_end_mark", (L - p["end_zone_m"] / 2, 0, z), (p["end_zone_m"] / 2, W / 2, 0.0004),
               rgba=(0.95, 0.85, 0.2, 1))
        sc.camera("venue", (L / 2 - 1.2, -5.2, 2.6), (L / 2 - 0.3, 0.0, 1.35), fovy=55)
        sc.camera("beam_end", (-2.2, -1.2, 2.3), (0.6, 0.0, 1.65), fovy=45)

    def reset(self, w):
        r, d = w.robot, w.d
        legs = r.arb.GROUPS["legs"]
        d.qpos[r.qadr[legs]] = TANDEM_LEGS
        d.qpos[r.fq + 1] = self.start[1] - TANDEM_COM[1]         # the centre of mass over the beam's centre line
        d.qpos[r.fq + 2] = self.p["height_m"] + TANDEM_SOLE
        w._hold_legs()                                           # the legs' hold targets: this pose
        w.mode = JOINT_MODE                                      # the command in force is a joint hold, not `stand`

    def referee_reset(self, w, ref):
        self.floor = ref.geoms(names=["floor"]) | ref.geoms(prefix="beam_leg") | ref.geoms(prefix="beam_base")
        self.beam_g = ref.geoms(names=["beam"])
        self.robot = ref.part("robot")
        self.not_feet = ref.part("robot") & ~ref.part("feet")
        self.foot = {s: ref.part(f"{s}_foot") for s in ("left", "right")}
        self.min_upright = math.cos(math.radians(self.p["stand_tilt_deg"]))
        self.trackers = {}

    def substep(self, w, ref):
        if ref.touching(self.robot, self.floor):
            ref.fail("touched the floor", parts=sorted(ref.parts_touching(self.floor)))
        elif ref.touching(self.not_feet, self.beam_g):
            ref.fail("fell on the beam", parts=sorted(ref.parts_touching(self.beam_g) - {"left_foot", "right_foot"}))

    def feet_span(self, ref):
        """(the rearmost, the foremost) x at which the feet touch the beam, or None unless both feet are on it."""
        lo, hi = [], []
        for s in ("left", "right"):
            pts = ref.contact_points(self.foot[s], self.beam_g)
            if not len(pts):
                return None
            lo.append(float(pts[:, 0].min()))
            hi.append(float(pts[:, 0].max()))
        return min(lo), max(hi)

    def step(self, w, ref):
        p = self.p
        if ref.failed:
            return
        span = self.feet_span(ref)
        if span is not None:
            ref.metrics["distance_m"] = round(max(ref.metrics.get("distance_m", 0.0), span[0]), 3)
            if span[0] >= p["length_m"] / 2:
                ref.stage("half way")
        zone = span is not None and span[0] >= p["length_m"] - p["end_zone_m"]
        if zone:
            ref.stage("far end")
        still = ref.standing(max_speed=p["still_m_s"], min_upright=self.min_upright, on=self.beam_g)
        if ref.hold("stand", zone and still, p["stand_s"]) and ref.has("far end"):
            if ref.stage("stand"):
                ref.metrics["time_s"] = round(w.t, 2)
                ref.succeed()

    def privileged(self, w):
        p = self.p
        return {"pelvis": w.pelvis().tolist(), "com": w.com().tolist(),
                "beam": {"x": [0.0, p["length_m"]], "half_width": p["width_m"] / 2, "top": p["height_m"]},
                "far_end_x": [p["length_m"] - p["end_zone_m"], p["length_m"]],
                "feet": {s: w.d.site_xpos[w.robot.foot_site[s]].tolist() for s in ("left", "right")}}
