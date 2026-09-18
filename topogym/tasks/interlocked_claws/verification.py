"""Independent evidence checks and timestep comparison for the Claw execution."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation
from omegaconf import OmegaConf

from .reference import ReferenceMotion


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_physical(folder):
    folder = Path(folder)
    result = json.loads((folder / "result.json").read_text())
    motion = ReferenceMotion()
    if not (result["passed"] and result["success"] and result["complete"]
            and result["final_stable"] and result["failed"] is None
            and result["physics_steps"] > 0 and result["initial_reference_time_s"] == 0
            and result["final_reference_time_s"] == motion.duration
            and result["pose_writes_after_initialization"] is False
            and not result["remaining_grasps"] and not any(result["held_at_end"])
            and result["reference_motion_sha256"] == motion.sha256
            and result["states_sha256"] == sha(folder / "states.jsonl")):
        raise ValueError("Incomplete, altered, nonphysical, or unsupported execution")
    if [p["name"] for p in result["phases"]] != [p["name"] for p in motion.source["timeline"]]:
        raise ValueError("Execution does not cover all source phases")
    if [r["piece"] for r in result["releases"]] != [0, 1]:
        raise ValueError("Both grasps must be removed in source order")
    rows = [json.loads(s) for s in (folder / "states.jsonl").read_text().splitlines()]
    if (len(rows) != result["physical_frame_count"]
            or not np.allclose([r["time_s"] for r in rows], np.arange(len(rows))/result["physical_frame_fps"], atol=1e-10)
            or rows[-1]["time_s"] < motion.duration+1.9
            or any(rows[-1]["held"])):
        raise ValueError("Invalid or truncated physical state sequence")
    return result, rows


def compare(first, second, output):
    a, ra = validate_physical(first)
    b, rb = validate_physical(second)
    if not (a["dt"] == 2*b["dt"] and len(ra) == len(rb)
            and a["source_mesh_sha256"] == b["source_mesh_sha256"]):
        raise ValueError("Compare matching complete runs at half the timestep")
    max_position, max_angle, max_q = 0., 0., 0.
    worst_time = 0.
    for x, y in zip(ra, rb):
        max_q = max(max_q, float(np.max(np.abs(np.array(x["qpos"])-y["qpos"]))))
        for u, v in zip(x["bodies"], y["bodies"]):
            d = float(np.linalg.norm(np.array(u["pos"])-v["pos"]))
            if d > max_position:
                max_position, worst_time = d, x["time_s"]
            r = [Rotation.from_quat(np.array(p["quat_wxyz"])[[1, 2, 3, 0]]) for p in (u, v)]
            max_angle = max(max_angle, float((r[0]*r[1].inv()).magnitude()))
    final_distance = [float(np.linalg.norm(np.array(u["pos"])-v["pos"])) for u,v in zip(a["final"],b["final"])]
    report = dict(passed=max_position < .001 and max_angle < .01 and max_q < .005 and max(final_distance) < .001,
        scope="full physical runs, same initial state and source commands; sampled 10 Hz state convergence",
        dt_s=[a["dt"], b["dt"]], substep_s=[a["dt"]/a["substeps"],b["dt"]/b["substeps"]],
        max_position_difference_m=max_position, worst_position_time_s=worst_time,
        max_rotation_difference_rad=max_angle, max_joint_difference_rad_or_m=max_q,
        final_position_difference_m=final_distance,
        thresholds=dict(position_m=.001,rotation_rad=.01,joint_rad_or_m=.005,final_position_m=.001),
        source_directories=[str(Path(first).resolve()),str(Path(second).resolve())],
        result_sha256=[sha(Path(p)/"result.json") for p in (first,second)],
        state_sha256=[a["states_sha256"],b["states_sha256"]],
        both_complete_and_released=True, friction_only_grasp_verified=False,
        generic_contact_robustness_certified=False)
    Path(output).write_text(json.dumps(report,indent=2)+"\n")
    return report


def reference_tracking(folder, output):
    """Compare actual saved body transforms with source poses at the same time."""
    result,rows=validate_physical(folder);motion=ReferenceMotion()
    cfg=OmegaConf.load(Path(folder)/"config.yaml")
    offset=np.array(cfg.env.robot_mount.pos)+[0,0,float(cfg.robot_control.robot.get("base_riser_height_m",0.))-.02]
    samples=[]
    for row in rows:
        _,_,poses,_,_=motion.sample(row["reference_time_s"])
        errors=[]
        for body,target in zip(row["bodies"],poses):
            position=float(np.linalg.norm(np.array(body["pos"])-offset-target[:3,3]))
            rotation=float((Rotation.from_quat(np.array(body["quat_wxyz"])[[1,2,3,0]])*
                            Rotation.from_matrix(target[:3,:3]).inv()).magnitude())
            errors.append(dict(position_m=position,rotation_rad=rotation))
        samples.append(dict(time_s=row["time_s"],phase=row["phase"],held=row["held"],errors=errors))
    held=[err for s in samples for err,h in zip(s["errors"],s["held"]) if h]
    report=dict(scope="10 Hz integrated body poses versus original video trajectory at identical times",
        source_motion_sha256=motion.sha256,states_sha256=result["states_sha256"],samples=samples,
        max_held_position_error_m=max(e["position_m"] for e in held),
        max_held_rotation_error_rad=max(e["rotation_rad"] for e in held),
        final_released_pose_errors=samples[-1]["errors"])
    Path(output).write_text(json.dumps(report,indent=2)+"\n")
    return report


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--first",required=True);p.add_argument("--second",required=True);p.add_argument("--output",required=True)
    a=p.parse_args();r=compare(a.first,a.second,a.output);print(json.dumps(r,indent=2))
    if not r["passed"]:raise SystemExit(1)
