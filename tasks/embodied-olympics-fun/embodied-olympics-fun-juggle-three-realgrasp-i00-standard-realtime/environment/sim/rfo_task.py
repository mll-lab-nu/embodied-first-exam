"""Juggle three balls with real grasping: juggle-three's three-ball cascade (two balls in one hand, one in the other at
the start; each ball thrown from one hand in an arc to the other; ten catches in a row in the cascade's order, no ball
on the ground), but both hands of the Unitree G1 are Unitree Dex1-1 two-jaw grippers and nothing is welded: a catch
is the jaws of a gripper closing on the ball (70 mm: it fits the 90 mm stroke), a ball is thrown by opening the jaws
and moving the hand, and a ball in a hand is held only by the pads' friction and the gripper it rests on.

Everything but the hold is juggle-three's (shared/rfo/tasks/juggle_three.py, copied: the balls, the cascade's order,
the venue's first throw of the second ball of the right hand, the flight rules and their numbers); what is new: the
real grippers (rfo/realhand.py, sold for the G1), a start pose whose jaws point up (a cup), the catch as a clamp of
both jaws' pads held for clamp_s, the release as the ball leaving the gripper, and the rule that a ball in a hand
touches nothing of you but that gripper."""
import math

import mujoco
import numpy as np

from rfo.task import TaskBase

BALLS = ("ball_a", "ball_b", "ball_c")         # the order in which they are caught: a, b, c, a, ...
COLOURS = ((0.90, 0.20, 0.20, 1), (0.20, 0.55, 0.90, 1), (0.95, 0.80, 0.15, 1))
OTHER = {"left": "right", "right": "left"}
SIDES = ("left", "right")
G = 9.81
# the start pose: forearms forward, a little below level, the wrists turned so that the jaws point up and close
# across the body (left-right); the jaw centres about 0.24 m in front of the pelvis, 0.37 m apart, 1.08 m high
# (found by a search over the arm's joints: the jaw axis within 2 degrees of vertical)
CUP = {"right": dict(right_shoulder_pitch=-0.207, right_shoulder_roll=-0.04, right_shoulder_yaw=-0.218,
                     right_elbow=0.198, right_wrist_roll=-1.565, right_wrist_pitch=-0.163, right_wrist_yaw=-1.534),
       "left": dict(left_shoulder_pitch=-0.228, left_shoulder_roll=-0.056, left_shoulder_yaw=0.39,
                    left_elbow=0.181, left_wrist_roll=-1.45, left_wrist_pitch=0.309, left_wrist_yaw=-1.534)}


def set_arm(w, **angles) -> None:
    """Put arm joints (names without "_joint") at angles for t = 0, and their held targets with them."""
    r, d = w.robot, w.d
    for name, v in angles.items():
        i = w.L.JOINTS.index(name + "_joint")
        d.qpos[r.qadr[i]] = v
        r.arb.q_a[i] = r.arb.q_b[i] = v
    mujoco.mj_kinematics(w.m, d)


def pinched(w, ball: int, pads, centre: int, cos_max: float) -> bool:
    """Both jaws' pads (two geom masks) touch the geom `ball` with a contact normal within acos(cos_max) of the
    closing axis of the jaw frame (the site `centre`), in this physics step's contacts."""
    d = w.d
    n = d.ncon
    g = d.contact.geom[:n]
    keep = d.contact.dist[:n] <= 0.0
    x = d.site_xmat[centre].reshape(3, 3)[:, 0]
    for pad in pads:
        sel = keep & (((g[:, 0] == ball) & pad[g[:, 1]]) | ((g[:, 1] == ball) & pad[g[:, 0]]))
        if not np.any(np.abs(d.contact.frame[:n][sel, :3] @ x) >= cos_max):
            return False
    return True


