"""Taekwondo: one scoring kick to the trunk protector (World Taekwondo, PSS electronic scoring) of a free-standing
body-opponent dummy, then land and stay standing. The Unitree G1 in the cadet male -33 kg division."""
import math

import mujoco
import numpy as np

from rfo.scene import HITTABLE, VISUAL
from rfo.task import TaskBase
# A rigid dummy's plastic base and stem (the foam torso and the hogu keep theirs)'s contact with the robot, the
# venue's fixtures and the other props (the ground keeps its own: rfo/world.py GROUND_SOLMIX): the stiff contact of
# the core's shells (rfo/world.py SHELL_CONTACT: solref 0.004 s, solimp 0.99 0.999 0.0005, from roboolympics'
# weightlifting fix, a rigid prop on the robot's aluminium) with a solmix that wins over a default-contact geom; a
# ball (priority 1) keeps its own bounce. With MuJoCo's default soft contact (solref 0.02 1, solimp 0.9 0.95) it sank
# 53 mm into a foot (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402

MAT = (0.20, 0.35, 0.65, 1)
MAT_RED = (0.75, 0.20, 0.20, 1)
SKIN = (0.85, 0.70, 0.55, 1)
BASE = (0.12, 0.12, 0.13, 1)
HOGU = (0.15, 0.25, 0.75, 1)          # a chung (blue) protector


def contact_impulse(w, A: np.ndarray, B: np.ndarray) -> float:
    """The normal contact force between selectors A and B now, times the physics step (N s): what an impact sensor
    behind the contact surface integrates."""
    m, d = w.m, w.d
    f, out = np.zeros(6), 0.0
    for i in range(d.ncon):
        c = d.contact[i]
        g1, g2 = int(c.geom[0]), int(c.geom[1])
        if (A[g1] and B[g2]) or (A[g2] and B[g1]):
            mujoco.mj_contactForce(m, d, i, f)
            out += float(f[0])
    return out * m.opt.timestep


