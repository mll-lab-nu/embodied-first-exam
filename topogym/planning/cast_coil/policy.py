"""Registered Coil geometry/routes and the original three feedback policies.

The policy reads the explicitly granted world observation and emits EE_ABS.
Contact-triggered grasp assistance belongs to the simulator, not the policy.
"""
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.cast_coil import CoilAssembly
from topogym.assets.variation_resources import read_json
from topogym.config.registry import task_definition
from topogym.planning.motions.cast_coil import prototype_route, variant_route
from .baseline import CastCoilBaselinePolicy, PARTS


def variant_reference(variant, *, task_parameters=None, seed=0):
    """Resolve geometry and motion together, including the frozen 9 mm value."""
    task = task_definition("cast_coil", variant, seed)(task_parameters, seed=seed)
    if getattr(task, "geometry_resource", None):
        from topogym.assets.geometry.cast_coil_simplified import SimplifiedCoilAssembly
        from topogym.utils.geometry.rigid_motion import RigidMotionSegment
        assembly = SimplifiedCoilAssembly(record=task.geometry())
        s = assembly.record["parameters"]["slide_mm"]*.001
        entry = np.array([0., s, 0.])
        route = []
        if s:
            route.append(RigidMotionSegment("slide_to_offset", 2., np.eye(3), np.zeros(3), entry))
        route.append(RigidMotionSegment("extract_straight", 3., np.eye(3), entry,
                                        entry+[.08*task.config["scale"], 0., 0.]))
        return assembly, route
    template = read_json(task.template_resource) if task.template_resource else None
    assembly = CoilAssembly(template=template, scale=float(task.config["scale"]))
    if template is None:
        route = prototype_route(assembly)
    else:
        design = template["inverse_design"]
        route = variant_route(design["kind"], design["parameters"])
    return assembly, route


class CastCoilPolicy(CastCoilBaselinePolicy):
    """Pause path time when measured tracking leaves its local error budget."""

    def __init__(self, *, body_origins, variant="easy", part="all"):
        assembly, route = variant_reference(variant)
        if hasattr(assembly, "record"):
            raise ValueError("Use SimplifiedCoilPolicy for the cube variants")
        super().__init__(body_origins=body_origins, part=part, route=route)
        self.place_from_rest = "inverse_design" in assembly.template
        self.variant = variant
        self.radius = max(float(np.linalg.norm(body.visual.vertices, axis=1).max())
                          for body in assembly.bodies)
        self.samples = []
        self.tracking = {}

    def attached_targets(self, bodies):
        actual = self.bodies()
        targets = {}
        for side, (position, turn) in bodies.items():
            error = position-actual[side][0]
            angle = (turn*actual[side][1].inv()).as_rotvec()
            # Compensate gravity/servo deflection; the path clock is separately
            # gated, so error cannot grow just because nominal time advances.
            self.bias[side] = np.clip(self.bias[side]+4*self.dt*error, -.10, .10)
            self.angle_bias[side] = np.clip(self.angle_bias[side]+4*self.dt*angle, -.3, .3)
            commanded = Rotation.from_rotvec(self.angle_bias[side]+.5*angle)*turn
            targets[side] = (position+self.bias[side]+.5*error+commanded.apply(self.offsets[side][0]),
                             commanded*self.offsets[side][1])
        return targets

    def tracking_error(self, desired):
        actual = self.bodies()
        absolute = max(float(np.linalg.norm(p-actual[s][0])) +
                       self.radius*float((r*actual[s][1].inv()).magnitude())
                       for s, (p, r) in desired.items())
        def relative(poses):
            gp, gr = poses["right"]
            sp, sr = poses["left"]
            return gr.inv().apply(sp-gp), gr.inv()*sr
        p, r = relative(desired)
        ap, ar = relative(actual)
        relative_error = float(np.linalg.norm(p-ap))+self.radius*float((r*ar.inv()).magnitude())
        return absolute, relative_error

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
            if fraction >= 1 and absolute < .00025 and relative < .00025:
                self.samples.append(dict(time_s=self.time(), **self.tracking))
                return
            # Absolute error matters in free space; in the narrow channel the
            # relative pose additionally determines whether progress is safe.
            can_advance = absolute < (.001 if tight else .004) and (not tight or relative < .00035)
            if can_advance:
                elapsed = min(seconds, elapsed+self.dt)
                last_advance = self.time()
            # Narrow passages can advance slowly while continuing to converge.
            # Keep the no-progress deadline separate from the nominal route
            # duration; the manager also enforces the episode time budget.
            if self.time()-start > max(30., seconds*24) or self.time()-last_advance > 12.:
                raise RuntimeError(f"Coil tracking stalled: {self.tracking}")
            targets = self.attached_targets(desired)
            yield {s: dict(position_world_m=p.tolist(),
                           orientation_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist(),
                           gripper_position_m=self.grip) for s, (p, r) in targets.items()}
