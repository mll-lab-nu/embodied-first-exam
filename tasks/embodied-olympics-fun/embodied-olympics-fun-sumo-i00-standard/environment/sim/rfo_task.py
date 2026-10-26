"""Sumo: one bout on a dohyo against a second, physical robot. Win by forcing the opponent out of the ring or
making any part of it other than the soles of its feet touch the ground, before you do.

The opponent is a second Unitree G1 from the same robot library (its own free base, its own motors with their
torque-speed curves, Unitree's walking policy on its legs, the library's joint arbiter on its arms), mounted into
the venue by this module. Its policy is scripted: from the tachiai it walks at the walking policy's largest forward
command straight at the robot, turning to keep facing it, both arms stretched forward at chest height (oshi-zumo,
the pushing style). It acts only through its motors: nothing writes its pose or velocity after t = 0."""
import importlib
import math

import numpy as np

from rfo.task import TaskBase
from rfo.referee import PART_OF_BODY, CENTRAL

OPP = "opp_"                     # the opponent's name prefix in the model
SIDES = ("left", "right")
LOSS, ON_CLAY, TOUCH, KICK = 1, 2, 4, 8          # what a contact means (Task.table)
# the opponent's push pose of each arm (shoulder pitch, roll, yaw, elbow, wrist roll, pitch, yaw), rad: the arms
# forward at chest height, elbows a little bent (the walking policy's rest pose has the upper arms down)
PUSH_ARM = {"left": (-1.25, 0.25, 0.0, 0.35, 0.0, 0.0, 0.0), "right": (-1.25, -0.25, 0.0, 0.35, 0.0, 0.0, 0.0)}


class _Opponent:
    """The opponent's controller memory for the state hash (the arbiter's, as World hashes the robot's)."""

    def __init__(self, arb, stage):
        self.arb, self.stage = arb, stage

    def state(self):
        a = self.arb
        ho, st = a.ho or {}, a.settle or {}
        extra = np.r_[ho.get("i", -1), ho.get("n", -1), st.get("i", -1), np.asarray(st.get("w", []), float).ravel()]
        return [np.round(a.memory(), 12).tolist(), extra.tolist(), self.stage[0], a.act.tau.tolist()]


