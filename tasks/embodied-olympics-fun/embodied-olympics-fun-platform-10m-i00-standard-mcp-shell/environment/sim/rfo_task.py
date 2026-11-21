"""10 m platform (World Aquatics diving): a forward dive straight (101A) from a standing take-off at the front end of
the 10 m platform, judged in the flight and at the entry into the water."""
import math

import numpy as np

from rfo.referee import Flights
from rfo.scene import HITTABLE
from rfo.task import TaskBase

SIDES = ("left", "right")
G1_TOE = 0.099                   # m: the front of the standing G1's sole spheres ahead of its pelvis (measured);
#                                  the end is 2 cm beyond: edge_ahead_m / tip_ahead_m = 0.119
DEG = math.pi / 180.0


# ---------------------------------------------------------------------- the dive judge (the same in springboard-3m)
class Body:
    """The diver's landmarks (joint centres, the head, the palms) and the shape measures the judges look at."""

    def __init__(self, w):
        m, r = w.m, w.robot
        j = lambda n: m.joint(n).id  # noqa: E731
        self.w = w
        self.hip = {s: j(f"{s}_hip_pitch_joint") for s in SIDES}
        self.knee = {s: j(f"{s}_knee_joint") for s in SIDES}
        self.ankle = {s: j(f"{s}_ankle_pitch_joint") for s in SIDES}
        self.shoulder = {s: j(f"{s}_shoulder_pitch_joint") for s in SIDES}
        self.ankle_q = {s: int(m.jnt_qposadr[self.ankle[s]]) for s in SIDES}
        self.head = r.head_site
        self.palm = dict(r.palm)

    def a(self, jid):
        return self.w.d.xanchor[jid]

    def line(self):
        """The body line: the unit vector from the ankles' midpoint to the shoulders' midpoint."""
        ank = (self.a(self.ankle["left"]) + self.a(self.ankle["right"])) / 2
        sh = (self.a(self.shoulder["left"]) + self.a(self.shoulder["right"])) / 2
        u = sh - ank
        return u / (np.linalg.norm(u) + 1e-12), ank, sh

    @staticmethod
    def _ang(p, a, b) -> float:
        u, v = a - p, b - p
        c = float(u @ v) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-12)
        return math.degrees(math.acos(max(-1.0, min(1.0, c))))

    def shape(self) -> dict:
        """hip: the smaller of the two angles between the trunk and a thigh (180 = straight); knee: the smaller angle
        between a thigh and its lower leg; feet: the distance between the ankles; toes: the smaller ankle plantar
        flexion (rad); hands: how far both palms are beyond the head's centre along the body line, how far apart, and
        the larger distance of a palm from the body line; tilt: the body line's angle to the vertical, head down
        (degrees); twist: the shoulders' axis against the venue's y axis (degrees)."""
        d = self.w.d
        u, ank, sh = self.line()
        hip = min(self._ang(self.a(self.hip[s]), self.a(self.shoulder[s]), self.a(self.knee[s])) for s in SIDES)
        knee = min(self._ang(self.a(self.knee[s]), self.a(self.hip[s]), self.a(self.ankle[s])) for s in SIDES)
        feet = float(np.linalg.norm(self.a(self.ankle["left"]) - self.a(self.ankle["right"])))
        toes = min(float(d.qpos[self.ankle_q[s]]) for s in SIDES)
        head = d.site_xpos[self.head]
        pl, pr = d.site_xpos[self.palm["left"]], d.site_xpos[self.palm["right"]]
        beyond = min(float((pl - head) @ u), float((pr - head) @ u))
        apart = float(np.linalg.norm(pl - pr))
        off = max(float(np.linalg.norm((p - ank) - float((p - ank) @ u) * u)) for p in (pl, pr))
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, -float(u[2])))))
        lat = self.a(self.shoulder["left"]) - self.a(self.shoulder["right"])
        lat = lat / (np.linalg.norm(lat) + 1e-12)
        twist = math.degrees(math.acos(max(-1.0, min(1.0, float(lat[1])))))
        return dict(hip=hip, knee=knee, feet=feet, toes=toes, beyond=beyond, apart=apart, off=off, tilt=tilt,
                    twist=twist)

    def somersault(self) -> float:
        """The body line's angle in the venue's x-z plane: 0 upright, +pi head down after a forward half turn."""
        u, _, _ = self.line()
        return math.atan2(float(u[0]), float(u[2]))


