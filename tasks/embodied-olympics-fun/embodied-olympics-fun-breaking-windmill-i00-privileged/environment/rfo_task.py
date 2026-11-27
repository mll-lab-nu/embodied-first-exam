"""Breaking windmill: the power move of breaking (WDSF Breaking, the Olympic programme of Paris 2024): from a stand, go
down to the floor and do consecutive windmills, the body rolling over the upper back, the shoulders and the chest
while the legs, held apart, circle round above the floor.

A windmill revolution is judged on the torso: its long axis (pelvis to neck) turns once round the vertical, and the
torso rolls once about that axis (back, shoulder, chest, shoulder, back on the floor), both the same way round; the
turning is counted only while the body lies on the floor: the long axis near horizontal and the pelvis low (a
heading of a near-vertical axis is ill-defined: a small wobble in a headstand or handstand would sweep through 360
degrees of it). During the set only the torso, the arms and the hands may touch the floor (the shoulders and the
upper back are the torso and the upper arms); the hips and the legs may not; in each half revolution the back, chest
or shoulders (the torso or an upper arm) must touch the floor. The G1's head is fixed to its torso (no neck joint)
and its back face lies 7 mm inside the torso's: on the upper back the head brushes the floor, so a head touch is
allowed, but it is not the back's touch (a head spin is not a windmill).

Robot: the G1 (33 kg, 1.32 m), the lighter and shorter body: a windmill is driven by the swing of the legs (88 N m
hips) round a body lying on its shoulders; the H1-2 has twice the mass and a waist of one joint."""
import math

import numpy as np

from rfo.task import TaskBase

BACK = ("torso", "left_upper_arm", "right_upper_arm")      # the back, chest and shoulders (the upper arms); not the head
ALLOWED = ("torso", "head", "left_upper_arm", "right_upper_arm", "left_forearm", "right_forearm", "left_hand", "right_hand")


def _unwrap(prev, new):
    """The step from angle prev to angle new, wrapped into [-pi, pi)."""
    return (new - prev + math.pi) % (2 * math.pi) - math.pi


