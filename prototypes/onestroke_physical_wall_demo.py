from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import add_common_config_arg, load_topogym_configs
from topogym.generation import EpisodeResult, build_onestroke_episode_spec
from topogym.planning import (
    OneStrokeWallCommand,
    plan_onestroke_separator,
)
from topogym.primitives import (
    PickPlacePrimitive,
    configure_gripper_contact_friction,
    ee_quat_for_yaw,
    entity_pos,
    print_collision_il_contract,
    validate_rigid_friction,
)
from topogym.primitives.pick_place import HAND_TO_PAD_Z
from topogym.tasks import OneStrokeSceneBuilder
from topogym.verification import OneStrokePuzzleEvaluator
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
DEFAULT_TASK_CONFIG = CONFIG_ROOT / "task_configs" / "onestroke_topogym_tabletop_v1.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Solve OneStroke using rigid wall contact and the real Franka gripper."
    )
    parser.add_argument("--env-config", type=Path, default=DEFAULT_ENV_CONFIG)
    parser.add_argument("--robot-config", type=Path, default=DEFAULT_ROBOT_CONFIG)
    parser.add_argument("--task-config", type=Path, default=DEFAULT_TASK_CONFIG)
    add_common_config_arg(parser, default=DEFAULT_COMMON_CONFIG)
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), default=None)
    parser.add_argument("--viewer", action="store_true")
    parser.add_argument("--keep-open", action="store_true")
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help=(
            "Stable episode seed. Current OneStroke layout is deterministic; "
            "this identifies the variant."
        ),
    )
    parser.add_argument(
        "--variant-id",
        default="default",
        help="Stable variant label for manifests and result lines.",
    )
    parser.add_argument(
        "--max-walls",
        type=int,
        default=None,
        help="Limit physical placements for smoke testing; default runs the full separator plan.",
    )
    parser.add_argument("--motion-steps", type=int, default=None)
    parser.add_argument("--gripper-steps", type=int, default=None)
    parser.add_argument("--grasp-qpos", type=float, default=None)
    terminal_lifetime = parser.add_mutually_exclusive_group()
    terminal_lifetime.add_argument(
        "--stop-on-terminal",
        dest="stop_on_terminal",
        action="store_true",
        help="Stop as soon as the puzzle evaluator reaches terminal. This is the stable-generation default.",
    )
    terminal_lifetime.add_argument(
        "--no-stop-on-terminal",
        dest="stop_on_terminal",
        action="store_false",
        help="Keep executing the complete planned separator wall sequence after terminal; useful for debugging only.",
    )
    failure_lifetime = parser.add_mutually_exclusive_group()
    failure_lifetime.add_argument(
        "--continue-on-failure",
        dest="continue_on_failure",
        action="store_true",
        help=(
            "Keep attempting later planned walls after a failed move. Useful for "
            "debug videos, but not the stable-generation default."
        ),
    )
    failure_lifetime.add_argument(
        "--stop-on-failure",
        dest="continue_on_failure",
        action="store_false",
        help="Stop immediately when a physical placement fails.",
    )
    parser.set_defaults(stop_on_terminal=True, continue_on_failure=False)
    edge_support = parser.add_mutually_exclusive_group()
    edge_support.add_argument(
        "--edge-support",
        dest="edge_support",
        action="store_true",
        help=(
            "Create invisible collision supports inside OneStroke cell gaps. "
            "Useful only as a diagnostic stabilizer; the default config uses real grooves."
        ),
    )
    edge_support.add_argument(
        "--no-edge-support",
        dest="edge_support",
        action="store_false",
        help=(
            "Do not create invisible collision supports inside OneStroke cell gaps. "
            "This is the default for the current physical demo."
        ),
    )
    parser.set_defaults(edge_support=None)
    parser.add_argument(
        "--target-xy-bias",
        type=float,
        nargs=2,
        default=None,
        metavar=("X", "Y"),
        help=(
            "World/task-frame XY offset applied only to the physical release target. "
            "The logical edge target remains the midpoint of the adjacent cell centers."
        ),
    )
    parser.add_argument(
        "--target-yaw-bias",
        type=float,
        default=None,
        help=(
            "Release-yaw pre-compensation in radians. The final success check still "
            "uses the true edge yaw, so this should stay small."
        ),
    )
    parser.add_argument("--finger-friction", type=float, default=None)
    parser.add_argument("--wall-friction", type=float, default=None)
    parser.add_argument("--noslip-iterations", type=int, default=None)
    parser.add_argument("--no-friction-override", action="store_true")
    add_recording_args(parser, default_fps=60, default_camera="oblique")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def load_configs(args: argparse.Namespace):
    cfg = load_topogym_configs(
        common_config=args.common_config,
        env_config=args.env_config,
        robot_config=args.robot_config,
        task_config=args.task_config,
    )
    if args.backend is not None:
        cfg = OmegaConf.merge(cfg, {"env": {"genesis": {"backend": args.backend}}})
    if args.edge_support is not None:
        cfg = OmegaConf.merge(
            cfg,
            {"task": {"edge_slots": {"collision": bool(args.edge_support)}}},
        )
    return merge_recording_config(cfg, args)


