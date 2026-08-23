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

from topogym.core import save_resolved_config
from topogym.planning.cloth_fold_planner import plan_cloth_fold
from topogym.primitives.cloth_link_attach_drag import ClothLinkAttachDragPrimitive
from topogym.primitives.physical_contact import ee_quat_for_yaw
from topogym.supervision import stop_before_physics
from topogym.supervision.cloth_fold import ClothFoldWatch
from topogym.tasks import ClothFoldSceneBuilder, cloth_particles, settle_cloth
from topogym.utils import (
    apply_recording_camera_overrides,
    initialize_franka_controller,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import ClothFoldEvaluator


@hydra.main(version_base="1.3", config_path="../../configs", config_name="cloth_fold")
def main(cfg: DictConfig) -> None:
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
    print(
        f"cloth_fold_physical_demo building_scene "
        f"backend={cfg.env.genesis.backend} viewer={cfg.run.viewer}",
        flush=True,
    )
    cloth_scene = ClothFoldSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        show_viewer=cfg.run.viewer
    )
    layout = cloth_scene.layout
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

    waypoints, episode_plan = plan_cloth_fold(layout)
    print(
        f"cloth_fold plan segments={len(waypoints)} "
        f"{episode_plan.waypoint_plan.metadata} "
        f"chord_ok={all(w.steps for w in waypoints)}",
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

    with recording_session_from_config(
        cloth_scene.scene, cloth_scene.cameras, cfg.recording
    ):
        # Everything is measured against the SETTLED sheet: it spawns a particle
        # radius above the table and has to land before its layout means anything.
        rest = settle_cloth(cloth_scene, int(cfg.task.success.settle_steps))
        watch = ClothFoldWatch(
            cloth=cloth_scene.cloth,
            table_z=layout.table_z,
            dt=float(cfg.env.sim.dt),
            fall_height=layout.fold_radius(),
            gravity=abs(float(cfg.env.sim.gravity[2])),
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
                grasp_point=layout.grasp_point(),
                waypoints=waypoints,
                ee_quat=ee_quat_for_yaw(controller.default_ee_quat, layout.grasp_yaw()),
                particles_fn=lambda: cloth_particles(cloth_scene),
                on_phase=lambda name: setattr(watch, "phase", name),
            )
            # A still tail with the arm out of the way, so the video ends on the
            # finished cloth rather than on the retreat.
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
    # Two independent verdicts, deliberately not merged: `folded` is whether the
    # arm did the task, `diverged` is whether the solver produced physics. An
    # episode that diverged is not a failed attempt, it is no attempt at all, and
    # scoring it either way would poison a dataset.
    folded = bool(state.is_terminal)
    print(
        f"cloth_fold result folded={folded} diverged={watch.diverged} "
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
    raise SystemExit(0 if folded and not watch.diverged else 1)


if __name__ == "__main__":
    main()
