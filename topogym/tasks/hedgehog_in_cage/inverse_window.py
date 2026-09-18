"""Trajectory-first eccentric window: vary solved IK, then infer a cage opening."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import fcl
import mujoco
import numpy as np
from omegaconf import OmegaConf
from scipy.optimize import least_squares, linprog
from scipy.spatial.transform import Rotation
import trimesh

from topogym.robot.assets import robot_asset
from topogym.robot.gripper import robotiq_joint_targets
from .geometry import ROOT, HedgehogLayout, load_template, clearance_samples, write_body, band_mesh
from .plan_escape import interpolate

SEED = ROOT / "runs/demo_metadata/hedgehog_in_cage/2026-09-16_classic_wood"
OUTPUT = ROOT / "runs/environment-solvability/hedgehog_in_cage/eccentric_window_v1"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def config():
    return OmegaConf.load(SEED / "extraction_config.yaml")


class Kinematics:
    def __init__(self):
        cfg = config()
        self.model = mujoco.MjModel.from_xml_path(robot_asset(cfg.robot_control))
        self.data = mujoco.MjData(self.model)
        self.q = np.zeros(self.model.nq)
        self.q[:7] = np.load(SEED / "robot_escape_plan.npz")["arm_qpos"][0]
        for name, value in robotiq_joint_targets(.0055).items():
            name = {"right_driver_joint": "finger_joint1", "left_driver_joint": "finger_joint2"}.get(name, "r85_" + name)
            self.q[self.model.joint(name).qposadr[0]] = value
        self.hand = self.model.body("hand").id
        self.mount = np.array(cfg.env.robot_mount.pos)
        self.cage_origin = np.r_[cfg.task.center_xy_m, float(cfg.env.frames.table_surface.origin[2]) + .22]
        self.cage_r = Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True)
        grasp = json.loads((SEED / "robot_escape_plan.json").read_text())["selected"]
        self.hand_p = np.array(grasp["hand_position_in_ball"])
        self.hand_r = Rotation.from_quat(grasp["hand_quaternion_in_ball_xyzw"])

    def forward(self):
        self.data.qpos[:] = self.q
        mujoco.mj_forward(self.model, self.data)
        return self.data.xpos[self.hand].copy() + self.mount, Rotation.from_matrix(self.data.xmat[self.hand].reshape(3, 3))

    def ball_pose(self):
        p, r = self.forward()
        br = r * self.hand_r.inv()
        bp = p - br.apply(self.hand_p)
        return np.r_[self.cage_r.inv().apply(bp - self.cage_origin), (self.cage_r.inv() * br).as_quat()]

    def solve(self, pose):
        r = self.cage_r * Rotation.from_quat(pose[3:])
        p = self.cage_origin + self.cage_r.apply(pose[:3])
        target_p, target_r = p + r.apply(self.hand_p), r * self.hand_r
        previous = self.q[:7].copy()
        def error(q):
            self.q[:7] = q
            hp, hr = self.forward()
            return np.r_[20 * (hp - target_p), (hr * target_r.inv()).as_rotvec(), .00005 * (q - previous)]
        limits = self.model.jnt_range[:7]
        result = least_squares(error, previous, bounds=(limits[:, 0] + 1e-6, limits[:, 1] - 1e-6),
                               max_nfev=100, ftol=1e-11, xtol=1e-11, gtol=1e-11)
        e = error(result.x)
        if np.linalg.norm(e[:3]) / 20 > .00001 or np.linalg.norm(e[3:6]) > .0001:
            raise ValueError(f"IK error: {e}")
        if np.max(abs(self.q[:7] - previous)) > .2:
            raise ValueError("IK branch discontinuity")
        bad = [c.dist for c in self.data.contact if c.dist < -.0001]
        if bad:
            raise ValueError(f"Robot self collision: {bad}")
        return self.ball_pose()


def propose(output, shift_m=.006, tilt_deg=2.):
    original = json.loads((SEED / "escape_upper.json").read_text())
    path = np.array(original["path"])
    for i in range(2, 8):
        weight = np.sin(np.pi * (i - 1) / 7)
        path[i, 1] += shift_m * weight
        path[i, 3:] = (Rotation.from_euler("x", tilt_deg * weight, degrees=True) * Rotation.from_quat(path[i, 3:])).as_quat()
    proposal = dict(id="eccentric_window", geometry_pending=True, side_shift_m=shift_m,
        tilt_deg=tilt_deg, path=path.tolist(), source_solution_sha256=sha(SEED / "escape_upper.json"),
        source_robot_ik_sha256=sha(SEED / "robot_escape_plan.npz"),
        design_order="seed IK -> varied relative motion and continuous IK -> inferred cage window")
    save(output / "motion_proposal.json", proposal)
    kin = Kinematics()
    frames = []
    # First solve the entire extraction and placement, without a new cage.
    release = json.loads((SEED / "robot_release_plan.json").read_text())
    paths = [*path, *np.array(release["path"])[1:]]
    knot_indices = []
    for index, (a, b) in enumerate(zip(paths[:-1], paths[1:])):
        points = list(interpolate(a, b, .0025))[int(index > 0):]
        for u, pose in enumerate(points):
            actual = kin.solve(pose)
            frames.append(dict(qpos=kin.q.tolist(), ball_pose=actual.tolist(), segment=index,
                stage="rotate_and_extract" if index < len(path)-1 else release["phases"][index-len(path)+1]))
        knot_indices.append(len(frames)-1)
        print(f"IK segment {index+1}/{len(paths)-1}: {len(frames)} states", flush=True)
    result = dict(geometry_pending=True, frames=frames, knot_indices=knot_indices,
        extraction_last_frame=knot_indices[len(path)-2], proposed_path=path.tolist(),
        release_path=release["path"], release_phases=release["phases"],
        proposal_sha256=sha(output / "motion_proposal.json"), grasp_spike="S2")
    save(output / "ik_before_geometry.json", result)
    return result


def inverse_profile(trace, output):
    """Fit asymmetric angular window limits to a conservative sphere sweep.

    Each sphere covers the core or a sampled cylinder segment. Its intersection
    with the whole annular wall thickness is projected into angle/height. Bounds
    are constant within 2 mm vertical bins; a linear profile is constrained at
    both ends of every bin, so it encloses the entire conservative projection.
    """
    layout = HedgehogLayout(load_template(), 3.)
    points, radii = clearance_samples(layout, spacing=.0005)
    # Independent continuous verification is applied to final exported solids.
    sampling = .0004
    radii = radii + .0012 + sampling
    # Fixed S2 grasp: include the actual finger-pad boxes in the carving sweep.
    # Cuboid cells are covered by circumspheres, rather than just mesh vertices.
    kin = Kinematics(); kin.q = np.array(trace["frames"][0]["qpos"]); first = kin.ball_pose()
    br = kin.cage_r * Rotation.from_quat(first[3:])
    bp = kin.cage_origin + kin.cage_r.apply(first[:3])
    finger_points = []; finger_radii = []
    for i in range(kin.model.ngeom):
        name = kin.model.body(kin.model.geom_bodyid[i]).name
        if name not in ("left_finger", "right_finger") or not kin.model.geom_contype[i]: continue
        if kin.model.geom_type[i] != mujoco.mjtGeom.mjGEOM_BOX: raise ValueError("Unexpected finger collider")
        size = kin.model.geom_size[i]; count = np.maximum(1, np.ceil(2*size/.001).astype(int)); step = 2*size/count
        axes = [-s+(np.arange(n)+.5)*d for s, n, d in zip(size, count, step)]
        local = np.array(np.meshgrid(*axes, indexing="ij")).reshape(3, -1).T
        world = local@kin.data.geom_xmat[i].reshape(3, 3).T + kin.data.geom_xpos[i] + kin.mount
        finger_points.append(br.inv().apply(world-bp))
        finger_radii.append(np.full(len(local), np.linalg.norm(step)/2 + .0004 + sampling))
    points = np.concatenate([points, *finger_points]); radii = np.concatenate([radii, *finger_radii])
    sweep_radius = float(np.linalg.norm(points, axis=1).max())
    poses = [np.array(f["ball_pose"]) for f in trace["frames"][:trace["extraction_last_frame"]+1]]
    centers = []; selected_radii = []; pose_count = 0
    for i, (a, b) in enumerate(zip(poses[:-1], poses[1:])):
        for q in list(interpolate(a, b, sampling/max(1., sweep_radius/.092)))[int(i > 0):]:
            world = Rotation.from_quat(q[3:]).apply(points) + q[:3]; pose_count += 1
            rho = np.linalg.norm(world[:, :2], axis=1); phi = np.arctan2(world[:, 1], world[:, 0])
            keep = (np.maximum(np.maximum(.0585-rho, rho-.0675), 0) < radii) & (abs(phi) < np.deg2rad(75))
            centers.append(world[keep]); selected_radii.append(radii[keep])
    centers = np.concatenate(centers); rads = np.concatenate(selected_radii)
    rho = np.linalg.norm(centers[:, :2], axis=1)
    phi = np.arctan2(centers[:, 1], centers[:, 0])
    inner, outer = .0585, .0675
    radial_gap = np.maximum(np.maximum(inner-rho, rho-outer), 0.)
    selected = (radial_gap < rads) & (abs(phi) < np.deg2rad(75))
    centers, rads, rho, phi = centers[selected], rads[selected], rho[selected], phi[selected]
    bins = np.linspace(-.09, .09, 91)
    left, right = [], []
    for lo, hi in zip(bins[:-1], bins[1:]):
        dz = np.maximum(np.maximum(lo-centers[:, 2], centers[:, 2]-hi), 0.)
        radial2 = rads*rads-dz*dz
        eligible = radial2 > 0
        rr, rh, ph = radial2[eligible], rho[eligible], phi[eligible]
        best_r = np.clip(np.sqrt(np.maximum(rh*rh-rr, 0)), inner, outer)
        cosine = (rh*rh + best_r*best_r - rr)/(2*rh*best_r)
        use = cosine < 1
        angle = np.arccos(np.clip(cosine[use], -1, 1))
        low_angle, high_angle = ph[use]-angle, ph[use]+angle
        front = (low_angle < np.deg2rad(42.75)) & (high_angle > -np.deg2rad(42.75))
        # Preserve at least the central portion of the original opening.
        left.append(min(-np.deg2rad(20), float(np.min(low_angle[front], initial=0))))
        right.append(max(np.deg2rad(20), float(np.max(high_angle[front], initial=0))))
    left, right = np.array(left), np.array(right)
    knots = np.linspace(-.09, .09, 19)
    rows = []
    lower, upper = [], []
    for i in range(len(bins)-1):
        for z in bins[i:i+2]:
            j = min(int(np.searchsorted(knots, z, side="right")-1), len(knots)-2)
            j = max(j, 0)
            u = (z-knots[j])/(knots[j+1]-knots[j])
            row = np.zeros(len(knots)); row[j:j+2] = [1-u, u]
            rows.append(row); lower.append(left[i]); upper.append(right[i])
    matrix = np.array(rows)
    limit = np.deg2rad(41.5)
    l = linprog(-np.ones(len(knots)), A_ub=matrix, b_ub=lower, bounds=[(-limit, -.1)]*len(knots), method="highs")
    r = linprog(np.ones(len(knots)), A_ub=-matrix, b_ub=-np.array(upper), bounds=[(.1, limit)]*len(knots), method="highs")
    if not l.success or not r.success:
        save(output / "profile_rejection.json", dict(left_min_deg=float(np.rad2deg(left.min())), right_max_deg=float(np.rad2deg(right.max()))))
        raise ValueError("Swept path would consume the neighboring cage bars")
    result = dict(z_knots_m=knots.tolist(), left_angle_rad=l.x.tolist(), right_angle_rad=r.x.tolist(),
        sweep_poses=pose_count, sweep_point_count=len(centers),
        material_motion_sampling_m=sampling, carving_clearance_m=.0012,
        finger_sweep_included=True, finger_box_cell_max_edge_m=.001, finger_clearance_m=.0004,
        maximum_window_half_angle_deg=41.5, modified_sector_half_angle_deg=42.75,
        maximum_cell_axis_spacing_m=.0005, source_ik_sha256=sha(output / "ik_before_geometry.json"))
    save(output / "inverse_profile.json", result)
    return result


def inferred_cells(profile):
    original = [trimesh.load(p, force="mesh") for p in sorted((SEED / "assets").glob("cage_collision_*.obj"))]
    extent = np.deg2rad(42.75)
    cells = []
    for cell in original:
        radius = np.linalg.norm(cell.vertices[:, :2], axis=1)
        phi = np.arctan2(cell.center_mass[1], cell.center_mass[0])
        if radius.max() <= .0585001 or abs(phi) >= extent-1e-8:
            cells.append(cell)
    # Restore full front rim sectors; radial collar pieces were kept above.
    angles = np.linspace(-extent, extent, 39)
    for lo, hi in ((-.12, -.09), (.09, .12)):
        for a, b in zip(angles[:-1], angles[1:]):
            cells.append(band_mesh([a, b], .0585, .0675, lo, hi, False).convex_hull)
    knots = profile["z_knots_m"]
    for i, (lo, hi) in enumerate(zip(knots[:-1], knots[1:])):
        for side in ("left", "right"):
            edge = profile[f"{side}_angle_rad"]
            bounds = ((-extent, edge[i]), (-extent, edge[i+1])) if side=="left" else ((edge[i], extent), (edge[i+1], extent))
            count = max(1, int(np.ceil(max(b-a for a, b in bounds)/np.deg2rad(2.25))))
            theta = [np.linspace(a, b, count+1) for a, b in bounds]
            for j in range(count):
                vertices = [[radius*np.cos(angle), radius*np.sin(angle), z]
                    for k, z in enumerate((lo, hi)) for angle in theta[k][j:j+2] for radius in (.0585, .0675)]
                cells.append(trimesh.convex.convex_hull(np.array(vertices)))
    return cells


def export_geometry(profile, output):
    folder = output / "assets"
    folder.mkdir(parents=True, exist_ok=True)
    for src in (SEED / "assets").glob("hedgehog*"):
        if src.is_file(): shutil.copy2(src, folder / src.name)
    shutil.copy2(SEED / "assets/template.json", folder / "template.json")
    cells = inferred_cells(profile)
    mesh = trimesh.boolean.union(cells, engine="manifold")
    components = sorted(mesh.split(), key=lambda m: -abs(m.volume))
    # Coincident collar interfaces can leave float32 zero-thickness shells.
    # Reject any additional material component; remove only numerical debris.
    discarded_volume = sum(abs(m.volume) for m in components[1:])
    if not mesh.is_watertight or discarded_volume > 1e-10:
        raise ValueError(f"Inferred cage is disconnected or open: {len(components)}")
    mesh = components[0]
    report = write_body(folder, "cage", mesh, cells, (.2, .1, .04, 1), 2700., finish="wood")
    record = dict(variant_id="eccentric_window", scale=3., geometry_modified=True,
        hedgehog_geometry_preserved=True, cage_connected=True, watertight=True,
        boolean_discarded_zero_thickness_volume_m3=float(discarded_volume),
        cage=report, hedgehog=json.loads((SEED / "assets/asset_report.json").read_text())["hedgehog"],
        profile_sha256=sha(output / "inverse_profile.json"), source_ik_sha256=sha(output / "ik_before_geometry.json"))
    save(folder / "asset_report.json", record)
    save(folder / "sha256.json", {p.name: sha(p) for p in sorted(folder.iterdir()) if p.name != "sha256.json" and p.is_file()})
    return cells


class SolidOracle:
    def __init__(self, folder):
        self.objects = []
        self.meshes = []
        self.managers = []
        for name in ("cage", "hedgehog"):
            meshes = [trimesh.load(p, force="mesh") for p in sorted(Path(folder).glob(f"{name}_collision_*.obj"))]
            objs = []
            for mesh in meshes:
                faces = np.column_stack([np.full(len(mesh.faces), 3), mesh.faces]).reshape(-1)
                objs.append(fcl.CollisionObject(fcl.Convex(mesh.vertices, len(mesh.faces), faces)))
            manager = fcl.DynamicAABBTreeCollisionManager()
            manager.registerObjects(objs); manager.setup()
            self.managers.append(manager); self.objects.append(objs); self.meshes.append(meshes)

    def distance(self, pose):
        transform = fcl.Transform(Rotation.from_quat(pose[3:]).as_matrix(), pose[:3])
        for obj in self.objects[1]: obj.setTransform(transform)
        self.managers[1].update()
        data = fcl.DistanceData()
        self.managers[0].distance(self.managers[1], data, fcl.defaultDistanceCallback)
        return float(data.result.min_distance)


def certify(output):
    trace = json.loads((output / "ik_before_geometry.json").read_text())
    oracle = SolidOracle(output / "assets")
    minimum = float("inf"); samples = 0; radius = .092; resolution = .0001
    for i, (a, b) in enumerate(zip(trace["frames"][:-1], trace["frames"][1:])):
        for q in interpolate(np.array(a["ball_pose"]), np.array(b["ball_pose"]), resolution):
            distance = oracle.distance(q); minimum = min(minimum, distance); samples += 1
            if distance < .0002:
                save(output / "certificate_failure.json", dict(frame=i, pose=q.tolist(), clearance_m=distance))
                raise ValueError(f"Inferred cage blocks new IK at {i}: {distance}")
        if i % 100 == 0: print(f"Certify {i}/{len(trace['frames'])}: min {minimum*1000:.3f} mm", flush=True)
    original = json.loads((SEED / "escape_upper.json").read_text())["path"]
    original_min = float("inf")
    for a, b in zip(original[:-1], original[1:]):
        original_min = min(original_min, min(oracle.distance(q) for q in interpolate(np.array(a), np.array(b), .001)))
    first = np.array(original[0]); pull = first.copy(); pull[0] = .17
    straight = min(oracle.distance(q) for q in interpolate(first, pull, .0005))
    report = dict(passed=True, sampled_minimum_clearance_m=minimum,
        continuous_clearance_lower_bound_m=minimum-resolution, material_motion_bound_m=resolution,
        checked_samples=samples, original_route_minimum_sampled_clearance_m=original_min,
        original_route_collision_found=original_min<=0, straight_pull_collision_found=straight<=0,
        straight_pull_minimum_sampled_clearance_m=straight, unique_solution_proven=False,
        ik_sha256=sha(output / "ik_before_geometry.json"), asset_manifest_sha256=sha(output / "assets/sha256.json"),
        source_fingerprints={n: sha(Path(__file__).with_name(n)) for n in ("inverse_window.py", "geometry.py", "plan_escape.py")})
    if not report["straight_pull_collision_found"]:
        raise ValueError("Inferred cage admits a trivial straight pull")
    save(output / "certificate.json", report)
    print(json.dumps(report, indent=2), flush=True)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("ik", "geometry", "certify"))
    p.add_argument("--output", type=Path, default=OUTPUT)
    p.add_argument("--shift", type=float, default=.006)
    p.add_argument("--tilt", type=float, default=2.)
    a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
    if a.action == "ik": propose(a.output, a.shift, a.tilt)
    elif a.action == "geometry":
        trace = json.loads((a.output / "ik_before_geometry.json").read_text())
        export_geometry(inverse_profile(trace, a.output), a.output)
    else: certify(a.output)


if __name__ == "__main__": main()
