"""Redesigned stacked-plate demo: rotate vertical disks on a Y rod to align sectors.

Each disk is a revolute joint about the horizontal Y rod. The arm pinches a disk's
rim between its two finger pads and rolls it downward; the disk turns **only from
finger friction** (no joint writes, no teleport), so the arc is contact-driven and
honest to the collision-based IL contract. Success = all disks' sector angles
within tolerance, with real rotation / follow-error / release-drift checks.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import load_topogym_configs
from topogym.generation import EpisodeResult, build_stacked_plate_episode_spec
from topogym.planning import plan_stacked_plate_rotation
from topogym.primitives import (
    RimRotatePrimitive,
    configure_gripper_contact_friction,
    print_collision_il_contract,
)
from topogym.tasks import (
    StackedPlatePuzzleEvaluator,
    StackedPlateSceneBuilder,
)
from topogym.utils import (
    add_recording_args,
    initialize_franka_controller,
    merge_recording_config,
    print_recording_saved,
    recording_session_from_config,
)


CONFIG_ROOT = Path(__file__).resolve().parents[1] / "configs"
DEFAULT_COMMON_CONFIG = CONFIG_ROOT / "common_configs" / "manipulation_space_tabletop_v1.yaml"
DEFAULT_ENV_CONFIG = CONFIG_ROOT / "env_configs" / "world_tabletop_v1.yaml"
DEFAULT_ROBOT_CONFIG = CONFIG_ROOT / "robot_control_configs" / "franka_panda_position_ik.yaml"
DEFAULT_TASK_CONFIG = CONFIG_ROOT / "task_configs" / "stacked_plate_topogym_tabletop_v1.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rotate vertical disks on a Y rod (pinch rim, roll down) to align their missing sectors."
    )
    parser.add_argument("--common-config", type=Path, default=DEFAULT_COMMON_CONFIG)
    parser.add_argument("--env-config", type=Path, default=DEFAULT_ENV_CONFIG)
    parser.add_argument("--robot-config", type=Path, default=DEFAULT_ROBOT_CONFIG)
    parser.add_argument("--task-config", type=Path, default=DEFAULT_TASK_CONFIG)
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), default=None)
    parser.add_argument("--viewer", action="store_true")
    parser.add_argument("--seed", type=int, default=0, help="Stable episode seed / variant id.")
    parser.add_argument("--variant-id", default="default")
    parser.add_argument("--keep-open", action="store_true")
    parser.add_argument("--close-on-finish", action="store_true")
    parser.add_argument("--settle-steps", type=int, default=None)
    parser.add_argument("--move-steps", type=int, default=None)
    parser.add_argument("--arc-steps", type=int, default=None)
    parser.add_argument("--gripper-steps", type=int, default=None)
    parser.add_argument("--grasp-qpos", type=float, default=None)
    parser.add_argument("--noslip-iterations", type=int, default=None)
    parser.add_argument("--target-angle-degrees", type=float, default=None)
    parser.add_argument("--verbose", action="store_true")
    add_recording_args(parser, default_fps=60, default_camera="oblique")
    return parser.parse_args()


def load_configs(args: argparse.Namespace):
    cfg = load_topogym_configs(
        common_config=args.common_config,
        env_config=args.env_config,
        robot_config=args.robot_config,
        task_config=args.task_config,
    )
    overrides: dict = {}
    if args.backend is not None:
        overrides.setdefault("env", {}).setdefault("genesis", {})["backend"] = args.backend
    if args.target_angle_degrees is not None:
        overrides.setdefault("task", {}).setdefault("oracle", {})[
            "target_angle_deg"
        ] = float(args.target_angle_degrees)
    if args.noslip_iterations is not None:
        overrides.setdefault("task", {}).setdefault("physical", {})[
            "noslip_iterations"
        ] = int(args.noslip_iterations)
    if overrides:
        cfg = OmegaConf.merge(cfg, overrides)
    return merge_recording_config(cfg, args)


def _physical_value(physical, name: str, override):
    return getattr(physical, name) if override is None else override


def _hud(plate_scene, status: dict):
    evaluator = StackedPlatePuzzleEvaluator()

    def render_lines():
        state = evaluator.classify(plate_scene)
        return [
            "task=stacked_plate (disks/sector)",
            f"phase={status.get('phase', 'setup')}",
            f"disk={status.get('disk', '-')}",
            f"spread={np.rad2deg(state.alignment_spread):.1f}deg (tol={np.rad2deg(state.alignment_tolerance):.1f})",
            f"aligned={state.is_terminal}",
        ]

    return render_lines


def _build_primitive(cfg, plate_scene, args) -> RimRotatePrimitive:
    physical = cfg.task.physical
    layout = plate_scene.layout
    return RimRotatePrimitive(
        approach_z=layout.world_z(float(physical.approach_z)),
        steps_move=int(_physical_value(physical, "move_steps", args.move_steps)),
        steps_arc=int(_physical_value(physical, "arc_steps", args.arc_steps)),
        gripper_steps=int(_physical_value(physical, "gripper_steps", args.gripper_steps)),
        grasp_qpos=float(_physical_value(physical, "grasp_qpos", args.grasp_qpos)),
        grasp_yaw_offset=float(physical.grasp_yaw_offset),
        approach_clearance=float(getattr(physical, "approach_clearance", 0.035)),
        retreat_clearance=float(getattr(physical, "retreat_clearance", 0.035)),
        close_hold_steps=int(physical.close_hold_steps),
        arc_settle_steps=int(physical.arc_settle_steps),
        release_hold_steps=int(physical.release_hold_steps),
        rotation_tolerance=float(np.deg2rad(float(physical.rotation_tolerance_deg))),
        min_rotation=float(np.deg2rad(float(physical.min_rotation_deg))),
        max_follow_error=float(getattr(physical, "max_rim_follow_error", 0.05)),
        max_release_drift=float(np.deg2rad(float(physical.max_release_drift_deg))),
        verbose=args.verbose,
    )


def run_demo(args, cfg, plate_scene, controller, status, *, episode_spec, episode_plan, commands) -> EpisodeResult:
    physical = cfg.task.physical
    layout = plate_scene.layout
    print_collision_il_contract(
        "stacked_plate_physical_rotate_demo",
        manipulated=tuple(f"disk_{c.disk_name}" for c in commands),
        success_checks=("rotation_achieved", "rim_follow_error", "target_angle_error", "release_drift", "sector_alignment"),
    )
    configure_gripper_contact_friction(
        entities=list(plate_scene.articulated_plate_entities.values()),
        robot=controller.robot,
        finger_links=physical.finger_links,
        object_friction=float(physical.disk_friction),
        finger_friction=float(physical.finger_friction),
    )

    controller.step(int(_physical_value(physical, "settle_steps", args.settle_steps)))
    primitive = _build_primitive(cfg, plate_scene, args)
    print(
        "stacked_plate_physical_rotate_demo setup "
        f"episode_id={episode_spec.stable_id()} plan_id={episode_plan.plan_id} "
        f"disks={[c.disk_name for c in commands]} "
        f"target_angle={np.rad2deg(layout.target_angle()):.1f}deg arc_steps={primitive.steps_arc}",
        flush=True,
    )

    results = []
    max_follow_error = 0.0
    for command in commands:
        status.update(disk=command.disk_name, phase="rotate")
        result = primitive.run(
            controller,
            disk_entity=plate_scene.articulated_plate_entities[command.disk_name],
            dof=plate_scene.plate_joint_dofs[command.disk_name],
            disk_name=command.disk_name,
            center=command.center_xyz,
            radius=command.radius,
            target_angle=command.target_angle,
            grasp_azimuth=command.grasp_azimuth,
            roll_sign=command.roll_sign,
            grasp_radius_scale=command.grasp_radius_scale,
        )
        results.append(result)
        max_follow_error = max(max_follow_error, result.max_follow_error)
        if args.verbose:
            print(
                f"stacked_plate_physical_rotate_demo disk={command.disk_name} "
                f"rotation_achieved={np.rad2deg(result.rotation_achieved):+.1f}deg "
                f"final_angle={np.rad2deg(result.final_disk_angle):+.1f}deg "
                f"target_error={np.rad2deg(result.target_error):.2f}deg "
                f"follow_error={result.max_follow_error:.4f} "
                f"release_drift={np.rad2deg(result.release_drift):.2f}deg "
                f"driven={result.driven} success={result.success}",
                flush=True,
            )

    status["phase"] = "verify"
    controller.step(max(0, int(physical.final_hold_steps)))
    state = StackedPlatePuzzleEvaluator().classify(plate_scene)
    follow_limit = float(getattr(physical, "max_rim_follow_error", 0.05))
    task_success = bool(state.is_terminal)
    physical_quality_success = bool(
        task_success
        and all(result.success for result in results)
        and max_follow_error <= follow_limit
    )
    status["phase"] = "success" if task_success else "failed"

    metrics = {
        "task_success": bool(task_success),
        "physical_quality_success": bool(physical_quality_success),
        "aligned": bool(state.is_terminal),
        "alignment_spread_deg": float(np.rad2deg(state.alignment_spread)),
        "alignment_tolerance_deg": float(np.rad2deg(state.alignment_tolerance)),
        "max_follow_error": float(max_follow_error),
        "all_disks_driven": bool(all(result.driven for result in results)),
    }
    episode_result = (
        EpisodeResult.ok(episode_spec.key, metrics=metrics, export_ready=physical_quality_success)
        if task_success
        else EpisodeResult.failed(
            episode_spec.key, "sectors_not_aligned", metrics=metrics, stable_ready=False
        )
    )
    print(
        "stacked_plate_physical_rotate_demo result "
        f"episode_id={episode_spec.stable_id()} success={episode_result.success} "
        f"task_success={task_success} "
        f"physical_quality_success={physical_quality_success} "
        f"aligned={state.is_terminal} spread={np.rad2deg(state.alignment_spread):.2f}deg "
        f"max_follow_error={max_follow_error:.4f}",
        flush=True,
    )
    return episode_result


def main() -> None:
    args = parse_args()
    cfg = load_configs(args)
    episode_spec = build_stacked_plate_episode_spec(
        cfg,
        seed=args.seed,
        common_config=args.common_config,
        env_config=args.env_config,
        robot_config=args.robot_config,
        task_config=args.task_config,
        variant_id=args.variant_id,
    )
    has_display = os.name == "nt" or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if args.viewer and not has_display:
        raise SystemExit("No graphical display detected.")
    noslip_iterations = int(cfg.task.physical.noslip_iterations)
    if noslip_iterations < 0:
        raise SystemExit("noslip-iterations must be non-negative.")

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(
        backend=backends[cfg.env.genesis.backend],
        precision=cfg.env.genesis.precision,
        logging_level=cfg.env.genesis.logging_level,
    )
    print(
        f"stacked_plate_physical_rotate_demo building_scene backend={cfg.env.genesis.backend} viewer={args.viewer}",
        flush=True,
    )
    plate_scene = StackedPlateSceneBuilder(
        cfg.env,
        cfg.task,
        cfg.robot_control,
        rigid_options=gs.options.RigidOptions(noslip_iterations=noslip_iterations),
    ).build(show_viewer=args.viewer)
    commands, episode_plan = plan_stacked_plate_rotation(plate_scene.layout)
    print("stacked_plate_physical_rotate_demo scene_ready", flush=True)
    controller = initialize_franka_controller(
        scene=plate_scene.scene,
        manifest=plate_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0,
    )
    print(
        f"stacked_plate_physical_rotate_demo robot_home_ready hand={controller.hand_pos().tolist()}",
        flush=True,
    )

    status = {"phase": "setup", "disk": "-"}
    with recording_session_from_config(
        plate_scene.scene,
        plate_scene.cameras,
        cfg.recording,
        hud=_hud(plate_scene, status),
    ):
        run_demo(
            args,
            cfg,
            plate_scene,
            controller,
            status,
            episode_spec=episode_spec,
            episode_plan=episode_plan,
            commands=commands,
        )

    print_recording_saved(cfg.recording)


if __name__ == "__main__":
    main()
