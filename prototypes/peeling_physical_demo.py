import argparse
import os
import time
from pathlib import Path

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import add_common_config_arg, load_topogym_configs
from topogym.primitives import AttachmentManager, parent_pos_for_child, rotate_z, yaw_quat
from topogym.tasks import (
    PeelingPuzzleEvaluator,
    PeelingSceneBuilder,
    apply_peel_zone_markers,
)
from topogym.utils import (
    add_recording_args,
    initialize_franka_controller,
    merge_recording_config,
    print_recording_saved,
    recording_session_from_config,
)


CONFIG_ROOT = Path(__file__).resolve().parents[1] / "configs"
DEFAULT_ENV_CONFIG = CONFIG_ROOT / "env_configs" / "world_tabletop_v1.yaml"
DEFAULT_COMMON_CONFIG = CONFIG_ROOT / "common_configs" / "manipulation_space_tabletop_v1.yaml"
DEFAULT_ROBOT_CONFIG = CONFIG_ROOT / "robot_control_configs" / "franka_panda_position_ik.yaml"
DEFAULT_TASK_CONFIG = CONFIG_ROOT / "task_configs" / "peeling_topogym_tabletop_v1.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-film topological peeling demo (tabletop V1, task frame).")
    parser.add_argument("--env-config", type=Path, default=DEFAULT_ENV_CONFIG)
    parser.add_argument("--robot-config", type=Path, default=DEFAULT_ROBOT_CONFIG)
    parser.add_argument("--task-config", type=Path, default=DEFAULT_TASK_CONFIG)
    add_common_config_arg(parser, default=DEFAULT_COMMON_CONFIG)
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), default=None)
    parser.add_argument("--viewer", action="store_true", help="Open the Genesis viewer.")
    parser.add_argument("--keep-open", action="store_true", help="Keep the viewer alive after the demo.")
    parser.add_argument("--keep-open-no-step", action="store_true", help="Keep the Python process alive without stepping.")
    parser.add_argument("--run-oracle", action="store_true", help="Run the scripted Level 1 peeling oracle.")
    parser.add_argument("--hide-peel-zones", action="store_true", help="Hide semantic peel-zone markers.")
    parser.add_argument("--settle-steps", type=int, default=None)
    parser.add_argument("--move-steps", type=int, default=None)
    parser.add_argument("--lift-steps", type=int, default=None)
    parser.add_argument("--place-steps", type=int, default=None)
    parser.add_argument("--gripper-steps", type=int, default=None)
    parser.add_argument("--grasp-qpos", type=float, default=None)
    parser.add_argument("--verbose", action="store_true")
    add_recording_args(parser, default_fps=30)
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
    if args.hide_peel_zones:
        cfg = OmegaConf.merge(cfg, {"task": {"peel_zones": {"marker": {"enabled": False}}}})
    return merge_recording_config(cfg, args)


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _entity_pos(entity) -> np.ndarray:
    return _as_numpy(entity.get_pos()).reshape(-1, 3)[0]


def _lerp(start, end, alpha: float) -> np.ndarray:
    return (1.0 - alpha) * np.asarray(start, dtype=float) + alpha * np.asarray(end, dtype=float)


def _quat_mul(a, b) -> np.ndarray:
    aw, ax, ay, az = np.asarray(a, dtype=float)
    bw, bx, by, bz = np.asarray(b, dtype=float)
    return np.array(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ],
        dtype=float,
    )


def _ee_quat_for_yaw(controller, yaw: float) -> np.ndarray:
    quat = _quat_mul(yaw_quat(yaw), controller.default_ee_quat)
    return quat / np.linalg.norm(quat)


def _move_free(controller, xy, z: float, *, yaw: float, steps: int) -> None:
    steps = max(1, int(steps))
    start = controller.hand_pos()
    target = np.array([float(xy[0]), float(xy[1]), float(z)], dtype=float)
    quat = _ee_quat_for_yaw(controller, yaw)
    for i in range(1, steps + 1):
        controller.move_ee_to(_lerp(start, target, i / steps), quat=quat, steps=1)


def _carry_attached_film(
    controller,
    attachment,
    start_center,
    end_center,
    *,
    yaw: float,
    grasp_offset,
    steps: int,
) -> None:
    steps = max(1, int(steps))
    start_center = np.asarray(start_center, dtype=float)
    end_center = np.asarray(end_center, dtype=float)
    grasp_offset = np.asarray(grasp_offset, dtype=float)
    quat = _ee_quat_for_yaw(controller, yaw)
    for i in range(1, steps + 1):
        center = _lerp(start_center, end_center, i / steps)
        attachment.set_yaw(yaw)
        hand_pos = parent_pos_for_child(center, grasp_offset, yaw)
        controller.move_ee_to(hand_pos, quat=quat, steps=1)


