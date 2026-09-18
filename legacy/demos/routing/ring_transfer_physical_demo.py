"""The whole ring_transfer episode: build, hook the loop onto B, lift it off A, judge.

docx 2.6「绳圈从柱 A 转移到柱 B」end to end with the Franka. The loop starts flat
around post A; the arm puts its two open fingers inside the loop's far cap and
carries it -- round A, up, over B's head, down on B's far side -- lets go, then
pinches the cap that hugs A, lifts it over A's head, shifts it past the post and
lets go. Winding (A:1, B:0) -> (A:0, B:1).

Nothing here decides anything on its own. The path comes from
`planning/ring_transfer_planner.py`, the grasp is `primitives/fem_attachment.py`
(follow bands under the IPC coupler: targets in the Newton solve, never a
written position), the verdict from `verification/ring_transfer_verifier.py`.
The bands ride `physical.hand_above` below the COMMANDED hand pose, the way
`untangle_continuous_fem_demo` does it: arm PD loop and band constraint chase
the same target. The arm is outside IPC (`needs_coup=False`, every rope task).

    python -B -m demos.routing.ring_transfer_physical_demo
    python -B -m demos.routing.ring_transfer_physical_demo run.viewer=true
    python -B -m demos.routing.ring_transfer_physical_demo run.motion=carry
    python -B -m demos.routing.ring_transfer_physical_demo run.motion=drape_outside
    python -B -m demos.routing.ring_transfer_physical_demo \\
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
from topogym.planning.ring_transfer_planner import GraspPhase, plan_ring_transfer
from topogym.primitives.physical_contact import ee_quat_for_yaw
from topogym.supervision import stop_before_physics
from topogym.tasks_legacy import RingTransferSceneBuilder
from topogym.utils import (
    apply_recording_camera_overrides,
    initialize_franka_controller,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification.ring_transfer_verifier import (
    RingTransferEvaluator,
    RingTransferWatch,
    post_contact_count,
    post_surface_gap,
)


TASK_ID = "ring_transfer"


def _variant_line(cfg, layout) -> str:
    """One parseable line with every sampled or derived leaf (the variation sweep script reads it)."""

    task = cfg.task
    return (
        f"{TASK_ID} variant seed={int(cfg.run.seed)} on_post={layout.anchor.name} "
        f"height={float(task.post_shape.height):.4f} radius={float(task.post_shape.radius):.4f} "
        f"head_overhang={float(task.post_shape.head_overhang):.4f} spacing={float(task.pair.spacing):.4f} "
        f"heading={float(task.pair.heading_deg):+.1f} mid_x={float(task.pair.mid_x):+.4f} mid_y={float(task.pair.mid_y):+.4f} "
        f"a_x={layout.posts['A'].center[0]:+.4f} a_y={layout.posts['A'].center[1]:+.4f} "
        f"b_x={layout.posts['B'].center[0]:+.4f} b_y={layout.posts['B'].center[1]:+.4f} "
        f"long_axis={layout.long_axis[0]:+.3f},{layout.long_axis[1]:+.3f} pinch_side={layout.pinch_side:+.0f} "
        f"pinch_along={layout.pinch_along:.4f} lift_low_z={layout.lift_low_z:.4f} drop_z={layout.drop_z:.4f}"
    )


def _checks_line(layout) -> str:
    return " ".join(
        f"{name}={measured:+.4f}/{limit:+.4f}/{'ok' if ok else 'FAIL'}"
        for name, measured, limit, ok in layout.checks()
    )


@hydra.main(version_base="1.3", config_path="../../configs", config_name="ring_transfer")
def main(cfg: DictConfig) -> None:
    # A seeded variant of the layout (the task yaml's `variation:` block).
    if bool(cfg.run.randomize_layout):
        cfg = randomize_task_cfg(cfg, TASK_ID, int(cfg.run.seed), difficulty=str(cfg.run.difficulty))
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"ring_transfer_config -> {resolved}", flush=True)

    has_display = os.name == "nt" or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if cfg.run.viewer and not has_display:
        raise SystemExit("No graphical display detected.")

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)], precision=str(cfg.env.genesis.precision))
    print(
        f"ring_transfer_physical_demo building_scene backend={cfg.env.genesis.backend} "
        f"viewer={cfg.run.viewer} motion={cfg.run.motion}",
        flush=True,
    )
    built = RingTransferSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(show_viewer=bool(cfg.run.viewer))
    layout, scene = built.layout, built.scene
    if bool(cfg.run.randomize_layout):
        print(_variant_line(cfg, layout), flush=True)
    print(f"{TASK_ID} checks {_checks_line(layout)}", flush=True)
    task, physical, grasp_cfg = cfg.task, cfg.task.physical, cfg.task.grasp
    evaluator = RingTransferEvaluator.from_layout(layout, task)
    watch = RingTransferWatch(posts=layout.posts, tube_radius=layout.ring.tube_radius)
    if stop_before_physics(cfg, scene, "ring_transfer"):
        return

    controller = initialize_franka_controller(scene=scene, manifest=built.manifest, robot_cfg=cfg.robot_control, settle_steps=0)
    print(f"ring_transfer_physical_demo robot_home_ready hand={controller.hand_pos().tolist()}", flush=True)

    hand_above = np.array([0.0, 0.0, float(physical.hand_above)])
    approach_z = float(physical.approach_z)
    speed = float(task.transfer.drive_speed)
    min_steps = int(task.transfer.min_segment_steps)
    gripper_open = float(cfg.robot_control.gripper.open_qpos)
    gripper_closed = float(cfg.robot_control.gripper.closed_qpos)
    hook_qpos = 0.5 * float(grasp_cfg.spread)
    half_spread = 0.5 * float(grasp_cfg.spread)
    counter = {"steps": 0}
    original_step = scene.step

    def watched_step(*args, **kwargs):
        original_step(*args, **kwargs)
        counter["steps"] += 1
        watch.check(built.nodes())

    scene.step = watched_step

    def classify():
        return evaluator.classify(built.nodes(), built.members, spawn_perimeter=built.frames.perimeter, watch=watch)

    def hand_for(held_task_xyz) -> np.ndarray:
        """Commanded hand position (world) that puts the held material at a task point."""

        return layout.to_world(held_task_xyz) + hand_above

    band_sides: dict[str, float] = {}

    def assign_sides(phase: GraspPhase, held_task_xyz) -> None:
        """Which hook band is on which side of the finger axis, from where the
        bands ARE. Band names follow the loop's spawn axis, not the wrist yaw;
        assigning by name drove them across each other (attach_error 68 mm)."""

        yaw = phase.yaw_at(held_task_xyz)
        across = np.array([-np.sin(yaw), np.cos(yaw), 0.0])
        for name in phase.bands:
            centre = layout.to_task(built.bands[name].band_center())
            band_sides[name] = 1.0 if float(np.dot(centre - np.asarray(held_task_xyz), across)) >= 0.0 else -1.0

    def band_targets(phase: GraspPhase, held_task_xyz) -> dict[str, np.ndarray]:
        held = np.asarray(held_task_xyz, dtype=float)
        if phase.kind == "hook":
            # Fingers open along `across` of the wrist yaw (yaw = pull direction).
            yaw = phase.yaw_at(held)
            across = np.array([-np.sin(yaw), np.cos(yaw), 0.0])
            return {name: layout.to_world(held + band_sides[name] * half_spread * across) for name in phase.bands}
        return {phase.bands[0]: layout.to_world(held)}

    # Pinch: where the rope sits relative to the fingertip point at the moment
    # of the grasp (world frame). The band is then driven to the MEASURED hand
    # plus this offset every step, so the rope stays exactly where the pads
    # closed on it. Driving it to the commanded hand instead (the pre-contact
    # recipe) put the rope a few mm ahead of the lagging fingers and pushed one
    # pad open on every accelerating leg (2026-08-25 video: "opens and
    # re-closes while carrying").
    grip_offset: dict[str, np.ndarray] = {}
    phase_assist: dict[str, bool] = {}

    def probe(label: str, step: int, hand_cmd: np.ndarray, phase: GraspPhase) -> dict:
        """One line of evidence per `physical.probe_every` steps while the rope is
        held: is the arm where it was told to be, is the rope where the fingers
        are, and is the loop touching the anchor. `arm_err` is the commanded hand
        minus the measured one -- an arm being pulled by a snagged rope shows up
        here first; `band_err` is the band centroid minus its target."""

        nodes = built.nodes()
        hand_now = np.asarray(controller.hand_pos(), dtype=float)
        arm_err = float(np.linalg.norm(hand_cmd - hand_now))
        tip_now = hand_now - hand_above
        # With the assist on this is the band's tracking error; without it, it is
        # how far the pinched material has slipped from where the pads closed.
        band_err = max(
            float(np.linalg.norm(built.bands[name].band_center() - (tip_now + grip_offset[name])))
            for name in phase.bands
            if name in grip_offset
        ) if phase.kind == "pinch" else float("nan")
        anchor = layout.anchor
        near_anchor = nodes[np.linalg.norm(nodes[:, :2] - anchor.center[None, :], axis=1) <= anchor.head_radius + 3.0 * layout.ring.tube_radius]
        reading = {
            "arm_err_mm": arm_err * 1000.0,
            "band_err_mm": band_err * 1000.0,
            "A_contacts": post_contact_count(nodes, anchor, tube_radius=layout.ring.tube_radius),
            "A_gap_mm": post_surface_gap(nodes, anchor) * 1000.0,
            "near_A_max_z_mm": (float(near_anchor[:, 2].max()) * 1000.0) if len(near_anchor) else float("nan"),
            "loop_min_z_mm": float(nodes[:, 2].min()) * 1000.0,
            "finger_qpos": np.round(controller.gripper_qpos(), 4).tolist(),
        }
        state = classify()
        print(
            f"ring_transfer probe {label} step={step} arm_err={reading['arm_err_mm']:.1f}mm band_err={reading['band_err_mm']:.1f}mm "
            f"A_contacts={reading['A_contacts']} A_gap={reading['A_gap_mm']:.1f}mm near_A_max_z={reading['near_A_max_z_mm']:.1f}mm "
            f"loop_min_z={reading['loop_min_z_mm']:.1f}mm winding={state.winding} finger_qpos={reading['finger_qpos']}",
            flush=True,
        )
        return reading

    def reactive_lift(phase: GraspPhase, held_from: np.ndarray, yaw: float) -> np.ndarray:
        """Take the loop off the anchor by feedback rather than by a fixed path
        (user's design, 2026-08-25): while the loop reads STRETCHED, step the hand
        horizontally toward the anchor's axis (the strand caught under the head is
        on the far side; moving over the post slackens it); while it reads slack,
        step straight up. Done when the lowest point of the loop is above the head.
        The hand never goes further past the axis than `carry.unhook_past`."""

        rl = task.carry.reactive
        anchor = layout.anchor
        clear_z = anchor.top_z + layout.ring.tube_radius + float(task.carry.clear_margin)
        limit_xy = anchor.center + float(task.carry.unhook_past) * (anchor.center - held_from[:2]) / max(float(np.linalg.norm(anchor.center - held_from[:2])), 1e-9)
        held = np.asarray(held_from, dtype=float).copy()
        quat = ee_quat_for_yaw(controller.default_ee_quat, yaw)
        moved_xy = moved_z = 0
        band = phase.bands[0]
        for step in range(1, int(rl.max_steps) + 1):
            nodes = built.nodes()
            state = classify()
            lowest = float(nodes[:, 2].min())
            if lowest > clear_z:
                print(f"ring_transfer reactive_lift done at step {step}: loop bottom {lowest * 1000:.1f}mm > {clear_z * 1000:.1f}mm (xy steps {moved_xy}, z steps {moved_z})", flush=True)
                break
            # Guards: a lost rope reads "slack" forever and the loop would climb
            # out of the workspace (2026-08-25: 400 z-steps to 1.32 m, arm 0.7 m
            # behind). Slip, an arm that cannot follow, or the height cap all end
            # the run here with the evidence printed.
            hand_now = np.asarray(controller.hand_pos(), dtype=float)
            slip = float(np.linalg.norm(built.bands[band].band_center() - (hand_now - hand_above + grip_offset[band])))
            arm_err = float(np.linalg.norm(hand_for(held) - hand_now))
            reason = None
            if slip > float(rl.slip_abort):
                reason = f"rope slipped {slip * 1000:.1f}mm from the pads"
            elif arm_err > float(rl.arm_err_abort):
                reason = f"arm cannot follow (arm_err {arm_err * 1000:.1f}mm)"
            elif held[2] > float(rl.max_z):
                reason = f"fingertip above max_z ({held[2] * 1000:.0f}mm)"
            if reason is not None:
                probe(f"{phase.name}:reactive_lift", step, hand_for(held), phase)
                print(f"ring_transfer reactive_lift ABORT at step {step}: {reason}; length_ratio {state.length_ratio:.3f}, lowest {lowest * 1000:.1f}mm", flush=True)
                raise SystemExit(3)
            to_axis = limit_xy - held[:2]
            dist = float(np.linalg.norm(to_axis))
            if state.length_ratio > float(rl.stretch_max) and dist > 1e-4:
                held[:2] += to_axis / dist * min(float(rl.step_xy), dist)
                moved_xy += 1
            else:
                held[2] += float(rl.step_z)
                moved_z += 1
            # Same as glide(): with the assist on, the band follows the MEASURED
            # hand every step. Missing here on 2026-08-26 (inspect_clear4): the
            # band target stayed put while the hand rose 39 mm -> "slipped" abort.
            if phase_assist.get(phase.name, True):
                built.bands[band].drive_to(hand_now - hand_above + grip_offset[band])
            controller.move_ee_to(hand_for(held), quat=quat, steps=1, continuous_ik=True)
            if cfg.run.verbose and step % int(physical.probe_every) == 0:
                probe(f"{phase.name}:reactive_lift", step, hand_for(held), phase)
                print(f"ring_transfer reactive_lift step={step} length_ratio={state.length_ratio:.3f} lowest={lowest * 1000:.1f}mm held={np.round(held * 1000).astype(int).tolist()} xy_steps={moved_xy} z_steps={moved_z}", flush=True)
        else:
            print(f"ring_transfer reactive_lift: NOT done after {rl.max_steps} steps (length_ratio {classify().length_ratio:.3f}, lowest {float(built.nodes()[:, 2].min()) * 1000:.1f}mm)", flush=True)
        return held

    def lift_verdict(phase: GraspPhase) -> None:
        """Did the loop come off the anchor cleanly? Clean means: no vertex touching
        the anchor and the whole loop above its head top. The winding number is
        NOT a criterion here: it is a top-down projection, and a loop hanging
        directly above the post still projects around its axis (read 1 at this
        moment on 2026-08-26, 0 twenty-five steps into travel). It is printed
        for the record; the final judgement uses it once the loop is down."""

        nodes = built.nodes()
        anchor = layout.anchor
        contacts = post_contact_count(nodes, anchor, tube_radius=layout.ring.tube_radius)
        state = classify()
        lowest = float(nodes[:, 2].min())
        clean = contacts == 0 and lowest > anchor.top_z
        print(
            f"ring_transfer lift verdict: {'CLEAN' if clean else 'SNAGGED'} -- {anchor.name} contacts={contacts} "
            f"winding={state.winding.get(anchor.name)} loop_min_z={lowest * 1000:.1f}mm head_top={anchor.top_z * 1000:.1f}mm",
            flush=True,
        )

    def settle_to(hand_target: np.ndarray, quat: np.ndarray, *, label: str) -> float:
        """Drive the MEASURED hand onto `hand_target`. The IK stops short of its
        target by a few mm (documented in franka.py) and per-step gliding never
        waits, so the pinch came down 16 mm above the rope (2026-08-25). Each
        step re-commands the target pushed out by the measured residual."""

        tol = float(grasp_cfg.settle_tol)
        residual = float("inf")
        steps = 0
        for steps in range(1, int(grasp_cfg.settle_max_steps) + 1):
            hand_now = np.asarray(controller.hand_pos(), dtype=float)
            error = hand_target - hand_now
            residual = float(np.linalg.norm(error))
            if residual < tol:
                break
            controller.move_ee_to(hand_target + error, quat=quat, steps=1, continuous_ik=True)
        tip_z = float(layout.to_task(np.asarray(controller.hand_pos(), dtype=float) - hand_above)[2])
        print(f"ring_transfer {label} settled: residual={residual * 1000:.1f}mm after {steps} steps (tip z={tip_z * 1000:.1f}mm){'' if residual < tol else ' NOT CONVERGED'}", flush=True)
        return residual

    def close_until_still(qpos: float, *, label: str) -> np.ndarray:
        """Close the gripper and step until the fingers stop moving; prints the
        finger reading every 10 steps so a delayed or blocked closure is visible
        (2026-08-25: 80 fixed steps ended with the fingers still open at 0.036)."""

        controller.set_gripper(qpos)
        history = [np.asarray(controller.gripper_qpos(), dtype=float).copy()]
        steps = 0
        for steps in range(1, int(grasp_cfg.close_max_steps) + 1):
            controller.step(1)
            history.append(np.asarray(controller.gripper_qpos(), dtype=float).copy())
            if steps % 10 == 0:
                print(f"ring_transfer {label} close step={steps} finger_qpos={np.round(history[-1], 4).tolist()}", flush=True)
                if float(np.abs(history[-1] - history[-11]).max()) < 5e-5:
                    break
        else:
            print(f"ring_transfer {label} close: fingers NOT STILL after {steps} steps", flush=True)
        print(f"ring_transfer {label} close done: {steps} steps, finger_qpos={np.round(history[-1], 4).tolist()} (commanded {qpos})", flush=True)
        return history[-1]

    def glide(hand_from: np.ndarray, hand_to: np.ndarray, yaw_from: float, yaw_to: float, *, phase: GraspPhase | None, held_to=None, held_from=None, label: str):
        distance = float(np.linalg.norm(hand_to - hand_from))
        steps = max(min_steps, int(np.ceil(distance / speed)))
        delta_yaw = float(np.arctan2(np.sin(yaw_to - yaw_from), np.cos(yaw_to - yaw_from)))
        for step in range(1, steps + 1):
            alpha = step / steps
            hand = hand_from + alpha * (hand_to - hand_from)
            yaw = yaw_from + alpha * delta_yaw
            if phase is not None and held_to is not None:
                if phase.kind == "pinch":
                    if phase_assist.get(phase.name, True):
                        tip_now = np.asarray(controller.hand_pos(), dtype=float) - hand_above
                        for name in phase.bands:
                            built.bands[name].drive_to(tip_now + grip_offset[name])
                else:
                    held = np.asarray(held_from) + alpha * (np.asarray(held_to) - np.asarray(held_from))
                    for name, target in band_targets(phase, held).items():
                        built.bands[name].drive_to(target)
            controller.move_ee_to(hand, quat=ee_quat_for_yaw(controller.default_ee_quat, yaw), steps=1, continuous_ik=True)
            if phase is not None and cfg.run.verbose and (step % int(physical.probe_every) == 0 or step == steps):
                probe(label, step, hand, phase)
        if cfg.run.verbose:
            state = classify()
            print(f"ring_transfer {label}: {steps} steps, hand {np.round(controller.hand_pos() * 1000, 1).tolist()}mm, {state.summary()}", flush=True)

    def run_phase(phase: GraspPhase) -> None:
        # Where the material to grasp actually is (observed), in the task frame.
        centres = {name: layout.to_task(built.bands[name].band_center()) for name in phase.bands}
        held0 = np.mean([centres[name] for name in phase.bands], axis=0)
        if phase.kind == "hook":
            assign_sides(phase, held0)
        yaw = phase.yaw_at(held0)
        quat = ee_quat_for_yaw(controller.default_ee_quat, yaw)
        # Pinch: open pads come down straddling the strand (the yaw puts the
        # closing axis across it), close on it, and only THEN does the assist
        # engage. Hook (transfer's on-phase): an internal grasp -- fingers enter
        # the loop closed and open against the rope from inside.
        controller.set_gripper(gripper_closed if phase.kind == "hook" else gripper_open, steps=int(physical.gripper_steps))
        hand_now = np.asarray(controller.hand_pos(), dtype=float)
        yaw_now = yaw
        hover = hand_for(np.array([held0[0], held0[1], approach_z]))
        glide(hand_now, hover, yaw_now, yaw, phase=None, label=f"{phase.name}:hover")
        if phase.kind == "pinch":
            settle_to(hover, quat, label=f"{phase.name}:hover")
        grasp_point = held0 + (np.array([0.0, 0.0, float(grasp_cfg.pinch_lift)]) if phase.kind == "pinch" else 0.0)
        grasp_hand = hand_for(grasp_point)
        glide(hover, grasp_hand, yaw, yaw, phase=None, label=f"{phase.name}:descend")
        if phase.kind == "pinch":
            settle_to(grasp_hand, quat, label=f"{phase.name}:descend")
            # Close on the rope: each finger stops at tube radius + d_hat from the
            # centre line, so the strand sits between the pads held by the barrier.
            close_until_still(float(grasp_cfg.grasp_qpos), label=phase.name)
        else:
            for _ in range(int(physical.touch_settle_steps)):
                controller.move_ee_to(grasp_hand, quat=quat, steps=1, continuous_ik=True)
        # The assist must not hide a hand that never got there: the fingertip
        # point has to be within attach_tolerance of the band(s) before engaging.
        tip = layout.to_task(np.asarray(controller.hand_pos(), dtype=float) - hand_above)
        # Each band is expected at the fingertip point plus its finger offset.
        expected = {name: tip + (layout.to_task(target) - held0) for name, target in band_targets(phase, held0).items()}
        errors = {name: float(np.linalg.norm(expected[name] - centres[name])) for name in phase.bands}
        worst = max(errors.values())
        print(
            f"ring_transfer {phase.name} attach_error_mm={ {k: round(v * 1000, 2) for k, v in errors.items()} } "
            f"tolerance={float(grasp_cfg.attach_tolerance) * 1000:.0f} finger_qpos={np.round(controller.gripper_qpos(), 4).tolist()}",
            flush=True,
        )
        if worst > float(grasp_cfg.attach_tolerance):
            raise SystemExit(f"ring_transfer {phase.name}: hand missed the band by {worst * 1000:.1f} mm; refusing to engage the assist.")
        if phase.kind == "hook":
            # Spread the fingers until the pads meet the rope from inside: the
            # visible act of taking hold. The bands engage only after that.
            controller.set_gripper(hook_qpos, steps=int(physical.gripper_steps))
        assist = phase.kind != "pinch" or bool(grasp_cfg.get("assist", True))
        for name in phase.bands:
            if assist:
                built.bands[name].attach()
            tip_now = np.asarray(controller.hand_pos(), dtype=float) - hand_above
            grip_offset[name] = np.asarray(built.bands[name].band_center(), dtype=float) - tip_now
        phase_assist[phase.name] = assist
        if phase.kind == "pinch":
            # The grasp evidence: lift a little and the pinched material must come
            # along (with the assist on, this checks the weld; without it, the
            # friction pinch). A position check cannot tell "pads round the rope"
            # from "pads above the rope" (2026-08-25: attach_error 4.6 mm, rope never moved).
            band = phase.bands[0]
            band_z0 = float(built.bands[band].band_center()[2])
            check = float(grasp_cfg.lift_check)
            grasp_point = grasp_point + np.array([0.0, 0.0, check])
            grasp_hand = hand_for(grasp_point)
            for _ in range(int(grasp_cfg.settle_max_steps)):
                if assist:
                    built.bands[band].drive_to(np.asarray(controller.hand_pos(), dtype=float) - hand_above + grip_offset[band])
                hand_now = np.asarray(controller.hand_pos(), dtype=float)
                if float(np.linalg.norm(grasp_hand - hand_now)) < float(grasp_cfg.settle_tol):
                    break
                controller.move_ee_to(grasp_hand + (grasp_hand - hand_now), quat=quat, steps=1, continuous_ik=True)
            print(f"ring_transfer {phase.name}:lift_check settled: residual={float(np.linalg.norm(grasp_hand - np.asarray(controller.hand_pos(), dtype=float))) * 1000:.1f}mm", flush=True)
            rise = float(built.bands[band].band_center()[2]) - band_z0
            held = rise >= float(grasp_cfg.lift_check_min_rise)
            print(f"ring_transfer {phase.name} lift_check: band rose {rise * 1000:.1f}mm of {check * 1000:.0f} finger_qpos={np.round(controller.gripper_qpos(), 4).tolist()} -> {'HELD' if held else 'NOT HELD'}", flush=True)
            if not held:
                raise SystemExit(f"ring_transfer {phase.name}: rope not held (band rose {rise * 1000:.1f} mm of {check * 1000:.0f}); nothing to carry.")
        print(
            f"ring_transfer {phase.name} grasped kind={phase.kind} finger_qpos={np.round(controller.gripper_qpos(), 4).tolist()} "
            f"bands={[f'{n}:{len(built.bands[n].indices)}' for n in phase.bands]}",
            flush=True,
        )
        held_prev = grasp_point if phase.kind == "pinch" else held0
        hand_prev = grasp_hand
        yaw_prev = yaw
        # A pinch phase's path is relative to where the material actually is
        # (the near band drifted 26.7 mm from its design point in the spike), so
        # its waypoints are shifted in xy onto the observed grasp.
        shift_xy = np.zeros(3)
        if phase.kind == "pinch":
            shift_xy = np.array([held0[0] - phase.waypoints[0].position[0], held0[1] - phase.waypoints[0].position[1], 0.0])
        reactive = phase.kind == "pinch" and bool(task.carry.get("reactive_lift", False)) and any(wp.label == "clear" for wp in phase.waypoints)
        for wp in phase.waypoints:
            held = np.asarray(wp.position, dtype=float) + shift_xy
            yaw_next = phase.yaw_at(held) if phase.kind == "hook" else yaw
            if reactive and wp.label in ("over_anchor", "clear"):
                if wp.label == "over_anchor":
                    continue  # the reactive lift decides where to go
                held = reactive_lift(phase, held_prev, yaw)
                hand_prev, held_prev = hand_for(held), held
                lift_verdict(phase)
                if str(cfg.run.stop_after or "") == "clear":
                    print(f"ring_transfer stop_after=clear: holding {int(cfg.run.final_hold_steps)} steps for inspection, then exiting", flush=True)
                    for _ in range(int(cfg.run.final_hold_steps)):
                        for name in phase.bands:
                            if built.bands[name].active:
                                built.bands[name].drive_to(np.asarray(controller.hand_pos(), dtype=float) - hand_above + grip_offset[name])
                        controller.move_ee_to(hand_prev, quat=ee_quat_for_yaw(controller.default_ee_quat, yaw_prev), steps=1, continuous_ik=True)
                    raise SystemExit(2)
                continue
            glide(hand_prev, hand_for(held), yaw_prev, yaw_next, phase=phase, held_from=held_prev, held_to=held, label=f"{phase.name}:{wp.label}")
            held_prev, hand_prev, yaw_prev = held, hand_for(held), yaw_next
            if wp.label == "clear":
                lift_verdict(phase)
            if str(cfg.run.stop_after or "") == wp.label:
                print(f"ring_transfer stop_after={wp.label}: holding {int(cfg.run.final_hold_steps)} steps for inspection, then exiting", flush=True)
                for _ in range(int(cfg.run.final_hold_steps)):
                    for name in phase.bands:
                        if phase.kind == "pinch" and built.bands[name].active:
                            built.bands[name].drive_to(np.asarray(controller.hand_pos(), dtype=float) - hand_above + grip_offset[name])
                    controller.move_ee_to(hand_prev, quat=ee_quat_for_yaw(controller.default_ee_quat, yaw_prev), steps=1, continuous_ik=True)
                raise SystemExit(2)
            if phase.kind == "pinch" and phase.close_axis is not None and wp.label in ("clear", "travel", "approach"):
                # How the pinched loop hangs: depth below the fingertips and the
                # width of its bottom U along the strand (across the closing
                # axis). The width is what the lasso onto B needs -- at least
                # 2 (r_post + 2 r_tube + d_hat).
                nodes = built.nodes()
                low = nodes[nodes[:, 2] <= nodes[:, 2].min() + 0.03]
                along = np.array([-phase.close_axis[1], phase.close_axis[0], 0.0])
                width = float(np.ptp(low @ along))
                depth = float(held[2] - nodes[:, 2].min())
                need = 2.0 * (layout.target.radius + 2.0 * layout.ring.tube_radius + float(task.rope.fem.contact_d_hat))
                print(
                    f"ring_transfer {phase.name}:{wp.label} hang_depth_mm={depth * 1000:.1f} u_width_mm={width * 1000:.1f} "
                    f"(need >= {need * 1000:.0f}) {'ok' if width >= need else 'U TOO NARROW'}",
                    flush=True,
                )
        for name in phase.bands:
            if built.bands[name].active:
                built.bands[name].release()
        # Letting go: an internal grasp closes (the fingers come back together
        # inside the loop and lift out of it); a pinch opens.
        controller.set_gripper(gripper_closed if phase.kind == "hook" else gripper_open, steps=int(physical.gripper_steps))
        retreat = hand_for(np.array([held_prev[0], held_prev[1], approach_z]))
        glide(hand_prev, retreat, yaw_prev, yaw_prev, phase=None, label=f"{phase.name}:retreat")
        for _ in range(int(task.transfer.release_settle_steps)):
            scene.step()
        print(f"ring_transfer after {phase.name}: {classify().summary()}", flush=True)

    with recording_session_from_config(scene, built.cameras, cfg.recording):
        # The home pose already has the gripper open (0.04); re-opening it was
        # 80 idle steps at the head of every video.
        if float(np.min(controller.gripper_qpos())) < gripper_open - 1e-3:
            controller.open_gripper(int(physical.gripper_steps))
        for _ in range(int(physical.settle_steps)):
            scene.step()
        start = classify()
        print(f"ring_transfer start_state {start.summary()}", flush=True)
        want_start = frozenset(layout.ring.enclosure)
        if start.enclosure != want_start or not start.integral:
            raise SystemExit(f"ring_transfer: the loop did not settle around {sorted(want_start)}: {start.summary()}")
        phases, plan = plan_ring_transfer(layout, motion=str(cfg.run.motion))
        print(f"ring_transfer plan {plan.plan_id} phases={[p.name for p in phases]} instruction={layout.instruction()!r} {layout.summary()}", flush=True)
        # The off-phase grasps wherever the near band ended up after the on-phase,
        # not the design point (measured 26.7 mm drift in the spike).
        for phase in phases:
            run_phase(phase)
        for _ in range(int(cfg.run.final_hold_steps)):
            scene.step()

    scene.step = original_step
    state = classify()
    print(
        f"ring_transfer result success={state.is_terminal} motion={cfg.run.motion} steps={counter['steps']} {state.summary()}",
        flush=True,
    )
    print_recording_saved(cfg.recording)
    if cfg.run.keep_open_no_step:
        while True:
            time.sleep(0.05)
    elif cfg.run.keep_open or cfg.run.viewer:
        while True:
            scene.step()
    raise SystemExit(0 if state.is_terminal else 1)


if __name__ == "__main__":
    main()