class Task(TaskBase):
    name = "sumo"
    title = "Sumo (one bout against a pushing robot)"
    category = "throwing-catching-striking"
    robot = "unitree_g1"
    rulebook = ("Japan Sumo Association, the rules of professional sumo (honzumo): the dohyo (the ring of "
                "{ring_diameter_m} m inside the shobu-dawara bales on a raised clay mound, the two shikiri-sen "
                "starting lines {shikiri_len_m} m long, {shikiri_width_m} m wide and {shikiri_gap_m} m apart); the "
                "decision (kimarite / shobu-dawara rules): a wrestler loses when any part of his body touches the "
                "ground outside the ring, or any part other than the soles of his feet touches the ground inside it, "
                "first; forbidden techniques (kinjite) lose the bout (among them striking with a closed fist and "
                "kicking the chest or stomach); there are no weight classes")
    deviations = [
        "the opponent: a second Unitree G1 with a scripted policy, not a wrestler: from t = {opp_start_s} s it "
        "walks at the walking policy's largest forward command ({opp_vx} m/s commanded) straight at you, turning "
        "(at most {opp_wz_max} rad/s) to face your pelvis, both arms stretched forward at chest height; it never "
        "grips, never changes its plan and never gives up; it acts only through its own motors (Unitree's walking "
        "policy on the legs, the robot library's joint servo on the arms)",
        "the tachiai: no shikiri ritual, no fists on the clay and no matta (false start): both stand behind their "
        "starting lines at t = 0, and the bout is on from then; the opponent charges at t = {opp_start_s} s",
        "the bodies: neither robot wears a mawashi (there is no belt to grip; the G1's hands are fists, pushing with "
        "them counts as an open-hand thrust, not a punch); 'the soles of the feet' are each foot's sole and foot "
        "shell (the G1's ankle-roll link)",
        "the dohyo: a rigid mound {mound_height_m} m high and {mound_size_m} m square, its clay a firm surface "
        "with friction {clay_friction} (packed clay, 0.5 to 0.7 for clay courts after Nigg 2003; no sand layer, no "
        "give); the ring's bales are a row of {n_bales} rigid half-buried capsules standing {bale_proud_m} m "
        "proud, their inside edge on the {ring_diameter_m} m circle; the four tokudawara (the bales set outwards "
        "at the four sides) are not modelled",
        "the decision is the referee's, on contact: the first physics step (1 ms) in which a part of a robot "
        "other than its feet touches the mound, the bales or the floor, or any part touches the mound outside the "
        "bales or the floor below it; both in the same step is no decision (in sumo a rematch); a bout with no "
        "decision after {time_limit_s} s fails (honzumo has no time limit for the bout itself)",
        "a kick with a foot on the opponent's trunk (pelvis or torso) is the kinjite of kicking the chest or "
        "stomach and loses the bout",
        "you also lose when your pelvis is lower than {fall_z_m} m above the clay (the benchmark's fall line: for the "
        "G1 a squat with the hips at the heels, from which it cannot get up; a rikishi is judged by touch alone)",
    ]
    time_limit_s = 30.0
    fall_rule = False                # the decision is the module's own, on the physics step (both wrestlers)
    params = dict(ring_diameter_m=4.55, mound_size_m=6.7, mound_height_m=0.55, shikiri_len_m=0.90,
                  shikiri_width_m=0.06, shikiri_gap_m=0.70, n_bales=20, bale_radius_m=0.06, bale_proud_m=0.05,
                  clay_friction=0.6, start_behind_line_m=0.30, opp_start_s=0.5, opp_vx=0.8, opp_wz_max=1.0,
                  opp_turn_gain=2.0, opp_self_collision=0, fall_z_m=0.35, start_x_m=0.71, mound_half_m=3.35)   # (the last two: derived)

    sentence = ("Win a sumo bout: force the opponent robot out of the ring, or make any part of it other than its "
                "feet touch the ground, before the same happens to you.")
    rules = ("The bout is on a dohyo: a clay mound {mound_height_m} m high, {mound_size_m} m square, with a ring of "
             "straw bales whose inside edge is a circle {ring_diameter_m} m across (the bales stand "
             "{bale_proud_m} m proud of the clay). You stand facing the opponent behind your starting line "
             "(the white lines are {shikiri_gap_m} m apart, across the middle of the ring); the opponent, another "
             "Unitree G1, stands behind its line facing you. The bout starts at t = 0; the opponent charges at "
             "t = {opp_start_s} s and keeps walking into you, arms forward, turning to face you. You win at the "
             "first moment the opponent touches the ground outside the ring (the mound beyond the bales, or the "
             "floor below the mound) with any part of its body, or touches the clay or the bales inside with any "
             "part other than its feet, provided you have not done the same before. You lose (the attempt fails) "
             "if that happens to you first: any part of you on the ground outside the ring, any part other than "
             "your feet on the clay or the bales, or your pelvis lower than {fall_z_m} m above the clay. Both in "
             "the same instant is no decision and fails. Kicking the opponent's trunk (its pelvis or torso) with a "
             "foot is forbidden and fails. If there is no decision after {time_limit_s} s, you fail.")
    venue = ("You stand on the dohyo's clay, {mound_height_m} m above the arena floor, facing +x, at the middle "
             "of the ring sideways; the ring's centre is ahead of you, {start_x_m} m in front of your pelvis. "
             "The two starting lines cross the ring's middle {shikiri_gap_m} m apart; the opponent stands the "
             "same distance beyond the centre, facing you. The ring of bales is {ring_diameter_m} m across inside; "
             "the clay goes on beyond the bales to the mound's square edge, {mound_half_m} m from the centre.")
    difficulty = ("The opponent is as heavy and as strong as you and walks into you on a balance policy that "
                  "pushes back; the robot must stay on its feet under the impact and the shove, and turn the "
                  "contact into the opponent leaving the ring or going down, with only fists and no belt to "
                  "grip.")

    def __init__(self):
        super().__init__()
        self._sync()

    def configure(self, params):
        super().configure(params)
        self._sync()

    def _sync(self):
        p = self.p
        self.d0 = p["shikiri_gap_m"] / 2 + p["shikiri_width_m"] + p["start_behind_line_m"]
        self.start = (-self.d0, 0.0, 0.0)
        self.stages = ["win"]
        self.fall_z = p["mound_height_m"] + p["fall_z_m"]
        p["start_x_m"] = round(self.d0, 3)
        p["mound_half_m"] = round(p["mound_size_m"] / 2, 3)

    # ------------------------------------------------------------------ the venue
    def build(self, sc):
        p = self.p
        H, S = p["mound_height_m"], p["mound_size_m"] / 2
        R = p["ring_diameter_m"] / 2
        clay = dict(contype="1", conaffinity="5", friction=(p["clay_friction"], 0.005, 0.0001))
        sc.geom(sc.wb, "dohyo", type="box", pos=(0, 0, H / 2), size=(S, S, H / 2), rgba=(0.72, 0.56, 0.38, 1), **clay)
        sc.ground += ["dohyo"]
        rb, n = p["bale_radius_m"], int(p["n_bales"])
        zc = H + p["bale_proud_m"] - rb
        rc = R + rb                                     # the bales' inside edge on the ring
        for i in range(n):
            a0, a1 = 2 * math.pi * (i + 0.04) / n, 2 * math.pi * (i + 0.96) / n
            sc.geom(sc.wb, f"bale{i}", type="capsule",
                    fromto=(rc * math.cos(a0), rc * math.sin(a0), zc, rc * math.cos(a1), rc * math.sin(a1), zc),
                    size=(rb,), rgba=(0.80, 0.72, 0.45, 1), **clay)
            sc.ground.append(f"bale{i}")
        sc.disc("janome", (0, 0), R + 2 * rb + 0.25, rgba=(0.86, 0.80, 0.62, 1), z=H + 0.0006)
        sc.disc("ring_clay", (0, 0), R, rgba=(0.72, 0.56, 0.38, 1), z=H + 0.0008)
        for s in (-1, 1):
            x = s * (p["shikiri_gap_m"] / 2 + p["shikiri_width_m"] / 2)
            sc.geom(sc.wb, f"shikiri{s:+d}", type="box", pos=(x, 0, H + 0.001),
                    size=(p["shikiri_width_m"] / 2, p["shikiri_len_m"] / 2, 0.0005), rgba=(0.97, 0.97, 0.97, 1),
                    contype="0", conaffinity="0")
        # the opponent: a second G1 from the robot library, facing -x behind its line
        from bodies import load_body                   # the robot library (rfo/world.py imports it first)
        B = load_body("unitree_g1")
        B.mount(sc.root, OPP, (self.d0, 0.0, H), math.pi, hand=None, lod="standard", accent=(0.75, 0.12, 0.10, 1),
                self_collision=self.p["opp_self_collision"] > 0)
        # Collision classes: the robot's hulls (contype 4, conaffinity 0) never touch each other, so the opponent's
        # hulls get contype 16 (they still never touch each other, nor the robot's: its pairs are explicit) and
        # conaffinity 1 | 4 | 8: the floor, the props, the robot's hulls and its feet hit them. Its foot strike boxes
        # (contype 8) the same with conaffinity 4 | 8 only, so that, as on the robot, they pass through the ground and
        # the opponent stands on its sole spheres, which accept the robot's hulls and feet too.
        # Its contact is the robot's (rfo/world.py): the hulls stiff (ROBOT_CONTACT; with MuJoCo's default they sank
        # 84 mm into the clay, stress test), the soles as the robot's (SOLE_CONTACT).
        from rfo import world as W
        for dc in sc.root.iter("default"):              # the hulls and the soles are set by the model's classes
            g = dc.find("geom")
            if dc.get("class") == f"{OPP}g1_collision":
                g.set("contype", "16"); g.set("conaffinity", "13")
                g.attrib.update(W.ROBOT_CONTACT)
            elif dc.get("class") == f"{OPP}g1_foot":
                g.set("conaffinity", "13")
                g.attrib.update(W.SOLE_CONTACT or {})
        for b in sc.root.iter("body"):
            if (b.get("name") or "").startswith(OPP):
                for g in b.findall("geom"):
                    if g.get("contype") == "8":
                        g.set("contype", "16"); g.set("conaffinity", "12")
                        g.attrib.update(W.ROBOT_CONTACT)
        sc.camera("venue", (0.0, -4.6, H + 1.6), (0.0, 0.0, H + 0.55), fovy=60)
        sc.camera("end_on", (-4.2, -1.2, H + 1.4), (0.0, 0.0, H + 0.5), fovy=55)

    def _ensure(self, w):
        """The opponent's rig and arbiter (the robot library's), once per model."""
        if getattr(self, "_m", None) is not w.m:
            from bodies import load_body
            from bodies.control.arbiter import Arbiter
            self._m = w.m
            self.rig = load_body("unitree_g1").rig(w.m, OPP, hand=None)
            self.arb = Arbiter(self.rig)

    def reset(self, w):
        d, r, p = w.d, w.robot, self.p
        d.qpos[r.fq + 2] += p["mound_height_m"]            # the robot stands on the clay
        self._ensure(w)
        rig, a = self.rig, self.arb
        stand_z = importlib.import_module("bodies.unitree_g1.body").STAND_Z
        rig.place(d, rig.rest, pos=(self.d0, 0.0, p["mound_height_m"] + stand_z), yaw=math.pi)
        a.reset(d)                                         # its legs on the walking policy (zero command), arms held
        a.act.reset()                                      # its motors' last torque (in the state hash) to zero

    # ------------------------------------------------------------------ the opponent's policy
    def _opp_pose(self, w):
        d, rig = w.d, self.rig
        x, y = d.qpos[rig.fqadr], d.qpos[rig.fqadr + 1]
        qw, qx, qy, qz = d.qpos[rig.fqadr + 3:rig.fqadr + 7]
        return float(x), float(y), math.atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz))

    def before_step(self, w):
        p, a, d = self.p, self.arb, w.d
        t = w.t
        if t >= p["opp_start_s"] - 1e-9:
            ox, oy, oyaw = self._opp_pose(w)
            rx, ry = w.d.qpos[w.robot.fq], w.d.qpos[w.robot.fq + 1]
            err = (math.atan2(ry - oy, rx - ox) - oyaw + math.pi) % (2 * math.pi) - math.pi
            wz = float(np.clip(p["opp_turn_gain"] * err, -p["opp_wz_max"], p["opp_wz_max"]))
            a.walk(d, (p["opp_vx"], 0.0, wz))
            self.stage[0] = 1
            # the arms to the push pose, at the joints' speed limits (the arbiter's plan: rows within the limits)
            G = a.GROUPS["arms"]
            goal = np.r_[PUSH_ARM["left"], PUSH_ARM["right"]]
            cur = a.target()[G]
            step = a.speed[G] * a.dt * 0.999
            a.last_plan_step = -10 ** 9
            a.plan(d, ["arms"], (cur + np.clip(goal - cur, -step, step))[None, :])
        a.begin_step(d)
        a.apply(d, 1)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        m, p = w.m, self.p
        self._ensure(w)
        self.stage = [0]
        self.R_in = p["ring_diameter_m"] / 2
        self.R_out = self.R_in + 2 * p["bale_radius_m"]       # the bales' outside edge: beyond is outside
        ng = m.ngeom
        self.gclass = np.zeros(ng, dtype=np.int64)          # the ground: 1 the arena floor, 2 the clay, 3 a bale
        self.gclass[m.geom("floor").id] = 1
        self.gclass[m.geom("dohyo").id] = 2
        for i in range(int(p["n_bales"])):
            self.gclass[m.geom(f"bale{i}").id] = 3
        # who each geom belongs to: 0 nobody, 1 the robot, 2 the opponent; and whether it is a foot
        self.owner = np.zeros(ng, dtype=np.int64)
        self.foot = np.zeros(ng, dtype=bool)
        self.trunk = np.zeros(ng, dtype=bool)
        self.owner[ref.robot_mask] = 1
        self.foot[ref.part("feet")] = True
        opp_bodies = self.arb.robot_bodies
        for g in range(ng):
            b = int(m.geom_bodyid[g])
            if b in opp_bodies and (m.geom_contype[g] or m.geom_conaffinity[g]):
                self.owner[g] = 2
                bn = m.body(b).name[len(OPP):]
                if bn.endswith("ankle_roll_link"):
                    self.foot[g] = True
                if bn in CENTRAL and CENTRAL[bn] in ("pelvis", "torso"):
                    self.trunk[g] = True
        # one code per geom and a table of what a contact between two codes means (one lookup per physics step)
        # codes: 0 other, 1 robot foot, 2 robot other part, 3 opponent foot, 4 opponent trunk, 5 opponent other part,
        # 6 the floor, 7 the clay, 8 a bale
        code = np.zeros(ng, dtype=np.int64)
        code[(self.owner == 1) & self.foot] = 1
        code[(self.owner == 1) & ~self.foot] = 2
        code[(self.owner == 2) & self.foot] = 3
        code[(self.owner == 2) & ~self.foot] = 5
        code[(self.owner == 2) & self.trunk] = 4
        code[self.gclass == 1], code[self.gclass == 2], code[self.gclass == 3] = 6, 7, 8
        T = np.zeros((9, 9), dtype=np.int64)
        for c in (1, 2, 3, 4, 5):
            for gnd in (6, 7, 8):
                T[c, gnd] = LOSS if (gnd == 6 or c in (2, 4, 5)) else (ON_CLAY if gnd == 7 else 0)
        for c in (1, 2):
            for o in (3, 4, 5):
                T[c, o] = TOUCH | (KICK if (c == 1 and o == 4) else 0)
        self.code, self.table = code, T | T.T
        self.trackers = {"opponent": _Opponent(self.arb, self.stage), "first_contact_t": None}

    def _verdicts(self, w, ref):
        """{1: (how, part), 2: (how, part)}: who has lost in this physics step (1 the robot, 2 the opponent), and
        whether the robot kicked the opponent's trunk, and whether the two touch."""
        out, kick, touch = {}, False, False
        g1, g2 = ref._g1, ref._g2
        if len(g1):
            f = self.table[self.code[g1], self.code[g2]]
            if f.any():
                touch = bool((f & TOUCH).any())
                kick = bool((f & KICK).any())
                for i in np.flatnonzero(f & (LOSS | ON_CLAY)):
                    a, b = int(g1[i]), int(g2[i])
                    if self.owner[a] == 0:
                        a, b = b, a
                    who = int(self.owner[a])
                    if who in out:
                        continue
                    gc = int(self.gclass[b])
                    pt = ref._cpos[i]
                    if gc == 1:
                        how = "off the dohyo"
                    elif gc == 2 and math.hypot(float(pt[0]), float(pt[1])) > self.R_out:
                        how = "out of the ring"
                    elif not self.foot[a]:
                        how = "down"
                    else:
                        continue
                    out[who] = (how, self._part(w, ref, a))
        if 1 not in out and float(w.d.qpos[w.robot.fq + 2]) < self.fall_z:
            out[1] = ("down", "pelvis low")
        return out, kick, touch

    def _part(self, w, ref, g):
        if self.owner[g] == 1:
            return ref.part_names[ref.part_code[g]]
        bn = w.m.body(int(w.m.geom_bodyid[g])).name[len(OPP):]
        if bn in CENTRAL:
            return CENTRAL[bn]
        side, rest = bn.split("_", 1)
        return f"{side}_{PART_OF_BODY.get(rest, rest)}"

    def substep(self, w, ref):
        tr = self.trackers
        lost, kick, touch = self._verdicts(w, ref)
        if touch and tr["first_contact_t"] is None:
            tr["first_contact_t"] = round(ref.time, 4)
            ref.event("contact")
        if kick:
            return ref.fail("kicked the opponent's trunk (kinjite)")
        if 1 in lost and 2 in lost:
            return ref.fail("both touched down together (no decision)", robot=list(lost[1]), opponent=list(lost[2]))
        if 1 in lost:
            return ref.fail(f"you lost: {lost[1][0]}", part=lost[1][1])
        if 2 in lost and not ref.success:
            ref.metrics["win_t"] = round(ref.time, 4)
            ref.event("opponent lost", how=lost[2][0], part=lost[2][1])
            if ref.stage("win", how=lost[2][0]):
                ref.succeed()
        j = ref.ph % w.SUB                                # the opponent's motors for the next physics step
        if j:
            self.arb.apply(w.d, j + 1)

    def privileged(self, w):
        ox, oy, oyaw = self._opp_pose(w)
        rig = self.rig
        return {"pelvis": w.pelvis().tolist(), "opponent_pelvis_xyz_yaw": [ox, oy, float(w.d.qpos[rig.fqadr + 2]), oyaw],
                "opponent_vel": w.d.qvel[rig.fvadr:rig.fvadr + 6].tolist(), "ring_centre": [0.0, 0.0],
                "ring_radius_m": self.R_in, "ring_out_radius_m": self.R_out, "clay_z": self.p["mound_height_m"],
                "opponent_charging": bool(self.stage[0])}
