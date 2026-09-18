"""The whole cloth_fold episode: build, grasp a corner, fold it, judge it.

docx 1.1「折角」end to end. The arm picks up the corner furthest from it, carries
it half a turn about the diagonal, sets it down on the opposite corner, lets go,
and the judges say whether that produced a fold.

Nothing here decides anything on its own. The trajectory comes from
`planning/cloth_fold_planner.py` (the arc is fixed by the material, not chosen),
the motion from `primitives/cloth_link_attach_drag.py`, the verdict from
`verification/cloth_fold_verifier.py`, and whether the solver stayed sane from
`supervision/cloth_fold.py`. This file wires them together and reports.

    python -B -m demos.deformation.cloth_fold_physical_demo
    python -B -m demos.deformation.cloth_fold_physical_demo run.viewer=true
    python -B -m demos.deformation.cloth_fold_physical_demo run.motion=drag
    python -B -m demos.deformation.cloth_fold_physical_demo run.randomize_layout=true run.seed=3
    python -B -m demos.deformation.cloth_fold_physical_demo \\
        recording=hq recording.camera=[oblique,topdown]
"""

from __future__ import annotations

import os
import time

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import hydra_config_sources, save_resolved_config
from topogym.data import dataset_writer_or_null
from topogym.generation import EpisodeResult, EpisodeStatus
from topogym.generation.variant_episode import build_variant_episode
from topogym.planning.cloth_fold_planner import execution_layout, plan_cloth_fold
from topogym.primitives.cloth_link_attach_drag import ClothLinkAttachDragPrimitive
from topogym.primitives.physical_contact import ee_quat_for_yaw
from topogym.supervision import stop_before_physics
from topogym.supervision.cloth_fold import ClothFoldWatch
from topogym.tasks_legacy import ClothFoldSceneBuilder, cloth_particles, settle_cloth
from topogym.utils import (
    apply_recording_camera_overrides,
    initialize_franka_controller,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import ClothFoldEvaluator

TASK_ID = "cloth_fold"


def _variant_line(cfg, layout) -> str:
    """One parseable line with every sampled or derived leaf (the variation sweep script reads it)."""

    task = cfg.task
    grasp, target = layout.grasp_point(), layout.fold_target()
    base = np.asarray([float(v) for v in task.reach.base_xy], dtype=float)
    far = grasp if grasp[0] >= target[0] else target
    return (
        f"{TASK_ID} variant seed={int(cfg.run.seed)} corner={layout.corner} "
        f"colour={layout.corner_colour_word()} "
        f"fold_fraction={layout.fold_fraction():.2f} center_x={float(task.cloth.center_x):+.4f} "
        f"center_y={float(task.cloth.center_y):+.4f} slack={float(task.physical.fold_slack):.3f} "
        f"material_mm={layout.material_distance() * 1e3:.1f} radius_mm={layout.fold_radius() * 1e3:.1f} "
        f"steps={layout.fold_steps()} grasp_x={grasp[0]:+.4f} grasp_y={grasp[1]:+.4f} "
        f"target_x={target[0]:+.4f} target_y={target[1]:+.4f} "
        f"far_reach={float(np.linalg.norm(far[:2] - base)):.4f}"
    )


def _checks_line(layout) -> str:
    return " ".join(
        f"{name}={measured:+.4f}/{limit:+.4f}/{'ok' if ok else 'FAIL'}"
        for name, measured, limit, ok in layout.checks()
    )


@hydra.main(version_base="1.3", config_path="../../configs", config_name="cloth_fold")
def main(cfg: DictConfig) -> None:
    # A seeded variant of the layout (the task yaml's `variation:` block), plus
    # the spec that records what this seed drew. The spec is what reaches the
    # H5's `setup/variant`, so a recorded episode can say which variant it is
    # instead of only which seed produced it.
    cfg, episode_spec = build_variant_episode(
        cfg,
        TASK_ID,
        int(cfg.run.seed),
        difficulty=str(cfg.run.difficulty),
        sources=hydra_config_sources(),
        variant_id=str(cfg.run.variant_id),
        randomize=bool(cfg.run.randomize_layout),
    )
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"cloth_fold_config -> {resolved}", flush=True)

    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    if cfg.run.viewer and not has_display:
        raise SystemExit("No graphical display detected.")

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(
        backend=backends[str(cfg.env.genesis.backend)],
        precision=str(cfg.env.genesis.precision),
    )
    motion = str(cfg.run.motion)
    print(
        f"cloth_fold_physical_demo building_scene "
        f"backend={cfg.env.genesis.backend} viewer={cfg.run.viewer} motion={motion}",
        flush=True,
    )
    cloth_scene = ClothFoldSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        show_viewer=cfg.run.viewer
    )
    # `layout` is what the instruction asked for and what the judge scores;
    # `hand` is what the arm executes -- the same thing except under the
    # `fixed_corner` control, which ignores the instruction.
    layout = cloth_scene.layout
    hand = execution_layout(layout, motion)
    if bool(cfg.run.randomize_layout):
        print(_variant_line(cfg, layout), flush=True)
    print(f"{TASK_ID} checks {_checks_line(layout)}", flush=True)
    print(f"{TASK_ID} instruction {layout.instruction()!r} executing={hand.corner}", flush=True)
    if stop_before_physics(cfg, cloth_scene.scene, "cloth_fold"):
        return

    controller = initialize_franka_controller(
        scene=cloth_scene.scene,
        manifest=cloth_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0,
    )
    print(
        f"cloth_fold_physical_demo robot_home_ready "
        f"hand={controller.hand_pos().tolist()}",
        flush=True,
    )

    waypoints, episode_plan = plan_cloth_fold(hand, motion=motion)
    print(
        f"cloth_fold plan segments={len(waypoints)} "
        f"{episode_plan.waypoint_plan.metadata} "
        f"chord_ok={all(w.steps for w in waypoints)} {hand.summary()}",
        flush=True,
    )

    primitive = ClothLinkAttachDragPrimitive(
        approach_z=float(cfg.task.physical.approach_z),
        touch_clearance=float(cfg.task.grasp.touch_clearance),
        attach_tolerance=float(cfg.task.grasp.attach_tolerance),
        attach_radius=float(cfg.task.grasp.attach_radius),
        gripper_steps=int(cfg.task.physical.gripper_steps),
        move_steps=int(cfg.task.physical.move_steps),
        release_settle_steps=int(cfg.task.physical.release_hold_steps),
        max_follow_error=float(cfg.task.physical.max_follow_error),
        grasp_qpos=(
            None if cfg.task.grasp.grasp_qpos is None else float(cfg.task.grasp.grasp_qpos)
        ),
        verbose=bool(cfg.run.verbose),
    )

    # The writer labels each frame with the phase the primitive is in, and it
    # reads that label at capture time -- so the phase has to live somewhere both
    # the primitive's callback and the writer can see.
    phase = {"name": "setup"}

    def on_phase(name: str) -> None:
        watch.phase = name
        phase["name"] = name

    # Two step-wrappers, outermost first: the writer is entered before the video
    # recorder so it is restored last, and both see every scene.step().
    with dataset_writer_or_null(
        cfg.run.record_dataset,
        scene=cloth_scene.scene,
        cameras=cloth_scene.cameras,
        controller=controller,
        spec=episode_spec,
        plan=episode_plan,
        every_n_steps=int(cfg.run.dataset_every_n_steps),
        subgoal_label_fn=lambda: phase["name"],
    ) as dataset_writer, recording_session_from_config(
        cloth_scene.scene, cloth_scene.cameras, cfg.recording
    ):
        # Everything is measured against the SETTLED sheet: it spawns a particle
        # radius above the table and has to land before its layout means anything.
        rest = settle_cloth(cloth_scene, int(cfg.task.success.settle_steps))
        # The settle is the sheet landing, not the demonstration: those frames
        # show an arm that has not moved and an action that repeats itself.
        if dataset_writer is not None:
            dataset_writer.start_capture()
        watch = ClothFoldWatch(
            cloth=cloth_scene.cloth,
            table_z=layout.table_z,
            dt=float(cfg.env.sim.dt),
            fall_height=hand.fold_radius(),
            gravity=abs(float(cfg.env.sim.gravity[2])),
            # The watch's ceiling is deliberately derived from gravity, not from
            # a rate -- see its module docstring. Its flat `max_speed` default
            # of 3 m/s is 30 mm a step at dt 0.01, and this task's gravity
            # budget is 49-55 mm (arc radius 13.6-17.0 cm), so the flat cap
            # overrode the derived limit on every cell and the design argument
            # never applied here. This is the ONLY one of the three cloth tasks
            # that lifts material: cloth_unpleat's budget is 19.7 mm (crest
            # 22 mm) and cloth_unroll's 28.2 mm (bar 45 mm), both tighter than
            # the flat cap, so they are unaffected and keep the default.
            #
            # Measured 2026-09-06 over the 96-corner sweep: 2 of the 3 oracle
            # trips were the flat cap firing at 44.8 and 47.1 mm while the
            # derived limit allowed 49.0 and 50.0, and both of those cells
            # passed every success gate at the end (c069, c091). c030 went over
            # the derived limit itself (97.2 vs 54.7 mm).
            #
            # This does NOT reduce the trip count, and the 2026-09-07 rerun of
            # all 96 says so: still 3, all of them now the derived rule
            # (c030 98.3, c069 59.5, c093 92.5 mm). c091 came back clean, but
            # c069 jumped 59.5 mm this time -- over its own budget, a different
            # event from the 44.8 mm one -- and c093 tripped for the first time.
            # Run-to-run noise is larger than the effect: 9 of 96 cells changed
            # verdict between the two runs, four of them folded<->not-folded
            # flips nowhere near the watch. What this setting buys is that the
            # ceiling is the one the watch derives, not a flat rate the module
            # docstring argues against; it cannot ADD a trip, since it only
            # makes the `speed` branch dead.
            max_speed=float("inf"),
            # So the carry's stretch is tracked too: a cloth that extends
            # while it is held reads as chewing gum, and by the end state the
            # crease dominates the reading and hides it.
            rest_nodes=rest,
        )
        # The watch runs off scene.step, which the primitive drives indirectly
        # through the controller, so hook it the same way the recorder does.
        original_step = cloth_scene.scene.step
        counter = {"n": 0}

        def watched_step(*args, **kwargs):
            original_step(*args, **kwargs)
            counter["n"] += 1
            watch.check(counter["n"])

        cloth_scene.scene.step = watched_step
        try:
            result = primitive.run(
                controller,
                cloth_scene.cloth,
                grasp_point=hand.grasp_point(),
                waypoints=waypoints,
                # None leaves the arm's own orientation alone, which is the
                # `arm_default` setting of `grasp.finger_axis` -- the fallback
                # when the wrist cannot hold a commanded angle.
                ee_quat=(
                    None
                    if hand.grasp_yaw() is None
                    else ee_quat_for_yaw(controller.default_ee_quat, hand.grasp_yaw())
                ),
                particles_fn=lambda: cloth_particles(cloth_scene),
                on_phase=on_phase,
            )
            # A still tail with the arm out of the way, so the video ends on the
            # finished cloth rather than on the retreat. It is for the video
            # only: frames of a scene nobody is acting on teach a policy to stall.
            if dataset_writer is not None:
                dataset_writer.stop_capture()
            for _ in range(max(0, int(cfg.run.final_hold_steps))):
                cloth_scene.scene.step()
        finally:
            cloth_scene.scene.step = original_step

        state = ClothFoldEvaluator.from_config(cfg.task).classify(
            rest,
            cloth_particles(cloth_scene),
            table_z=layout.table_z,
            fold_point=layout.fold_point(),
            fold_normal=layout.fold_normal(),
        )
        # Two independent verdicts, deliberately not merged: `folded` is whether
        # the arm did the task, `diverged` is whether the solver produced
        # physics. An episode that diverged is not a failed attempt, it is no
        # attempt at all, and scoring it either way would poison a dataset.
        folded = bool(state.is_terminal)
        # Judged inside the `with` so the writer has the verdict before it
        # writes: status, success and the end-of-episode readings all come from
        # here, and they are what a later filter selects training data on.
        if dataset_writer is not None:
            metrics = {
                "folded": folded,
                "diverged": bool(watch.diverged),
                "blowup": str(watch.tripped or "none"),
                "grasped": bool(result.grasped),
                "attach_error_mm": float(result.attach_error * 1e3),
                "follow_error_mm": float(result.worst_follow_error * 1e3),
                "motion": motion,
                "corner": str(layout.corner),
                "executed_corner": str(hand.corner),
            }
            if folded and not watch.diverged:
                episode_result = EpisodeResult.ok(episode_spec.key, metrics=metrics)
            else:
                # A solver blow-up is `error`, not `fail`: the episode did not
                # happen, so it is neither a success nor a failed attempt.
                episode_result = EpisodeResult.failed(
                    episode_spec.key,
                    str(result.failure_reason or state.summary()),
                    metrics=metrics,
                    status=EpisodeStatus.ERROR if watch.diverged else EpisodeStatus.FAIL,
                )
            dataset_writer.finalize(episode_result)
            print(f"saved dataset -> {cfg.run.record_dataset}", flush=True)
    print(
        f"cloth_fold result folded={folded} diverged={watch.diverged} "
        f"motion={motion} corner={layout.corner} executed={hand.corner} "
        f"grasped={result.grasped} "
        f"attach_error_mm={result.attach_error * 1e3:.2f} "
        f"attached={result.attached_particles} "
        f"follow_error_mm={result.worst_follow_error * 1e3:.1f} "
        f"arm_pos_err_mm={result.worst_pose_error * 1e3:.1f} "
        f"arm_tilt_deg={np.degrees(result.worst_tilt_rad):.1f} "
        f"phases={'/'.join(result.completed_phases)} "
        f"{state.summary()} {watch.summary()}",
        flush=True,
    )
    if result.failure_reason:
        print(f"cloth_fold primitive_note {result.failure_reason}", flush=True)

    print_recording_saved(cfg.recording)
    if cfg.run.keep_open_no_step:
        while True:
            time.sleep(0.05)
    elif cfg.run.keep_open or cfg.run.viewer:
        while True:
            cloth_scene.scene.step()
    # The control motions are run to show the judge rejects them, so their exit
    # code says whether the run happened, not whether it folded: only `fold` is
    # supposed to succeed.
    if motion != "fold":
        raise SystemExit(0 if not watch.diverged else 1)
    raise SystemExit(0 if folded and not watch.diverged else 1)


if __name__ == "__main__":
    main()
