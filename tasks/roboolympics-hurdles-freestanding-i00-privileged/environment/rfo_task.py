"""50 m hurdles with free-standing hurdles (World Athletics TR 22 at the indoor distance): the `hurdles` race (four
1.067 m hurdles at 13.72 m + 9.14 m x i, 8.86 m to the finish, the Unitree H1-2), but every hurdle is a free rigid
body standing on the track, as a real one does: an L-shaped base on each side (its foot pointing towards the
approaching athlete, the upright at its far end), a rectangular frame (the top bar and a cross bar) and two
counterweights on the feet that set the official toppling force. It touches the track (with the friction of rubber
feet on a polyurethane track) and the robot: it can be pushed, slide, tip over forwards or backwards, bounce, and a
fallen hurdle stays where it comes to rest, an obstacle that can trip the runner.

The referee is `hurdles`' (TR 22.6 over each hurdle, 22.6.1 a leg beside it, 22.6.2 knocked by hand or body, the lane,
the down rule, the finish), with the hurdle's plane and top defined for a hurdle that moves: each hurdle is judged at
its standing pose on its mark (the plane of its top bar there, its top's height), wherever it is now; it may leave its
standing pose only by a legal knock (a leg on its top bar while the robot is in the air or its pelvis is already over),
never pushed, kicked or shoved along the track first, never by hand or body; and the robot may not climb on it (the
hurdle carrying it, measured by the contact force)."""
import math

import mujoco
import numpy as np

from rfo.referee import Crossing
from rfo.task import TaskBase

TRACK = (0.72, 0.25, 0.18, 1)
H1_FOOT_FRONT = 0.158            # m: the front end of the standing H1-2's feet ahead of its pelvis (`hurdles`)
UPPER = ("hands", "forearms", "upper_arms", "torso", "pelvis")     # "hand or body" of TR 22.6.2
ORD = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth")
# The hurdle's construction (TR 22.4: metal, the top bar of a non-metallic material; two bases and two uprights at the
# extreme end of each base, a rectangular frame reinforced by a cross bar; adjustable counterweights). The rule book
# fixes the width, the top bar's height and thickness, the base's length, the total mass and the toppling force; the
# rest is a typical competition hurdle's (steel 30 mm tubes, a wooden top bar, steel counterweights).
BAR_DEPTH = 0.02                 # m: the top bar's thickness (TR 22.4: 10 to 25 mm)
TUBE = 0.03                      # m: the uprights' and the bases' square steel tube
CROSS_R = 0.0125                 # m: the frame's cross bar (a 25 mm tube), cross_below_m below the hurdle's top
CW_HALF = (0.05, 0.03, 0.0292)   # m: a counterweight's half sizes (steel, 2.75 kg)
PAD_R, CLEAR = 0.010, 0.002      # m: the rubber feet (one under each end of each base: what stands on the track) and
#                                  the base tube's clearance above the track
MASS = dict(bar=1.0, upright=0.9, cross=0.8, base=0.85, pad=0.025, counterweight=2.75)    # kg (10.9 kg in all)
TRACK_FRICTION = 0.6             # the hurdle's rubber feet on a polyurethane track (a hard rubber on a synthetic
#                                  surface, dry: 0.5 to 0.7); World Athletics does not specify it
G = 9.80665
CONTACT_GAP_S = 0.02             # s: a break in a contact shorter than this does not end it (contact chatter)
# The hurdle's contacts (they win over the other geom's: priority): nearly hard, so that a push below the toppling
# force holds it on the track by friction instead of letting it creep (with MuJoCo's default soft contacts a push of
# 3.6 kgf at the top bar walks it 2.5 mm/s; with these 0.007 mm/s)
CONTACT = dict(solref="0.003 1", solimp="0.998 0.9995 0.001")


