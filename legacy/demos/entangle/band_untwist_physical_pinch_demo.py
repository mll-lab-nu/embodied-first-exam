"""band_untwist (docx 3.3) end to end: lay a rope that crosses itself out flat.

One rope lies on the table crossing itself once or twice (figure-8, "6", twist,
O|-|O; `task.band.shape`). The episode has to end with zero self-crossings and
both ends back on the table. Each move grasps the plug whose strand is ON TOP at
a crossing, lifts that strand clear, carries it round and lays it down; the
move model plans the whole sequence on the settled rope at the start, the
budget is that sequence's length, and every move is re-planned on the measured
rope. After each oracle move the measured crossing sequence must be the one the
plan predicted, or the run stops (``off_plan``) instead of improvising. The
contrast ``wrong_end`` grasps the plug on the under side of the same crossing:
the docx's "flipped from the wrong side", 1 -> 2 on the figure-8. ``one_move``
is the oracle with a budget of one.

The scene, and why it is an open rope on a table rather than the docx's closed
band on a peg, is in `topogym/tasks_legacy/entangle/band_untwist.py`. The gripper
closes on a rigid plug on the rope end; the rope follows the plug through the
backend's link attachment (see the `pinch:` block in the task config).

    # the oracle, with a video
    python -m demos.entangle.band_untwist_physical_pinch_demo run.verbose=true recording=default

    # the contrast pair: same move on the under end -- expected to run to
    # completion and be judged a failure with two crossings
    python -m demos.entangle.band_untwist_physical_pinch_demo run.oracle_mode=wrong_end run.verbose=true

    # watch it in the viewer
    python -m demos.entangle.band_untwist_physical_pinch_demo run.viewer=true run.keep_open=true run.verbose=true

    # a seeded variant of the layout (task yaml's variation block)
    python -m demos.entangle.band_untwist_physical_pinch_demo run.randomize_layout=true run.seed=3

    # print the resolved config and exit
    python -m demos.entangle.band_untwist_physical_pinch_demo --cfg job
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.generation.layout_randomization import randomize_task_cfg
from topogym.planning import make_band_untwist_rule
from topogym.primitives import (
    AttachmentManager,
    HandleDragPrimitive,
    ee_quat_for_yaw,
    entity_pos,
    entity_quat,
    quat_about_axis,
    quat_mul,
)
from topogym.supervision import RopeTrace, rope_blow_ups, stop_before_physics
from topogym.supervision.band_untwist import crossing_lines, variant_line
from topogym.supervision.untangle_continuous import rope_health_lines
from topogym.tasks_legacy import BandUntwistSceneBuilder, settle_scene
from topogym.utils import (
    apply_recording_camera_overrides,
    initialize_franka_controller,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import BandUntwistPuzzleEvaluator

CONFIG_ROOT = Path(__file__).resolve().parents[2] / "configs"


def _hud(status: dict):
    def render() -> list[str]:
        return [
            "task: band_untwist",
            f"phase: {status.get('phase', '?')}",
            f"move: {status.get('move', 0)}/{status.get('budget', 0)}",
            f"self-crossings: {status.get('crossings', '?')}",
            f"ends_on_table={status.get('ends_on_table', '?')}",
            f"terminal={status.get('terminal', False)}",
        ]

    return render


TASK_ID = "band_untwist"


def _end_heading(polyline: np.ndarray, end: int) -> float:
    """Compass angle (rad) the rope leaves ``end`` on, from the measured
    centreline: the plug's axis follows it, and after a move it is not the
    spawn heading any more."""

    tip, before = (polyline[0], polyline[1]) if int(end) == 0 else (polyline[-1], polyline[-2])
    direction = np.asarray(tip[:2], dtype=float) - np.asarray(before[:2], dtype=float)
    return float(np.arctan2(direction[1], direction[0]))


def _checks_line(layout) -> str:
    return " ".join(
        f"{name}={measured:+.4f}/{limit:+.4f}/{'ok' if ok else 'FAIL'}"
        for name, measured, limit, ok in layout.checks()
    )


def _connector_report(rope_scene, tag: str) -> None:
    for end, connector in sorted(rope_scene.free_end_connectors.items()):
        pos = np.asarray(entity_pos(connector), dtype=float)
        print(
            f"connector_probe [{tag}] end{end}: "
            f"xy=({pos[0] * 1000:+.1f},{pos[1] * 1000:+.1f})mm z={pos[2] * 1000:.1f}mm",
            flush=True,
        )


def run_demo(cfg: DictConfig) -> tuple[bool, object]:
    rope_scene = BandUntwistSceneBuilder(
        cfg.env,
        cfg.task,
        cfg.robot_control,
        seed=cfg.run.seed,
    ).build(show_viewer=cfg.run.viewer)
    print(f"{TASK_ID} checks {_checks_line(rope_scene.layout)}", flush=True)
    if cfg.run.randomize_layout:
        print(variant_line(cfg.task, rope_scene.layout, seed=int(cfg.run.seed)), flush=True)
    _connector_report(rope_scene, "post_build")
    # Park each plug at its spawn pose until the gripper takes it -- same assist
    # as swap_crossing_sign (a flat-lying plug is a wheel and rolls during the
    # first ~90 FEM steps; probe 2026-08-07).
    parked: dict[int, tuple] = {
        end: (
            connector,
            np.asarray(entity_pos(connector), dtype=float).copy(),
            np.asarray(entity_quat(connector), dtype=float).copy(),
        )
        for end, connector in rope_scene.free_end_connectors.items()
    }

    _original_step = rope_scene.scene.step

    def _step_with_parked_plugs(*step_args, **step_kwargs):
        for _end, (connector, pos, quat) in parked.items():
            connector.set_pos(tuple(pos), zero_velocity=True)
            connector.set_quat(tuple(quat), zero_velocity=True)
        return _original_step(*step_args, **step_kwargs)

    rope_scene.scene.step = _step_with_parked_plugs

    controller = initialize_franka_controller(
        scene=rope_scene.scene,
        manifest=rope_scene.manifest,
        robot_cfg=cfg.robot_control,
    )
    _connector_report(rope_scene, "post_home_settle")

    pinch_cfg = cfg.task.pinch
    evaluator = BandUntwistPuzzleEvaluator.from_config(cfg.task)
    rule = make_band_untwist_rule(str(cfg.run.oracle_mode))
    primitive = HandleDragPrimitive(
        approach_z=float(rope_scene.layout.world_z(float(pinch_cfg.approach_z))),
        lift_delta=float(pinch_cfg.lift_delta),
        move_steps=int(pinch_cfg.move_steps),
        gripper_steps=int(pinch_cfg.gripper_steps),
        grasp_qpos=float(pinch_cfg.grasp_qpos_handle),
        close_hold_steps=int(pinch_cfg.close_hold_steps),
        motion_settle_steps=int(pinch_cfg.motion_settle_steps),
        min_lift_delta=float(pinch_cfg.min_lift_delta),
        max_handle_error=float(pinch_cfg.max_handle_error),
        release_hold_steps=int(pinch_cfg.release_hold_steps),
        verbose=cfg.run.verbose,
    )

    for line in rope_health_lines(rope_scene, particle_size=float(cfg.task.rope.particle_size)):
        print(line)

    settle_steps, moved = settle_scene(rope_scene)
    _connector_report(rope_scene, "post_settle")

    state = evaluator.classify(rope_scene)
    spawn_crossings = state.crossing_count
    gt_ok, gt_detail = evaluator.matches_spawn_ground_truth(rope_scene)
    # Plan the whole sequence on the settled rope; its length is the budget (no
    # spare move: a move that does not do what the plan says is a result).
    first = rule.decide(rope_scene, state, evaluator.polyline(rope_scene), pinch_cfg=pinch_cfg)
    planned_moves = first[0].planned_moves if first is not None else 0
    budget = planned_moves if cfg.run.max_moves is None else int(cfg.run.max_moves)
    if rule.budget_cap is not None:
        budget = min(budget, int(rule.budget_cap))
    status = {
        "phase": "settled",
        "move": 0,
        "budget": budget,
        "crossings": state.crossing_count,
        "ends_on_table": state.ends_on_table,
        "terminal": state.is_terminal,
    }
    trace = None
    if cfg.run.trace is not None:
        trace_path = (
            Path(f"runs/band_untwist_trace_{datetime.now():%Y%m%d-%H%M%S}.log")
            if str(cfg.run.trace) == "auto"
            else Path(str(cfg.run.trace))
        )
        trace = RopeTrace(
            rope_scene,
            trace_path,
            every=int(cfg.run.trace_every),
            offset_tolerance=float(pinch_cfg.blow_up_tolerance),
            fixed_band=float(cfg.task.rope.anchor_radius),
            rope_radius=float(cfg.task.rope.radius),
            particle_size=float(cfg.task.rope.particle_size),
            status=status,
            notes="\n".join(
                (
                    f"oracle_mode={str(cfg.run.oracle_mode)} seed={cfg.run.seed}",
                    f"segment_length={float(cfg.task.rope.mesh.segment_length)} "
                    f"radial_segments={int(cfg.task.rope.mesh.radial_segments)} "
                    f"radius={float(cfg.task.rope.radius)}",
                    f"rope_model={str(cfg.task.rope.model)} "
                    + " ".join(
                        f"fem.{key}={float(cfg.task.rope.fem[key])}"
                        for key in ("E", "nu", "rho", "friction_mu", "contact_d_hat", "follow_strength")
                    ),
                    variant_line(cfg.task, rope_scene.layout, seed=int(cfg.run.seed)),
                    f"detector vs spawn ground truth: {'match' if gt_ok else 'MISMATCH'} ({gt_detail})",
                )
            ),
        )
        print(f"band_untwist_trace -> {trace_path}")

    print(
        f"band_untwist_start seed={cfg.run.seed} mode={cfg.run.oracle_mode} shape={cfg.task.band.shape} "
        f"settle_steps={settle_steps} max_particle_step={moved:.6f} "
        f"self_crossings={state.crossing_count} gt_match={gt_ok} {gt_detail} budget={budget}"
    )
    print(f"band_untwist_planned moves={planned_moves} first=" + (
        "none" if first is None else
        f"(end={first[0].end} lift={(first[0].lift_z - rope_scene.layout.world_z(0.0)) * 1000:.0f}mm "
        f"swing={first[0].swing_deg:.0f}deg slack={first[0].slack:.2f} lay_down={first[0].lay_down_clearance * 1000:.0f}mm)"
    ), flush=True)
    if not gt_ok:
        print(
            "band_untwist WARNING: the settled spawn's crossing sequence is not the one the "
            "generator built. The oracle acts on the measured reading, so this run's verdict "
            "says nothing about the oracle -- fix the spawn first.",
            flush=True,
        )
    if cfg.run.verbose:
        for line in crossing_lines(
            state,
            rope_radius=float(cfg.task.rope.radius),
            d_hat=float(cfg.task.rope.fem.contact_d_hat),
        ):
            print(line)

    moves = 0
    off_plan = None
    ceiling_exceeded = False
    if stop_before_physics(cfg, rope_scene.scene, "band_untwist_physical_pinch_demo"):
        raise SystemExit(0)

    result = None
    with recording_session_from_config(
        rope_scene.scene,
        rope_scene.cameras,
        cfg.recording,
        hud=_hud(status),
    ), AttachmentManager(rope_scene.scene) as attachment_manager:
        while moves < budget:
            _connector_report(rope_scene, "pre_plan")
            polyline = evaluator.polyline(rope_scene)
            planned = first if moves == 0 else rule.decide(
                rope_scene, state, polyline, pinch_cfg=pinch_cfg, moves_done=moves
            )
            if planned is None:
                print(
                    f"band_untwist: no move available from this state "
                    f"(self_crossings={state.crossing_count}); stopping rather than running a "
                    "move that cannot do what it claims."
                )
                break
            command, plan = planned
            connector = rope_scene.free_end_connectors[command.end]
            carry = np.asarray(command.carry, dtype=float)
            place = np.asarray(command.cross, dtype=float)
            settle_down = np.asarray(command.settle, dtype=float)
            print(
                f"band_untwist_move {moves + 1}/{budget} kind={command.kind} end={command.end} "
                f"({'over' if command.grasped_over_end else 'UNDER'} strand) "
                f"grasp_xy=({command.grasp_xy[0]:+.3f},{command.grasp_xy[1]:+.3f}) "
                f"place_xy=({command.place_xy[0]:+.3f},{command.place_xy[1]:+.3f}) "
                f"crossing_xy=({command.crossing_xy[0]:+.3f},{command.crossing_xy[1]:+.3f}) "
                f"arc_to_crossing={command.crossing_arc * 1000:.0f}mm "
                f"lift={(command.lift_z - rope_scene.layout.world_z(0.0)) * 1000:.0f}mm "
                f"carry={(command.carry[2] - rope_scene.layout.world_z(0.0)) * 1000:.0f}mm "
                f"cross={(command.cross[2] - rope_scene.layout.world_z(0.0)) * 1000:.0f}mm "
                f"slack={command.slack:.2f} bend={command.bend * 1000:.0f}mm "
                f"room={'inf' if command.room == float('inf') else f'{command.room * 1000:.0f}mm'} "
                f"flip_radius={command.flip_radius * 1000:.0f}mm axis=({command.axis[0]:+.2f},{command.axis[1]:+.2f})"
            )
            lift_ceiling = float(
                rope_scene.layout.world_z(float(cfg.common.manipulation_space.workspace.z[1]))
            )
            if command.lift_z > lift_ceiling:
                ceiling_exceeded = True
                print(
                    f"band_untwist WARNING: this move needs the hand at "
                    f"{(command.lift_z - rope_scene.layout.world_z(0.0)) * 1000:.0f}mm, above the "
                    f"{float(cfg.common.manipulation_space.workspace.z[1]) * 1000:.0f}mm workspace "
                    "ceiling. Expect the IK to clip the lift and the crossing to stay on the table.",
                    flush=True,
                )

            status["phase"] = "grasp"
            if trace is not None:
                trace.note(
                    f"move {moves + 1}: grasping end {command.end} by its plug; target "
                    f"({command.place_xy[0]:+.3f},{command.place_xy[1]:+.3f})"
                )
            # Yaw the wrist so the finger pads close ACROSS the plug's axis, which
            # is the rope's own direction at that end -- measured now, since a plug
            # grasped a second time has been carried round since spawn.
            heading = _end_heading(polyline, command.end)
            plug_axis = np.array([np.cos(heading), np.sin(heading), 0.0])
            ee_quat = ee_quat_for_yaw(controller.default_ee_quat, heading)
            pitch_angle = np.radians(float(pinch_cfg.carry_pitch_deg))
            pitch_steps = int(pinch_cfg.carry_pitch_steps)

            held: list = []
            flat_quat: list = []

            def engage_grasp_attachment(_connector=connector, _end=command.end):
                # Weld honesty check: the assist succeeds no matter where the
                # hand is, so verify the plug really is between the pads first.
                hand_xy = np.asarray(controller.hand_pos(), dtype=float)[:2]
                plug_xy = np.asarray(entity_pos(_connector), dtype=float)[:2]
                attach_error = float(np.linalg.norm(hand_xy - plug_xy))
                attach_tolerance = float(getattr(pinch_cfg, "attach_tolerance", 0.02))
                if attach_error > attach_tolerance:
                    raise RuntimeError(
                        f"grasp attach check failed: hand is {attach_error * 1000:.1f}mm "
                        f"from the plug in xy (tolerance {attach_tolerance * 1000:.0f}mm); "
                        "refusing to weld a grasp the fingers did not make."
                    )
                parked.pop(int(_end), None)
                attachment = attachment_manager.create(
                    entity=_connector,
                    parent_pos_fn=controller.hand_pos,
                    offset=entity_pos(_connector) - np.asarray(controller.hand_pos(), dtype=float),
                    quat=entity_quat(_connector),
                )
                attachment.attach()
                held.append(attachment)
                flat_quat.append(entity_quat(_connector))
                if trace is not None:
                    trace.note(f"step {trace.count}: fingers closed, attachment engaged")

            def pitch_nose_down(lift_steps: int, _axis=plug_axis):
                if not held or pitch_angle == 0.0:
                    return
                axis = np.cross(_axis / np.linalg.norm(_axis), np.array([0.0, 0.0, 1.0]))
                target = quat_mul(quat_about_axis(axis, pitch_angle), flat_quat[0])
                held[0].ramp_to(target, pitch_steps)

            def lay_plug_flat():
                if not held or pitch_angle == 0.0:
                    return
                held[0].ramp_to(flat_quat[0], pitch_steps)

            def release_grasp_attachment(_pre_release_pos=None, _final_target=None):
                attachment = held.pop()
                if attachment.ramping():
                    print(
                        "band_untwist WARNING: released mid-pitch -- the plug is still turning "
                        "and will land off-pose."
                    )
                attachment.release(sync=False)
                attachment_manager.attachments.remove(attachment)
                if trace is not None:
                    trace.note("attachment released; the plug's pose is now solver-driven")
                return False

            flip_axis = np.asarray(command.axis, dtype=float)
            flip_steps = int(pinch_cfg.move_steps)

            def on_segment_start(index, count, label, _target):
                status["phase"] = label
                if command.kind == "flip":
                    # The plug turns with the arc: rolled about the flip axis by
                    # the same angle the hand has travelled round it, ramped
                    # over each segment (the plug may turn inside the closed
                    # fingers; the wrist itself keeps its yaw).
                    if held:
                        angle = np.pi * index / count
                        target_quat = quat_mul(quat_about_axis(flip_axis, angle), flat_quat[0])
                        held[0].ramp_to(target_quat, 2 * flip_steps)
                elif label == "place_down":
                    lay_plug_flat()

            result = primitive.run(
                controller,
                handle=connector,
                ee_quat=ee_quat,
                on_close=engage_grasp_attachment,
                on_lift=pitch_nose_down,
                before_release=release_grasp_attachment,
                on_segment_start=on_segment_start,
                target_centers=[np.asarray(xyz, dtype=float) for _label, xyz in command.path],
                segment_labels=[label for label, _xyz in command.path],
            )
            if held:
                release_grasp_attachment()
            moves += 1

            status["phase"] = "settle"
            rest_steps, rest_motion = settle_scene(
                rope_scene,
                steps=int(pinch_cfg.between_moves_settle_steps),
                require_converged=False,
            )
            # Hold the plug just laid down where it came to rest, as every plug is
            # held until its first grasp (the park above): lying flat it rolls, and a
            # later move can push it. Probe 2026-09-10: O|-|O's second landing, 4 cm
            # from the released plug of the first move, pushed it across the rope.
            parked[command.end] = (
                connector,
                np.asarray(entity_pos(connector), dtype=float).copy(),
                np.asarray(entity_quat(connector), dtype=float).copy(),
            )
            if rest_motion > float(cfg.task.settle.max_particle_step):
                print(
                    f"  WARNING rope still moving after {rest_steps} settle steps "
                    f"({rest_motion * 1000:.4f} mm/step > "
                    f"{float(cfg.task.settle.max_particle_step) * 1000:.4f}); "
                    "the reading below is measured on a moving rope"
                )

            state = evaluator.classify(rope_scene, spawn_crossings=spawn_crossings)
            status.update(
                move=moves,
                crossings=state.crossing_count,
                ends_on_table=state.ends_on_table,
                terminal=state.is_terminal,
            )
            print(
                f"band_untwist_after_move {moves} success={result.success} grasped={result.grasped} "
                f"reason={result.failure_reason} "
                f"self_crossings={command.crossing_count_before}->{state.crossing_count} "
                f"ends_on_table={state.ends_on_table} "
                f"end_heights=({state.end_heights[0] * 1000:.1f},{state.end_heights[1] * 1000:.1f})mm "
                f"failure_label={state.failure_label} terminal={state.is_terminal}"
            )
            if cfg.run.verbose:
                for line in crossing_lines(
                    state,
                    rope_radius=float(cfg.task.rope.radius),
                    d_hat=float(cfg.task.rope.fem.contact_d_hat),
                ):
                    print(line)
            for blow_up in rope_blow_ups(rope_scene, tolerance=float(pinch_cfg.blow_up_tolerance)):
                print(f"  BLOW-UP {blow_up} (grasped end={command.end})")
            if state.is_terminal:
                break
            if command.grasped_over_end and state.crossing_sequence != tuple(command.predicted_sequence):
                off_plan = moves
                print(
                    f"band_untwist_off_plan move={moves} predicted={tuple(command.predicted_sequence)} "
                    f"measured={state.crossing_sequence}: stopping instead of improvising",
                    flush=True,
                )
                break

    print(
        f"band_untwist_result seed={cfg.run.seed} mode={cfg.run.oracle_mode} shape={cfg.task.band.shape} "
        f"terminal={state.is_terminal} moves={moves}/{budget} planned={planned_moves} "
        f"spawn_self_crossings={spawn_crossings} final_self_crossings={state.crossing_count} "
        f"ends_on_table={state.ends_on_table} failure_label={state.failure_label} "
        f"off_plan={off_plan} ceiling_exceeded={ceiling_exceeded} success={state.is_terminal}"
    )
    if trace is not None:
        trace.close()
    print_recording_saved(cfg.recording)
    return bool(state.is_terminal), rope_scene


@hydra.main(version_base="1.3", config_path="../../configs", config_name="band_untwist_pinch")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)

    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"band_untwist_config -> {resolved}", flush=True)

    if cfg.run.randomize_layout:
        cfg = randomize_task_cfg(cfg, TASK_ID, cfg.run.seed, difficulty=cfg.run.difficulty)

    if int(cfg.env.sim.substeps) != 4 and bool(cfg.env.preset.locked):
        print(
            f"band_untwist: env.sim.substeps={int(cfg.env.sim.substeps)} is pinned to 4 by the "
            "frozen topogym_tabletop_v1 baseline. Add env.preset.locked=false to get past it -- "
            "that disables every other baseline check as well, so the run is off-baseline and "
            "must not be recorded as a dataset.",
            flush=True,
        )

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)])

    solved, rope_scene = run_demo(cfg)

    if cfg.run.keep_open or cfg.run.viewer:
        print("band_untwist holding the viewer open; Ctrl+C to exit.")
        while True:
            rope_scene.scene.step()
    raise SystemExit(0 if solved else 1)


if __name__ == "__main__":
    main()