def _set_film_pose(entity, pos, yaw: float) -> None:
    entity.set_pos(tuple(pos), zero_velocity=True)
    entity.set_quat(yaw_quat(yaw), zero_velocity=True, relative=False)


def _settle_film_pose(scene, entity, start, target, *, yaw: float, steps: int) -> None:
    steps = max(1, int(steps))
    start = np.asarray(start, dtype=float)
    target = np.asarray(target, dtype=float)
    for i in range(1, steps + 1):
        _set_film_pose(entity, _lerp(start, target, i / steps), yaw)
        scene.step()


def _peeling_hud(peeling_scene):
    evaluator = PeelingPuzzleEvaluator()

    def render_lines():
        state = evaluator.classify(peeling_scene)
        lines = [
            "task=peeling",
            f"peeled={'->'.join(state.peeled) if state.peeled else 'none'}",
            f"active={list(state.active_films)}",
            f"terminal={state.is_terminal}",
        ]
        if state.is_terminal:
            lines.append("TASK COMPLETE")
        return lines

    return render_lines


def _primitive_value(peeling_scene, name: str, override):
    if override is not None:
        return override
    return getattr(peeling_scene.layout.cfg.primitive, name)


def _primitive_float(primitive, name: str, default: float) -> float:
    return float(getattr(primitive, name, default))


