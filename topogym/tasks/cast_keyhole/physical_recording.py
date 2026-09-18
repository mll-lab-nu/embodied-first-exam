"""Select synchronized camera frames directly from an audited physical trace.

No interpolation or synthetic body poses: every selected state is an actual
saved physics step. Rendering can happen later without rerunning the controller.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from hydra import compose,initialize_config_dir
import numpy as np
from scipy.spatial.transform import Rotation

from .robot_motion import Kinematics,ROOT


def prepare(folder,reference,output,fps=12):
    folder=Path(folder);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    audit=json.loads((folder/"audit.json").read_text());physical=json.loads((folder/"report.json").read_text())
    if not audit["passed"] or not physical["passed"]:raise ValueError("Actual physical trace must pass its independent audit")
    for name,digest in audit["source_sha256"].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:raise ValueError("Physical trace changed after audit")
    ref=json.loads(Path(reference).read_text());trace=json.loads((folder/"trajectory.json").read_text())
    with initialize_config_dir(config_dir=str(ROOT/"configs"),version_base="1.3"):
        cfg=compose(config_name="cast_keyhole_aloha")
    kin=Kinematics(cfg.robot_control);times=np.array([f["time_s"] for f in trace])
    targets=np.arange(0,times[-1]-times[0]+1e-8,1/fps)+times[0]
    selected=[int(np.argmin(np.abs(times-t))) for t in targets];selected[-1]=len(trace)-1
    frames=[];phases=[]
    for j,i in enumerate(selected):
        source=trace[i];kin.q=np.array(source["qpos"])
        grasp_targets={side:dict(pos=kin.pose(side)[0].tolist(),quat=Rotation.from_matrix(kin.pose(side)[1]).as_quat().tolist()) for side in ("left","right")}
        stage="contact_grasp_hold" if source["time_s"]<.5 else source["stage"]
        if not phases or phases[-1]["name"]!=stage:phases.append(dict(name=stage,frame=j,time_s=j/fps))
        frames.append(dict(source,source_trace_index=i,stage=stage,grasp_targets=grasp_targets))
    report=dict(scope="Saved states from one continuous physical ALOHA execution; every rendered frame is an actual physics step",
        passed=True,scene_scale=ref["report"]["scene_scale"],pregrasp_start=True,
        solution_sha256=ref["report"].get("solution_sha256",ref["report"].get("source_proposal_sha256")),
        template_sha256=ref["report"].get("template_sha256"),
        planning_ik_report=ref["report"],pose_source="actual Genesis physics states",
        kinematic_replay=False,robot_execution_verified=True,physics_steps=physical["physics_steps"],
        rendering_physics_steps=0,source_physical_audit_passed=True,assisted_weld_grasp=True,
        grasp_assistance_active_at_end=True,friction_only_grasp_verified=False,
        actual_physics_dt_s=physical["dt"],actual_physics_duration_s=physical["simulated_seconds"],
        camera_sampling="nearest saved actual physics state at nominal 12 Hz; exact step/time saved in every frame",
        first_recorded_physics_time_s=frames[0]["time_s"],last_recorded_physics_time_s=frames[-1]["time_s"],
        physical_source_sha256=audit["source_sha256"],physical_audit=audit,
        sampled_robot_scene_clearance_passed=True,robot_clearance_scope=audit["scope"],
        minimum_sampled_physical_gap_m=audit["minimum_sampled_gap_m"],
        final_separation_lower_bound_m=audit["final_separation_lower_bound_m"],
        formal_demo_qualified=False)
    if "variant_id" in ref["report"]:
        report.update(variant_id=ref["report"]["variant_id"],geometry_sha256=ref["report"]["geometry_sha256"])
    (output/"robot_motion.json").write_text(json.dumps(dict(fps=fps,frames=frames,phases=phases,report=report),allow_nan=False)+"\n")
    print(f"Selected {len(frames)} actual physical states, steps {frames[0]['physics_step']} through {frames[-1]['physics_step']}")


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--folder",type=Path,required=True)
    p.add_argument("--reference",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();prepare(a.folder,a.reference,a.output)


if __name__=="__main__":main()
