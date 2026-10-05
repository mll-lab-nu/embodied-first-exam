"""Object-level checks for the below-easy Slotted Post settings (very_easy, easier).

The ring starts around the post at its foot. Only cord that passes over the ring can hold it,
because the end discs cannot pass through the ring. Checked on the authored geometry:

1. Route: where the cord crosses the ring's radial band, it passes under or over the ring
   (below_easy.ring_band_runs). very_easy: under on both sides. easier: under on the near side,
   over on the far side only, where the over-runs belong to the loop between the two slot passes,
   which carries bead 2 and no disc.
2. very_easy: the ring lifts straight up off the post top, certified edge by edge with
   RigidPathChecker against post, base, cord, beads and discs (margin LIFT_MARGIN_M).
   easier: the same lift meets the cord, and bead 2 fits through the widest gap between ring
   and post (ring pushed against the post on the other side).

settle_check runs the FEM/IPC scene on the GPU with the robot held at home and repeats the
under/over test on the settled cord vertices in the settled ring's frame.
"""
from pathlib import Path

import fcl
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.slotted_post_ring import geometry_report, make_meshes
from topogym.config.registry import task_definition
from topogym.planning.rigid_reference.geometry import RigidPathChecker, matrix
from topogym.tasks.slotted_post_ring.below_easy import ring_band_runs

LIFT_MARGIN_M = .0002     # the ring rests 0.4 mm above the cord
SAMPLE_STEP_M = .001


def scene(variation):
    task = task_definition("slotted_post_ring", variation)()
    layout = task.make_layout()
    parts, cord = make_meshes(layout)
    return task, layout, parts, cord


def _lift(layout, parts):
    fixed = trimesh.util.concatenate([m for n, m in parts.items() if n not in ("target_ring",) and not n.startswith("stop_knot")])
    rise = layout.base_height_m + layout.post_height_m - layout.ring_z + layout.ring_tube_radius_m + .01
    return fixed, parts["target_ring"], (np.zeros(3), Rotation.identity()), (np.array([0., 0., rise]), Rotation.identity())


def lift_certified(layout, parts):
    fixed, ring, start, end = _lift(layout, parts)
    result = RigidPathChecker(fixed, ring, margin_m=LIFT_MARGIN_M).edge(start, end)
    return dict(passed=bool(result["passed"]), rise_m=float(end[0][2]),
                clearance_lower_bound_m=result.get("clearance_lower_bound_m"))


def lift_collides(layout, parts):
    """True if the straight lift meets anything (1 mm samples)."""
    fixed, ring, _, (top, _) = _lift(layout, parts)
    objects = []
    for mesh in (fixed, ring):
        model = fcl.BVHModel()
        model.beginModel(len(mesh.vertices), len(mesh.faces))
        model.addSubModel(np.asarray(mesh.vertices), np.asarray(mesh.faces, dtype=np.int32))
        model.endModel()
        objects.append(fcl.CollisionObject(model))
    for z in np.arange(SAMPLE_STEP_M, top[2], SAMPLE_STEP_M):
        t = matrix(np.array([0., 0., z]), Rotation.identity())
        objects[1].setTransform(fcl.Transform(t[:3, :3], t[:3, 3]))
        if fcl.collide(*objects, fcl.CollisionRequest(), fcl.CollisionResult()):
            return True
    return False


def widest_gap_m(layout):
    """Gap between ring and post face when the ring is pushed against the post on the other side."""
    inner, w, d = layout.ring_inner_radius, layout.post_width_m / 2, layout.post_depth_m / 2
    shift = np.sqrt(inner ** 2 - w ** 2) - d
    return float(inner + shift - d)


def loop_runs_between_slot_passes(layout, cord):
    """The far-side over-runs lie between the cord's two slot passes (the loop that carries bead 2)."""
    passes = [i for i in np.flatnonzero(cord[:-1, 1] * cord[1:, 1] < 0) if abs(cord[i, 0]) < layout.slot_width_m / 2]
    if len(passes) != 2:
        return False
    r = np.hypot(cord[:, 0], cord[:, 1])
    over = (r < layout.ring_major_radius_m + layout.ring_tube_radius_m + layout.rope_radius_m) & (
        cord[:, 2] > layout.ring_z + layout.ring_tube_radius_m + layout.rope_radius_m) & (cord[:, 1] > 0) & (
        r > layout.ring_inner_radius - layout.rope_radius_m)
    return bool(over.any() and passes[0] < np.flatnonzero(over).min() and np.flatnonzero(over).max() < passes[1])


