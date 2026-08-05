from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import add_common_config_arg, load_topogym_configs
from topogym.generation import EpisodeResult, build_maze_wall_removal_episode_spec
from topogym.planning import MazeWallRemovalCommand, plan_maze_wall_removals
from topogym.primitives import (
    PickPlacePrimitive,
    configure_gripper_contact_friction,
    ee_quat_for_yaw,
    entity_pos,
    print_collision_il_contract,
    validate_rigid_friction,
)
from topogym.primitives.pick_place import HAND_TO_PAD_Z
from topogym.tasks import MazeWallRemovalSceneBuilder
from topogym.verification import MazeWallRemovalPuzzleEvaluator
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
DEFAULT_TASK_CONFIG = CONFIG_ROOT / "task_configs" / "maze_wall_removal_topogym_tabletop_v1.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove Maze walls using rigid contact and the real Franka gripper."
    )
    parser.add_argument("--env-config", type=Path, default=DEFAULT_ENV_CONFIG)
    parser.add_argument("--robot-config", type=Path, default=DEFAULT_ROBOT_CONFIG)
    parser.add_argument("--task-config", type=Path, default=DEFAULT_TASK_CONFIG)
    add_common_config_arg(parser, default=DEFAULT_COMMON_CONFIG)
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), default=None)
    parser.add_argument("--viewer", action="store_true")
    viewer_lifetime = parser.add_mutually_exclusive_group()
    viewer_lifetime.add_argument(
        "--keep-open",
        dest="keep_open",
        action="store_true",
        help="Keep stepping after the demo finishes; this is the default with --viewer.",
    )
    viewer_lifetime.add_argument(
        "--close-on-finish",
        dest="keep_open",
        action="store_false",
        help="Close the viewer and exit immediately after the demo finishes.",
    )
    parser.set_defaults(keep_open=None)
    parser.add_argument(
        "--seed",
        type=int,
        default=11,
        help="Stable episode seed used by the maze instance sampler.",
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
        help="Limit removals for smoke testing; default runs the full optimal plan.",
    )
    parser.add_argument("--motion-steps", type=int, default=None)
    parser.add_argument("--gripper-steps", type=int, default=None)
    parser.add_argument("--grasp-qpos", type=float, default=None)
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
    return merge_recording_config(cfg, args)


def _value(cli_value, config_value, cast):
    return cast(config_value if cli_value is None else cli_value)


def _positive_int(value: int, name: str) -> int:
    value = int(value)
    if value <= 0:
        raise SystemExit(f"{name} must be positive; got {value}.")
    return value


def _grasp_qpos(args, cfg) -> float:
    value = _value(args.grasp_qpos, cfg.task.physical.grasp_qpos, float)
    closed = float(cfg.robot_control.gripper.closed_qpos)
    opened = float(cfg.robot_control.gripper.open_qpos)
    if not min(closed, opened) <= value <= max(closed, opened):
        raise SystemExit(
            f"grasp-qpos must be within [{min(closed, opened):.4f}, "
            f"{max(closed, opened):.4f}]; got {value:.4f}."
        )
    return value


def _hud(maze_scene):
    evaluator = MazeWallRemovalPuzzleEvaluator(
        edge_tolerance_xy=float(maze_scene.layout.cfg.edge_slots.width) * 1.6
    )

    def render_lines():
        state = evaluator.classify(maze_scene)
        return [
            "task=maze removal physical",
            f"seed={maze_scene.instance.seed}",
            f"terminal={state.is_terminal}",
            f"current_min={state.current_min_wall_count}",
            f"removed={len(state.removed_edges)}",
            f"invalid={len(state.invalid_walls)}",
        ]

    return render_lines


def _configure_friction(args, cfg, maze_scene, controller) -> tuple[float, float]:
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
            maze_scene.manifest.get(maze_scene.layout.edge_name(edge))
            for edge in maze_scene.wall_edges
        ]
        configure_gripper_contact_friction(
            entities=walls,
            robot=controller.robot,
            finger_links=physical.finger_links,
            object_friction=wall_friction,
            finger_friction=finger_friction,
        )
    return wall_friction, finger_friction