def _value(cli_value, config_value, cast):
    return cast(config_value if cli_value is None else cli_value)


def _positive_int(value: int, name: str) -> int:
    value = int(value)
    if value <= 0:
        raise SystemExit(f"{name} must be positive; got {value}.")
    return value


def _slot_geometry_clearance(layout, physical) -> dict[str, float]:
    wall_size = np.asarray(
        OmegaConf.to_container(layout.cfg.wall_block.size, resolve=True),
        dtype=float,
    )
    cell_size = np.asarray(
        OmegaConf.to_container(layout.cfg.grid.cell_size, resolve=True),
        dtype=float,
    )
    cell_gap = float(layout.cfg.grid.cell_gap)
    slot_width = float(layout.cfg.edge_slots.width)
    wall_thickness = float(min(wall_size[0], wall_size[1]))
    wall_length = float(max(wall_size[0], wall_size[1]))
    cell_edge_length = float(max(cell_size[0], cell_size[1]))
    gap_clearance_each_side = 0.5 * (cell_gap - wall_thickness)
    length_clearance_each_side = 0.5 * (cell_edge_length - wall_length)
    slot_clearance_each_side = 0.5 * (cell_gap - slot_width)

    min_side_clearance = 0.003
    if gap_clearance_each_side < min_side_clearance:
        raise SystemExit(
            "OneStroke physical insertion geometry is too tight: "
            f"grid.cell_gap={cell_gap:.4f}, wall_thickness={wall_thickness:.4f}, "
            f"side_clearance={gap_clearance_each_side:.4f}. "
            f"Use at least {min_side_clearance:.3f} m side clearance."
        )
    if slot_clearance_each_side < min_side_clearance:
        raise SystemExit(
            "OneStroke edge support is too wide for the cell gap: "
            f"grid.cell_gap={cell_gap:.4f}, edge_slots.width={slot_width:.4f}, "
            f"side_clearance={slot_clearance_each_side:.4f}. "
            f"Use at least {min_side_clearance:.3f} m side clearance."
        )
    if length_clearance_each_side < min_side_clearance:
        raise SystemExit(
            "OneStroke wall block is too long for stable physical insertion: "
            f"cell_edge_length={cell_edge_length:.4f}, wall_length={wall_length:.4f}, "
            f"end_clearance={length_clearance_each_side:.4f}. "
            f"Use at least {min_side_clearance:.3f} m end clearance."
        )

    place_tolerance_xy = float(physical.place_tolerance_xy)
    if place_tolerance_xy > gap_clearance_each_side + 1e-9:
        raise SystemExit(
            "OneStroke place_tolerance_xy exceeds the real wall side clearance: "
            f"place_tolerance_xy={place_tolerance_xy:.4f}, "
            f"gap_clearance_each_side={gap_clearance_each_side:.4f}. "
            "Tighten the tolerance or increase grid.cell_gap."
        )

    floor_top = layout.wall_placement_floor_z()
    target_object_z = layout.wall_target_center_z()
    release_object_z = (
        target_object_z
        + float(physical.release_clearance)
        - float(getattr(physical, "placement_preload", 0.0))
    )
    return {
        "cell_gap": cell_gap,
        "cell_edge_length": cell_edge_length,
        "slot_width": slot_width,
        "wall_thickness": wall_thickness,
        "wall_length": wall_length,
        "gap_clearance_each_side": gap_clearance_each_side,
        "length_clearance_each_side": length_clearance_each_side,
        "slot_clearance_each_side": slot_clearance_each_side,
        "place_tolerance_xy": place_tolerance_xy,
        "edge_support_enabled": float(layout.edge_support_enabled()),
        "placement_floor_top": float(floor_top),
        "target_object_z": float(target_object_z),
        "release_object_z": float(release_object_z),
    }


