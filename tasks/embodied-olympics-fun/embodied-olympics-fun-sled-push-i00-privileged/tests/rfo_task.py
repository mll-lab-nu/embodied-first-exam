"""Sled push: one length of HYROX's sled-push station (12.5 m on turf), a weighted prowler-type push sled pushed with
the bare palms on its two upright handles (no grip), within the time limit. The Unitree H1-2."""
import math

import numpy as np

from rfo.scene import HITTABLE, VISUAL
from rfo.task import TaskBase
# A rigid sled's steel frame (poles, deck, post, plates; the runners keep their turf contact)'s contact with the
# robot, the venue's fixtures and the other props (the ground keeps its own: rfo/world.py GROUND_SOLMIX): the stiff
# contact of the core's shells (rfo/world.py SHELL_CONTACT: solref 0.004 s, solimp 0.99 0.999 0.0005, from
# Embodied Olympics' weightlifting fix, a rigid prop on the robot's aluminium) with a solmix that wins over a default-
# contact geom; a ball (priority 1) keeps its own bounce. With MuJoCo's default soft contact (solref 0.02 1, solimp
# 0.9 0.95) it sank 49 mm into the robot and 38 mm into the turf (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402

TURF = (0.18, 0.42, 0.22, 1)
STEEL = (0.18, 0.18, 0.20, 1)
PLATE = (0.10, 0.10, 0.11, 1)


