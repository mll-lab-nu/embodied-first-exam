"""High jump (World Athletics TR 26-27): a 4.00 m bar on its supports between uprights 4.02 m apart, the 6 m x 4 m x
0.7 m landing mat behind it; a take-off from one foot, over the bar, and the bar stays on."""
import mujoco
import numpy as np

from rfo.referee import Flights
from rfo.task import TaskBase
# A rigid crossbar (fibreglass; the landing mat keeps its foam)'s contact with the robot, the venue's fixtures and the
# other props (the ground keeps its own: rfo/world.py GROUND_SOLMIX): the stiff contact of the core's shells
# (rfo/world.py SHELL_CONTACT: solref 0.004 s, solimp 0.99 0.999 0.0005, from Embodied Olympics' weightlifting fix, a rigid
# prop on the robot's aluminium) with a solmix that wins over a default- contact geom; a ball (priority 1) keeps its
# own bounce. With MuJoCo's default soft contact (solref 0.02 1, solimp 0.9 0.95) it sank 40 mm into the floor and 39
# mm into the robot (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402

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
            contype="1", conaffinity="13", **RIGID)
    for s, tag in ((1, "L"), (-1, "R")):                 # the end pieces: flat undersides, so the bar does not roll
        sc.geom(b, f"{name}_end{tag}", type="box", pos=(0, s * (L / 2 - end), 0), size=(r, end, r), mass=m_end,
                rgba=(0.95, 0.95, 0.95, 1), friction=(0.6, 0.005, 0.0001), contype="1", conaffinity="13", **RIGID)
    return dict(x=x, height=height, rest_z=height - r, plane_x=x - r, half_gap=gap / 2)


