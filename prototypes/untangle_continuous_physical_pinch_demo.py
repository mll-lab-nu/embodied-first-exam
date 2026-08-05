"""Continuous Untangle end to end: Franka grasps rope bodies and sorts the braid out.

The scene spawns a braid (topogym/generation/braid.py), settles it, then loops
plan -> grasp -> lift -> place -> re-measure until the geometric proxy says the
ropes are untangled and separated, or the move budget runs out.

Grasping is a kinematic weld of a band of PBD particles to the hand
(`PBDParticleAttachmentDragPrimitive`), not a friction pinch -- see the `pinch:`
block in the task config for why.

    # one move, to watch a single crossing come undone
    python -m prototypes.untangle_continuous_physical_pinch_demo --viewer --keep-open --max-moves 1 --verbose

    # the whole thing
    python -m prototypes.untangle_continuous_physical_pinch_demo --viewer --keep-open --verbose
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import add_common_config_arg, load_topogym_configs
from topogym.planning import plan_next_untangle_continuous_move
from topogym.primitives import (
    AttachmentManager,
    PBDHandleDragPrimitive,
    ee_quat_for_yaw,
    entity_pos,
    entity_quat,
    quat_about_axis,
    quat_mul,
)
from topogym.supervision import RopeTrace, rope_blow_ups
from topogym.supervision.untangle_continuous import crossing_lines, rope_health_lines
from topogym.tasks import UntangleContinuousSceneBuilder, settle_scene
from topogym.utils import (
    add_recording_args,
    initialize_franka_controller,
    merge_recording_config,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import UntangleContinuousPuzzleEvaluator, strand_polylines

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "configs"
DEFAULT_COMMON_CONFIG = CONFIG_ROOT / "common_configs" / "manipulation_space_tabletop_v1.yaml"
DEFAULT_ENV_CONFIG = CONFIG_ROOT / "env_configs" / "world_tabletop_v1.yaml"
DEFAULT_ROBOT_CONFIG = CONFIG_ROOT / "robot_control_configs" / "franka_panda_position_ik.yaml"
DEFAULT_TASK_CONFIG = CONFIG_ROOT / "task_configs" / "untangle_continuous_topogym_tabletop_v1.yaml"

# braid.length per difficulty bucket. `easy` is 1 because that is what the
# config baseline is (braid.length: 1) -- a bucket that silently disagreed
# with the config is how a run asked for one crossing and got three.
# Passing no --difficulty uses the config value; the other two buckets are
# deliberately harder scenes, kept for the benchmark difficulty axis.
_DIFFICULTY_LENGTH = {"easy": 1, "default": 3, "hard": 5}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Solve the continuous Untangle braid by physically grasping rope bodies."
    )
    parser.add_argument("--env-config", type=Path, default=DEFAULT_ENV_CONFIG)
    parser.add_argument("--robot-config", type=Path, default=DEFAULT_ROBOT_CONFIG)
    parser.add_argument("--task-config", type=Path, default=DEFAULT_TASK_CONFIG)
    add_common_config_arg(parser, default=DEFAULT_COMMON_CONFIG)
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), default="gpu")
    parser.add_argument("--seed", type=int, default=0, help="Braid layout seed.")
    parser.add_argument(
        "--difficulty",
        choices=tuple(_DIFFICULTY_LENGTH),
        default=None,
        help=(
            "Override braid.length: easy=1 (the config baseline), default=3, hard=5. "
            "Omit it to use the config value."
        ),
    )
    parser.add_argument(
        "--strands",
        type=int,
        default=None,
        help=(
            "Override braid.n_strands. Two ropes is now the config default -- one "
            "crossing needs exactly two strands, so a third adds particles and debug "
            "variables without adding task semantics. `--strands 3` gets it back."
        ),
    )
    parser.add_argument(
        "--max-moves",
        type=int,
        default=None,
        help="Stop after this many grasps (default: oracle.max_moves_per_crossing x crossings).",
    )
    parser.add_argument(
        "--segment-length",
        type=float,
        default=None,
        help=(
            "Override rope.mesh.segment_length (metres), the ring spacing along the "
            "rope. The contact sweep measured the settled centreline gap between two "
            "crossing ropes at 2.4mm with the 9mm default and 8.7mm at 4mm; 8mm is "
            "where the two tubes stop overlapping. Here so the two can be compared "
            "without editing the config."
        ),
    )
    parser.add_argument(
        "--rope-static-friction",
        type=float,
        default=None,
        help=(
            "Override rope.elastic.static_friction, the rope-to-rope tangential "
            "coefficient in the PBD contact solve. This task sets 0.05 against the "
            "prefab's 0.35, on the grounds that a higher value drags the strand "
            "underneath along. That reasoning predates the interpenetration fix -- "
            "the dragging was attributed to geometric interlock at 5.5mm of overlap, "
            "which no longer exists. Decides whether the upper rope is carried by the "
            "lower one or slides off it."
        ),
    )
    parser.add_argument(
        "--rope-kinetic-friction",
        type=float,
        default=None,
        help="Override rope.elastic.kinetic_friction. Prefab value is 0.25, this task uses 0.02.",
    )
    parser.add_argument(
        "--substeps",
        type=int,
        default=None,
        help=(
            "Override sim.substeps (default 4). Contact is solved once per substep and "
            "has no iteration count of its own, while stretch/bending/volume run 16/12/6 "
            "times per substep ahead of it. Raising this gives contact more passes per "
            "unit of gripper displacement; cost is proportional wall-clock time. "
            "DIAGNOSTIC ONLY: the frozen tabletop_v1 baseline pins substeps to 4, so "
            "this also sets env.preset.locked=false, which disables every other baseline "
            "check as well. Data recorded from such a run is off-baseline."
        ),
    )
    parser.add_argument(
        "--grasp-strand",
        type=int,
        default=None,
        help=(
            "Grasp this strand instead of whichever one the planner picks. Set it to "
            "the strand that is UNDERNEATH to run the contact test: dragging the lower "
            "rope cannot undo the crossing, so the one on top must stay on top for the "
            "whole move. Watch the over_z column -- its sign is the over/under "
            "relationship, and a sign flip means the ropes passed through each other. "
            "Strand order follows braid.strand_colors: 0=red, 1=green."
        ),
    )
    parser.add_argument("--viewer", action="store_true")
    parser.add_argument("--keep-open", action="store_true", help="Step forever when finished.")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--trace",
        type=Path,
        nargs="?",
        # Stamped, not a fixed name: `RopeTrace` opens with "w", so a fixed name
        # means every run destroys the previous one's evidence. The trace that
        # finally located this task's blow-up survived only by being copied out
        # by hand minutes before the next run would have overwritten it.
        const=Path(f"runs/untangle_continuous_trace_{datetime.now():%Y%m%d-%H%M%S}.log"),
        default=None,
        help=(
            "Stream per-step rope health to a file (default "
            "runs/untangle_continuous_trace_<timestamp>.log). Written flushed, so a solver "
            "crash still leaves the history; the lines before the EVENT marker are what "
            "identify a blow-up's cause."
        ),
    )
    parser.add_argument(
        "--trace-every",
        type=int,
        default=1,
        help="Sample the trace every N physics steps (1 = every step).",
    )
    add_recording_args(parser)
    return parser.parse_args()


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


def run_demo(args: argparse.Namespace, cfg) -> tuple[bool, object]:
    rope_scene = UntangleContinuousSceneBuilder(
        cfg.env,
        cfg.task,
        cfg.robot_control,
        seed=args.seed,
    ).build(show_viewer=args.viewer)
    controller = initialize_franka_controller(
        scene=rope_scene.scene,
        manifest=rope_scene.manifest,
        robot_cfg=cfg.robot_control,
    )

    pinch_cfg = cfg.task.pinch
    evaluator = UntangleContinuousPuzzleEvaluator.from_config(cfg.task)
    # The rigid-handle primitive the discrete Untangle and cable_routing already
    # use: the gripper physically closes on a rigid fitting (rigid-rigid contact,
    # solved properly) and the rope follows it through Genesis' native
    # particle-to-link attachment. Replaces this task's hand-rolled particle weld,
    # which held its band at fixed world-axis offsets and kinked the rope at the
    # band edge on every lift.
    primitive = PBDHandleDragPrimitive(
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
        verbose=args.verbose,
    )

    # Before anything moves: can the ropes satisfy PBD self-collision at all?
    # If not, they will never come to rest and every number below is downstream
    # of that -- worth seeing at the top of the log rather than inferring later.
    for line in rope_health_lines(rope_scene, particle_size=float(cfg.task.rope.particle_size)):
        print(line)

    settle_steps, moved = settle_scene(rope_scene)
    state = evaluator.classify(rope_scene)
    gt_ok, gt_detail = evaluator.matches_braid_ground_truth(rope_scene)
    braid_crossings = len(rope_scene.braid.crossings)
    budget = (
        int(args.max_moves)
        if args.max_moves is not None
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
    if args.trace is not None:
        trace = RopeTrace(
            rope_scene,
            args.trace,
            every=int(args.trace_every),
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
                    f"seed={args.seed} word={rope_scene.braid.word}",
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
        print(f"untangle_continuous_trace -> {args.trace}")

    print(
        f"untangle_continuous_start seed={args.seed} word={rope_scene.braid.word} "
        f"settle_steps={settle_steps} max_particle_step={moved:.6f} "
        f"crossings={state.crossing_count} gt_match={gt_ok} {gt_detail} budget={budget}"
    )
    if args.verbose:
        for line in crossing_lines(
                state,
                rope_radius=float(cfg.task.rope.radius),
                particle_size=float(cfg.task.rope.particle_size),
            ):
            print(line)

    moves = 0
    with recording_session_from_config(
        rope_scene.scene,
        rope_scene.cameras,
        cfg.recording,
        hud=_hud(status),
    ), AttachmentManager(rope_scene.scene) as attachment_manager:
        while moves < budget:
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
                grasp_strand=args.grasp_strand,
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
                # `PBDHandleDragPrimitive` calls this as
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
            if args.verbose:
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
        f"untangle_continuous_result seed={args.seed} terminal={state.is_terminal} "
        f"moves={moves} braid_crossings={braid_crossings} "
        f"moves_per_crossing={efficiency:.2f} "
        f"final_crossings={state.crossing_count} "
        f"min_sep={state.min_separation * 1000:.1f}mm"
    )
    if trace is not None:
        trace.close()
    print_recording_saved(cfg.recording)
    return bool(state.is_terminal), rope_scene


def main() -> None:
    args = parse_args()
    cfg = load_topogym_configs(
        common_config=args.common_config,
        env_config=args.env_config,
        robot_config=args.robot_config,
        task_config=args.task_config,
    )
    if args.difficulty is not None:
        cfg = OmegaConf.merge(
            cfg, {"task": {"braid": {"length": _DIFFICULTY_LENGTH[args.difficulty]}}}
        )
    if args.strands is not None:
        cfg = OmegaConf.merge(
            cfg, {"task": {"braid": {"n_strands": args.strands}}}
        )
    if args.segment_length is not None:
        cfg = OmegaConf.merge(
            cfg, {"task": {"rope": {"mesh": {"segment_length": args.segment_length}}}}
        )
    if args.rope_static_friction is not None:
        cfg = OmegaConf.merge(
            cfg, {"task": {"rope": {"elastic": {"static_friction": args.rope_static_friction}}}}
        )
    if args.rope_kinetic_friction is not None:
        cfg = OmegaConf.merge(
            cfg, {"task": {"rope": {"elastic": {"kinetic_friction": args.rope_kinetic_friction}}}}
        )
    if args.substeps is not None:
        # `_validate_locked_preset` pins substeps to 4 for topogym_tabletop_v1, and it
        # only runs when preset.locked is set, so unlocking is the only way through.
        # That switches off the table AABB, robot home pose and camera checks too.
        print(
            f"untangle_continuous WARNING: sim.substeps={args.substeps} requires "
            "env.preset.locked=false, which disables the whole frozen-baseline check. "
            "Diagnostic run only; do not record a dataset from it.",
            flush=True,
        )
        cfg = OmegaConf.merge(
            cfg,
            {"env": {"sim": {"substeps": args.substeps}, "preset": {"locked": False}}},
        )
    cfg = merge_recording_config(cfg, args)
    cfg = OmegaConf.merge(cfg, {"env": {"genesis": {"backend": args.backend}}})
    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[cfg.env.genesis.backend])

    solved, rope_scene = run_demo(args, cfg)

    if args.keep_open or args.viewer:
        print("untangle_continuous holding the viewer open; Ctrl+C to exit.")
        while True:
            rope_scene.scene.step()
    raise SystemExit(0 if solved else 1)


if __name__ == "__main__":
    main()