def _remove_wall(
    *,
    cfg,
    maze_scene,
    controller,
    edge,
    discard_index: int,
    motion_steps: int,
    gripper_steps: int,
    grasp_qpos: float | None,
    verbose: bool,
):
    layout = maze_scene.layout
    physical = cfg.task.physical
    block_name = layout.edge_name(edge)
    block = maze_scene.manifest.get(block_name)
    source_pos = entity_pos(block)
    source_wall_yaw = float(layout.edge_pose_for_key(edge, for_wall=True).yaw)
    grasp_yaw = source_wall_yaw + float(physical.grasp_yaw_offset)
    target_pos = layout.discard_pos(discard_index)

    primitive = PickPlacePrimitive(
        approach_z=layout.world_z(layout.cfg.oracle.remove_z),
        grasp_z=float(source_pos[2]) + HAND_TO_PAD_Z,
        lift_z=layout.world_z(layout.cfg.oracle.carry_z),
        place_z=layout.world_z(layout.cfg.oracle.place_z),
        steps_per_phase=motion_steps,
        gripper_steps=gripper_steps,
        grasp_qpos=grasp_qpos,
        close_hold_steps=int(physical.close_hold_steps),
        release_hold_steps=int(physical.release_hold_steps),
        lift_check_delta=float(physical.lift_check_delta),
        min_lift_delta=float(physical.min_lift_delta),
        max_grasp_xy_error=float(physical.max_grasp_xy_error),
        motion_settle_steps=int(physical.motion_settle_steps),
        lift_hold_steps=int(physical.lift_hold_steps),
        max_lift_drift=float(physical.max_lift_drift),
        place_tolerance_xy=float(physical.place_tolerance_xy),
        place_tolerance_z=float(physical.place_tolerance_z),
        verbose=verbose,
    )
    result = primitive.run(
        controller,
        block=block,
        source_xy=source_pos[:2],
        target_xy=target_pos[:2],
        ee_quat=ee_quat_for_yaw(controller.default_ee_quat, grasp_yaw),
    )
    return block_name, target_pos, result