def peel_film(
    peeling_scene,
    controller,
    attachments: AttachmentManager,
    *,
    film_name: str,
    move_steps: int,
    lift_steps: int,
    place_steps: int,
    gripper_steps: int,
    grasp_qpos: float,
    verbose: bool = False,
) -> bool:
    layout = peeling_scene.layout
    peeled = tuple(peeling_scene.peeled)
    if not layout.is_film_active(film_name, peeled=peeled):
        blockers = layout.higher_overlapping_films(film_name, peeled=peeled)
        print(
            "peeling_physical_demo blocked "
            f"film={film_name} blockers={list(blockers)} active={list(layout.active_film_names(peeled=peeled))}"
        )
        return False

    film = peeling_scene.manifest.get(film_name)
    zone = layout.zone_center(film_name)
    yaw = layout.film_yaw(film_name)
    primitive = layout.cfg.primitive

    if verbose:
        print(
            "peeling_physical_demo peel "
            f"film={film_name} label={layout.film_label(film_name)} "
            f"zone={zone.tolist()} target={layout.target_film_pos(film_name).tolist()}"
        )

    hand_surface_offset = _primitive_float(primitive, "hand_surface_offset", 0.108)
    grasp_clearance = _primitive_float(primitive, "grasp_clearance", 0.004)
    grasp_z = max(layout.world_z(float(primitive.grasp_z)), float(zone[2]) + hand_surface_offset + grasp_clearance)

    controller.open_gripper(gripper_steps)
    _move_free(controller, zone[:2], layout.world_z(float(primitive.approach_z)), yaw=yaw, steps=move_steps)
    _move_free(controller, zone[:2], grasp_z, yaw=yaw, steps=max(1, move_steps // 2))
    controller.set_gripper(float(grasp_qpos), steps=gripper_steps)

    film_start = _entity_pos(film)
    hand_at_grasp = controller.hand_pos()
    grasp_offset = rotate_z(film_start - hand_at_grasp, -yaw)
    attachment = attachments.create(
        entity=film,
        parent_pos_fn=controller.hand_pos,
        offset=grasp_offset,
        yaw=yaw,
    )
    attachment.attach()

    lift_center = np.array(film_start, dtype=float)
    lift_center[2] = layout.world_z(float(primitive.lift_z)) + float(grasp_offset[2])
    target_center = layout.target_film_pos(film_name)
    release_clearance = _primitive_float(primitive, "release_clearance", 0.03)
    release_center = np.array(target_center, dtype=float)
    release_center[2] += release_clearance
    hover_center = np.array(target_center, dtype=float)
    hover_center[2] = layout.world_z(float(primitive.carry_z)) + float(grasp_offset[2])

    _carry_attached_film(
        controller,
        attachment,
        film_start,
        lift_center,
        yaw=yaw,
        grasp_offset=grasp_offset,
        steps=lift_steps,
    )
    _carry_attached_film(
        controller,
        attachment,
        lift_center,
        hover_center,
        yaw=yaw,
        grasp_offset=grasp_offset,
        steps=move_steps,
    )
    _carry_attached_film(
        controller,
        attachment,
        hover_center,
        release_center,
        yaw=yaw,
        grasp_offset=grasp_offset,
        steps=place_steps,
    )

    controller.open_gripper(gripper_steps)
    attachment.release()
    _settle_film_pose(
        peeling_scene.scene,
        film,
        _entity_pos(film),
        target_center,
        yaw=yaw,
        steps=int(getattr(primitive, "film_settle_steps", 8)),
    )
    if film_name not in peeling_scene.peeled:
        peeling_scene.peeled.append(film_name)
    apply_peel_zone_markers(peeling_scene)

    retreat_hand = parent_pos_for_child(release_center, grasp_offset, yaw)
    _move_free(
        controller,
        retreat_hand[:2],
        layout.world_z(float(primitive.retreat_z)),
        yaw=yaw,
        steps=max(1, move_steps // 2),
    )
    return True


def run_oracle(
    peeling_scene,
    controller,
    attachments: AttachmentManager,
    *,
    move_steps: int,
    lift_steps: int,
    place_steps: int,
    gripper_steps: int,
    grasp_qpos: float,
    verbose: bool = False,
) -> bool:
    layout = peeling_scene.layout
    sequence = layout.oracle_sequence()
    print(
        "peeling_physical_demo "
        f"sequence={list(sequence)} active_initial={list(layout.active_film_names())}"
    )
    for index, film_name in enumerate(sequence, start=1):
        if verbose:
            state = PeelingPuzzleEvaluator().classify(peeling_scene)
            print(
                "peeling_physical_demo step "
                f"{index}/{len(sequence)} film={film_name} active={list(state.active_films)} "
                f"blocked_by={state.blocked_by}"
            )
        if not peel_film(
            peeling_scene,
            controller,
            attachments,
            film_name=film_name,
            move_steps=move_steps,
            lift_steps=lift_steps,
            place_steps=place_steps,
            gripper_steps=gripper_steps,
            grasp_qpos=grasp_qpos,
            verbose=verbose,
        ):
            break

    controller.reset_home(settle_steps=controller.cfg.control_loop.steps_per_action)
    final_state = PeelingPuzzleEvaluator().classify(peeling_scene)
    print(
        "peeling_physical_demo "
        f"success={final_state.is_terminal} peeled={list(final_state.peeled)} "
        f"remaining={list(final_state.remaining)} active={list(final_state.active_films)}"
    )
    return final_state.is_terminal


def main() -> None:
    args = parse_args()
    cfg = load_configs(args)
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if args.viewer and not has_display:
        raise SystemExit(
            "No graphical DISPLAY/WAYLAND_DISPLAY detected. Re-run without --viewer, or use GUI/X forwarding."
        )

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(
        backend=backends[cfg.env.genesis.backend],
        precision=cfg.env.genesis.precision,
        logging_level=cfg.env.genesis.logging_level,
    )
    peeling_scene = PeelingSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(show_viewer=args.viewer)
    controller = initialize_franka_controller(
        scene=peeling_scene.scene,
        manifest=peeling_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=args.settle_steps,
    )

    move_steps = int(_primitive_value(peeling_scene, "move_steps", args.move_steps))
    lift_steps = int(_primitive_value(peeling_scene, "lift_steps", args.lift_steps))
    place_steps = int(_primitive_value(peeling_scene, "place_steps", args.place_steps))
    gripper_steps = int(_primitive_value(peeling_scene, "gripper_steps", args.gripper_steps))
    grasp_qpos = float(_primitive_value(peeling_scene, "grasp_qpos", args.grasp_qpos))

    with AttachmentManager(peeling_scene.scene) as attachments:
        with recording_session_from_config(
            peeling_scene.scene,
            peeling_scene.cameras,
            cfg.recording,
            hud=_peeling_hud(peeling_scene),
        ):
            if args.run_oracle:
                run_oracle(
                    peeling_scene,
                    controller,
                    attachments,
                    move_steps=max(1, move_steps),
                    lift_steps=max(1, lift_steps),
                    place_steps=max(1, place_steps),
                    gripper_steps=max(1, gripper_steps),
                    grasp_qpos=grasp_qpos,
                    verbose=args.verbose,
                )

    print_recording_saved(cfg.recording)
    if args.keep_open_no_step:
        while args.keep_open:
            time.sleep(0.1)
    else:
        while args.keep_open:
            peeling_scene.scene.step()


if __name__ == "__main__":
    main()