class Task(TaskBase):
    name = "taekwondo-kick"
    title = "Taekwondo: a scoring kick to the trunk protector"
    category = "throwing-catching-striking"
    robot = "unitree_g1"
    rulebook = ("World Taekwondo Competition Rules & Interpretation (2024): Article 5 (weight divisions: cadet male "
                "-33 kg, the robot's 33 kg), Article 11 (permitted techniques: a foot technique delivered with any "
                "part of the foot below the ankle bone; permitted area: the trunk, the area covered by the trunk "
                "protector), Article 12 (valid points: a valid kick to the trunk protector scores; the Protector and "
                "Scoring System "
                "(PSS) decides validity by the level of impact, set per weight division and gender), Article 21 "
                "(prohibited acts: falling down is a penalty)")
    deviations = [
        "Article 12 (the PSS level): WT sets the impact level per division in its PSS's own units (KP&P men's "
        "levels 18-25 from -58 kg to +80 kg, Choi, Oh and Jeon 2021, BMC Sports Sci Med Rehabil 13:110); no "
        "conversion to physical units is published, nor a cadet level. The referee measures the impulse the "
        "protector receives during the kick and requires {min_impulse_n_s} N s: the mean minus one standard "
        "deviation of elite adult roundhouse kicks on an electronic protector (19.8 +- 4.5 N s input impulse, "
        "Chae et al. 2026, PLoS One 21:e0328749; athletes of 70 kg) scaled to a 33 kg athlete by body mass (a "
        "kick's impulse is its striking leg's momentum, which scales with body mass).",
        "Article 12 (an impact, not a push): a PSS registers impacts; here a touch may last at most "
        "{max_contact_s} s, about twice an elite kick's 0.026 s on a protector (Chae et al. 2026): a longer "
        "touch is a push.",
        "No opponent and no bout: the target is a free-standing body-opponent dummy (Century BOB at its lowest "
        "setting, {dummy_h_m} m tall; its base filled with sand, about {base_kg} kg, {base_d_m} m across) wearing a "
        "trunk protector from {hogu_low_m} m to {hogu_high_m} m above the floor, {hogu_w_m} m wide: the height of "
        "a cadet's protector. One kick, then stand: a single action, not a round.",
        "The protector's padding: its contact lasts as long as a measured kick's (half an oscillation of "
        "{hogu_contact_s} s, Chae et al. 2026) with a damping ratio of {hogu_damping} (an estimate: the foam "
        "absorbs most of a kick's energy); the dummy is one rigid body (BOB's stem and plastisol torso do not "
        "bend). The floor is rigid, not a foam mat.",
        "Article 11 (below the ankle bone): the foot is the robot's ankle-roll link; its lower-leg collision hull "
        "covers the top of the foot, so a contact with that hull counts as the foot only over the foot (from "
        "{heel_x_m} m behind to {toe_x_m} m ahead of the ankle joint) and not above the ankle joint.",
    ]
    time_limit_s = 15.0
    start = (0.0, 0.0, 0.0)
    stages = ["kick", "stand"]
    fall_z = 0.35
    params = dict(dummy_distance_m=0.58, dummy_h_m=1.52, base_kg=122.0, base_d_m=0.61, base_h_m=0.50, base_mu=0.5,
                  torso_w_m=0.36, torso_d_m=0.22, torso_low_m=0.74, torso_kg=8.0, hogu_low_m=0.78, hogu_high_m=1.12,
                  hogu_w_m=0.32, hogu_t_m=0.04, hogu_contact_s=0.026, hogu_damping=0.5, min_impulse_n_s=7.2,
                  max_contact_s=0.05, touch_gap_s=0.03, stand_s=2.0, heel_x_m=0.08, toe_x_m=0.15, fall_z_m=0.35)

    sentence = ("Kick the trunk protector of the dummy in front of you once with a foot, hard enough to score, then "
                "land and stand still for {stand_s} s.")
    rules = ("A body-opponent dummy stands free on the floor in front of you: a heavy round base ({base_d_m} m across, "
             "{base_h_m} m high, {base_kg} kg, friction {base_mu} on the floor) carrying on a stem a torso "
             "({torso_w_m} m wide, {torso_d_m} m deep, from {torso_low_m} m up, {torso_kg} kg) and a head, "
             "{dummy_h_m} m tall in all, one rigid body. Its torso wears a taekwondo trunk protector, {hogu_w_m} m "
             "wide and {hogu_t_m} m thick, from {hogu_low_m} m to {hogu_high_m} m above the floor, facing you; the "
             "front of the protector is {dummy_distance_m} m in front of your pelvis. Your "
             "first touch of the dummy is your kick: it must be made with a foot (the part below the ankle; your "
             "lower leg counts only where it lies over the foot and below the ankle joint) and must land on the "
             "protector. It is an impact, not a push: the touch lasts at most {max_contact_s} s (it ends when foot and "
             "dummy have been apart for {touch_gap_s} s), and during it the protector must receive an impulse of at "
             "least {min_impulse_n_s} N s (the sum of the contact forces on it over the touch). After a valid kick "
             "you succeed when you stand for {stand_s} s without a break, clear of the dummy: both feet and nothing "
             "else on the floor, the torso within about 20 degrees of upright, the pelvis slower than 0.35 m/s. "
             "You fail if any other "
             "part of you touches the dummy, if the kick lands anywhere but on the protector, is too weak or is a "
             "push, if after the kick any part of you other than a foot touches the dummy (a foot may touch it again "
             "but scores nothing more), if you fall (your pelvis lower than {fall_z_m} m "
             "above the floor, or any part of you other than the feet on the floor), or after {time_limit_s} s.")
    venue = ("You stand on the mat facing the dummy (+x); the front of its protector is {dummy_distance_m} m in front "
             "of your pelvis, centred on you, from {hogu_low_m} m to {hogu_high_m} m high (above your hips).")
    difficulty = ("The protector is above the robot's hip joints: the foot has to rise above hip height, fast, while "
                  "the other leg alone carries the 33 kg body; the robot has no kicking or one-leg balance skill, "
                  "and the protector's push back and the leg's swing both throw the body off its standing foot "
                  "before it has to come down on both feet and stand.")

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_z_m"]

    def geometry(self):
        p = self.p
        front = p["dummy_distance_m"]                       # the protector's front face
        cx = front + p["hogu_t_m"] + p["torso_d_m"] / 2      # the dummy's axis
        return dict(front_x=front, axis_x=cx)

    def build(self, sc):
        p, g = self.p, self.geometry()
        self.fall_z = p["fall_z_m"]
        sc.box("mat", (0.5, 0, 0.0003), (4.0, 4.0, 0.0003), rgba=MAT)
        sc.box("mat_inner", (0.5, 0, 0.0006), (2.0, 2.0, 0.0003), rgba=MAT_RED)
        # The dummy (Century BOB: 60-78 in tall in seven settings, the base 24 in across and 19.5 in high, about 270
        # lb filled with sand; listings at academy.com and bytomic.com): one free body on the floor.
        b = sc.body("dummy", (g["axis_x"], 0.0, 0.0), free=True)
        sc.geom(b, "dummy_base", type="cylinder", pos=(0, 0, p["base_h_m"] / 2),
                size=(p["base_d_m"] / 2, p["base_h_m"] / 2),
                mass=p["base_kg"], rgba=BASE, friction=(p["base_mu"], 0.005, 0.0001), **HITTABLE, **RIGID)
        stem_h = p["torso_low_m"] - p["base_h_m"]
        sc.geom(b, "dummy_stem", type="cylinder", pos=(0, 0, p["base_h_m"] + stem_h / 2), size=(0.04, stem_h / 2),
                mass=1.5, rgba=BASE, **HITTABLE, **RIGID)
        top = p["dummy_h_m"] - 0.24
        th = top - p["torso_low_m"]
        sc.geom(b, "dummy_torso", type="box", pos=(0, 0, p["torso_low_m"] + th / 2),
                size=(p["torso_d_m"] / 2, p["torso_w_m"] / 2, th / 2), mass=p["torso_kg"], rgba=SKIN, **HITTABLE)
        sc.geom(b, "dummy_head", type="sphere", pos=(0, 0, p["dummy_h_m"] - 0.11), size=(0.11,), mass=1.5, rgba=SKIN,
                **HITTABLE)
        # the trunk protector on the torso's front: its padding's contact (priority: its parameters win)
        w_ = 2 * math.pi / (2 * p["hogu_contact_s"])           # half an oscillation in hogu_contact_s
        z = p["hogu_damping"]
        hh = (p["hogu_high_m"] - p["hogu_low_m"]) / 2
        sc.geom(b, "hogu", type="box", pos=(-p["torso_d_m"] / 2 - p["hogu_t_m"] / 2, 0, p["hogu_low_m"] + hh),
                size=(p["hogu_t_m"] / 2, p["hogu_w_m"] / 2, hh), mass=0.8, rgba=HOGU, priority=2,
                solref=f"{-w_ * w_:.6g} {-2 * z * w_:.6g}", solimp="0.9 0.99 0.005", friction=(0.6, 0.005, 0.0001),
                **HITTABLE)
        sc.geom(b, "hogu_mark", type="cylinder",
                pos=(-p["torso_d_m"] / 2 - p["hogu_t_m"] - 0.001, 0, p["hogu_low_m"] + hh),
                quat=(math.cos(math.pi / 4), 0, math.sin(math.pi / 4), 0), size=(0.07, 0.001), rgba=(1, 1, 1, 1),
                mass=0, **VISUAL)
        sc.camera("venue", (-0.8, -2.6, 1.5), (0.45, 0.0, 0.8), fovy=50)

    def reset(self, w):
        w.put("dummy", (self.geometry()["axis_x"], 0.0, 0.0))

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        self.dummy = ref.geoms(body="dummy")
        self.hogu = ref.geoms(names=["hogu"])
        self.robot = ref.part("robot")
        self.feet = ref.part("feet")
        self.shin = {s: ref.part(f"{s}_shin") for s in ("left", "right")}
        self.foot_body = {s: w.m.body(f"{s}_ankle_roll_link").id for s in ("left", "right")}
        self.other = self.robot & ~self.feet & ~ref.part("shins")
        self.trackers = {"t0": None, "t_last": None, "impulse": 0.0, "judged": False, "peak_n": 0.0}

    def _foot_ok(self, w, ref):
        """No contact of the lower-leg hull with the dummy above the ankle joint or outside the foot's length."""
        p = self.p
        for s in ("left", "right"):
            pts = ref.contact_points(self.dummy, self.shin[s])
            if len(pts):
                b = self.foot_body[s]
                loc = (pts - w.d.xpos[b]) @ w.d.xmat[b].reshape(3, 3)
                bad = (loc[:, 2] > 0.0) | (loc[:, 0] < -p["heel_x_m"]) | (loc[:, 0] > p["toe_x_m"])
                if np.any(bad):
                    return False, f"{s}_shin"
        return True, None

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        touch = ref.touching(self.dummy, self.robot)
        if tr["judged"]:                                       # after the kick: a foot may touch it again (no
            if ref.touching(self.dummy, self.other):           # second point), anything else is a push
                ref.fail("the dummy was pushed after the kick", parts=sorted(ref.parts_touching(self.dummy)))
            return
        if touch:
            if ref.touching(self.dummy, self.other):
                return ref.fail("the dummy was touched by something other than a foot",
                                parts=sorted(ref.parts_touching(self.dummy)))
            ok, part = self._foot_ok(w, ref)
            if not ok:
                return ref.fail("the dummy was touched by something other than a foot", parts=[part])
            if ref.touching(self.dummy & ~self.hogu, self.robot):
                return ref.fail("the kick landed outside the trunk protector",
                                parts=sorted(ref.parts_touching(self.dummy & ~self.hogu)))
            if tr["t0"] is None:
                tr["t0"] = ref.time
            tr["t_last"] = ref.time
            J = contact_impulse(w, self.robot, self.hogu)
            tr["impulse"] += J
            tr["peak_n"] = max(tr["peak_n"], J / w.m.opt.timestep)
            if ref.time - tr["t0"] > p["max_contact_s"]:
                tr["judged"] = True
                return ref.fail("the protector was pushed, not struck", contact_s=round(ref.time - tr["t0"], 3))
        elif tr["t0"] is not None and ref.time - tr["t_last"] >= p["touch_gap_s"]:
            tr["judged"] = True
            ref.metrics["impulse_n_s"] = round(tr["impulse"], 2)
            ref.metrics["peak_force_n"] = round(tr["peak_n"], 1)
            ref.metrics["contact_s"] = round(tr["t_last"] - tr["t0"], 3)
            if tr["impulse"] < p["min_impulse_n_s"]:
                ref.fail("the kick was too weak to score", impulse_n_s=round(tr["impulse"], 2))
            else:
                ref.stage("kick", impulse_n_s=round(tr["impulse"], 2))

    def step(self, w, ref):
        if not ref.has("kick"):
            return
        both = ref.parts_touching(ref.ground) == {"left_foot", "right_foot"}
        free = not ref.touching(self.dummy, self.robot)        # standing on the feet alone, not against the dummy
        if ref.hold("stand", both and free and ref.standing(), self.p["stand_s"]):
            if ref.stage("stand"):
                ref.succeed()

    def privileged(self, w):
        p, g = self.p, self.geometry()
        return {"dummy": w.pos("dummy").tolist(), "dummy_quat": w.d.xquat[w.m.body("dummy").id].tolist(),
                "protector_front_x_at_start": g["front_x"], "protector_z": [p["hogu_low_m"], p["hogu_high_m"]],
                "protector_half_width": p["hogu_w_m"] / 2, "impulse_so_far_n_s": self.trackers.get("impulse", 0.0)}
