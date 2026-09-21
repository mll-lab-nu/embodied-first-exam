"""Vary the solved robot motion first, then infer a longer staggered-tooth slot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from hydra import compose, initialize_config_dir
import numpy as np
from scipy.spatial.transform import Rotation
from shapely.geometry import Polygon, Point, box

from .geometry import ASSET_ROOT, load_template, outlines
from .inverse_variants import (UNIT, save, sha, pack, polygon_record, geometry_from_record,
    sweep_polygons, certify_variant, check_robot, overview)
from .robot_motion import ROOT, Kinematics, solve_coupled
from .solution import read_motion
from .trajectory_probe import schedule

SEED = ROOT / "runs/environment_bootstrap/cast_keyhole/aloha_current_instance/robot_motion.json"
OUTPUT = ROOT / "runs/environment-solvability/cast_keyhole/long_stroke_v1"


def relative(frame):
    gold, silver = [frame["bodies"][n] for n in ("keyhole_gold", "keyhole_silver")]
    rg, rs = [Rotation.from_quat(p["quat"]).as_matrix() for p in (gold, silver)]
    return rg.T @ rs, rg.T @ (np.array(silver["pos"]) - gold["pos"])


def propose(folder, factor):
    seed = json.loads(SEED.read_text())
    if not seed["report"]["passed"]:
        raise ValueError("Seed IK did not pass")
    phases = []
    poses = [relative(seed["frames"][0])]
    for i in range(max(f["motion"] for f in seed["frames"]) + 1):
        frames = [f for f in seed["frames"] if f["motion"] == i]
        poses.append(relative(frames[-1])); phases.append(frames[-1]["stage"])
    index = phases.index("pass_right_tooth")
    old_length = (poses[index][1][1] - poses[index+1][1][1]) / UNIT
    extra = old_length * (factor-1)
    for i in (index+1, index+2):
        poses[i] = (poses[i][0], poses[i][1] - np.array([0, extra*UNIT, 0]))
    motions = [dict(type="pose_segment", name=f"{s}_{i:02d}", stage=s, start=pack(*a), end=pack(*b))
        for i, (a,b,s) in enumerate(zip(poses, poses[1:], phases))]
    data = dict(id="long_stroke", title_zh="长行程错齿型", units="mm", scale=3.,
        moving_piece="silver", fixed_piece="gold", source_ik_sha256=sha(SEED),
        seed_ik_path=str(SEED.relative_to(ROOT)), source_template_sha256=sha(ASSET_ROOT/"template.json"),
        pass_length_ratio=factor, original_pass_length_mm=old_length,
        proposed_pass_length_mm=old_length*factor, extra_pass_length_mm=extra,
        design_order="solved robot FK -> relative motion variation -> seeded coupled IK -> inferred geometry",
        description_zh="延长穿右齿行程，将横移避齿位置下移；由新的实际 IK 轨迹反推错齿位置和孔道。",
        motions=motions)
    save(folder/"proposal.json",data)
    return data, seed


def plan(data,seed,folder):
    with initialize_config_dir(config_dir=str(ROOT/"configs"),version_base="1.3"):
        cfg=compose(config_name="cast_keyhole_aloha")
    kin=Kinematics(cfg.robot_control);kin.q=np.array(seed["frames"][0]["qpos"])
    motions=[read_motion(m,3.) for m in data["motions"]]
    boundaries=schedule(motions,speed=.065,angular_speed=.55)
    frames=[];phases=[];maximum=np.zeros(2);fps=12
    for i,m in enumerate(motions):
        stage=data["motions"][i]["stage"]
        if not phases or phases[-1]["name"]!=stage:
            phases.append(dict(name=stage,frame=len(frames),time_s=len(frames)/fps))
        count=int(np.ceil((boundaries[i+1]-boundaries[i])*fps))
        for s in np.linspace(0,1,count+1)[int(i>0):]:
            u=10*s**3-15*s**4+6*s**5;r,t=m.pose(u)
            error,bodies=solve_coupled(kin,r,t,np.array(seed["report"]["grasp_midpoint_m"]))
            maximum=np.maximum(maximum,error)
            if maximum[0]>.00002 or maximum[1]>.0001:
                raise ValueError(f"Unreachable proposal {i}: {error}")
            poses={n:dict(pos=p.tolist(),quat=Rotation.from_matrix(w).as_quat().tolist())
                for n,(w,p) in zip(("keyhole_gold","keyhole_silver"),bodies)}
            targets={side:dict(pos=kin.pose(side)[0].tolist(),quat=Rotation.from_matrix(kin.pose(side)[1]).as_quat().tolist())
                for side in ("left","right")}
            (rg,tg),(rs,ts)=bodies
            frames.append(dict(qpos=kin.q.tolist(),bodies=poses,stage=stage,motion=i,u=float(u),
                grasp_targets=targets,relative_pose=pack(rg.T@rs,rg.T@(ts-tg))))
        print(f"Long-stroke IK {i+1}/{len(motions)}",flush=True)
    trace=dict(fps=fps,frames=frames,phases=phases,report=dict(passed=False,stage="inverse_geometry_pending",
        physics_steps=0,kinematic_replay=True,pregrasp_start=True,scene_scale=3.,
        geometry_known_during_ik=False,source_ik_sha256=data["source_ik_sha256"],
        source_proposal_sha256=sha(folder/"proposal.json"),
        max_relative_ik_position_error_m=float(maximum[0]),max_relative_ik_rotation_error_rad=float(maximum[1])))
    save(folder/"ik_proposal.json",trace)
    return trace


def infer(data,trace,folder):
    template=load_template();gold=Polygon(outlines(template,"gold")[0])
    rings=outlines(template,"silver");silver=Polygon(rings[0],rings[1:])
    frames=[f for f in trace["frames"] if f["stage"]=="pass_right_tooth"]
    # Actual FK fixes the crossing height. 3 mm is the retained sum of the
    # plate half-thickness and the original 1.5 mm endpoint design clearance.
    end_y=frames[-1]["relative_pose"]["translation_mm"][1]
    right_bottom=end_y+3.;left_top=end_y-3.;extra=-9.5-end_y
    stock=gold.union(box(.2,right_bottom,8.2,-6.5))
    stock=stock.difference(box(-5.6,left_top,-.2,-12.5))
    stock=stock.union(box(-5.6,-17.1-extra,-.2,-17.1))
    # At larger versioned strokes the extended tooth encloses an unused pocket.
    # Fill stock BEFORE machining, so the full conservative motion sweep still
    # removes every point needed by the moving piece.
    pocket_area = 0.
    if data.get("fill_stock_pockets", False):
        filled = Polygon(stock.exterior)
        pocket_area = filled.area - stock.area
        stock = filled
    sweep,sampling=sweep_polygons(trace)
    carved=stock.difference(sweep).simplify(.025,preserve_topology=True)
    if carved.geom_type!="Polygon" or len(carved.interiors) or not carved.is_valid:
        raise ValueError(f"Disconnected/invalid gold: {carved.geom_type}")
    if not carved.buffer(1e-8).covers(Point(-10.6,-31).buffer(1.0)) or carved.area<gold.area*.70:
        raise ValueError("Grasp anchor or solid material lost")
    record=dict(id=data["id"],title_zh=data["title_zh"],units="mm",scale=3.,thickness_mm=3.,density_kg_m3=6600.,
        rings_mm=dict(gold=polygon_record(carved),silver=polygon_record(silver)),
        design_method="Actual varied IK -> crossing height -> staggered stock/tooth shift -> conservative silver sweep subtraction",
        input_trace_sha256=sha(folder/"ik_proposal.json"),source_template_sha256=sha(ASSET_ROOT/"template.json"),
        source_proposal_sha256=sha(folder/"proposal.json"),sweep_sampling=sampling,
        geometry_modified=True,silver_geometry_preserved=True,grasp_anchors_preserved=True,
        inferred_right_tooth_bottom_mm=right_bottom,inferred_left_tooth_top_mm=left_top,
        gold_area_before_mm2=gold.area,gold_area_after_mm2=carved.area,
        removed_area_mm2=gold.difference(carved).area,added_area_mm2=carved.difference(gold).area)
    if data.get("fill_stock_pockets", False):
        record["filled_stock_pockets_mm2"] = pocket_area
    save(folder/"geometry.json",record)
    meshes,cells=geometry_from_record(record);audits=[]
    for name,mesh,parts,euler in zip(("gold","silver"),meshes,cells,(2,0)):
        item=dict(name=name,watertight=bool(mesh.is_watertight),components=len(mesh.split()),euler=int(mesh.euler_number),
            collision_prisms=len(parts),volume_error_m3=float(abs(sum(p.volume for p in parts)-mesh.volume)))
        if not item["watertight"] or item["components"]!=1 or item["euler"]!=euler or item["volume_error_m3"]>1e-10:
            raise ValueError(item)
        audits.append(item)
    save(folder/"solid_audit.json",dict(passed=True,pieces=audits))
    return record,meshes,cells


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,default=OUTPUT)
    p.add_argument("--factor",type=float,default=1.2);p.add_argument("--reuse-ik",action="store_true")
    args=p.parse_args();folder=args.output;folder.mkdir(parents=True,exist_ok=True)
    data,seed=propose(folder,args.factor)
    trace=json.loads((folder/"ik_proposal.json").read_text()) if args.reuse_ik else plan(data,seed,folder)
    if trace["report"]["source_proposal_sha256"]!=sha(folder/"proposal.json"):
        raise ValueError("Stale IK proposal")
    record,meshes,cells=infer(data,trace,folder)
    proof=certify_variant(data,trace,record,meshes,cells,folder)
    if not all(n["collision_found"] for n in proof["negative_controls"].values()):
        raise ValueError("The original path or direct pull still works")
    check_robot(trace,record,cells,folder);overview(data,record,folder)
    save(folder/"design_result.json",dict(passed=True,variant=data["id"],pass_length_ratio=args.factor,
        source_ik_sha256=sha(SEED),new_ik_sha256=sha(folder/"robot_motion.json"),
        geometry_sha256=sha(folder/"geometry.json"),certificate_sha256=sha(folder/"certificate.json"),
        generator_sha256=sha(__file__),negative_controls=proof["negative_controls"]))


if __name__=="__main__":main()
