"""Baseline assembly through observations and ordinary ALOHA EE actions.

Grasp points and reversed prototype route recover the historical baseline
semantics. No scene handles, state writes or attachment commands enter policy.
"""
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from topogym.assets.geometry.cast_coil import CoilAssembly
from topogym.planning.motions.cast_coil import prototype_route


def rotation(q):
    return Rotation.from_quat(np.asarray(q)[[1, 2, 3, 0]])


GRASP_POINTS = {"left": np.array([.022, .032, .0405]),
                "right": np.array([-.022, -.032, .0405])}
PARTS = {"left": "coil_silver", "right": "coil_gold"}


class CastCoilBaselinePolicy:
    def __init__(self, *, body_origins, part="all", route=None):
        self.origins = {k: np.asarray(v) for k, v in body_origins.items()}
        self.part = part
        self.phase = "created"
        self.route = route
        self.place_from_rest = False

    def initialize(self, context):
        if context["action_spec"]["robot_id"] != "aloha" or context["action_spec"]["mode"] != "EE_ABS":
            raise ValueError("Coil baseline requires ALOHA EE_ABS")
        self.dt = context["timing_spec"]["control_dt_s"]
        self.grip = .037
        self.program = None
        self.bias = {s: np.zeros(3) for s in PARTS}
        self.angle_bias = {s: np.zeros(3) for s in PARTS}

    def act(self, obs):
        self.obs = obs
        if self.program is None:
            self.program = self.actions()
        return next(self.program, None)

    def time(self):
        return self.obs["state"]["sim_time_s"]

    def bodies(self):
        out = {}
        for side, name in PARTS.items():
            body = self.obs["privileged"]["world"]["bodies"][name]
            r = rotation(body["quaternion_wxyz"])
            out[side] = (np.asarray(body["position_m"])-r.apply(self.origins[name]), r)
        return out

    def tcp(self):
        return {s: (np.asarray(v["tcp_position_world_m"]), rotation(v["tcp_orientation_wxyz"]))
                for s, v in self.obs["robot"].items()}

    def hold(self, seconds):
        start = self.time()
        while self.time()-start < seconds-1e-8:
            yield {}

    def follow(self, pose_at, seconds, phase):
        self.phase = phase
        start = self.time()
        while True:
            t = min(1., (self.time()-start+self.dt)/seconds)
            u = float(np.clip(t**3*(10+t*(-15+6*t)), 0., 1.))
            targets = pose_at(u)
            yield {s: dict(position_world_m=p.tolist(), orientation_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist(),
                           gripper_position_m=self.grip) for s, (p, r) in targets.items()}
            if t >= 1.-1e-8:
                break
        yield from self.hold(.25)

    def move(self, targets, seconds, phase):
        initial = self.tcp()
        turns = {s: Slerp([0, 1], Rotation.from_quat([initial[s][1].as_quat(), r.as_quat()]))
                 for s, (_, r) in targets.items()}
        yield from self.follow(lambda u: {s: (initial[s][0]+u*(p-initial[s][0]), turns[s](u))
                                         for s, (p, _) in targets.items()}, seconds, phase)

    def grasp_targets(self, bodies):
        yaw = Rotation.from_euler("z", 90, degrees=True)
        turns = {"left": Rotation.from_matrix(np.column_stack(([1, 0, 0], [0, 0, -1], [0, 1, 0]))),
                 "right": Rotation.from_matrix(np.column_stack(([-1, 0, 0], [0, 0, 1], [0, 1, 0])))}
        result = {}
        for side, (p, r) in bodies.items():
            turn = r*yaw.inv()*turns[side]
            # Historical points reference pad center; the public TCP is 13.81 mm behind it.
            result[side] = (p+r.apply(GRASP_POINTS[side])+turn.apply([-.01381, 0, .00055]), turn)
        return result

    def attached_targets(self, bodies):
        actual = self.bodies()
        targets = {}
        for s, (p, r) in bodies.items():
            # Slow integral compensation for load-dependent servo deflection.
            # Only measured object poses and ordinary EE actions are used.
            delta = np.clip(2.*self.dt*(p-actual[s][0]), -.002, .002)
            self.bias[s] = np.clip(self.bias[s]+delta, -.10, .10)
            error = (r*actual[s][1].inv()).as_rotvec()
            self.angle_bias[s] = np.clip(self.angle_bias[s]+2.*self.dt*error, -.3, .3)
            commanded_r = Rotation.from_rotvec(self.angle_bias[s])*r
            targets[s] = (p+self.bias[s]+commanded_r.apply(self.offsets[s][0]), commanded_r*self.offsets[s][1])
        return targets

    def follow_bodies(self, pose_at, seconds, phase):
        yield from self.follow(lambda u: self.attached_targets(pose_at(u)), seconds, phase)
        target = pose_at(1.)
        start = self.time()
        while True:
            actual = self.bodies()
            errors = {s: (float(np.linalg.norm(p-actual[s][0])), float((r*actual[s][1].inv()).magnitude()))
                      for s, (p, r) in target.items()}
            if all(p < .001 and a < .01 for p, a in errors.values()):
                return
            if self.time()-start > 4.:
                raise RuntimeError(f"Body tracking failed in {phase}: {errors}")
            targets = self.attached_targets(target)
            yield {s: dict(position_world_m=p.tolist(), orientation_wxyz=r.as_quat()[[3,0,1,2]].tolist(),
                           gripper_position_m=self.grip) for s, (p, r) in targets.items()}

    def actions(self):
        self.phase = "open_at_home"
        yield {s: dict(gripper_position_m=self.grip) for s in PARTS}
        yield from self.hold(.5)
        initial = self.bodies()
        resting_gold_pose = initial["right"]
        grasp = self.grasp_targets(initial)
        outside = {s: (p-r.apply([.10, 0, 0]), r) for s, (p, r) in grasp.items()}
        above = {s: (p+[0, 0, .12], r) for s, (p, r) in outside.items()}
        yield from self.move(above, 4., "home_to_pregrasp")
        yield from self.move(outside, 2., "descend_outside")
        yield from self.move(grasp, 2., "side_approach")
        self.phase, self.grip = "close_and_acquire", .002
        yield {s: dict(gripper_position_m=self.grip) for s in PARTS}
        yield from self.hold(1.5)
        hands = self.obs["privileged"]["world"]["grasp"]["hands"]
        if any(hands[s]["phase"] != "holding" for s in PARTS):
            raise RuntimeError("Bilateral automatic grasp not acquired: "+str({s: hands[s]["phase"] for s in PARTS}))
        initial, tcp = self.bodies(), self.tcp()
        self.offsets = {s: (r.inv().apply(tcp[s][0]-p), r.inv()*tcp[s][1]) for s, (p, r) in initial.items()}
        yield from self.follow_bodies(lambda u: {s: (p+[0, 0, .08*u], r)
            for s, (p, r) in initial.items()}, 4., "lift")
        if self.part == "pickup":
            return
        gold_p, gold_r = initial["right"]
        gold_p = gold_p+[0, 0, .08]
        route = self.route if self.route is not None else prototype_route(CoilAssembly(scale=3.))
        final_r, final_t = route[-1].pose(1.)
        target_bodies = {"right": (gold_p, gold_r), "left": (gold_p+gold_r.apply(final_t), gold_r*Rotation.from_matrix(final_r))}
        actual = self.bodies()
        turns = {s: Slerp([0,1], Rotation.from_quat([actual[s][1].as_quat(),r.as_quat()])) for s,(_,r) in target_bodies.items()}
        yield from self.follow_bodies(lambda u: {s: (actual[s][0]+u*(p-actual[s][0]),turns[s](u))
            for s,(p,r) in target_bodies.items()},4.,"approach_align")
        phases = dict(prototype_extract="assembly_insert", prototype_quarter_turn="assembly_quarter_turn",
                      prototype_slide="assembly_close", screw_turn="assembly_screw_turn",
                      turn_second_45="assembly_second_45", intermediate_offset="assembly_undo_offset",
                      turn_first_45="assembly_first_45")
        for motion in reversed(route):
            def target(u, motion=motion):
                r, t = motion.pose(1.-u)
                return {"right": (gold_p, gold_r), "left": (gold_p+gold_r.apply(t), gold_r*Rotation.from_matrix(r))}
            yield from self.follow_bodies(target, motion.duration_s*2, phases[motion.name])
        if self.place_from_rest:
            # Pickup can tilt a part while its original edge still touches the
            # table. That tilted pose need not support the assembled pair.
            # Recover the measured support pose before either hand touched it.
            rest_p, rest_r = resting_gold_pose
            place_turn = Slerp([0, 1], Rotation.from_quat([gold_r.as_quat(), rest_r.as_quat()]))
            yield from self.follow_bodies(lambda u: {s: (gold_p+u*(rest_p-gold_p), place_turn(u))
                for s in PARTS}, 4., "place_assembly")
        else:
            yield from self.follow_bodies(lambda u: {s: (gold_p-[0, 0, .08*u], gold_r)
                for s in PARTS}, 4., "place_assembly")
        self.phase, self.grip = "release", .037
        yield {s: dict(gripper_position_m=self.grip) for s in PARTS}
        yield from self.hold(.3)
        # The gold grasp closes vertically. Raising that hand would scoop the
        # assembled piece with its lower finger; withdraw along each hand axis.
        retreat = {s: (p-r.apply([.08, 0, 0]), r) for s, (p, r) in self.tcp().items()}
        yield from self.move(retreat, 3., "retreat")
        self.phase = "settle"
        yield from self.hold(4.)