def _target_xy_bias(args, physical) -> np.ndarray:
    if args.target_xy_bias is not None:
        return np.asarray(args.target_xy_bias, dtype=float)
    if hasattr(physical, "target_xy_bias"):
        return np.asarray(
            OmegaConf.to_container(physical.target_xy_bias, resolve=True),
            dtype=float,
        )
    return np.zeros(2, dtype=float)


def _target_yaw_bias(args, physical) -> float:
    if args.target_yaw_bias is not None:
        return float(args.target_yaw_bias)
    return float(getattr(physical, "target_yaw_bias", 0.0))


def _fmt_xy(value) -> str:
    xy = np.asarray(value, dtype=float)
    return f"[{xy[0]:+.4f},{xy[1]:+.4f}]"


def _hud(one_scene):
    physical = one_scene.layout.cfg.physical
    evaluator = OneStrokePuzzleEvaluator(
        edge_tolerance_xy=float(physical.place_tolerance_xy),
        wall_tolerance_z=float(physical.place_tolerance_z),
        wall_tolerance_tilt=float(getattr(physical, "place_tolerance_tilt", np.pi)),
    )

    def render_lines():
        state = evaluator.classify(one_scene)
        return [
            "task=onestroke physical",
            f"terminal={state.is_terminal}",
            f"walls={len(state.placed_edges)}",
            f"invalid={len(state.invalid_walls)}",
            f"unseparated={state.unseparated_component_count()}",
        ]

    return render_lines


def _configure_friction(args, cfg, one_scene, controller) -> tuple[float, float]:
    physical = cfg.task.physical
    wall_friction = validate_rigid_friction(
        _value(args.wall_friction, physical.wall_friction, float),
        "wall_friction",
    )
    finger_friction = validate_rigid_friction(
        _value(args.finger_friction, physical.finger_friction, float),
        "finger_friction",
    )
    if not args.no_friction_override:
        walls = [
            one_scene.manifest.get(one_scene.layout.supply_block_name(index))
            for index in range(one_scene.layout.wall_count)
        ]
        configure_gripper_contact_friction(
            entities=walls,
            robot=controller.robot,
            finger_links=physical.finger_links,
            object_friction=wall_friction,
            finger_friction=finger_friction,
        )
    return wall_friction, finger_friction


