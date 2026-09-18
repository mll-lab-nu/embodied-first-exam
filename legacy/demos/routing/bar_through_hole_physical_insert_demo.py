"""Push a rigid shaft through a bulkhead aperture (docx 2.3).

Assisted grasp: the shaft is gripped 75 mm behind its centre of mass, so the
pads see a pure moment the Franka's finger gains cannot hold. The part is
carried by `AttachmentManager` (`topogym/primitives/attachment.py`), the same
mechanism cable_routing and untangle use for their rigid handles. That is a
declared kinematic event, so the IL contract line reports
`runtime_attachment=True` per `docs/develop/visual/physical_realism_guidelines_zh.md`
P1/P4.

The attachment carries the shaft; it does not aim it. The grip is rigid in the
HAND's frame (`parent_quat_fn`), so every motion the shaft makes -- the lift, the
alignment turn, the push through the bore -- is one the arm made. Nothing here
re-poses the part on its own. An episode recorded from this demo can therefore
be imitated: the actions explain the observations.

Configuration is Hydra (`configs/bar_through_hole.yaml`).

    python -m demos.routing.bar_through_hole_physical_insert_demo run.viewer=true run.verbose=true
    python -m demos.routing.bar_through_hole_physical_insert_demo run.inspect_only=true run.viewer=true
    python -m demos.routing.bar_through_hole_physical_insert_demo run.oracle_mode=bypass run.viewer=true
    python -m demos.routing.bar_through_hole_physical_insert_demo run.randomize_layout=true run.seed=3
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
from topogym.generation.layout_randomization import randomize_task_cfg
from topogym.primitives import (
    AttachmentManager,
    AxialInsertPrimitive,
    configure_gripper_contact_friction,
    entity_pos,
    entity_quat,
    print_collision_il_contract,
)
from topogym.supervision import stop_before_physics
from topogym.tasks_legacy import BarThroughHoleSceneBuilder
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import BarThroughHolePuzzleEvaluator

TASK_ID = "bar_through_hole"


def _checks_line(layout) -> str:
    return " ".join(
        f"{name}={measured:+.4f}/{limit:+.4f}/{'ok' if ok else 'FAIL'}"
        for name, measured, limit, ok in layout.checks()
    )


def _variant_line(cfg, layout) -> str:
    """One parseable line with every sampled or derived leaf (the variation sweep script reads it)."""
    task = cfg.task
    lo, hi = layout.push_window()
    side_clear = layout.aperture_inradius - layout.bar_inradius
    return (
        f"{TASK_ID} variant seed={int(cfg.run.seed)} af={float(task.aperture.across_flats):.4f} "
        f"sides={int(task.aperture.sides)} open_index={int(task.aperture.open_index)} "
        f"pitch={float(task.aperture.pitch):.4f} hole_y={float(layout.aperture_center_task()[1]):+.4f} "
        f"rest_x={float(task.bar.rest_x):+.4f} rest_y={float(task.bar.rest_y):+.4f} "
        f"panel_x={float(task.panel.x):.4f} length={float(task.bar.length):.4f} "
        f"grasp_off={float(task.bar.grasp_offset):.4f} "
        f"side_clear={side_clear:.4f} window={hi - lo:.4f} push_z={layout.push_center_z():.4f}"
    )


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


def configure_contacts(cfg, bar_scene, controller) -> None:
    """Apply the configured friction to the shaft and the fingers.

    Called from `main` rather than from `run_demo` so the inspect-only path gets
    it too: that path exists to judge how the scene settles, and settling under
    Genesis' default friction instead of the configured value would make it
    answer a question about a scene nobody runs.
    """

    physical = cfg.task.physical
    configure_gripper_contact_friction(
        entities=[bar_scene.bar_entity()],
        robot=controller.robot,
        finger_links=list(physical.finger_links),
        object_friction=float(physical.bar_friction),
        finger_friction=float(physical.finger_friction),
    )


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
        success_checks=(
            "lift_delta",
            "lift_tilt",
            "align_tilt",
            "threading_count",
            "release_stable",
        ),
    )

    evaluator = BarThroughHolePuzzleEvaluator(
        tilt_tolerance=float(np.deg2rad(float(cfg.task.success.tilt_tolerance_deg))),
        seated_z_tolerance=float(cfg.task.success.seated_z_tolerance),
        min_end_clearance=float(cfg.task.success.min_end_clearance),
    )

    # Both modes travel to the same xy; only the carry height differs. The bypass
    # goes over the panel top instead of through the aperture, so the shaft lands
    # on the lintel and the crossing falls outside the aperture rectangle.
    # Heights in config are task-frame (task z=0 is the table top); the
    # controller drives IK in world. `layout.world_z` is the conversion every
    # other demo in the repo applies at exactly this call -- see
    # the removed stacked_plate demo and its three siblings did. Passing
    # the task number straight through commands the hand to world z=0.210, i.e.
    # 0.71 m *below* the table, and the arm dives for the floor.
    # The aperture centre is where the SHAFT has to be; the primitive works out
    # where that puts the hand from the pair's measured offset.
    # The four carry heights are derived by the layout from the shaft's rest
    # height, the aperture and the cradles (2026-09-04); only approach / clear
    # are stated in config, since no axis moves them.
    insert_part_xy = layout.aperture_center()[:2]
    if mode == "wrong_hole":
        # The contrast baseline for the three-bore panel: aim at the middle bore
        # whatever the picture shows. The judge still scores the bore that is
        # actually open, so this succeeds only on the third of layouts where the
        # middle one happens to be it -- the same shape as cloth_fold's
        # `fixed_corner` and linkbar's `nearest_zone`. It reads the aperture's
        # size and height from the layout and overrides only the y, so the two
        # runs differ in one number.
        middle = layout.aperture_center_y(int(cfg.task.aperture.count) // 2)
        insert_part_xy = np.array(
            [insert_part_xy[0], float(layout.position_to_world((0.0, middle, 0.0))[1])],
            dtype=float,
        )
    if mode == "bypass":
        insert_z = layout.world_z(float(cfg.task.oracle.bypass_lift_z))
        seat_z = insert_z
    else:
        insert_z = layout.world_z(layout.insert_hand_z())
        seat_z = layout.world_z(layout.seat_hand_z())

    primitive = AxialInsertPrimitive(
        approach_z=layout.world_z(float(primitive_cfg.approach_z)),
        grasp_z=layout.world_z(layout.grasp_hand_z()),
        lift_z=layout.world_z(layout.lift_hand_z()),
        insert_z=insert_z,
        seat_z=seat_z,
        clear_z=layout.world_z(float(primitive_cfg.clear_z)),
        steps_per_phase=int(primitive_cfg.steps_per_phase),
        insert_steps=int(primitive_cfg.insert_steps),
        gripper_steps=int(primitive_cfg.gripper_steps),
        grasp_qpos=float(physical.grasp_qpos),
        close_hold_steps=int(physical.close_hold_steps),
        insert_settle_steps=int(physical.insert_settle_steps),
        release_hold_steps=int(physical.release_hold_steps),
        min_lift_delta=float(physical.min_lift_delta),
        max_grasp_tilt=float(np.deg2rad(float(physical.max_grasp_tilt_deg))),
        max_align_tilt=float(np.deg2rad(float(physical.max_align_tilt_deg))),
        align_axis_steps=int(physical.align_axis_steps),
        max_grasp_xy_error=float(physical.max_grasp_xy_error),
        min_finger_qpos=(
            None if physical.min_finger_qpos is None else float(physical.min_finger_qpos)
        ),
        verbose=bool(cfg.run.verbose),
    )

    if stop_before_physics(cfg, bar_scene.scene, "bar_through_hole_physical_insert_demo"):
        raise SystemExit(0)

    with AttachmentManager(bar_scene.scene) as attachment_manager:
        held: list = []

        origin = np.asarray(layout.task_origin, dtype=float)

        def stop_at_material(child_pos):
            """Where the shaft is allowed to be, given what is in front of it.

            The carry writes the shaft's pose, so a blind bore cannot stop it on
            its own -- see `RigidAttachment.clamp_fn`. Without this the panel
            shows two sealed holes and the shaft goes through them anyway, and a
            policy learning from the pictures would be taught that the seal means
            nothing.
            """

            pos = np.asarray(child_pos, dtype=float)
            limit = layout.max_shaft_center_x(float(pos[1] - origin[1]))
            if not np.isfinite(limit):
                return pos
            ceiling = float(limit) + float(origin[0])
            if pos[0] <= ceiling:
                return pos
            return np.array([ceiling, pos[1], pos[2]], dtype=float)

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
                # Hold the shaft RELATIVE to the hand, the same way rope_winding
                # holds its plug. Without this the shaft keeps whatever world
                # orientation it had at the grasp while the wrist turns underneath
                # it -- which would make `align_axis` sweep the pads across a shaft
                # that never moves, and leave the alignment undone.
                parent_quat_fn=controller.hand_quat,
                clamp_fn=stop_at_material,
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
            insert_part_xy=insert_part_xy,
            retreat_xy=layout.grasp_xy(),
            part_axis=(1.0, 0.0, 0.0),
            # The bore's axis: the shaft has to come out parallel to the panel
            # normal, which `layout.panel_plane()` already publishes.
            insert_axis=layout.panel_plane()[1],
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
        "finger_qpos": float(result.finger_qpos),
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
        f"align_tilt={np.rad2deg(result.align_tilt):.2f}deg "
        f"finger_qpos={result.finger_qpos:.4f} "
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

    if cfg.run.randomize_layout:
        cfg = randomize_task_cfg(cfg, TASK_ID, cfg.run.seed, difficulty=cfg.run.difficulty)

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
    print(f"{TASK_ID} checks {_checks_line(bar_scene.layout)}", flush=True)
    if cfg.run.randomize_layout:
        print(_variant_line(cfg, bar_scene.layout), flush=True)

    controller = initialize_franka_controller(
        scene=bar_scene.scene,
        manifest=bar_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=int(cfg.task.physical.settle_steps),
    )

    configure_contacts(cfg, bar_scene, controller)

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
            #
            # Report the settle drift per axis, not just the final pose: the
            # shaft is spawned exactly on its cradles, so any lateral creep here
            # is spent out of the insertion budget before the arm even moves,
            # and a bare world-frame position makes that invisible.
            spawn = entity_pos(bar_scene.bar_entity()).copy()
            controller.step(int(cfg.run.inspect_settle_steps))
            settled = entity_pos(bar_scene.bar_entity())
            drift = settled - spawn
            layout = bar_scene.layout
            budget = layout.aperture_inradius - layout.bar_inradius
            state = evaluator.classify(bar_scene)
            print(
                "bar_through_hole inspect "
                f"bar_pos={settled} "
                f"drift_mm=({drift[0] * 1e3:+.2f}, {drift[1] * 1e3:+.2f}, {drift[2] * 1e3:+.2f}) "
                f"lateral_drift_mm={float(np.hypot(drift[1], drift[2])) * 1e3:.2f} "
                f"align_budget_mm={budget * 1e3:.2f} "
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
