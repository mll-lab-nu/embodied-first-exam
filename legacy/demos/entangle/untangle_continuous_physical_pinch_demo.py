"""Continuous Untangle end to end: Franka grasps rope bodies and sorts the braid out.

The scene spawns a braid (topogym/generation/braid.py), settles it, then loops
plan -> grasp -> lift -> place -> re-measure until the geometric proxy says the
ropes are untangled and separated, or the move budget runs out.

The gripper closes on a rigid fitting welded to each rope's free end; the rope
follows the fitting through the backend's own link attachment. See the `pinch:`
block in the task config for why it is not a friction pinch.

Configuration is Hydra (`configs/untangle_continuous_pinch.yaml`): every scene and
physics value is a config path, and `run.*` carries the run-mode switches.

    # one move, to watch a single crossing come undone
    python -m demos.entangle.untangle_continuous_physical_pinch_demo run.viewer=true run.keep_open=true run.max_moves=1 run.verbose=true

    # the contact test: drag the LOWER strand, watch the trace's over_z sign
    python -m demos.entangle.untangle_continuous_physical_pinch_demo run.grasp_strand=1 run.max_moves=1 run.trace=auto

    # print the resolved config and exit
    python -m demos.entangle.untangle_continuous_physical_pinch_demo --cfg job
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.planning import plan_next_untangle_continuous_move
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
from topogym.supervision.untangle_continuous import crossing_lines, rope_health_lines
from topogym.tasks_legacy import UntangleContinuousSceneBuilder, settle_scene
from topogym.utils import (
    apply_recording_camera_overrides,
    initialize_franka_controller,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import UntangleContinuousPuzzleEvaluator, strand_polylines

CONFIG_ROOT = Path(__file__).resolve().parents[2] / "configs"


def _hud(status: dict):
    def render() -> list[str]:
        return [
            "task: untangle_continuous",
            f"move: {status.get('move', 0)}/{status.get('budget', 0)}",
            f"crossings: {status.get('crossings', '?')} (gt {status.get('gt', '?')})",
            f"min_sep: {status.get('min_sep', 0.0) * 1000:.0f}mm",
            f"terminal={status.get('terminal', False)}",
        ]

    return render


def _connector_report(rope_scene, tag: str) -> None:
    """Where each free-end plug actually is. Spawn lanes are y=+-42.5mm; a plug
    that has wandered off its lane drags the rope's follow band with it, so
    localizing WHEN the wander happens is the whole diagnosis."""

    for strand, connector in sorted(rope_scene.free_end_connectors.items()):
        pos = np.asarray(entity_pos(connector), dtype=float)
        print(
            f"connector_probe [{tag}] s{strand}: "
            f"xy=({pos[0] * 1000:+.1f},{pos[1] * 1000:+.1f})mm z={pos[2] * 1000:.1f}mm",
            flush=True,
        )


def run_demo(cfg: DictConfig) -> tuple[bool, object]:
    rope_scene = UntangleContinuousSceneBuilder(
        cfg.env,
        cfg.task,
        cfg.robot_control,
        seed=cfg.run.seed,
    ).build(show_viewer=cfg.run.viewer)
    _connector_report(rope_scene, "post_build")
    # Park each plug at its spawn pose until the gripper takes it. Lying on its
    # flange rim the plug is a wheel -- in the FEM scene it rolls ~20mm inward
    # during the first ~90 steps (probe 2026-08-07; mechanism unidentified, ruled
    # out: rope pull, follow band, substeps, IPC contact -- the plug is in none
    # of them). The task's design wants the plug graspable where it spawned; the
    # park is the same kind of assist as the grasp weld itself.
    parked: dict[int, tuple] = {
        strand: (
            connector,
            np.asarray(entity_pos(connector), dtype=float).copy(),
            np.asarray(entity_quat(connector), dtype=float).copy(),
        )
        for strand, connector in rope_scene.free_end_connectors.items()
    }

    _original_step = rope_scene.scene.step

    def _step_with_parked_plugs(*step_args, **step_kwargs):
        for _strand, (connector, pos, quat) in parked.items():
            connector.set_pos(tuple(pos), zero_velocity=True)
            connector.set_quat(tuple(quat), zero_velocity=True)
        return _original_step(*step_args, **step_kwargs)

    rope_scene.scene.step = _step_with_parked_plugs

    def unpark_connector(strand: int) -> None:
        parked.pop(int(strand), None)

    if cfg.run.connector_probe_steps:
        # Diagnostic: place the arm at home without the usual settle, then step
        # manually and sample the plug positions -- the drift CURVE (constant
        # velocity vs diffusion vs single hop) discriminates mechanism classes
        # in a way the endpoint numbers cannot.
        controller = initialize_franka_controller(
            scene=rope_scene.scene,
            manifest=rope_scene.manifest,
            robot_cfg=cfg.robot_control,
            settle_steps=0,
        )
        for probe_step in range(1, int(cfg.run.connector_probe_steps) + 1):
            rope_scene.scene.step()
            if probe_step % 10 == 0 or probe_step == 1:
                _connector_report(rope_scene, f"home_step{probe_step:03d}")
    else:
        controller = initialize_franka_controller(
            scene=rope_scene.scene,
            manifest=rope_scene.manifest,
            robot_cfg=cfg.robot_control,
        )
    _connector_report(rope_scene, "post_home_settle")

    pinch_cfg = cfg.task.pinch
    evaluator = UntangleContinuousPuzzleEvaluator.from_config(cfg.task)
    # The rigid-handle primitive the discrete Untangle and cable_routing already
    # use: the gripper physically closes on a rigid fitting (rigid-rigid contact,
    # solved properly) and the rope follows it through Genesis' native
    # particle-to-link attachment. Replaces this task's hand-rolled particle weld,
    # which held its band at fixed world-axis offsets and kinked the rope at the
    # band edge on every lift.
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

    # Before anything moves: can the ropes satisfy PBD self-collision at all?
    # If not, they will never come to rest and every number below is downstream
    # of that -- worth seeing at the top of the log rather than inferring later.
    for line in rope_health_lines(rope_scene, particle_size=float(cfg.task.rope.particle_size)):
        print(line)

    settle_steps, moved = settle_scene(rope_scene)
    _connector_report(rope_scene, "post_settle")
    state = evaluator.classify(rope_scene)
    gt_ok, gt_detail = evaluator.matches_braid_ground_truth(rope_scene)
    braid_crossings = len(rope_scene.braid.crossings)
    budget = (
        int(cfg.run.max_moves)
        if cfg.run.max_moves is not None
        else int(cfg.task.oracle.max_moves_per_crossing) * max(1, braid_crossings)
    )
    status = {
        "move": 0,
        "budget": budget,
        "crossings": state.crossing_count,
        "gt": braid_crossings,
        "min_sep": state.min_separation,
        "terminal": state.is_terminal,
    }
    trace = None
    if cfg.run.trace is not None:
        # "auto" produces a stamped name. A fixed name would be worse than no
        # trace: `RopeTrace` opens with "w", so every run would destroy the
        # previous one's evidence.
        trace_path = (
            Path(f"runs/untangle_continuous_trace_{datetime.now():%Y%m%d-%H%M%S}.log")
            if str(cfg.run.trace) == "auto"
            else Path(str(cfg.run.trace))
        )
        trace = RopeTrace(
            rope_scene,
            trace_path,
            every=int(cfg.run.trace_every),
            offset_tolerance=float(pinch_cfg.blow_up_tolerance),
            # Both ends are held over this radius: the anchored end by
            # `fix_particles`, the free end by `fix_particles_to_link`. Tells the
            # trace how much of each end to drop for the `bend_free` column.
            fixed_band=float(cfg.task.rope.anchor_radius),
            rope_radius=float(cfg.task.rope.radius),
            particle_size=float(cfg.task.rope.particle_size),
            status=status,
            # Recorded in the trace header: every one of these has been the
            # culprit at least once, so a trace without them is ambiguous.
            notes="\n".join(
                (
                    f"seed={cfg.run.seed} word={rope_scene.braid.word}",
                    f"segment_length={float(cfg.task.rope.mesh.segment_length)} "
                    f"radial_segments={int(cfg.task.rope.mesh.radial_segments)} "
                    f"particle_size={float(cfg.task.rope.particle_size)} "
                    f"radius={float(cfg.task.rope.radius)}",
                    f"tabletop_friction={bool(cfg.task.rope.tabletop_friction.enabled)} "
                    f"damp_every={int(cfg.task.settle.damp_every)}",
                    # Every value a CLI override can change has to appear here.
                    # A run whose flags silently did not apply looks identical to
                    # one whose flags did, and that costs a whole GPU run to notice.
                    f"rope_static_friction={float(cfg.task.rope.elastic.static_friction)} "
                    f"rope_kinetic_friction={float(cfg.task.rope.elastic.kinetic_friction)} "
                    f"substeps={int(cfg.env.sim.substeps)} "
                    f"preset_locked={bool(cfg.env.preset.locked)}",
                    # FEM 后端的材料与接触参数（2026-08-10 从 Python 常量搬进配置）。
                    f"rope_model={str(cfg.task.rope.model)} "
                    + " ".join(
                        f"fem.{key}={float(cfg.task.rope.fem[key])}"
                        for key in ("E", "nu", "rho", "friction_mu",
                                    "contact_d_hat", "follow_strength")
                    ),
                    # Which strand the detector says is on top, and whether that
                    # agrees with the braid the scene was generated from. The
                    # detector reads centreline z at the crossing, so with tubes
                    # that overlap it is deciding on a fraction of a rope radius.
                    f"detector vs braid ground truth: {'match' if gt_ok else 'MISMATCH'} "
                    f"({gt_detail})",
                    "measured crossings: "
                    + "; ".join(
                        f"s{c.over_strand} over s{c.under_strand} "
                        f"z_gap={c.z_gap * 1000:.1f}mm"
                        for c in state.crossings
                    ),
                    f"grasp_half_width={float(pinch_cfg.grasp_half_width)} "
                    f"grasp_taper={float(pinch_cfg.grasp_taper)} "
                    f"anchor_radius={float(cfg.task.rope.anchor_radius)}",
                )
            ),
        )
        print(f"untangle_continuous_trace -> {trace_path}")

    print(
        f"untangle_continuous_start seed={cfg.run.seed} word={rope_scene.braid.word} "
        f"settle_steps={settle_steps} max_particle_step={moved:.6f} "
        f"crossings={state.crossing_count} gt_match={gt_ok} {gt_detail} budget={budget}"
    )
    if cfg.run.verbose:
        for line in crossing_lines(
                state,
                rope_radius=float(cfg.task.rope.radius),
                particle_size=float(cfg.task.rope.particle_size),
            ):
            print(line)

    moves = 0
    if stop_before_physics(cfg, rope_scene.scene, "untangle_continuous_physical_pinch_demo"):
        raise SystemExit(0)

    with recording_session_from_config(
        rope_scene.scene,
        rope_scene.cameras,
        cfg.recording,
        hud=_hud(status),
    ), AttachmentManager(rope_scene.scene) as attachment_manager:
        while moves < budget:
            _connector_report(rope_scene, f"pre_plan_move{moves + 1}")
            polylines = strand_polylines(rope_scene, samples=evaluator.samples)
            planned = plan_next_untangle_continuous_move(
                rope_scene,
                state,
                polylines,
                lift_clearance=float(pinch_cfg.lift_clearance),
                grasp_offset=float(pinch_cfg.grasp_offset),
                place_pullback=float(pinch_cfg.place_pullback),
                tail_clearance=float(pinch_cfg.tail_clearance),
                max_taut_ratio=float(pinch_cfg.max_taut_ratio),
                lane_overshoot=float(pinch_cfg.lane_overshoot),
                grasp_strand=cfg.run.grasp_strand,
            )
            if planned is None:
                break
            command, _plan = planned
            connector = rope_scene.free_end_connectors[command.strand_index]
            # Straight from the planner: it clamps each target to what the rope can
            # reach, so rebuilding them here from grasp_xy/place_xy would silently
            # undo the clamp.
            carry = np.asarray(command.carry, dtype=float)
            place = np.asarray(command.cross, dtype=float)
            settle_down = np.asarray(command.settle, dtype=float)
            print(
                f"untangle_continuous_move {moves + 1}/{budget} strand={command.strand_index} "
                f"over strand={command.under_strand} "
                f"grasp_xy=({command.grasp_xy[0]:+.3f},{command.grasp_xy[1]:+.3f}) "
                f"place_xy=({command.place_xy[0]:+.3f},{command.place_xy[1]:+.3f}) "
                f"z_gap={command.crossing_z_gap * 1000:.1f}mm "
                f"tail_arc={command.tail_arc * 1000:.0f}mm "
                f"crossing_arc={command.crossing_arc * 1000:.0f}mm "
                f"lift={(command.lift_z - rope_scene.layout.world_z(0.0)) * 1000:.0f}mm "
                f"pulled_back={(command.grasp_xy[0] - command.carry[0]) * 1000:.0f}mm"
            )

            # The over/under call is a measurement of centreline z at the
            # crossing. When the tubes overlap, that measurement is deciding on a
            # fraction of a rope radius, and the whole plan hangs off it: the
            # grasped strand is the one the detector called "over".
            resting_gap = 2 * float(cfg.task.rope.radius) + float(cfg.task.rope.particle_size)
            if command.crossing_z_gap < 0.5 * resting_gap:
                unreliable = (
                    f"over/under decided on {command.crossing_z_gap * 1000:.1f}mm of centreline "
                    f"separation, less than half the {resting_gap * 1000:.0f}mm the two tubes "
                    f"should rest at -- the tubes overlap, so which one is on top is within "
                    f"measurement noise"
                )
                print(f"untangle_continuous WARNING: {unreliable}", flush=True)
                if trace is not None:
                    trace.note(f"WARN {unreliable}")

            status["phase"] = f"move{moves + 1}_grasp"
            if trace is not None:
                trace.note(
                    f"move {moves + 1}: grasping s{command.strand_index} "
                    f"(over s{command.under_strand}, centreline gap "
                    f"{command.crossing_z_gap * 1000:.1f}mm of a possible "
                    f"{(2 * float(cfg.task.rope.radius) + float(cfg.task.rope.particle_size)) * 1000:.0f}mm) "
                    f"by its free-end connector (arclength "
                    f"{command.grasp_arclength:.2f}, tail past the grip "
                    f"{command.tail_arc * 1000:.0f}mm) "
                    f"(compare against the bend_at column)"
                )
            # Yaw the wrist so the finger pads do not flank the plug along its own
            # axis -- that is the direction the cable drapes away in, and a pad
            # sitting over it hooks the rope on release. Same convention, and the
            # same `ee_quat_for_yaw` call, as the discrete variant.
            plug_axis = polylines[command.strand_index][-1] - polylines[command.strand_index][-6]
            ee_quat = ee_quat_for_yaw(
                controller.default_ee_quat,
                float(np.arctan2(plug_axis[1], plug_axis[0])),
            )
            pitch_angle = np.radians(float(pinch_cfg.carry_pitch_deg))
            pitch_steps = int(pinch_cfg.carry_pitch_steps)

            # Assisted grasp, engaged the instant the fingers close and *before*
            # the primitive's lift check. Without it the lift is asked to run on
            # bare friction, and there is none to run on: `grasp_qpos_handle`
            # equals the grasp column's radius, so the pads close to exactly the
            # surface with zero preload. That is deliberate and shared with the
            # other two tasks that grasp this same plug -- both of them hand the
            # part to an attachment here, so the fingers only ever have to *look*
            # like they are holding it. This demo was the one that did not, which
            # is why the arm closed on the plug and then left it on the table.
            held: list = []
            flat_quat: list = []

            def engage_grasp_attachment(_connector=connector):
                # Weld honesty check: the attachment succeeds no matter where the
                # hand actually is (assist masks placement error by design), so
                # verify the plug really is between the pads before welding.
                # Measured failure mode: a 9.5mm planner drift walked the hand in
                # between the two plugs, the fingers closed on air, and the weld
                # carried the rope anyway.
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
                # The hand has it now; stop holding it at its spawn pose.
                unpark_connector(command.strand_index)
                # Hand over the plug's *actual* orientation. Without this the
                # attachment holds a yaw-only pose, which for a plug lying flat
                # means snapping it upright in one step -- and the rope particles
                # welded to its link get dragged through that 90 degrees with it.
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
                # The plug is held with its axis horizontal and its cap (where the
                # cable leaves) pointing back at the anchor. A slack rope hangs
                # vertically from whatever holds it, so that cap is a ~90 degree
                # corner in the few mm of rope right outside the weld band -- which
                # is where every blow-up in this task's log has started. Turning the
                # plug so the cap points *down* puts the outlet along the direction
                # the rope is going anyway.
                #
                # The wrist deliberately does not follow. The plug's pose is written
                # by the attachment every step and the pads hold it with zero
                # preload (`grasp_qpos_handle` == the column radius), so this is the
                # only thing that decides where it points; making the wrist track it
                # would mean per-segment orientations in the shared primitive and a
                # large wrist pitch to reach. Pads flanking a solid of revolution
                # permit exactly this rotation, so it is consistent, if bare-looking.
                if not held or pitch_angle == 0.0:
                    return
                axis = np.cross(_axis / np.linalg.norm(_axis), np.array([0.0, 0.0, 1.0]))
                target = quat_mul(quat_about_axis(axis, pitch_angle), flat_quat[0])
                held[0].ramp_to(target, pitch_steps)
                if trace is not None:
                    trace.note(
                        f"lift_test starting ({lift_steps} steps); rotating the plug "
                        f"{np.degrees(pitch_angle):.0f} deg so its outlet faces down, "
                        f"over {pitch_steps} sync calls"
                    )

            def lay_plug_flat():
                # Back to the pose it was picked up in, or it lands on its nose.
                if not held or pitch_angle == 0.0:
                    return
                held[0].ramp_to(flat_quat[0], pitch_steps)

            def release_grasp_attachment(_pre_release_pos=None, _final_target=None):
                # `HandleDragPrimitive` calls this as
                # `before_release(pre_release_pos, final_target)` and reads the
                # return value as "did something else take the handle over".
                # Nothing does here -- the plug is simply handed back to the
                # solver -- so the two arguments are unused and the answer is no.
                # The demo also calls this with no arguments on the failure path.
                attachment = held.pop()
                if attachment.ramping():
                    print(
                        "untangle_continuous WARNING: released mid-pitch -- the plug is still "
                        "turning and will land off-pose. Raise pinch.carry_pitch_steps' headroom "
                        "or start the lay-flat ramp earlier."
                    )
                attachment.release(sync=False)
                attachment_manager.attachments.remove(attachment)
                if trace is not None:
                    trace.note("attachment released; the plug's pose is now solver-driven")
                return False

            def on_segment_start(_index, _count, label, _target):
                status["phase"] = f"move{moves + 1}_{label}"
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

            # Settle to rest, not for a fixed count. A rope that was just lifted,
            # carried sideways and put down is a pendulum anchored at one end, and
            # these ropes have almost no damping -- a fixed 120 steps (1.2 s) is
            # nowhere near enough. Measuring crossings on a still-swinging rope
            # gives an unreliable count *and* sends the next grasp to a stale
            # position, so reuse the same convergence logic (and velocity damping)
            # the spawn settle uses. Not strict here: failing to converge makes the
            # reading suspect, which is worth saying loudly, but not worth killing
            # a half-finished episode over.
            status["phase"] = f"move{moves + 1}_settle"
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
                    "crossing count below is measured on a moving rope"
                )
            state = evaluator.classify(rope_scene)
            status.update(
                move=moves,
                crossings=state.crossing_count,
                min_sep=state.min_separation,
                terminal=state.is_terminal,
            )
            print(
                f"untangle_continuous_after_move {moves} success={result.success} "
                f"grasped={result.grasped} reason={result.failure_reason} "
                f"crossings={command.crossing_count_before}->{state.crossing_count} "
                f"min_sep={state.min_separation * 1000:.1f}mm terminal={state.is_terminal}"
            )
            # Say which rope tore and at what point along it, rather than leaving
            # it to be guessed from a viewer full of stretched triangles. s near
            # the grasp arclength means the weld band is the culprit; s near 0
            # means the anchor.
            if cfg.run.verbose:
                for line in crossing_lines(
                state,
                rope_radius=float(cfg.task.rope.radius),
                particle_size=float(cfg.task.rope.particle_size),
            ):
                    print(line)
            for blow_up in rope_blow_ups(rope_scene, tolerance=float(pinch_cfg.blow_up_tolerance)):
                print(
                    f"  BLOW-UP {blow_up} (grasped strand={command.strand_index} "
                    f"at s={command.grasp_arclength:.2f})"
                )
            if state.is_terminal:
                break

    efficiency = (moves / braid_crossings) if braid_crossings else float("nan")
    print(
        f"untangle_continuous_result seed={cfg.run.seed} terminal={state.is_terminal} "
        f"moves={moves} braid_crossings={braid_crossings} "
        f"moves_per_crossing={efficiency:.2f} "
        f"final_crossings={state.crossing_count} "
        f"min_sep={state.min_separation * 1000:.1f}mm"
    )
    if trace is not None:
        trace.close()
    print_recording_saved(cfg.recording)
    return bool(state.is_terminal), rope_scene

@hydra.main(version_base="1.3", config_path="../../configs", config_name="untangle_continuous_pinch")
def main(cfg: DictConfig) -> None:
    # Every override this demo used to spell out as a flag is now a config path.
    # The eleven hand-written `OmegaConf.merge` blocks that used to live here are
    # gone; Hydra applies `key=value` from the command line, and writes both the
    # resolved config and the overrides into the run's output directory, so
    # "did that flag take effect" stops being unanswerable after the fact.
    #
    #   task.rope.mesh.segment_length=0.004
    #   task.rope.fem.E=200000.0
    #   task.rope.elastic.static_friction=0.35
    #   task.rope.model=fem_ipc_tube
    #   task.rope.free_end_connector.follow_enabled=false
    #   task.braid.n_strands=2   task.braid.length=3
    #   env.genesis.backend=cpu
    #   run.viewer=true   run.grasp_strand=1   run.trace=auto

    # `recording.res` resizes cameras, so it has to be applied before the build.
    cfg = apply_recording_camera_overrides(cfg)

    # Alongside Hydra's own snapshot, one with the interpolations expanded -- see
    # `save_resolved_config` for why the reference-preserving form is not enough.
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"untangle_continuous_config -> {resolved}", flush=True)

    # The frozen baseline pins sim.substeps to 4 and only checks when
    # env.preset.locked is set, so raising substeps needs both overrides. Say which
    # one rather than leaving the validator's message as the whole explanation.
    if int(cfg.env.sim.substeps) != 4 and bool(cfg.env.preset.locked):
        print(
            f"untangle_continuous: env.sim.substeps={int(cfg.env.sim.substeps)} is pinned "
            "to 4 by the frozen topogym_tabletop_v1 baseline. Add env.preset.locked=false "
            "to get past it -- that disables every other baseline check as well, so the "
            "run is off-baseline and must not be recorded as a dataset.",
            flush=True,
        )

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)])

    solved, rope_scene = run_demo(cfg)

    if cfg.run.keep_open or cfg.run.viewer:
        print("untangle_continuous holding the viewer open; Ctrl+C to exit.")
        while True:
            rope_scene.scene.step()
    raise SystemExit(0 if solved else 1)


if __name__ == "__main__":
    main()
