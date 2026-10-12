"""Kick the heavy bag: one clean kick with the named foot or shin on the mark at trunk height that gives the bag at
least the set impulse; then back on both feet, standing. A 30 kg, 1.2 m bag on a 0.5 m chain; the Unitree H1-2."""
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from rfo.scene import HITTABLE, VISUAL
from rfo.task import TaskBase



def build_bag(sc, x: float, p: dict, zone: tuple[float, float], zone_rgba) -> None:
    """A heavy bag hanging from a hook above (x, 0): one rigid body on a ball joint at the hook (the chain is part of
    it), a cylinder of the bag's length, diameter and mass; the marked zone is a painted band."""
    L, R, chain = p["bag_length_m"], p["bag_diameter_m"] / 2, p["chain_length_m"]
    hook = p["bag_top_m"] + chain
    sc.box("frame_post", (x + 1.2, 0, hook / 2 + 0.05), (0.05, 0.05, hook / 2 + 0.05), rgba=(0.3, 0.3, 0.33, 1), solid="hit")
    sc.box("frame_arm", (x + 0.6, 0, hook + 0.05), (0.65, 0.04, 0.04), rgba=(0.3, 0.3, 0.33, 1))
    b = sc.body("bag", (x, 0.0, hook))
    ET.SubElement(b, "joint", name="bag", type="ball", damping="1.0")
    sc.geom(b, "bag", type="cylinder", pos=(0, 0, -(chain + L / 2)), size=(R, L / 2), mass=p["bag_mass_kg"],
            rgba=(0.55, 0.12, 0.10, 1), friction=(0.8, 0.005, 0.0001), solref="0.02 1", **HITTABLE)
    sc.geom(b, "bag_chain", type="capsule", fromto=(0, 0, 0, 0, 0, -chain), size=(0.008,), mass=0,
            rgba=(0.6, 0.6, 0.62, 1), **VISUAL)
    sc.geom(b, "bag_zone", type="cylinder", pos=(0, 0, -(hook - (zone[0] + zone[1]) / 2)), size=(R + 0.002, (zone[1] - zone[0]) / 2),
            mass=0, rgba=zone_rgba, **VISUAL)


class BagMeter:
    """What the bag receives: its angular momentum about the hook (world frame), from the ball joint's velocity and the
    bag's inertia about the hook. A horizontal blow of impulse J at depth d below the hook changes its horizontal part
    by J d (the hook's own force has no moment about the hook; gravity's is negligible over a short touch)."""

    def __init__(self, w):
        m = w.m
        self.body = m.body("bag").id
        self.dof = int(m.joint("bag").dofadr[0])
        M = np.zeros((m.nv, m.nv))
        mujoco.mj_fullM(m, M, w.d.qM)
        self.inertia = M[self.dof:self.dof + 3, self.dof:self.dof + 3].copy()      # about the hook, in the bag's frame
        self.hook = w.d.xpos[self.body].copy()

    def momentum(self, w) -> np.ndarray:
        R = w.d.xmat[self.body].reshape(3, 3)
        return R @ (self.inertia @ w.d.qvel[self.dof:self.dof + 3])

    def depth(self, w, point) -> float:
        """How far below the hook, along the bag, a world point is."""
        R = w.d.xmat[self.body].reshape(3, 3)
        return float(-(R.T @ (np.asarray(point) - self.hook))[2])

    def speed(self, w) -> float:
        return float(np.linalg.norm(w.d.qvel[self.dof:self.dof + 3]))