def lowest_part(w, ref, ids):
    """(the lowest point of the robot, the part it belongs to) over its collision geoms' bounding boxes."""
    m, d = w.m, w.d
    R = d.geom_xmat[ids].reshape(-1, 3, 3)
    c = d.geom_xpos[ids] + np.einsum("gij,gj->gi", R, m.geom_aabb[ids, :3])
    half = np.sum(np.abs(R[:, 2, :]) * m.geom_aabb[ids, 3:], axis=1)
    lo = c[:, 2] - half
    i = int(np.argmin(lo))
    return float(lo[i]), ref.part_names[int(ref.part_code[ids[i]])], float(np.max(c[:, 2] + half))


class Dive:
    """The referee of a standing forward dive (a Task mixin): the take-off, the flight's straight position, the
    head-first entry. The Task sets geo["front_x"] (the end of the board or platform the entry distance is measured
    from) and WORDS (the failure reasons naming its apparatus)."""

    def dive_reset(self, w, ref, surface, rails):
        """surface: the selector of what the robot stands on and must leave (with its railings); rails: the
        railings (no touch at all)."""
        self.body = Body(w)
        self.platform = surface | rails
        self.rails = rails
        self.sole = {s: ref.part(f"{s}_foot") for s in SIDES}
        ankles = ref.geoms(body="left_ankle_pitch_link") | ref.geoms(body="right_ankle_pitch_link")
        self.not_feet = ref.part("robot") & ~ankles          # the feet and the ankle housings above them may touch
        self.ids = ref._robot_col
        self.trackers = {"flights": Flights(ref, min_air=self.p["min_air_s"]), "phase": "stand",
                         "com0": round(float(w.com()[2]), 6), "com_max": None, "t_off": None, "last_on": [0.0, 0.0],
                         "turn": 0.0, "prev": 0.0, "entry": None, "worst": {}, "settled": False, "hips": None}

    def _fail_shape(self, ref, sh, where) -> bool:
        p = self.p
        bad = None
        if 180.0 - sh["hip"] > p["straight_tol_deg"]:
            bad = ("bent at the hips", round(180.0 - sh["hip"], 1))
        elif 180.0 - sh["knee"] > p["straight_tol_deg"]:
            bad = ("bent at the knees", round(180.0 - sh["knee"], 1))
        elif sh["feet"] > p["feet_apart_m"]:
            bad = ("feet apart", round(sh["feet"], 3))
        elif sh["toes"] < p["toe_point_rad"]:
            bad = ("toes not pointed", round(sh["toes"], 3))
        if bad:
            ref.fail(f"not straight {where}: {bad[0]}", value=bad[1])
            return True
        return False

    def _worst(self, sh):
        """The entry's worst values (reported as metrics at the end)."""
        wv = self.trackers["worst"]
        for k, f in (("hip", min), ("knee", min), ("feet", max), ("toes", min), ("beyond", min), ("apart", max),
                     ("off", max), ("twist", max)):
            v = round(sh[k], 4)
            wv[k] = v if k not in wv else f(wv[k], v)

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        fl = tr["flights"]
        com_z = float(w.com()[2])
        a = self.body.somersault()                     # the turn, unwrapped
        da = (a - tr["prev"] + math.pi) % (2 * math.pi) - math.pi
        tr["prev"], tr["turn"] = a, tr["turn"] + da
        if tr["phase"] == "stand":
            on = [ref.touching(self.sole[s], self.platform) for s in SIDES]
            if not tr["settled"]:                      # the robot is placed a few mm above the top: it settles first
                if not all(on):
                    return
                tr["settled"] = True
                fl.reset()
            if ref.touching(self.not_feet, self.platform) or ref.touching(ref.robot_mask, self.rails):
                return ref.fail("fell (a part above the ankles on the surface) or touched the railings before the "
                                "take-off",
                                parts=sorted(ref.parts_touching(self.platform)))
            for i in range(2):
                if on[i]:
                    tr["last_on"][i] = ref.time
            for i in range(2):
                if on[i] and not on[1 - i] and ref.time - tr["last_on"][1 - i] > p["two_foot_window_s"]:
                    return ref.fail(self.WORDS["early_foot"], foot=SIDES[1 - i])
            done = fl.update()
            if done is not None:
                return ref.fail(self.WORDS["double"],
                                air_s=done["air_s"])
            if fl.air and ref.time - fl.cur["t0"] >= p["min_air_s"]:
                tr["phase"], tr["t_off"], tr["com_max"] = "air", round(fl.cur["t0"], 4), com_z
                ref.event("take-off: in the air")
            return
        if tr["phase"] in ("air", "entry") and ref.touching(ref.robot_mask, self.platform):
            parts = sorted(ref.parts_touching(self.platform))
            if set(parts) <= {"left_foot", "right_foot"} and float(w.pelvis()[2]) > self.geo["top"]:
                return ref.fail(self.WORDS["double"], parts=parts)       # back on its feet on top: a second jump
            return ref.fail(self.WORDS["touch"], parts=parts)
        tr["com_max"] = max(tr["com_max"], com_z)
        if not ref.has("take-off") and tr["com_max"] - tr["com0"] >= p["takeoff_rise_m"]:
            ref.stage("take-off", rise_m=round(tr["com_max"] - tr["com0"], 3))
        low, part, high = lowest_part(w, ref, self.ids)
        sh = None
        if tr["turn"] >= math.pi / 2:                  # the last quarter somersault: the straight position
            sh = self.body.shape()
            if self._fail_shape(ref, sh, "in the flight (D 8.5.5)"):
                return
        if tr["phase"] == "air":
            if low > 0.0:
                return
            if not ref.has("take-off"):
                return ref.fail("no take-off: the centre of mass never rose (D 8.4.4), a fall is not a dive",
                                rise_m=round(tr["com_max"] - tr["com0"], 3))
            turn = math.degrees(tr["turn"])
            ref.metrics["somersault_deg"] = round(turn, 1)
            if abs(turn - p["somersault_deg"]) > p["somersault_tol_deg"]:
                return ref.fail("not a forward half somersault (D 1.5)", somersault_deg=round(turn, 1))
            if part not in ("left_hand", "right_hand", "head"):
                return ref.fail("not head first: the hands or the head must enter first (D 6.5.8.1)", first=part)
            xy = self.first_point(w, ref)
            dist = xy[0] - self.geo["front_x"]
            ref.metrics["entry_distance_m"] = round(dist, 3)
            if dist < p["entry_near_m"]:
                return ref.fail(self.WORDS["near"], distance_m=round(dist, 3))
            if dist > p["entry_far_m"]:
                return ref.fail(self.WORDS["far"],
                                distance_m=round(dist, 3))
            if abs(xy[1] - self.start[1]) > p["line_tol_m"]:
                return ref.fail("dived to the side of the line of flight (D 8.5.1)", y=round(xy[1], 3))
            tr["phase"], tr["entry"] = "entry", round(ref.time, 4)
            ref.stage("entry", first=part)
        if tr["phase"] == "entry":
            sh = sh or self.body.shape()
            self._worst(sh)
            if tr.get("hips") is None and float(w.pelvis()[2]) <= 0.0:    # the hips pass the surface: the angle
                tr["hips"] = round(sh["tilt"], 2)
                ref.metrics["entry_tilt_deg"] = round(sh["tilt"], 1)
                if sh["tilt"] > p["entry_tilt_deg"]:
                    return ref.fail("the entry is not vertical (D 8.6.1)", tilt_deg=round(sh["tilt"], 1))
            if sh["twist"] > p["twist_tol_deg"]:
                return ref.fail("the entry is twisted (D 8.6.1)", twist_deg=round(sh["twist"], 1))
            if self._fail_shape(ref, sh, "at the entry (D 8.6.1)"):
                return
            if sh["beyond"] < p["hands_beyond_m"] or sh["apart"] > p["hands_apart_m"] or sh["off"] > p["hands_line_m"]:
                return ref.fail("the arms are not stretched beyond the head, in line, hands together (D 8.6.3)",
                                beyond_m=round(sh["beyond"], 3), apart_m=round(sh["apart"], 3),
                                off_line_m=round(sh["off"], 3))
            if high < 0.0:                             # the whole body under the surface: the dive is complete
                tr["phase"] = "done"
                for k, v in tr["worst"].items():
                    ref.metrics[f"entry_{k}"] = v
                if ref.stage("under water"):
                    ref.succeed()

    def first_point(self, w, ref):
        """Where the entry is: the middle of the palms (x, y) at the first touch of the surface."""
        r = w.robot
        return [float(v) for v in (w.d.site_xpos[r.palm["left"]][:2] + w.d.site_xpos[r.palm["right"]][:2]) / 2]