def _place_wall(
    *,
    cfg,
    one_scene,
    controller,
    command: OneStrokeWallCommand,
    motion_steps: int,
    gripper_steps: int,
    grasp_qpos: float | None,
    target_xy_bias: np.ndarray,
    target_yaw_bias: float,
    verbose: bool,
):
    layout = one_scene.layout
    physical = cfg.task.physical
    block_name = command.block_name
    block = one_scene.manifest.get(block_name)
    source_pos = entity_pos(block)
    edge_pose = layout.edge_pose_for_key(command.edge_key)
    geometric_target_xy = np.asarray(edge_pose.pos[:2], dtype=float)
    release_target_xy = geometric_target_xy + np.asarray(target_xy_bias, dtype=float)

    source_wall_yaw = 0.0
    target_wall_yaw = float(edge_pose.yaw)
    release_wall_yaw = target_wall_yaw + float(target_yaw_bias)
    grasp_yaw_offset = float(physical.grasp_yaw_offset)
    source_gripper_yaw = source_wall_yaw + grasp_yaw_offset
    target_gripper_yaw = release_wall_yaw + grasp_yaw_offset

    target_object_z = layout.wall_target_center_z()
    release_object_z = (
        target_object_z
        + float(physical.release_clearance)
        - float(getattr(physical, "placement_preload", 0.0))
    )
    primitive = PickPlacePrimitive(
        approach_z=layout.world_z(layout.cfg.oracle.supply_pick_z),
        grasp_z=float(source_pos[2]) + HAND_TO_PAD_Z,
        lift_z=layout.world_z(layout.cfg.oracle.carry_z),
        place_z=release_object_z + HAND_TO_PAD_Z,
        steps_per_phase=motion_steps,
        gripper_steps=gripper_steps,
        grasp_qpos=grasp_qpos,
        close_hold_steps=int(physical.close_hold_steps),
        release_hold_steps=int(physical.release_hold_steps),
        release_lift_clearance=float(getattr(physical, "release_lift_clearance", 0.0)),
        release_lift_steps=int(getattr(physical, "release_lift_steps", 0)),
        lift_check_delta=float(physical.lift_check_delta),
        min_lift_delta=float(physical.min_lift_delta),
        max_grasp_xy_error=float(physical.max_grasp_xy_error),
        motion_settle_steps=int(getattr(physical, "motion_settle_steps", 0)),
        place_hold_steps=int(getattr(physical, "place_hold_steps", 0)),
        place_tolerance_xy=float(physical.place_tolerance_xy),
        place_tolerance_z=float(physical.place_tolerance_z),
        verbose=verbose,
    )
    result = primitive.run(
        controller,
        block=block,
        source_xy=source_pos[:2],
        target_xy=release_target_xy,
        ee_quat=ee_quat_for_yaw(controller.default_ee_quat, source_gripper_yaw),
        target_ee_quat=ee_quat_for_yaw(
            controller.default_ee_quat,
            target_gripper_yaw,
        ),
        target_object_yaw=target_wall_yaw,
        target_object_z=target_object_z,
        place_tolerance_yaw=float(physical.place_tolerance_yaw),
        place_tolerance_tilt=float(getattr(physical, "place_tolerance_tilt", np.pi)),
        place_yaw_period=float(np.pi),
        placement_target_xy=geometric_target_xy,
    )
    return block_name, edge_pose, release_target_xy, result


