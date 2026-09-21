"""Geometric width study: six fixed spikes through a rounded side opening.

This is a custom working model, not an AXIS/GEN replica. It neither models a
movable bearing nor qualifies robot reachability or physical execution.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

import fcl
import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from .geometry import HedgehogLayout, load_template, hedgehog_meshes, band_mesh, write_body
from .plan_escape import interpolate
from .variants import ROOT, prototype, save, file_sha


def template(width_mm):
    data = deepcopy(load_template())
    data["template_id"] = "fixed_six_spike_rounded_side_window_probe_v1"
    data["reference_model"] = "Custom side-window experiment; not official AXIS or GEN CAD"
    data["geometry_status"] = "custom_geometry_probe_not_manufacturer_CAD"
    data["provenance"] = dict(official_facts=[],
        note="Dimensions and six orthogonal spike directions are custom. No bearing mechanism is modeled.")
    data["hedgehog"]["spikes"] = data["hedgehog"]["spikes"][:6]
    data["cage"]["window_widths"][0] = float(width_mm)
    data["cage"]["collar_hole_radius"] = 7.5  # Axial hole smaller than the core.
    data["cage"]["angular_segments"] = 180
    data["cage"]["corner_policy"] = "each window has semicircular ends in chord coordinates"
    return data


def cage_meshes(layout):
    c, u = layout.template["cage"], layout.unit
    outer = c["outer_diameter"] / 2 * u
    inner = outer - c["wall_thickness"] * u
    half = c["height"] / 2 * u
    rim = half - c["collar_height"] * u
    centers = np.radians(c["window_centers_deg"])
    widths = np.array(c["window_widths"]) * u
    if not np.all(np.isfinite(widths) & (widths > 0) & (widths < 2*inner)):
        raise ValueError("Window widths must fit the inner cage diameter")
    half_angles = np.arcsin(widths / (2*inner))
    if np.any(half_angles + np.roll(half_angles, -1) >= 2*np.pi/5):
        raise ValueError("Widening would merge neighboring windows")
    boundaries = np.r_[centers-half_angles, centers+half_angles] % (2*np.pi)
    # Boundaries can coincide with regular samples; merge floating-point twins
    # before constructing convex wedges, which must have nonzero volume.
    angles = np.unique(np.round(np.r_[np.linspace(0, 2*np.pi, c["angular_segments"], endpoint=False), boundaries], 12))
    delta = (angles[:, None]-centers+np.pi) % (2*np.pi)-np.pi
    # A wide window can extend beyond the midpoint between window centers.
    # Classify by membership, not just by the nearest center.
    selected = np.argmin(abs(delta)/half_angles, axis=1)
    distance = abs(delta[np.arange(len(angles)), selected])
    in_window = distance <= half_angles[selected]+1e-10
    radius = widths[selected]/2
    offset = inner*np.sin(distance)
    rise = radius-np.sqrt(np.maximum(radius**2-offset**2, 0))
    low = np.where(in_window, -rim+rise, -rim+radius)
    high = -low
    visual = [band_mesh(angles, inner, outer, -half, low), band_mesh(angles, inner, outer, high, half)]
    collision = []
    for i in range(len(angles)):
        j = (i+1) % len(angles)
        pair = [angles[i], angles[j] if j else 2*np.pi]
        midpoint = np.mean(pair) % (2*np.pi)
        d = abs((midpoint-centers+np.pi) % (2*np.pi)-np.pi)
        for lower, upper in ((np.full(2, -half), low[[i,j]]), (high[[i,j]], np.full(2, half))):
            collision.append(band_mesh(pair, inner, outer, lower, upper, False).convex_hull)
        if not np.any(d < half_angles):
            mesh = band_mesh(pair, inner, outer, low[[i,j]], high[[i,j]], False)
            visual.append(mesh)
            collision.append(mesh.convex_hull)
    hole = c["collar_hole_radius"]*u
    for lo, hi in ((-half,-rim),(rim,half)):
        visual.append(band_mesh(angles, hole, inner, lo, hi))
        for i in range(len(angles)):
            pair = [angles[i], angles[i+1] if i+1<len(angles) else 2*np.pi]
            collision.append(band_mesh(pair, hole, inner, lo, hi, False).convex_hull)
    return trimesh.util.concatenate(visual), collision


class Oracle:
    def __init__(self, cage, ball):
        self.objects, self.managers = [], []
        for meshes in (cage, ball):
            objects = []
            for mesh in meshes:
                faces = np.column_stack([np.full(len(mesh.faces),3),mesh.faces]).ravel()
                objects.append(fcl.CollisionObject(fcl.Convex(mesh.vertices,len(mesh.faces),faces)))
            manager = fcl.DynamicAABBTreeCollisionManager()
            manager.registerObjects(objects)
            manager.setup()
            self.objects.append(objects)
            self.managers.append(manager)

    def distance(self, pose):
        transform = fcl.Transform(Rotation.from_quat(pose[3:]).as_matrix(),pose[:3])
        for obj in self.objects[1]:
            obj.setTransform(transform)
        self.managers[1].update()
        result = fcl.DistanceData()
        self.managers[0].distance(self.managers[1],result,fcl.defaultDistanceCallback)
        return float(result.result.min_distance)


def check(oracle, path, resolution):
    minimum, count, worst = float("inf"), 0, None
    for a,b in zip(path[:-1],path[1:]):
        for pose in interpolate(np.array(a),np.array(b),resolution):
            distance = oracle.distance(pose)
            count += 1
            if distance < minimum:
                minimum, worst = distance, pose.tolist()
            if distance <= 0:
                return dict(collision=True, samples=count, minimum_sampled_gap_m=minimum, witness=worst)
    return dict(collision=False,samples=count,minimum_sampled_gap_m=minimum,
                continuous_clearance_lower_bound_m=minimum-resolution,witness=worst)


def run(output, widths, path_file=None, plan_width=None, seed=19):
    output = Path(output).resolve()
    if output.is_relative_to(ROOT / "demos"):
        raise ValueError("Metadata belongs outside demos")
    output.mkdir(exist_ok=False, parents=True)
    parent, _, manifest = prototype("oblique_gate")
    if file_sha(parent/"motion.json") != manifest["files_sha256"]["motion.json"]:
        raise ValueError("Source witness checksum changed")
    # The existing classic route is an initial witness, not a claim that a failed
    # width is globally unsolvable. Its four extra spikes are omitted explicitly.
    path = np.array(json.loads((parent/"motion.json").read_text())["seed_path"])
    ball, ball_cells = hedgehog_meshes(HedgehogLayout(template(widths[0]),3.))
    if np.linalg.norm(ball.vertices,axis=1).max() > .092:
        raise ValueError("Interpolation travel bound does not cover the moving body")
    source = dict(parent_motion_sha256=file_sha(parent/"motion.json"),
                  method="reuse_classic_route_on_custom_geometry")
    if path_file is not None:
        path = np.array(json.loads(Path(path_file).read_text())["path"])
        source.update(method="replay_saved_path", source_sha256=file_sha(Path(path_file)))
        (output/"replayed_motion.json").write_bytes(Path(path_file).read_bytes())
    elif plan_width is not None:
        from ompl import util as ou
        from .plan_escape import search
        ou.RNG.setSeed(seed)
        _, cells = cage_meshes(HedgehogLayout(template(plan_width),3.))
        planned = search(Oracle(cells,ball_cells),path[0],path[-1],seconds=40,margin=.001)
        if planned is None:
            raise RuntimeError("Planner did not find a path; this does not prove infeasibility")
        path = np.array(planned)
        source.update(method="RRTConnect",planning_nominal_width_mm=plan_width,
                      planner_seed=seed,planning_margin_m=.001)
    if path.ndim != 2 or path.shape[1] != 7 or len(path) < 2 or not np.isfinite(path).all():
        raise ValueError("Expected a finite pose path with xyz and xyzw quaternion")
    if not np.allclose(np.linalg.norm(path[:,3:],axis=1),1.,atol=1e-8):
        raise ValueError("Path quaternions must be normalized")
    save(output/"motion_source.json",dict(**source,path=path.tolist()))
    rows = []
    selected = None
    for width in widths:
        layout = HedgehogLayout(template(width),3.)
        cage, cage_cells = cage_meshes(layout)
        oracle = Oracle(cage_cells,ball_cells)
        positive = check(oracle,path,.0003)
        end = path[0].copy()
        end[0] = path[-1,0]
        direct = check(oracle,[path[0],end],.0003)
        accepted = not positive["collision"] and positive["continuous_clearance_lower_bound_m"] >= .0005 and direct["collision"]
        row = dict(nominal_window_width_mm=width, scene_window_width_mm=3*width,
                   initial_pose_gap_m=oracle.distance(path[0]), rotating_path=positive,
                   initial_orientation_straight_pull=direct, accepted=accepted)
        rows.append(row)
        print(json.dumps({k:v for k,v in row.items() if k not in ("rotating_path","initial_orientation_straight_pull")}),flush=True)
        if accepted and selected is None:
            selected = (layout,cage,cage_cells,oracle,row)
    report = dict(scope="custom six-fixed-spike cage, geometry-only; no official AXIS dimensions or bearing mechanism",
        ball_core_diameter_nominal_mm=18, scene_scale=3, spike_count=6, all_spikes_rigidly_fixed=True,
        nominal_cage_outer_diameter_mm=45,nominal_cage_height_mm=80,
        nominal_window_height_mm=60,nominal_wall_thickness_mm=3,
        nominal_other_window_widths_mm=[18.5]*4,
        trials=rows, accepted=False, global_minimum_width_proven=False,
        robot_ik="not_run",physics="not_run",export_ready=False)
    if selected is not None:
        layout,cage,cage_cells,oracle,row = selected
        fine = check(oracle,path,.00005)
        if fine["collision"] or fine["continuous_clearance_lower_bound_m"] < .0005:
            raise ValueError("Fine certification failed")
        final = Rotation.from_quat(path[-1,3:]).apply(ball.vertices)+path[-1,:3]
        outside = float(final[:,0].min()-cage.bounds[1,0])
        if outside < .003:
            raise ValueError("The ball is not completely outside")
        folder = output/"assets"
        folder.mkdir()
        asset_reports = dict(
            cage=write_body(folder,"cage",cage,cage_cells,(1,1,1,1),700,finish="wood"),
            hedgehog=write_body(folder,"hedgehog",ball,ball_cells,(1,1,1,1),700,finish="wood"))
        if not all(r["all_parts_watertight"] and r["all_parts_convex"] for r in asset_reports.values()):
            raise ValueError("Invalid compound collision assets")
        save(folder/"asset_report.json",asset_reports)
        save(folder/"template.json",layout.template)
        save(output/"path.json",dict(path=path.tolist(),classification="object_kinematic_witness",physical_execution=False))
        report.update(accepted=True,selected_nominal_window_width_mm=row["nominal_window_width_mm"],
            selected_scene_window_width_mm=row["scene_window_width_mm"],fine_certificate=fine,
            final_outside_margin_m=outside,
            limitation="Only the supplied rotating route and the initial-orientation direct pull were tested. Other easy paths may exist.")
    save(output/"report.json",report)
    save(output/"files_sha256.json",{str(p.relative_to(output)):file_sha(p) for p in sorted(output.rglob("*")) if p.is_file()})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--widths",type=float,nargs="+",default=[19,19.5,20,20.5,21,21.5,22,23,24])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--path",type=Path,help="Replay an archived xyz/xyzw path")
    source.add_argument("--plan-width",type=float,help="Replan in a window of this nominal width in mm")
    parser.add_argument("--seed",type=int,default=19)
    args = parser.parse_args()
    run(args.output,args.widths,args.path,args.plan_width,args.seed)
