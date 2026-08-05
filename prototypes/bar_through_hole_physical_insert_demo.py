"""Push a rigid shaft through a bulkhead aperture (docx 2.3).

Assisted grasp: the shaft is gripped 65 mm behind its centre of mass, so the
pads see a pure moment the Franka's finger gains cannot hold. The part is
carried by `AttachmentManager` (`topogym/primitives/attachment.py`), the same
mechanism cable_routing and untangle use for their rigid handles. That is a
declared kinematic event, so the IL contract line reports
`runtime_attachment=True` per `docs/develop/visual/physical_realism_guidelines_zh.md`
P1/P4.

    python -m prototypes.bar_through_hole_physical_insert_demo --viewer --verbose
    python -m prototypes.bar_through_hole_physical_insert_demo --inspect-only --viewer
    python -m prototypes.bar_through_hole_physical_insert_demo --oracle-mode bypass --viewer
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import genesis as gs
import numpy as np

from topogym.core import add_common_config_arg, load_topogym_configs
from topogym.generation import EpisodeKey, EpisodeResult
from topogym.primitives import (
    AttachmentManager,
    AxialInsertPrimitive,
    configure_gripper_contact_friction,
    entity_pos,
    entity_quat,
    print_collision_il_contract,
)
from topogym.tasks import BarThroughHoleSceneBuilder
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import (
    add_recording_args,
    merge_recording_config,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import BarThroughHolePuzzleEvaluator

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "configs"
DEFAULT_ENV_CONFIG = CONFIG_ROOT / "env_configs" / "world_tabletop_v1.yaml"
DEFAULT_ROBOT_CONFIG = CONFIG_ROOT / "robot_control_configs" / "franka_panda_position_ik.yaml"
DEFAULT_TASK_CONFIG = CONFIG_ROOT / "task_configs" / "bar_through_hole_topogym_tabletop_v1.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Push a rigid shaft through a bulkhead aperture."
    )
    add_common_config_arg(parser)
    parser.add_argument("--env-config", type=Path, default=DEFAULT_ENV_CONFIG)
    parser.add_argument("--robot-config", type=Path, default=DEFAULT_ROBOT_CONFIG)
    parser.add_argument("--task-config", type=Path, default=DEFAULT_TASK_CONFIG)
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), default="gpu")
    parser.add_argument("--viewer", action="store_true", help="Open the interactive viewer.")
    parser.add_argument("--keep-open", action="store_true", help="Keep stepping after the run.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--inspect-only",
        action="store_true",
        help="Build the scene and settle at home without running the motion. "
        "Use this first: it is where a home-pose/geometry interpenetration shows up.",
    )
    parser.add_argument(
        "--oracle-mode",
        choices=("insert", "bypass"),
        default=None,
        help="insert = thread it through; bypass = lift over the panel top "
        "(the anti-shortcut, expected to be judged a failure).",
    )
    parser.add_argument("--verbose", action="store_true")
    add_recording_args(parser)
    return parser.parse_args()


def load_configs(args: argparse.Namespace):
    cfg = load_topogym_configs(
        common_config=args.common_config,
        env_config=args.env_config,
        robot_config=args.robot_config,
        task_config=args.task_config,
    )
    cfg.env.genesis.backend = args.backend
    # Returns a new config -- `OmegaConf.merge` does not modify in place, so
    # dropping the result leaves cfg without the `recording` section that
    # `recording_session_from_config` reads.
    return merge_recording_config(cfg, args)


def _hud(bar_scene, evaluator, status):
    def render_lines():
        state = evaluator.classify(bar_scene, release_stable=bool(status.get("release_stable", True)))
        return [
            "task=bar_through_hole",
            f"phase={status.get('phase', '-')}",
            f"mode={status.get('mode', 'insert')}",
            f"threading={state.threading_count}",
            f"tilt={np.rad2deg(state.tilt_rad):.1f}deg",
            f"seated={state.seated}",
        ]

    return render_lines


def run_demo(args, cfg, bar_scene, controller, *, episode_key, mode, status) -> EpisodeResult:
    layout = bar_scene.layout
    physical = cfg.task.physical
    primitive_cfg = cfg.task.primitive
    bar = bar_scene.bar_entity()

    print_collision_il_contract(
        "bar_through_hole_physical_insert_demo",
        manipulated=["bar"],
        runtime_attachment=True,
        runtime_set_pose=False,
        success_checks=("lift_delta", "lift_tilt", "threading_count", "release_stable"),
    )

    configure_gripper_contact_friction(
        entities=[bar],
        robot=controller.robot,
        finger_links=list(physical.finger_links),
        object_friction=float(physical.bar_friction),
        finger_friction=float(physical.finger_friction),
    )

    evaluator = BarThroughHolePuzzleEvaluator(
        tilt_tolerance=float(np.deg2rad(float(cfg.task.success.tilt_tolerance_deg))),
        seated_z_tolerance=float(cfg.task.success.seated_z_tolerance),
        min_end_clearance=float(cfg.task.success.min_end_clearance),
    )

    # Both modes travel to the same xy; only the carry height differs. The bypass
    # goes over the panel top instead of through the aperture, so the shaft lands
    # on the lintel and the crossing falls outside the aperture rectangle.
    insert_xy = layout.insert_hand_xy()
    if mode == "bypass":
        insert_z = float(cfg.task.oracle.bypass_lift_z)
        seat_z = insert_z
    else:
        insert_z = float(primitive_cfg.insert_z)
        seat_z = float(primitive_cfg.seat_z)

    primitive = AxialInsertPrimitive(
        approach_z=float(primitive_cfg.approach_z),
        grasp_z=float(primitive_cfg.grasp_z),
        lift_z=float(primitive_cfg.lift_z),
        insert_z=insert_z,
        seat_z=seat_z,
        clear_z=float(primitive_cfg.clear_z),
        steps_per_phase=int(primitive_cfg.steps_per_phase),
        insert_steps=int(primitive_cfg.insert_steps),
        gripper_steps=int(primitive_cfg.gripper_steps),
        grasp_qpos=float(physical.grasp_qpos),
        close_hold_steps=int(physical.close_hold_steps),
        insert_settle_steps=int(physical.insert_settle_steps),
        release_hold_steps=int(physical.release_hold_steps),
        min_lift_delta=float(physical.min_lift_delta),
        max_grasp_tilt=float(np.deg2rad(float(physical.max_grasp_tilt_deg))),
        max_grasp_xy_error=float(physical.max_grasp_xy_error),
        verbose=bool(args.verbose),
    )

    with AttachmentManager(bar_scene.scene) as attachment_manager:
        held: list = []

        def attach_bar():
            # Hand over the shaft's *actual* pose. RigidAttachment's default is a
            # yaw-only hold that assumes an upright child; a shaft lying flat is
            # exactly the case its docstring warns about, and the default would
            # snap it upright in a single step.
            attachment = attachment_manager.create(
                entity=bar,
                parent_pos_fn=controller.hand_pos,
                offset=entity_pos(bar) - np.asarray(controller.hand_pos(), dtype=float),
                quat=entity_quat(bar),
            )
            attachment.attach()
            held.append(attachment)
            status["phase"] = "carrying"
            return attachment

        def release_bar():
            status["phase"] = "released"
            for attachment in held:
                attachment.release(sync=False)
            held.clear()

        status["phase"] = "insert" if mode == "insert" else "bypass"
        result = primitive.run(
            controller,
            part=bar,
            grasp_xy=layout.grasp_xy(),
            insert_xy=insert_xy,
            retreat_xy=layout.grasp_xy(),
            part_axis=(1.0, 0.0, 0.0),
            ee_quat=controller.default_ee_quat,
            attach_fn=attach_bar,
            release_fn=release_bar,
        )

        # Physical recheck (Section 4.2): keep stepping after the arm is clear and
        # require the reading to survive. Geometry alone is not task_success.
        status["phase"] = "release_check"
        before = entity_pos(bar)
        pre_state = evaluator.classify(bar_scene, release_stable=True)
        controller.step(int(physical.release_check_steps))
        drift = float(np.linalg.norm(entity_pos(bar) - before))
        post_state = evaluator.classify(bar_scene, release_stable=True)
        release_stable = bool(
            drift <= float(physical.release_max_drift)
            and post_state.threading_count == pre_state.threading_count
        )
        status["release_stable"] = release_stable

    state = evaluator.classify(bar_scene, release_stable=release_stable)
    status["phase"] = "done"

    metrics = {
        "physical_success": bool(result.success),
        "threading_count": int(state.threading_count),
        "geometry_ok": bool(state.geometry_ok),
        "release_stable": bool(release_stable),
        "release_drift": drift,
        "lift_delta": float(result.lift_delta),
        "lift_tilt_deg": float(np.rad2deg(result.lift_tilt)),
        "align_tilt_deg": float(np.rad2deg(result.align_tilt)),
        "bar_tilt_deg": float(np.rad2deg(state.tilt_rad)),
        "oracle_mode": mode,
    }

    # In bypass mode the anti-shortcut succeeding physically is the *expected*
    # outcome; the point is that the task judge still rejects it.
    task_success = bool(state.is_terminal)
    if task_success:
        episode_result = EpisodeResult.ok(
            episode_key, metrics=metrics, export_ready=bool(result.success)
        )
    else:
        episode_result = EpisodeResult.failed(
            episode_key,
            result.failure_reason or f"bar_not_threaded(threading={state.threading_count})",
            metrics=metrics,
            stable_ready=False,
        )

    print(
        "bar_through_hole_physical_insert_demo result "
        f"mode={mode} success={episode_result.success} "
        f"threading={state.threading_count} geometry_ok={state.geometry_ok} "
        f"release_stable={release_stable} drift={drift:.5f} "
        f"lift_delta={result.lift_delta:.4f} lift_tilt={np.rad2deg(result.lift_tilt):.2f}deg "
        f"failure_reason={episode_result.failure_reason} "
        f"phases={len(result.completed_phases)}/{len(AxialInsertPrimitive.NOMINAL_PHASES)}",
        flush=True,
    )
    if args.verbose:
        print(f"bar_through_hole topology {state.to_info()}", flush=True)
    return episode_result


def main() -> None:
    args = parse_args()
    cfg = load_configs(args)
    mode = args.oracle_mode or str(cfg.task.oracle.mode)

    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    show_viewer = bool(args.viewer and has_display)
    if args.viewer and not show_viewer:
        print("[warn] no display detected; falling back to headless.", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[args.backend], precision=str(cfg.env.genesis.precision))

    builder = BarThroughHoleSceneBuilder(cfg.env, cfg.task, cfg.robot_control)
    bar_scene = builder.build(show_viewer=show_viewer)

    controller = initialize_franka_controller(
        scene=bar_scene.scene,
        manifest=bar_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=int(cfg.task.physical.settle_steps),
    )

    episode_key = EpisodeKey(task_id="bar_through_hole", seed=int(args.seed))
    evaluator = BarThroughHolePuzzleEvaluator()
    status = {"phase": "home", "mode": mode, "release_stable": True}

    with recording_session_from_config(
        bar_scene.scene,
        bar_scene.cameras,
        cfg.recording,
        hud=_hud(bar_scene, evaluator, status),
    ):
        if args.inspect_only:
            # Home settle only. This is the step that surfaces a home-pose /
            # geometry interpenetration, which is how stacked_plate got a solver
            # NaN before its raised-home config existed.
            controller.step(200)
            state = evaluator.classify(bar_scene)
            print(
                "bar_through_hole inspect "
                f"bar_pos={entity_pos(bar_scene.bar_entity())} "
                f"threading={state.threading_count} tilt_deg={np.rad2deg(state.tilt_rad):.2f}",
                flush=True,
            )
        else:
            run_demo(args, cfg, bar_scene, controller, episode_key=episode_key, mode=mode, status=status)

    print_recording_saved(cfg.recording)
    while args.keep_open and show_viewer:
        bar_scene.scene.step()


if __name__ == "__main__":
    main()
