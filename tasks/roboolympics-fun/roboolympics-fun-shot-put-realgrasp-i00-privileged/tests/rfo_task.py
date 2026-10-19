"""Shot put with a real hold (World Athletics TR 32 and 33): the shot-put family's circle, stop board, sector, shot,
robot and rules, but nothing grips: the men's shot rests on the open right palm against the neck, held by contact and
friction only, and is put from the shoulder with that hand so that it lands inside the sector at least the qualifying
mark away; then leave the circle from its rear half. The Unitree H1-2."""
import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from rfo.scene import HITTABLE, OFFICIAL, STANDABLE
from rfo.task import TaskBase

SHOT = OFFICIAL["shot"]                       # TR 33: 7.260 kg, 110-130 mm (120 mm here)
APRON, RAMP = 1.0, 1.0                        # the ground outside the circle: level for APRON m, then down to the field
N_WEDGE = 48
# ---- the hold at the start ----
# No grip: the shot (120 mm, larger than any gripper's stroke) rests on the open right palm (the pad's broad face, the
# mount's +x) beside the neck, pressed against the trunk's hull there (the H1-2's trunk and head are one hull), the
# palm facing up, in and a little back (about 37 degrees from vertical, towards the neck): the palm carries most of its
# weight, the neck the rest, friction both. The H1-2's arm servos are soft (40 N m/rad at the shoulder, 18 at the
# elbow) and have no gravity feed-forward, so the start command (HOLD) differs from where the arm stands: under the
# shot's weight the arm settles at SETTLED, where the robot starts, at rest, the shot where it then rests (SHOT_AT: from
# the centre of the pad's face plus the shot's radius along its normal, mount frame). Found by a CMA-ES search in
# physics over the arm's angles, its targets and where the shot touches the neck, every angle and target inside the
# joints' ranges (a target outside them would make every plan be refused), then settled for 8 s: under the start
# command the shot moves 4 mm relative to the hand and then rests, and the robot stands.
SETTLED = dict(shoulder_pitch=-0.6816, shoulder_roll=0.1604, shoulder_yaw=0.2654, elbow_pitch=-0.8991,
               elbow_roll=-0.8855, wrist_pitch=-0.4440, wrist_yaw=-1.1934)
HOLD = dict(shoulder_pitch=-0.7315, shoulder_roll=0.1587, shoulder_yaw=0.3103, elbow_pitch=-0.8292,
            elbow_roll=-1.0113, wrist_pitch=-0.4500, wrist_yaw=-0.8479)
SHOT_AT = (-0.0001, 0.0084, -0.0293)
PAD_HALF, PAD_Z = 0.022, 0.05                  # the palm pad's half thickness and its centre along the forearm
PALM_SOLREF, PALM_SOLIMP, PALM_MU, PALM_REBOUND = "0.005 1", "0.99 0.999 0.001", 0.7, 0.12
CONE, IMPRATIO = "elliptic", 100.0
# ---- end of the hold ----


def shot_on_palm(w, radius: float) -> None:
    """t = 0: the right arm settled in the stance (SETTLED), its targets (the start command) HOLD; the shot where it
    then rests: on the palm pad's face, SHOT_AT (mount frame) from the face's centre plus its radius along the
    normal."""
    r, d = w.robot, w.d
    for jn, v in SETTLED.items():
        i = w.L.JOINTS.index(f"right_{jn}_joint")
        d.qpos[r.qadr[i]] = v
        r.arb.q_a[i] = r.arb.q_b[i] = HOLD[jn]
    mujoco.mj_kinematics(w.m, d)
    b = r.mount["right"]
    R = d.xmat[b].reshape(3, 3)
    w.put("shot", d.xpos[b] + R @ (np.array([PAD_HALF + radius, 0.0, PAD_Z]) + np.array(SHOT_AT)))