def run_demo(
    args,
    cfg,
    maze_scene,
    controller,
    *,
    episode_spec,
    episode_plan,
    wall_commands: tuple[MazeWallRemovalCommand, ...],
) -> EpisodeResult:
    layout = maze_scene.layout
    physical = cfg.task.physical
    active_edges = set(maze_scene.instance.active_blocked_edges)
    print_collision_il_contract(
        "maze_wall_removal_physical_demo",
        manipulated=tuple(
            command.block_name
            for command in wall_commands
            if command.edge_key in active_edges
        ),
        success_checks=(
            "lift_delta",
            "lift_drift",
            "grasp_xy_error",
            "discard_place_xy_error",
            "discard_place_z_error",
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
    grasp_qpos = _grasp_qpos(args, cfg)
    wall_friction, finger_friction = _configure_friction(
        args,
        cfg,
        maze_scene,
        controller,
    )
    evaluator = MazeWallRemovalPuzzleEvaluator(
        edge_tolerance_xy=float(maze_scene.layout.cfg.edge_slots.width) * 1.6
    )
    cell_size = np.asarray(
        OmegaConf.to_container(layout.cfg.grid.cell_size, resolve=True),
        dtype=float,
    )
    wall_size = np.asarray(
        OmegaConf.to_container(layout.cfg.wall_block.size, resolve=True),
        dtype=float,
    )
    maze_center = 0.5 * (
        layout.cell_center(0, 0)
        + layout.cell_center(layout.rows - 1, layout.cols - 1)
    )
    discard_center = layout.position_to_world(layout.cfg.discard.pos)
    discard_size = np.asarray(
        OmegaConf.to_container(layout.cfg.discard.size, resolve=True),
        dtype=float,
    )
    discard_visible = bool(getattr(layout.cfg.discard, "visible", False))

    print(
        "maze_wall_removal_physical_demo setup "
        f"requested_seed={args.seed} instance_seed={maze_scene.instance.seed} "
        f"episode_id={episode_spec.stable_id()} plan_id={episode_plan.plan_id} "
        f"planned_removals={len(wall_commands)} "
        f"active_walls={len(active_edges)} "
        f"optimal={maze_scene.instance.optimal_wall_count} "
        f"maze_center_xy={np.asarray(maze_center[:2]).round(4).tolist()} "
        f"cell_size={cell_size.round(4).tolist()} "
        f"cell_gap={float(layout.cfg.grid.cell_gap):.4f} "
        f"wall_size={wall_size.round(4).tolist()} "
        f"discard_xy={np.asarray(discard_center[:2]).round(4).tolist()} "
        f"discard_size={discard_size.round(4).tolist()} "
        f"discard_visible={discard_visible} "
        f"grasp_mode=long_axis_end_grasp "
        f"grasp_qpos={grasp_qpos:.4f} motion_steps={motion_steps} "
        f"phases_per_wall={len(PickPlacePrimitive.NOMINAL_PHASES)} "
        f"wall_friction={wall_friction:.2f} finger_friction={finger_friction:.2f}",
        flush=True,
    )
    all_moves_succeeded = True
    attempted_moves = 0
    stop_reason = "plan_exhausted"
    for command in wall_commands:
        block_name, target_pos, result = _remove_wall(
            cfg=cfg,
            maze_scene=maze_scene,
            controller=controller,
            edge=command.edge_key,
            discard_index=command.discard_index,
            motion_steps=motion_steps,
            gripper_steps=gripper_steps,
            grasp_qpos=grasp_qpos,
            verbose=args.verbose,
        )
        attempted_moves += 1
        state = evaluator.classify(maze_scene)
        print(
            "maze_wall_removal_physical_demo move "
            f"index={command.move_index}/{len(wall_commands)} wall={block_name} "
            f"edge={command.edge_label} "
            f"discard_xy={np.asarray(target_pos[:2]).round(4).tolist()} "
            f"success={result.success} grasped={result.grasped} placed={result.placed} "
            f"current_min={state.current_min_wall_count} "
            f"failure_reason={result.failure_reason}",
            flush=True,
        )
        if not result.success:
            all_moves_succeeded = False
            stop_reason = f"move_failed:{block_name}:{result.failure_reason}"
            break
        if state.is_terminal:
            stop_reason = f"terminal_after_move:{command.move_index}"
            break

    final_state = evaluator.classify(maze_scene)
    controller.reset_home(settle_steps=controller.cfg.control_loop.steps_per_action)
    success = bool(all_moves_succeeded and final_state.is_terminal)
    metrics = {
        "physical_success": bool(all_moves_succeeded),
        "terminal": bool(final_state.is_terminal),
        "attempted_moves": int(attempted_moves),
        "planned_removals": int(len(wall_commands)),
        "removed": int(len(final_state.removed_edges)),
        "optimal": int(final_state.optimal_wall_count),
        "current_min": int(final_state.current_min_wall_count),
        "invalid_walls": int(len(final_state.invalid_walls)),
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
        "maze_wall_removal_physical_demo result "
        f"episode_id={episode_spec.stable_id()} success={episode_result.success} "
        f"physical_success={all_moves_succeeded} "
        f"stable_ready={episode_result.stable_ready} export_ready={episode_result.export_ready} "
        f"terminal={final_state.is_terminal} "
        f"attempted_moves={attempted_moves}/{len(wall_commands)} "
        f"stop_reason={stop_reason} "
        f"removed={len(final_state.removed_edges)} "
        f"optimal={final_state.optimal_wall_count} "
        f"current_min={final_state.current_min_wall_count} "
        f"invalid_walls={list(final_state.invalid_walls)}",
        flush=True,
    )
    return episode_result


def main() -> None:
    args = parse_args()
    cfg = load_configs(args)
    episode_spec = build_maze_wall_removal_episode_spec(
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
            "maze_wall_removal_physical_demo runtime "
            f"python={sys.executable} "
            f"genesis={getattr(gs, '__version__', '<unknown>')} "
            f"genesis_path={Path(gs.__file__).resolve()}",
            flush=True,
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
    print(
        "maze_wall_removal_physical_demo building_scene "
        f"backend={cfg.env.genesis.backend} viewer={args.viewer}",
        flush=True,
    )
    maze_scene = MazeWallRemovalSceneBuilder(
        cfg.env,
        cfg.task,
        cfg.robot_control,
        seed=args.seed,
        rigid_options=gs.options.RigidOptions(noslip_iterations=noslip_iterations),
    ).build(show_viewer=args.viewer)
    try:
        wall_commands, episode_plan = plan_maze_wall_removals(
            maze_scene.layout,
            maze_scene.instance,
            max_walls=args.max_walls,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print("maze_wall_removal_physical_demo scene_ready", flush=True)
    controller = initialize_franka_controller(
        scene=maze_scene.scene,
        manifest=maze_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=int(cfg.task.physical.settle_steps),
    )
    print(
        "maze_wall_removal_physical_demo robot_home_ready "
        f"hand={controller.hand_pos().round(4).tolist()}",
        flush=True,
    )

    with recording_session_from_config(
        maze_scene.scene,
        maze_scene.cameras,
        cfg.recording,
        hud=_hud(maze_scene),
    ):
        run_demo(
            args,
            cfg,
            maze_scene,
            controller,
            episode_spec=episode_spec,
            episode_plan=episode_plan,
            wall_commands=wall_commands,
        )

    print_recording_saved(cfg.recording)
    keep_open = bool(args.viewer) if args.keep_open is None else bool(args.keep_open)
    if keep_open:
        print(
            "maze_wall_removal_physical_demo viewer_hold "
            "simulation finished; keeping the viewer open until Ctrl+C",
            flush=True,
        )
    while keep_open:
        maze_scene.scene.step()


if __name__ == "__main__":
    main()