def parts(p) -> list:
    """The hurdle's solid parts: (name, type, centre, size, mass), in the hurdle's frame: on the track under the
    front rubber feet (the line it tips over when pushed forwards), x towards the finish, y across the lane."""
    H, bw, bh, L = p["hurdle_height_m"], p["hurdle_width_m"], p["bar_height_m"], p["base_length_m"]
    fy = bw / 2 - TUBE / 2                       # the uprights and the bases, under the ends of the top bar
    up_h = (H - bh - CLEAR - TUBE) / 2           # an upright: from the base's top to the top bar's lower edge
    cw_x = -counterweight_d(p)
    out = [("bar", "box", (PAD_R - TUBE - BAR_DEPTH / 2, 0.0, H - bh / 2), (BAR_DEPTH / 2, bw / 2, bh / 2),
            MASS["bar"]),
           ("cross", "capsule", (PAD_R - TUBE / 2, 0.0, H - p["cross_below_m"]), (CROSS_R, fy - TUBE / 2),
            MASS["cross"])]
    for s, tag in ((1, "L"), (-1, "R")):
        out += [(f"up{tag}", "box", (PAD_R - TUBE / 2, s * fy, CLEAR + TUBE + up_h), (TUBE / 2, TUBE / 2, up_h),
                 MASS["upright"]),
                (f"base{tag}", "box", (PAD_R - L / 2, s * fy, CLEAR + TUBE / 2), (L / 2, TUBE / 2, TUBE / 2),
                 MASS["base"]),
                (f"cw{tag}", "box", (cw_x, s * fy, CLEAR + TUBE + CW_HALF[2]), CW_HALF, MASS["counterweight"]),
                (f"pad{tag}0", "sphere", (0.0, s * fy, PAD_R), (PAD_R,), MASS["pad"]),
                (f"pad{tag}1", "sphere", (2 * PAD_R - L, s * fy, PAD_R), (PAD_R,), MASS["pad"])]
    return out


def hull_points(m, g, n=400) -> np.ndarray:
    """The support points of mesh geom g (geom frame) along n fixed directions (a Fibonacci sphere)."""
    mid = int(m.geom_dataid[g])
    v = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]].astype(float)
    i = np.arange(n) + 0.5
    phi, th = np.arccos(1 - 2 * i / n), math.pi * (1 + 5 ** 0.5) * i
    dirs = np.c_[np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)]
    return v[np.unique(np.argmax(v @ dirs.T, axis=0))]


def fixed_moment(p) -> float:
    """sum(m d) (kg m) of the hurdle's parts other than the counterweights, d = each part's distance behind the front
    rubber feet (the line it tips over when pushed forwards)."""
    L = p["base_length_m"]
    return (MASS["bar"] * (TUBE + BAR_DEPTH / 2 - PAD_R) + (2 * MASS["upright"] + MASS["cross"]) * (TUBE / 2 - PAD_R)
            + 2 * MASS["base"] * (L / 2 - PAD_R) + 2 * MASS["pad"] * (L - 2 * PAD_R))


def counterweight_d(p) -> float:
    """Where the counterweights sit on the bases (their centres' distance behind the front rubber feet, m) for the
    toppling force of the rules: a horizontal force F at the centre of the top bar's top edge tips the hurdle over
    its front feet when F h > g sum(m d) (the official hurdle's adjustable counterweights, set)."""
    return (p["toppling_force_kgf"] * p["hurdle_height_m"] - fixed_moment(p)) / (2 * MASS["counterweight"])


def balance_deg(p) -> float:
    """The forward tilt past which the hurdle falls on by itself (its centre of mass over the front feet)."""
    ps = parts(p)
    M = sum(q[4] for q in ps)
    cx = sum(q[4] * q[2][0] for q in ps) / M
    cz = sum(q[4] * q[2][2] for q in ps) / M
    return math.degrees(math.atan2(-cx, cz))