def run_demo(
    args,
    cfg,
    one_scene,
    controller,
    *,
    episode_spec,
    episode_plan,
    wall_commands: tuple[OneStrokeWallCommand, ...],
) -> EpisodeResult:
    layout = one_scene.layout
    physical = cfg.task.physical
    print_collision_il_contract(
        "onestroke_physical_wall_demo",
        manipulated=tuple(command.block_name for command in wall_commands),
        success_checks=(
            "lift_delta",
            "grasp_xy_error",
            "place_xy_error",
            "place_z_error",
            "place_yaw_error",
            "place_tilt_error",
            "task_terminal",
        ),
    )

    motion_steps = _positive_int(
        _value(args.motion_steps, physical.motion_steps, int),
        "motion-steps",
    )
    gripper_steps = _positive_int(
        _value(args.gripper_steps, physical.gripper_steps, int),
        "gripper-steps",
    )
    wall_friction, finger_friction = _configure_friction(
        args,
        cfg,
        one_scene,
        controller,
    )
    evaluator = OneStrokePuzzleEvaluator(
        edge_tolerance_xy=float(physical.place_tolerance_xy),
        wall_tolerance_z=float(physical.place_tolerance_z),
        wall_tolerance_tilt=float(getattr(physical, "place_tolerance_tilt", np.pi)),
    )
    slot_geom = _slot_geometry_clearance(layout, physical)
    target_xy_bias = _target_xy_bias(args, physical)
    target_yaw_bias = _target_yaw_bias(args, physical)
    if float(np.linalg.norm(target_xy_bias)) > slot_geom["gap_clearance_each_side"] + 1e-9:
        raise SystemExit(
            "OneStroke target_xy_bias is larger than the wall side clearance: "
            f"target_xy_bias={_fmt_xy(target_xy_bias)}, "
            f"gap_clearance_each_side={slot_geom['gap_clearance_each_side']:.4f}."
        )

    print(
        "onestroke_physical_wall_demo setup "
        f"episode_id={episode_spec.stable_id()} plan_id={episode_plan.plan_id} "
        f"planned_walls={len(wall_commands)} grasp_mode=long_axis_end_grasp "
        f"planned_edges=[{','.join(command.edge_label for command in wall_commands)}] "
        f"stop_on_terminal={args.stop_on_terminal} "
        f"continue_on_failure={args.continue_on_failure} "
        f"phases_per_wall={len(PickPlacePrimitive.NOMINAL_PHASES)} "
        f"wall_friction={wall_friction:.2f} finger_friction={finger_friction:.2f} "
        f"cell_gap={slot_geom['cell_gap']:.4f} "
        f"cell_edge_length={slot_geom['cell_edge_length']:.4f} "
        f"wall_length={slot_geom['wall_length']:.4f} "
        f"wall_thickness={slot_geom['wall_thickness']:.4f} "
        f"edge_slot_width={slot_geom['slot_width']:.4f} "
        f"gap_clearance_each_side={slot_geom['gap_clearance_each_side']:.4f} "
        f"length_clearance_each_side={slot_geom['length_clearance_each_side']:.4f} "
        f"slot_clearance_each_side={slot_geom['slot_clearance_each_side']:.4f} "
        f"place_tolerance_xy={slot_geom['place_tolerance_xy']:.4f} "
        f"edge_support_enabled={bool(slot_geom['edge_support_enabled'])} "
        f"placement_floor_top={slot_geom['placement_floor_top']:.4f} "
        f"target_object_z={slot_geom['target_object_z']:.4f} "
        f"target_xy_bias={_fmt_xy(target_xy_bias)} "
        f"target_yaw_bias={target_yaw_bias:+.4f} "
        f"release_clearance={float(physical.release_clearance):.4f} "
        f"release_lift_clearance={float(getattr(physical, 'release_lift_clearance', 0.0)):.4f} "
        f"placement_preload={float(getattr(physical, 'placement_preload', 0.0)):.4f}"
    )
    all_moves_succeeded = True
    attempted_moves = 0
    stop_reason = "plan_exhausted"
    for wall_index, command in enumerate(wall_commands):
        block_name, edge_pose, release_target_xy, result = _place_wall(
            cfg=cfg,
            one_scene=one_scene,
            controller=controller,
            command=command,
            motion_steps=motion_steps,
            gripper_steps=gripper_steps,
            grasp_qpos=args.grasp_qpos,
            target_xy_bias=target_xy_bias,
            target_yaw_bias=target_yaw_bias,
            verbose=args.verbose,
        )
        attempted_moves += 1
        final_xy = np.asarray(result.final_block_pos[:2], dtype=float)
        edge_mid_xy = np.asarray(edge_pose.pos[:2], dtype=float)
        geometry_xy_error = float(np.linalg.norm(final_xy - edge_mid_xy))
        release_xy_error = float(np.linalg.norm(final_xy - release_target_xy))
        state_after_move = evaluator.classify(one_scene)
        print(
            "onestroke_physical_wall_demo move "
            f"index={wall_index + 1}/{len(wall_commands)} wall={block_name} "
            f"target={command.edge_label} orientation={edge_pose.orientation} "
            f"edge_mid_xy={_fmt_xy(edge_mid_xy)} "
            f"release_xy={_fmt_xy(release_target_xy)} "
            f"final_xy={_fmt_xy(final_xy)} "
            f"geometry_xy_error={geometry_xy_error:.4f} "
            f"release_xy_error={release_xy_error:.4f} "
            f"success={result.success} grasped={result.grasped} placed={result.placed} "
            f"yaw_error={result.place_yaw_error} "
            f"tilt_error={result.place_tilt_error} "
            f"terminal_after_move={state_after_move.is_terminal} "
            f"placed_edges_after_move={len(state_after_move.placed_edges)} "
            f"unseparated_after_move={state_after_move.unseparated_component_count()} "
            f"failure_reason={result.failure_reason}"
        )
        if not result.success:
            all_moves_succeeded = False
            stop_reason = f"move_failed:{block_name}:{result.failure_reason}"
            if not args.continue_on_failure:
                break
        if args.stop_on_terminal and state_after_move.is_terminal:
            stop_reason = f"terminal_after_move:{wall_index + 1}"
            break

    final_state = evaluator.classify(one_scene)
    controller.reset_home(settle_steps=controller.cfg.control_loop.steps_per_action)
    success = bool(all_moves_succeeded and final_state.is_terminal)
    metrics = {
        "physical_success": bool(all_moves_succeeded),
        "terminal": bool(final_state.is_terminal),
        "attempted_moves": int(attempted_moves),
        "planned_walls": int(len(wall_commands)),
        "placed_edges": int(len(final_state.placed_edges)),
        "invalid_walls": int(len(final_state.invalid_walls)),
        "unseparated": int(final_state.unseparated_component_count()),
    }
    episode_result = (
        EpisodeResult.ok(
            episode_spec.key,
            metrics=metrics,
            export_ready=True,
        )
        if success
        else EpisodeResult.failed(
            episode_spec.key,
            stop_reason,
            metrics=metrics,
            stable_ready=False,
        )
    )
    print(
        "onestroke_physical_wall_demo result "
        f"episode_id={episode_spec.stable_id()} success={episode_result.success} "
        f"physical_success={all_moves_succeeded} "
        f"stable_ready={episode_result.stable_ready} export_ready={episode_result.export_ready} "
        f"terminal={final_state.is_terminal} "
        f"attempted_moves={attempted_moves}/{len(wall_commands)} "
        f"stop_reason={stop_reason} "
        f"placed_edges={len(final_state.placed_edges)} "
        f"invalid_walls={list(final_state.invalid_walls)} "
        f"unseparated={final_state.unseparated_component_count()}"
    )
    return episode_result


