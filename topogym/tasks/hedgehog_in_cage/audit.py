"""Audit the recorded physical extraction, release, and synchronized videos."""
import json
import subprocess

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .geometry import ROOT
from .plan_escape import CollisionOracle, interpolate


def main():
    out = ROOT / "runs/environment_bootstrap/hedgehog_in_cage/classic_wood"
    result = json.loads((out / "extraction_result.json").read_text())
    if not result.get("success") or not result.get("grasp_released"):
        raise ValueError("The complete physical episode has not passed")
    cfg = OmegaConf.load(out / "extraction_config.yaml")
    rows = [json.loads(line) for line in (out / "extraction_states.jsonl").read_text().splitlines()]
    table_z = float(cfg.env.frames.table_surface.origin[2])
    cage_origin = np.r_[np.asarray(cfg.task.center_xy_m), table_z + float(cfg.task.mount_height_m) + .12]
    cage_r = Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True)
    oracle = CollisionOracle(out / "assets")
    radius = float(np.linalg.norm(oracle.meshes[1].vertices, axis=1).max())
    if radius > .092:
        raise ValueError("Mesh exceeds the swept motion bound")
    poses = [np.r_[cage_r.inv().apply(np.asarray(row["ball_position_m"]) - cage_origin),
        (cage_r.inv() * Rotation.from_quat(row["ball_quaternion_xyzw"])).as_quat()] for row in rows]
    template = json.loads((out / "assets/template.json").read_text())
    scale = float(cfg.task.scale) / 1000
    core_radius = float(template["hedgehog"]["core_radius"]) * scale
    initially_inside = bool(np.linalg.norm(poses[0][:2]) + core_radius < .0675
        and abs(poses[0][2]) + core_radius < .12)
    resolution = .00005
    minimum = np.inf
    # Whole-body radial bounds skip the far-away placement segment. A line
    # segment can approach the cage by at most its endpoint displacement.
    for a, b in zip(poses[:-1], poses[1:]):
        if min(np.linalg.norm(a[:2]), np.linalg.norm(b[:2])) - np.linalg.norm(b[:3]-a[:3]) > .0675 + radius:
            continue
        minimum = min(minimum, min(oracle.distance(q) for q in interpolate(a, b, resolution)))
    final_rows = [r for r in rows if r["time_s"] >= rows[-1]["time_s"] - 2]
    final_positions = np.asarray([r["ball_position_m"] for r in final_rows])
    drift = float(np.linalg.norm(final_positions - final_positions[0], axis=1).max())
    final_speed = max(r["linear_speed_m_s"] for r in final_rows)
    final_angular_speed = max(r["angular_speed_rad_s"] for r in final_rows)
    last = rows[-1]
    lowest_point = float((Rotation.from_quat(last["ball_quaternion_xyzw"]).apply(oracle.meshes[1].vertices)
        + last["ball_position_m"])[:, 2].min())
    release_rows = [r for r in rows if r["phase"] in ("release", "final_settle")]
    released = bool(release_rows) and not any(r["grasp_constraint_active"] for r in release_rows)
    phases = {phase: [r["time_s"] for r in rows if r["phase"] == phase]
        for phase in dict.fromkeys(r["phase"] for r in rows)}
    videos = {}
    expected_frames = round(result["simulated_seconds"] / .005) // 10 + 1
    for name in ("agentview", "front_oblique", "wrist"):
        path = out / f"extraction_{name}.mp4"
        probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,nb_frames,duration", "-of", "json", str(path)]))
        stream = probe["streams"][0]
        stream["matches_physics_duration"] = int(stream["nb_frames"]) == expected_frames
        videos[name] = stream
    passed = bool(initially_inside and minimum > resolution and released and drift < .0002 and final_speed < .001
        and final_angular_speed < np.deg2rad(.5) and lowest_point >= table_z - .0001
        and all(v["matches_physics_duration"] for v in videos.values()))
    report = dict(passed=passed, extraction_success=result["success"],
        initial_core_inside_cage_envelope=initially_inside,
        recorded_path_minimum_sampled_clearance_m=float(minimum),
        recorded_path_interpolation_clearance_lower_bound_m=float(minimum-resolution),
        interpolation_motion_bound_m=resolution,
        interpolation_note="Bounds the piecewise interpolation of recorded states; live solver contact checks are separate evidence.",
        final_2s_drift_m=drift, final_2s_max_speed_m_s=final_speed,
        final_2s_max_angular_speed_rad_s=final_angular_speed,
        final_lowest_point_above_table_m=lowest_point-table_z,
        grasp_constraint_removed=released, videos=videos,
        phases={name:dict(start_s=min(times), end_s=max(times)) for name,times in phases.items()})
    (out / "extraction_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
