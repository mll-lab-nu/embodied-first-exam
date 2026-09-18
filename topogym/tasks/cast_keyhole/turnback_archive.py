"""Archive the push-turn-return physical robot episode and its evidence."""
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .inverse_variants import save, sha
from .long_stroke import relative
from .long_stroke_archive import archive
from .turnback import OUTPUT


def verify_maneuver(folder, proposal):
    """Check the distinctive maneuver in actual physics body poses."""
    trace = json.loads((folder / "trajectory.json").read_text())
    names = ("align_right_tooth", "advance_to_turn_chamber", "turn_in_chamber",
             "return_to_offset_gate", "restore_after_gate")
    frames = {n: [f for f in trace if f["stage"] == n] for n in names}
    if not all(frames.values()):
        raise ValueError("A physical maneuver stage is missing")
    poses = {n: relative(fs[-1]) for n, fs in frames.items()}
    advance, turned, returned = [poses[n] for n in names[1:4]]
    turn_deg = float(np.degrees(Rotation.from_matrix(turned[0] @ advance[0].T).magnitude()))
    return_mm = float((returned[1][1] - turned[1][1]) * 1000)
    held_deg = float(np.degrees(Rotation.from_matrix(returned[0] @ turned[0].T).magnitude()))
    restored_deg = float(np.degrees(Rotation.from_matrix(poses[names[-1]][0] @ poses[names[0]][0].T).magnitude()))
    passed = (abs(turn_deg - proposal["turn_angle_deg"]) < 1.
              and abs(return_mm - proposal["return_distance_scene_mm"]) < 1.
              and held_deg < 1. and restored_deg < 1.)
    result = dict(passed=passed, observed_turn_angle_deg=turn_deg,
                  observed_return_distance_mm=return_mm,
                  orientation_change_during_return_deg=held_deg,
                  restored_orientation_error_deg=restored_deg,
                  actual_physics_trace_sha256=sha(folder / "trajectory.json"),
                  stage_end_steps={n: fs[-1]["physics_step"] for n, fs in frames.items()})
    if not passed:
        raise ValueError(f"Physical maneuver differs from the proposed sequence: {result}")
    return result


if __name__ == "__main__":
    proposal = json.loads((OUTPUT / "proposal.json").read_text())
    design = json.loads((OUTPUT / "design_result.json").read_text())
    required = {"unchanged_solved_robot_ik", "omit_forward_excursion",
                "omit_return_diagonal_exit", "omit_chamber_turn"}
    if (not design["passed"] or design["variant"] != "turnback"
            or design["generator_sha256"] != sha(Path(__file__).with_name("turnback.py"))
            or design["certificate_sha256"] != sha(OUTPUT / "certificate.json")
            or not required.issubset(design["negative_controls"])
            or not all(c["collision_found"] for c in design["negative_controls"].values())):
        raise ValueError("Missing or changed push-turn-return design evidence")
    actual = {name: verify_maneuver(OUTPUT / name, proposal)
              for name in ("robot_physics", "robot_physics_half")}
    save(OUTPUT / "maneuver_execution.json", dict(passed=True, physics=actual))
    angle, distance = proposal["turn_angle_deg"], proposal["return_distance_scene_mm"]
    archive(
        variant=OUTPUT,
        run_id="2026-09-17_turnback_v1",
        generator="turnback",
        scope=f"前送—转向—回退型：深入转向空间后转动{angle:g}°，保持新姿态回退{distance:g} mm（场景尺寸），再横移、恢复姿态并完整分离；由新IK扫掠体反推窗口和挡肩。原IK、省略前送、省略转动及省略回退的斜切捷径均发生碰撞；未证明全局唯一解。预抓取起点，双指接触后辅助抓持，分离后双臂保持。七路视频来自同一次物理执行；1 ms与0.5 ms时间步均通过独立检查。",
    )