def build_circle(sc, R: float, rim_h: float, half_sector: float, mark: float, far: float) -> list[str]:
    """A throwing circle of inner radius R round the origin, its inside the floor: the ground outside is rim_h higher
    (TR 32.6), built as N_WEDGE convex wedges that are level for APRON m and then fall to the field over RAMP m; the
    white rim, the two 0.75 m lines through the centre, the sector lines (from the centre, 50 mm, outside the sector)
    and the qualifying mark. Returns the wedges' names (they are ground)."""
    asset = sc.root.find("asset")
    sc.disc("circle", (0.0, 0.0), R, rgba=(0.62, 0.62, 0.60, 1))
    names = []
    da = 2 * math.pi / N_WEDGE
    k = 1.0 / math.cos(da / 2)                               # the polygon lies outside the circle and touches it
    for i in range(N_WEDGE):
        a0, a1 = i * da, (i + 1) * da
        v = []
        for a in (a0, a1):
            c, s = math.cos(a), math.sin(a)
            for r, z in ((R * k, 0.0), (R * k, rim_h), ((R + APRON) * k, rim_h), ((R + APRON + RAMP) * k, 0.0)):
                v += [r * c, r * s, z]
        ET_mesh = asset.makeelement("mesh", dict(name=f"apron{i}", vertex=" ".join(f"{x:.6g}" for x in v)))
        asset.append(ET_mesh)
        sc.geom(sc.wb, f"apron{i}", type="mesh", mesh=f"apron{i}", rgba=(0.24, 0.50, 0.26, 1),
                friction=(1.0, 0.005, 0.0001), **STANDABLE)
        names.append(f"apron{i}")
        sc.line(f"rim{i}", ((R + 0.003) * math.cos(a0), (R + 0.003) * math.sin(a0)),
                ((R + 0.003) * math.cos(a1), (R + 0.003) * math.sin(a1)), width=0.006, z=rim_h + 0.0008)
    for s, tag in ((1, "L"), (-1, "R")):                     # TR 32.7: 50 mm lines, their rear edge through the centre
        sc.line(f"centre_line{tag}", (0.025, s * R), (0.025, s * (R + 0.75)), width=0.05, z=rim_h + 0.0008)
        a = s * half_sector
        n = (-math.sin(a) * s * 0.025, math.cos(a) * s * 0.025)
        r0 = R + APRON + RAMP
        sc.line(f"sector_line{tag}", (r0 * math.cos(a) + n[0], r0 * math.sin(a) + n[1]),
                (far * math.cos(a) + n[0], far * math.sin(a) + n[1]), width=0.05, z=0.0012)
    m = 12
    for i in range(m):
        a0, a1 = -half_sector + 2 * half_sector * i / m, -half_sector + 2 * half_sector * (i + 1) / m
        sc.line(f"mark{i}", ((R + mark) * math.cos(a0), (R + mark) * math.sin(a0)),
                ((R + mark) * math.cos(a1), (R + mark) * math.sin(a1)), width=0.05, rgba=(0.95, 0.85, 0.2, 1))
    return names


