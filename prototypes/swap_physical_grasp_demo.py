from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import add_common_config_arg, load_topogym_configs
from topogym.data import dataset_writer_or_null
from topogym.generation import EpisodeResult, build_swap_episode_spec
from topogym.planning import SwapMoveCommand, plan_swap_move
from topogym.primitives import (
    PickPlacePrimitive,
    configure_gripper_contact_friction,
    ee_quat_for_yaw,
    entity_pos,
    print_collision_il_contract,
    validate_rigid_friction,
)
from topogym.tasks import SwapSceneBuilder
from topogym.verification import SwapPuzzleEvaluator
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
DEFAULT_TASK_CONFIG = CONFIG_ROOT / "task_configs" / "swap_topogym_tabletop_v1.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Move one Swap block using only Franka gripper contact and rigid-body physics."
    )
    parser.add_argument("--env-config", type=Path, default=DEFAULT_ENV_CONFIG)
    parser.add_argument("--robot-config", type=Path, default=DEFAULT_ROBOT_CONFIG)
    parser.add_argument("--task-config", type=Path, default=DEFAULT_TASK_CONFIG)
    add_common_config_arg(parser, default=DEFAULT_COMMON_CONFIG)
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), default=None)
    parser.add_argument("--viewer", action="store_true", help="Open the Genesis viewer.")
    parser.add_argument("--keep-open", action="store_true", help="Keep stepping after the attempt.")
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Stable episode seed. Current Swap layout is deterministic; this identifies the variant.",
    )
    parser.add_argument(
        "--variant-id",
        default="default",
        help="Stable variant label for manifests and result lines.",
    )
    parser.add_argument("--block", default=None, help="Block name; defaults to task.oracle.block_to_move.")
    parser.add_argument("--source-slot", type=int, default=None)
    parser.add_argument("--target-slot", type=int, default=None)
    parser.add_argument(
        "--motion-steps",
        type=int,
        default=None,
        help="Linear IK waypoints per arm-motion phase.",
    )
    parser.add_argument("--gripper-steps", type=int, default=None)
    parser.add_argument(
        "--grasp-qpos",
        type=float,
        default=None,
        help="Per-finger target qpos. Default is the robot's fully closed target.",
    )
    parser.add_argument("--grasp-yaw", type=float, default=0.0, help="Top-down grasp yaw in radians.")
    parser.add_argument("--close-hold-steps", type=int, default=None)
    parser.add_argument("--place-hold-steps", type=int, default=None)
    parser.add_argument("--release-hold-steps", type=int, default=None)
    parser.add_argument("--lift-check-delta", type=float, default=None)
    parser.add_argument("--min-lift-delta", type=float, default=None)
    parser.add_argument("--max-grasp-xy-error", type=float, default=None)
    parser.add_argument("--block-friction", type=float, default=None)
    parser.add_argument("--finger-friction", type=float, default=None)
    parser.add_argument("--noslip-iterations", type=int, default=None)
    parser.add_argument(
        "--no-friction-override",
        action="store_true",
        help="Use friction values parsed/defaulted by Genesis instead of task.physical overrides.",
    )
    add_recording_args(parser, default_fps=60, default_camera="oblique")
    parser.add_argument(
        "--record-dataset",
        type=Path,
        default=None,
        help="Write a RoboMME-structural HDF5 dataset for this episode to this path.",
    )
    parser.add_argument(
        "--dataset-every-n-steps",
        type=int,
        default=10,
        help="Capture one dataset frame every N scene.step() calls (action granularity).",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def _swap_task_goal(move: SwapMoveCommand) -> str:
    return (
        f"Move the {move.block_name} from slot {move.source_slot} "
        f"to slot {move.target_slot}."
    )


def load_configs(args: argparse.Namespace):
    cfg = load_topogym_configs(
        common_config=args.common_config,
        env_config=args.env_config,
        robot_config=args.robot_config,
        task_config=args.task_config,
    )
    if args.backend is not None:
        cfg = OmegaConf.merge(cfg, {"env": {"genesis": {"backend": args.backend}}})
    return merge_recording_config(cfg, args)


def _config_value(cli_value, config_value, cast):
    return cast(config_value if cli_value is None else cli_value)


def _positive_steps(value: int, name: str) -> int:
    value = int(value)
    if value <= 0:
        raise SystemExit(f"{name} must be a positive integer; got {value}.")
    return value


def _nonnegative_steps(value: int, name: str) -> int:
    value = int(value)
    if value < 0:
        raise SystemExit(f"{name} must be non-negative; got {value}.")
    return value


def _positive_float(value: float, name: str) -> float:
    value = float(value)
    if value <= 0.0:
        raise SystemExit(f"{name} must be positive; got {value}.")
    return value


def _configure_contact_friction(
    swap_scene,
    controller,
    *,
    block_friction: float,
    finger_friction: float,
    finger_links,
) -> None:
    configure_gripper_contact_friction(
        entities=[
            swap_scene.manifest.get(block_name)
            for block_name in swap_scene.layout.block_names()
        ],
        robot=controller.robot,
        finger_links=finger_links,
        object_friction=block_friction,
        finger_friction=finger_friction,
    )


def _swap_hud(swap_scene):
    evaluator = SwapPuzzleEvaluator(
        tolerance_xy=float(swap_scene.layout.cfg.task.success_tolerance_xy)
    )

    def render_lines():
        state = evaluator.classify(swap_scene)
        return [
            "task=swap physical grasp",
            f"reward={state.reward():+.2f}",
            f"terminal={state.is_terminal}",
            f"empty={list(state.empty_slots)}",
        ]

    return render_lines


def _validate_physical_move(move: SwapMoveCommand, swap_scene) -> None:
    layout = swap_scene.layout
    block_pos = entity_pos(swap_scene.manifest.get(move.block_name))
    source_xy = layout.slot_xy(move.source_slot)
    source_error = float(np.linalg.norm(block_pos[:2] - source_xy))
    if source_error > float(layout.cfg.task.success_tolerance_xy):
        raise SystemExit(
            f"{move.block_name} is not at source slot {move.source_slot}: "
            f"xy error is {source_error:.4f} m. "
            "This physical demo will not teleport it into place."
        )

    target_xy = layout.slot_xy(move.target_slot)
    tolerance = float(layout.cfg.task.success_tolerance_xy)
    occupied_by = [
        other_name
        for other_name in layout.block_names()
        if other_name != move.block_name
        and float(np.linalg.norm(entity_pos(swap_scene.manifest.get(other_name))[:2] - target_xy))
        <= tolerance
    ]
    if occupied_by:
        raise SystemExit(
            f"Target slot {move.target_slot} is occupied by {occupied_by}; choose an empty slot."
        )


def run_demo(
    args: argparse.Namespace,
    cfg,
    swap_scene,
    controller,
    *,
    episode_spec,
    episode_plan,
    move: SwapMoveCommand,
) -> EpisodeResult:
    physical_cfg = cfg.task.physical
    _validate_physical_move(move, swap_scene)
    block = swap_scene.manifest.get(move.block_name)
    print_collision_il_contract(
        "swap_physical_grasp_demo",
        manipulated=(move.block_name,),
        success_checks=(
            "lift_delta",
            "grasp_xy_error",
            "place_xy_error",
            "place_z_error",
            "puzzle_terminal",
        ),
    )

    block_friction = validate_rigid_friction(
        _config_value(args.block_friction, physical_cfg.block_friction, float),
        "block-friction",
    )
    finger_friction = validate_rigid_friction(
        _config_value(args.finger_friction, physical_cfg.finger_friction, float),
        "finger-friction",
    )
    if not args.no_friction_override:
        _configure_contact_friction(
            swap_scene,
            controller,
            block_friction=block_friction,
            finger_friction=finger_friction,
            finger_links=physical_cfg.finger_links,
        )

    motion_steps = _positive_steps(
        _config_value(args.motion_steps, cfg.task.primitive.steps_per_phase, int),
        "motion-steps",
    )
    gripper_steps = _positive_steps(
        _config_value(args.gripper_steps, cfg.task.primitive.gripper_steps, int),
        "gripper-steps",
    )
    close_hold_steps = _nonnegative_steps(
        _config_value(args.close_hold_steps, physical_cfg.close_hold_steps, int),
        "close-hold-steps",
    )
    place_hold_steps = _nonnegative_steps(
        _config_value(
            args.place_hold_steps, getattr(physical_cfg, "place_hold_steps", 0), int
        ),
        "place-hold-steps",
    )
    release_hold_steps = _nonnegative_steps(
        _config_value(args.release_hold_steps, physical_cfg.release_hold_steps, int),
        "release-hold-steps",
    )
    lift_check_delta = _positive_float(
        _config_value(args.lift_check_delta, physical_cfg.lift_check_delta, float),
        "lift-check-delta",
    )
    min_lift_delta = _positive_float(
        _config_value(args.min_lift_delta, physical_cfg.min_lift_delta, float),
        "min-lift-delta",
    )
    max_grasp_xy_error = _positive_float(
        _config_value(
            args.max_grasp_xy_error,
            physical_cfg.max_grasp_xy_error,
            float,
        ),
        "max-grasp-xy-error",
    )
    # Default the grasp target from config (matched to the block half-width) instead of the
    # primitive's fully-closed default; --grasp-qpos still overrides. Falls back to None
    # (fully closed) if a task config doesn't define physical.grasp_qpos.
    grasp_qpos_cfg = getattr(physical_cfg, "grasp_qpos", None)
    grasp_qpos = (
        float(args.grasp_qpos)
        if args.grasp_qpos is not None
        else (float(grasp_qpos_cfg) if grasp_qpos_cfg is not None else None)
    )
    primitive = PickPlacePrimitive(
        approach_z=swap_scene.layout.world_z(cfg.task.primitive.approach_z),
        grasp_z=swap_scene.layout.world_z(cfg.task.primitive.grasp_z),
        lift_z=swap_scene.layout.world_z(cfg.task.primitive.lift_z),
        place_z=swap_scene.layout.world_z(cfg.task.primitive.place_z),
        steps_per_phase=motion_steps,
        gripper_steps=gripper_steps,
        grasp_qpos=grasp_qpos,
        close_hold_steps=close_hold_steps,
        place_hold_steps=place_hold_steps,
        release_hold_steps=release_hold_steps,
        lift_check_delta=lift_check_delta,
        min_lift_delta=min_lift_delta,
        max_grasp_xy_error=max_grasp_xy_error,
        place_tolerance_xy=float(cfg.task.task.success_tolerance_xy),
        place_tolerance_z=float(physical_cfg.place_tolerance_z),
        verbose=args.verbose,
    )

    source_xy = entity_pos(block)[:2]
    target_xy = swap_scene.layout.slot_xy(move.target_slot)
    print(
        "swap_physical_grasp_demo setup "
        f"episode_id={episode_spec.stable_id()} plan_id={episode_plan.plan_id} "
        f"block={move.block_name} source_slot={move.source_slot} target_slot={move.target_slot} "
        f"phases={len(PickPlacePrimitive.NOMINAL_PHASES)} "
        f"phase_names={','.join(PickPlacePrimitive.NOMINAL_PHASES)} "
        f"friction_override={not args.no_friction_override} "
        f"block_friction={block_friction:.2f} finger_friction={finger_friction:.2f}"
    )

    result = primitive.run(
        controller,
        block=block,
        source_xy=source_xy,
        target_xy=target_xy,
        ee_quat=ee_quat_for_yaw(controller.default_ee_quat, args.grasp_yaw),
    )
    puzzle_state = SwapPuzzleEvaluator(
        tolerance_xy=float(cfg.task.task.success_tolerance_xy)
    ).classify(swap_scene)
    stable_ready = bool(result.success and puzzle_state.is_terminal)
    metrics = {
        "physical_success": bool(result.success),
        "puzzle_terminal": bool(puzzle_state.is_terminal),
        "grasped": bool(result.grasped),
        "placed": bool(result.placed),
    }
    episode_result = (
        EpisodeResult.ok(
            episode_spec.key,
            metrics=metrics,
            export_ready=stable_ready,
        )
        if stable_ready
        else EpisodeResult.failed(
            episode_spec.key,
            result.failure_reason or "swap_not_terminal",
            metrics=metrics,
            stable_ready=False,
        )
    )
    print(
        "swap_physical_grasp_demo result "
        f"episode_id={episode_spec.stable_id()} success={episode_result.success} "
        f"status={episode_result.status.value} "
        f"physical_success={result.success} "
        f"stable_ready={episode_result.stable_ready} export_ready={episode_result.export_ready} "
        f"grasped={result.grasped} placed={result.placed} "
        f"failure_reason={episode_result.failure_reason} "
        f"completed_phases={list(result.completed_phases)} "
        f"final_block_pos={result.final_block_pos.round(4).tolist()} "
        f"puzzle_terminal={puzzle_state.is_terminal}"
    )
    return episode_result


def main() -> None:
    args = parse_args()
    cfg = load_configs(args)
    episode_spec = build_swap_episode_spec(
        cfg,
        seed=args.seed,
        common_config=args.common_config,
        env_config=args.env_config,
        robot_config=args.robot_config,
        task_config=args.task_config,
        variant_id=args.variant_id,
    )
    if args.verbose:
        print(
            "swap_physical_grasp_demo runtime "
            f"python={sys.executable} "
            f"genesis={getattr(gs, '__version__', '<unknown>')} "
            f"genesis_path={Path(gs.__file__).resolve()}"
        )
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if args.viewer and not has_display:
        raise SystemExit(
            "No graphical DISPLAY/WAYLAND_DISPLAY detected. Re-run without --viewer, or use GUI/X forwarding."
        )

    physical_cfg = cfg.task.physical
    noslip_iterations = _config_value(
        args.noslip_iterations,
        physical_cfg.noslip_iterations,
        int,
    )
    if noslip_iterations < 0:
        raise SystemExit("noslip-iterations must be non-negative.")

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(
        backend=backends[cfg.env.genesis.backend],
        precision=cfg.env.genesis.precision,
        logging_level=cfg.env.genesis.logging_level,
    )
    swap_scene = SwapSceneBuilder(
        cfg.env,
        cfg.task,
        cfg.robot_control,
        rigid_options=gs.options.RigidOptions(noslip_iterations=noslip_iterations),
    ).build(show_viewer=args.viewer)
    try:
        move, episode_plan = plan_swap_move(
            swap_scene.layout,
            block_name=args.block,
            source_slot=args.source_slot,
            target_slot=args.target_slot,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    controller = initialize_franka_controller(
        scene=swap_scene.scene,
        manifest=swap_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=int(physical_cfg.settle_steps),
    )

    if args.verbose:
        force_lower = list(cfg.robot_control.controller.force_lower)[-2:]
        force_upper = list(cfg.robot_control.controller.force_upper)[-2:]
        gripper_kp = list(cfg.robot_control.controller.kp)[-2:]
        print(
            "swap_physical_grasp_demo physics "
            f"noslip_iterations={noslip_iterations} "
            f"gripper_force_range={force_lower}..{force_upper} "
            f"gripper_kp={gripper_kp}"
        )

    dataset_writer_cm = dataset_writer_or_null(
        args.record_dataset,
        scene=swap_scene.scene,
        cameras=swap_scene.cameras,
        controller=controller,
        spec=episode_spec,
        plan=episode_plan,
        task_goal=_swap_task_goal(move),
        every_n_steps=args.dataset_every_n_steps,
    )
    with dataset_writer_cm as dataset_writer:
        with recording_session_from_config(
            swap_scene.scene,
            swap_scene.cameras,
            cfg.recording,
            hud=_swap_hud(swap_scene),
        ):
            episode_result = run_demo(
                args,
                cfg,
                swap_scene,
                controller,
                episode_spec=episode_spec,
                episode_plan=episode_plan,
                move=move,
            )
        if dataset_writer is not None:
            dataset_writer.finalize(episode_result)
            print(f"saved dataset -> {args.record_dataset}")

    print_recording_saved(cfg.recording)
    while args.keep_open:
        swap_scene.scene.step()


if __name__ == "__main__":
    main()
