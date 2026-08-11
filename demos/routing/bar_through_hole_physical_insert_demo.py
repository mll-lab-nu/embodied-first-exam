"""Push a rigid shaft through a bulkhead aperture (docx 2.3).

Assisted grasp: the shaft is gripped 65 mm behind its centre of mass, so the
pads see a pure moment the Franka's finger gains cannot hold. The part is
carried by `AttachmentManager` (`topogym/primitives/attachment.py`), the same
mechanism cable_routing and untangle use for their rigid handles. That is a
declared kinematic event, so the IL contract line reports
`runtime_attachment=True` per `docs/develop/visual/physical_realism_guidelines_zh.md`
P1/P4.

Configuration is Hydra (`configs/bar_through_hole.yaml`).

    python -m demos.routing.bar_through_hole_physical_insert_demo run.viewer=true run.verbose=true
    python -m demos.routing.bar_through_hole_physical_insert_demo run.inspect_only=true run.viewer=true
    python -m demos.routing.bar_through_hole_physical_insert_demo run.oracle_mode=bypass run.viewer=true
    python -m demos.routing.bar_through_hole_physical_insert_demo --cfg job
"""

from __future__ import annotations

import os

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.generation import EpisodeKey, EpisodeResult
from topogym.primitives import (
    AttachmentManager,
    AxialInsertPrimitive,
    configure_gripper_contact_friction,
    entity_pos,
    entity_quat,
    print_collision_il_contract,
)
from topogym.supervision import stop_before_physics
from topogym.tasks import BarThroughHoleSceneBuilder
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import BarThroughHolePuzzleEvaluator

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


def run_demo(cfg, bar_scene, controller, *, episode_key, mode, status) -> EpisodeResult:
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
        verbose=bool(cfg.run.verbose),
    )

    if stop_before_physics(cfg, bar_scene.scene, "bar_through_hole_physical_insert_demo"):
        raise SystemExit(0)

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
    if cfg.run.verbose:
        print(f"bar_through_hole topology {state.to_info()}", flush=True)
    return episode_result


@hydra.main(version_base="1.3", config_path="../../configs", config_name="bar_through_hole")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"bar_through_hole_config -> {resolved}", flush=True)

    mode = cfg.run.oracle_mode or str(cfg.task.oracle.mode)

    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    show_viewer = bool(cfg.run.viewer and has_display)
    if cfg.run.viewer and not show_viewer:
        print("[warn] no display detected; falling back to headless.", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)], precision=str(cfg.env.genesis.precision))

    builder = BarThroughHoleSceneBuilder(cfg.env, cfg.task, cfg.robot_control)
    bar_scene = builder.build(show_viewer=show_viewer)

    controller = initialize_franka_controller(
        scene=bar_scene.scene,
        manifest=bar_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=int(cfg.task.physical.settle_steps),
    )

    episode_key = EpisodeKey(task_id="bar_through_hole", seed=int(cfg.run.seed))
    evaluator = BarThroughHolePuzzleEvaluator()
    status = {"phase": "home", "mode": mode, "release_stable": True}

    with recording_session_from_config(
        bar_scene.scene,
        bar_scene.cameras,
        cfg.recording,
        hud=_hud(bar_scene, evaluator, status),
    ):
        if cfg.run.inspect_only:
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
            run_demo(cfg, bar_scene, controller, episode_key=episode_key, mode=mode, status=status)

    print_recording_saved(cfg.recording)
    while cfg.run.keep_open and show_viewer:
        bar_scene.scene.step()


if __name__ == "__main__":
    main()
