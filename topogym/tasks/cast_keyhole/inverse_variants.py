"""Trajectory-first Keyhole variants: solve IK, carve its sweep, then certify.

The silver plate and both grasp regions are fixed design constraints. Gold is
reconstructed inside an explicit stock domain from the proposed relative motion.
Certificates use the final exported convex solids, not the carving approximation.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from hydra import compose,initialize_config_dir
import numpy as np
import trimesh
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation
from shapely.geometry import Polygon,MultiPoint,box,Point
from shapely.ops import unary_union

from .geometry import ASSET_ROOT,load_template,outlines,polygon_slabs,extrude_slabs
from .solution import canonical_geometry,read_motion
from .route_probe import PoseSegment
from .collision import CompoundCollision,certify_motion
from .robot_motion import ROOT,Kinematics,RobotClearance,solve_frame,solve_coupled,bodies_from_fk
from .trajectory_probe import schedule

OUTPUT=ROOT/"runs/environment-solvability/cast_keyhole/inverse_motion_variants_v1"
VARIANTS=("offset_window","double_gate","tilted_window")
TITLES={"offset_window":"偏心转弯窗口","double_gate":"双重错槽","tilted_window":"倾转穿窗"}
UNIT=.003


def save(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+"\n")


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pack(r,t):return dict(translation_mm=(np.asarray(t)/UNIT).tolist(),quaternion_xyzw=Rotation.from_matrix(r).as_quat().tolist())


def polygon_record(poly):
    return [np.asarray(poly.exterior.coords[:-1]).tolist()]+[np.asarray(r.coords[:-1]).tolist() for r in poly.interiors]


def geometry_from_record(record):
    meshes=[];cells=[]
    for name in ("gold","silver"):
        layers=record.get("layers",{}).get(name,[dict(z_min_mm=-record["thickness_mm"]/2,
            z_max_mm=record["thickness_mm"]/2,rings_mm=record["rings_mm"][name])])
        layer_meshes=[];all_parts=[]
        for layer in layers:
            lo,hi=layer["z_min_mm"],layer["z_max_mm"]
            mesh,parts=extrude_slabs(polygon_slabs([np.asarray(r) for r in layer["rings_mm"]]),hi-lo)
            for p in [mesh,*parts]:p.apply_translation([0,0,(hi+lo)/2])
            layer_meshes.append(mesh);all_parts.extend(parts)
        mesh=layer_meshes[0] if len(layer_meshes)==1 else trimesh.boolean.union(layer_meshes,engine="manifold")
        meshes.append(mesh.apply_scale(UNIT));cells.append([p.apply_scale(UNIT) for p in all_parts])
    return meshes,cells


def proposal(name):
    base=json.loads((ASSET_ROOT/"baseline_solution.json").read_text())
    ms=[read_motion(m,3.) for m in base["motions"]]
    poses=[ms[0].pose(0)]+[m.pose(1) for m in ms]
    stages=[m["stage"] for m in base["motions"]]
    if name=="offset_window":
        for i in range(17,24):
            weight=np.sin(np.pi*(i-16)/8)
            r,t=poses[i];poses[i]=(r,t+UNIT*np.array([1.0*weight,.5*weight,0.]))
        description="顶部绕行轨迹向外偏移，最大模板偏移 1 mm 横向 / 0.5 mm 纵向；先求 IK，再据扫掠体重构偏心窗口。"
    elif name=="double_gate":
        poses=poses[:27];stages=stages[:26]
        r=poses[-1][0]
        for xyz,stage in [([14.9,-9.5,-20],"shift_to_middle_lane"),([14.9,-19.1,-20],"pass_middle_gate"),
                          ([7.9,-19.1,-20],"align_second_gate"),([7.9,-29.5,-20],"pass_second_gate"),
                          ([15.8,-29.5,-20],"clear_second_gate"),([15.8,-55,-20],"withdraw")]:
            poses.append((r,np.array(xyz)*UNIT));stages.append(stage)
        description="在第一道右齿之后增加不同高度的外移、下移、内移、再次穿槽及外移退出；由轨迹反推第二挡齿和对侧让位区。"
    elif name=="tilted_window":
        poses=poses[:26];stages=stages[:25]
        r0,t0=poses[-1];pivot=np.array([7.9,-4.,0.])*UNIT
        d=(Rotation.from_euler("y",25,degrees=True)*Rotation.from_euler("x",8,degrees=True)).as_matrix()
        rt=d@r0;start=pivot+d@(np.array([7.9,1.1,-19])*UNIT-pivot)
        end=pivot+d@(np.array([7.9,-9.5,-19])*UNIT-pivot)
        for r,t,stage in [(rt,start,"tilt_for_window"),(rt,end,"pass_tilted_window"),
                          (r0,np.array([7.9,-9.5,-20])*UNIT,"restore_orientation"),
                          (r0,np.array([15.8,-9.5,-20])*UNIT,"clear_lower_tooth"),
                          (r0,np.array([15.8,-55,-20])*UNIT,"withdraw")]:
            poses.append((r,t));stages.append(stage)
        description="右齿前增加 25° 面内倾转及 8° 板面倾斜，保持倾角穿槽后恢复；由该轨迹反推带外侧止挡的斜窗口。"
    else:raise ValueError(name)
    motions=[dict(type="pose_segment",name=f"{stage}_{i:02d}",stage=stage,start=pack(*a),end=pack(*b))
             for i,(a,b,stage) in enumerate(zip(poses,poses[1:],stages))]
    return dict(id=name,title_zh=TITLES[name],description_zh=description,units="mm",scale=3.,
        moving_piece="silver",fixed_piece="gold",source_solution_sha256=sha(ASSET_ROOT/"baseline_solution.json"),
        design_order="motion proposal -> coupled IK -> inverse swept-volume geometry -> independent certification",motions=motions)


def plan_ik(data,folder,fps=12):
    with initialize_config_dir(config_dir=str(ROOT/"configs"),version_base="1.3"):
        cfg=compose(config_name="cast_keyhole_aloha")
    kin=Kinematics(cfg.robot_control);motions=[read_motion(m,3.) for m in data["motions"]]
    boundaries=schedule(motions,speed=.065,angular_speed=.55)
    frames=[];phases=[];max_error=np.zeros(2)
    for i,m in enumerate(motions):
        stage=data["motions"][i]["stage"]
        if not phases or phases[-1]["name"]!=stage:phases.append(dict(name=stage,frame=len(frames),time_s=len(frames)/fps))
        count=int(np.ceil((boundaries[i+1]-boundaries[i])*fps))
        for s in np.linspace(0,1,count+1)[int(i>0):]:
            u=10*s**3-15*s**4+6*s**5;r,t=m.pose(u)
            if not frames:
                errors,_=solve_frame(kin,r,t,-1.57,[0,0,.28])
                if np.max(errors)>1e-5:raise ValueError("Initial IK is not reachable")
            errors,bodies=solve_coupled(kin,r,t,np.array([0,0,.28]))
            max_error=np.maximum(max_error,errors)
            if max_error[0]>.00002 or max_error[1]>.0001:raise ValueError(f"Unreachable motion {i}: {errors}")
            poses={n:dict(pos=p.tolist(),quat=Rotation.from_matrix(w).as_quat().tolist())
                   for n,(w,p) in zip(("keyhole_gold","keyhole_silver"),bodies)}
            (rg,tg),(rs,ts)=bodies
            targets={side:dict(pos=kin.pose(side)[0].tolist(),quat=Rotation.from_matrix(kin.pose(side)[1]).as_quat().tolist()) for side in ("left","right")}
            frames.append(dict(qpos=kin.q.tolist(),bodies=poses,stage=stage,motion=i,u=float(u),grasp_targets=targets,
                relative_pose=pack(rg.T@rs,rg.T@(ts-tg))))
        print(f"{data['id']} IK {i+1}/{len(motions)}",flush=True)
    result=dict(fps=fps,frames=frames,phases=phases,report=dict(passed=False,stage="inverse_geometry_pending",
        physics_steps=0,kinematic_replay=True,pregrasp_start=True,scene_scale=3.,
        max_relative_ik_position_error_m=float(max_error[0]),max_relative_ik_rotation_error_rad=float(max_error[1]),
        geometry_known_during_ik=False,source_proposal_sha256=sha(folder/"proposal.json")))
    save(folder/"ik_proposal.json",result)
    return result


def motions_from_trace(trace):
    result=[]
    for i,(a,b) in enumerate(zip(trace["frames"],trace["frames"][1:])):
        result.append(read_motion(dict(type="pose_segment",name=f"fk_segment_{i:04d}",start=a["relative_pose"],end=b["relative_pose"]),3.))
    return result


def sweep_polygons(trace,step_raw=.10,clearance_raw=.16,z_min=-1.5,z_max=1.5):
    """Conservative planar sweep of silver through the expanded gold thickness slab.

    Endpoint samples are at most step_raw apart by a material-point speed bound.
    Expanding the clipping slab and XY footprint by clearance_raw+step_raw/2
    accounts for the unsampled intervals before a separate SAT certificate.
    """
    _,_,cells=canonical_geometry(3.)
    source=[]
    for mesh in cells[1]:source.append((mesh.vertices/UNIT,mesh.edges_unique))
    points=np.concatenate([v for v,_ in source])*UNIT
    padding=clearance_raw+step_raw/2
    low=z_min-padding;high=z_max+padding;polys=[];samples=0
    for i,m in enumerate(motions_from_trace(trace)):
        count=max(1,int(np.ceil(m.speed_bound(points)/(step_raw*UNIT))))
        for u in np.linspace(0,1,count+1)[int(i>0):]:
            r,t=m.pose(u);t=t/UNIT;samples+=1
            for vertices,edges in source:
                v=vertices@r.T+t
                if v[:,2].min()>high or v[:,2].max()<low:continue
                selected=[v[(v[:,2]>=low)&(v[:,2]<=high)]]
                a,b=v[edges[:,0]],v[edges[:,1]]
                for z in (low,high):
                    mask=(np.minimum(a[:,2],b[:,2])<z)&(np.maximum(a[:,2],b[:,2])>z)
                    aa,bb=a[mask],b[mask]
                    if len(aa):selected.append(aa+(bb-aa)*((z-aa[:,2])/(bb[:,2]-aa[:,2]))[:,None])
                selected=np.concatenate(selected)
                if len(selected)>=3:
                    poly=MultiPoint(selected[:,:2]).convex_hull
                    if poly.area>1e-10:polys.append(poly.buffer(padding,quad_segs=2))
        if i%50==0:print(f"Sweep {i+1}/{len(trace['frames'])-1}, {samples} poses",flush=True)
    return unary_union(polys),dict(samples=samples,material_point_step_mm=step_raw,
        carving_clearance_mm=clearance_raw,inter_sample_expansion_mm=step_raw/2)


def inverse_geometry(data,trace,folder):
    template=load_template();gold=Polygon(*[outlines(template,"gold")[0]])
    rings=outlines(template,"silver");silver=Polygon(rings[0],rings[1:])
    stock=gold
    if data["id"]=="offset_window":stock=stock.union(box(4.7,14.,9.5,25.))
    elif data["id"]=="double_gate":stock=stock.union(box(.2,-26.,13.,-22.))
    elif data["id"]=="tilted_window":stock=stock.union(box(12.8,-6.5,13.8,-2.))
    intervals=[(-1.5,1.5)] if data["id"]!="tilted_window" else [(-1.5,-.25),(-.25,.25),(.25,1.5)]
    layers=[];polygons=[]
    for lo,hi in intervals:
        sweep,sampling=sweep_polygons(trace,z_min=lo,z_max=hi)
        # Simplification is checked again against exact exported solids by SAT.
        carved=stock.difference(sweep).simplify(.025,preserve_topology=True)
        if carved.geom_type!="Polygon" or len(carved.interiors):
            save(folder/"rejected_geometry.json",dict(type=carved.geom_type,areas=[p.area for p in getattr(carved,"geoms",[carved])]))
            raise ValueError(f"Gold layer became disconnected or acquired a hole: {carved.geom_type}")
        layers.append(dict(z_min_mm=lo,z_max_mm=hi,rings_mm=polygon_record(carved)))
        polygons.append(carved)
    carved=polygons[len(polygons)//2]
    if not carved.is_valid or not silver.is_valid:raise ValueError("Invalid polygon")
    if not carved.buffer(1e-8).covers(Point(-10.6,-31).buffer(1.0)):
        raise ValueError("Gold grasp anchor was cut away")
    if carved.area<gold.area*.70:raise ValueError("Too much load-bearing material removed")
    record=dict(id=data["id"],title_zh=data["title_zh"],units="mm",scale=3.,thickness_mm=3.,density_kg_m3=6600.,
        rings_mm=dict(gold=polygon_record(carved),silver=polygon_record(silver)),
        design_method="Gold stock minus conservative silver sweep recovered from the varied coupled IK",
        input_trace_sha256=sha(folder/"ik_proposal.json"),source_template_sha256=sha(ASSET_ROOT/"template.json"),
        source_proposal_sha256=sha(folder/"proposal.json"),sweep_sampling=sampling,
        geometry_modified=True,silver_geometry_preserved=True,grasp_anchors_preserved=True,
        gold_area_before_mm2=gold.area,gold_area_after_mm2=carved.area,
        removed_area_mm2=gold.difference(carved).area,added_area_mm2=carved.difference(gold).area)
    if len(layers)>1:record["layers"]=dict(gold=layers)
    save(folder/"geometry.json",record)
    meshes,cells=geometry_from_record(record)
    audit=[]
    for name,m,cs,euler in zip(("gold","silver"),meshes,cells,(2,0)):
        item=dict(name=name,watertight=bool(m.is_watertight),components=len(m.split()),euler=int(m.euler_number),
            collision_prisms=len(cs),volume_error_m3=float(abs(sum(c.volume for c in cs)-m.volume)))
        if not item["watertight"] or item["components"]!=1 or item["euler"]!=euler or item["volume_error_m3"]>1e-10:
            raise ValueError(f"Invalid physical solid: {item}")
        audit.append(item)
    save(folder/"solid_audit.json",dict(passed=True,pieces=audit))
    return record,meshes,cells


def certify_variant(data,trace,record,meshes,cells,folder):
    collision=CompoundCollision(*cells);motions=motions_from_trace(trace)
    segments=[]
    for i,m in enumerate(motions):
        result=certify_motion(collision,m,margin_m=.00015);segments.append(result)
        if not result["passed"]:
            save(folder/"certificate.json",dict(passed=False,failed=result,segments=segments));raise ValueError(result)
        if i%50==0:print(f"Certify {i+1}/{len(motions)}",flush=True)
    gap=float(collision.gap(*motions[-1].pose(1)))
    if gap<.02:raise ValueError("Incomplete extraction")
    negative={}
    base=json.loads((ASSET_ROOT/"baseline_solution.json").read_text())
    minbase=float("inf");witness=None
    for i,item in enumerate(base["motions"]):
        m=read_motion(item,3.)
        for u in np.linspace(0,1,11):
            g=collision.gap(*m.pose(u))
            if g<minbase:minbase=g;witness=dict(motion=i,u=float(u))
    negative["unchanged_baseline_solution"]=dict(minimum_sample_gap_m=minbase,collision_found=minbase<0,witness=witness)
    # The deliberately direct pull is a rejected shortcut, not a global search.
    r,t=motions[0].pose(0);er,et=motions[-1].pose(1)
    direct=PoseSegment("straight_to_exit",r,r,t,et)
    values=[collision.gap(*direct.pose(u)) for u in np.linspace(0,1,101)]
    negative["initial_straight_pull"]=dict(minimum_sample_gap_m=float(min(values)),collision_found=min(values)<0)
    if data["id"]=="tilted_window":
        # Keep the designed translated path but omit the extra gate rotation.
        down=Rotation.from_euler("x",-90,degrees=True).as_matrix()
        selected=[f for f in trace["frames"] if f["stage"]=="pass_tilted_window"]
        gaps=[collision.gap(down,np.array(f["relative_pose"]["translation_mm"])*UNIT) for f in selected]
        negative["omit_gate_tilt"]=dict(minimum_sample_gap_m=float(min(gaps)),collision_found=min(gaps)<0)
    report=dict(passed=True,certificate_type="trajectory_first_inverse_variant_v1",segments=segments,
        clearance_margin_m=.00015,continuous_gap_lower_bound_m=min(s["continuous_gap_lower_bound_m"] for s in segments),
        final_separation_lower_bound_m=gap,negative_controls=negative,unique_solution_proven=False,
        global_shortcut_search_completed=False,geometry_sha256=sha(folder/"geometry.json"),
        ik_input_sha256=sha(folder/"ik_proposal.json"),proposal_sha256=sha(folder/"proposal.json"),
        source_fingerprints={n:sha(Path(__file__).with_name(n)) for n in ("inverse_variants.py","collision.py","geometry.py")})
    save(folder/"certificate.json",report)
    return report


def check_robot(trace,record,cells,folder):
    with initialize_config_dir(config_dir=str(ROOT/"configs"),version_base="1.3"):
        cfg=compose(config_name="cast_keyhole_aloha")
    kin=Kinematics(cfg.robot_control);check=RobotClearance(kin,cells);collision=CompoundCollision(*cells)
    min_gap=float("inf");samples=0
    qs=[np.array(f["qpos"]) for f in trace["frames"]]
    for i,qa in enumerate(qs):
        qb=qs[min(i+1,len(qs)-1)];n=max(1,int(np.ceil(np.max(np.abs(qb-qa))/.003)))
        for u in np.linspace(0,1,n+1)[:-1]:
            kin.q=(1-u)*qa+u*qb;bodies=bodies_from_fk(kin)
            bad=check.violations(bodies)
            if bad:raise ValueError(f"Robot collision frame {i}: {bad[:3]}")
            (rg,tg),(rs,ts)=bodies;gap=collision.gap(rg.T@rs,rg.T@(ts-tg));min_gap=min(min_gap,gap)
            if gap<.00015:raise ValueError(f"Robot joint interpolation gap failed: {gap}")
            samples+=1
    trace["report"].update(passed=True,stage="complete_ik_and_geometry_checked",sampled_robot_scene_clearance_passed=True,
        minimum_sampled_gap_m=min_gap,robot_samples=samples,max_joint_sampling_step_rad=.003,
        geometry_sha256=sha(folder/"geometry.json"),certificate_sha256=sha(folder/"certificate.json"),
        variant_id=record["id"],robot_execution_verified=False,formal_demo_qualified=False)
    save(folder/"robot_motion.json",trace)


def overview(data,record,folder):
    import matplotlib;matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as PlotPolygon
    base=outlines(load_template(),"gold")[0];gold=np.array(record["rings_mm"]["gold"][0])
    fig,ax=plt.subplots(figsize=(5,8))
    ax.add_patch(PlotPolygon(base,closed=True,fill=False,edgecolor="#666",linestyle="--",linewidth=1.5,label="Original gold"))
    ax.add_patch(PlotPolygon(gold,closed=True,facecolor="#ba903e",alpha=.7,edgecolor="#866117",label="Inverse-designed gold"))
    ax.autoscale_view();ax.set_aspect("equal");ax.legend();ax.set_xlabel("template mm (scene scale 3)")
    ax.set_title(data["id"]);fig.tight_layout();fig.savefig(folder/"geometry_comparison.png",dpi=150);plt.close(fig)


def generate(name,root=OUTPUT,reuse_ik=False):
    folder=Path(root)/name;folder.mkdir(parents=True,exist_ok=True)
    data=proposal(name);save(folder/"proposal.json",data)
    trace=json.loads((folder/"ik_proposal.json").read_text()) if reuse_ik else plan_ik(data,folder)
    record,meshes,cells=inverse_geometry(data,trace,folder)
    proof=certify_variant(data,trace,record,meshes,cells,folder)
    check_robot(trace,record,cells,folder);overview(data,record,folder)
    print(json.dumps(dict(id=name,passed=True,negative_controls=proof["negative_controls"],
        modified_gold_area_mm2=record["added_area_mm2"]+record["removed_area_mm2"]),indent=2),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--variant",choices=VARIANTS,required=True)
    p.add_argument("--output",type=Path,default=OUTPUT);p.add_argument("--reuse-ik",action="store_true")
    a=p.parse_args();generate(a.variant,a.output,a.reuse_ik)


if __name__=="__main__":main()