# The landing mat, from foam mechanics. A landing area is blocks of soft polyurethane foam under a cover. Such foam
# carries about 4-6 kPa at 25 % compression (the lower layer of a sports landing mat: US patent 5,562,573, "Landing
# mat for gymnasts", 1996: 0.040-0.060 kgf/cm^2) and, being a foam, keeps near that stress over a long plateau of strain
# before it densifies, absorbing a landing with little rebound (Gibson and Ashby, Cellular Solids, 2nd ed. 1997,
# ch. 5). For the H1-2 coming down on its back (about 0.4 m^2 in contact, 5 kPa carrying 2 kN, three times its weight)
# at 4 m/s that is a sink of about 0.4 m, and lying still, below the plateau, about 1 cm. World Athletics (TR 27.10)
# sets only the area's size (at least 6 m x 4 m x 0.7 m); the shock-absorption classes of EN 12503-2 were not
# available. MuJoCo's contact is a spring-damper normalised by the bodies' masses, not a pressure law: fitted to those
# numbers (measured with a rigid block and with the robot), a time constant of 0.8 s, critically
# damped, an impedance that falls from 0.4 at the surface to 0.05 at 8 cm (a firm skin, then the yielding plateau).
# Measured with the H1-2 dropped into the mat at 3.7 m/s: 0.46 m deep, no rebound (the box contact
# it replaces: 0.20 m and 0.96 m/s back up); the body then rests about 0.28 m deep (no elastic recovery of the foam is
# modelled). Friction 1.0 on the cover (not measured).
MAT_CONTACT = dict(mat_timeconst_s=0.8, mat_dampratio=1.0, mat_imp0=0.4, mat_imp1=0.05, mat_give_m=0.08, mat_friction=1.0)


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
        "TR 27.1 (\"The athlete shall take off from one foot\") is judged on the ground's forces, after every 1 ms "
        "physics step: during the last {takeoff_window_s} s before the lift-off of the jump's flight the other "
        "(free) foot's ground force stays below {free_foot_force_frac} of the robot's weight, or the free foot is "
        "off the ground for the whole of the take-off foot's last ground contact; nothing else of the robot touches "
        "the ground in that time (or in that contact); a break of at most {contact_gap_s} s in a foot's contact "
        "is not a new contact. A staggered two-foot push, with the free foot leaving just "
        "before the lift-off, is a take-off from both feet",
        "TR 27.2(b) is judged geometrically, in one flight: the robot's pelvis and feet (the ankle joints) must "
        "pass the plane between the uprights and above the height of the bar's upper side, and every part of the "
        "robot must get beyond the plane, all in the same flight (from the take-off to the first contact with "
        "anything but the bar); a crossing made while touching the ground or the mat, or after a landing, never "
        "counts; any contact with the ground or the mat beyond the plane before that clearance is the rule's "
        "failure; the rule's allowance for a foot that touches the landing area without advantage is not used",
        "TR 27.2(a) (the bar does not remain on the supports): judged {bar_wait_s} s after the clearance and the "
        "landing, the bar must lie on its supports: touching both, its centre within half a support's width "
        "({support_width_m}/2 m) of its resting place along the runway and within {bar_rest_dz_m} m of its resting "
        "height, and at rest (its centre slower than {bar_still_m_s} m/s, turning slower than {bar_still_rad_s} "
        "rad/s); at any time before, it is off its supports when its centre is more than {bar_drop_m} m below its "
        "resting height",
        "TR 27.10 (the landing area): the mat is one box whose contact follows soft polyurethane foam (about 5 kPa "
        "at 25 % compression, then a plateau: a body landing at 4 m/s sinks about 0.4 m and does not bounce back); "
        "MuJoCo's contact fitted to it on this robot: a time constant of {mat_timeconst_s} s, damping ratio "
        "{mat_dampratio}, an impedance falling from {mat_imp0} to {mat_imp1} over {mat_give_m} m, friction "
        "{mat_friction}; the foam does not spring back after the landing, and its shock absorption is not a "
        "certified one (the rule book sets only the size); it begins {mat_gap_m} m behind the bar's plane",
        "the bar is rigid (no sag); no wind; the athlete alone, one trial at one height, {bar_height_m} m "
        "(FAMILIES.md: a school competition's opening height; the men's world record is 2.45 m)",
        "TR 27 does not define a jump; here its flight lasts at least {min_air_s} s and raises the pelvis at least "
        "{rise_min_m} m above its height at lift-off (a fall from a stand raises it by nothing); the number is kept "
        "within this robot's reach: an open-loop two-foot squat jump leaves the ground at about 1.8 m/s (0.17 m of "
        "rise); a one-foot take-off of an agent's own on the declared H2-class legs (2.5 kW, 295 N m per joint) "
        "left the ground at 2.78 m/s (0.39 m of rise of the centre of mass)",
        "the bar is rigid and its supports are fixed, so unlike a real bar it would carry a body: touching it is "
        "allowed, as in the rules, but contact with it for more than {bar_touch_max_s} s in all is a failure, and so "
        "is a push from it: the normal impulse of the bar on the robot, summed over the attempt, may be at most "
        "{bar_impulse_max_Ns} N s (a real bar sags and falls under any weight; a free 2 kg bar given that much "
        "momentum across its 4 cm supports slides off them, and here one already leaves them at about 0.7 N s; "
        "on the 67 kg robot it is 0.03 m/s); a pelvis or a foot that comes back over the plane has not passed it",
    ]
    time_limit_s = 60.0
    start = (-8.0, 0.0, 0.0)
    stages = ["take-off", "clearance", "bar stays"]
    fall_rule = False                # no rule of the event says a fall is a failure; the contacts below judge it
    params = dict(bar_height_m=1.00, bar_length_m=4.00, bar_diameter_m=0.030, bar_mass_kg=2.0, upright_gap_m=4.02,
                  support_width_m=0.04, support_length_m=0.06, mat_length_m=4.0, mat_width_m=6.0, mat_height_m=0.70,
                  mat_gap_m=0.10, **MAT_CONTACT, runway_m=15.0, takeoff_window_s=0.15, free_foot_force_frac=0.05,
                  contact_gap_s=0.03,
                  min_air_s=0.05, rise_min_m=0.08, bar_drop_m=0.05, bar_wait_s=2.0, bar_touch_max_s=0.3,
                  bar_rest_dz_m=0.005, bar_still_m_s=0.05, bar_still_rad_s=0.5,
                  bar_impulse_max_Ns=2.0)

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
             "your pelvis crosses the bar's plane. Its take-off must be from one foot: in the last "
             "{takeoff_window_s} s before lift-off your other foot presses on the ground with less than "
             "{free_foot_force_frac} of your weight (or it is off the ground for the whole of the take-off foot's "
             "last ground contact), and nothing else of you touches the ground; and in it your pelvis must rise at least {rise_min_m} m above its height at lift-off. The clearance is "
             "judged in that one flight, between the take-off and your first contact with anything but the bar: "
             "your pelvis and both feet (the ankle joints) must cross the plane between the uprights and higher "
             "than the bar's upper side (one that comes back over the plane has not passed it and must pass it "
             "again), and every part of you must get beyond the plane. A crossing made while you touch the ground "
             "or the mat, or after the flight has ended, never counts. You have cleared the bar when all of that "
             "has happened in the flight. You may touch the bar, for at most {bar_touch_max_s} s in all, and it "
             "may push you with a normal impulse of at most {bar_impulse_max_Ns} N s in all (a real bar falls "
             "under any weight: it does not carry you or throw you up), and after the clearance you may land on any part of your body, on the mat or not. You "
             "succeed when you have cleared the bar and landed, and {bar_wait_s} s later the bar still lies on its "
             "supports: touching both, its centre within half a support's width of its resting place along x and "
             "within {bar_rest_dz_m} m of its resting height, and at rest (its centre slower than {bar_still_m_s} "
             "m/s, turning slower than {bar_still_rad_s} rad/s); a bar knocked up or off counts as off. A fall is not a "
             "failure by itself. You fail if the bar drops more than {bar_drop_m} m at "
             "any time, or is not lying on its supports at that judgement; if you are in contact with the bar for "
             "more than {bar_touch_max_s} s in all, or it pushes you with more than {bar_impulse_max_Ns} N s; if you touch "
             "the ground or the mat beyond the plane before you have cleared the bar, with or without a jump; if "
             "your jump's flight ends (you touch anything but the bar) before you have cleared the bar; if the "
             "take-off is not from one foot; if the flight is not a jump; if your pelvis or a foot passes the plane "
             "outside the uprights or not higher than the bar; if your landing after the clearance touches the "
             "ground on the take-off side; or after {time_limit_s} s (the time allowed for a trial).")
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
               friction=(p["mat_friction"], 0.005, 0.0001), solref=(p["mat_timeconst_s"], p["mat_dampratio"]),
               solimp=(p["mat_imp0"], p["mat_imp1"], p["mat_give_m"], 0.5, 2), priority=1)
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
        self.supports = [ref.geoms(names=[f"bar_support{t}"]) for t in ("L", "R")]
        self.robot = ref.part("robot")
        self.weight = float(m.body_subtreemass[w.robot.pelvis]) * float(-m.opt.gravity[2])
        # phase: approach -> jump (its take-off judged) ; crossed: who has passed the plane; prev: the points one
        # physics step ago; last_on / at_t0: the feet's last ground contact (now / at the start of the current flight)
        self.trackers = {"flights": Flights(ref, min_air=self.p["min_air_s"], also_allowed=self.bar_mask),
                         "phase": "approach", "crossed": [], "prev": None, "last_on": {"left": -1.0, "right": -1.0},
                         "other_on": -1.0, "force_t": {"left": -1.0, "right": -1.0},
                         "contact_t0": {"left": None, "right": None}, "at_t0": None, "t_land": None, "t_clear": None, "bar_z0": None, "bar_s": 0.0,
                         "bar_J": 0.0}

    def _takeoff(self, w, ref) -> bool:
        """Judge the take-off of the jump's flight (TR 27.1: one foot). False: the attempt has failed."""
        tr, p = self.trackers, self.p
        t0 = tr["at_t0"]
        foot = max(SIDES, key=lambda s: t0[s])
        other = "right" if foot == "left" else "left"
        lift, c0, win = t0[foot], t0["contact_t0"][foot], p["takeoff_window_s"]
        c0 = lift if c0 is None else c0
        free = lift - t0["force_t"][other] >= win - 1e-9 or t0[other] < c0     # the free foot: unloaded, or off
        alone = lift - t0["other"] >= win - 1e-9 or t0["other"] < c0           # nothing else on the ground
        if not (free and alone):
            ref.fail("the take-off was not from one foot", free_foot_loaded_s_before=round(lift - t0["force_t"][other], 3),
                     free_foot_left_s_before=round(lift - t0[other], 3), other_part_s=round(lift - t0["other"], 3),
                     takeoff_contact_s=round(lift - c0, 3))
            return False
        tr["phase"] = "jump"
        ref.stage("take-off", foot=foot)
        return True

    def bar_force(self, w, ref) -> float:
        """The bar's normal force (N) on the robot in the physics step just taken (mj_contactForce, summed)."""
        d, m = w.d, w.m
        n = d.ncon
        g = d.contact.geom[:n]
        A, B = self.robot, self.bar_mask
        f, tot = np.zeros(6), 0.0
        for i in np.flatnonzero((A[g[:, 0]] & B[g[:, 1]]) | (A[g[:, 1]] & B[g[:, 0]])):
            if d.contact.efc_address[i] >= 0:
                mujoco.mj_contactForce(m, d, int(i), f)
                tot += float(f[0])
        return tot

    def ground_force(self, w, ref, side) -> float:
        """The normal force (N) of the ground on that foot in the physics step just taken (mj_contactForce)."""
        d, m = w.d, w.m
        n = d.ncon
        g = d.contact.geom[:n]
        A, B = self.sole[side], ref.ground
        f, tot = np.zeros(6), 0.0
        for i in np.flatnonzero((A[g[:, 0]] & B[g[:, 1]]) | (A[g[:, 1]] & B[g[:, 0]])):
            if d.contact.efc_address[i] >= 0:
                mujoco.mj_contactForce(m, d, int(i), f)
                tot += float(f[0])
        return tot

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        fl = tr["flights"]
        plane, half, H = self.bar["plane_x"], self.bar["half_gap"], p["bar_height_m"]
        if tr["bar_z0"] is None:
            tr["bar_z0"] = float(w.pos("bar")[2])
        if float(w.pos("bar")[2]) < tr["bar_z0"] - p["bar_drop_m"]:
            return ref.fail("the bar did not stay on its supports")
        if ref.touching(self.robot, self.bar_mask):      # the bar's push on the robot (the rigid supports carry it)
            tr["bar_J"] += self.bar_force(w, ref) * w.m.opt.timestep
            ref.metrics["bar_impulse_Ns"] = round(tr["bar_J"], 3)
            if tr["bar_J"] > p["bar_impulse_max_Ns"]:
                return ref.fail("the bar pushed the robot", bar_impulse_Ns=round(tr["bar_J"], 3))
        if ref.has("clearance") and tr["t_land"] is not None:
            return
        if ref.touching(self.robot, self.bar_mask):      # the rigid bar would carry a body: a real one would not
            tr["bar_s"] += w.m.opt.timestep
            if tr["bar_s"] > p["bar_touch_max_s"]:
                return ref.fail("rested on the bar", bar_contact_s=round(tr["bar_s"], 3))
        was_air = fl.air
        done = fl.update()                               # a flight of at least min_air_s that lands now, or None
        if fl.air and not was_air:
            tr["at_t0"] = {**tr["last_on"], "other": tr["other_on"], "force_t": dict(tr["force_t"]),
                           "contact_t0": dict(tr["contact_t0"])}
            if not ref.has("clearance"):                 # TR 27.2(b) in one flight: a new flight starts the count again
                tr["crossed"] = []
        for s in SIDES:
            if ref.touching(self.sole[s], ref.ground):
                if tr["contact_t0"][s] is None or ref.time - tr["last_on"][s] > p["contact_gap_s"] + 1e-9:
                    tr["contact_t0"][s] = ref.time       # a new ground contact of this foot begins
                tr["last_on"][s] = ref.time
                if self.ground_force(w, ref, s) >= p["free_foot_force_frac"] * self.weight:
                    tr["force_t"][s] = ref.time
        if ref.parts_touching(~ref.robot_mask & ~self.bar_mask) - {"left_foot", "right_foot"}:
            tr["other_on"] = ref.time
        pts = {k: [float(x) for x in w.d.xpos[b]] for k, b in self.points.items()}
        prev, tr["prev"] = tr["prev"], pts
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
            if not fl.air or ref.has("clearance"):       # touching the ground or the mat: a crossing that never counts
                continue
            tr["crossed"] = sorted(tr["crossed"] + [k])
        if (tr["phase"] == "approach" and fl.air and "pelvis" in tr["crossed"]
                and ref.time - fl.cur["t0"] >= p["min_air_s"] and not self._takeoff(w, ref)):
            return                                       # the pelvis over the plane in a flight: the jump; its take-off
        if (tr["phase"] == "jump" and fl.air and not ref.has("clearance") and len(tr["crossed"]) == 3
                and ref.robot_span((1.0, 0.0, 0.0))[0] > plane):
            tr["t_clear"] = ref.time                     # cleared in the jump's flight, before any landing
            ref.stage("clearance")
        if fl.air:
            return
        cp = ref.contact_points(self.robot, ref.ground)
        beyond = len(cp) and bool(np.any(cp[:, 0] > plane))
        if not ref.has("clearance"):
            if beyond:                                   # TR 27.2(b): beyond the plane before clearing the bar
                if tr["phase"] == "approach" and done is None:
                    return ref.fail("touched the ground or the mat beyond the bar's plane without a jump",
                                    parts=sorted(ref.parts_touching(ref.ground)))
                if done is not None:
                    ref.metrics["air_s"] = done["air_s"]
                    ref.metrics["rise_m"] = round(done["apex_z"] - done["pelvis0"][2], 3)
                return ref.fail("touched the ground or the mat beyond the bar's plane before clearing the bar",
                                parts=sorted(ref.parts_touching(ref.ground)), crossed=list(tr["crossed"]),
                                on_the_mat=bool(ref.touching(self.robot, ref.geoms(names=["mat"]))))
            if tr["phase"] == "jump":                    # the jump's flight ended (a contact, not the bar's) uncleared
                return ref.fail("the jump's flight ended before the bar was cleared", crossed=list(tr["crossed"]),
                                parts=sorted(ref.parts_touching(~ref.robot_mask & ~self.bar_mask)))
            return
        if tr["t_land"] is None:                         # the landing after the clearance: was the flight a jump?
            if done is None:
                return ref.fail("the flight was not a jump", air_s=round(ref.time - fl.flights[-1]["t0"], 3)
                                if fl.flights else None)
            rise = done["apex_z"] - done["pelvis0"][2]
            ref.metrics["air_s"], ref.metrics["rise_m"] = done["air_s"], round(rise, 3)
            if rise < p["rise_min_m"]:
                return ref.fail("the flight was not a jump", rise_m=round(rise, 3))
            if len(cp) and bool(np.any(cp[:, 0] <= plane)):
                return ref.fail("touched the ground on the take-off side after the clearance",
                                parts=sorted(ref.parts_touching(ref.ground)))
            tr["t_land"] = ref.time
            ref.event("landing", parts=sorted(ref.parts_touching(~ref.robot_mask & ~self.bar_mask)),
                      on_the_mat=bool(ref.touching(self.robot, ref.geoms(names=["mat"]))))

    def bar_on_supports(self, w, ref) -> dict:
        """TR 27.2(a) at the judgement: the bar lies on its supports (touching both, near its resting place) and is
        at rest. A bar knocked upwards, or still moving, is not on them."""
        p, d = self.p, w.d
        pos = w.pos("bar")
        _, va = w.free["bar"]
        v, om = float(np.linalg.norm(d.qvel[va:va + 3])), float(np.linalg.norm(d.qvel[va + 3:va + 6]))
        on = [ref.touching(self.bar_mask, s) for s in self.supports]
        dx, dz = float(pos[0]) - self.bar["x"], float(pos[2]) - self.bar["rest_z"]
        ok = (all(on) and abs(dx) <= p["support_width_m"] / 2 and abs(dz) <= p["bar_rest_dz_m"]
              and v <= p["bar_still_m_s"] and om <= p["bar_still_rad_s"])
        return dict(ok=bool(ok), on_supports=on, dx_m=round(dx, 4), dz_m=round(dz, 4), speed_m_s=round(v, 3),
                    turn_rad_s=round(om, 3))

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        if ref.has("clearance") and tr["t_land"] is not None:
            if ref.time - max(tr["t_clear"], tr["t_land"]) >= p["bar_wait_s"]:
                bar = self.bar_on_supports(w, ref)
                if not bar.pop("ok"):
                    return ref.fail("the bar did not stay on its supports", **bar)
                if ref.stage("bar stays"):
                    ref.succeed()

    def privileged(self, w):
        tr = self.trackers
        return {"pelvis": w.pelvis().tolist(), "bar": w.pos("bar").tolist(), "bar_top_m": self.p["bar_height_m"],
                "plane_x": self.bar["plane_x"], "phase": tr["phase"], "crossed": list(tr["crossed"]),
                "landed": tr["t_land"] is not None}
