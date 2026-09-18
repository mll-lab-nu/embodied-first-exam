"""Export the saved rehearsal without solving IK or changing its commands."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .robot_motion import Kinematics

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "runs/demo_metadata/horseshoe_ring/2026-09-16_aloha_full"
OUTPUT = ROOT / "runs/environment-solvability/horseshoe_ring/fixed_ik_trace_v1"


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode()).hexdigest()


def command_hash(motion):
    """The whole 16-qpos/time contract, including both passive finger rails."""
    return canonical_hash(dict(fps=motion["fps"], qpos=[f["qpos"] for f in motion["frames"]]))


def export_trace(source=SOURCE, output=OUTPUT):
    source, output = Path(source), Path(output)
    motion = json.loads((source / "robot_motion.json").read_text())
    cfg = OmegaConf.load(source / "config.yaml")
    kin = Kinematics(cfg.robot_control)
    names = [kin.model.joint(i).name for i in range(kin.model.njnt)]
    if len(names) != 16 or kin.model.nq != 16:
        raise ValueError("Expected the recorded ALOHA 16-qpos articulation")
    mount = np.asarray(cfg.env.robot_mount.pos)
    mount_r = Rotation.from_euler("xyz", cfg.env.robot_mount.euler, degrees=True)
    frames = []
    maximum_saved_target_error = 0.
    for i, frame in enumerate(motion["frames"]):
        kin.q = np.asarray(frame["qpos"], dtype=float)
        if not np.isfinite(kin.q).all():
            raise ValueError("Nonfinite recorded joint state")
        if np.any(kin.q < kin.model.jnt_range[:, 0]-1e-12) or np.any(kin.q > kin.model.jnt_range[:, 1]+1e-12):
            raise ValueError("Recorded joint state exceeds the source model limits")
        tips = {}
        for side in ("left", "right"):
            p, r = kin.pose(side)
            tips[side] = dict(pos_m=(mount+mount_r.apply(p)).tolist(),
                              quat_xyzw=(mount_r*r).as_quat().tolist())
            if side in frame["grasp_targets"]:
                maximum_saved_target_error = max(maximum_saved_target_error,
                    float(np.linalg.norm(p-frame["grasp_targets"][side]["pos"])))
        frames.append(dict(frame=i, time_s=i/motion["fps"], phase=frame["stage"],
            qpos=frame["qpos"], tcp_world=tips,
            finger_rail_qpos_m={"left": frame["qpos"][6:8], "right": frame["qpos"][14:16]},
            geometry_source_index=frame["source_index"]))
    if maximum_saved_target_error > .0005:
        raise ValueError("FK no longer reproduces the saved gripper targets")
    trace = dict(schema_version=1, task="horseshoe_ring", robot="aloha", fps=motion["fps"],
        duration_s=len(frames)/motion["fps"], last_sample_time_s=frames[-1]["time_s"],
        joint_names=names, joint_units=["rad"]*6+["m"]*2+["rad"]*6+["m"]*2,
        actuated_qpos_indices=list(range(7))+list(range(8, 15)),
        passive_finger_qpos_indices=[7, 15],
        tcp_definition="Centre of the finger pads; gripper_link offset [0.14381, 0, -0.00355] m",
        world_from_robot_mount=dict(pos_m=mount.tolist(), quat_xyzw=mount_r.as_quat().tolist()),
        export_contract="Copy this recording's 16 joint states, frame rate, phases and gripper schedule; export itself performs FK only",
        interpolation_scope="Saved 12 Hz samples; interpolating qpos does not inherit a continuous robot collision certificate",
        command_sha256=command_hash(motion), source_frames_sha256=canonical_hash(motion["frames"]),
        source_motion_file_sha256=hashlib.sha256((source/"robot_motion.json").read_bytes()).hexdigest(),
        source_geometry_template_sha256=motion["report"]["source_template_sha256"],
        source_config_sha256=hashlib.sha256((source/"config.yaml").read_bytes()).hexdigest(),
        phases=motion["phases"], frames=frames,
        validation=dict(qpos_exactly_copied=True, joint_limits_passed=True,
            maximum_saved_tcp_position_error_m=maximum_saved_target_error,
            source_sampled_collision_passed=motion["report"]["sampled_robot_scene_clearance_passed"],
            physics_steps=0, dynamic_execution_verified=False,
            initial_condition="Pre-positioned grasp; no table pickup; handover support is a kinematic assumption"))
    output.mkdir(parents=True, exist_ok=True)
    (output/"ik_trace.json").write_text(json.dumps(trace, ensure_ascii=False)+"\n")
    with (output/"ik_trace.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        tip_cols = [f"{side}_tcp_{v}" for side in ("left", "right") for v in ("x_m", "y_m", "z_m", "qx", "qy", "qz", "qw")]
        writer.writerow(["frame", "time_s", "phase", *names, *tip_cols])
        for frame in frames:
            tips = [v for side in ("left", "right") for key in ("pos_m", "quat_xyzw") for v in frame["tcp_world"][side][key]]
            writer.writerow([frame["frame"], frame["time_s"], frame["phase"], *frame["qpos"], *tips])
    (output/"trace_summary.json").write_text(json.dumps({k: v for k, v in trace.items() if k != "frames"}, ensure_ascii=False, indent=2)+"\n")
    return trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    trace = export_trace(args.source, args.output)
    print(json.dumps(dict(frames=len(trace["frames"]), command_sha256=trace["command_sha256"],
                         validation=trace["validation"]), indent=2))


if __name__ == "__main__":
    main()