class Task(TaskBase):
    name = "shot-put-realgrasp"
    title = "Athletics: shot put, real hold"
    category = "throwing-catching-striking"
    robot = "unitree_h1"
    rulebook = ("World Athletics Competition and Technical Rules 2024: TR 32.5-32.8 (the circle), TR 32.12 (the "
                "sector), TR 32.13, 32.14, 32.16, 32.17 and 32.20 (throwing events: the start, failures, the landing, "
                "leaving the circle, the measurement), TR 33.1 (the put from the shoulder), TR 33.2 (the stop board), "
                "TR 33.4-33.5 (the men's shot)")
    deviations = [
        "TR 33.1 (\"the shot shall touch or be in close proximity to the neck or the chin\"; the hand that holds it): the "
        "H1-2's hand is a flat rubber palm pad without fingers and nothing grips: the shot rests on the open right "
        "palm, which faces up and in towards the neck, and leans against the neck (the trunk's hull: the H1-2's trunk "
        "and head are one hull), held only by the palm's support, the neck and friction; it rolls or slides off when "
        "the palm does not carry it. The stance is given at the start (the shot's centre within {neck_reach_m} m of "
        "the line from the base of the neck to the chin). From then to the release the rule is judged on the shot's "
        "centre in the trunk's frame: \"the hand shall not be dropped below this position\" as not lower than "
        "{drop_below_shoulders_m} m below the line of the two shoulder joints, \"not behind the line of the "
        "shoulders\" as not more than {behind_shoulders_m} m behind that line, and \"put\" (not thrown or slung) as: "
        "at the release (the right hand's last contact) the shot moves away from the putting shoulder's joint with at "
        "least {push_fraction} of its speed relative to that joint.",
        "The hand: the palm is modelled as the soft part of a hand: it absorbs the shot (a ball thrown at a still palm "
        f"keeps {PALM_REBOUND:.2f} of its speed; friction {PALM_MU:g}), the contact of the two-palm basketball "
        "families (dunk-realgrasp); the shot's contact with the rest of the robot, the ground and the stop board is "
        "its own (rebound " + f"{SHOT['bounce']:.2f}" + ").",
        "TR 32.5-32.6: the ground outside the circle is level with the rim's top for " + f"{APRON:g} m and then falls to "
        f"the field's level over {RAMP:g} m" + " (the circle's inside is the field's level, {rim_height_m} m below the "
        "rim, instead of the field being level with the rim).",
        "TR 32.20: the mark is the point where the shot first touches the ground, not the nearest edge of its dent.",
        "TR 32.15 (interrupting a trial, laying the implement down): not modelled; the first release is the put, and "
        "nothing of the robot may touch the shot again.",
        "TR 32.14 names no fall: here a fall ends the trial as a failure, as in every task of this benchmark; the "
        "trial ends when the robot has left the circle correctly and stands.",
        "TR 25.17 (one minute for a trial): the whole trial, leaving the circle included, has {time_limit_s} s.",
        "Flight: the shot's drag in still air (MuJoCo's ellipsoid fluid model, a quasi-steady model), no wind.",
        "The qualifying mark of {qualifying_mark_m} m is this benchmark's (a school standard for the 7.26 kg shot); "
        "the rule book only measures.",
    ]
    time_limit_s = 60.0
    start = (-0.45, 0.0, 0.0)
    stages = ["release", "landing", "exit"]
    fall_z = 0.50
    params = dict(shot_mass_kg=SHOT["mass"], shot_diameter_m=2 * SHOT["radius"], circle_diameter_m=2.135,
                  rim_height_m=0.02, rim_edge_m=0.003, stop_board_length_m=1.21, stop_board_width_m=0.112, stop_board_height_m=0.10,
                  sector_deg=34.92, qualifying_mark_m=6.0, neck_reach_m=0.22, neck_base_above_shoulders_m=0.08,
                  chin_above_shoulders_m=0.20, chin_forward_m=0.09, drop_below_shoulders_m=0.0,
                  behind_shoulders_m=0.0, push_fraction=0.5, release_gap_s=0.03, stand_s=1.0, fall_pelvis_m=0.50)

    sentence = ("Put the shot that rests on your open right palm at your neck, from the shoulder with that hand alone, "
                "so that it lands inside the sector at least {qualifying_mark_m} m from the circle, then leave the "
                "circle from its rear half and stand.")
    rules = ("The men's shot ({shot_mass_kg} kg, {shot_diameter_m} m across) starts resting on your open right palm "
             "beside your neck, leaning against the neck: you have taken your stance. Your hands have no fingers and "
             "no grip (the grip columns do nothing; nothing is grippable): only the palm's support, your neck and "
             "friction hold the shot, and it rolls or slides off when the palm does not carry it. The circle is "
             "{circle_diameter_m} m across inside its rim; the ground outside is {rim_height_m} m higher than its "
             "inside. At the front, a stop board {stop_board_length_m} m long, {stop_board_width_m} m wide and "
             "{stop_board_height_m} m high follows the rim. The sector opens from the circle's centre, {sector_deg} "
             "degrees wide, symmetric about the direction you face at the start. Holding: the shot touches your right "
             "hand (the palm pad and the wrist); breaks of that contact shorter than {release_gap_s} s are part of "
             "the hold. The release is the hand's last contact before a break of at least {release_gap_s} s; at that "
             "moment of the break's end the shot must touch no part of you (a shot that leaves the hand but still "
             "rests on your trunk is a failure). The put (TR 33.1), judged on the shot's centre relative to your trunk "
             "(the line through your two shoulder joints, your trunk's up and forward directions) from the start to "
             "the release: the centre never lower than {drop_below_shoulders_m} m below the line of the shoulders and "
             "never more than {behind_shoulders_m} m behind it; nothing but your right hand and your trunk touches "
             "the shot; and at the release the shot must be moving away from your right shoulder joint with at least "
             "{push_fraction} of its speed relative to that joint (a push from the shoulder, not a throw or a sling). "
             "There is one release: after it nothing of you may touch the shot. The shot's first touch of the ground "
             "must be inside the sector lines (on a line is out); the put is measured from that point to the inside "
             "of the rim along the line through the circle's centre. You succeed when a valid put measures at least "
             "{qualifying_mark_m} m and you have then left the circle correctly and stood for {stand_s} s. Leaving "
             "correctly: after the shot has landed, your first touch of the rim's top or of the ground outside the "
             "circle is behind the line through the circle's centre across the putting direction (the rear half). "
             "Standing: only your feet on the ground, the torso within about 20 degrees of upright, the pelvis slower "
             "than 0.35 m/s. You fail if any part of you touches the rim's top (its top inside edge included), the "
             "ground outside the circle or any part of the stop board other than its inner side (its top edge is "
             "not its inner side) before the shot has landed, or in the front half before you have left correctly; "
             "if the shot drops below or goes behind the line of the shoulders (falling off the palm included), is "
             "touched by anything but the right hand and the trunk, leaves the hand onto the trunk, or is not pushed "
             "at the release; if it lands outside the sector or short of {qualifying_mark_m} m; if any part of you "
             "touches it after the release; if you fall (your pelvis lower than {fall_pelvis_m} m above the circle's "
             "floor, or any part of you other than your feet on the ground); or after {time_limit_s} s. Where you "
             "touch the ground is judged on the points of contact; a contact within {rim_edge_m} m of the rim's top, "
             "or that far outside the stop board's inner side, counts as on the top. The neck line of the stance runs "
             "from {neck_base_above_shoulders_m} m above the middle of the shoulder line to the chin, "
             "{chin_above_shoulders_m} m above and {chin_forward_m} m in front of it; at the start the shot's centre "
             "is within {neck_reach_m} m of it.")
    venue = ("You stand in the rear half of the circle facing the sector (+x), your pelvis 0.45 m behind the circle's "
             "centre; the stop board is at the front of the circle, 1.5 m ahead of you. Your right arm is folded up "
             "in front of the right side of your chest, the open palm facing up, in towards the neck and a little "
             "back, the shot resting on it against the right side of the neck, just above and in front of the right "
             "shoulder. The start command is not where the arm stands (the joint table's start targets differ from "
             "its angles: the difference carries the shot's weight on the soft arm servos); held as it is, the shot "
             "stays and the robot stands (its pelvis drifts about 2 cm in the minute). Still air.")
    difficulty = ("The shot weighs 7.26 kg and rests on a flat palm without fingers: every move of the trunk or the arm "
                  "that tilts the palm or accelerates the hand sideways rolls it off, and the H1-2's arm motors (40 N m "
                  "at the shoulder, 18 N m at the elbow, soft servos) only just carry it, so the legs and the trunk have "
                  "to drive the put while the palm stays under and behind the shot, inside a circle two steps wide. "
                  "{qualifying_mark_m} m needs a release near 7 m/s at about 40 degrees.")

    def build(self, sc):
        p = self.p
        self.fall_z = p["fall_pelvis_m"]
        self.R = R = p["circle_diameter_m"] / 2
        self.half_sector = math.radians(p["sector_deg"]) / 2
        sc.root.find("option").append(sc.root.makeelement("flag", dict(multiccd="enable")))   # feet (hulls) on the apron
        sc.ground += build_circle(sc, R, p["rim_height_m"], self.half_sector, p["qualifying_mark_m"], 25.0)
        # TR 33.2: the stop board, an arc whose inner edge is the rim's inner edge; a body and a top plate
        half_arc = p["stop_board_length_m"] / 2 / R
        hw, hh, n = p["stop_board_width_m"] / 2, p["stop_board_height_m"], 16
        for i in range(n):
            a = -half_arc + (i + 0.5) * 2 * half_arc / n
            seg = (R + hw) * half_arc / n + 0.004
            for tag, z0, z1 in (("stop", 0.0, hh - 0.005), ("stop_top", hh - 0.005, hh)):
                sc.geom(sc.wb, f"{tag}{i}", type="box", pos=((R + hw) * math.cos(a), (R + hw) * math.sin(a), (z0 + z1) / 2),
                        size=(hw, seg, (z1 - z0) / 2), quat=(math.cos(a / 2), 0, 0, math.sin(a / 2)), rgba=(1, 1, 1, 1),
                        friction=(1.0, 0.005, 0.0001), **HITTABLE)
        sc.ball("shot", "shot", (0.3, -0.3, 1.5), mass=p["shot_mass_kg"], radius=p["shot_diameter_m"] / 2)
        opt = sc.root.find("option")                          # no grip: the shot is not grippable
        opt.set("cone", CONE)
        opt.set("impratio", f"{IMPRATIO:g}")
        for side in ("left", "right"):
            ET.SubElement(sc.root.find("contact"), "pair", name=f"palm_ball_{side}", geom1="shot",
                          geom2=f"{side}_palm_pad", condim="6",
                          friction=f"{PALM_MU} {PALM_MU} 0.003 {SHOT['roll']} {SHOT['roll']}", solref=PALM_SOLREF,
                          solimp=PALM_SOLIMP)
        sc.camera("venue", (-2.6, -3.4, 2.4), (1.2, 0.0, 0.8), fovy=55)
        sc.camera("sector", (-2.0, 0.0, 9.0), (4.5, 0.0, 0.0), fovy=70)

    def reset(self, w):
        shot_on_palm(w, self.p["shot_diameter_m"] / 2)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        m = w.m
        self.shot = ref.geoms(body="shot")
        self.robot = ref.part("robot")
        self.apron = ref.geoms(prefix="apron")
        self.floor = ref.geoms(names=["floor"])
        self.stop = ref.geoms(prefix="stop")
        self.sh = (m.body("right_shoulder_pitch_link").id, m.body("left_shoulder_pitch_link").id)
        self.joint = m.body("right_shoulder_roll_link").id       # the putting shoulder's joint
        self.shot_id = m.body("shot").id
        # last: the shot's state at the right hand's last contact (time, centre, velocity, the shoulder joint's velocity)
        vs = np.zeros(6)
        mujoco.mj_objectVelocity(m, w.d, mujoco.mjtObj.mjOBJ_BODY, self.joint, vs, 0)
        self.trackers = {"released": None, "landed": None, "exit": False,
                         "last": [0.0, *w.d.xpos[self.shot_id].tolist(), *w.vel("shot").tolist(), *vs[3:].tolist(),
                                  *w.d.xpos[self.joint].tolist()]}
        ref.metrics["stance_neck_distance_m"] = round(self.shot_in_trunk(w)[2], 3)

    def may_grip(self, w, side, name):
        return False                                          # no grip at all (nothing is grippable either)

    def shot_in_trunk(self, w):
        """The shot's centre in the trunk's frame: (height above the line of the shoulder joints, distance in front of
        it, distance from the neck line)."""
        d, p = w.d, self.p
        Rt = d.xmat[w.robot.torso].reshape(3, 3)
        mid = 0.5 * (d.xpos[self.sh[0]] + d.xpos[self.sh[1]])
        rel = (d.xpos[self.shot_id] - mid) @ Rt               # forward, left, up
        a = np.array([0.0, 0.0, p["neck_base_above_shoulders_m"]])
        b = np.array([p["chin_forward_m"], 0.0, p["chin_above_shoulders_m"]])
        t = float(np.clip((rel - a) @ (b - a) / ((b - a) @ (b - a)), 0.0, 1.0))
        return float(rel[2]), float(rel[0]), float(np.linalg.norm(rel - (a + t * (b - a))))

    def _marks(self, w, ref):
        """Where the robot touches now: (a foul touch?, outside the circle in the rear half?, ... in the front half?).
        Outside = the ground beyond the rim or the rim's top (its top inside edge included); a foul touch = the stop
        board other than its inner side."""
        p, R = self.p, self.R
        rear = front = foul = False
        pts = ref.contact_points(self.robot, self.apron)
        if len(pts):
            out = pts[pts[:, 2] >= p["rim_height_m"] - p["rim_edge_m"]]
            rear, front = bool((out[:, 0] < 0).any()), bool((out[:, 0] >= 0).any())
        pts = ref.contact_points(self.robot, self.floor)
        if len(pts):
            out = pts[np.hypot(pts[:, 0], pts[:, 1]) >= R]
            rear, front = rear or bool((out[:, 0] < 0).any()), front or bool((out[:, 0] >= 0).any())
        pts = ref.contact_points(self.robot, self.stop)
        if len(pts):
            foul = bool(((np.hypot(pts[:, 0], pts[:, 1]) > R + p["rim_edge_m"])
                         | (pts[:, 2] >= p["stop_board_height_m"] - 0.005 - 1e-4)).any())
        return foul, rear, front

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        foul, rear, front = self._marks(w, ref)
        if not tr["exit"]:
            if foul:
                return ref.fail("touched the stop board other than its inner side")
            if tr["landed"] is None and (rear or front):
                return ref.fail("touched the rim's top or the ground outside the circle before the shot had landed")
            if front:
                return ref.fail("left the circle from its front half")
            if rear and ref.has("landing"):
                tr["exit"] = True
                ref.stage("exit")
        if tr["landed"] is not None:
            return
        if tr["released"] is None:
            up, fwd, _ = self.shot_in_trunk(w)
            on = ref.parts_touching(self.shot)
            others = on - {"right_hand", "torso"}
            if up < -p["drop_below_shoulders_m"]:
                return ref.fail("the shot dropped below the line of the shoulders", below_m=round(-up, 3))
            if fwd < -p["behind_shoulders_m"]:
                return ref.fail("the shot went behind the line of the shoulders", behind_m=round(-fwd, 3))
            if others:
                return ref.fail("the shot was touched by something other than the putting hand", parts=sorted(others))
            if "right_hand" in on:                             # in the hand: remember its state at this contact
                vs = np.zeros(6)
                mujoco.mj_objectVelocity(w.m, w.d, mujoco.mjtObj.mjOBJ_BODY, self.joint, vs, 0)
                tr["last"] = [ref.time, *w.d.xpos[self.shot_id].tolist(), *w.vel("shot").tolist(),
                              *vs[3:].tolist(), *w.d.xpos[self.joint].tolist()]
                return
            if ref.time - tr["last"][0] < p["release_gap_s"] - 1e-9:
                return                                         # a short break of the contact: still in the hand
            if on:
                return ref.fail("the shot left the hand but not the body (it rests on the trunk)")
            last = np.asarray(tr["last"], float)                # the release: the hand's last contact
            tr["released"] = round(float(last[0]), 4)
            c, v, vj, pj = last[1:4], last[4:7], last[7:10], last[10:13]
            rel, arm = v - vj, c - pj
            speed = float(np.linalg.norm(rel))
            away = float(rel @ arm / max(float(np.linalg.norm(arm)), 1e-9))
            ref.metrics["release_time_s"] = tr["released"]
            ref.metrics["release_speed_m_s"] = round(float(np.linalg.norm(v)), 2)
            ref.metrics["release_height_m"] = round(float(c[2]), 3)
            ref.metrics["release_push_fraction"] = round(away / speed, 3) if speed > 1e-6 else 0.0
            if away < p["push_fraction"] * speed or speed <= 1e-6:
                return ref.fail("the shot was not put from the shoulder", push_fraction=round(away / max(speed, 1e-9), 3))
            ref.stage("release")
        elif ref.touching(self.shot, self.robot):
            return ref.fail("the shot was touched after the release", parts=sorted(ref.parts_touching(self.shot)))
        pts = ref.contact_points(self.shot, ref.ground)
        if not len(pts):
            return
        x, y = float(pts[0][0]), float(pts[0][1])                # the landing: the first touch of the ground
        dist = math.hypot(x, y) - self.R
        tr["landed"] = [round(x, 4), round(y, 4)]
        ref.metrics["distance_m"] = round(dist, 3)
        if dist <= 0 or abs(math.atan2(y, x)) >= self.half_sector:
            ref.fail("the shot landed outside the sector", x=round(x, 3), y=round(y, 3))
        elif dist < p["qualifying_mark_m"]:
            ref.fail("the put is short of the qualifying mark", distance_m=round(dist, 3))
        else:
            ref.stage("landing", distance_m=round(dist, 3))

    def step(self, w, ref):
        if ref.has("exit") and ref.hold("stand", ref.standing(), self.p["stand_s"]):
            ref.succeed()

    def privileged(self, w):
        up, fwd, neck = self.shot_in_trunk(w)
        tr = self.trackers
        return {"shot": w.pos("shot").tolist(), "shot_velocity": w.vel("shot").tolist(),
                "in_hand": tr["released"] is None and tr["last"] is not None and w.t - tr["last"][0] < 0.011,
                "shot_above_shoulder_line_m": up, "shot_in_front_of_shoulder_line_m": fwd, "shot_to_neck_line_m": neck,
                "circle_radius": self.R, "sector_half_angle_deg": math.degrees(self.half_sector)}