class Task(Dive, TaskBase):
    name = "platform-10m"
    title = "10 m platform: forward dive straight (101A)"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("World Aquatics (FINA) Diving Rules 2022-2025 (in force 3 December 2022): D 1.5 (dive numbers: 101 = "
                "front group, no flying action, one half somersault; A = straight), D 6.5.4 (a double jump on the "
                "platform is a failed dive), D 6.5.7 (a twist of 90 degrees or more at the entry: failed), D 6.5.8 / "
                "6.5.8.1 (head first: arms below the head, maximum 4.5 points; the feet entering before the head or "
                "hands: failed), D 8.1.1 (awards 0 to 10), D 8.2.4 (standing dives: the starting position on the "
                "front end, the feet stay on the platform until the take-off), D 8.4.4 (the take-off bold, balanced "
                "and high, from the end of the platform), D 8.5.1-8.5.5 (the direct line of flight; touching the "
                "platform; unsafely close: at most 2 points; straight: not bent at the knees or hips, feet together, "
                "toes pointed), D 8.6.1-8.6.3 and 8.6.7 (the entry vertical, not twisted, the body straight, feet "
                "together, toes pointed; head first with the arms stretched beyond the head in line with the body, "
                "the hands close together; the dive is complete when the whole body is under the surface). World "
                "Aquatics Facilities Rules FR 5.2 (the 10 m platform at least 6.0 m long and 3.0 m wide, rigid and "
                "horizontal, a 0.2 m front edge, projecting at least 1.50 m beyond the pool edge, handrails at the "
                "back and the sides up to 1 m from the front edge)")
    deviations = [
        "D 8.1.1 (the judges' award): the panel's 0-10 award is replaced by pass/fail lines that stand for a dive "
        "with no failed-dive call and no capped award: the entry within {entry_tilt_deg} degrees of vertical, hips "
        "and knees bent less than {straight_tol_deg} degrees, the ankles at most {feet_apart_m} m apart, the toes "
        "pointed (each ankle extended at least {toe_point_rad} rad of the robot's 0.52), both palms at least "
        "{hands_beyond_m} m beyond the head along the body line, at most {hands_apart_m} m apart and within "
        "{hands_line_m} m of the body line, a twist under {twist_tol_deg} degrees; the rule book gives the qualities, "
        "not these numbers",
        "D 8.6 and D 8.1.2 (the entry): the water is not simulated. The pool's surface is a plane the robot passes "
        "through without resistance; the entry is judged from the first touch of the surface until the whole body is "
        "under it (D 8.6.7), and nothing after that is judged (D 8.1.2: no movement beneath the surface counts). With "
        "no water the body keeps turning through the entry (the water stops a diver's rotation), so the entry's "
        "angle is "
        "taken at one moment, when the hips (the pelvis) reach the surface; the shape is judged through the whole "
        "passage",
        "D 8.4.4 (a high take-off): a take-off counts once the robot's centre of mass rises at least "
        "{takeoff_rise_m} m above its height at the start, so that a fall forward is not a dive",
        "D 8.5.5 (the straight position): judged from the moment the body line passes the horizontal until the "
        "entry (the last quarter somersault; D 8.5.7's quarter somersault for flying dives), with the entry's limits",
        "D 8.5.3 / 8.5.4 / 8.4.4 (touching the platform; unsafely close; a take-off from the end): any touch of the "
        "platform or its railings after the take-off fails, and the distance is judged at the water surface: the "
        "entry point (the middle of the palms at the first touch of the water) between {entry_near_m} m and "
        "{entry_far_m} m in front of the platform's front edge (the rule book leaves 'unsafely close' and 'from the "
        "end' to the judges)",
        "D 8.5.1 (the direct line of flight): the entry point must be within {line_tol_m} m to either side of the "
        "line the robot faces at the start",
        "D 8.2.4.2 / 6.5.4 (the feet stay on the platform; no double jump): a flight of {min_air_s} s or more that "
        "lands on the platform again fails, and neither foot may be off the platform for more than "
        "{two_foot_window_s} s while the other is on it (a step, a crow-hop)",
        "D 8.2.1 (the starting position): the robot is placed at the front end at t = 0 instead of walking there; "
        "it stands as its rest pose stands (the arms in front), not straight with the head erect",
        "D 1.5 (the dive): the half somersault is checked as the body line's turn in the vertical plane from the "
        "start to the entry, {somersault_deg} degrees within {somersault_tol_deg}",
        "FR 5.3.1 (the pool): the pool's water is a drawn surface over a floor that nothing collides with; the "
        "pool's depth and the other boards are not built",
    ]
    time_limit_s = 20.0
    start = (0.0, 0.0, 0.0)
    stages = ["take-off", "entry", "under water"]
    fall_rule = False                # the robot leaves the platform on purpose; the family's own rules judge it
    params = dict(platform_height_m=10.0, platform_length_m=6.0, platform_width_m=3.0, front_edge_m=0.2,
                  projection_m=1.5, rail_height_m=1.0, rail_free_m=1.0, edge_ahead_m=0.119,
                  takeoff_rise_m=0.10, min_air_s=0.03, two_foot_window_s=0.10,
                  entry_tilt_deg=15.0, straight_tol_deg=20.0, feet_apart_m=0.12, toe_point_rad=0.30,
                  hands_beyond_m=0.15, hands_apart_m=0.20, hands_line_m=0.15, twist_tol_deg=20.0,
                  somersault_deg=180.0, somersault_tol_deg=45.0, entry_near_m=0.5, entry_far_m=3.0, line_tol_m=0.5,
                  platform_friction=1.0)

    sentence = ("Do a forward dive straight (101A) from the 10 m platform: from your standing start at its front "
                "end, take off, turn half a somersault forwards in the straight position and enter the water head "
                "first, vertical, with your arms stretched beyond your head.")
    rules = ("You stand on the 10 m platform's front end facing the water (+x). The dive: take off from the "
             "platform (both feet stay on it until the take-off: a foot off it for more than {two_foot_window_s} s "
             "while the other is on it, or any flight of {min_air_s} s or more that lands on the platform again, "
             "fails; the take-off counts when you are in the air and your centre of mass has risen at least "
             "{takeoff_rise_m} m above its height at the start), turn forwards through half a somersault "
             "({somersault_deg} degrees, within {somersault_tol_deg}, counted from your upright start) and enter the "
             "water head first. From the "
             "moment your body line (from the middle of your ankles to the middle of your shoulders) passes the "
             "horizontal until the dive is complete you must be in the straight position: hips and knees each bent "
             "less than {straight_tol_deg} degrees from straight, the ankles at most {feet_apart_m} m apart, the toes "
             "pointed (each ankle pitched at least {toe_point_rad} rad towards the toes). The entry starts when the "
             "first part of you reaches the water surface (z = 0) and the dive is complete when the whole of you is "
             "under it; that first part must be a hand or the head (feet first fails); when your pelvis reaches the "
             "surface your body line must be within {entry_tilt_deg} degrees of vertical, head down; through the "
             "entry: not twisted (your shoulders' axis "
             "within {twist_tol_deg} degrees of the platform's width direction); both palms at least "
             "{hands_beyond_m} m beyond the centre of your head along the body line, at most {hands_apart_m} m "
             "apart and each within {hands_line_m} m of the body line; and the straight position. The entry point (the "
             "middle of your palms when the first part of you touches the water) must be between {entry_near_m} m "
             "and {entry_far_m} m in front of the platform's front edge (closer is unsafely close) and within "
             "{line_tol_m} m to either side of the line you face at the start. You fail if, after the take-off, any "
             "part of you touches the platform or its railings. Before the take-off any part other than the feet on "
             "the platform, or anything on the "
             "railings, fails. The water is not simulated: nothing after the dive is complete is judged. Success: a "
             "complete dive that keeps all of these. The attempt ends after {time_limit_s} s.")
    venue = ("The platform's top is {platform_height_m} m above the water, {platform_length_m} m long and "
             "{platform_width_m} m wide; its front edge (a {front_edge_m} m thick slab) is {edge_ahead_m} m ahead of "
             "your pelvis, about 2 cm ahead of your toes, square across your path, and you stand on its centre line. "
             "It projects {projection_m} m beyond the pool's edge; the water lies ahead and below. Handrails "
             "{rail_height_m} m high run along both sides of the platform and across its back, the side rails "
             "ending {rail_free_m} m before the front edge. The platform is rigid; nothing in the venue moves.")
    difficulty = ("A dive needs a take-off that is high enough and gives exactly the "
                  "right forward rotation, then a straight body with the legs drawn together, the toes pointed and "
                  "the short arms stretched overhead through a 1.4 s fall. A small error at the take-off becomes a "
                  "short or over-rotated entry, and nothing can be corrected once it is in the air.")

    # ------------------------------------------------------------------ the venue
    def build(self, sc):
        p = self.p
        H, L, W, T = p["platform_height_m"], p["platform_length_m"], p["platform_width_m"], p["front_edge_m"]
        xf = p["edge_ahead_m"]
        xp = xf - p["projection_m"]                    # the pool's edge
        self.geo = dict(front_x=xf, top=H, half_width=W / 2, pool_edge_x=xp)
        floor = next(g for g in sc.wb.findall("geom") if g.get("name") == "floor")
        floor.set("contype", "0")                      # the water is not simulated: nothing collides at z = 0
        floor.set("conaffinity", "0")
        # the platform: a rigid slab with its front edge square across +x; the tower behind the pool's edge
        sc.box("platform", (xf - L / 2, 0.0, H - T / 2), (L / 2, W / 2, T / 2), rgba=(0.62, 0.30, 0.22, 1),
               solid="stand", friction=(p["platform_friction"], 0.005, 0.0001))
        sc.box("tower", (xp - 2.5, 0.0, (H - T) / 2), (2.5, W / 2, (H - T) / 2), rgba=(0.72, 0.72, 0.70, 1),
               solid="stand")
        # handrails (FR 5.2.8): two bars on posts along both sides, ending rail_free_m before the front edge, and
        # across the back
        rh, x0, x1 = p["rail_height_m"], xf - L, xf - p["rail_free_m"]
        grey = (0.80, 0.80, 0.82, 1)
        for s, tag in ((1, "L"), (-1, "R")):
            y = s * (W / 2 - 0.03)
            for zz, k in ((rh, "top"), (rh / 2, "mid")):
                sc.geom(sc.wb, f"rail_{tag}_{k}", type="capsule", fromto=(x0, y, H + zz, x1, y, H + zz), size=(0.02,),
                        rgba=grey, **HITTABLE)
            for i, x in enumerate(np.linspace(x0, x1, 4)):
                sc.geom(sc.wb, f"rail_{tag}_post{i}", type="capsule", fromto=(x, y, H, x, y, H + rh), size=(0.02,),
                        rgba=grey, **HITTABLE)
        for zz, k in ((rh, "top"), (rh / 2, "mid")):
            sc.geom(sc.wb, f"rail_B_{k}", type="capsule", fromto=(x0 + 0.03, -W / 2, H + zz, x0 + 0.03, W / 2, H + zz),
                    size=(0.02,), rgba=grey, **HITTABLE)
        # the pool: water ahead of the pool's edge (drawn only), a deck behind it
        sc.geom(sc.wb, "water", type="box", pos=(xp + 12.5, 0.0, 0.001), size=(12.5, 12.0, 0.001),
                rgba=(0.16, 0.45, 0.70, 1), contype="0", conaffinity="0")
        sc.geom(sc.wb, "deck", type="box", pos=(xp - 6.0, 0.0, 0.002), size=(6.0, 12.0, 0.002),
                rgba=(0.85, 0.85, 0.82, 1), contype="0", conaffinity="0")
        sc.camera("venue", (xf + 1.5, -8.5, 5.4), (xf + 1.2, 0.0, 5.2), fovy=78)
        sc.camera("platform", (xf + 2.5, -3.5, H + 0.8), (xf - 0.3, 0.0, H + 0.4), fovy=55)

    def reset(self, w):
        r, d = w.robot, w.d
        d.qpos[r.fq + 2] = self.p["platform_height_m"] + r.stand_z     # the robot stands on the platform's top

    WORDS = {"early_foot": "a foot left the platform before the take-off (D 8.2.4.2)",
             "double": "a double jump: landed on the platform again before the dive (D 6.5.4)",
             "touch": "touched the platform or its railings during the dive (D 8.5.3)",
             "near": "the entry is unsafely close to the platform (D 8.5.4)",
             "far": "the entry is too far from the platform (D 8.4.4: from the end of the platform)"}

    def referee_reset(self, w, ref):
        self.dive_reset(w, ref, ref.geoms(names=["platform", "tower"]), ref.geoms(prefix="rail_"))

    def privileged(self, w):
        tr = self.trackers
        return {"pelvis": w.pelvis().tolist(), "com": w.com().tolist(), "phase": tr.get("phase"),
                "somersault_rad": tr.get("turn"), "platform": {"front_x": self.geo["front_x"], "top": self.geo["top"],
                                                               "half_width": self.geo["half_width"]},
                "water_z": 0.0}
