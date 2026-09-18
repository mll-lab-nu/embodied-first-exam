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
from pathlib import Path

import genesis as gs
import hydra
import numpy as np
from dataclasses import replace
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.generation.layout_randomization import randomize_task_cfg
from topogym.planning.cloth_unpleat_planner import FIRST_LEG_ONLY, PullExtender, CrossPullExtender, CrossCornerExtender, continuous_pull_waypoints, pull_waypoints, plan_cloth_unpleat
from topogym.primitives.cloth_link_attach_drag import ClothLinkAttachDragPrimitive
from topogym.primitives.physical_contact import ee_quat_for_yaw
from topogym.supervision import stop_before_physics
from topogym.supervision.cloth_fold import ClothFoldWatch
from topogym.tasks_legacy import ClothUnpleatSceneBuilder, band_particles, settle_band
from topogym.tasks_legacy.deformation._cloth_unpleat_geometry import PULL_MAX, pull_room
from topogym.tasks_legacy.deformation.cloth_unpleat import apply_layout_solver
from topogym.utils import (
    apply_recording_camera_overrides,
    initialize_franka_controller,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import ClothUnpleatEvaluator

TASK_ID = "cloth_unpleat"


def _variant_line(cfg, layout) -> str:
    """One parseable line with every sampled or derived leaf (the variation sweep script reads it)."""

    task = cfg.task
    pleat = task.cloth.pleat
    marks = layout.landmarks()
    ends = []
    for i in range(layout.pull_count):
        direction = layout.pull_direction(i)
        point = layout.design_grasp_point(i) + direction * layout.pull_distance(i)
        # Each pull's end on the axis that pull travels. The band's pulls all
        # run along the material axis; the cross's first one runs across it.
        ends.append(float(point[int(np.argmax(np.abs(direction)))]))
    sizes = ",".join(f"{p['width'] * 1e3:.1f}x{p['height'] * 1e3:.1f}" for p in marks["pleats"])
    stored = ",".join(f"{p['stored'] * 1e3:.1f}" for p in marks["pleats"])
    pulls_mm = ",".join(f"{layout.pull_distance(i) * 1e3:.1f}" for i in range(layout.pull_count))
    ends_y = ",".join(f"{v:+.4f}" for v in ends)

    if layout.is_cross:
        # The cross has no band runs. `lead` / `tail` report the FIRST fold's
        # bare panels so the sweep's columns keep meaning something, and the
        # second fold and the sheet's width follow as extra fields.
        cross = task.cloth.cross
        lead, tail, gap = float(cross.first.lead), float(cross.first.tail), 0.0
        extra = (
            f" W={float(task.cloth.width) * 1e3:.1f}"
            f" fold1={lead * 1e3:.0f}/{float(cross.first.depth) * 1e3:.1f}/{tail * 1e3:.0f}"
            f" fold2={float(cross.second.lead) * 1e3:.0f}/{float(cross.second.depth) * 1e3:.1f}"
            f"/{float(cross.second.tail) * 1e3:.0f}"
            f" cross_flip={int(cross.flip):+d}"
            f" particle_mm={float(task.cloth.particle_size) * 1e3:.1f}"
        )
    else:
        lead, tail = float(task.cloth.lead), float(task.cloth.tail)
        gap = float(pleat.gap) * 1e3 if int(marks["count"]) > 1 else 0.0
        extra = ""
    return (
        f"{TASK_ID} variant seed={int(cfg.run.seed)} layout={str(pleat.layout)} "
        f"pleats={sizes} gap={gap:.1f} lead={lead * 1e3:.1f} "
        f"tail={tail * 1e3:.1f} L={float(task.cloth.material_length) * 1e3:.1f} "
        f"center_x={float(task.cloth.center_x):+.4f} center_y={float(task.cloth.center_y):+.4f} "
        f"inset={float(task.grasp.edge_inset):.4f} "
        f"pull_scale={float(task.physical.pull_scale):.3f} flip={layout.band_sign:+.0f} "
        f"stored_mm={stored} pull_mm={pulls_mm} end_y={ends_y}{extra}"
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
    # The solver preset follows the DRAWN layout, so it can only be settled once
    # the draw is in -- before the resolved config is saved and the scene built.
    if apply_layout_solver(cfg):
        print(
            f"{TASK_ID} solver_preset={cfg.env.preset.id} substeps={int(cfg.env.sim.substeps)} "
            f"particle_size={float(cfg.task.cloth.particle_size):.4f} "
            f"mesh_spacing={float(cfg.task.cloth.mesh.spacing):.4f}",
            flush=True,
        )
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
    cross = layout.is_cross
    corner = cross and layout.continuous_grasp
    if bool(cfg.run.randomize_layout):
        print(_variant_line(cfg, layout), flush=True)
    print(f"{TASK_ID} checks {_checks_line(layout)}", flush=True)
    # Built once and used twice: the start-state guard reads the same measures the
    # end-state verdict does, so "still a pleat" and "unpleated" are the same
    # arithmetic on two different moments rather than two definitions.
    evaluator = ClothUnpleatEvaluator.from_config(cfg.task, material_nodes=band.material_nodes)
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
        if cross:
            from topogym.verification.cloth_fold_verifier import stretch_report
            from topogym.tasks_legacy.deformation._cloth_cross_geometry import cross_spawn_checks
            earlier = rest.copy()
            for _ in range(300):
                band.scene.step()
            rest = band_particles(band)
            cross_birth = cross_spawn_checks(earlier, rest, band.material_nodes, cfg.task)
            print(f"cloth_unpleat cross_birth_checks={cross_birth}", flush=True)
            metric = stretch_report(band.material_nodes, rest, np.asarray(band.cloth.edges, dtype=int))
            print(f"cloth_unpleat cross_spawn material_stretch={metric}", flush=True)
            if cfg.run.diagnostics_dir is not None:
                directory = Path(str(cfg.run.diagnostics_dir))
                directory.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(directory / "spawn.npz", nodes=rest,
                                    earlier=earlier,
                                    material=band.material_nodes, edges=np.asarray(band.cloth.edges),
                                    table_z=layout.table_z)
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
        # Is this still a pleat? One direct reading: the material has to still be
        # stored, i.e. the band's spread is well short of its material length.
        # Height was dropped 2026-08-23 (the pleat always lies down within 25
        # steps). The three-layer cell count was dropped 2026-09-05: it is a
        # statistic of an 8 mm occupancy grid and read 24 or 6 cells for the same
        # pleat depending on where the band sat relative to the grid, which
        # aborted ten envelope corners. It is still printed, as a record.
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
        # RELATIVE to the design, not an absolute number (2026-09-10). The guard
        # asks one thing -- did the pleat open on its own during the settle -- and
        # the honest reading of that is the settled spread against the spread the
        # layout was BUILT with. The absolute form (settled <= 0.80) tripped on a
        # band whose design spread was 0.800 exactly, because the band-length
        # ceiling is derived to sit on that same number and the settle drifts by
        # +0.001..+0.004. The 0.80 stays as a design ceiling; this is the settle.
        marks = layout.landmarks()
        design_ratio = float(marks["plan_span"]) / float(marks["material_length"])
        drift = start.spread_ratio - design_ratio
        stored_ok = abs(drift) <= float(cfg.task.grasp.max_start_spread_drift)
        if cross:
            width_span = float(np.ptp(rest[:, layout.sweep_axis]))
            width_drift = (width_span - marks["width_span"]) / marks["width"]
            stored_ok = all(row[3] for row in cross_birth)
            print(f"cloth_unpleat cross_start width_span_mm={width_span * 1e3:.1f} "
                  f"width_drift={width_drift:+.4f} fold_order=first_then_second", flush=True)
        print(
            f"cloth_unpleat start_state spread_ratio={start.spread_ratio:.3f} "
            f"design={design_ratio:.3f} drift={drift:+.3f} "
            f"max_drift={float(cfg.task.grasp.max_start_spread_drift)} "
            f"three_layer_cells={start.over_layer_cells} "
            f"single_layer_frac={start.single_layer_frac:.3f} "
            f"peak_mm={start.peak_above_table * 1e3:.2f} "
            f"across_excess_mm={start.across_excess * 1e3:.1f} "
            f"stored_ok={stored_ok}",
            flush=True,
        )
        if not stored_ok:
            reason = "cross_spawn_not_stable" if cross else "spawn_shape_drift"
            print(
                f"cloth_unpleat aborted reason={reason} "
                f"holding={int(cfg.run.final_hold_steps)}",
                flush=True,
            )
            for _ in range(max(0, int(cfg.run.final_hold_steps))):
                band.scene.step()
            if cross:
                raise SystemExit(f"cross fold failed unforced spawn checks: {cross_birth}")
            raise SystemExit(
                f"the pleat did not survive the settle ({reason}): spread_ratio "
                f"{start.spread_ratio:.3f} drifted {drift:+.3f} from the design "
                f"{design_ratio:.3f} (max drift "
                f"{float(cfg.task.grasp.max_start_spread_drift)}). "
                f"Run `bash bash_scripts/tests/pleat_stability_sweep.sh` -- the "
                f"material parameters that hold the pleat together are measured, "
                f"not guessed."
            )

        legs, episode_plan = plan_cloth_unpleat(
            layout,
            motion=str(cfg.run.motion),
            overpull_scale=float(cfg.run.overpull_scale),
        )
        print(
            f"cloth_unpleat plan legs={len(legs)} "
            f"segments={'/'.join(str(len(leg)) for leg in legs)} "
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
            attach_hold_steps=int(cfg.task.physical.get("attach_hold_steps", 0)),
            segment_settle_steps=int(cfg.task.physical.get("segment_settle_steps", 0)),
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

        # Genesis exposes the remeshed particle graph. Matching a rectangular
        # particle COUNT does not establish vertex order (s18 falsely reported
        # 49 mm anchor motion while its geometric far edge moved only 2 mm).
        pairs = np.asarray(band.cloth.edges, dtype=int)
        print(f"cloth_unpleat stretch_tracking=solver_edges particles={len(rest)} "
              f"edges={len(pairs)}", flush=True)
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
            # The tallest pleat: with two, the second one's crest can ride over
            # the first, and the budget is whatever the highest material could
            # fall from.
            fall_height=max(
                [float(p["height"]) for p in layout.landmarks()["pleats"]]
                + [float(cfg.task.cloth.cross.get("pull_lift", 0.0)) if cross else 0.0]
            ),
            gravity=abs(float(cfg.env.sim.gravity[2])),
            # Both or neither: `rest_nodes` is only there for the stretch reading,
            # and passing it without pairs sends the watch to `cloth_fold`'s
            # square-sheet fallback, which raises on a band.
            rest_nodes=band.material_nodes if cross else rest,
            pairs=pairs,
        )
        original_step = band.scene.step
        counter = {"n": 0}

        def watched_step(*args, **kwargs):
            original_step(*args, **kwargs)
            counter["n"] += 1
            watch.check(counter["n"])

        band.scene.step = watched_step
        # One observed grasp, held continuously across both pleats. Progress and
        # travel are measured from this same episode start throughout.
        extenders: list = []
        results: list = []
        diagnostics_dir = cfg.run.diagnostics_dir
        snapshot_counts: dict = {}

        def on_phase(name, index):
            watch.phase = f"leg{index + 1}_{name}"
            if diagnostics_dir is None or name not in (
                "approach", "attach", "carry_settled", "before_release",
                "detached", "release", "retreat", "done",
            ):
                return
            particles = band_particles(band)
            state = evaluator.classify(rest, particles, table_z=layout.table_z)
            tag = watch.phase
            occurrence = snapshot_counts.get(tag, 0)
            snapshot_counts[tag] = occurrence + 1
            directory = Path(str(diagnostics_dir))
            directory.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                directory / f"{tag}_{occurrence:02d}.npz",
                nodes=particles, rest=rest, hand=controller.hand_pos(),
                step=counter["n"], table_z=layout.table_z,
            )
            print(f"cloth_unpleat snapshot phase={tag} occurrence={occurrence} "
                  f"step={counter['n']} {state.summary()}", flush=True)

        def execute_pull(grasp_here, leg, extender, event_index, pull_index):
            yaw = layout.grasp_yaw(pull_index)
            return primitive.run(
                controller, band.cloth, grasp_point=grasp_here, waypoints=leg,
                ee_quat=None if yaw is None else ee_quat_for_yaw(controller.default_ee_quat, yaw),
                particles_fn=lambda: band_particles(band),
                on_phase=lambda name: on_phase(name, event_index),
                on_snapshot=lambda name: on_phase(name, event_index), extend=extender,
            )
        try:
            for index in range(len(legs)):
                nodes = band_particles(band)
                grasp_here = layout.observe(nodes, index)
                waypoint_fn = continuous_pull_waypoints if layout.continuous_grasp else pull_waypoints
                leg = waypoint_fn(
                    layout,
                    motion=str(cfg.run.motion),
                    overpull_scale=float(cfg.run.overpull_scale),
                    **({"index": index} if not layout.continuous_grasp else {}),
                )
                target_index = index if not layout.continuous_grasp else (1 if str(cfg.run.motion) in FIRST_LEG_ONLY else layout.pull_count) - 1
                # PULL_MAX is the per-pleat design stroke, not an absolute bound
                # on a continuous grasp spanning two strokes. Their sum is
                # already reserved by geometry; actual workspace room still caps it.
                direction = layout.pull_direction(index)[:2]
                if str(cfg.run.motion) == "shove":
                    direction = -direction
                room = pull_room(cfg.task, grasp_here[:2] - layout.origin[:2], index, direction=direction)
                if target_index == 0 and not cross:
                    room = min(PULL_MAX, room)
                requested = float(np.linalg.norm(np.asarray(leg[-1].position) - grasp_here))
                if corner and str(cfg.run.motion) == "shove":
                    # The control pushes the corner back over the sheet along the
                    # reversed diagonal. On a large sheet that can leave the
                    # workspace/reach budget from the observed grasp (seed 8 of
                    # the 2026-09-13 sweep raised here). A control only has to
                    # push the wrong way, not the full design stroke, so cut the
                    # leg to what the budget allows and say so, instead of
                    # commanding a waypoint the arm cannot reach.
                    end = np.asarray(leg[-1].position)
                    push = end[:2] - grasp_here[:2]
                    length = float(np.linalg.norm(push))
                    if length > 1e-12 and length > room + 1e-9:
                        scale = room / length
                        leg = [replace(w, position=tuple(grasp_here + (np.asarray(w.position) - grasp_here) * scale))
                               for w in leg]
                        print(f"{TASK_ID} shove_clamped leg={index + 1} requested_mm={length * 1e3:.1f} "
                              f"room_mm={room * 1e3:.1f}", flush=True)
                if corner:
                    previous = grasp_here
                    for waypoint in leg:
                        position = np.asarray(waypoint.position)
                        delta = position[:2] - previous[:2]
                        travel = float(np.linalg.norm(delta))
                        if travel < 1e-12:
                            previous = position
                            continue
                        available = pull_room(cfg.task, previous[:2] - layout.origin[:2], direction=delta / travel)
                        if travel > available + 1e-9:
                            raise ValueError("cross corner waypoint leaves the actual workspace/reach budget")
                        previous = position
                if str(cfg.run.motion) != "shove" and requested > room + 1e-9:
                    raise ValueError(f"pull {index + 1} needs {requested:.4f} m from observed grasp; room={room:.4f} m")
                extender = (
                    (CrossCornerExtender if corner else CrossPullExtender if cross else PullExtender)(
                        layout,
                        rest,
                        leg,
                        index=target_index,
                        target_recovered=float(cfg.task.physical.pull_extend_target),
                        max_scale=float(cfg.task.physical.pull_extend_max_scale),
                        recoil_m=float(cfg.task.physical.pull_extend_recoil_m),
                        require_local_flat=bool(cfg.task.physical.get("pull_local_flatness", False)),
                        previous_pulled=sum(e.pulled for e in extenders if e is not None),
                        start_point=grasp_here,
                        **({"material_nodes": band.material_nodes,
                            "max_drift_m": float(cfg.task.physical.get("cross_max_drift_m", 0.0))} if cross else {}),
                    )
                    # The task motion closes the loop on the band's spread (see
                    # the task config's `pull_extend_*`). The calibration motions
                    # stay open-loop for `shove` and fixed `overpull`.
                    # `single_pull` stops after the first pleat's stroke and
                    # local completion, instead of continuing to the second.
                    if str(cfg.run.motion) in ("unfold", "single_pull")
                    else None
                )
                extenders.append(extender)
                if extender is not None and not corner:
                    extender.cap = min(extender.cap, room)
                print(
                    f"cloth_unpleat leg={index + 1}/{len(legs)} "
                    f"grasp=({grasp_here[0]:+.4f},{grasp_here[1]:+.4f},{grasp_here[2]:+.4f}) "
                    f"pleats={target_index + 1} continuous_grasp={layout.continuous_grasp} "
                    f"pull_mm={requested * 1e3:.1f} "
                    f"requested_mm={requested * 1e3:.1f} room_mm={room * 1e3:.1f}",
                    flush=True,
                )
                results.append(execute_pull(grasp_here, leg, extender, index, index))
            if corner and str(cfg.run.motion) == "unfold" and bool(cfg.task.cloth.cross.get("repair_corners", False)):
                from topogym.verification.cloth_unpleat_verifier import material_dimensions
                # The first free corner does not control both remote ends of
                # these wide edges. Re-observe their material corners and spend
                # only the still-unpaid dimension, using their actual room.
                for axis, ends in ((0, (1, -1)), (1, (-1, 1))):
                    nodes = band_particles(band)
                    current = evaluator.classify(rest, nodes, table_z=layout.table_z)
                    # Once both dimensions are back, shallow contact wrinkles
                    # may settle without another grasp. Recheck before moving
                    # the hand to a corner that no longer needs pulling.
                    if (not current.is_terminal and current.gates["recovered_frac"]
                            and current.gates["width_recovered_frac"]):
                        watch.phase = "cross_repair_settle"
                        for _ in range(max(0, int(cfg.task.cloth.cross.get("repair_settle_steps", 300)))):
                            band.scene.step()
                        nodes = band_particles(band)
                        current = evaluator.classify(rest, nodes, table_z=layout.table_z)
                        print(f"cloth_unpleat repair_recheck {current.summary()}", flush=True)
                    if current.is_terminal:
                        print("cloth_unpleat repair_skipped reason=already_flat", flush=True)
                        break
                    spans, _ = material_dimensions(band.material_nodes, nodes,
                        particle_size=float(cfg.task.cloth.particle_size), material_axis=layout.material_axis,
                        length=float(cfg.task.cloth.material_length), width=float(cfg.task.cloth.width))
                    full = float(cfg.task.cloth.width if axis == 0 else cfg.task.cloth.material_length)
                    deficit = full + float(cfg.task.physical.pull_extend_recoil_m) - spans[1-axis]
                    grasp_here = layout.observe_corner(nodes, ends, index=axis)
                    room = pull_room(cfg.task, grasp_here[:2] - layout.origin[:2], direction=layout.pull_direction(axis)[:2])
                    design_cap = (layout.pull_distance(axis) / float(cfg.task.physical.pull_scale)
                                  * float(cfg.task.physical.pull_extend_max_scale))
                    distance = min(max(deficit, 0.005), room, design_cap)
                    if distance < 0.002:
                        print(f"cloth_unpleat repair_skipped axis={axis} reason=no_room "
                              f"grasp=({grasp_here[0]:+.3f},{grasp_here[1]:+.3f}) room_mm={room * 1e3:.1f} "
                              f"deficit_mm={deficit * 1e3:.1f}", flush=True)
                        continue
                    leg = pull_waypoints(layout, index=axis, start=grasp_here, distance=distance)
                    extender = CrossPullExtender(layout, rest, leg, index=axis, start_point=grasp_here,
                        material_nodes=band.material_nodes, target_recovered=float(cfg.task.physical.pull_extend_target),
                        max_drift_m=float(cfg.task.physical.get("cross_max_drift_m", 0.0)),
                        anchor_ends=tuple(-e for e in ends), anchor_reference_nodes=nodes,
                        max_scale=float(cfg.task.physical.pull_extend_max_scale), recoil_m=float(cfg.task.physical.pull_extend_recoil_m))
                    extender.cap = min(extender.cap, room)
                    extenders.append(extender)
                    event_index = len(results)
                    print(f"cloth_unpleat repair_corner leg={event_index + 1} axis={layout.pull_axis(axis)} "
                          f"deficit_mm={deficit * 1e3:.1f} room_mm={room * 1e3:.1f}", flush=True)
                    results.append(execute_pull(grasp_here, leg, extender, event_index, axis))
                    # Second round from the OPPOSITE edge (2026-09-13): if this
                    # leg gave up on anchor drift with the axis still short, take
                    # the corner on the anchored edge and pull the axis the other
                    # way. Its tow runs against the earlier legs' and cancels
                    # some of it, and the stack is already loosened, so material
                    # can leave the fold from that side too. Off unless asked.
                    if (bool(cfg.task.physical.get("cross_reverse_repair", False))
                            and extender.stop_reason == "drift"):
                        nodes = band_particles(band)
                        spans, _ = material_dimensions(band.material_nodes, nodes,
                            particle_size=float(cfg.task.cloth.particle_size), material_axis=layout.material_axis,
                            length=float(cfg.task.cloth.material_length), width=float(cfg.task.cloth.width))
                        deficit = full + float(cfg.task.physical.pull_extend_recoil_m) - spans[1-axis]
                        if deficit > 0.005:
                            far = (-1, -1)
                            grasp_here = layout.observe_corner(nodes, far, index=axis)
                            room = pull_room(cfg.task, grasp_here[:2] - layout.origin[:2],
                                             direction=-layout.pull_direction(axis)[:2])
                            distance = min(deficit, room, design_cap)
                            if distance >= 0.002:
                                leg = pull_waypoints(layout, index=axis, start=grasp_here, distance=-distance)
                                extender = CrossPullExtender(layout, rest, leg, index=axis, start_point=grasp_here,
                                    material_nodes=band.material_nodes, target_recovered=float(cfg.task.physical.pull_extend_target),
                                    max_drift_m=float(cfg.task.physical.get("cross_max_drift_m", 0.0)),
                                    anchor_ends=(1, 1), anchor_reference_nodes=nodes, direction_sign=-1.0,
                                    max_scale=float(cfg.task.physical.pull_extend_max_scale), recoil_m=float(cfg.task.physical.pull_extend_recoil_m))
                                extender.cap = min(extender.cap, room)
                                extenders.append(extender)
                                event_index = len(results)
                                print(f"cloth_unpleat repair_reverse leg={event_index + 1} axis={layout.pull_axis(axis)} "
                                      f"deficit_mm={deficit * 1e3:.1f} room_mm={room * 1e3:.1f}", flush=True)
                                results.append(execute_pull(grasp_here, leg, extender, event_index, axis))
                            else:
                                print(f"cloth_unpleat repair_reverse_skipped axis={axis} room_mm={room * 1e3:.1f}", flush=True)
            # A still tail with the arm out of the way, so the video ends on the
            # finished band rather than on the retreat.
            for _ in range(max(0, int(cfg.run.final_hold_steps))):
                band.scene.step()
        finally:
            band.scene.step = original_step

    final_nodes = band_particles(band)
    if cfg.run.diagnostics_dir is not None:
        np.savez_compressed(Path(str(cfg.run.diagnostics_dir)) / "final.npz",
                            nodes=final_nodes, rest=rest, edges=pairs, table_z=layout.table_z,
                            **({"material": band.material_nodes} if cross else {}))
    state = evaluator.classify(
        rest,
        final_nodes,
        table_z=layout.table_z,
        pairs=pairs,
    )
    # Two independent verdicts, deliberately not merged: `unpleated` is whether
    # the arm did the task, `diverged` is whether the solver produced physics. An
    # episode that diverged is not a failed attempt, it is no attempt at all, and
    # scoring it either way would poison a dataset.
    unpleated = bool(state.is_terminal)
    # Worst reading across the legs, not the last one's: with two pulls a lag on
    # either is the episode's lag, and reporting only the second would hide the
    # first.
    print(
        f"cloth_unpleat result unpleated={unpleated} diverged={watch.diverged} "
        f"motion={cfg.run.motion} legs={len(results)} "
        f"grasped={all(r.grasped for r in results)} "
        f"attach_error_mm={max(r.attach_error for r in results) * 1e3:.2f} "
        f"attached={','.join(str(r.attached_particles) for r in results)} "
        f"follow_error_mm={max(r.worst_follow_error for r in results) * 1e3:.1f} "
        f"arm_pos_err_mm={max(r.worst_pose_error for r in results) * 1e3:.1f} "
        f"arm_tilt_deg={np.degrees(max(r.worst_tilt_rad for r in results)):.1f} "
        f"phases={' | '.join('/'.join(r.completed_phases) for r in results)} "
        f"{state.summary()} {watch.summary()}",
        flush=True,
    )
    for extender in extenders:
        if extender is not None:
            print(f"cloth_unpleat pull_extend {extender.summary()}", flush=True)
    for index, r in enumerate(results):
        if r.failure_reason:
            print(f"cloth_unpleat primitive_note leg={index + 1} {r.failure_reason}", flush=True)

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
