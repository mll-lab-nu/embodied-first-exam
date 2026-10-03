"""External grasp, cube assembly and released placement through native EE actions.

Only explicitly granted observations are read. The simulator owns automatic
contact-gated grasp acquisition and release; the policy never writes state.
"""
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from topogym.tasks.cast_coil.simplified import grasp_points
from .baseline import CastCoilBaselinePolicy, PARTS
from .policy import CastCoilPolicy, variant_reference


class SimplifiedCoilPolicy(CastCoilPolicy):
    def __init__(self, *, body_origins, variant="very_easy", part="all", task_parameters=None, seed=0):
        if part not in ("pickup", "all"):
            raise ValueError("Simplified Coil supports pickup or all")
        assembly, route = variant_reference(variant, task_parameters=task_parameters, seed=seed)
        if not hasattr(assembly, "record"):
            raise ValueError("Simplified policy requires one of the two cube geometries")
        CastCoilBaselinePolicy.__init__(self, body_origins=body_origins, part=part, route=route)
        self.variant = variant
        self.grasp_points = grasp_points(assembly.record)
        self.radius = max(float(np.linalg.norm(b.visual.vertices, axis=1).max()) for b in assembly.bodies)
        self.samples, self.tracking = [], {}
        self.require_grasps = False

    def act(self, obs):
        if self.require_grasps:
            hands = obs["privileged"]["world"]["grasp"]["hands"]
            if any(hands[s]["phase"] != "holding" for s in PARTS):
                raise RuntimeError(f"Lost grasp during {self.phase}")
        return super().act(obs)

    def grasp_targets(self, bodies):
        result = {}
        tilt = np.deg2rad(20.)
        for side, (p, r) in bodies.items():
            sign = 1. if side == "right" else -1.
            forward = np.array([sign*np.cos(tilt), 0., -np.sin(tilt)])
            jaw = np.array([0., sign, 0.])
            turn = r*Rotation.from_matrix(np.column_stack((forward, jaw, np.cross(forward, jaw))))
            result[side] = (p+r.apply(self.grasp_points[side])+turn.apply([-.01381, 0., .00055]), turn)
        return result

    def follow_bodies(self, pose_at, seconds, phase):
        self.phase = phase
        start = self.time()
        elapsed, last_advance = 0., start
        tight = phase.startswith("assembly_")
        while True:
            fraction = min(1., elapsed/seconds)
            u = float(np.clip(fraction**3*(10+fraction*(-15+6*fraction)), 0., 1.))
            desired = pose_at(u)
            absolute, relative = self.tracking_error(desired)
            self.tracking = dict(phase=phase, progress=u, absolute_material_error_m=absolute,
                                 relative_material_error_m=relative)
            if fraction >= 1. and absolute < .0001 and relative < .0001:
                self.samples.append(dict(time_s=self.time(), **self.tracking))
                return
            if absolute < (.0007 if tight else .003) and (not tight or relative < .00012):
                elapsed = min(seconds, elapsed+self.dt)
                last_advance = self.time()
            if self.time()-start > max(40., seconds*24) or self.time()-last_advance > 12.:
                raise RuntimeError(f"Cube tracking stalled: {self.tracking}")
            yield {s: dict(position_world_m=p.tolist(), orientation_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist(),
                           gripper_position_m=self.grip)
                   for s, (p, r) in self.attached_targets(desired).items()}

    def actions(self):
        self.phase = "open_at_home"
        yield {s: dict(gripper_position_m=self.grip) for s in PARTS}
        yield from self.hold(.5)
        rest = self.bodies()
        grasp = self.grasp_targets(rest)
        outside = {s: (p-r.apply([.04, 0., 0.]), r) for s, (p, r) in grasp.items()}
        yield from self.move({s: (p+[0., 0., .07], r) for s, (p, r) in outside.items()}, 4., "home_to_pregrasp")
        yield from self.move(outside, 2., "descend_outside")
        yield from self.move(self.grasp_targets(self.bodies()), 2., "side_approach")
        self.phase, self.grip = "close_and_acquire", .002
        yield {s: dict(gripper_position_m=self.grip) for s in PARTS}
        yield from self.hold(1.)
        hands = self.obs["privileged"]["world"]["grasp"]["hands"]
        if any(hands[s]["phase"] != "holding" for s in PARTS):
            raise RuntimeError("External grasps not acquired: "+str({s: hands[s]["phase"] for s in PARTS}))
        self.require_grasps = True
        initial, tcp = self.bodies(), self.tcp()
        self.offsets = {s: (r.inv().apply(tcp[s][0]-p), r.inv()*tcp[s][1]) for s, (p, r) in initial.items()}
        yield from self.follow_bodies(lambda u: {s: (p+[0., 0., .08*u], r)
            for s, (p, r) in initial.items()}, 3., "lift")
        if self.part == "pickup":
            return
        rest_p, rest_r = rest["right"]
        gold_p, gold_r = rest_p+[0., 0., .08], rest_r
        _, entry = self.route[-1].pose(1.)
        target = {"right": (gold_p, gold_r), "left": (gold_p+gold_r.apply(entry), gold_r)}
        actual = self.bodies()
        turns = {s: Slerp([0., 1.], Rotation.from_quat([actual[s][1].as_quat(), r.as_quat()]))
                 for s, (_, r) in target.items()}
        yield from self.follow_bodies(lambda u: {s: (actual[s][0]+u*(p-actual[s][0]), turns[s](u))
            for s, (p, _) in target.items()}, 4., "approach_align")
        for motion in reversed(self.route):
            def poses(u, motion=motion):
                r, t = motion.pose(1.-u)
                return {"right": (gold_p, gold_r), "left": (gold_p+gold_r.apply(t), gold_r*Rotation.from_matrix(r))}
            phase = "assembly_insert" if motion.name == "extract_straight" else "assembly_lateral_slide"
            yield from self.follow_bodies(poses, motion.duration_s*2, phase)
        yield from self.follow_bodies(lambda u: {s: (gold_p+u*(rest_p-gold_p), gold_r)
            for s in PARTS}, 4., "place_assembly")
        self.require_grasps = False
        self.phase, self.grip = "release", .037
        yield {s: dict(gripper_position_m=self.grip) for s in PARTS}
        yield from self.hold(.3)
        retreat = {s: (p-r.apply([.08, 0., 0.]), r) for s, (p, r) in self.tcp().items()}
        yield from self.move(retreat, 3., "retreat")
        self.phase = "settle"
        yield from self.hold(4.)