class Task(TaskBase):
    name = "breaking-windmill"
    title = "Breaking: windmills"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("WDSF Breaking Rules and Regulations Manual (BRRM, version 4, January 2023, the rules of the Paris "
                "2024 qualification): 2.2 'The elements of Breaking' (power moves: spinning moves driven by "
                "centrifugal force, the windmill family among the most frequent; in a pure power move set the feet "
                "seldom touch the ground); 4.6.4 (judging, the values affecting all domains): 'Crash' (slip, crash, wipe-out: non-intentional "
                "loss of physical control); 7.1 Field of Play: a 'Fast Break System Laminate' floor, at least 6.5 m x 6.5 m, "
                "advised 8.00 m x 8.00 m, a red line on the right side and a blue line on the left side")
    deviations = [
        "BRRM judging (Technique, Vocabulary, Originality, Execution, Musicality, compared head to head in a "
        "battle): a single power move is judged pass or fail: {n_windmills} consecutive windmill revolutions, "
        "because the task is one element without a judging panel or an opponent; the BRRM sets no number of "
        "revolutions, {n_windmills} is this benchmark's choice (a short set)",
        "BRRM 2.2 (a windmill): the BRRM names the move but does not define it; here a revolution is the torso's "
        "long axis turning once round the vertical and the torso rolling once about that axis, both the same way, "
        "counted only while the body lies on the floor (the long axis within {axis_max_deg} degrees of horizontal, "
        "the pelvis at most {pelvis_max_m} m up: a windmill is done on the upper back, not on the head or the "
        "hands), with only the torso (the head included), the arms and the hands on the floor (no hips or legs) and "
        "the back, chest or shoulders (the torso or an upper arm, not the head) touching the floor in each half "
        "revolution",
        "BRRM 7.1 (the laminate floor): the floor is rigid and level; the contact between the robot's shell and the "
        "floor uses the robot model's friction coefficient of 1.0 (no sourced figure for a robot's shell on "
        "laminate exists; breakers wear slippery clothes, the robot wears none: this makes sliding on the back "
        "harder, not easier)",
        "the head: a breaker's chin is tucked and the head stays off the floor in a windmill; the G1 has no neck "
        "joint and its head's back face lies 7 mm inside the torso's, so a head touch is allowed, but only the "
        "torso's or an upper arm's touch counts as the back's, chest's or shoulders'",
        "BRRM crash (a fall in a set is a deduction, not an end): a set is any {n_windmills} consecutive "
        "revolutions; a forbidden contact only ends the current set (the count starts again), and only the time "
        "limit ends the attempt",
    ]
    time_limit_s = 30.0
    start = (0.0, 0.0, 0.0)
    fall_rule = False                        # the family's own rules: the floor is where the move happens
    legal_ground = ALLOWED
    stages = ["down", "1 windmill", "2 windmills", "3 windmills"]
    params = dict(n_windmills=3, fop_m=8.0, roll_frac=0.85, torso_touch=True, axis_max_deg=30.0, pelvis_max_m=0.45)

    sentence = ("Get down on the floor and do three windmills in a row, rolling over your back, shoulders and chest "
                "while your legs circle above the floor.")
    rules = ("A windmill revolution is counted on your torso. Its long axis (from your pelvis up to your neck) must "
             "turn once round the vertical (360 degrees of heading) and in the same time your torso must roll once "
             "about that axis (back, shoulder, chest, shoulder, back towards the floor: at least {roll_frac} of a "
             "full roll per revolution), both the same way round. The turning and the rolling are counted only "
             "while you lie on the floor: your torso's long axis within {axis_max_deg} degrees of horizontal and "
             "your pelvis at most {pelvis_max_m} m above the floor (on your head or your hands, upside down, nothing "
             "is counted). Your back, chest or shoulders (your torso or upper arms; your head does not count for "
             "this) must touch the floor in each half of each revolution. While you are doing windmills only your torso (back, chest, shoulders; your head, which is "
             "fixed to it, counts with it), your upper arms, forearms and hands may touch the floor: your hips and "
             "your legs (thighs, shins, feet) may not. The count starts when you are down (your back, chest or shoulders touching the "
             "floor with no foot on it) and goes back to zero whenever your hips or a leg touch the floor or the rotation reverses. You succeed "
             "when {n_windmills} revolutions are counted without such a reset. How you get down from standing is "
             "free (any part may touch the floor then). You fail if any part of you touches the floor outside the "
             "{fop_m} m x {fop_m} m field of play, or after {time_limit_s} s.")
    venue = ("You stand in the middle of a breaking stage, a {fop_m} m by {fop_m} m laminate floor, flat, level and "
             "rigid, with a red line on its right side and a blue line on its left; you face +x.")
    difficulty = ("A windmill is a continuous rolling and spinning motion on the shoulders with nothing built in for "
                  "any of it, and every revolution loses energy to the floor that has to be put back. You also have "
                  "to get down to the floor from standing first.")

    def build(self, sc):
        h = self.p["fop_m"] / 2
        sc.box("stage", (0.0, 0, 0.0003), (h, h, 0.0003), rgba=(0.62, 0.62, 0.64, 1))
        sc.line("side_red", (-h, -h), (h, -h), rgba=(0.93, 0.11, 0.14, 1), width=0.08)
        sc.line("side_blue", (-h, h), (h, h), rgba=(0.0, 0.35, 0.66, 1), width=0.08)
        sc.camera("venue", (2.2, -2.6, 1.6), (0.0, 0.0, 0.3), fovy=55)

    def referee_reset(self, w, ref):
        self.allowed = ref.part(*ALLOWED)
        self.tb = w.robot.torso
        self.trackers = {"spin": 0.0, "roll": 0.0, "count": 0, "best": 0, "touched": [False, False], "down": False,
                         "phi": None, "psi": None, "lying": False, "rev_spin0": 0.0, "rev_roll0": 0.0,
                         "parts_k": []}                # the parts on the floor during this control step (every 1 ms)

    def angles(self, w):
        R = w.d.xmat[self.tb].reshape(3, 3)
        u, n = R[:, 2], R[:, 0]                       # the torso's long axis, its chest normal
        phi = math.atan2(u[1], u[0])
        e = np.array([0.0, 0.0, 1.0]) - u[2] * u
        ne = float(np.linalg.norm(e))
        if ne < 1e-6:
            return phi, None
        e /= ne
        psi = math.atan2(float(np.cross(u, e) @ n), float(e @ n))
        return phi, psi

    def _reset_set(self, tr):
        tr["count"] = 0
        tr["spin"] = tr["roll"] = 0.0
        tr["rev_spin0"] = tr["rev_roll0"] = 0.0
        tr["touched"] = [False, False]

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        half = p["fop_m"] / 2
        pts = ref.contact_points(ref.robot_mask, ref.ground)       # after every physics step (1 ms)
        if len(pts) and (np.abs(pts[:, :2]) > half + 1e-9).any():
            return ref.fail("outside the field of play")
        now = ref.parts_touching(ref.ground)
        if not now <= set(tr["parts_k"]):
            tr["parts_k"] = sorted(set(tr["parts_k"]) | now)

    def step(self, w, ref):
        p, tr = self.p, self.trackers
        parts, tr["parts_k"] = set(tr["parts_k"]), []
        bad = parts - set(ALLOWED)
        phi, psi = self.angles(w)
        uz = float(w.d.xmat[self.tb].reshape(3, 3)[2, 2])     # the long axis' vertical component
        lying = (abs(uz) < math.sin(math.radians(p["axis_max_deg"]))
                 and float(w.d.xpos[w.robot.pelvis][2]) <= p["pelvis_max_m"])
        if tr["phi"] is not None and psi is not None and tr["psi"] is not None and lying and tr["lying"]:
            tr["spin"] += _unwrap(tr["phi"], phi)    # counted only from one lying step to the next
            tr["roll"] += _unwrap(tr["psi"], psi)
        tr["phi"], tr["psi"], tr["lying"] = phi, psi, lying
        if not tr["down"]:
            if parts & set(BACK) and not bad:
                tr["down"] = True
                ref.stage("down")
                self._reset_set(tr)
            return
        if bad:
            if tr["count"]:
                ref.event("set broken", parts=sorted(bad), revolutions=tr["count"])
            self._reset_set(tr)
            return
        ds, dr = tr["spin"] - tr["rev_spin0"], tr["roll"] - tr["rev_roll0"]
        if parts & set(BACK):                         # the back, chest or shoulders down, in this half revolution
            tr["touched"][0 if abs(ds) < math.pi else 1] = True
        if ds * dr < 0 and abs(ds) > math.pi / 2 and abs(dr) > math.pi / 2:
            self._reset_set(tr)                       # spinning one way and rolling the other: not a windmill
            return
        if abs(ds) >= 2 * math.pi:
            if abs(dr) >= p["roll_frac"] * 2 * math.pi and ds * dr > 0 and (all(tr["touched"]) or not p["torso_touch"]):
                if tr["count"] and math.copysign(1, ds) != tr.get("dir", math.copysign(1, ds)):
                    self._reset_set(tr)
                    return
                tr["dir"] = math.copysign(1, ds)
                tr["count"] += 1
                tr["best"] = max(tr["best"], tr["count"])
                ref.metrics["windmills"] = tr["best"]
                ref.event("windmill", n=tr["count"], spin_deg=round(math.degrees(ds), 1),
                          roll_deg=round(math.degrees(dr), 1))
                ref.stage(f"{min(tr['count'], 3)} windmill" + ("s" if tr["count"] > 1 else ""))
                if tr["count"] >= p["n_windmills"] and len(ref.stages) == len(self.stages):
                    ref.succeed()
            else:
                self._reset_set(tr)
                return
            tr["rev_spin0"], tr["rev_roll0"] = tr["spin"], tr["roll"]
            tr["touched"] = [False, False]

    def privileged(self, w):
        tr = self.trackers
        return {"pelvis": w.pelvis().tolist(), "torso_heading_deg": None if tr.get("phi") is None else math.degrees(tr["phi"]),
                "spin_deg": math.degrees(tr.get("spin", 0.0)), "roll_deg": math.degrees(tr.get("roll", 0.0)),
                "count": tr.get("count", 0), "down": tr.get("down", False)}
