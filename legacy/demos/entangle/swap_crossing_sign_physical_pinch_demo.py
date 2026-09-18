"""swap_crossing_sign (docx 3.2) end to end: at every crossing, the other cable on top.

2 or 3 cables anchored in a power strip cross 1 or 2 times. The episode has to
end with every spawn crossing still there and the other cable on top of it
(judged on the end state). With one arm the rope placed last is the rope on top,
so the oracle takes 2-5 grasp-lift-lay moves in an order the geometry forces:
it re-plans from the measured ropes before every move and executes the first
move of the plan (`topogym/planning/swap_crossing_sign_planner.py`). The start
line prints the whole planned sequence (``planned=[...]``); the result line
carries a failure label (unchanged / partial_flip / extra_crossing /
missing_crossing / reordered).

The gripper closes on a rigid fitting welded to each rope's free end; the rope
follows the fitting through the backend's own link attachment. See the `pinch:`
block in the task config for why it is not a friction pinch.

    # the oracle, with a video
    python -m demos.entangle.swap_crossing_sign_physical_pinch_demo run.verbose=true recording=default

    # contrasts: take everything apart and rebuild the spawn (judged `unchanged`);
    # flip only the crossing nearest the plugs (`partial_flip` on two crossings)
    python -m demos.entangle.swap_crossing_sign_physical_pinch_demo run.oracle_mode=restack_same run.verbose=true
    python -m demos.entangle.swap_crossing_sign_physical_pinch_demo run.oracle_mode=flip_nearest task.braid.length=2

    # watch it in the viewer, one move at a time
    python -m demos.entangle.swap_crossing_sign_physical_pinch_demo run.viewer=true run.keep_open=true run.max_moves=1 run.verbose=true

    # a seeded variant of the layout (task yaml's variation block)
    python -m demos.entangle.swap_crossing_sign_physical_pinch_demo run.randomize_layout=true run.seed=3

    # print the resolved config and exit
    python -m demos.entangle.swap_crossing_sign_physical_pinch_demo --cfg job
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
from topogym.planning import make_swap_crossing_sign_rule
from topogym.planning.rope_crossings import code_text
from topogym.planning.swap_crossing_sign_sequence import params_from_config
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
from topogym.tasks_legacy import SwapCrossingSignSceneBuilder, settle_scene
from topogym.utils import (
    apply_recording_camera_overrides,
    initialize_franka_controller,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import SwapCrossingSignPuzzleEvaluator, strand_polylines

CONFIG_ROOT = Path(__file__).resolve().parents[2] / "configs"
TASK_ID = "swap_crossing_sign"


def _variant_line(cfg, layout) -> str:
    """One parseable line with every sampled leaf (the variation sweep script reads it)."""
    braid = cfg.task.braid
    if layout.crossed_pair:
        # This cell is built from its own block (one rope straight out of the strip,
        # two crossing it), so the braid leaves would describe ropes nobody built.
        cp = cfg.task.crossed_pair
        plan = layout.spawn_plan
        return (
            f"{TASK_ID} variant seed={int(cfg.run.seed)} ropes=3 crossings=2 build=crossed_pair "
            f"cross_x={float(cp.cross_x_1):+.3f}/{float(cp.cross_x_2):+.3f} "
            f"anchor_dy={float(cp.anchor_dy_1):+.3f}/{float(cp.anchor_dy_2):+.3f} "
            f"turn_x={float(cp.turn_x_1):+.3f}/{float(cp.turn_x_2):+.3f} "
            f"tail={float(cp.tail_1):.3f}/{float(cp.tail_2):.3f} cy={float(cp.center_y):+.4f} "
            f"x_end={float(braid.x_end):.4f} planned_moves={'none' if plan is None else len(plan.moves)} "
            f"lift_pred={layout.predicted_lift():.3f}"
        )
    fracs = "/".join(f"{f:.3f}" for f in layout.crossing_fractions())
    bows = "/".join(f"{b * 1000:+.0f}" for b in layout.bows())
    plan = layout.spawn_plan
    return (
        f"{TASK_ID} variant seed={int(cfg.run.seed)} ropes={layout.n_strands} crossings={layout.length} "
        f"word={','.join(f'{w:+d}' for w in layout.word)} frac={fracs} window_u={float(braid.window_u):.3f} "
        f"bows_mm={bows} spacing={float(braid.channel_spacing):.4f} cy={float(braid.center_y):+.4f} "
        f"x_end={float(braid.x_end):.4f} planned_moves={'none' if plan is None else len(plan.moves)} "
        f"lift_pred={layout.predicted_lift():.3f}"
    )


def _plan_text(plan) -> str:
    """``s<rope>:hang<mm>[(pinned)]-><landing>`` per move, as the start and move lines print it."""

    return "none" if plan is None else " | ".join(
        f"s{m.strand}:hang{m.hang * 1000:.0f}{'(pinned)' if m.pinned_at is not None else ''}"
        f"->({m.land_xy[0]:+.3f},{m.land_xy[1]:+.3f})"
        for m in plan.moves
    )


def _checks_line(layout) -> str:
    return " ".join(
        f"{name}={measured:+.4f}/{limit:+.4f}/{'ok' if ok else 'FAIL'}"
        for name, measured, limit, ok in layout.checks()
    )


def _closest_approach(polylines: dict) -> str:
    """Where two centrelines come closest: xy, and how far along each rope.

    `min_sep` alone says *that* ropes touch; this says *where*, which is what
    tells a bow in a laid rope apart from a dragged tail (2026-09-06 variation
    sweep: three cells stopped with min_sep 9.7 mm after separate). Every pair.
    """

    strands = sorted(polylines)
    best = None
    for k, sa in enumerate(strands):
        for sb in strands[k + 1:]:
            a, b = polylines[sa], polylines[sb]
            distance = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
            i, j = np.unravel_index(int(np.argmin(distance)), distance.shape)
            if best is None or distance[i, j] < best[0]:
                best = (float(distance[i, j]), sa, sb, i, j, a, b)
    if best is None:
        return ""
    _d, sa, sb, i, j, a, b = best
    return (
        f"closest s{sa}[{i}/{len(a) - 1}]=({a[i, 0]:+.3f},{a[i, 1]:+.3f}) "
        f"s{sb}[{j}/{len(b) - 1}]=({b[j, 0]:+.3f},{b[j, 1]:+.3f})"
    )


def _hud(status: dict):
    def render() -> list[str]:
        return [
            "task: swap_crossing_sign",
            f"phase: {status.get('phase', '?')}",
            f"move: {status.get('move', 0)}/{status.get('budget', 0)}",
            f"crossings: {status.get('crossings', '?')}",
            f"now: {status.get('signature', '?')}",
            f"start: {status.get('initial', '?')}",
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
    rope_scene = SwapCrossingSignSceneBuilder(
        cfg.env,
        cfg.task,
        cfg.robot_control,
        seed=cfg.run.seed,
    ).build(show_viewer=cfg.run.viewer)
    print(f"{TASK_ID} checks {_checks_line(rope_scene.layout)}", flush=True)
    if cfg.run.randomize_layout:
        print(_variant_line(cfg, rope_scene.layout), flush=True)
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

    controller = initialize_franka_controller(
        scene=rope_scene.scene,
        manifest=rope_scene.manifest,
        robot_cfg=cfg.robot_control,
    )
    _connector_report(rope_scene, "post_home_settle")

    pinch_cfg = cfg.task.pinch
    evaluator = SwapCrossingSignPuzzleEvaluator.from_config(cfg.task)
    rule = make_swap_crossing_sign_rule(str(cfg.run.oracle_mode))
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

    # Before anything moves: can the ropes satisfy self-collision at all? If not,
    # they will never come to rest and every number below is downstream of that.
    for line in rope_health_lines(rope_scene, particle_size=float(cfg.task.rope.particle_size)):
        print(line)

    settle_steps, moved = settle_scene(rope_scene)
    _connector_report(rope_scene, "post_settle")

    # The code the episode has to flip away from. Captured once, here, on the
    # settled spawn -- not read from the braid word. The braid says what was
    # generated; this says what the detector sees, and the detector is what
    # grades the end state, so both ends of the comparison come from the same
    # instrument.
    spawn_code = evaluator.capture_spawn_code(rope_scene)
    state = evaluator.classify(rope_scene, spawn_code=spawn_code)
    gt_ok, gt_detail = evaluator.matches_braid_ground_truth(rope_scene)
    params = params_from_config(cfg.task)
    # restack_same first takes every crossing away, then rebuilds the spawn.
    cleared = False
    spawn_plan = rule.plan(
        rope_scene, strand_polylines(rope_scene, samples=evaluator.samples),
        spawn_code=spawn_code, cleared=cleared, params=params,
    )
    planned_moves = None if spawn_plan is None else len(spawn_plan.moves)
    if rule.mode == "restack_same" and spawn_plan is not None:
        # take apart, then rebuild; re-budgeted from the rebuild's own plan once apart
        planned_moves = len(spawn_plan.moves) + len(spawn_plan.moves)
    # One move beyond the plan: a move the physics resolves differently gets one re-plan.
    budget_cap = int(cfg.task.oracle.max_moves) + (4 if rule.mode == "restack_same" else 0)
    budget = int(cfg.run.max_moves) if cfg.run.max_moves is not None else min(budget_cap, (planned_moves or 0) + 1)
    status = {
        "phase": "settled",
        "move": 0,
        "budget": budget,
        "crossings": state.crossing_count,
        "signature": code_text(state.code),
        "initial": code_text(spawn_code),
        "terminal": state.is_terminal,
    }
    trace = None
    if cfg.run.trace is not None:
        # "auto" produces a stamped name. A fixed name would be worse than no
        # trace: `RopeTrace` opens with "w", so every run would destroy the
        # previous one's evidence.
        trace_path = (
            Path(f"runs/swap_crossing_sign_trace_{datetime.now():%Y%m%d-%H%M%S}.log")
            if str(cfg.run.trace) == "auto"
            else Path(str(cfg.run.trace))
        )
        trace = RopeTrace(
            rope_scene,
            trace_path,
            every=int(cfg.run.trace_every),
            offset_tolerance=float(pinch_cfg.blow_up_tolerance),
            # Both ends are held over this radius: the anchored end by
            # `fix_particles`, the free end by `fix_particles_to_link`.
            fixed_band=float(cfg.task.rope.anchor_radius),
            rope_radius=float(cfg.task.rope.radius),
            particle_size=float(cfg.task.rope.particle_size),
            status=status,
            notes="\n".join(
                (
                    f"oracle_mode={str(cfg.run.oracle_mode)} seed={cfg.run.seed} "
                    f"word={rope_scene.braid.word}",
                    f"spawn_code={code_text(spawn_code)}",
                    f"segment_length={float(cfg.task.rope.mesh.segment_length)} "
                    f"radial_segments={int(cfg.task.rope.mesh.radial_segments)} "
                    f"particle_size={float(cfg.task.rope.particle_size)} "
                    f"radius={float(cfg.task.rope.radius)}",
                    f"tabletop_friction={bool(cfg.task.rope.tabletop_friction.enabled)} "
                    f"damp_every={int(cfg.task.settle.damp_every)}",
                    f"rope_static_friction={float(cfg.task.rope.elastic.static_friction)} "
                    f"rope_kinetic_friction={float(cfg.task.rope.elastic.kinetic_friction)} "
                    f"substeps={int(cfg.env.sim.substeps)} "
                    f"preset_locked={bool(cfg.env.preset.locked)}",
                    f"rope_model={str(cfg.task.rope.model)} "
                    + " ".join(
                        f"fem.{key}={float(cfg.task.rope.fem[key])}"
                        for key in ("E", "nu", "rho", "friction_mu",
                                    "contact_d_hat", "follow_strength")
                    ),
                    # This task grades who is on top at each crossing, so whether
                    # the detector's code agrees with the braid word on the spawn
                    # state is the calibration for everything downstream.
                    f"detector vs braid ground truth: {'match' if gt_ok else 'MISMATCH'} "
                    f"({gt_detail})",
                    f"planned_moves={planned_moves} place_clearance={float(pinch_cfg.place_clearance)}",
                )
            ),
        )
        print(f"swap_crossing_sign_trace -> {trace_path}")

    planned_text = _plan_text(spawn_plan)
    print(
        f"swap_crossing_sign_start seed={cfg.run.seed} mode={cfg.run.oracle_mode} "
        f"word={rope_scene.braid.word} settle_steps={settle_steps} "
        f"max_particle_step={moved:.6f} crossings={state.crossing_count} "
        f"initial=[{code_text(spawn_code)}] "
        f"gt_match={gt_ok} {gt_detail} budget={budget} planned=[{planned_text}]"
    )
    if not gt_ok:
        # Not fatal, but it means the crossings this episode is about are being
        # read off tubes that do not show what they were built to show.
        print(
            "swap_crossing_sign WARNING: the detector's crossing code disagrees with the "
            "braid word on the spawn state. Who is on top is the quantity under test, so "
            "treat this run's verdict as unreliable rather than as evidence about the oracle.",
            flush=True,
        )
    if cfg.run.verbose:
        for line in crossing_lines(
            state,
            rope_radius=float(cfg.task.rope.radius),
            particle_size=float(cfg.task.rope.particle_size),
        ):
            print(line)

    diagnostics_dir = None if cfg.run.diagnostics_dir is None else Path(str(cfg.run.diagnostics_dir))

    def dump(name: str, polylines: dict) -> None:
        # What each plan was made from, so a move the physics resolved differently
        # from the plan can be replayed through the planner offline.
        if diagnostics_dir is None:
            return
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            diagnostics_dir / f"{name}.npz",
            origin=np.asarray(rope_scene.layout.task_origin, dtype=float),
            **{f"rope_{k}": np.asarray(v, dtype=float) for k, v in polylines.items()},
            **{f"plug_{k}": entity_pos(c) for k, c in rope_scene.free_end_connectors.items()},
        )

    moves = 0
    # Ropes moved and left in no crossing; the planner does not move them again as
    # bystanders (swap_crossing_sign_sequence.plan_sequence).
    bystanders: frozenset = frozenset()
    if stop_before_physics(cfg, rope_scene.scene, "swap_crossing_sign_physical_pinch_demo"):
        raise SystemExit(0)

    with recording_session_from_config(
        rope_scene.scene,
        rope_scene.cameras,
        cfg.recording,
        hud=_hud(status),
    ), AttachmentManager(rope_scene.scene) as attachment_manager:
        while moves < budget and not rule.reached(state.code, spawn_code, cleared=cleared):
            phase = "relay"
            _connector_report(rope_scene, f"pre_plan_{moves + 1}")
            polylines = strand_polylines(rope_scene, samples=evaluator.samples)
            dump(f"decision_{moves + 1:02d}", polylines)
            planned = rule.decide(
                rope_scene, polylines, spawn_code=spawn_code, cleared=cleared, params=params, moved_bystanders=bystanders
            )
            if planned is None:
                print(
                    f"swap_crossing_sign: no move sequence reaches the target from this state "
                    f"(now=[{code_text(state.code)}] min_sep={state.min_separation * 1000:.1f}mm); "
                    "stopping rather than running a move that cannot do what it claims."
                )
                break
            command, plan, sequence = planned
            connector = rope_scene.free_end_connectors[command.strand_index]
            # Straight from the planner: every target keeps the hand within the
            # lifted tail's reach of the peel point, so rebuilding them here would
            # silently undo that.
            carry = np.asarray(command.carry, dtype=float)
            swing = [np.asarray(p, dtype=float) for p in plan.metadata["swing"]]
            place = np.asarray(command.cross, dtype=float)
            settle_down = np.asarray(command.settle, dtype=float)
            print(
                f"swap_crossing_sign_move {moves + 1}/{budget} phase={phase} "
                f"strand={command.strand_index} other={command.under_strand} "
                f"grasp_xy=({command.grasp_xy[0]:+.3f},{command.grasp_xy[1]:+.3f}) "
                f"place_xy=({command.place_xy[0]:+.3f},{command.place_xy[1]:+.3f}) "
                f"arc_to_contact={command.crossing_arc * 1000:.0f}mm "
                + (
                    f"place_clearance={plan.metadata['place_clearance'] * 1000:.0f}mm"
                    f"/{plan.metadata['place_clearance_target'] * 1000:.0f}mm "
                    if "place_clearance" in plan.metadata
                    else ""
                ) +
                f"lift={(command.lift_z - rope_scene.layout.world_z(0.0)) * 1000:.0f}mm "
                f"hang={plan.metadata['hang'] * 1000:.0f}mm pinned={plan.metadata['pinned']} "
                f"moves_left={plan.metadata['moves_left']}"
                f"{'(no full sequence: best single move)' if plan.metadata.get('fallback') else ''} "
                f"pulled_back={(command.grasp_xy[0] - command.carry[0]) * 1000:.0f}mm "
                f"expect=[{code_text(sequence.moves[0].code_after)}] plan=[{_plan_text(sequence)}]"
            )

            # How high a move has to go is not a tuning constant -- it is the rope
            # that must hang below the hand to lift the crossings clear, measured
            # on the ropes as they lie now. The planner keeps it under the ceiling
            # when it can; the ceiling is the arm's own workspace, and past it the
            # IK simply cannot go, failing with a reason that does not name this.
            lift_ceiling = float(
                rope_scene.layout.world_z(float(cfg.common.manipulation_space.workspace.z[1]))
            )
            if command.lift_z > lift_ceiling:
                print(
                    f"swap_crossing_sign WARNING: this move needs the hand at "
                    f"{(command.lift_z - rope_scene.layout.world_z(0.0)) * 1000:.0f}mm, above the "
                    f"{float(cfg.common.manipulation_space.workspace.z[1]) * 1000:.0f}mm workspace "
                    f"ceiling ({command.crossing_arc * 1000:.0f}mm of rope hangs below the hand). "
                    "Expect the IK to clip the lift and the carried rope to plough into the one underneath.",
                    flush=True,
                )

            status["phase"] = f"{phase}_grasp"
            if trace is not None:
                trace.note(
                    f"move {moves + 1} ({phase}): grasping s{command.strand_index} "
                    f"by its free-end connector; target "
                    f"({command.place_xy[0]:+.3f},{command.place_xy[1]:+.3f})"
                )
            # Yaw the wrist so the finger pads do not flank the plug along its own
            # axis -- that is the direction the cable drapes away in, and a pad
            # sitting over it hooks the rope on release.
            plug_axis = polylines[command.strand_index][-1] - polylines[command.strand_index][-6]
            ee_quat = ee_quat_for_yaw(
                controller.default_ee_quat,
                float(np.arctan2(plug_axis[1], plug_axis[0])),
            )
            pitch_angle = np.radians(float(pinch_cfg.carry_pitch_deg))
            pitch_steps = int(pinch_cfg.carry_pitch_steps)

            # Assisted grasp, engaged the instant the fingers close and *before*
            # the primitive's lift check. `grasp_qpos_handle` equals the fitting's
            # radius, so the pads close to exactly the surface with zero preload;
            # without the assist the lift would be asked to run on friction that
            # is not there.
            held: list = []
            flat_quat: list = []

            def engage_grasp_attachment(_connector=connector, _strand=command.strand_index):
                # Weld honesty check: the attachment succeeds no matter where the
                # hand actually is (assist masks placement error by design), so
                # verify the plug really is between the pads before welding.
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
                unpark_connector(_strand)
                # Hand over the plug's *actual* orientation, or the attachment
                # snaps it upright in one step and drags the welded rope
                # particles through that 90 degrees with it.
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
                # corner in the few mm of rope right outside the weld band --
                # where every blow-up in this task's log has started.
                if not held or pitch_angle == 0.0:
                    return
                axis = np.cross(_axis / np.linalg.norm(_axis), np.array([0.0, 0.0, 1.0]))
                target = quat_mul(quat_about_axis(axis, pitch_angle), flat_quat[0])
                held[0].ramp_to(target, pitch_steps)
                if trace is not None:
                    trace.note(
                        f"lift starting ({lift_steps} steps); rotating the plug "
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
                # Nothing does -- the plug is handed back to the solver.
                attachment = held.pop()
                if attachment.ramping():
                    print(
                        "swap_crossing_sign WARNING: released mid-pitch -- the plug is still "
                        "turning and will land off-pose. Raise pinch.carry_pitch_steps' headroom "
                        "or start the lay-flat ramp earlier."
                    )
                attachment.release(sync=False)
                attachment_manager.attachments.remove(attachment)
                if trace is not None:
                    trace.note("attachment released; the plug's pose is now solver-driven")
                return False

            def on_segment_start(_index, _count, label, _target):
                status["phase"] = f"{phase}_{label}"
                if label == "place_down":
                    lay_plug_flat()
                    # The hand is at the end of the sideways carry, where the plan
                    # models the tail as a straight line from the table to the hand:
                    # the ropes here say how high a lifted crossing really rides.
                    if diagnostics_dir is not None:
                        dump(f"carry_{moves + 1:02d}", strand_polylines(rope_scene, samples=evaluator.samples))

            result = primitive.run(
                controller,
                handle=connector,
                ee_quat=ee_quat,
                on_close=engage_grasp_attachment,
                on_lift=pitch_nose_down,
                before_release=release_grasp_attachment,
                on_segment_start=on_segment_start,
                target_centers=[carry, *swing, place, settle_down],
                segment_labels=["carry_up", *(["cross_over"] * (len(swing) + 1)), "place_down"],
            )
            if held:
                release_grasp_attachment()
            moves += 1

            # Settle to rest, not for a fixed count. A rope that was just lifted,
            # carried sideways and put down is a pendulum anchored at one end,
            # and these ropes have almost no damping. Measuring on a swinging
            # rope gives an unreliable count *and* sends the next grasp to a
            # stale position.
            status["phase"] = f"{phase}_settle"
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

            state = evaluator.classify(rope_scene, spawn_code=spawn_code)
            if command.strand_index not in {e[0] for e in state.code} | {e[2] for e in state.code}:
                bystanders = bystanders | {int(command.strand_index)}
            print(
                f"swap_crossing_sign_geometry after move {moves}: "
                + _closest_approach(strand_polylines(rope_scene, samples=evaluator.samples)),
                flush=True,
            )
            if rule.mode == "restack_same" and not cleared and state.crossing_count == 0:
                cleared = True  # taken apart; from here the rule rebuilds the spawn
                if cfg.run.max_moves is None:
                    # The rebuild can take more moves than the take-apart did
                    # (offline dry run, seed 1: 2 apart, 3 back).
                    rebuild = rule.plan(
                        rope_scene, strand_polylines(rope_scene, samples=evaluator.samples),
                        spawn_code=spawn_code, cleared=cleared, params=params,
                    )
                    budget = min(budget_cap, moves + (0 if rebuild is None else len(rebuild.moves)) + 1)
                    status["budget"] = budget

            status.update(
                move=moves,
                crossings=state.crossing_count,
                signature=code_text(state.code),
                terminal=state.is_terminal,
            )
            print(
                f"swap_crossing_sign_after_move {moves} phase={phase} "
                f"success={result.success} grasped={result.grasped} "
                f"reason={result.failure_reason} "
                f"crossings={command.crossing_count_before}->{state.crossing_count} "
                f"now=[{code_text(state.code)}] "
                f"min_sep={state.min_separation * 1000:.1f}mm terminal={state.is_terminal}"
            )
            if cfg.run.verbose:
                for line in crossing_lines(
                    state,
                    rope_radius=float(cfg.task.rope.radius),
                    particle_size=float(cfg.task.rope.particle_size),
                ):
                    print(line)
            # Say which rope tore and where, rather than leaving it to be guessed
            # from a viewer full of stretched triangles.
            for blow_up in rope_blow_ups(rope_scene, tolerance=float(pinch_cfg.blow_up_tolerance)):
                print(
                    f"  BLOW-UP {blow_up} (grasped strand={command.strand_index} "
                    f"at s={command.grasp_arclength:.2f})"
                )

    dump("final", strand_polylines(rope_scene, samples=evaluator.samples))
    print(
        f"swap_crossing_sign_result seed={cfg.run.seed} mode={cfg.run.oracle_mode} "
        f"terminal={state.is_terminal} label={state.failure_label or 'none'} moves={moves}/{budget} "
        f"initial=[{code_text(spawn_code)}] "
        f"final=[{code_text(state.code)}] "
        f"final_crossings={state.crossing_count} "
        f"min_sep={state.min_separation * 1000:.1f}mm"
    )
    if trace is not None:
        trace.close()
    print_recording_saved(cfg.recording)
    return bool(state.is_terminal), rope_scene


@hydra.main(version_base="1.3", config_path="../../configs", config_name="swap_crossing_sign_pinch")
def main(cfg: DictConfig) -> None:
    # `recording.res` resizes cameras, so it has to be applied before the build.
    cfg = apply_recording_camera_overrides(cfg)

    # Alongside Hydra's own snapshot, one with the interpolations expanded -- see
    # `save_resolved_config` for why the reference-preserving form is not enough.
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"swap_crossing_sign_config -> {resolved}", flush=True)

    if cfg.run.randomize_layout:
        cfg = randomize_task_cfg(cfg, TASK_ID, cfg.run.seed, difficulty=cfg.run.difficulty)

    # The frozen baseline pins sim.substeps to 4 and only checks when
    # env.preset.locked is set, so raising substeps needs both overrides.
    if int(cfg.env.sim.substeps) != 4 and bool(cfg.env.preset.locked):
        print(
            f"swap_crossing_sign: env.sim.substeps={int(cfg.env.sim.substeps)} is pinned "
            "to 4 by the frozen topogym_tabletop_v1 baseline. Add env.preset.locked=false "
            "to get past it -- that disables every other baseline check as well, so the "
            "run is off-baseline and must not be recorded as a dataset.",
            flush=True,
        )

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)])

    solved, rope_scene = run_demo(cfg)

    if cfg.run.keep_open or cfg.run.viewer:
        print("swap_crossing_sign holding the viewer open; Ctrl+C to exit.")
        while True:
            rope_scene.scene.step()
    raise SystemExit(0 if solved else 1)


if __name__ == "__main__":
    main()