def contact_impulse(w, A: np.ndarray, B: np.ndarray) -> float:
    """The normal contact force between selectors A and B now, times the physics step (N s)."""
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
    name = "kick-target"
    title = "Kick the heavy bag at trunk height"
    category = "throwing-catching-striking"
    robot = "unitree_h1"
    rulebook = ("No rule book for a bag. The kick is judged by the scoring criterion of World Taekwondo's Competition "
                "Rules (a valid point is a kick delivered with a part of the foot below the ankle bone to the trunk "
                "protector, with the required level of impact) and of kickboxing (the shin also strikes), applied "
                "to a standard heavy bag (30 kg, 1.2 m, on a chain)")
    deviations = [
        "No opponent: the scoring area is a marked band on a heavy bag ({zone_low_m} m to {zone_high_m} m above the "
        "floor: trunk height, 1.1 m, for the robot); one kick, not a bout.",
        "The striking surface is the named leg's foot or shin (taekwondo scores the foot only).",
        "\"The required level of impact\" is measured: the impulse the bag receives during the touch (the change of "
        "the bag's angular momentum about its hook, divided by the depth below the hook of the lowest point the blow touched) must be at "
        "least {min_impulse_n_s} N s; \"not a push\": the touch lasts at most {max_contact_s} s. Both numbers are "
        "this benchmark's (a light, clean kick of a trained adult on a heavy bag), not a rule book's.",
        "The chain is rigid: the bag and its chain swing as one body about the hook (a ball joint).",
    ]
    time_limit_s = 15.0
    start = (0.0, 0.0, 0.0)
    stages = ["strike", "stand"]
    fall_z = 0.50
    params = dict(leg="right", bag_mass_kg=30.0, bag_length_m=1.2, bag_diameter_m=0.35, chain_length_m=0.5,
                  bag_top_m=1.75, bag_distance_m=0.80, zone_low_m=0.95, zone_high_m=1.25, min_impulse_n_s=20.0,
                  max_contact_s=0.15, touch_gap_s=0.03, stand_s=2.0, fall_pelvis_m=0.50)

    sentence = ("Kick the heavy bag once with your {leg} foot or shin, on the marked band at trunk height, hard enough "
                "to give it {min_impulse_n_s} N s, then stand on both feet.")
    rules = ("A heavy bag ({bag_mass_kg} kg, {bag_length_m} m long, {bag_diameter_m} m across) hangs by a "
             "{chain_length_m} m chain from a hook, free to swing in every direction; its top is {bag_top_m} m above "
             "the floor and its axis {bag_distance_m} m in front of you. The marked band runs round the bag from "
             "{zone_low_m} m to {zone_high_m} m above the floor. Your first touch of the bag is your kick. It must be "
             "made with your {leg} foot or {leg} shin alone and must first meet the bag inside the band. It is a "
             "blow, not a push: the touch lasts at most {max_contact_s} s (it ends when leg and bag have been apart "
             "for {touch_gap_s} s), and during it the bag must receive an impulse of at least {min_impulse_n_s} "
             "N s, measured as the change of the bag's angular momentum about its hook divided by the depth below the "
             "hook of the lowest point the blow touched. You succeed when, after the kick, you stand for {stand_s} s without a break: "
             "both feet and nothing else on the floor, the torso within about 20 degrees of upright, the pelvis "
             "slower than 0.35 m/s. You fail if anything other than the {leg} foot or shin touches the bag at any "
             "time; if the kick lands outside the band, is too weak or is a push; if anything touches the bag again "
             "after the kick; if you fall (your pelvis lower than {fall_pelvis_m} m above the floor, or any part of "
             "you other than your feet on the floor); or after {time_limit_s} s.")
    venue = ("You face the bag (+x); its near side is 0.625 m in front of your pelvis and it hangs still, its lower "
             "end 0.55 m above the floor. The band is white.")
    difficulty = ("The band is higher than the robot's hip joint: the foot has to be swung above hip height, fast, "
                  "while the other leg alone carries 67 kg; there is no kicking or one-leg balance policy. The bag "
                  "pushes back with the same impulse, and the body has to end on both feet, still.")

    def build(self, sc):
        p = self.p
        self.fall_z = p["fall_pelvis_m"]
        sc.box("mat", (0.3, 0, 0.0003), (1.8, 1.8, 0.0003), rgba=(0.30, 0.45, 0.40, 1))
        build_bag(sc, p["bag_distance_m"], p, (p["zone_low_m"], p["zone_high_m"]), (0.96, 0.96, 0.94, 1))
        sc.camera("venue", (-1.2, -2.8, 1.5), (0.45, 0.0, 1.0), fovy=50)

    def referee_reset(self, w, ref):
        leg = self.p["leg"]
        self.bag = ref.geoms(names=["bag"])
        self.robot = ref.part("robot")
        self.legal_names = {f"{leg}_foot", f"{leg}_shin"}
        self.leg = ref.part(*sorted(self.legal_names))
        self.not_leg = self.robot & ~self.leg
        self.meter = BagMeter(w)
        self.hook_z = float(self.meter.hook[2])
        self.trackers = {"t0": None, "t_last": None, "L0": None, "L": None, "depth": None, "contact": 0.0,
                         "judged": False}

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        touch = ref.touching(self.bag, self.robot)
        if tr["judged"]:
            if touch:
                ref.fail("the bag was touched again after the kick", parts=sorted(ref.parts_touching(self.bag)))
            return
        if touch:
            if ref.touching(self.bag, self.not_leg):
                return ref.fail(f"the bag was touched by something other than the {p['leg']} foot or shin",
                                parts=sorted(ref.parts_touching(self.bag) - self.legal_names))
            pts = ref.contact_points(self.leg, self.bag)
            if tr["t0"] is None:
                z = float(pts[:, 2].mean())
                tr["t0"], tr["depth"] = ref.time, self.meter.depth(w, pts.mean(axis=0))
                tr["L0"] = [float(x) for x in self.meter.momentum(w)]
                ref.metrics["hit_height_m"] = round(z, 3)
                if not (self.hook_z - p["zone_high_m"] <= tr["depth"] <= self.hook_z - p["zone_low_m"]):
                    return ref.fail("the kick landed outside the marked band", height_m=round(z, 3))
            tr["t_last"] = ref.time
            if len(pts):                                          # a blow that slides down the bag has a longer lever
                tr["depth"] = max(tr["depth"], max(self.meter.depth(w, q) for q in pts))
            tr["L"] = [float(x) for x in self.meter.momentum(w)]
            tr["contact"] += contact_impulse(w, self.leg, self.bag)
            if ref.time - tr["t0"] > p["max_contact_s"]:
                tr["judged"] = True
                return ref.fail("the bag was pushed, not struck", contact_s=round(ref.time - tr["t0"], 3))
        elif tr["t0"] is not None and ref.time - tr["t_last"] >= p["touch_gap_s"]:
            tr["judged"] = True                                   # the touch is over: the blow is measured
            dL = np.array(tr["L"]) - np.array(tr["L0"])
            J = float(np.hypot(dL[0], dL[1])) / tr["depth"]
            ref.metrics["impulse_n_s"] = round(J, 2)
            ref.metrics["contact_impulse_n_s"] = round(tr["contact"], 2)
            ref.metrics["contact_s"] = round(tr["t_last"] - tr["t0"], 3)
            if J < p["min_impulse_n_s"]:
                ref.fail("the kick was too weak", impulse_n_s=round(J, 2))
            else:
                ref.stage("strike", impulse_n_s=round(J, 2))

    def step(self, w, ref):
        if not ref.has("strike"):
            return
        both = ref.parts_touching(ref.ground) == {"left_foot", "right_foot"}
        if ref.hold("stand", both and ref.standing(), self.p["stand_s"]):
            if ref.stage("stand"):
                ref.succeed()

    def privileged(self, w):
        p = self.p
        return {"bag_hook": self.meter.hook.tolist(), "bag_axis": (-w.d.xmat[self.meter.body].reshape(3, 3)[:, 2]).tolist(),
                "bag_angular_speed": self.meter.speed(w), "leg": p["leg"], "zone": [p["zone_low_m"], p["zone_high_m"]]}
