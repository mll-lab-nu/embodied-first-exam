"""The whole cloth_unpleat episode: build, pinch the crest, spread it, judge it.

docx 1.2「展开单个褶皱」end to end. The band spawns with an unpressed pleat in its
middle, the arm pinches the crest, sweeps it round to flat, lets go, and the
judges say whether that unfolded the pleat or merely moved it.

Nothing here decides anything on its own. The trajectory comes from
`planning/cloth_unpleat_planner.py` (the arc is fixed by the material, not
chosen), the motion from `primitives/cloth_link_attach_drag.py`, the verdict from
`verification/cloth_unpleat_verifier.py`, and whether the solver stayed sane from
`supervision/cloth_fold.py`. This file wires them together and reports.

    python -B -m demos.deformation.cloth_unpleat_physical_demo
    python -B -m demos.deformation.cloth_unpleat_physical_demo run.viewer=true
    python -B -m demos.deformation.cloth_unpleat_physical_demo run.motion=press
    python -B -m demos.deformation.cloth_unpleat_physical_demo \\
        recording=hq recording.camera=[oblique,front,wrist]
"""

from __future__ import annotations

import os
import time

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.planning.cloth_unpleat_planner import chord_error, plan_cloth_unpleat
from topogym.primitives.cloth_link_attach_drag import ClothLinkAttachDragPrimitive
from topogym.primitives.physical_contact import ee_quat_for_yaw
from topogym.supervision import stop_before_physics
from topogym.supervision.cloth_fold import ClothFoldWatch
from topogym.tasks import ClothUnpleatSceneBuilder, band_particles, settle_band
from topogym.utils import (
    apply_recording_camera_overrides,
    initialize_franka_controller,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import ClothUnpleatEvaluator
from topogym.verification.cloth_unpleat_verifier import simulated_grid_pairs


@hydra.main(version_base="1.3", config_path="../../configs", config_name="cloth_unpleat")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"cloth_unpleat_config -> {resolved}", flush=True)

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
        f"cloth_unpleat_physical_demo building_scene "
        f"backend={cfg.env.genesis.backend} viewer={cfg.run.viewer} "
        f"motion={cfg.run.motion}",
        flush=True,
    )
    band = ClothUnpleatSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        show_viewer=cfg.run.viewer
    )
    layout = band.layout
    if stop_before_physics(cfg, band.scene, "cloth_unpleat"):
        return

    controller = initialize_franka_controller(
        scene=band.scene,
        manifest=band.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0,
    )
    print(
        f"cloth_unpleat_physical_demo robot_home_ready "
        f"hand={controller.hand_pos().tolist()}",
        flush=True,
    )

    primitive = ClothLinkAttachDragPrimitive(
        approach_z=float(cfg.task.physical.approach_z),
        touch_clearance=float(cfg.task.grasp.touch_clearance),
        attach_tolerance=float(cfg.task.grasp.attach_tolerance),
        attach_radius=float(cfg.task.grasp.attach_radius),
        # The band's flat run passes directly under the crest, so the attachment
        # has to be told which height it is grasping at. Without it the hand binds
        # the layer it is nowhere near -- see `attached_indices`.
        attach_z_band=float(cfg.task.grasp.attach_z_band),
        gripper_steps=int(cfg.task.physical.gripper_steps),
        move_steps=int(cfg.task.physical.move_steps),
        release_settle_steps=int(cfg.task.physical.release_hold_steps),
        max_follow_error=float(cfg.task.physical.max_follow_error),
        grasp_qpos=(
            None if cfg.task.grasp.grasp_qpos is None else float(cfg.task.grasp.grasp_qpos)
        ),
        verbose=bool(cfg.run.verbose),
    )

    with recording_session_from_config(band.scene, band.cameras, cfg.recording):
        # Everything is measured against the SETTLED band. More load-bearing here
        # than in cloth_fold: the pleat is authored into the mesh, so whether it
        # stands at all is decided during this settle, not at build time.
        rest = settle_band(band, int(cfg.task.success.settle_steps))
        # Where the crest ACTUALLY is. The pleat is authored into the mesh and
        # then let go, so it sags before the arm arrives; reaching for the design
        # position after a settle reaches into empty air, which is how the first
        # run of this demo failed. Everything the planner derives -- start angle,
        # start radius, step count -- follows from the observed crest.
        crest = layout.observe(rest)
        design = layout.design_crest_point()
        print(
            f"cloth_unpleat crest_after_settle "
            f"design=({design[0]:+.4f},{design[1]:+.4f},{design[2]:+.4f}) "
            f"observed=({crest[0]:+.4f},{crest[1]:+.4f},{crest[2]:+.4f}) "
            f"design_mm={(design[2] - layout.rest_z()) * 1e3:.2f} "
            f"observed_mm={layout.crest_height() * 1e3:.2f} "
            f"kept={layout.crest_kept():.3f}",
            flush=True,
        )
        # An episode that starts from a collapsed pleat is not a harder episode,
        # it is a different task -- and judging it would put a meaningless row in
        # the dataset. Fail here rather than sweep a flat band sideways.
        if layout.crest_kept() < float(cfg.task.grasp.min_crest_kept):
            raise SystemExit(
                f"the pleat did not survive the settle: crest kept "
                f"{layout.crest_kept():.3f} of its height, below "
                f"task.grasp.min_crest_kept={float(cfg.task.grasp.min_crest_kept)}. "
                f"Run `python -B -m tests.pleat_settle_spike` to see the sag over "
                f"time before changing the geometry."
            )

        waypoints, episode_plan = plan_cloth_unpleat(
            layout,
            motion=str(cfg.run.motion),
            overpull_scale=float(cfg.run.overpull_scale),
        )
        print(
            f"cloth_unpleat plan segments={len(waypoints)} "
            f"{episode_plan.waypoint_plan.metadata} "
            f"chord_error_mm={chord_error(layout) * 1e3:.3f} "
            f"{layout.summary()}",
            flush=True,
        )

        # Neighbour pairs for the carry-time stretch reading. A band is not a
        # square sheet, so they cannot be inferred from the particle count the way
        # `cloth_fold` does; and when Genesis' remesh is not a clean subdivision
        # they cannot be had at all, in which case the stretch reading is dropped
        # rather than guessed. **None of the three success gates need it** -- they
        # are height, layer count and spread length, and none of those needs to
        # know which particle is which.
        pairs = simulated_grid_pairs(rest, band.grid)
        if pairs is None:
            print(
                f"cloth_unpleat stretch_tracking=off particles={len(rest)} "
                f"control_grid={band.grid[0]}x{band.grid[1]} "
                f"reason=remesh_is_not_a_clean_subdivision",
                flush=True,
            )
        watch = ClothFoldWatch(
            cloth=band.cloth,
            table_z=layout.table_z,
            dt=float(cfg.env.sim.dt),
            # What the carried material may honestly fall from: the crest's own
            # height, which is the highest anything gets in this task.
            fall_height=float(cfg.task.cloth.pleat.crest_height),
            gravity=abs(float(cfg.env.sim.gravity[2])),
            # Both or neither: `rest_nodes` is only there for the stretch reading,
            # and passing it without pairs sends the watch to `cloth_fold`'s
            # square-sheet fallback, which raises on a band.
            rest_nodes=None if pairs is None else rest,
            pairs=pairs,
        )
        original_step = band.scene.step
        counter = {"n": 0}

        def watched_step(*args, **kwargs):
            original_step(*args, **kwargs)
            counter["n"] += 1
            watch.check(counter["n"])

        band.scene.step = watched_step
        try:
            result = primitive.run(
                controller,
                band.cloth,
                grasp_point=layout.crest_point(),
                waypoints=waypoints,
                ee_quat=ee_quat_for_yaw(controller.default_ee_quat, layout.grasp_yaw()),
                particles_fn=lambda: band_particles(band),
                on_phase=lambda name: setattr(watch, "phase", name),
            )
            # A still tail with the arm out of the way, so the video ends on the
            # finished band rather than on the retreat.
            for _ in range(max(0, int(cfg.run.final_hold_steps))):
                band.scene.step()
        finally:
            band.scene.step = original_step

    state = ClothUnpleatEvaluator.from_config(cfg.task).classify(
        rest,
        band_particles(band),
        table_z=layout.table_z,
        grid=band.grid,
    )
    # Two independent verdicts, deliberately not merged: `unpleated` is whether
    # the arm did the task, `diverged` is whether the solver produced physics. An
    # episode that diverged is not a failed attempt, it is no attempt at all, and
    # scoring it either way would poison a dataset.
    unpleated = bool(state.is_terminal)
    print(
        f"cloth_unpleat result unpleated={unpleated} diverged={watch.diverged} "
        f"motion={cfg.run.motion} "
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
        print(f"cloth_unpleat primitive_note {result.failure_reason}", flush=True)

    print_recording_saved(cfg.recording)
    if cfg.run.keep_open_no_step:
        while True:
            time.sleep(0.05)
    elif cfg.run.keep_open or cfg.run.viewer:
        while True:
            band.scene.step()
    # `press` and `overpull` are run to calibrate the thresholds, so their exit
    # code says whether the run happened, not whether it unpleated: only `unfold`
    # is supposed to succeed.
    if str(cfg.run.motion) != "unfold":
        raise SystemExit(0 if not watch.diverged else 1)
    raise SystemExit(0 if unpleated and not watch.diverged else 1)


if __name__ == "__main__":
    main()
