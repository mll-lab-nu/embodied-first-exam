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
from topogym.planning.ring_transfer_planner import GraspPhase, plan_ring_transfer
from topogym.primitives.physical_contact import ee_quat_for_yaw
from topogym.supervision import stop_before_physics
from topogym.tasks import RingTransferSceneBuilder
from topogym.utils import (
    apply_recording_camera_overrides,
    initialize_franka_controller,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification.ring_transfer_verifier import RingTransferEvaluator, RingTransferWatch


@hydra.main(version_base="1.3", config_path="../../configs", config_name="ring_transfer")
def main(cfg: DictConfig) -> None:
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

    def band_targets(phase: GraspPhase, held_task_xyz) -> dict[str, np.ndarray]:
        held = np.asarray(held_task_xyz, dtype=float)
        if phase.kind == "hook":
            direction = held[:2] - np.asarray(phase.anchor_xy)
            direction = direction / max(float(np.linalg.norm(direction)), 1e-9)
            across = np.array([-direction[1], direction[0], 0.0])
            return {
                phase.bands[0]: layout.to_world(held + half_spread * across),
                phase.bands[1]: layout.to_world(held - half_spread * across),
            }
        return {phase.bands[0]: layout.to_world(held)}

    def glide(hand_from: np.ndarray, hand_to: np.ndarray, yaw_from: float, yaw_to: float, *, phase: GraspPhase | None, held_to=None, held_from=None, label: str):
        distance = float(np.linalg.norm(hand_to - hand_from))
        steps = max(min_steps, int(np.ceil(distance / speed)))
        delta_yaw = float(np.arctan2(np.sin(yaw_to - yaw_from), np.cos(yaw_to - yaw_from)))
        for step in range(1, steps + 1):
            alpha = step / steps
            hand = hand_from + alpha * (hand_to - hand_from)
            yaw = yaw_from + alpha * delta_yaw
            if phase is not None and held_to is not None:
                held = np.asarray(held_from) + alpha * (np.asarray(held_to) - np.asarray(held_from))
                for name, target in band_targets(phase, held).items():
                    built.bands[name].drive_to(target)
            controller.move_ee_to(hand, quat=ee_quat_for_yaw(controller.default_ee_quat, yaw), steps=1, continuous_ik=True)
        if cfg.run.verbose:
            state = classify()
            print(f"ring_transfer {label}: {steps} steps, hand {np.round(controller.hand_pos() * 1000, 1).tolist()}mm, {state.summary()}", flush=True)

    def run_phase(phase: GraspPhase) -> None:
        # Where the material to grasp actually is (observed), in the task frame.
        centres = {name: layout.to_task(built.bands[name].band_center()) for name in phase.bands}
        held0 = np.mean([centres[name] for name in phase.bands], axis=0)
        yaw = phase.yaw_at(held0)
        quat = ee_quat_for_yaw(controller.default_ee_quat, yaw)
        controller.set_gripper(hook_qpos if phase.kind == "hook" else gripper_open, steps=int(physical.gripper_steps))
        hand_now = np.asarray(controller.hand_pos(), dtype=float)
        yaw_now = yaw
        hover = hand_for(np.array([held0[0], held0[1], approach_z]))
        glide(hand_now, hover, yaw_now, yaw, phase=None, label=f"{phase.name}:hover")
        grasp_hand = hand_for(held0)
        glide(hover, grasp_hand, yaw, yaw, phase=None, label=f"{phase.name}:descend")
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
        if phase.kind == "pinch":
            controller.set_gripper(gripper_closed, steps=int(physical.gripper_steps))
        for name in phase.bands:
            built.bands[name].attach()
        held_prev = held0
        hand_prev = grasp_hand
        yaw_prev = yaw
        # A pinch phase's path is relative to where the material actually is
        # (the near band drifted 26.7 mm from its design point in the spike), so
        # its waypoints are shifted in xy onto the observed grasp.
        shift_xy = np.zeros(3)
        if phase.kind == "pinch":
            shift_xy = np.array([held0[0] - phase.waypoints[0].position[0], held0[1] - phase.waypoints[0].position[1], 0.0])
        for wp in phase.waypoints:
            held = np.asarray(wp.position, dtype=float) + shift_xy
            yaw_next = phase.yaw_at(held) if phase.kind == "hook" else yaw
            glide(hand_prev, hand_for(held), yaw_prev, yaw_next, phase=phase, held_from=held_prev, held_to=held, label=f"{phase.name}:{wp.label}")
            held_prev, hand_prev, yaw_prev = held, hand_for(held), yaw_next
        for name in phase.bands:
            built.bands[name].release()
        controller.set_gripper(gripper_open, steps=int(physical.gripper_steps))
        retreat = hand_for(np.array([held_prev[0], held_prev[1], approach_z]))
        glide(hand_prev, retreat, yaw_prev, yaw_prev, phase=None, label=f"{phase.name}:retreat")
        for _ in range(int(task.transfer.release_settle_steps)):
            scene.step()
        print(f"ring_transfer after {phase.name}: {classify().summary()}", flush=True)

    with recording_session_from_config(scene, built.cameras, cfg.recording):
        controller.open_gripper(int(physical.gripper_steps))
        for _ in range(int(physical.settle_steps)):
            scene.step()
        start = classify()
        print(f"ring_transfer start_state {start.summary()}", flush=True)
        want_start = frozenset(layout.ring.enclosure)
        if start.enclosure != want_start or not start.integral:
            raise SystemExit(f"ring_transfer: the loop did not settle around {sorted(want_start)}: {start.summary()}")
        phases, plan = plan_ring_transfer(layout, motion=str(cfg.run.motion))
        print(f"ring_transfer plan {plan.plan_id} phases={[p.name for p in phases]} {layout.summary()}", flush=True)
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
