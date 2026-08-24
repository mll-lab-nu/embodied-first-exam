"""The whole cloth_unroll episode: build, take the band's end, pay the roll out, judge it.

docx 1.3「展开自身卷曲的布带」end to end. The band spawns wound twice around a
horizontal bar held between two posts -- a washroom paper dispenser -- with a
short flat run lying on the table. The arm takes that run's free END and drags it
away along the table until the roll is empty, then lets go. The judges say whether
that paid the roll out or merely towed it.

**The wrist never turns.** Every bit of rotation is absorbed by the roll turning
on its bar, which is what keeps the gripper's pose relative to the cloth fixed.
Orbiting the roll instead would ask the wrist to follow through 720 degrees for
two turns, past the last joint's travel.

**One continuous stroke, slowly.** Two turns on an 8 mm bar store about 161 mm
and the arm reaches that, so the loop below runs once as shipped. It was three
strokes until 2026-08-24; splitting was a mistake, because the hand ends up at
the start plus the TOTAL however the travel is cut, so the cuts bought no reach
and only added two release-retreat-reapproach cycles -- the stop-start motion
visible in the first recordings. The loop is kept for a larger `turns`, and the
free end is re-measured before every stroke because it is somewhere new each time.

The speed matters more than anything else here. `fix_particles_to_link` binds the
caught particles kinematically, so they go exactly where the hand goes and there
is no force to tune; what limits stretch is how fast PBD propagates that into the
rest of the cloth. At 1.2's 1.5 mm a step the band stretched into a thin strip and
the recoil drove particles through the table -- see `physical.pull_step_m`.

Nothing here decides anything on its own. The trajectory comes from
`planning/cloth_unroll_planner.py` (the travel is fixed by the material, not
chosen), the motion from `primitives/cloth_link_attach_drag.py`, the verdict from
`verification/cloth_unroll_verifier.py`, and whether the solver stayed sane from
`supervision/cloth_fold.py`. This file wires them together and reports.

    python -B -m demos.deformation.cloth_unroll_physical_demo
    python -B -m demos.deformation.cloth_unroll_physical_demo run.viewer=true
    python -B -m demos.deformation.cloth_unroll_physical_demo run.motion=shove
    python -B -m demos.deformation.cloth_unroll_physical_demo run.max_strokes=1
    python -B -m demos.deformation.cloth_unroll_physical_demo \\
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
from topogym.planning.cloth_unroll_planner import plan_cloth_unroll
from topogym.primitives.cloth_link_attach_drag import ClothLinkAttachDragPrimitive
from topogym.primitives.physical_contact import ee_quat_for_yaw
from topogym.supervision import stop_before_physics
from topogym.supervision.cloth_fold import ClothFoldWatch
from topogym.tasks import ClothUnrollSceneBuilder
from topogym.tasks.deformation.cloth_unroll import band_particles, settle_band
from topogym.utils import (
    apply_recording_camera_overrides,
    initialize_franka_controller,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import ClothUnrollEvaluator
from topogym.verification.cloth_unpleat_verifier import simulated_grid_pairs


def make_primitive(cfg, *, skip_initial_open: bool) -> ClothLinkAttachDragPrimitive:
    """One primitive per stroke.

    ``skip_initial_open`` differs between the first stroke and the rest, and that
    is the whole reason this is a function. The primitive's release lets the
    PARTICLES go but leaves the fingers where they are, so every stroke after the
    first has to open them again before it descends; the first does not, because
    the gripper was opened during the settle.
    """

    return ClothLinkAttachDragPrimitive(
        approach_z=float(cfg.task.physical.approach_z),
        touch_clearance=float(cfg.task.grasp.touch_clearance),
        attach_tolerance=float(cfg.task.grasp.attach_tolerance),
        attach_radius=float(cfg.task.grasp.attach_radius),
        # None for this task: the grasp is the band's end, a single layer on the
        # table with nothing under it to catch by mistake. What keeps the disc off
        # the roll is distance, checked in `tests/check_cloth_unroll_geometry.py`.
        attach_z_band=(
            None
            if cfg.task.grasp.attach_z_band is None
            else float(cfg.task.grasp.attach_z_band)
        ),
        skip_initial_open=skip_initial_open,
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


@hydra.main(version_base="1.3", config_path="../../configs", config_name="cloth_unroll")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"cloth_unroll_config -> {resolved}", flush=True)

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
        f"cloth_unroll_physical_demo building_scene "
        f"backend={cfg.env.genesis.backend} viewer={cfg.run.viewer} "
        f"motion={cfg.run.motion}",
        flush=True,
    )
    band = ClothUnrollSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        show_viewer=cfg.run.viewer
    )
    layout = band.layout
    # Built once and used twice: the start-state guard reads the same measures the
    # end-state verdict does, so "still a roll" and "unrolled" are the same
    # arithmetic on two different moments rather than two definitions.
    evaluator = ClothUnrollEvaluator.from_config(cfg.task)
    bar = {"bar_centre": layout.bar_centre(), "bar_height": layout.bar_height()}
    if stop_before_physics(cfg, band.scene, "cloth_unroll"):
        return

    controller = initialize_franka_controller(
        scene=band.scene,
        manifest=band.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0,
    )
    print(
        f"cloth_unroll_physical_demo robot_home_ready "
        f"hand={controller.hand_pos().tolist()}",
        flush=True,
    )

    with recording_session_from_config(band.scene, band.cameras, cfg.recording):
        # Everything is measured against the SETTLED band. More load-bearing here
        # than in cloth_fold: the roll is authored into the mesh rather than
        # wound by anything, so whether it stays on the bar at all is decided
        # during this settle. `tests/roll_settle_spike.py` asks that on its own.
        #
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
        grasp = layout.observe(rest)
        design = layout.design_grasp_point()
        print(
            f"cloth_unroll grasp_after_settle "
            f"design=({design[0]:+.4f},{design[1]:+.4f},{design[2]:+.4f}) "
            f"observed=({grasp[0]:+.4f},{grasp[1]:+.4f},{grasp[2]:+.4f}) "
            f"moved_mm={float(np.linalg.norm(grasp - design)) * 1e3:.2f}",
            flush=True,
        )
        # Is this still a roll? Two direct readings: the material has to still be
        # wound (or there is nothing to pay out) and the layers have to still be
        # stacked (or it is not this task). Same pair `cloth_unpleat` gates on and
        # the same pair `roll_settle_spike` decides its verdict by -- two
        # definitions of the same thing is how they drift apart.
        #
        # An episode that starts from a roll that has already come apart is not a
        # harder episode, it is a different task, and judging it would put a
        # meaningless row in the dataset. It holds still for a moment before
        # stopping so the recording ends on the collapsed roll rather than cutting
        # off mid-settle; the recorder saves on the way out of its `with` even
        # when the body raises, so the video survives the SystemExit.
        start = evaluator.classify(rest, rest, table_z=layout.table_z, grid=band.grid, **bar)
        stored_ok = start.spread_ratio <= float(cfg.task.grasp.max_start_spread_ratio)
        layers_ok = start.over_layer_cells >= int(
            cfg.task.grasp.min_start_three_layer_cells
        )
        print(
            f"cloth_unroll start_state spread_ratio={start.spread_ratio:.3f} "
            f"max={float(cfg.task.grasp.max_start_spread_ratio)} "
            f"multi_layer_cells={start.over_layer_cells} "
            f"min={int(cfg.task.grasp.min_start_three_layer_cells)} "
            f"single_layer_frac={start.single_layer_frac:.3f} "
            f"on_bar={start.on_bar} "
            f"out_of_plane_mm={start.out_of_plane * 1e3:.2f} "
            f"stored_ok={stored_ok} layers_ok={layers_ok}",
            flush=True,
        )
        if not (stored_ok and layers_ok):
            reason = "material_already_released" if not stored_ok else "layers_came_apart"
            print(
                f"cloth_unroll aborted reason={reason} "
                f"holding={int(cfg.run.final_hold_steps)}",
                flush=True,
            )
            for _ in range(max(0, int(cfg.run.final_hold_steps))):
                band.scene.step()
            raise SystemExit(
                f"the roll did not survive the settle ({reason}): spread_ratio "
                f"{start.spread_ratio:.3f} (max "
                f"{float(cfg.task.grasp.max_start_spread_ratio)}), multi-layer "
                f"cells {start.over_layer_cells} (min "
                f"{int(cfg.task.grasp.min_start_three_layer_cells)}), on_bar "
                f"{start.on_bar}. Run `python -B -m tests.roll_settle_spike` -- "
                f"the geometry that holds the roll on the bar is measured, not "
                f"guessed."
            )

        # The travel budget, echoed because its absence and its presence look
        # identical in every other line of the log. Three times on 1.2 a run was
        # read as new evidence when it was the previous binary -- the readings the
        # settle holds change (`attach_error_mm`, the z term of `arm_gap_mm`, the
        # residual after `carry_settled`) all look plausible either way.
        strokes = layout.stroke_count()
        planned = strokes if int(cfg.run.max_strokes) <= 0 else min(
            strokes, int(cfg.run.max_strokes)
        )
        final = layout.final_grasp_point()
        print(
            f"cloth_unroll motion_budget "
            f"strokes={planned}/{strokes} "
            f"stroke_mm={layout.stroke_distance() * 1e3:.1f} "
            f"total_mm={layout.pull_total() * 1e3:.1f} "
            f"rolled_mm={layout.rolled_length() * 1e3:.1f} "
            f"stroke_steps={layout.stroke_steps()} "
            f"touch_settle={int(cfg.task.physical.touch_settle_steps)} "
            f"carry_settle={int(cfg.task.physical.carry_settle_steps)} "
            f"pull_scale={float(cfg.task.physical.pull_scale)} "
            f"pull_step_mm={float(cfg.task.physical.pull_step_m) * 1e3:.2f} "
            f"final_y={float(final[layout.material_axis]):+.4f} "
            f"{layout.summary()}",
            flush=True,
        )

        # Neighbour pairs for the carry-time stretch reading. A band is not a
        # square sheet, so they cannot be inferred from the particle count the way
        # `cloth_fold` does; and when Genesis' remesh is not a clean subdivision
        # they cannot be had at all, in which case the stretch reading is dropped
        # rather than guessed. **Neither success gate needs it** -- they are layer
        # count and spread length, and neither needs to know which particle is
        # which.
        pairs = simulated_grid_pairs(rest, band.grid)
        if pairs is None:
            print(
                f"cloth_unroll stretch_tracking=off particles={len(rest)} "
                f"control_grid={band.grid[0]}x{band.grid[1]} "
                f"reason=remesh_is_not_a_clean_subdivision",
                flush=True,
            )
        watch = ClothFoldWatch(
            cloth=band.cloth,
            table_z=layout.table_z,
            dt=float(cfg.env.sim.dt),
            # What the material may honestly fall from. Nothing is lifted -- the
            # pull stays in the plane -- so the bar's own height is the budget,
            # which is what the outermost turn drops through if it comes off.
            fall_height=float(cfg.task.dispenser.bar_height),
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
        results = []
        try:
            for stroke in range(1, planned + 1):
                # Re-measure the free end before EVERY stroke. It has moved by the
                # length of the last pull, and the roll has turned behind it.
                if stroke > 1:
                    here = layout.observe(band_particles(band))
                    print(
                        f"cloth_unroll stroke_start index={stroke}/{planned} "
                        f"end=({here[0]:+.4f},{here[1]:+.4f},{here[2]:+.4f})",
                        flush=True,
                    )
                waypoints, episode_plan = plan_cloth_unroll(
                    layout,
                    stroke=stroke,
                    motion=str(cfg.run.motion),
                    overpull_scale=float(cfg.run.overpull_scale),
                )
                print(
                    f"cloth_unroll plan stroke={stroke}/{planned} "
                    f"segments={len(waypoints)} "
                    f"{episode_plan.waypoint_plan.metadata}",
                    flush=True,
                )
                result = make_primitive(cfg, skip_initial_open=(stroke == 1)).run(
                    controller,
                    band.cloth,
                    grasp_point=layout.grasp_point(),
                    waypoints=waypoints,
                    # None leaves the arm's own orientation alone, which is the
                    # `arm_default` setting of `grasp.finger_axis` -- the fallback
                    # when the wrist cannot hold a commanded angle out at the
                    # pull's far end without giving up position for it.
                    ee_quat=(
                        None
                        if layout.grasp_yaw() is None
                        else ee_quat_for_yaw(
                            controller.default_ee_quat, layout.grasp_yaw()
                        )
                    ),
                    particles_fn=lambda: band_particles(band),
                    on_phase=lambda name: setattr(watch, "phase", name),
                )
                results.append(result)
                here = evaluator.classify(
                    rest, band_particles(band), table_z=layout.table_z, grid=band.grid, **bar
                )
                print(
                    f"cloth_unroll stroke_done index={stroke}/{planned} "
                    f"grasped={result.grasped} "
                    f"attach_error_mm={result.attach_error * 1e3:.2f} "
                    f"attached={result.attached_particles} "
                    f"follow_error_mm={result.worst_follow_error * 1e3:.1f} "
                    f"recovered_frac={here.recovered_frac:.3f} "
                    f"single_layer_frac={here.single_layer_frac:.3f} "
                    f"on_bar={here.on_bar}",
                    flush=True,
                )
                if not result.grasped:
                    # Stop rather than plan the next stroke from an end the hand
                    # never held: after a missed grasp the cloth is where the last
                    # stroke left it, and pulling again from a re-measured end
                    # would look like progress in the log while the roll has not
                    # moved. The judges still run on whatever state this is.
                    print(
                        f"cloth_unroll stroke_aborted index={stroke}/{planned} "
                        f"reason={result.failure_reason or 'grasp_failed'}",
                        flush=True,
                    )
                    break
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
        **bar,
    )
    # Two independent verdicts, deliberately not merged: `unrolled` is whether the
    # arm did the task, `diverged` is whether the solver produced physics. An
    # episode that diverged is not a failed attempt, it is no attempt at all, and
    # scoring it either way would poison a dataset.
    unrolled = bool(state.is_terminal)
    worst_follow = max((r.worst_follow_error for r in results), default=float("nan"))
    worst_pose = max((r.worst_pose_error for r in results), default=float("nan"))
    worst_tilt = max((r.worst_tilt_rad for r in results), default=float("nan"))
    print(
        f"cloth_unroll result unrolled={unrolled} diverged={watch.diverged} "
        f"motion={cfg.run.motion} "
        f"strokes_run={len(results)}/{planned} "
        f"grasped={sum(1 for r in results if r.grasped)} "
        f"attach_error_mm={'/'.join(f'{r.attach_error * 1e3:.2f}' for r in results)} "
        f"attached={'/'.join(str(r.attached_particles) for r in results)} "
        f"follow_error_mm={worst_follow * 1e3:.1f} "
        f"arm_pos_err_mm={worst_pose * 1e3:.1f} "
        f"arm_tilt_deg={np.degrees(worst_tilt):.1f} "
        f"{state.summary()} {watch.summary()}",
        flush=True,
    )
    for index, result in enumerate(results, start=1):
        if result.failure_reason:
            print(
                f"cloth_unroll primitive_note stroke={index} "
                f"{result.failure_reason}",
                flush=True,
            )

    print_recording_saved(cfg.recording)
    if cfg.run.keep_open_no_step:
        while True:
            time.sleep(0.05)
    elif cfg.run.keep_open or cfg.run.viewer:
        while True:
            band.scene.step()
    # `shove` and `overpull` are run to calibrate the thresholds, so their exit
    # code says whether the run happened, not whether it unrolled: only `unroll`
    # is supposed to succeed. Same for a deliberately shortened run -- one stroke
    # of three cannot empty the roll and it is not a failure that it did not.
    if str(cfg.run.motion) != "unroll" or planned < strokes:
        raise SystemExit(0 if not watch.diverged else 1)
    raise SystemExit(0 if unrolled and not watch.diverged else 1)


if __name__ == "__main__":
    main()
