"""band_untwist (docx 3.3) end to end: open a rope's figure-8 into an O.

One rope lies on the table in a figure-8 with a single self-crossing. The
episode has to end with zero self-crossings and both ends back on the table.
The oracle is one move: grasp the end whose strand is ON TOP at the crossing,
lift that strand clear, carry it across the other strand, lay it down beside the
other end. The contrast pair grasps the OTHER end with the same motion and lands
a second crossing instead: the docx's "flipped from the wrong side", 1 -> 2.

The scene, and why it is an open rope on a table rather than the docx's closed
band on a peg, is in `topogym/tasks/entangle/band_untwist.py`. The gripper
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
from topogym.supervision.band_untwist import crossing_lines
from topogym.supervision.untangle_continuous import rope_health_lines
from topogym.tasks import BandUntwistSceneBuilder, settle_scene
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


def _variant_line(cfg, layout) -> str:
    """One parseable line with every sampled or derived leaf (the variation sweep script reads it)."""
    eight = cfg.task.figure_eight
    spec = layout.figure_eight_spec()
    ramp = min(spec.lift_ramp, 0.8 * min(spec.tangent_length(spec.closed_lobe_radius),
                                         spec.tangent_length(spec.open_lobe_radius)))
    return (
        f"{TASK_ID} variant seed={int(cfg.run.seed)} over_end={int(eight.over_end)} "
        f"heading={float(eight.heading_deg):+.1f} cx={float(eight.center_x):+.4f} cy={float(eight.center_y):+.4f} "
        f"half_angle={float(eight.half_angle_deg):.1f} r_closed={float(eight.closed_lobe_radius):.4f} "
        f"r_open={float(eight.open_lobe_radius):.4f} end_gap={float(eight.end_gap):.4f} "
        f"ramp={ramp:.4f} lift_pred={layout.predicted_lift():.3f}"
    )


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
        print(_variant_line(cfg, rope_scene.layout), flush=True)
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
    gt_ok, gt_detail = evaluator.matches_spawn_ground_truth(rope_scene)
    budget = (
        int(cfg.run.max_moves)
        if cfg.run.max_moves is not None
        else int(cfg.task.oracle.max_moves)
    )
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
                    f"figure_eight: closed_r={float(cfg.task.figure_eight.closed_lobe_radius)} "
                    f"open_r={float(cfg.task.figure_eight.open_lobe_radius)} "
                    f"end_gap={float(cfg.task.figure_eight.end_gap)} "
                    f"half_angle={float(cfg.task.figure_eight.half_angle_deg)} "
                    f"over_lift={float(cfg.task.figure_eight.over_lift)}",
                    f"detector vs spawn ground truth: {'match' if gt_ok else 'MISMATCH'} ({gt_detail})",
                )
            ),
        )
        print(f"band_untwist_trace -> {trace_path}")

    print(
        f"band_untwist_start seed={cfg.run.seed} mode={cfg.run.oracle_mode} "
        f"settle_steps={settle_steps} max_particle_step={moved:.6f} "
        f"self_crossings={state.crossing_count} gt_match={gt_ok} {gt_detail} budget={budget}"
    )
    if not gt_ok:
        print(
            "band_untwist WARNING: the settled spawn does not read as one crossing with the "
            "generator's over end on top. The oracle acts on the measured reading, so this "
            "run's verdict says nothing about the oracle -- fix the spawn first.",
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
            planned = rule.decide(rope_scene, state, polyline, pinch_cfg=pinch_cfg)
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
                f"band_untwist_move {moves + 1}/{budget} end={command.end} "
                f"({'over' if command.grasped_over_end else 'UNDER'} strand) "
                f"grasp_xy=({command.grasp_xy[0]:+.3f},{command.grasp_xy[1]:+.3f}) "
                f"place_xy=({command.place_xy[0]:+.3f},{command.place_xy[1]:+.3f}) "
                f"crossing_xy=({command.crossing_xy[0]:+.3f},{command.crossing_xy[1]:+.3f}) "
                f"arc_to_crossing={command.crossing_arc * 1000:.0f}mm "
                f"lift={(command.lift_z - rope_scene.layout.world_z(0.0)) * 1000:.0f}mm"
            )
            lift_ceiling = float(
                rope_scene.layout.world_z(float(cfg.common.manipulation_space.workspace.z[1]))
            )
            if command.lift_z > lift_ceiling:
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
            # is the rope's own direction at that end.
            heading = float(rope_scene.end_headings[command.end])
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

            def on_segment_start(_index, _count, label, _target):
                status["phase"] = label
                if label == "place_down":
                    lay_plug_flat()

            result = primitive.run(
                controller,
                handle=connector,
                ee_quat=ee_quat,
                on_close=engage_grasp_attachment,
                on_lift=pitch_nose_down,
                before_release=release_grasp_attachment,
                on_segment_start=on_segment_start,
                target_centers=[carry, place, settle_down],
                segment_labels=["carry_up", "cross_over", "place_down"],
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
            if rest_motion > float(cfg.task.settle.max_particle_step):
                print(
                    f"  WARNING rope still moving after {rest_steps} settle steps "
                    f"({rest_motion * 1000:.4f} mm/step > "
                    f"{float(cfg.task.settle.max_particle_step) * 1000:.4f}); "
                    "the reading below is measured on a moving rope"
                )

            state = evaluator.classify(rope_scene)
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

    print(
        f"band_untwist_result seed={cfg.run.seed} mode={cfg.run.oracle_mode} "
        f"terminal={state.is_terminal} moves={moves}/{budget} "
        f"final_self_crossings={state.crossing_count} ends_on_table={state.ends_on_table} "
        f"failure_label={state.failure_label}"
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
