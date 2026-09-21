"""Fixed-spike side-window and GEN-inspired axial keyhole prototypes.

These are custom, dimensioned adaptations, not manufacturer CAD replicas.
The default seeded generator promotes only independently qualified prototypes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation, Slerp
import trimesh

from .geometry import HedgehogLayout, hedgehog_meshes, band_mesh, write_body
from .side_window_probe import template, cage_meshes, Oracle, check
from .inverse_window import Kinematics, SEED, save, sha, SolidOracle
from .family_geometry import union64, evaluate
from .plan_escape import interpolate
from .variants import ROOT

OUTPUT = ROOT / "runs/demo_metadata/hedgehog_in_cage/2026-09-19_classic_replacements_v2"
FAMILIES = ("fixed_side_window", "gen_keyhole")


def gen_cage(radius=.0475, slot_width=.026, twist_deg=35., stem_angle_deg=-56.69642381826812):
    """A connected cage with six slanted bars and a top keyhole plate."""
    from shapely.geometry import Point, box, Polygon
    from shapely.affinity import rotate
    cells = []
    outer, inner = .0675, .0585
    angles = np.linspace(0, 2*np.pi, 97)
    for a,b in zip(angles[:-1],angles[1:]):
        cells.append(band_mesh([a,b], .021, outer, -.12, -.102, False).convex_hull)
    # 14-degree bars leave side gaps narrower than the 54 mm spherical core.
    # Their changing azimuth gives GEN's open diagonal appearance.
    for phase in np.arange(6)*60. + 15.:
        for low,high in zip(np.linspace(-.106,.114,25)[:-1],np.linspace(-.106,.114,25)[1:]):
            vertices = []
            for z in (low,high):
                center = np.radians(phase + twist_deg*(z-.065)/.22)
                for angle in (center-np.radians(7),center+np.radians(7)):
                    for r in (inner,outer):
                        vertices.append([r*np.cos(angle),r*np.sin(angle),z])
            cells.append(trimesh.convex.convex_hull(vertices))
    stem=rotate(box(-.006,-slot_width/2,.055,slot_width/2),stem_angle_deg,origin=(-.006,0))
    hole = Point(-.006,0).buffer(radius,quad_segs=48).union(stem)
    plate = Point(0,0).buffer(outer,quad_segs=48).difference(hole)
    vertices, faces = trimesh.creation.triangulate_polygon(plate, engine="earcut")
    for face in faces:
        tri = vertices[face]
        points = np.vstack([np.column_stack([tri,np.full(3,z)]) for z in (.106,.12)])
        cells.append(trimesh.convex.convex_hull(points))
    mesh = union64(cells)
    return mesh,cells,dict(keyhole_bulb_radius_m=radius,slot_width_m=slot_width,
        slot_tip_x_m=.055,stem_angle_deg=stem_angle_deg,bar_count=6,bar_twist_deg=twist_deg,side_exit_blocked_by_core=True)


def assets(family, folder, *, keyhole_radius=.0475):
    folder = Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    asset_dir=folder/"assets"
    if asset_dir.exists():
        raise FileExistsError(asset_dir)
    data=template(23.)
    data["template_id"] = f"{family}_fixed_six_spikes_v2"
    if family=="fixed_side_window":
        data["cage"]["height"]=85.
        data["cage"]["mesh_z_offset_m"]=.0075
    else:
        # GEN-inspired matching six-spike layout: retain the established S2
        # grasp, with shorter transverse spikes that can turn inside the cage.
        for spike,length in zip(data["hedgehog"]["spikes"],(7.5,13.,5.,8.,7.,11.)):
            spike["exposed_length"]=length
    layout=HedgehogLayout(data,3.)
    ball, ball_cells=hedgehog_meshes(layout)
    if family=="fixed_side_window":
        cage,cells=cage_meshes(layout)
        for mesh in [cage,*cells]:mesh.apply_translation([0,0,.0075])
        shape=dict(window_width_m=.069,window_height_m=.195,axial_exit_blocked_by_core=True)
    else:
        cage,cells,shape=gen_cage(radius=keyhole_radius)
        data["cage"]["custom_shape"] = shape
    asset_dir.mkdir()
    reports={}
    for name,visual,collision in (("cage",cage,cells),("hedgehog",ball,ball_cells)):
        reports[name]=write_body(asset_dir,name,visual,collision,(1,1,1,1),700.,finish="wood")
    if family=="gen_keyhole":
        # Counterfactual material that closes only the stem. It is never loaded
        # into the actual scene; descendants transform and retest this control.
        from shapely.geometry import Point, box
        from shapely.affinity import rotate
        stem=rotate(box(-.006,-.013,.055,.013),shape["stem_angle_deg"],origin=(-.006,0))
        added=stem.difference(Point(-.006,0).buffer(keyhole_radius,quad_segs=48))
        vertices,faces=trimesh.creation.triangulate_polygon(added,engine="earcut")
        for i,face in enumerate(faces):
            tri=vertices[face]
            points=np.vstack([np.column_stack([tri,np.full(3,z)]) for z in (.106,.12)])
            trimesh.convex.convex_hull(points).export(asset_dir/f"counterfactual_closed_stem_{i:03d}.obj")
    save(asset_dir/"template.json",data)
    save(asset_dir/"asset_report.json",dict(family=family,custom_reference_adaptation=True,
        all_spikes_fixed=True,spike_count=6,shape=shape,bodies=reports,
        maximum_radial_extent_m=float(np.linalg.norm(cage.vertices[:,:2],axis=1).max())))
    save(asset_dir/"sha256.json",{p.name:sha(p) for p in sorted(asset_dir.iterdir()) if p.is_file()})
    grasp=json.loads((SEED/"robot_escape_plan.json").read_text())["selected"]
    save(folder/"grasp.json",{k:grasp[k] for k in ("hand_position_in_ball","hand_quaternion_in_ball_xyzw","grip_point_in_ball","pad_offset_in_hand")})
    return cage,cells,ball,ball_cells


def plan(family,folder):
    folder=Path(folder)
    oracle=SolidOracle(folder/"assets")
    if family=="fixed_side_window":
        prior=SEED/"escape_upper.json"
        path=np.array(json.loads(prior.read_text())["path"])
        phases=["turn_through_rounded_side_window"]*(len(path)-2)+["withdraw"]
    else:
        # Lift and tilt together: the grasp stays above the lid while the last
        # long transverse spike (S6) is aligned with the keyhole's narrow stem.
        rotation=Rotation.from_euler("z",105,degrees=True)*Rotation.from_euler("y",90,degrees=True)
        start=np.r_[[-.006,0.,.055],rotation.as_quat()]
        nx,nz=-.53,.66;ny=np.sqrt(1-nx*nx-nz*nz)
        tilted=Rotation.align_vectors([[0,0,1]],[[nx,ny,nz]])[0]
        projected=tilted.apply([-1,0,0])
        tilted=Rotation.from_euler("z",-np.arctan2(projected[1],projected[0]))*tilted
        raised=start.copy();raised[2]=.075
        aligned=start.copy();aligned[2]=.115;aligned[3:]=tilted.as_quat()
        intermediate=raised.copy();intermediate[2]=.090
        intermediate[3:]=Slerp([0,1],Rotation.from_quat([raised[3:],aligned[3:]]))([.6]).as_quat()[0]
        goal=aligned.copy();goal[2]=.225
        path=np.array([start,raised,intermediate,aligned,goal])
        clear=path[-1].copy();clear[0]=.22
        path=np.vstack([path,clear])
        phases=["raise_before_tilt","tilt_within_lid_clearance","align_last_spike_with_keyhole_stem",
                "lift_through_keyhole","carry_clear_of_cage"]
    positive=check(oracle,path,.0001)
    save(folder/"object_path_search.json",dict(family=family,path=path.tolist(),phases=phases,
         construction="fixed_representative_recipe",geometry_check=positive))
    if positive["collision"] or positive["continuous_clearance_lower_bound_m"]<.0007:
        raise ValueError("Object path clearance failed")
    return robot_plan(family,folder,path,phases)


def robot_plan(family,folder,path,phases):
    folder=Path(folder);kin=Kinematics()
    # This only initializes a pregrasp configuration. It is not an executed
    # approach and is not included in the task's success evidence.
    for pose in interpolate(kin.ball_pose(),path[0],.0025):
        kin.solve(pose)
    release=json.loads((SEED/"robot_release_plan.json").read_text())
    release_path=np.array(release["path"])
    release_path[0]=path[-1]
    if family=="gen_keyhole":
        # Select a stable placement reachable from this family's arm branch.
        # The original lateral family's wrist orientation need not be reachable
        # from a top-down grasp, even when the extraction itself is reachable.
        initial_q=kin.q.copy()
        for a,b in zip(path[:-1],path[1:]):
            for pose in interpolate(a,b,.0025):kin.solve(pose)
        release_path=stable_release(kin,path[-1],folder)
        kin.q[:]=initial_q
    # Place this six-spike body close to the table rather than inheriting the
    # ten-spike body's bottom height. Gravity and final settling are still tested.
    ball=trimesh.load(folder/"assets/hedgehog.obj",force="mesh")
    bottom=Rotation.from_quat(release_path[-1,3:]).apply(ball.vertices)[:,2].min()
    release_path[-1,2]=-.22-bottom+.0015
    frames=[];knots=[]
    all_path=np.vstack([path,release_path[1:]])
    names=[*phases,*release["phases"]]
    try:
        for i,(a,b) in enumerate(zip(all_path[:-1],all_path[1:])):
            for target in list(interpolate(a,b,.0025))[int(i>0):]:
                actual=kin.solve(target)
                frames.append(dict(qpos=kin.q.tolist(),ball_pose=actual.tolist(),segment=i,stage=names[i]))
            knots.append(len(frames)-1)
            print(f"{family} IK {i+1}/{len(all_path)-1}",flush=True)
    except Exception as exc:
        save(folder/"ik_failure.json",dict(error=str(exc),segment=i,target=target.tolist(),completed_frames=len(frames)))
        raise
    result=dict(family=family,frames=frames,knot_indices=knots,extraction_last_frame=knots[len(path)-2],
        proposed_path=path.tolist(),extraction_phases=phases,release_path=release_path.tolist(),release_phases=release["phases"],
        grasp_spike="S2",seed_path=path.tolist(),pregrasp_start=True,
        negative_paths=controls(path,family),custom_reference_adaptation=True)
    save(folder/"ik_before_geometry.json",result)
    return result


def stable_release(kin,start,folder):
    ball=trimesh.load(Path(folder)/"assets/hedgehog.obj",force="mesh")
    transforms,probabilities=trimesh.poses.compute_stable_poses(ball,sigma=0,n_samples=1)
    candidates=[];start_r=Rotation.from_quat(start[3:])
    for transform,probability in zip(transforms,probabilities):
        if probability<.01:continue
        for yaw in np.arange(0,360,15):
            r=Rotation.from_euler("z",yaw,degrees=True)*Rotation.from_matrix(transform[:3,:3])
            bottom=float(r.apply(ball.vertices)[:,2].min())
            if -bottom+r.apply(kin.hand_p)[2]<.12:continue
            candidates.append(((r*start_r.inv()).magnitude(),r,bottom))
    initial=kin.q.copy()
    for _,r,bottom in sorted(candidates,key=lambda v:v[0]):
        for x,z in ((.28,.13),(.30,.18),(.25,.08),(.32,.08)):
            carry=start.copy();carry[:3]=[x,0,z]
            oriented=carry.copy();oriented[3:]=r.as_quat()
            placed=oriented.copy();placed[2]=-.22-bottom+.0015
            path=np.array([start,carry,oriented,placed]);kin.q[:]=initial
            try:
                for a,b in zip(path[:-1],path[1:]):
                    for pose in interpolate(a,b,.0025):kin.solve(pose)
            except ValueError:
                continue
            return path
    kin.q[:]=initial
    raise ValueError("No stable reachable placement from this grasp branch")


def controls(path,family):
    first=np.array(path[0]);last=np.array(path[-1]);direct=last.copy();direct[3:]=first[3:]
    up=first.copy();up[2]+=.35
    side=first.copy();side[0]+=.35
    down=first.copy();down[2]-=.35
    return {k:np.asarray(v).tolist() for k,v in dict(straight_lift=[first,up],straight_side_pull=[first,side],
        straight_lower=[first,down],direct_to_exit_without_rotation=[first,direct]).items()}


def certify(folder):
    folder=Path(folder);trace=json.loads((folder/"ik_before_geometry.json").read_text())
    oracle=SolidOracle(folder/"assets")
    positive=evaluate(oracle,[f["ball_pose"] for f in trace["frames"]],.0001)
    negative={n:evaluate(oracle,p) for n,p in trace["negative_paths"].items()}
    geometry_controls={}
    blockers=[trimesh.load(p,force="mesh") for p in sorted((folder/"assets").glob("counterfactual_closed_stem_*.obj"))]
    if trace["family"]=="gen_keyhole" and not blockers:
        raise ValueError("The keyhole family requires its closed-stem counterfactual")
    if blockers:
        ball_cells=[trimesh.load(p,force="mesh") for p in sorted((folder/"assets").glob("hedgehog_collision_*.obj"))]
        geometry_controls["closed_keyhole_stem"]=evaluate(Oracle(blockers,ball_cells),trace["proposed_path"])
    lower=positive["minimum_sampled_gap_m"]-.0001
    passed=not positive["collision_found"] and lower>=.0007 and all(n["collision_found"] for n in [*negative.values(),*geometry_controls.values()])
    result=dict(passed=passed,family=trace["family"],positive=positive,finite_controls=negative,
        continuous_clearance_lower_bound_m=lower,material_motion_bound_m=.0001,unique_solution_proven=False,
        geometry_ablation_controls=geometry_controls,
        distinct_ik_family_proven=False,ik_sha256=sha(folder/"ik_before_geometry.json"),
        asset_manifest_sha256=sha(folder/"assets/sha256.json"),
        source_fingerprints={n:sha(Path(__file__).with_name(n)) for n in ("classic_families.py","plan_escape.py","geometry.py")})
    save(folder/"certificate.json",result)
    print(json.dumps(result),flush=True)
    if not passed:raise ValueError("Geometry certificate rejected")
    from .family_runtime import plan_audit
    plan_audit(folder)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("assets","plan","certify"))
    parser.add_argument("family",choices=FAMILIES)
    parser.add_argument("--output",type=Path,default=OUTPUT)
    parser.add_argument("--keyhole-radius",type=float,default=.0475)
    args=parser.parse_args();folder=args.output/args.family
    if args.action=="assets":assets(args.family,folder,keyhole_radius=args.keyhole_radius)
    elif args.action=="plan":plan(args.family,folder)
    else:certify(folder)