def main() -> None:
    args = parse_args()
    cfg = load_configs(args)
    episode_spec = build_onestroke_episode_spec(
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
            "onestroke_physical_wall_demo runtime "
            f"python={sys.executable} "
            f"genesis={getattr(gs, '__version__', '<unknown>')} "
            f"genesis_path={Path(gs.__file__).resolve()}"
        )
    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    if args.viewer and not has_display:
        raise SystemExit(
            "No graphical DISPLAY/WAYLAND_DISPLAY detected. Re-run without --viewer, or use GUI/X forwarding."
        )

    noslip_iterations = _value(
        args.noslip_iterations,
        cfg.task.physical.noslip_iterations,
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
    one_scene = OneStrokeSceneBuilder(
        cfg.env,
        cfg.task,
        cfg.robot_control,
        rigid_options=gs.options.RigidOptions(noslip_iterations=noslip_iterations),
    ).build(show_viewer=args.viewer)
    try:
        wall_commands, episode_plan = plan_onestroke_separator(
            one_scene.layout,
            max_walls=args.max_walls,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    controller = initialize_franka_controller(
        scene=one_scene.scene,
        manifest=one_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=int(cfg.task.physical.settle_steps),
    )

    with recording_session_from_config(
        one_scene.scene,
        one_scene.cameras,
        cfg.recording,
        hud=_hud(one_scene),
    ):
        run_demo(
            args,
            cfg,
            one_scene,
            controller,
            episode_spec=episode_spec,
            episode_plan=episode_plan,
            wall_commands=wall_commands,
        )

    print_recording_saved(cfg.recording)
    while args.keep_open:
        one_scene.scene.step()


if __name__ == "__main__":
    main()