class Task(TaskBase):
    name = "juggle-three-realgrasp"
    title = "Juggling: a three-ball cascade, real grasp"
    category = "throwing-catching-striking"
    robot = "unitree_g1"
    rulebook = ("No rule book: the three-ball cascade as jugglers define and count it (siteswap 3; the International "
                "Jugglers' Association counts a run in catches): each ball is thrown from one hand and caught by the "
                "other, the hands throw in turn, the balls follow one another in a fixed order; a run ends with a "
                "drop")
    deviations = [
        "The hands are Unitree's Dex1-1 two-jaw grippers (90 mm stroke, jaws 80 mm long and 34 mm wide with rubber "
        "pads, at most 120 N of grip, opening and closing at most 375 mm/s); nothing is welded. A gripper holds one "
        "ball between its jaws, so \"two balls in one hand at the start\" is modelled: the first of the two (the red "
        "ball) waits {waiting_above_jaws_m} m above the right gripper's jaw centre and is thrown by the venue at "
        "t = {launch_time_s} s, on an arc that rises {first_throw_rise_m} m and comes down on where the left "
        "gripper's jaw centre is at the start. Until then it may not be touched.",
        "A catch is the pads of both jaws of the catching gripper pressing on the ball from its two sides (each with "
        "a contact within {max_contact_angle_deg} degrees of the jaws' closing direction) for {clamp_s} s without a "
        "break, the clamp beginning at the latest {catch_window_s} s after the ball first touched you again; a ball "
        "is in a hand from its catch until it has touched nothing of that gripper for {release_s} s (released, at its "
        "last contact: a ball that rattles in the jaws is not released), and it may touch nothing of you but that "
        "gripper.",
        "A throw is a release after which the ball, touching nothing, rises at least {min_rise_m} m above where it "
        "left the gripper; a hand-to-hand pass is not a throw. So that a ball laid on the other hand and lifted is "
        "not one, the rise counts only until the ball first touches you again.",
        "The balls are spheres of a juggling ball's size and mass with a soft bounce; they fly in air (MuJoCo's "
        "ellipsoid fluid model: drag, a quasi-steady model), still air.",
    ]
    time_limit_s = 20.0
    start = (0.0, 0.0, 0.0)
    stages = ["first catch", "half way", "ten catches"]
    params = dict(ball_diameter_m=0.07, ball_mass_kg=0.13, catches=10, min_rise_m=0.30, launch_time_s=2.0,
                  first_throw_rise_m=0.50, waiting_above_jaws_m=0.16, retouch_grace_s=0.10, catch_window_s=0.15,
                  clamp_s=0.05, release_s=0.02, max_contact_angle_deg=45.0, fall_pelvis_m=0.35)

    sentence = ("Juggle three balls in a cascade: throw each ball from one gripper in an arc to the other, the hands in "
                "turn, catching each between the jaws, until {catches} catches have been made in a row.")
    rules = ("Three balls ({ball_diameter_m} m across, {ball_mass_kg} kg). Both your hands are two-jaw grippers (90 mm "
             "stroke, jaws 80 mm long with rubber pads on their inner faces, at most 120 N of grip) that hold things "
             "only by friction. At the start your forearms point forwards and your grippers' jaws point up; the blue "
             "ball is held between the jaws of your left gripper, the yellow ball between those of your right "
             "gripper, and the red ball waits {waiting_above_jaws_m} m above the centre of your right gripper's jaws: "
             "it stands for the second ball of the right hand and is thrown for you at t = {launch_time_s} s, on an "
             "arc that rises {first_throw_rise_m} m and comes down on where the centre of your left gripper's jaws "
             "is at the start. Before that it may not be touched (by you or by a ball you hold). A catch: the pads of "
             "both jaws of a gripper press on a ball from its two sides (each with a contact whose direction is "
             "within {max_contact_angle_deg} degrees of the jaws' closing direction: a ball lying on the jaws' tips "
             "or edges is not caught) for {clamp_s} s without a break, on a ball that has been thrown by the other "
             "hand (the red ball's first throw counts as the right hand's), the clamp beginning at the latest "
             "{catch_window_s} s after the ball first touched you again. A ball is in a hand from its catch (the "
             "blue and the yellow ball from the start) until it has touched nothing of that gripper for {release_s} s: "
             "its release, at its last contact with the gripper; "
             "a ball in a hand may touch nothing of you but that gripper. A throw: after the release the ball, "
             "touching nothing but air, rises at least {min_rise_m} m above the point where it left the gripper; "
             "only the rise before the ball first touches you again counts. The cascade's order: the catches "
             "alternate between the hands, the left hand first, and take the balls in the order red, blue, yellow, "
             "red, ... You succeed at the {catches}th catch. You fail if a ball touches the ground; if a ball in a "
             "hand touches any part of you other than that gripper (the other gripper included); if a ball in flight "
             "touches any part of you other than a gripper, or still touches the gripper that released it later than "
             "{retouch_grace_s} s after the release; if a ball is caught by the gripper that released it, or before "
             "it has risen {min_rise_m} m; if a ball that has touched a gripper again is not clamped within "
             "{catch_window_s} s (it rests on the gripper or bounces off it); if a catch is out of the cascade's "
             "order (the wrong hand or the wrong ball); if the waiting ball is touched before its launch; if you fall "
             "(your pelvis lower than {fall_pelvis_m} m above the ground, or any part of you other than your feet on "
             "the ground); or after {time_limit_s} s.")
    venue = ("You stand on level ground, nothing around you. Your forearms point forwards, the grippers' jaws point up "
             "and close across your body (left-right), their centres about 0.37 m apart and 1.1 m above the ground; a "
             "ball is held between the jaws of each, and the red ball hangs above the yellow one over your right "
             "gripper until it is thrown towards your left gripper. A gripper's closure command closes its jaws; "
             "with them open, a ball rests on the gripper's housing between the jaws.")
    difficulty = ("Each throw has to come down between jaws that leave 10 mm on each side of the ball, 0.4 m away, "
                  "about 0.6 s later, the jaws must close on it within a few hundredths of a second before it "
                  "bounces off, and the catching gripper must have thrown its own ball before: three balls, two "
                  "hands, never two in one. A throw is the gripper opening while the arm moves, and errors add up "
                  "from throw to throw, because a ball is thrown from wherever it was caught.")

    def build(self, sc):
        p = self.p
        self.fall_z = p["fall_pelvis_m"]
        sc.real_hands["left"] = sc.real_hands["right"] = "dex1"
        sc.box("mat", (0.2, 0, 0.0003), (1.2, 1.2, 0.0003), rgba=(0.25, 0.35, 0.55, 1))
        for name, rgba in zip(BALLS, COLOURS):           # nothing grippable: held only by the jaws' friction
            sc.ball(name, "baseball", (0.3, 0.0, 0.5), radius=p["ball_diameter_m"] / 2, mass=p["ball_mass_kg"],
                    bounce=0.30, drag=0.47, rgba=rgba)
        sc.camera("venue", (2.1, -1.6, 1.4), (0.15, 0.0, 0.95), fovy=50)

    def reset(self, w):
        p = self.p
        set_arm(w, **CUP["left"], **CUP["right"])
        centres = {}
        for side, name in (("left", "ball_b"), ("right", "ball_c")):
            c, _ = w.jaw_frame(side)
            w.put(name, c)
            w.close_on(side, name, closure=1.0)
            centres[side] = w.jaw_frame(side)[0]
        # the red ball's launch: from above the right jaws to the left jaws' centre, over an apex first_throw_rise_m up
        p0 = centres["right"] + [0.0, 0.0, p["waiting_above_jaws_m"]]
        target = centres["left"]
        vz = math.sqrt(2 * G * p["first_throw_rise_m"])
        T = (vz + math.sqrt(vz * vz + 2 * G * max(float(p0[2] - target[2]), 0.0))) / G
        self.launch = (p0.copy(), np.array([(target[0] - p0[0]) / T, (target[1] - p0[1]) / T, vz]))
        w.pin("ball_a", p0)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        self.geom = {n: ref.geoms(body=n) for n in BALLS}
        self.gid = {n: w.m.geom(n).id for n in BALLS}
        self.robot = ref.part("robot")
        self.hands = {s: ref.part(f"{s}_hand") for s in SIDES}
        self.not_hands = self.robot & ~ref.part("hands")
        self.not_hand = {s: self.robot & ~self.hands[s] for s in SIDES}
        self.pads = {s: (ref.geoms(prefix=f"{s}_hand_pad_a"), ref.geoms(prefix=f"{s}_hand_pad_b")) for s in SIDES}
        self.cos_max = math.cos(math.radians(self.p["max_contact_angle_deg"]))
        # per ball: where it is ("waiting", "held", "flight"), who holds or released it, the release height and time,
        # its rise, when it met you again, when the clamp by the other hand began
        def ball(at, by):
            z = float(w.pos(f"ball_{'bc'[SIDES.index(by)]}")[2]) if at == "held" else 0.0
            return {"at": at, "by": by, "z0": z, "t0": 0.0, "rise": 0.0, "met": None, "clamp": None}
        self.trackers = {"launched": False, "catches": 0, "ball_a": ball("waiting", "right"),
                         "ball_b": ball("held", "left"), "ball_c": ball("held", "right")}

    def clamped(self, w, ref, name, side) -> bool:
        a, b = self.pads[side]
        g = self.geom[name]
        if not (ref.touching(g, a) and ref.touching(g, b)):
            return False
        return pinched(w, self.gid[name], (a, b), w.hands.centre[side], self.cos_max)

    def before_step(self, w):
        tr = self.trackers
        if not tr["launched"] and w.t >= self.p["launch_time_s"] - 1e-9:
            tr["launched"] = True
            pos, vel = self.launch
            w.launch("ball_a", pos, vel)
            tr["ball_a"].update(at="flight", by="right", z0=float(pos[2]), t0=w.ref.time, rise=0.0, met=None,
                                clamp=None)
            w.ref.event("launch", ball="ball_a")

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        for name in BALLS:
            st, g = tr[name], self.geom[name]
            if st["at"] == "waiting":
                if ref.touching(g, ~g):
                    return ref.fail("the waiting ball was touched before its launch")
                continue
            if ref.touching(g, ref.ground):
                return ref.fail("a ball touched the ground", ball=name)
            z = float(w.d.xpos[w.m.geom_bodyid[self.gid[name]]][2])
            by = st["by"]
            if st["at"] == "held":
                if ref.touching(g, self.not_hand[by]):
                    return ref.fail("a ball in a hand touched another part of you", ball=name, hand=by,
                                    parts=sorted(ref.parts_touching(g) - {f"{by}_hand"}))
                if ref.touching(g, self.hands[by]):
                    st.update(t0=round(ref.time, 4), z0=z)    # (its last contact with the gripper)
                elif ref.time - st["t0"] >= p["release_s"] - 1e-9:   # away from it for release_s: the release, at
                    st.update(at="flight", rise=0.0, met=None, clamp=None)   # its last contact: a throw begins
                    ref.event("release", ball=name, hand=by, at_t=st["t0"])
                continue
            # in flight
            if ref.touching(g, self.not_hands):
                return ref.fail("a ball in flight touched the body", ball=name,
                                parts=sorted(ref.parts_touching(g) - {"left_hand", "right_hand"}))
            if self.clamped(w, ref, name, by):
                return ref.fail("a ball was caught by the gripper that released it", ball=name, hand=by)
            if ref.time - st["t0"] > p["retouch_grace_s"] and ref.touching(g, self.hands[by]):
                return ref.fail("a ball in flight was touched again by the gripper that released it", ball=name)
            # met: when the ball first touched you again (after the release's grace): its flight is over
            if st["met"] is None:
                if not ref.touching(g, self.robot):
                    st["rise"] = max(st["rise"], z - st["z0"])
                elif ref.time - st["t0"] > p["retouch_grace_s"]:
                    st["met"] = round(ref.time, 4)
            hand = OTHER[by]
            if self.clamped(w, ref, name, hand):
                if st["clamp"] is None:
                    st["clamp"] = round(ref.time, 4)
                if ref.time - st["clamp"] < p["clamp_s"] - 1e-9:
                    continue
                k = tr["catches"] + 1                          # the clamp has lasted clamp_s: a catch
                if st["rise"] < p["min_rise_m"]:
                    return ref.fail("a ball was caught before it had made its flight", ball=name,
                                    rise_m=round(st["rise"], 3))
                if name != BALLS[(k - 1) % 3] or hand != ("left" if k % 2 else "right"):
                    return ref.fail("a catch out of the cascade's order", ball=name, hand=hand, catch=k)
                tr["catches"] = k
                st.update(at="held", by=hand, t0=round(ref.time, 4), z0=z)
                ref.event("catch", n=k, ball=name, hand=hand, rise_m=round(st["rise"], 3))
                ref.metrics["catches"] = k
                if k == 1:
                    ref.stage("first catch")
                if k == (p["catches"] + 1) // 2:
                    ref.stage("half way")
                if k == p["catches"] and ref.stage("ten catches"):
                    ref.succeed()
                continue
            st["clamp"] = None
            if st["met"] is not None and ref.time - st["met"] > p["catch_window_s"]:
                return ref.fail("a ball that came down on a gripper was not caught", ball=name,
                                rise_m=round(st["rise"], 3))

    def privileged(self, w):
        tr = self.trackers
        pos, vel = self.launch
        return {"balls": {n: {"position": w.pos(n).tolist(), "velocity": w.vel(n).tolist(), "held_by": w.holder(n),
                              "state": tr[n]["at"], "by": tr[n]["by"]} for n in BALLS},
                "catches": tr["catches"], "next_ball": BALLS[tr["catches"] % 3],
                "next_hand": "left" if (tr["catches"] + 1) % 2 else "right",
                "launch_time_s": self.p["launch_time_s"], "launch_position": pos.tolist(), "launch_velocity": vel.tolist(),
                "grippers": w.hands.state() if w.hands else {}}
