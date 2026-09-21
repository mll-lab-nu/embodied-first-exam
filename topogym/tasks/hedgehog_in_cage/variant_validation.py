"""Geometry witness and robot preflight for a sampled, saved instance.

This qualifies a planning instance, never a dynamically successful episode.
The continuous bound applies to the frozen object path, while robot checks are
explicitly discrete joint-space checks. Release dynamics require a later run.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import fcl
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from topogym.robot.assets import robot_asset
from topogym.robot.gripper import robotiq_joint_targets
from .family_runtime import RobotAudit
from .family_geometry import evaluate
from .inverse_window import Kinematics, SolidOracle
from .variants import prototype, identity, rules, save, file_sha, generator_version, families_for_version, LEGACY_VERSION


def frame(cfg):
    return (np.r_[cfg.task.center_xy_m, float(cfg.env.frames.table_surface.origin[2]) + .22],
            Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True))


def build_assets(cfg, output):
    source, core, _ = prototype(str(cfg.task.randomization.family_id), verify_assets=True)
    assets = Path(output) / "assets"
    shutil.copytree(source / "assets", assets)
    shutil.copy2(source / "grasp.json", Path(output) / "grasp.json")
    shutil.copy2(source / "motion.json", Path(output) / "object_witness.json")
    d, p = cfg.task.derived_variant, cfg.task.randomization
    transform = np.eye(4)
    transform[:3, :3] = np.diag([d.cage_radial_scale, d.cage_radial_scale, d.cage_height_scale])
    anchor = np.array(d.cage_scale_origin_m)
    transform[:3, 3] = anchor - transform[:3, :3] @ anchor
    geometry_changed = not np.array_equal(transform, np.eye(4))
    maximum = 0.
    cage_cells = []
    for file in sorted(assets.glob("cage_collision_*.obj")):
        mesh = trimesh.load(file, force="mesh", process=False)
        before = mesh.vertices.copy()
        mesh.apply_transform(transform)
        maximum = max(maximum, float(np.linalg.norm(mesh.vertices - before, axis=1).max()))
        if not mesh.is_watertight or not mesh.is_convex:
            raise ValueError("Invalid affine collider")
        if geometry_changed:
            file.write_text(trimesh.exchange.obj.export_obj(mesh, digits=12))
        cage_cells.append(mesh)
    if geometry_changed:
        for file in sorted(assets.glob("counterfactual_closed_stem_*.obj")):
            mesh=trimesh.load(file,force="mesh",process=False)
            mesh.apply_transform(transform)
            file.write_text(trimesh.exchange.obj.export_obj(mesh,digits=12))
    if maximum > float(d.maximum_design_displacement_m) + 1e-10:
        raise ValueError("Cage deformation exceeded the certified clearance budget")
    if geometry_changed:
        mesh = trimesh.load(assets / "cage.obj", force="mesh", process=False)
        mesh.apply_transform(transform)
        (assets / "cage.obj").write_text(trimesh.exchange.obj.export_obj(mesh, digits=12))
        # Recompute the same additive-parts mass model used by the prototype.
        tree = ET.parse(assets / "cage.urdf")
        inertial = tree.getroot().find("link/inertial")
        original_volume = sum(trimesh.load(f, force="mesh").volume
                              for f in (source / "assets").glob("cage_collision_*.obj"))
        density = float(inertial.find("mass").attrib["value"]) / original_volume
        aggregate = trimesh.util.concatenate(cage_cells)
        aggregate.density = density
        props = aggregate.mass_properties
        inertial.find("origin").set("xyz", " ".join(map(str, props.center_mass)))
        inertial.find("mass").set("value", str(props.mass))
        for a, b, i, j in (("x", "x", 0, 0), ("y", "y", 1, 1), ("z", "z", 2, 2),
                           ("x", "y", 0, 1), ("x", "z", 0, 2), ("y", "z", 1, 2)):
            inertial.find("inertia").set(f"i{a}{b}", str(props.inertia[i, j]))
        ET.indent(tree)
        tree.write(assets / "cage.urdf", encoding="unicode", xml_declaration=True)
    for name, tint in (("cage", float(p.cage_wood_tint)), ("hedgehog", float(p.ball_wood_tint))):
        if (name == "cage" and geometry_changed) or tint != 1 or p.wood_roughness_delta != 0:
            visual = trimesh.load(assets / f"{name}.glb", force="mesh", process=False)
            if name == "cage":
                visual.apply_transform(transform)
            material = visual.visual.material
            material.baseColorFactor = np.rint(np.array([tint, tint, tint, 1.]) * 255).astype(np.uint8)
            material.roughnessFactor = (.67 if name == "cage" else .62) + float(p.wood_roughness_delta)
            visual.export(assets / f"{name}.glb", include_normals=True)
    frozen_files = [assets / "hedgehog.urdf", *assets.glob("hedgehog_collision_*.obj")]
    if any(file_sha(f) != file_sha(source / "assets" / f.name) for f in frozen_files):
        raise ValueError("The ball collision, mass or grasp geometry changed")
    bound = core["parent_path_clearance_lower_bound_m"] - maximum - 1e-8
    if bound < rules(generator_version(cfg.task))["acceptance"]["minimum_object_witness_clearance_m"]:
        raise ValueError("Insufficient continuous object-path clearance")
    report = dict(passed=True, family=str(p.family_id), parent_manifest_sha256=core["manifest_sha256"],
        maximum_cage_vertex_displacement_m=maximum, affine_transform=transform.tolist(),
        continuous_object_witness_clearance_lower_bound_m=bound,
        bound_method="parent exact frozen SE3 path bound minus affine vertex displacement minus 1e-8 export allowance",
        cage_bottom_fixed=True, ball_collision_and_inertia_identical=True,
        collision_cells=dict(cage=len(cage_cells), hedgehog=len(list(assets.glob("hedgehog_collision_*.obj")))),
        parent_physics_passed=True, descendant_physics="not_run")
    # Replace stale parent reports, keeping the exact fixed-mode asset bytes.
    if geometry_changed or p.cage_wood_tint != 1 or p.ball_wood_tint != 1 or p.wood_roughness_delta != 0:
        save(assets / "asset_report.json", report)
        save(assets / "sha256.json", {f.name: file_sha(f) for f in sorted(assets.iterdir())
                                      if f.is_file() and f.name != "sha256.json"})
    return report


class InstanceKinematics(Kinematics):
    """Reuse the established solver with explicit instance inputs, no run paths."""
    def __init__(self, cfg, folder, q):
        self.model = mujoco.MjModel.from_xml_path(robot_asset(cfg.robot_control))
        self.data = mujoco.MjData(self.model)
        self.q = np.array(q, dtype=float)
        if self.q.shape != (self.model.nq,):
            raise ValueError("Robot qpos dimension changed")
        self.hand = self.model.body("hand").id
        self.mount = np.array(cfg.env.robot_mount.pos)
        self.cage_origin, self.cage_r = frame(cfg)
        grasp = json.loads((Path(folder) / "grasp.json").read_text())
        self.hand_p = np.array(grasp["hand_position_in_ball"])
        self.hand_r = Rotation.from_quat(grasp["hand_quaternion_in_ball_xyzw"])


class InstanceAudit(RobotAudit):
    def __init__(self, cfg, folder, kin):
        self.kin = kin
        m = kin.model
        self.oracle = SolidOracle(Path(folder) / "assets")
        fixed = fcl.Transform(kin.cage_r.as_matrix(), kin.cage_origin)
        for obj in self.oracle.objects[0]:
            obj.setTransform(fixed)
        self.oracle.managers[0].update()
        self.geoms = []
        for i in range(m.ngeom):
            if not (m.geom_contype[i] or m.geom_conaffinity[i]):
                continue
            if m.geom_type[i] == mujoco.mjtGeom.mjGEOM_MESH:
                mesh = m.mesh(m.geom_dataid[i])
                vertices = m.mesh_vert[mesh.vertadr[0]:mesh.vertadr[0]+mesh.vertnum[0]]
                hull = trimesh.convex.convex_hull(vertices)
                shape = fcl.Convex(hull.vertices, len(hull.faces),
                    np.column_stack([np.full(len(hull.faces), 3), hull.faces]).ravel())
                vertices = hull.vertices
            elif m.geom_type[i] == mujoco.mjtGeom.mjGEOM_BOX:
                size = m.geom_size[i]
                shape = fcl.Box(*(2 * size))
                vertices = trimesh.bounds.corners(np.array([-size, size]))
            else:
                raise ValueError("Unvalidated robot collider type")
            self.geoms.append((i, m.body(m.geom_bodyid[i]).name, fcl.CollisionObject(shape), vertices))
        self.all_robot = fcl.DynamicAABBTreeCollisionManager()
        self.all_robot.registerObjects([g[2] for g in self.geoms])
        self.all_robot.setup()
        self.nonfinger = fcl.DynamicAABBTreeCollisionManager()
        self.nonfinger.registerObjects([g[2] for g in self.geoms if g[1] not in ("left_finger", "right_finger")])
        self.nonfinger.setup()
        mount_r = Rotation.from_euler("z", float(cfg.task.mount_yaw_delta_deg), degrees=True)
        self.mount = fcl.CollisionObject(fcl.Box(.22, .22, .10),
            fcl.Transform(mount_r.as_matrix(), np.r_[cfg.task.center_xy_m, kin.cage_origin[2] - .17]))


def negative_paths(trace):
    """Regenerate entire controls; an old first-contact point is not robust.

    A small cage deformation can move the first collision further along an
    otherwise still-blocked path. Checking only that old point falsely rejects
    valid perturbations and biases the seed distribution.
    """
    if "negative_paths" in trace:
        return {name: np.asarray(path) for name,path in trace["negative_paths"].items()}
    first = np.array(trace["frames"][0]["ball_pose"])
    path = np.array(trace["proposed_path"])
    seed = np.array(trace["seed_path"])
    pull = path[-1].copy()
    pull[3:] = first[3:]
    up, down = first.copy(), first.copy()
    up[2] += .30
    down[2] -= .30
    controls = dict(original_route=seed, straight_pull=[first, pull],
                    straight_lift=[first, up], straight_lower=[first, down])
    if trace["family"] == "oblique_gate":
        ablation = path.copy()
        ablation[:, 1] = seed[:, 1]
        controls["remove_lateral_excursion"] = ablation
    elif trace["family"] == "staggered_gates":
        controls["skip_second_gate_alignment"] = np.array([*path[:9], path[-1]])
    else:
        unturned = path.copy()
        unturned[:, 3:] = seed[:, 3:]
        controls["advance_without_added_turn"] = unturned
        prerotated = path.copy()
        prerotated[:, 3:] = (Rotation.from_euler("z", 36, degrees=True)*Rotation.from_quat(seed[:, 3:])).as_quat()
        controls["rotate_first_then_advance"] = np.array([first, *prerotated])
    return controls


def qualify(cfg, folder, geometry):
    folder = Path(folder)
    source, _, _ = prototype(str(cfg.task.randomization.family_id))
    witness = json.loads((folder / "object_witness.json").read_text())
    oracle = SolidOracle(folder / "assets")
    controls = {name: evaluate(oracle, path) for name, path in negative_paths(witness).items()}
    if not all(control["collision_found"] for control in controls.values()):
        raise ValueError("A family-defining negative path became free")
    geometry_controls={}
    blockers=[trimesh.load(p,force="mesh") for p in sorted((folder/"assets").glob("counterfactual_closed_stem_*.obj"))]
    if str(cfg.task.randomization.family_id)=="gen_keyhole" and not blockers:
        raise ValueError("Missing keyhole mechanism control")
    if blockers:
        from .side_window_probe import Oracle
        ball_cells=[trimesh.load(p,force="mesh") for p in sorted((folder/"assets").glob("hedgehog_collision_*.obj"))]
        geometry_controls["closed_keyhole_stem"]=evaluate(Oracle(blockers,ball_cells),witness["proposed_path"])
        if not geometry_controls["closed_keyhole_stem"]["collision_found"]:
            raise ValueError("The keyhole stem became unnecessary for the stored solution")
    cross_controls = {}
    version_id = generator_version(cfg.task)
    for other in families_for_version(version_id):
        if other == str(cfg.task.randomization.family_id):
            continue
        other_folder, _, manifest = prototype(other)
        if file_sha(other_folder / "motion.json") != manifest["files_sha256"]["motion.json"]:
            raise ValueError("Cross-family reference motion changed")
        trace = json.loads((other_folder / "motion.json").read_text())
        for i, row in enumerate(trace["frames"][:trace["extraction_last_frame"]+1]):
            if oracle.distance(np.array(row["ball_pose"])) < 0:
                cross_controls[other] = dict(blocked=True, frame=i, witness_pose=row["ball_pose"])
                break
        else:
            if version_id == LEGACY_VERSION:
                raise ValueError(f"Other-family witness {other} no longer blocked")
            cross_controls[other] = dict(blocked=False)
        if version_id != LEGACY_VERSION:
            cross_controls[other]["interpretation"] = "diagnostic only: the families may have different spike geometry and share motion strategies"
    kin = InstanceKinematics(cfg, folder, witness["frames"][0]["qpos"])
    frames = []
    position_error = rotation_error = 0.
    for i, original in enumerate(witness["frames"]):
        target = np.array(original["ball_pose"])
        actual = kin.solve(target)
        position_error = max(position_error, float(np.linalg.norm(actual[:3] - target[:3])))
        rotation_error = max(rotation_error, float((Rotation.from_quat(actual[3:]) * Rotation.from_quat(target[3:]).inv()).magnitude()))
        frames.append(dict(qpos=kin.q.tolist(), ball_pose=actual.tolist(),
                           witness_ball_pose=target.tolist(), stage=original["stage"], attached=True))
        if i % 200 == 0:
            print(f"IK {cfg.task.randomization.family_id}: {i}/{len(witness['frames'])}", flush=True)
    # Open at the placed pose, then withdraw vertically. These are planning
    # states with a fixed placed ball; settling/contact success is not inferred.
    release_pose = kin.ball_pose()
    released_world = (kin.cage_origin + kin.cage_r.apply(release_pose[:3]),
                      (kin.cage_r * Rotation.from_quat(release_pose[3:])).as_quat())
    closed = kin.q.copy()
    opened = closed.copy()
    for name, value in robotiq_joint_targets(.085).items():
        name = {"right_driver_joint": "finger_joint1", "left_driver_joint": "finger_joint2"}.get(name, "r85_" + name)
        opened[kin.model.joint(name).qposadr[0]] = value
    for t in np.linspace(0, 1, 25)[1:]:
        q = (1-t)*closed + t*opened
        frames.append(dict(qpos=q.tolist(), ball_pose=release_pose.tolist(), stage="open_gripper", attached=False))
    kin.q[:] = opened
    for height in np.linspace(0, .08, 41)[1:]:
        target = release_pose.copy()
        target[2] += height
        kin.solve(target)
        frames.append(dict(qpos=kin.q.tolist(), ball_pose=release_pose.tolist(), stage="retreat", attached=False))
    audit = InstanceAudit(cfg, folder, kin)
    checks = 0
    min_gap = float("inf")
    step = float(rules(version_id)["acceptance"]["maximum_robot_joint_sample_step_rad"])
    for i, row in enumerate(frames):
        following = frames[min(i+1, len(frames)-1)]
        qa, qb = np.array(row["qpos"]), np.array(following["qpos"])
        n = max(1, int(np.ceil(np.max(abs(qb-qa))/step)))
        for t in np.linspace(0, 1, n+1)[:-1]:
            q = (1-t)*qa+t*qb
            errors = audit.check(q, ball_world=None if row["attached"] else released_world)
            if errors:
                raise ValueError(f"Robot clearance at {i}/{row['stage']}: {errors}")
            pose = kin.ball_pose() if row["attached"] else release_pose
            distance = float(oracle.distance(pose))
            min_gap = min(min_gap, distance)
            if distance < .0005:
                raise ValueError(f"Ball/cage clearance at interpolated robot state {i}: {distance}")
            checks += 1
        if i % 200 == 0:
            print(f"Collision audit {i}/{len(frames)}", flush=True)
    result = dict(passed=True, instance_sha256=identity(cfg), geometry=geometry,
        robot_ik=dict(passed=True, frames=len(frames), max_position_error_m=position_error,
                      max_rotation_error_rad=rotation_error, continuous_branch=True),
        robot_clearance=dict(passed=True, samples=checks, maximum_joint_sample_step_rad=step,
                             minimum_sampled_ball_cage_gap_m=min_gap,
                             scope="discrete whole-robot/table/mount/cage/held-ball plus open/retreat; not a continuous robot certificate"),
        finite_controls=controls, cross_family_controls=cross_controls, unique_solution_proven=False,
        geometry_ablation_controls=geometry_controls,
        physical_execution="not_run", export_ready=False)
    motion = dict(family=str(cfg.task.randomization.family_id), frames=frames,
        extraction_last_frame=witness["extraction_last_frame"],
        release_last_attached_frame=len(witness["frames"])-1,
        pregrasp_start=True, contact_triggered_assistance=True,
        simulated=False, final_settle_required=True, instance_sha256=identity(cfg))
    return result, motion