def check_variant(variation):
    """Design report for one below-easy setting: 'very_easy', 'easier', or why neither."""
    task, layout, parts, cord = scene(variation)
    report = geometry_report(layout, parts, cord)
    runs = ring_band_runs(layout, cord)
    result = dict(variation_id=task.variation_id, instance_id=task.instance_id, cord_route=task.config["cord_route"],
                  geometry_passed=report["passed"], route_checks={k: v for k, v in report["checks"].items()},
                  cord_length_m=report["cord_length_m"], ring_runs=runs,
                  scope="authored geometry, cord frozen; no robot, IK or physics")
    if not report["passed"]:
        return dict(result, design="invalid_geometry")
    if runs and all(kind == "under" for _, kind in runs):
        lift = lift_certified(layout, parts)
        return dict(result, design="very_easy" if lift["passed"] else "no_certified_lift", lift=lift)
    near_under = all(kind == "under" for side, kind in runs if side < 0)
    far_over = [kind for side, kind in runs if side > 0] == ["over", "over"]
    gap, bead = widest_gap_m(layout), 2 * layout.bead_radius_m
    easier = (near_under and far_over and loop_runs_between_slot_passes(layout, cord)
              and lift_collides(layout, parts) and bead + 2 * layout.rope_radius_m < gap)
    return dict(result, design="easier" if easier else "blocked", widest_gap_m=gap, bead_diameter_m=bead)


def settle_check(variation, output, *, seconds=2., seed=0):
    """Hold the robot at home on the GPU; report ring motion and the under/over test on the settled cord."""
    from topogym.simulator import Env, SimulatorConfig
    config = SimulatorConfig(task_id="slotted_post_ring", variation_id=variation, compute_backend="cuda",
                             enable_rgb=False, max_physics_steps=None, work_dir=Path(output) / "scene")
    with Env(config) as env:
        env.reset(seed=seed)
        hold = {name: {"joint_position_rad": list(group["joint_position_rad"])}
                for name, group in env._robot.observe().items()}
        start = env._world.read_state()
        steps = int(round(seconds / (config.physics_dt_s * config.control_decimation)))
        for _ in range(steps):
            env.step(hold)
        end = env._world.read_state()
        task, layout = env._task, env._task.layout
        ring0, ring1 = (np.asarray(s["bodies"]["target_ring"]["position_m"]) for s in (start, end))
        q = np.asarray(end["bodies"]["target_ring"]["quaternion_wxyz"])
        cord = np.asarray(end["fem"]["cord"]["position_m"])
        cord0 = np.asarray(start["fem"]["cord"]["position_m"])
        ipc = end.get("ipc", {})
        # The ring body's origin is the assembly origin; its centre sits ring_z above it.
        local = Rotation.from_quat(q[[1, 2, 3, 0]]).inv().apply(cord - ring1) - [0., 0., layout.ring_z]
        r = np.hypot(local[:, 0], local[:, 1])
        band = (r > layout.ring_inner_radius) & (r < layout.ring_major_radius_m + layout.ring_tube_radius_m)
        above = band & (local[:, 2] > layout.ring_tube_radius_m)
        below = band & (local[:, 2] < -layout.ring_tube_radius_m)
        far = local[:, 1] > 0
        return dict(variation_id=task.variation_id, instance_id=task.instance_id, seconds=steps * config.physics_dt_s * config.control_decimation,
                    backend="cuda", physics_dt_s=config.physics_dt_s, solver_substeps=config.solver_substeps,
                    ring_translation_mm=float(np.linalg.norm(ring1 - ring0) * 1000),
                    ring_tilt_deg=float(np.degrees(np.arccos(np.clip(Rotation.from_quat(q[[1, 2, 3, 0]]).apply([0, 0, 1])[2], -1, 1)))),
                    cord_max_displacement_mm=float(np.linalg.norm(cord - cord0, axis=1).max() * 1000),
                    cord_vertices_over_ring={"near": int((above & ~far).sum()), "far": int((above & far).sum())},
                    cord_vertices_under_ring={"near": int((below & ~far).sum()), "far": int((below & far).sum())},
                    ipc_valid=ipc.get("native_valid"), terminated=bool(task.result.terminated), reason=task.result.reason)


if __name__ == "__main__":
    import argparse
    from topogym.utils.io import write_json_atomic
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variant", required=True, choices=("very_easy", "easier"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--settle-seconds", type=float, default=0., help="also settle the FEM scene on the GPU")
    args = parser.parse_args()
    report = check_variant(args.variant)
    if args.settle_seconds:
        report["settle"] = settle_check(args.variant, args.output, seconds=args.settle_seconds)
    write_json_atomic(args.output / "below_easy_check.json", report)
    print(report["variation_id"], report["design"], report.get("settle", ""))
