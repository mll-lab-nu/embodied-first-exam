"""Balance board: stay for 30 s on a roller board (a rigid deck lying loose on a free cylinder that rolls on the floor),
without a deck end or the robot ever touching the floor."""
import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from rfo.scene import STANDABLE, VISUAL
from rfo.task import TaskBase
# A rigid roller (PVC pipe) and wooden deck's contact with the robot, the venue's fixtures and the other props (the
# ground keeps its own: rfo/world.py GROUND_SOLMIX): the stiff contact of the core's shells (rfo/world.py
# SHELL_CONTACT: solref 0.004 s, solimp 0.99 0.999 0.0005, from Embodied Olympics' weightlifting fix, a rigid prop on the
# robot's aluminium) with a solmix that wins over a default-contact geom; a ball (priority 1) keeps its own bounce.
# With MuJoCo's default soft contact (solref 0.02 1, solimp 0.9 0.95) it sank 60 mm into the floor and 53 mm into the
# robot (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402

DECK_MASS, ROLLER_MASS = 2.7, 1.8        # kg: a 18 mm plywood deck, a hollow plastic roller


class Task(TaskBase):
    name = "balance-board"
    title = "Balance board"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("No federation rule book: the roller balance board (Indo Board style rocker-roller trainer): a rigid "
                "deck 0.76 m x 0.38 m lying loose on a free roller of 0.085 m radius, with a stop under each end of "
                "the deck; the standard is the balance trainer's: time on the board with neither end of the deck nor "
                "the rider touching the floor")
    deviations = [
        "the board: deck and roller are rigid bodies (a {deck_mass_kg} kg box and a {roller_mass_kg} kg hollow "
        "cylinder) with a friction coefficient of {friction} between deck, roller and floor, without grip tape or a "
        "rubber-lined roller, because the simulator has rigid bodies only",
        "the mount: a rider steps onto a deck that rests on one end and rolls it up to level; the robot does not "
        "step on: it starts standing square on the deck just after that mount, the deck {start_tilt_deg} degrees "
        "from level with its left end low, resting on the roller under its middle, the robot tilted with it (feet "
        "flat on the deck), its centre of mass about 4 cm left of the roller's line of contact and everything at "
        "rest; it has to bring the board level itself. The start is the same in every trial (no random "
        "perturbation), because a trial is one frozen instance",
    ]
    time_limit_s = 30.5
    start = (0.0, 0.0, 0.0)
    fall_rule = False                # the family's own rule: only the feet on the deck, nothing on the floor
    stages = ["10 s", "20 s", "30 s"]
    params = dict(duration_s=30.0, deck_length_m=0.76, deck_width_m=0.38, deck_thickness_m=0.018,
                  roller_radius_m=0.085, roller_length_m=0.46, deck_mass_kg=DECK_MASS, roller_mass_kg=ROLLER_MASS,
                  friction=1.0, stop_height_m=0.02, stop_length_m=0.03, off_board_s=1.0, start_tilt_deg=3.0)

    sentence = ("Stay balanced on the roller board for {duration_s} s: neither end of the deck nor any part of you "
                "may touch the floor.")
    rules = ("The board is a rigid deck {deck_length_m} m long (left to right), {deck_width_m} m wide and "
             "{deck_thickness_m} m thick, {deck_mass_kg} kg, lying loose on a roller: a free cylinder of "
             "{roller_radius_m} m radius, {roller_length_m} m long, {roller_mass_kg} kg, whose axis points "
             "fore-aft and which rolls on the floor to your left and right. Nothing holds the deck to the roller or "
             "the roller to the floor but contact and friction (coefficient {friction}); there is no spring. A stop "
             "{stop_height_m} m high and {stop_length_m} m long under each end of the deck keeps the roller from rolling out from under it. You succeed "
             "when {duration_s} s have passed from the start without a failure. You fail the moment any part of the "
             "deck (an end or a stop) touches the floor, any part of you touches the floor or the roller, any part "
             "of you other than a foot touches the deck (a fall on the board), or neither of your feet has touched "
             "the deck for more than {off_board_s} s (you have left the board). With the roller in the middle, an end of the "
             "deck meets the floor at a tilt of about 24 degrees.")
    venue = ("You face +x, standing upright in the rest pose with your feet side by side on the middle of the deck, "
             "0.24 m apart, one on each side of the roller, whose axis runs fore-aft under you. At t = 0 the board "
             "is not level: as just after a mount, the deck is tilted {start_tilt_deg} degrees with its left end "
             "low (its top about 0.188 m above the floor at the middle), resting on the roller under its middle, "
             "and you stand square on it, tilted with it, your centre of mass about 4 cm to the left of the "
             "roller's line of contact; everything is at rest. Left alone, the board tips further to the left and "
             "runs out from under you within a second; the robot's stance does not correct it. The floor is "
             "all around.")
    difficulty = ("Two unstable motions are coupled: the deck tilts on the roller and the roller rolls away under "
                  "the deck. Neither the platform's stance nor the walking policy corrects them; the legs have to "
                  "shift the body's weight against the board fast enough to keep the roller between the feet for "
                  "{duration_s} s.")

    def build(self, sc):
        p = self.p
        R, T, hl, hw, mu = (p["roller_radius_m"], p["deck_thickness_m"], p["deck_length_m"] / 2, p["deck_width_m"] / 2,
                            p["friction"])
        self.cx = 0.009                                  # under the middle of the feet (the soles' centre)
        self.top = 2 * R + T
        fr = (mu, 0.005, 0.0001)
        sc.box("mat", (self.cx, 0, 0.0003), (1.5, 2.0, 0.0003), rgba=(0.25, 0.30, 0.42, 1))
        rl = p["roller_length_m"] / 2
        b = sc.body("roller", (self.cx, 0.0, R), free=True)
        Ix = p["roller_mass_kg"] * R * R                 # a hollow cylinder about its axis
        Iy = p["roller_mass_kg"] * (6 * R * R + (2 * rl) ** 2) / 12
        ET.SubElement(b, "inertial", pos="0 0 0", mass=f"{p['roller_mass_kg']:g}", diaginertia=f"{Ix:.6g} {Iy:.6g} {Iy:.6g}")
        # the rolling surface is a capsule whose straight part is the roller's length (exact line contact with the
        # floor and the deck; its round ends are beyond the deck's edges); the flat-ended cylinder is what is drawn
        sc.geom(b, "roller", type="capsule", fromto=(-rl, 0, 0, rl, 0, 0), size=(R,), rgba=(0, 0, 0, 0),
                friction=fr, condim=3, **STANDABLE, **RIGID)
        sc.geom(b, "roller_look", type="cylinder", fromto=(-rl, 0, 0, rl, 0, 0), size=(R,), rgba=(0.20, 0.45, 0.75, 1),
                **VISUAL)
        sc.geom(b, "roller_mark", type="box", pos=(0, 0, 0), size=(rl + 0.001, 0.004, R * 0.98), rgba=(1, 1, 1, 1),
                **VISUAL)
        dk = sc.body("deck", (self.cx, 0.0, 2 * R + T / 2), free=True)
        sc.geom(dk, "deck", type="box", size=(hw, hl, T / 2), mass=DECK_MASS * 0.94, rgba=(0.72, 0.52, 0.30, 1),
                friction=fr, condim=3, **STANDABLE, **RIGID)
        lip = (p["stop_length_m"], p["stop_height_m"])       # the stops under the deck's two ends
        for s, tag in ((1, "L"), (-1, "R")):
            sc.geom(dk, f"deck_stop{tag}", type="box", pos=(0, s * (hl - lip[0] / 2), -T / 2 - lip[1] / 2),
                    size=(hw, lip[0] / 2, lip[1] / 2), mass=DECK_MASS * 0.03, rgba=(0.45, 0.30, 0.15, 1), friction=fr,
                    condim=3, **STANDABLE, **RIGID)
        sc.camera("venue", (2.3, -0.9, 0.9), (0.0, 0.0, 0.60), fovy=50)

    def reset(self, w):
        """The start just after a mount: deck and robot, as one rigid piece, turned about the roller's axis by the
        start tilt (left end low) from the level stance over the roller; the deck stays tangent to the roller at the
        middle of its underside, the robot's soles flat on the deck."""
        p, d, fq = self.p, w.d, w.robot.fq
        R, T = p["roller_radius_m"], p["deck_thickness_m"]
        th = -math.radians(p["start_tilt_deg"])          # about +x: a positive angle lifts the left (+y) end
        c, s = math.cos(th), math.sin(th)
        rot = np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])
        q = np.array([math.cos(th / 2), math.sin(th / 2), 0.0, 0.0])
        axis = np.array([self.cx, 0.0, R])               # the roller's axis (along x)
        w.put("roller", (self.cx, 0.0, R))
        w.put("deck", axis + rot @ np.array([0.0, 0.0, R + T / 2]), quat=q)
        d.qpos[fq + 2] += self.top                       # the robot stands on the deck, not on the floor ...
        d.qpos[fq:fq + 3] = axis + rot @ (d.qpos[fq:fq + 3] - axis)     # ... and is turned with it
        out = np.zeros(4)
        mujoco.mju_mulQuat(out, q, d.qpos[fq + 3:fq + 7].copy())
        d.qpos[fq + 3:fq + 7] = out

    def board(self, w) -> dict:
        """The deck's tilt (rad, positive lifts its left end), where the roller is under it (m, positive towards the
        deck's left end), the roller's and the deck's y and their rates."""
        d = w.d
        dk, ro = w.m.body("deck").id, w.m.body("roller").id
        R = d.xmat[dk].reshape(3, 3)
        tilt = math.atan2(float(R[2, 1]), float(R[1, 1]))
        rel = float(R[:, 1] @ (d.xpos[ro] - d.xpos[dk]))
        return {"tilt_rad": tilt, "roller_under_deck_m": rel, "roller_y": float(d.xpos[ro][1]),
                "deck_y": float(d.xpos[dk][1]), "roller_vy": float(w.vel("roller")[1]),
                "deck_vy": float(w.vel("deck")[1]), "tilt_rate_rad_s": float(d.cvel[dk][0])}

    def referee_reset(self, w, ref):
        self.floor = ref.geoms(names=["floor"])
        self.deck_g = ref.geoms(body="deck")
        self.roller_g = ref.geoms(body="roller")
        self.robot = ref.part("robot")
        self.feet = ref.part("feet")
        self.not_feet = ref.part("robot") & ~ref.part("feet")
        self.trackers = {"off_s": 0.0, "max_tilt_deg": 0.0}

    def substep(self, w, ref):
        if ref.touching(self.deck_g, self.floor):
            ref.fail("the deck touched the floor")
        elif ref.touching(self.robot, self.floor):
            ref.fail("touched the floor", parts=sorted(ref.parts_touching(self.floor)))
        elif ref.touching(self.robot, self.roller_g):
            ref.fail("touched the roller", parts=sorted(ref.parts_touching(self.roller_g)))
        elif ref.touching(self.not_feet, self.deck_g):
            ref.fail("fell on the board", parts=sorted(ref.parts_touching(self.deck_g) - {"left_foot", "right_foot"}))

    def step(self, w, ref):
        p, tr = self.p, self.trackers
        if ref.failed:
            return
        tr["off_s"] = 0.0 if ref.touching(self.feet, self.deck_g) else round(tr["off_s"] + w.CONTROL_DT, 4)
        if tr["off_s"] > p["off_board_s"]:
            return ref.fail("left the board")
        tr["max_tilt_deg"] = max(tr["max_tilt_deg"], round(abs(math.degrees(self.board(w)["tilt_rad"])), 2))
        ref.metrics["max_tilt_deg"] = tr["max_tilt_deg"]
        ref.metrics["time_on_board_s"] = round(w.t, 2)
        for name in self.stages:
            if w.t >= float(name.split()[0]) * p["duration_s"] / 30.0 - 1e-9:
                ref.stage(name)
        if w.t >= p["duration_s"] - 1e-9 and ref.has(self.stages[-1]):
            ref.succeed()

    def privileged(self, w):
        return {**self.board(w), "com": w.com().tolist(), "pelvis": w.pelvis().tolist(),
                "deck_top_m": self.top, "roller_radius_m": self.p["roller_radius_m"]}
