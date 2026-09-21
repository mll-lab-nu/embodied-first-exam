"""Compare two complete robot executions at nominal and half time steps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation, Slerp

from .physics import save
from .render import physical_assets_signature, sha


def compare(nominal, refined, output):
    directories = {
        "nominal": Path(nominal).resolve(),
        "refined": Path(refined).resolve(),
    }
    reports = {
        key: json.loads((path / "report.json").read_text())
        for key, path in directories.items()
    }
    traces = {
        key: [
            row
            for row in json.loads((path / "frames.json").read_text())
            if row["phase"] == "traverse"
        ]
        for key, path in directories.items()
    }
    start = max(rows[0]["progress"] for rows in traces.values())
    end = min(rows[-1]["progress"] for rows in traces.values())
    progress = np.linspace(start, end, 2001)
    poses = {}
    for key, rows in traces.items():
        u = np.array([row["progress"] for row in rows])
        if np.any(np.diff(u) <= 0):
            raise ValueError("Traversal progress must strictly increase")
        p = np.array([row["position_m"] for row in rows])
        r = Rotation.from_quat(
            np.array([row["quaternion_wxyz"] for row in rows])[:, [1, 2, 3, 0]]
        )
        poses[key] = (
            np.column_stack([np.interp(progress, u, p[:, j]) for j in range(3)]),
            Slerp(u, r)(progress),
        )
    dp = np.linalg.norm(poses["nominal"][0] - poses["refined"][0], axis=1)
    dr = (poses["nominal"][1].inv() * poses["refined"][1]).magnitude()
    equivalent = physical_assets_signature(
        directories["nominal"] / "assets"
    ) == physical_assets_signature(directories["refined"] / "assets")
    settings = {}
    for key, path in directories.items():
        cfg = OmegaConf.to_container(OmegaConf.load(path / "config.yaml"), resolve=True)
        cfg["env"]["sim"].pop("dt")
        settings[key] = cfg
        plan = json.loads((path / "planning/plan.json").read_text())
        if (
            not plan["passed"]
            or abs(plan["frames"][0]["progress"]) > 1e-12
            or abs(plan["frames"][-1]["progress"] - plan["release_progress"]) > 1e-12
            or not plan["remaining_path_is_terminal_post"]
        ):
            raise ValueError("Qualification requires the complete maze and final post")
    servo_fields = (
        "gripper_half_gap_command_m",
        "gripper_driver_kp",
        "gripper_driver_kv",
        "gripper_max_driver_torque_nm",
        "noslip_iterations",
        "noslip_tolerance",
        "feedback_rate_hz",
    )
    checks = dict(
        both_complete_and_passed=all(
            r["passed"] and r["complete"] and r["terminal_stop_reached"]
            for r in reports.values()
        ),
        contact_penetration_below_0_5mm=all(
            r["maxima"]["wand_penetration_m"] < 0.0005 for r in reports.values()
        ),
        terminal_stops_reached=all(
            r.get("terminal_stop_reached", False) for r in reports.values()
        ),
        final_states_settled=all(
            r.get("final_linear_speed_m_s", float("inf")) < 0.002
            and r.get("final_angular_speed_rad_s", float("inf")) < 0.02
            for r in reports.values()
        ),
        settled_for_required_window=all(
            r.get("settled_continuous_seconds", 0.0)
            >= r.get("settled_window_seconds", 0.0)
            for r in reports.values()
        ),
        half_time_step=abs(reports["nominal"]["dt"] / 2 - reports["refined"]["dt"])
        < 1e-12,
        same_settings_except_time_step=settings["nominal"] == settings["refined"],
        same_gripper_servo_settings=all(
            reports["nominal"][k] == reports["refined"][k] for k in servo_fields
        ),
        bilateral_grasp_throughout_traverse=all(
            r["total_traverse_steps"] > 0
            and r["bilateral_traverse_contact_steps"] == r["total_traverse_steps"]
            for r in reports.values()
        ),
        same_robot_plan=reports["nominal"]["plan_sha256"]
        == reports["refined"]["plan_sha256"],
        same_physical_assets=equivalent,
        no_pose_driving=all(
            not r["live_object_pose_overwrites"]
            and not r["live_robot_pose_overwrites"]
            and not r["object_external_wrenches"]
            for r in reports.values()
        ),
        passive_release_energy_bounded=all(
            r.get("passive_release_energy", {}).get("initial_j") is not None
            and r["passive_release_energy"]["maximum_j"]
            <= r["passive_release_energy"]["initial_j"]
            + r["passive_release_energy"]["tolerance_j"]
            for r in reports.values()
        ),
        pure_contact_grasps=all(not r["assisted_grasp"] for r in reports.values()),
        zero_wire_contacts_while_grasped=all(
            r["traverse_wire_contact_steps"] == 0 for r in reports.values()
        ),
        controlled_position_difference_below_2mm=float(dp.max()) < 0.002,
        controlled_orientation_difference_below_0_1rad=float(dr.max()) < 0.1,
    )
    result = dict(
        passed=all(checks.values()),
        checks=checks,
        scope="This compact single-arm instance and recorded policy only; nominal/refined contact dynamics, full maze, release and settle.",
        comparison_scope="Matched route progress while grasped; gravity-release trajectories are checked for stable completion independently.",
        maximum_controlled_position_difference_m=float(dp.max()),
        maximum_controlled_orientation_difference_rad=float(dr.max()),
        comparison_progress_range=[float(start), float(end)],
        reports=reports,
        runs={
            key: dict(
                directory=str(path),
                report_sha256=sha(path / "report.json"),
                frames_sha256=sha(path / "frames.json"),
            )
            for key, path in directories.items()
        },
    )
    output = Path(output)
    save(output, result)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    axes[0].plot(progress, 1000 * dp)
    axes[0].set_ylabel("Position difference (mm)")
    axes[0].axhline(2, color="r", ls="--")
    axes[1].plot(progress, np.rad2deg(dr))
    axes[1].set_ylabel("Orientation difference (deg)")
    axes[1].set_xlabel("Route progress")
    for ax in axes:
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output.with_suffix(".png"), dpi=160)
    plt.close(fig)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("reports", "runs")}, indent=2
        )
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nominal", type=Path, required=True)
    parser.add_argument("--refined", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.nominal, args.refined, args.output)
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
