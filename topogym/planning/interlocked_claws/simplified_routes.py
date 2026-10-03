"""Object routes for the approved low tiers; continuously checked before use."""
from dataclasses import dataclass
from tempfile import TemporaryDirectory
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.assets.variation_resources import read_json
from topogym.config.registry import task_definition
from topogym.planning.rigid_reference.geometry import RigidPathChecker, interpolate, pose_dict
from topogym.planning.rigid_reference.feedback import body_pose


PARTS = {"left": "piece_0", "right": "piece_1"}


@dataclass
class Motion:
    phase: str
    start: tuple
    end: tuple
    seconds: float

    def at(self, u):
        return interpolate(self.start, self.end, u)


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
        record = read_json("variations/interlocked_claws/easier/reference_route.json")
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
    """Recheck measured entry; hold the blue piece at its acquired pose."""
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
    destination = (base_r.inv().apply(target_p-base_p), base_r.inv()*target_r)
    transfer = checker.edge(local[-1].end, destination)
    if not transfer["passed"]:
        raise ValueError("Goal transfer intersects the other piece: "+str(transfer))
    local.append(Motion("transfer_into_goal", local[-1].end, destination, 8.))
    audit.update(measured_entry=entry, goal_transfer=transfer)
    world = [Motion(m.phase, (base_p+base_r.apply(m.start[0]), base_r*m.start[1]),
                    (base_p+base_r.apply(m.end[0]), base_r*m.end[1]), m.seconds) for m in local]
    return world, audit