class Task(TaskBase):
    name = "sled-push"
    title = "Sled push: one 12.5 m length on turf"
    category = "parkour-apparatus-balance"
    robot = "unitree_h1"
    rulebook = ("HYROX Rulebook 2026/27 (the Sled Push station: the sled pushed 50 m in four 12.5 m lengths on the "
                "competition turf, each length counted when the whole sled is over the line; the athlete stays in the "
                "lane; the loads, the sled included: 102 kg Women Open, 152 kg Men Open and Women Pro, 202 kg Men "
                "Pro). There is no rule book for a sled push alone; HYROX's station is the closest official event")
    deviations = [
        "HYROX Sled Push (load): a light sled frame of {sled_empty_kg} kg with the dimensions and the two 1.04 m push "
        "poles of a real weight sled (a 57 lb sled, the lightest with upright poles found: 25.9 kg, 114 N to "
        "start on this turf), so that the start takes about 22 N, within what this robot's walking pushes. "
        "{sled_total_kg} kg in all ({plates_kg} kg of plates) is {load_percent_bm} % of the robot's {robot_mass_kg} "
        "kg. HYROX's lightest official load, 102 kg (Women Open), takes about {hyrox_force_n} N to start on the "
        "turf: far beyond a 67 kg robot pushing at hip height.",
        "HYROX Sled Push (distance): one 12.5 m length, not four: one action, not the station.",
        "HYROX Sled Push (technique): the sled is pushed with the palms only, on the two upright handles; hands "
        "cannot grip (the H1-2's hands are its fixed hands, which do not close), and no other part of the body may touch the sled.",
        "Turf friction: MuJoCo has one friction coefficient per contact: the runners slide on the turf at mu "
        "{runner_mu}, the measured push-sled-on-AstroTurf static range (0.37-0.53, Hoffmann 2014) mid value, "
        "above the measured kinetic range (0.28-0.35): starting is as hard as on real turf, keeping it moving harder.",
    ]
    time_limit_s = 60.0
    start = (0.0, 0.0, 0.0)
    stages = ["moved", "line"]
    fall_z = 0.50
    params = dict(length_m=12.5, lane_half_m=1.0, sled_empty_kg=5.0, plates_kg=0.0, runner_mu=0.45,
                  sled_length_m=0.919, sled_width_m=0.620, pole_height_m=1.041, pole_diameter_m=0.05,
                  sled_gap_m=0.50, move_m=0.10, robot_mass_kg=67.0, load_percent_bm=7, sled_total_kg=5.0,   # these two: _derive()
                  hyrox_force_n=450, fall_pelvis_m=0.50)

    sentence = ("Push the sled by its handles along your lane until all of it is over the line ahead.")
    rules = ("A prowler-type push sled stands on the turf in front of you, its two upright handles towards you: two "
             "steel runners {sled_length_m} m long, {sled_width_m} m apart outside, the handles {pole_diameter_m} m "
             "thick and {pole_height_m} m high at its rear corners; it carries {sled_total_kg} kg in all and its "
             "runners slide on the turf with a friction coefficient of {runner_mu}. The sled's front edge stands on "
             "the start line; the finish line is {length_m} m beyond it, and the lane is {lane_half_m} m to each side "
             "of its centre line. Push the sled: only your hands may touch it, and only on the two upright handles "
             "(they cannot grip: push, do not pull). The sled has moved once its rear has gone {move_m} m forward. "
             "You succeed when the whole sled, its rear included, is over the finish line. You fail if any part of "
             "you other than a hand touches the sled, or a hand touches it anywhere but on a handle; if any part of "
             "the sled leaves the lane; if you fall (your pelvis lower than {fall_pelvis_m} m above the ground, or "
             "any part of you other than your feet on the ground); or after {time_limit_s} s.")
    venue = ("You stand facing the sled (+x) in the middle of the lane; its two handles are {sled_gap_m} m in front of "
             "your pelvis, one each side of your centre line. The start line runs under the sled's front edge, the "
             "finish line {length_m} m farther on; the lane's side lines are {lane_half_m} m to each side.")
    difficulty = ("The sled weighs {sled_total_kg} kg on high-friction turf: keeping it moving takes a steady push of "
                  "about 22 N, against which the walking policy (trained for walking, not pushing) has to keep "
                  "its balance on 67 kg. Bare palms can only push: if the sled drifts sideways or the hands slip off "
                  "a handle, nothing holds it.")

    def configure(self, params):
        super().configure(params)
        self._derive()

    def _derive(self):
        p = self.p
        self.fall_z = p["fall_pelvis_m"]
        p["sled_total_kg"] = p["sled_empty_kg"] + p["plates_kg"]          # derived: the texts quote them
        p["load_percent_bm"] = int(round(100 * p["sled_total_kg"] / p["robot_mass_kg"]))

    # ------------------------------------------------------------------ geometry
    def geometry(self):
        p = self.p
        rear = p["sled_gap_m"]                     # the handles' rear faces (the sled's rear), ahead of the pelvis
        front = rear + p["sled_length_m"]
        return dict(rear_x=rear, front_x=front, line_x=front + p["length_m"])

    def build(self, sc):
        self._derive()
        p, g = self.p, self.geometry()
        L, W = p["sled_length_m"], p["sled_width_m"]
        sc.box("turf", (g["line_x"] / 2, 0, 0.0003), (g["line_x"] / 2 + 4.0, 4.0, 0.0003), rgba=TURF)
        sc.line("start_line", (g["front_x"], -p["lane_half_m"]), (g["front_x"], p["lane_half_m"]), width=0.05)
        sc.line("finish_line", (g["line_x"], -p["lane_half_m"]), (g["line_x"], p["lane_half_m"]), width=0.05)
        for s in (1, -1):
            sc.line(f"lane{s}", (-1.0, s * p["lane_half_m"]), (g["line_x"] + 2.0, s * p["lane_half_m"]), width=0.05)
        # The sled: the shape of the lightest push sled with two upright push poles found (a 57 lb weight sled,
        # walmart.com listing 15189613633: 36.20 x 24.40 x 41.00 in assembled, two removable push poles; 2 in poles as
        # on the PRISP power sled) at a light frame's mass (a deviation: the 25.9 kg real one needs 114 N to start,
        # beyond this robot's walking push; real speed sleds that light, Titan's 13 lb and BLK BOX's 10 kg, carry only
        # a 0.23-0.45 m plate post, below a standing robot's hands). One free body; its mass sits in the runners and
        # the frame, the plates on the central post. The runners alone touch the turf (their friction wins the
        # contact: priority).
        cx = g["rear_x"] + L / 2
        b = sc.body("sled", (cx, 0.0, 0.0), free=True)
        rw, rh = 0.025, 0.02
        m_run = 0.30 * p["sled_empty_kg"] / 2
        for s, tag in ((1, "L"), (-1, "R")):
            y = s * (W / 2 - rw)
            sc.geom(b, f"sled_runner{tag}", type="box", pos=(0, y, rh), size=(L / 2, rw, rh), mass=m_run, rgba=STEEL,
                    friction=(p["runner_mu"], 0.005, 0.0001), priority=2, condim=3, **HITTABLE)
            # the upright handle at the rear corner, from the runner up to the pole's top
            ph = p["pole_height_m"]
            sc.geom(b, f"sled_pole{tag}", type="cylinder",
                    pos=(-L / 2 + p["pole_diameter_m"] / 2, y, (ph + 2 * rh) / 2),
                    size=(p["pole_diameter_m"] / 2, (ph - 2 * rh) / 2), mass=0.12 * p["sled_empty_kg"] / 2, rgba=STEEL,
                    friction=(0.8, 0.005, 0.0001), **HITTABLE, **RIGID)
        m_frame = p["sled_empty_kg"] - 2 * m_run - 0.12 * p["sled_empty_kg"]
        sc.geom(b, "sled_deck", type="box", pos=(0.05, 0, 0.09), size=(L / 2 - 0.12, W / 2 - 0.06, 0.02),
                mass=m_frame * 0.8, rgba=STEEL, **HITTABLE, **RIGID)
        sc.geom(b, "sled_post", type="cylinder", pos=(0.05, 0, 0.30), size=(0.025, 0.19), mass=m_frame * 0.2,
                rgba=STEEL, **HITTABLE, **RIGID)
        if p["plates_kg"] > 0:                       # 0.45 m (20 kg Olympic) plates stacked on the post
            n = max(1, int(math.ceil(p["plates_kg"] / 20.0)))
            for i in range(n):
                sc.geom(b, f"sled_plate{i}", type="cylinder", pos=(0.05, 0, 0.13 + 0.03 * i), size=(0.225, 0.015),
                        mass=p["plates_kg"] / n, rgba=PLATE, **HITTABLE, **RIGID)
        sc.camera("venue", (-2.5, -4.5, 2.4), (3.5, 0.0, 0.6), fovy=55)

    def reset(self, w):
        g = self.geometry()
        w.put("sled", (g["rear_x"] + self.p["sled_length_m"] / 2, 0.0, 0.0))

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        self.sled = ref.geoms(body="sled")
        self.poles = ref.geoms(names=["sled_poleL", "sled_poleR"])
        self.hands = ref.part("hands")
        self.not_hands = ref.part("robot") & ~self.hands
        m = w.m
        self.sled_geoms = [g for g in range(m.ngeom) if self.sled[g]]
        self.trackers = {"t_line": None}

    def _sled_span(self, w):
        """The sled's extent along x and y (its collision geoms' bounding boxes in the world)."""
        m, d = w.m, w.d
        lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
        for g in self.sled_geoms:
            R = d.geom_xmat[g].reshape(3, 3)
            c = d.geom_xpos[g] + R @ m.geom_aabb[g, :3]
            h = np.abs(R) @ m.geom_aabb[g, 3:]
            lo, hi = np.minimum(lo, c - h), np.maximum(hi, c + h)
        return lo, hi

    def substep(self, w, ref):
        if ref.touching(self.sled, self.not_hands):
            return ref.fail("the sled was touched by a part other than a hand",
                            parts=sorted(ref.parts_touching(self.sled) - {"left_hand", "right_hand"}))
        if ref.touching(self.sled & ~self.poles, self.hands):
            return ref.fail("a hand touched the sled elsewhere than on a handle")

    def step(self, w, ref):
        p, g = self.p, self.geometry()
        lo, hi = self._sled_span(w)
        ref.metrics["sled_rear_x_m"] = round(float(lo[0]), 3)
        ref.metrics["sled_distance_m"] = round(float(lo[0] - g["rear_x"]), 3)
        if lo[1] < -p["lane_half_m"] or hi[1] > p["lane_half_m"]:
            return ref.fail("the sled left the lane")
        if not ref.has("moved") and lo[0] >= g["rear_x"] + p["move_m"]:
            ref.stage("moved")
        if lo[0] >= g["line_x"]:
            if ref.stage("line"):
                ref.succeed()

    def privileged(self, w):
        lo, hi = self._sled_span(w)
        return {"sled": w.pos("sled").tolist(), "sled_velocity": w.vel("sled").tolist(),
                "sled_box": [lo.tolist(), hi.tolist()], "finish_line_x": self.geometry()["line_x"],
                "poles": [w.d.geom_xpos[w.m.geom(n).id].tolist() for n in ("sled_poleL", "sled_poleR")]}