class Task(TaskBase):
    name = "hurdles-freestanding"
    title = "50 m hurdles, free-standing hurdles"
    category = "track-and-jumps"
    robot = "unitree_h1"
    rulebook = ("World Athletics Competition and Technical Rules, 2024 edition: TR 22 (22.1-22.3 distances and "
                "heights: the men's hurdle 1.067 m high, 13.72 m to the first, 9.14 m between; at the indoor "
                "distance of 50 m that is four hurdles and 8.86 m from the last to the finish; 22.4-22.5 the hurdle: "
                "metal with a non-metallic top bar, two bases and two uprights at the extreme end of each base "
                "supporting a rectangular frame reinforced by a cross bar, 1.18 to 1.20 m wide, a top bar 70 mm "
                "high and 10 to 25 mm thick, a base at most 0.70 m long, at least 10 kg, counterweights set so that "
                "a horizontal force of 3.6 to 4.0 kg at the centre of the top bar's top edge topples it; placed with "
                "the feet towards the approaching athlete; 22.6 each hurdle is gone over in the athlete's own lane; "
                "22.6.1 a foot or leg beside the hurdle below the plane of its top; 22.6.2 knocking down or "
                "displacing a hurdle by hand or body; 22.7 knocking hurdles down otherwise is no offence), TR 17.3 "
                "(lanes), TR 18.2 and TR 19 (the finish)")
    deviations = [
        "TR 16 (the start): no starter's commands, no blocks and no reaction time: the robot stands with the front "
        "ends of its feet {toe_gap_m} m behind the start line and the clock runs from t = 0",
        "TR 22.6 ('goes over each hurdle') is judged geometrically at the hurdle's standing pose on its mark, "
        "wherever the hurdle is now: the pelvis must pass above the height of the hurdle's top, each foot (its "
        "ankle joint) above the lower edge of the top bar, all three between the bar's ends, through the plane "
        "where the top bar stood, all three in one flight (from the first crossing to the last the robot "
        "touches nothing but that hurdle's top bar: the rule book's clearance is a stride in the air, and a leg "
        "swung over from the ground or a step over a hurdle that lies on the track is not one); a hurdle that "
        "has fallen, or has been pushed on or out of the lane, does not "
        "lower or move what is to be gone over; going over it on the hurdle (climbing) is judged by contact: a "
        "hurdle not yet gone over that still stands may not push the robot upwards by more than {support_n} N for "
        "longer than {strike_s} s, and at the instant the pelvis or a foot crosses its plane only the legs may "
        "touch it, on its top bar",
        "TR 22.6.2 (knocking down or displacing a hurdle by hand, body or the upper side of the lead leg) and TR 22.7: "
        "intent and the side of the leg cannot be judged, so the cause of a hurdle's displacement is judged from "
        "contacts: a hurdle that leaves its standing pose (a point of its top bar more than {displaced_m} m from "
        "where it stood) within {touch_window_s} s of a touch by a hand, an arm, the trunk or the pelvis is a "
        "failure if that touch was the robot's latest on it or came within {blame_recent_s} s; the legs may "
        "knock it down, on its top bar, during the clearance (while the robot touches nothing but that hurdle's "
        "top bar, or its pelvis is over the hurdle's plane); any other displacement before "
        "the hurdle is gone over (pushed, kicked or shoved along the track first, from the ground) is a failure: "
        "the athlete did not go over that hurdle as it stood",
        "TR 17.3 (lanes): the lane is judged by the pelvis (its centre more than half a lane width from the "
        "lane's centre line); TR 22.6.1 is judged on the centres of the legs' collision bodies within "
        "{beside_m} m of the hurdle's plane",
        "TR 17 (a fallen athlete): a robot whose pelvis is below {down_z_m} m is down; it may get up and go on, "
        "but {down_limit_s} s down in a row end the race (did not finish)",
        "TR 19 (photo finish): the time is the instant the leading point of the torso link's collision mesh "
        "reaches the finish line's plane, interpolated between 1 ms physics steps (the H1-2's trunk and head are "
        "one link, so its torso includes the head); no wind; the robot alone on a straight of three lanes",
        "TR 22.4-22.5 (the hurdle): a rigid body (no deflection of the top bar); the rule book does not give the "
        "friction of a hurdle on the track: {track_friction} (rubber feet on a polyurethane track); the "
        "counterweights are set once for the toppling force {toppling_force_kgf} kg; the distance is the indoor "
        "50 m with its four hurdles, on an outdoor straight, not the 110 m; the time limit, {time_limit_s} s, is "
        "this benchmark's (FAMILIES.md)",
    ]
    time_limit_s = 140.0
    start = (-(0.05 + 0.02 + H1_FOOT_FRONT), 0.0, 0.0)
    stages = [f"hurdle {i + 1}" for i in range(4)] + ["finish"]
    fall_rule = False                # the race's own: a fallen runner may get up (the "down" rule)
    params = dict(distance_m=50.0, hurdles=4, first_hurdle_m=13.72, spacing_m=9.14, hurdle_height_m=1.067,
                  hurdle_width_m=1.19, bar_height_m=0.07, base_length_m=0.70, cross_below_m=0.35,
                  toppling_force_kgf=3.8, hurdle_mass_kg=10.9, balance_deg=55, track_friction=TRACK_FRICTION,
                  lane_width_m=1.22, start_line_m=0.05, toe_gap_m=0.02, knocked_deg=60.0, displaced_m=0.10,
                  touch_window_s=0.5, blame_recent_s=0.1, support_n=100.0,
                  strike_s=0.15, beside_m=0.10, down_z_m=0.40, down_limit_s=10.0)

    sentence = ("Run the 50 m hurdles over four free-standing hurdles: go over each one in your lane, never beside "
                "it, under its top, or after pushing it away, and bring your torso to the finish line.")
    rules = ("World Athletics rules for the hurdles, at the indoor distance of 50 m. The lane runs along +x, "
             "{lane_width_m} m wide, centred on y = 0; the start line ({start_line_m} m wide) has its far edge at "
             "x = 0, the finish line is x = {distance_m} m. {hurdles} hurdles stand across the lane, the face of "
             "the first one's top bar {first_hurdle_m} m from the start line and one every {spacing_m} m after it "
             "(the last 8.86 m before the finish). A hurdle is a loose object standing on the track: "
             "{hurdle_width_m} m wide and {hurdle_height_m} m high, a top bar {bar_height_m} m high, two uprights "
             "and a cross bar {cross_below_m} m below its top; its two bases, {base_length_m} m long, lie on the "
             "track on your side of it, with counterweights on them; it weighs {hurdle_mass_kg} kg and tips over "
             "forwards when a horizontal force of more than {toppling_force_kgf} kg pushes the middle of its top "
             "bar (tipped further than about {balance_deg} degrees it falls on by itself); it can slide on the "
             "track (friction {track_friction}), fall, bounce and lie where it comes to rest, and you can trip on "
             "it, but not climb on it. Each hurdle is judged where it stands at the start (its standing pose on "
             "its mark), wherever it is later. The clock starts at t = 0. You go over a hurdle when your pelvis "
             "and both your feet (the "
             "ankle joints) have crossed the plane of its top bar in its standing pose towards +x, each between "
             "the bar's two ends, the pelvis higher than the hurdle's top ({hurdle_height_m} m above the track) "
             "and each foot higher than the lower edge of its top bar ({hurdle_height_m} m less {bar_height_m} m), "
             "whether the hurdle still stands there or not, and in one flight: from the first of these three "
             "crossings to the last, no part of you touches anything but that hurdle's top bar; a pelvis or a foot "
             "that comes back over the plane has "
             "not crossed it and must cross it again. The hurdles are gone over in order. A hurdle leaves its "
             "standing pose when a point of its top bar is more than {displaced_m} m from where it stood. Knocking "
             "a hurdle down with your legs is allowed when a leg strikes its top bar during the clearance: while "
             "you touch nothing else but that hurdle's top bar (in the air) or once your pelvis is over the "
             "hurdle's plane; a hurdle tipped more than "
             "{knocked_deg} degrees is counted as down, without a fault. Where a hurdle comes to rest after that "
             "does not matter. You finish at the moment the leading point of your torso (the "
             "trunk and head hull; not the arms, legs or feet) reaches the finish line, with all hurdles gone "
             "over. You succeed with a finish within {time_limit_s} s of robot time. A fall does not end the race: "
             "you are down while your pelvis is below {down_z_m} m, you may get up and go on, but {down_limit_s} s "
             "down in a row end it. You fail if your pelvis or a foot crosses the next hurdle's plane beside the "
             "hurdle, or lower than said above (going under its top); if between the first and the last of these "
             "crossings you touch the track or anything else but its top bar (stepping over it); if a part of one "
             "of your legs is beside the "
             "next hurdle (beyond the bar's ends, within {beside_m} m of its plane) lower than the hurdle's top; "
             "if a hurdle leaves its standing pose within {touch_window_s} s of being touched by a hand, an arm, "
             "your trunk or your pelvis, that touch being your latest on it or within {blame_recent_s} s before "
             "(knocked by hand or body; also one you have gone over); if you climb on a hurdle you have not yet "
             "gone over while it stands (tipped less than {knocked_deg} degrees): it pushes you upwards by more "
             "than {support_n} N for longer than {strike_s} s, or anything of you but a leg on its top bar touches "
             "it at the instant your pelvis or a foot crosses its plane; if a hurdle you "
             "have not yet gone over leaves its standing pose in any other way than the legal knock above "
             "(pushed, kicked or shoved along the track before you went over it); if your pelvis is more than "
             "half the lane's width from y = 0; if your torso reaches the finish line before every hurdle is gone "
             "over; when down for {down_limit_s} s; or "
             "after {time_limit_s} s.")
    venue = ("You stand in your lane facing the finish (+x), the front ends of your feet {toe_gap_m} m behind the "
             "start line, your pelvis 0.23 m behind it. The lane lines are white on a red track; the hurdles' top "
             "bars are white with black stripes, their bases and counterweights grey on the track, reaching "
             "{base_length_m} m towards you along the lane's edges; two white posts stand beside the finish line. "
             "In your rest pose your forearms point forward at about the height of a hurdle's top.")
    difficulty = ("A hurdle's top is higher than the robot's hip joints: each of the four has to be jumped with the "
                  "whole pelvis above 1.067 m and each foot lifted a metre, on a body of 67 kg whose only built-in "
                  "gait walks at 0.7 m/s and drifts in heading. The hurdles are loose: a clipped bar tips one into "
                  "the landing, where it lies as an obstacle, and walking up to one shoves it away, which is a "
                  "failure.")

    # ------------------------------------------------------------------ the venue
    def hurdle_x(self):
        """The marks: the x of each hurdle's top bar face on the approach side, standing."""
        p = self.p
        return [round(p["first_hurdle_m"] + i * p["spacing_m"], 2) for i in range(int(p["hurdles"]))]

    def plane_x(self, i) -> float:
        """The plane of hurdle i's top bar (its middle) in the standing pose: what is gone over."""
        return self.hurdle_x()[i] + BAR_DEPTH / 2

    def hurdle_mass(self) -> float:
        return sum(q[4] for q in parts(self.p))

    def toppling_force_kgf(self) -> float:
        """The horizontal force at the centre of the top bar's top edge that just tips a hurdle over (kgf), from
        its parts (the statics of a rigid body on its front feet)."""
        ps = parts(self.p)
        return sum(q[4] * -q[2][0] for q in ps) / self.p["hurdle_height_m"]

    def _hurdle(self, sc, name, mark):
        """One hurdle, a free body (frame: parts())."""
        p = self.p
        H, bh = p["hurdle_height_m"], p["bar_height_m"]
        b = sc.body(name, (mark + BAR_DEPTH + TUBE - PAD_R, 0.0, 0.0), free=True)
        kw = dict(contype="1", conaffinity="13", condim="3", priority="1",
                  friction=(p["track_friction"], 0.005, 0.0001), **CONTACT)
        colour = {"bar": (0.97, 0.97, 0.97, 1), "cw": (0.18, 0.18, 0.2, 1), "pad": (0.1, 0.1, 0.1, 1)}
        for part, typ, pos, size, mass in parts(p):
            extra = {}
            if typ == "capsule":                         # along y
                extra = dict(fromto=(pos[0], -size[1], pos[2], pos[0], size[1], pos[2]))
                size, pos = size[:1], None
            sc.geom(b, f"{name}_{part}", type=typ, pos=pos, size=size, mass=mass,
                    rgba=colour.get(part.rstrip("LR01"), (0.3, 0.3, 0.32, 1)), **extra, **kw)
        for i, yy in enumerate((-0.4, 0.0, 0.4)):        # the stripes (visual only)
            sc.geom(b, f"{name}_stripe{i}", type="box", pos=(PAD_R - TUBE - BAR_DEPTH - 0.0005, yy, H - bh / 2),
                    size=(0.0005, 0.1, bh / 2 - 0.002), rgba=(0.08, 0.08, 0.08, 1), contype="0", conaffinity="0",
                    mass=0)

    def build(self, sc):
        p = self.p
        assert counterweight_d(p) + CW_HALF[0] <= p["base_length_m"] - PAD_R, "the counterweights are off the bases"
        assert abs(self.hurdle_mass() - p["hurdle_mass_kg"]) < 1e-9 and abs(balance_deg(p) - p["balance_deg"]) < 1.0, \
            "hurdle_mass_kg and balance_deg are what the hurdle's construction gives"
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
        sc.camera("first_hurdle", (11.0, -3.2, 1.6), (13.9, 0.0, 0.55), fovy=55)

    def reset(self, w):
        for i, x in enumerate(self.hurdle_x()):          # each hurdle on its mark, standing, at rest
            w.put(f"hurdle{i + 1}", (x + BAR_DEPTH + TUBE - PAD_R, 0.0, 0.0))

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        m = w.m
        xs = self.hurdle_x()
        self.n_hurdles = len(xs)
        self.planes = [self.plane_x(i) for i in range(self.n_hurdles)]
        self.hbody = [m.body(f"hurdle{i + 1}").id for i in range(self.n_hurdles)]
        self.bar_geom = [m.geom(f"hurdle{i + 1}_bar").id for i in range(self.n_hurdles)]
        self.hurdle_mask = [ref.geoms(body=f"hurdle{i + 1}") for i in range(self.n_hurdles)]
        self.bar_mask = [ref.geoms(names=[f"hurdle{i + 1}_bar"]) for i in range(self.n_hurdles)]
        self.any_hurdle = np.any(self.hurdle_mask, axis=0)
        self.frame_mask = [ref.geoms(names=[f"hurdle{i + 1}_{q}" for q in ("bar", "upL", "upR", "cross")])
                           for i in range(self.n_hurdles)]
        self.points = {"pelvis": w.robot.pelvis, "left foot": m.body("left_ankle_roll_link").id,
                       "right foot": m.body("right_ankle_roll_link").id}
        self.leg_ids = np.flatnonzero(ref.part("legs"))
        self.legs = ref.part("legs")
        self.upper = ref.part(*UPPER)
        self.not_upper = ref.robot_mask & ~self.upper
        self.not_legs = ref.robot_mask & ~self.legs
        self.not_bar = [self.hurdle_mask[i] & ~self.bar_mask[i] for i in range(self.n_hurdles)]
        self.cos_down = math.cos(math.radians(self.p["knocked_deg"]))
        self._f6 = np.zeros(6)
        self.torso_geom = next(g for g in range(m.ngeom) if m.body(int(m.geom_bodyid[g])).name == "torso_link"
                               and m.geom_contype[g] and int(m.geom_dataid[g]) >= 0
                               and m.mesh(int(m.geom_dataid[g])).name.endswith("torso_link"))
        self.torso_pts = hull_points(m, self.torso_geom)
        self.bar_rest = [self.bar_points(w, i) for i in range(self.n_hurdles)]
        qa = [w.free[f"hurdle{i + 1}"][0] for i in range(self.n_hurdles)]
        self.hq = np.array([[a + k for k in range(7)] for a in qa])
        self.q_rest = w.d.qpos[self.hq].copy()
        self.bar_reach = max(float(np.max(np.linalg.norm(self.bar_points(w, i) - w.d.xpos[self.hbody[i]], axis=1)))
                             for i in range(self.n_hurdles))
        # over: who (pelvis, left foot, right foot) is over the next hurdle; upper_t / leg_t: when each hurdle was
        # last touched, while it still stood, by a hand, an arm or the trunk / by a leg on its top bar during the
        # clearance; other_t: by any other part; touch: [when, by which parts] each was last touched while it stood;
        # climb: [first, last] time of the current episode in which it carries the robot; moved: the hurdles that
        # have left their standing pose (legally); down: the hurdles tipped beyond knocked_deg; front: the torso's
        # leading x one physics step ago; down_k: since when the robot is down
        self.trackers = {"over": [], "upper_t": [None] * self.n_hurdles, "leg_t": [None] * self.n_hurdles,
                         "touch": [None] * self.n_hurdles, "other_t": [None] * self.n_hurdles,
                         "climb": [None] * self.n_hurdles,
                         "moved": [], "down": [], "front": None, "down_k": None}
        for i in range(self.n_hurdles):
            for k in self.points:
                self.trackers[f"bar{i + 1} {k}"] = Crossing((1, 0, 0), self.plane_x(i), direction=1)

    def bar_points(self, w, i) -> np.ndarray:
        """The top bar's centre and its two ends (the middle of each end face), world (3, 3)."""
        g = self.bar_geom[i]
        R = w.d.geom_xmat[g].reshape(3, 3)
        h = self.p["hurdle_width_m"] / 2
        return w.d.geom_xpos[g] + np.array([[0.0, 0.0, 0.0], [0.0, h, 0.0], [0.0, -h, 0.0]]) @ R.T

    def displacement(self, w, i) -> float:
        return float(np.max(np.linalg.norm(self.bar_points(w, i) - self.bar_rest[i], axis=1)))

    def support_n(self, w, ref, i) -> float:
        """The upward force (N) that hurdle i exerts on the robot now (the sum over their contacts)."""
        d, m = w.d, w.m
        k = d.ncon
        g = d.contact.geom[:k]
        rob, hm = ref.robot_mask, self.hurdle_mask[i]
        on2 = rob[g[:, 1]] & hm[g[:, 0]]                 # the robot is geom2: the force on it is + the frame's
        sel = np.flatnonzero((on2 | (rob[g[:, 0]] & hm[g[:, 1]])) & (d.contact.dist[:k] <= 0))
        fz = 0.0
        for c in sel:
            mujoco.mj_contactForce(m, d, int(c), self._f6)
            f = d.contact.frame[c].reshape(3, 3).T @ self._f6[:3]
            fz += float(f[2]) if on2[c] else -float(f[2])
        return fz

    def torso_front(self, w) -> float:
        g = self.torso_geom
        R = w.d.geom_xmat[g].reshape(3, 3)
        return float(w.d.geom_xpos[g][0] + np.max(self.torso_pts @ R[0]))

    def tilt_deg(self, w, i) -> float:
        """The angle of the hurdle's uprights from the vertical, degrees (0 standing, about 90 lying)."""
        return math.degrees(math.acos(max(-1.0, min(1.0, float(w.d.xmat[self.hbody[i]][8])))))

    def substep(self, w, ref):
        if ref.failed:                                   # (the rest of the control step after a failure)
            return
        tr, p = self.trackers, self.p
        half, H, D = p["hurdle_width_m"] / 2, p["hurdle_height_m"], p["distance_m"]
        n = len(ref.stages)                              # hurdles gone over so far
        i = n
        while i == n < self.n_hurdles:                   # only the next hurdle counts (its crossings start when it
            for k, b in self.points.items():             # becomes the next one: 9 m after the last)
                x = tr[f"bar{i + 1} {k}"].update(w.d.xpos[b])
                if x is None:
                    continue
                y, z = float(x[1]), float(x[2])
                if abs(y) >= half:
                    return ref.fail(f"went beside the {ORD[i]} hurdle", what=k, y=round(y, 3))
                low = H if k == "pelvis" else H - p["bar_height_m"]
                if ref.touching(ref.robot_mask, self.hurdle_mask[i]) and (ref.touching(
                        self.not_bar[i], ref.robot_mask) or ref.touching(self.not_legs, self.hurdle_mask[i])):
                    return ref.fail(f"climbed on the {ORD[i]} hurdle", what=k,
                                    parts=sorted(ref.parts_touching(self.hurdle_mask[i])))
                if z <= low:
                    return ref.fail(f"went under the top of the {ORD[i]} hurdle", what=k, z=round(z, 3),
                                    must_be_above=round(low, 3))
                if k not in tr["over"]:
                    tr["over"] = sorted(tr["over"] + [k])
            if tr["over"]:                               # a point that comes back has not gone over the hurdle
                back = [k for k in tr["over"] if float(w.d.xpos[self.points[k]][0]) < self.planes[i]]
                if back:
                    tr["over"] = [k for k in tr["over"] if k not in back]
            # a clearance is one flight: from the first of the three crossings to the last the robot touches
            # nothing but this hurdle's top bar (a leg swung over from the ground, a step or a hop over a hurdle
            # already knocked down is not going over it)
            if tr["over"] and not ref.airborne(self.bar_mask[i]):
                return ref.fail(f"went over the {ORD[i]} hurdle without a jump", over=list(tr["over"]),
                                parts=sorted(ref.parts_touching(~ref.robot_mask & ~self.bar_mask[i])))
            if len(tr["over"]) == len(self.points):
                ref.stage(f"hurdle {i + 1}", tilt_deg=round(self.tilt_deg(w, i), 1),
                          displaced_m=round(self.displacement(w, i), 3))
                tr["over"] = []
                n += 1
            i += 1
        if n < self.n_hurdles:                           # TR 22.6.1: a leg beside the next hurdle below its top
            c = w.d.geom_xpos[self.leg_ids]
            bad = (np.abs(c[:, 0] - self.planes[n]) < p["beside_m"]) & (np.abs(c[:, 1]) > half) & (c[:, 2] < H)
            if bool(np.any(bad)):
                g = int(self.leg_ids[np.flatnonzero(bad)[0]])
                return ref.fail(f"a leg beside the {ORD[n]} hurdle below its top",
                                part=ref.part_names[int(ref.part_code[g])], y=round(float(w.d.geom_xpos[g][1]), 3))
        # TR 22.6.2 and 22.7: who moves a hurdle from its standing pose. A cheap bound first (the body's translation
        # plus its rotation times the bar's farthest point), the bar's points only when it could be over the line.
        P = w.d.qpos[self.hq]
        rot = 2 * np.arccos(np.minimum(1.0, np.abs(np.sum(P[:, 3:] * self.q_rest[:, 3:], axis=1))))
        bound = np.linalg.norm(P[:, :3] - self.q_rest[:, :3], axis=1) + rot * self.bar_reach
        touch = ref.touching(ref.robot_mask, self.any_hurdle)
        up_down = w.d.xmat[self.hbody, 8]
        for i in range(self.n_hurdles):
            # TR 22.6 "goes over": never on the hurdle. A hurdle not yet gone over that still stands (not down) may
            # not carry the robot: an upward push of more than support_n on the robot for longer than strike_s
            # (standing, sitting or hanging on it, a step up onto its cross bar) is climbing it.
            if touch and i >= n and up_down[i] >= self.cos_down and ref.touching(ref.robot_mask, self.hurdle_mask[i]):
                fz = self.support_n(w, ref, i)
                if fz > p["support_n"]:
                    c = tr["climb"][i]
                    if c is None or ref.time - c[1] > CONTACT_GAP_S:
                        c = [ref.time, ref.time]
                    c[1] = ref.time
                    tr["climb"][i] = c
                    if c[1] - c[0] > p["strike_s"]:
                        return ref.fail(f"climbed on the {ORD[i]} hurdle", support_n=round(fz, 1),
                                        parts=sorted(ref.parts_touching(self.hurdle_mask[i])))
            if i in tr["moved"]:                         # judged once: when it leaves its standing pose
                continue
            if touch and ref.touching(ref.robot_mask, self.hurdle_mask[i]):
                tr["touch"][i] = [round(ref.time, 4), sorted(ref.parts_touching(self.hurdle_mask[i]))]
                if ref.touching(self.upper, self.hurdle_mask[i]):
                    tr["upper_t"][i] = ref.time
                if ref.touching(self.not_upper, self.hurdle_mask[i]):
                    tr["other_t"][i] = ref.time
                # a leg on the top bar during the clearance: the robot touches nothing but this hurdle's top bar (in
                # the air), or its pelvis is over the hurdle's plane
                if i >= n and ref.touching(self.legs, self.bar_mask[i]) and (
                        (i == n and "pelvis" in tr["over"]) or ref.airborne(self.bar_mask[i])):
                    tr["leg_t"][i] = ref.time
            if bound[i] <= p["displaced_m"]:
                continue
            dist = self.displacement(w, i)
            if dist <= p["displaced_m"]:
                continue
            ut, lt, win = tr["upper_t"][i], tr["leg_t"][i], p["touch_window_s"]
            info = dict(displaced_m=round(dist, 3), tilt_deg=round(self.tilt_deg(w, i), 1),
                        last_touch=tr["touch"][i])          # [t, the robot's parts] of the latest touch
            # by hand or body (also a hurdle already gone over): a hand, an arm or the trunk was the latest to touch
            # it (or touched it within blame_recent_s)
            if ut is not None and ref.time - ut <= win and (ut >= (tr["other_t"][i] or -1.0)
                                                            or ref.time - ut <= p["blame_recent_s"]):
                return ref.fail(f"knocked the {ORD[i]} hurdle with a hand, an arm or the trunk", **info)
            if i >= n and (lt is None or ref.time - lt > win):
                return ref.fail(f"displaced the {ORD[i]} hurdle before going over it", **info)
            tr["moved"] = sorted(tr["moved"] + [i])
            ref.event("hurdle_knocked", hurdle=i + 1, **info)
        if len(tr["down"]) < self.n_hurdles:
            up = w.d.xmat[self.hbody, 8]
            for i in np.flatnonzero(up < math.cos(math.radians(p["knocked_deg"]))):
                if int(i) not in tr["down"]:
                    tr["down"] = sorted(tr["down"] + [int(i)])
                    ref.event("hurdle_down", hurdle=int(i) + 1)
                    ref.metrics["hurdles_down"] = len(tr["down"])
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
        hs = []
        for i in range(self.n_hurdles):
            qa, _ = w.free[f"hurdle{i + 1}"]
            hs.append({"mark_x": self.hurdle_x()[i], "plane_x": self.plane_x(i),
                       "pos": [round(float(v), 4) for v in w.d.qpos[qa:qa + 3]],
                       "quat": [round(float(v), 5) for v in w.d.qpos[qa + 3:qa + 7]],
                       "tilt_deg": round(self.tilt_deg(w, i), 2), "displaced_m": round(self.displacement(w, i), 4),
                       "knocked_legally": i in self.trackers["moved"]})
        return {"pelvis": w.pelvis().tolist(), "next_hurdle": n + 1, "hurdles": hs,
                "hurdle_top_m": self.p["hurdle_height_m"], "torso_front_x": self.torso_front(w)}
