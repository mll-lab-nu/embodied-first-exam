"""Object routes for the approved low tiers; continuously checked before use."""
from dataclasses import dataclass
from tempfile import TemporaryDirectory
from pathlib import Path
import json

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.config.registry import task_definition
from topogym.planning.rigid_reference.geometry import RigidPathChecker, interpolate, pose_dict
from topogym.planning.rigid_reference.feedback import body_pose


PARTS = {"left": "piece_0", "right": "piece_1"}


def read_reference_route():
    # Authoring data belongs with the planner: benchmark images strip this
    # directory, while task geometry remains available without a solution.
    return json.loads(Path(__file__).with_name("easier_reference_route.json").read_text())


@dataclass
class Motion:
    phase: str
    start: tuple
    end: tuple
    seconds: float
    right_start: tuple | None = None
    right_end: tuple | None = None

    def at(self, u):
        return interpolate(self.start, self.end, u)

    def bodies_at(self, u):
        if self.right_start is None or self.right_end is None:
            raise ValueError("World motion requires both arm references")
        return {"left": self.at(u), "right": interpolate(self.right_start, self.right_end, u)}


def reference(variant):
    task = task_definition("interlocked_claws", variant)()
    if task.family_id not in {"shallow_l_hooks", "cross_square_offset"}:
        raise ValueError("This reference supports only the approved two low tiers")
    with TemporaryDirectory(prefix="claws-reference-") as directory:
        assembly, _ = task.build_assets(Path(directory))
    checker = RigidPathChecker(assembly.bodies[1].mesh, assembly.bodies[0].mesh, margin_m=.0015)
    if task.family_id == "shallow_l_hooks":
        pivot = np.array([-.13, 0., -.022])
        turn = Rotation.from_euler("y", 12., degrees=True)
        shifted = pivot-turn.apply(pivot)
        poses = [(np.zeros(3), Rotation.identity()), (shifted, turn),
                 (shifted+[-.08, 0., 0.], turn), (np.array([-.09, 0., 0.]), Rotation.identity())]
        phases = ["unhook_small_turn", "separate_short_legs", "restore_attitude"]
    else:
        record = read_reference_route()
        if record["model_revision"] != task.model_revision:
            raise ValueError("Cross route does not match this model revision")
        poses = [body_pose(p) for p in record["poses"]]
        phases = [f"thread_cross_{i:02d}" for i in range(1, len(poses))]
        phases[-1] = "separate_cross"
    if not checker.initial_free(poses[0]):
        raise ValueError("Reference starts in collision or containment")
    audits = [checker.edge(a, b) for a, b in zip(poses, poses[1:])]
    if not all(e["passed"] for e in audits):
        raise ValueError("Uncertified object route: "+str(audits))
    motions = [Motion(phase, a, b, max(1.2, np.linalg.norm(b[0]-a[0])/.025,
                    (b[1]*a[1].inv()).magnitude()/.22))
               for phase, a, b in zip(phases, poses, poses[1:])]
    wrong_pull = checker.edge(poses[0], (np.array([-.04, 0., 0.]), Rotation.identity()))
    if wrong_pull["passed"]:
        raise ValueError("The straight-pull negative control unexpectedly passes")
    return task, assembly, checker, motions, dict(
        model_revision=task.model_revision, object_route_verified=True,
        poses=[pose_dict(p) for p in poses], edges=audits, straight_pull=wrong_pull,
        clearance_margin_m=checker.margin, robot_path_verified=False, physics_verified=False)


def world_route(variant, initial, region):
    """Recheck the measured entry and share separation between both hands."""
    task, assembly, checker, motions, audit = reference(variant)
    base_p, base_r = initial["right"]
    p, r = initial["left"]
    start = (base_r.inv().apply(p-base_p), base_r.inv()*r)
    entry = checker.edge(start, motions[0].start)
    if not entry["passed"]:
        raise ValueError("Measured grasp cannot connect to the reference: "+str(entry))
    local = [Motion("align_acquired_grasps", start, motions[0].start, 1.)]+motions
    # Place the entire target's bounds within the current task's fixed zone;
    # continued grasping is allowed, so do not introduce a release stage.
    bounds = assembly.bodies[0].mesh.bounds
    target_r = Rotation.identity()
    target_p = np.r_[region["center_xy_m"], region["table_height_m"]+region["placement_height_m"]/2]-bounds.mean(0)
    # Share the axial separation between the two hands. Holding the blue hand
    # fixed puts the brown wrist too close to its base during attitude recovery.
    def common(p):
        return np.array([np.clip(-.5*p[0], 0., .045), 0., 0.])
    final_common = common(local[-1].end[0])
    destination = (base_r.inv().apply(target_p-base_p)-final_common, base_r.inv()*target_r)
    transfers = []
    if task.family_id == "cross_square_offset":
        # Clear the square laterally before moving back toward its x plane.
        # A direct diagonal toward the zone clips a corner of the frame.
        lateral = (np.array([local[-1].end[0][0], destination[0][1], local[-1].end[0][2]]), local[-1].end[1])
        transfers.append(Motion("clear_frame_side", local[-1].end, lateral, 7.))
    transfers.append(Motion("transfer_into_goal", transfers[-1].end if transfers else local[-1].end, destination, 8.))
    transfer_edges = [checker.edge(m.start, m.end) for m in transfers]
    if not all(e["passed"] for e in transfer_edges):
        raise ValueError("Goal transfer intersects the other piece: "+str(transfer_edges))
    audit.update(measured_entry=entry, goal_transfer=dict(passed=True, edges=transfer_edges))
    world = []
    for index, m in enumerate(local+transfers):
        ca, cb = (common(m.start[0]), common(m.end[0])) if index < len(local) else (final_common, final_common)
        world.append(Motion(m.phase, (base_p+base_r.apply(m.start[0]+ca), base_r*m.start[1]),
                            (base_p+base_r.apply(m.end[0]+cb), base_r*m.end[1]), m.seconds,
                            (base_p+base_r.apply(ca), base_r), (base_p+base_r.apply(cb), base_r)))
    return world, audit
