"""Vault (FIG men's vault): from the run-up, over the 1.35 m vault table with the hands (only) on it, landing on the
feet on the mat, and stand."""
import math
import xml.etree.ElementTree as ET

from rfo.referee import Crossing
from rfo.scene import HITTABLE, STANDABLE, VISUAL
from rfo.task import TaskBase

HANDS = {"left_hand", "right_hand"}
FEET = {"left_foot", "right_foot"}


class Task(TaskBase):
    name = "vault"
    title = "Vault"
    category = "parkour-apparatus-balance"
    robot = "unitree_h1"
    rulebook = ("FIG Apparatus Norms (men's vault): the vault table 1.35 m high, its top 1.20 m long and 0.95 m wide; a "
                "run-up of 25 m, 1 m wide; a springboard 1.20 m by 0.60 m, 0.22 m high at its high end; landing mats "
                "6 m by 2.5 m, 0.20 m thick. FIG Code of Points for Men's Artistic Gymnastics, the vault section, for "
                "what makes a vault invalid: no support of a hand on the table, a foot on the table, not landing "
                "feet first")
    deviations = [
        "Apparatus Norms (springboard): the board is a rigid plate hinged at its low end on one spring of "
        "{board_stiffness_nm_rad} N m/rad (83 kN/m at its high end with the default) with light damping, "
        "not a leaf-spring board with coil springs; its elasticity is not FIG-tested (the norm is a drop test on "
        "the real board)",
        "Code of Points (springboard position): the board stands at a fixed place, its high end {board_gap_m} m "
        "before the table, instead of where the gymnast puts it (nobody sets up the venue for the robot)",
        "Code of Points (the vault): any passage over the table with hand support counts, with no vault number, no "
        "required take-off from the board and no execution score: the family asks whether the vault is valid, not "
        "how well it is done",
        "Code of Points (landing): judged to a stand of {stand_s} s on the mat with nothing but the feet on it; the "
        "landing mat's corridor lines are not judged",
        "Apparatus Norms (run-up): the robot starts at the far end of the {runup_m} m run-up (the gymnast may start "
        "nearer); the table's safety collar and the mat around the board are left out",
    ]
    time_limit_s = 80.0
    start = (0.0, 0.0, 0.0)
    stages = ["hands on the table", "over the table", "landing", "stand"]
    fall_rule = False                # hands may be on the floor before the table; the family's own rules judge the landing
    params = dict(table_height_m=1.35, table_length_m=1.20, table_width_m=0.95, runup_m=25.0, runup_width_m=1.0,
                  board_length_m=1.20, board_width_m=0.60, board_height_m=0.22, board_gap_m=0.50, board_mass_kg=20.0,
                  board_stiffness_nm_rad=120000.0, board_damping_nms_rad=300.0,
                  mat_length_m=6.0, mat_width_m=2.5, mat_thickness_m=0.20, mat_contact_s=0.04,
                  top_tol_m=0.02, stand_s=1.0, stand_tilt_deg=20.0, still_m_s=0.35)

    sentence = ("Vault over the vault table at the end of the run-up: go over it with only your hands touching it, land "
                "on your feet on the landing mat and stand.")
    rules = ("The vault table's top is {table_height_m} m above the floor, {table_length_m} m long (along +x, the way "
             "you face) and {table_width_m} m wide, on a pedestal; its near edge is {runup_m} m ahead of where your "
             "pelvis starts, centred on your line. A springboard stands before it: a board {board_length_m} m long "
             "and {board_width_m} m wide ({board_mass_kg} kg), hinged at its low near end and rising to "
             "{board_height_m} m at its high end, which is {board_gap_m} m before the table; it rests on a spring of "
             "{board_stiffness_nm_rad} N m/rad about the hinge (damping {board_damping_nms_rad} N m s/rad) and gives "
             "way under load down to the floor. The landing mat begins at the table's far edge: {mat_length_m} m "
             "long, {mat_width_m} m wide, {mat_thickness_m} m thick, softer than the floor (contact time constant "
             "{mat_contact_s} s). A valid vault, in order: at least one hand touches the table's top surface (a contact within "
             "{top_tol_m} m of the top plane; a hand against a side of the table does not count); your pelvis "
             "passes the table's far edge; your feet touch the mat; you stand on the mat for {stand_s} s without a "
             "break (only your feet on it, your torso within {stand_tilt_deg} degrees of vertical, your pelvis moving "
             "no faster than {still_m_s} m/s). You fail the moment: any part of you other than your hands (the wrist "
             "links and the palms; not the forearms) touches the table or its pedestal; your pelvis is between the table's near and "
             "far edges without being higher than its top and within its width (you went under, beside or round "
             "it); your pelvis passes the far edge before a hand has touched the top; after your pelvis has passed "
             "the far edge, any part of you touches the floor, or a part other than your feet touches the mat "
             "before the stand is complete. Before the table there is no fall rule: any part of you may touch the "
             "floor and the springboard, and using the springboard is not required. The attempt ends after "
             "{time_limit_s} s of robot time.")
    venue = ("You stand at the start of the run-up, a strip {runup_width_m} m wide that leads straight ahead (+x) to "
             "the springboard and the table; the board's low end is 23.3 m ahead of you and its high end 24.5 m. The "
             "table's top is higher than your shoulders' joints are when you stand (about 1.47 m is the height of "
             "your shoulders, 1.03 m that of your pelvis). Table, pedestal and mat are fixed; the board moves on its "
             "spring.")
    difficulty = ("The table is 1.35 m high and the robot has no running policy: its walk reaches about 0.65 m/s and "
                  "its best standing jump lifts it far less than a metre, so the 67 kg body has to be carried over "
                  "the table by a take-off and arm support that nobody has built for it. It must then come down "
                  "feet first from above 1.35 m and absorb the landing without a hand on the mat.")

    def build(self, sc):
        p = self.p
        H, TL, TW, R = p["table_height_m"], p["table_length_m"], p["table_width_m"], p["runup_m"]
        BL, BW, BH, gap = p["board_length_m"], p["board_width_m"], p["board_height_m"], p["board_gap_m"]
        ML, MW, MT = p["mat_length_m"], p["mat_width_m"], p["mat_thickness_m"]
        x0, x1 = R, R + TL
        self.geo = dict(table_x=(x0, x1), table_top=H, table_half_width=TW / 2, mat_x=(x1, x1 + ML),
                        mat_half_width=MW / 2, mat_top=MT, board_x=(x0 - gap - BL, x0 - gap))
        # The H1-2's sole is one convex hull: on a box (unlike the floor plane) MuJoCo gives a convex pair a single
        # contact point unless multiccd is on, and a foot on one point does not stand. Board and mat are boxes.
        ET.SubElement(sc.root.find("option"), "flag", multiccd="enable")
        sc.zone("runup", ((x0 - gap - BL) / 2, 0.0), ((x0 - gap - BL) / 2, p["runup_width_m"] / 2), rgba=(0.30, 0.42, 0.72, 1))
        # the table: a padded top on a pedestal
        tt = 0.25
        sc.box("table_top", ((x0 + x1) / 2, 0.0, H - tt / 2), (TL / 2, TW / 2, tt / 2), rgba=(0.80, 0.68, 0.45, 1),
               solid="hit", friction=(1.0, 0.005, 0.0001))
        sc.box("table_pedestal", ((x0 + x1) / 2, 0.0, (H - tt) / 2), (0.14, 0.14, (H - tt) / 2), rgba=(0.30, 0.30, 0.33, 1),
               solid="hit")
        sc.box("table_foot", ((x0 + x1) / 2, 0.0, 0.02), (0.45, 0.35, 0.02), rgba=(0.30, 0.30, 0.33, 1), solid="hit")
        # the springboard: a rigid plate hinged at its low near end, held up by a spring about the hinge
        th, z0 = 0.03, 0.025
        ang = math.asin((BH - z0 - th / 2) / BL)
        self.geo["board_angle_rad"] = ang
        b = sc.body("springboard", (x0 - gap - BL, 0.0, z0), quat=(math.cos(-ang / 2), 0.0, math.sin(-ang / 2), 0.0))
        ET.SubElement(b, "joint", name="springboard", type="hinge", axis="0 1 0", range=f"-0.05 {ang - 0.012:.5f}",
                      stiffness=f"{p['board_stiffness_nm_rad']:g}", damping=f"{p['board_damping_nms_rad']:g}",
                      springref="0", armature="0.01")
        sc.geom(b, "springboard", type="box", pos=(BL / 2, 0.0, 0.0), size=(BL / 2, BW / 2, th / 2),
                mass=p["board_mass_kg"], rgba=(0.75, 0.55, 0.30, 1), friction=(1.0, 0.005, 0.0001), **STANDABLE)
        ET.SubElement(sc.root.find("contact"), "exclude", body1="world", body2="springboard")
        sc.geom(sc.wb, "springboard_base", type="box", pos=(x0 - gap - BL / 2, 0.0, 0.004), size=(BL / 2, BW / 2, 0.004),
                rgba=(0.25, 0.25, 0.28, 1), **VISUAL)
        # the landing mat
        sc.geom(sc.wb, "mat", type="box", pos=(x1 + ML / 2, 0.0, MT / 2), size=(ML / 2, MW / 2, MT / 2),
                rgba=(0.20, 0.35, 0.65, 1), friction=(1.0, 0.005, 0.0001), solref=(p["mat_contact_s"], 1.0), **STANDABLE)
        sc.ground.append("mat")
        sc.camera("venue", (R / 2, -20.0, 7.0), (R / 2 + 2.0, 0.0, 0.5), fovy=70)          # the start to the mat
        sc.camera("table", (x0 - 1.5, -8.5, 3.0), (x0 + 1.2, 0.0, 0.9), fovy=55)

    def board_height(self, w) -> float:
        """The height of the board's high end (the top surface) above the floor, m."""
        q = float(w.d.qpos[w.m.joint("springboard").qposadr[0]])
        return 0.025 + self.p["board_length_m"] * math.sin(self.geo["board_angle_rad"] - q) + 0.015 * math.cos(
            self.geo["board_angle_rad"] - q)

    def referee_reset(self, w, ref):
        g = self.geo
        self.table_g = ref.geoms(prefix="table")
        self.top_g = ref.geoms(names=["table_top"])
        self.mat_g = ref.geoms(names=["mat"])
        self.floor = ref.geoms(names=["floor"])
        self.robot = ref.part("robot")
        self.hands = ref.part("hands")
        self.not_hands = self.robot & ~self.hands
        self.feet = ref.part("feet")
        self.not_feet = self.robot & ~self.feet
        self.trackers = {"far": Crossing((1.0, 0.0, 0.0), g["table_x"][1], direction=1)}

    def substep(self, w, ref):
        g, tr = self.geo, self.trackers
        if ref.has("stand"):
            return
        if ref.touching(self.not_hands, self.table_g):
            return ref.fail("touched the table with something other than the hands",
                            parts=sorted(ref.parts_touching(self.table_g) - HANDS))
        if not ref.has("hands on the table") and ref.touching(self.hands, self.top_g):
            pts = ref.contact_points(self.hands, self.top_g)      # on the top surface, not against a side of it
            if float(pts[:, 2].max()) >= g["table_top"] - self.p["top_tol_m"]:
                ref.stage("hands on the table", hands=sorted(ref.parts_touching(self.top_g)))
        px, py, pz = (float(v) for v in w.d.xpos[w.robot.pelvis])
        if g["table_x"][0] < px < g["table_x"][1] and not (pz > g["table_top"] and abs(py) <= g["table_half_width"]):
            return ref.fail("did not pass over the table", pelvis=[round(px, 3), round(py, 3), round(pz, 3)])
        x = tr["far"].update((px, py, pz))
        if x is not None and not ref.has("over the table"):
            if not ref.has("hands on the table"):
                return ref.fail("passed the table without a hand on it")
            ref.stage("over the table", pelvis_z=round(float(x[2]), 3))
        if ref.has("over the table"):
            if ref.touching(self.robot, self.floor):
                return ref.fail("landed off the mat", parts=sorted(ref.parts_touching(self.floor)))
            if ref.touching(self.not_feet, self.mat_g):
                return ref.fail("did not land on the feet", parts=sorted(ref.parts_touching(self.mat_g) - FEET))
            if ref.touching(self.feet, self.mat_g):
                ref.stage("landing")

    def step(self, w, ref):
        p = self.p
        if ref.failed or not ref.has("landing"):
            return
        ok = ref.standing(max_speed=p["still_m_s"], min_upright=math.cos(math.radians(p["stand_tilt_deg"])), on=self.mat_g)
        if ref.hold("stand", ok, p["stand_s"]):
            if ref.stage("stand"):
                ref.succeed()

    def privileged(self, w):
        return {"pelvis": w.pelvis().tolist(), **{k: (list(v) if isinstance(v, tuple) else v) for k, v in self.geo.items()},
                "board_high_end_z": self.board_height(w)}
