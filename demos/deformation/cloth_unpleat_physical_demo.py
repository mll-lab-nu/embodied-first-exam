"""The whole cloth_unpleat episode: build, take the band's end, pull it, judge it.

docx 1.2「展开单个褶皱」end to end. The band spawns with a pleat in its middle, the
arm takes the band's free END, drags it away from the fold along the table, lets
go, and the judges say whether that unfolded the pleat or merely towed the band.

The pleat itself is never touched: table friction on the far half is the anchor,
and the tension runs down the flat tail into the fold.

Nothing here decides anything on its own. The trajectory comes from
`planning/cloth_unpleat_planner.py` (the arc is fixed by the material, not
chosen), the motion from `primitives/cloth_link_attach_drag.py`, the verdict from
`verification/cloth_unpleat_verifier.py`, and whether the solver stayed sane from
`supervision/cloth_fold.py`. This file wires them together and reports.

    python -B -m demos.deformation.cloth_unpleat_physical_demo
    python -B -m demos.deformation.cloth_unpleat_physical_demo run.viewer=true
    python -B -m demos.deformation.cloth_unpleat_physical_demo run.motion=shove
    python -B -m demos.deformation.cloth_unpleat_physical_demo run.randomize_layout=true run.seed=3
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
from topogym.generation.layout_randomization import randomize_task_cfg
from topogym.planning.cloth_unpleat_planner import plan_cloth_unpleat
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

TASK_ID = "cloth_unpleat"


def _variant_line(cfg, layout) -> str:
    """One parseable line with every sampled or derived leaf (the variation sweep script reads it)."""

    task = cfg.task
    marks = layout.landmarks()
    grasp = layout.design_grasp_point()
    end = grasp + layout.pull_direction() * layout.pull_distance()
    return (
        f"{TASK_ID} variant seed={int(cfg.run.seed)} width={float(task.cloth.pleat.width):.4f} "
        f"crest={float(task.cloth.pleat.crest_height):.4f} center_x={float(task.cloth.center_x):+.4f} "
        f"center_y={float(task.cloth.center_y):+.4f} inset={float(task.grasp.edge_inset):.4f} "
        f"pull_scale={float(task.physical.pull_scale):.3f} side={layout.pull_sign:+.0f} "
        f"stored_mm={marks['stored'] * 1e3:.1f} pull_mm={layout.pull_distance() * 1e3:.1f} "
        f"grasp_y={grasp[1]:+.4f} end_y={end[1]:+.4f}"
    )


def _checks_line(layout) -> str:
    return " ".join(
        f"{name}={measured:+.4f}/{limit:+.4f}/{'ok' if ok else 'FAIL'}"
        for name, measured, limit, ok in layout.checks()
    )


@hydra.main(version_base="1.3", config_path="../../configs", config_name="cloth_unpleat")
def main(cfg: DictConfig) -> None:
    # A seeded variant of the layout (the task yaml's `variation:` block).
    if bool(cfg.run.randomize_layout):
        cfg = randomize_task_cfg(cfg, TASK_ID, int(cfg.run.seed), difficulty=str(cfg.run.difficulty))
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
    if bool(cfg.run.randomize_layout):
        print(_variant_line(cfg, layout), flush=True)
    print(f"{TASK_ID} checks {_checks_line(layout)}", flush=True)
    # Built once and used twice: the start-state guard reads the same measures the
    # end-state verdict does, so "still a pleat" and "unpleated" are the same
    # arithmetic on two different moments rather than two definitions.
    evaluator = ClothUnpleatEvaluator.from_config(cfg.task)
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

    with recording_session_from_config(band.scene, band.cameras, cfg.recording):
        # Everything is measured against the SETTLED band. More load-bearing here
        # than in cloth_fold: the pleat is authored into the mesh, so whether it
        # stands at all is decided during this settle, not at build time.
        # The settle and the gripper's opening happen at the same time. They are
        # independent -- the cloth relaxes whether or not the hand is doing
        # anything -- and running them in sequence put the arm on screen doing
        # nothing for two seconds before the episode started.
        controller.open_gripper(int(cfg.task.physical.gripper_steps))
        rest = settle_band(
            band,
            max(
                0,
                int(cfg.task.success.settle_steps)
                - int(cfg.task.physical.gripper_steps),
            ),
        )
        # Where the band's free end ACTUALLY is. It should agree with the design
        # position -- the band does not move during the settle once the bending
        # constraint is off -- but agreeing is a fact to check, not to assume.
        grasp = layout.observe(rest)
        design = layout.design_grasp_point()
        print(
            f"cloth_unpleat grasp_after_settle "
            f"design=({design[0]:+.4f},{design[1]:+.4f},{design[2]:+.4f}) "
            f"observed=({grasp[0]:+.4f},{grasp[1]:+.4f},{grasp[2]:+.4f}) "
            f"moved_mm={float(np.linalg.norm(grasp - design)) * 1e3:.2f}",
            flush=True,
        )
        # Is this still a pleat? Two direct readings rather than the crest height
        # this used to gate on: the material has to still be stored (or there is
        # nothing to unfold) and the layers have to still be stacked (or it is not
        # this task). Height was dropped 2026-08-23 -- the pleat always lies down
        # within 25 steps and no material parameter prevents it, so gating on
        # height rejected every episode. See the task config.
        #
        # An episode that starts from a pleat that has already come apart is not a
        # harder episode, it is a different task, and judging it would put a
        # meaningless row in the dataset. Stop here rather than sweep a flat band
        # sideways.
        #
        # It holds still for a moment before stopping, so the recording ends on
        # the collapsed pleat instead of cutting off mid-settle. A truncated clip
        # reads as a crashed run; a held one IS the evidence for what went wrong,
        # and it is the only picture of the failure anyone gets. The recorder
        # saves on the way out of its `with` even when the body raises, so the
        # video survives the SystemExit below.
        start = evaluator.classify(rest, rest, table_z=layout.table_z, grid=band.grid)
        stored_ok = start.spread_ratio <= float(cfg.task.grasp.max_start_spread_ratio)
        layers_ok = start.over_layer_cells >= int(
            cfg.task.grasp.min_start_three_layer_cells
        )
        print(
            f"cloth_unpleat start_state spread_ratio={start.spread_ratio:.3f} "
            f"max={float(cfg.task.grasp.max_start_spread_ratio)} "
            f"three_layer_cells={start.over_layer_cells} "
            f"min={int(cfg.task.grasp.min_start_three_layer_cells)} "
            f"single_layer_frac={start.single_layer_frac:.3f} "
            f"peak_mm={start.peak_above_table * 1e3:.2f} "
            f"stored_ok={stored_ok} layers_ok={layers_ok}",
            flush=True,
        )
        if not (stored_ok and layers_ok):
            reason = "material_already_released" if not stored_ok else "layers_came_apart"
            print(
                f"cloth_unpleat aborted reason={reason} "
                f"holding={int(cfg.run.final_hold_steps)}",
                flush=True,
            )
            for _ in range(max(0, int(cfg.run.final_hold_steps))):
                band.scene.step()
            raise SystemExit(
                f"the pleat did not survive the settle ({reason}): spread_ratio "
                f"{start.spread_ratio:.3f} (max "
                f"{float(cfg.task.grasp.max_start_spread_ratio)}), three-layer "
                f"cells {start.over_layer_cells} (min "
                f"{int(cfg.task.grasp.min_start_three_layer_cells)}). "
                f"Run `bash bash_scripts/tests/pleat_stability_sweep.sh` -- the "
                f"material parameters that hold the pleat together are measured, "
                f"not guessed."
            )

        waypoints, episode_plan = plan_cloth_unpleat(
            layout,
            motion=str(cfg.run.motion),
            overpull_scale=float(cfg.run.overpull_scale),
        )
        print(
            f"cloth_unpleat plan segments={len(waypoints)} "
            f"{episode_plan.waypoint_plan.metadata} "
            f"{layout.summary()}",
            flush=True,
        )

        primitive = ClothLinkAttachDragPrimitive(
            approach_z=float(cfg.task.physical.approach_z),
            touch_clearance=float(cfg.task.grasp.touch_clearance),
            attach_tolerance=float(cfg.task.grasp.attach_tolerance),
            attach_radius=float(cfg.task.grasp.attach_radius),
            # None for this task: the grasp is the band's end, a single layer on
            # the table with nothing under it to catch by mistake.
            attach_z_band=layout.attach_z_band(),
            # The gripper was opened during the settle above.
            skip_initial_open=True,
            # Same switch as `cloth_unroll`, same reason: the fingers straddle
            # the grasp point by 80 mm while open, and both the descent and the
            # close sweep them across the cloth. Off by default so this task's
            # calibrated readings do not move until an A/B says they should.
            attach_single_particle=bool(
                cfg.task.grasp.get("attach_single_particle", False)
            ),
            hold_pad_height=bool(
                cfg.task.grasp.get("hold_pad_height", True)
            ),
            close_before_descend=bool(
                cfg.task.grasp.get("close_before_descend", False)
            ),
            gripper_steps=int(cfg.task.physical.gripper_steps),
            move_steps=int(cfg.task.physical.move_steps),
            release_settle_steps=int(cfg.task.physical.release_hold_steps),
            max_follow_error=float(cfg.task.physical.max_follow_error),
            carry_settle_steps=int(cfg.task.physical.carry_settle_steps),
            touch_settle_steps=int(cfg.task.physical.touch_settle_steps),
            grasp_qpos=(
                None
                if cfg.task.grasp.grasp_qpos is None
                else float(cfg.task.grasp.grasp_qpos)
            ),
            verbose=bool(cfg.run.verbose),
        )
        # The two settle budgets, echoed because their absence and their presence
        # look identical in every other line of the log. Three times now a run
        # has been read as new evidence when it was the previous binary -- the
        # readings these change (`attach_error_mm`, the z term of `arm_gap_mm`,
        # the residual after `carry_settled`) all look plausible either way.
        print(
            f"cloth_unpleat motion_budget "
            f"pull_steps={layout.pull_steps()} "
            f"touch_settle={int(cfg.task.physical.touch_settle_steps)} "
            f"carry_settle={int(cfg.task.physical.carry_settle_steps)} "
            f"pull_scale={float(cfg.task.physical.pull_scale)} "
            f"pull_step_mm={float(cfg.task.physical.pull_step_m) * 1e3:.2f}",
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
            # `particle_size`, NOT `mesh.spacing`: Genesis remeshes the control mesh
            # to the solver's own particle spacing (595 control vertices came back as
            # 2346), so the control value is the wrong denominator by about 2x.
            # The primary reference is `median_gap` anyway -- it is measured from the
            # sheet itself, so a tear reads as worst >> median with no config in it.
            rest_spacing=float(cfg.task.cloth.particle_size),
            dt=float(cfg.env.sim.dt),
            # What the carried material may honestly fall from. Nothing is
            # lifted in this task -- the pull stays in the plane -- so the pleat's
            # own height is the whole budget.
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
                grasp_point=layout.grasp_point(),
                waypoints=waypoints,
                # None leaves the arm's own orientation alone, which is the
                # `arm_default` setting of `grasp.finger_axis` -- the fallback
                # when the wrist cannot hold a commanded angle out at the pull's
                # far end without giving up position for it.
                ee_quat=(
                    None
                    if layout.grasp_yaw() is None
                    else ee_quat_for_yaw(controller.default_ee_quat, layout.grasp_yaw())
                ),
                particles_fn=lambda: band_particles(band),
                on_phase=lambda name: setattr(watch, "phase", name),
            )
            # A still tail with the arm out of the way, so the video ends on the
            # finished band rather than on the retreat.
            for _ in range(max(0, int(cfg.run.final_hold_steps))):
                band.scene.step()
        finally:
            band.scene.step = original_step

    state = evaluator.classify(
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
