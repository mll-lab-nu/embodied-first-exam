"""Independently audit saved physical states before allowing their video export."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from hydra import compose,initialize_config_dir
import numpy as np
from scipy.spatial.transform import Rotation

from .collision import CompoundCollision
from .instance_solution import initial_relative_pose,require_current_instance_certificate
from .geometry import ASSET_ROOT
from .robot_motion import Kinematics,RobotClearance,ROOT
from .solution import canonical_geometry


def audit(folder,geometry_path=None):
    folder=Path(folder);report=json.loads((folder/"report.json").read_text())
    if not report.get("passed") or not report.get("robot_execution_verified") or report.get("pose_writes_after_reset"):
        raise ValueError("A passing physical execution without pose overwrites is required")
    hashes={n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in ("report.json","trajectory.json")}
    trace=json.loads((folder/"trajectory.json").read_text())
    if geometry_path is None:
        require_current_instance_certificate(ASSET_ROOT/"baseline_solution.json",folder.parent/"certificate.json")
        variant=None
    else:
        from .variant_assets import require_variant
        from .inverse_variants import geometry_from_record,sha
        variant,_=require_variant(geometry_path)
        if report.get("geometry_sha256")!=sha(geometry_path):raise ValueError("Physics used different geometry")
    with initialize_config_dir(config_dir=str(ROOT/"configs"),version_base="1.3"):
        cfg=compose(config_name="cast_keyhole_aloha")
    kin=Kinematics(cfg.robot_control)
    if variant is None:_,_,cells=canonical_geometry(3.)
    else:_,cells=geometry_from_record(variant)
    check=RobotClearance(kin,cells);collision=CompoundCollision(*cells)
    errors=[];mingap=float("inf");final_gap=0.;tailv=0.;tailw=0.;previous=None
    for i,frame in enumerate(trace):
        kin.q=np.array(frame["qpos"])
        bodies=[(Rotation.from_quat(frame["bodies"][n]["quat"]).as_matrix(),np.array(frame["bodies"][n]["pos"]))
                for n in ("keyhole_gold","keyhole_silver")]
        bad=check.violations(bodies)
        if bad:errors.append(dict(frame=i,time_s=frame["time_s"],violations=bad))
        (rg,tg),(rs,ts)=bodies;rr=rg.T@rs;tt=rg.T@(ts-tg)
        gap=collision.gap(rr,tt);mingap=min(mingap,gap);final_gap=gap
        if gap<=0:errors.append(dict(frame=i,interpiece_gap_m=gap))
        if i==0:
            r0,t0=initial_relative_pose(3.)
            initial_position_error=float(np.linalg.norm(tt-t0));initial_angle=float(Rotation.from_matrix(rr@r0.T).magnitude())
            if initial_position_error>.0005 or initial_angle>.005:errors.append("Initial assembly changed before recorded execution")
        if previous and frame["time_s"]>trace[-1]["time_s"]-.5:
            elapsed=frame["time_s"]-previous[0]
            for (r,t),(pr,pt) in zip(bodies,previous[1]):
                tailv=max(tailv,float(np.linalg.norm(t-pt)/elapsed))
                tailw=max(tailw,float(Rotation.from_matrix(r@pr.T).magnitude()/elapsed))
        previous=(frame["time_s"],bodies)
        if i%200==0:print(f"Physical trace audit {i+1}/{len(trace)}",flush=True)
    if final_gap<.02 or tailv>.001 or tailw>.01:errors.append("Final separation or final rest failed")
    if any(hashlib.sha256((folder/n).read_bytes()).hexdigest()!=h for n,h in hashes.items()):
        errors.append("Physical trace changed during audit")
    result=dict(passed=not errors,errors=errors,scope=f"saved actual physics states, {report['dt']*10000:g} ms sampling; independent robot/puzzle convex collision audit",
        states_checked=len(trace),minimum_sampled_gap_m=mingap,final_separation_lower_bound_m=final_gap,
        initial_relative_position_error_m=initial_position_error,initial_relative_rotation_error_rad=initial_angle,
        tail_max_body_origin_speed_m_s=tailv,tail_max_angular_speed_rad_s=tailw,
        pregrasp_start=True,assisted_weld_grasp=True,grasp_assistance_active_at_end=True,
        final_state="pieces fully separated and held at rest by two arms",source_sha256=hashes,
        formal_demo_qualified=False)
    if variant is not None:result.update(variant_id=variant["id"],geometry_sha256=sha(geometry_path))
    (folder/"audit.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="errors"},indent=2))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--folder",type=Path,required=True)
    p.add_argument("--geometry",type=Path);a=p.parse_args()
    if not audit(a.folder,a.geometry)["passed"]:raise SystemExit(1)


if __name__=="__main__":main()
