"""Cage the rolling ball by dropping the gate at the right moment (docx 4.1).

The robot never touches the ball. It takes the plate off its rack, holds it over
the slot, waits, and commits to the descent when the ball is inside with time to
spare. Success is a property of the BALL's free space, judged by flood-fill, and
the physical recheck is a separate step after release.

Assisted grasp: the plate is 1.1 kg held on a 12 mm edge, carried by
`AttachmentManager` as in cable_routing / untangle / bar_through_hole, so the IL
contract reports `runtime_attachment=True`. The grip is rigid in the HAND's frame
(`parent_quat_fn`), so every motion the plate makes is one the arm made -- nothing
re-poses it on its own.

Two oracles share one interface so the contrast pair is honest:

    run.trigger=oracle   wait until the ball is in with time to spare, then seal
    run.trigger=greedy   seal the moment the arm is in place, ignoring the ball

Which of the two wins is a property of the instance, not something this scene is
built to decide: it turns on whether the arm reaches its station before or after
the ball arrives. Separating them across a distribution is the randomization job
described in `configs/run_configs/gate_cage_ball_gate.yaml`.

    python -m demos.connectivity.gate_cage_ball_physical_gate_demo run.viewer=true run.verbose=true
    python -m demos.connectivity.gate_cage_ball_physical_gate_demo run.trigger=greedy run.verbose=true
    python -m demos.connectivity.gate_cage_ball_physical_gate_demo task.ball.release_y=-0.300
"""

from __future__ import annotations

import os

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.generation import EpisodeKey, EpisodeResult
from topogym.planning import GateTriggerRule, GreedyTriggerRule
from topogym.primitives import (
    AttachmentManager,
    GatedInsertPrimitive,
    configure_gripper_contact_friction,
    entity_pos,
    entity_quat,
    print_collision_il_contract,
)
from topogym.supervision import stop_before_physics
from topogym.tasks import GateCageBallSceneBuilder
from topogym.tasks.connectivity._ball_drive import BallShuttle
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import GateCageBallEvaluator


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def ball_state(ball_scene) -> tuple[float, float]:
    """The ball's y and its y velocity, in task-frame terms."""

    ball = ball_scene.ball_entity()
    origin_y = float(ball_scene.layout.task_origin[1])
    pos_y = float(entity_pos(ball)[1]) - origin_y
    vel_y = float(_as_numpy(ball.get_vel()).reshape(-1, 3)[0][1])
    return pos_y, vel_y


def _hud(ball_scene, status):
    def render_lines():
        y, vy = ball_state(ball_scene)
        return [
            "task=gate_cage_ball",
            f"phase={status.get('phase', '-')}",
            f"ball_y={y:+.3f} vy={vy:+.3f}",
            f"inside={y > ball_scene.layout.door_y}",
            f"trigger={status.get('trigger', '-')}",
        ]

    return render_lines


def run_demo(cfg, ball_scene, controller, *, episode_key, status) -> EpisodeResult:
    layout = ball_scene.layout
    plate = ball_scene.gate_entity()
    motion = cfg.task.motion

    print_collision_il_contract(
        "gate_cage_ball_physical_gate_demo",
        manipulated=["gate"],
        runtime_attachment=True,
        runtime_set_pose=False,
        success_checks=("finger_qpos", "plate_yaw", "escape_paths", "release_stable"),
    )

    primitive = GatedInsertPrimitive(
        approach_z=layout.world_z(float(motion.approach_z)),
        grasp_z=layout.world_z(float(motion.grasp_z)),
        carry_z=layout.world_z(float(motion.carry_z)),
        hover_z=layout.world_z(float(motion.hover_z)),
        seated_z=layout.world_z(float(motion.seated_z)),
        clear_z=layout.world_z(float(motion.clear_z)),
        steps_per_phase=int(motion.steps_per_phase),
        gripper_steps=int(motion.gripper_steps),
        insert_steps=int(motion.insert_steps),
        grasp_qpos=float(motion.grasp_qpos),
        close_hold_steps=int(motion.close_hold_steps),
        insert_settle_steps=int(motion.insert_settle_steps),
        release_hold_steps=int(motion.release_hold_steps),
        min_lift_delta=float(motion.min_lift_delta),
        min_finger_qpos=(
            None if motion.min_finger_qpos is None else float(motion.min_finger_qpos)
        ),
        max_plate_yaw=float(np.deg2rad(float(motion.max_plate_yaw_deg))),
        max_hover_steps=int(motion.max_hover_steps),
        verbose=bool(cfg.run.verbose),
    )

    dt = float(cfg.env.sim.dt)
    insert_duration = primitive.insert_duration(dt)
    if str(cfg.run.trigger) == "greedy":
        rule = GreedyTriggerRule()
    else:
        rule = GateTriggerRule(
            door_y=layout.door_y,
            insert_duration=insert_duration,
            safety_margin=float(cfg.run.safety_margin),
        )
    # The ball is free from the moment the episode starts, so the arm is racing it.
    # Two facts, of different kinds.
    #
    # `solvable` is a condition on the instance: unless the window is still open,
    # with time to seal, by the moment the arm is on station, no policy of any kind
    # can win and the instance is broken rather than hard. Warned about.
    #
    # `hover_wait` is where the baseline difficulty comes from -- the arm arrives
    # BEFORE the ball and has to hold station and wait. Reported, not asserted: it
    # is a property of this instance's geometry, and choosing geometry to fix what
    # a particular baseline scores would put that score into the scene definition.
    # Separating the baselines is a randomization job, not a layout job. See
    # configs/run_configs/gate_cage_ball_gate.yaml.
    entry_delay = layout.entry_delay()
    window = layout.predicted_window(dt=dt)
    margin = float(cfg.run.safety_margin)
    t_ready = primitive.time_to_station(dt)
    last_commit = entry_delay + window - insert_duration
    solvable = last_commit > t_ready
    print(
        f"gate_cage_ball trigger={cfg.run.trigger} entry_delay={entry_delay:.2f}s "
        f"window={window:.2f}s insert_duration={insert_duration:.2f}s "
        f"safety_margin={margin:.2f}s t_ready={t_ready:.2f}s "
        f"hover_wait={entry_delay - t_ready:+.2f}s "
        f"last_commit={last_commit:.2f}s slack={last_commit - t_ready:+.2f}s "
        f"solvable={solvable}",
        flush=True,
    )
    if not solvable:
        print(
            f"[warn] last_commit {last_commit:.2f}s <= t_ready {t_ready:.2f}s: the ball "
            "is back out before the arm can seal, so no policy can win this instance. "
            "Lengthen the closed section (task.channel.flat_end_y), slow the ball "
            "(task.feed_ramp.rise down), or speed the arm "
            "(task.motion.steps_per_phase down).",
            flush=True,
        )

    if stop_before_physics(cfg, ball_scene.scene, "gate_cage_ball_physical_gate_demo"):
        raise SystemExit(0)

    evaluator = GateCageBallEvaluator()

    with AttachmentManager(ball_scene.scene) as attachment_manager:
        held: list = []

        def attach_plate():
            attachment = attachment_manager.create(
                entity=plate,
                parent_pos_fn=controller.hand_pos,
                offset=entity_pos(plate) - np.asarray(controller.hand_pos(), dtype=float),
                quat=entity_quat(plate),
                # Rigid in the hand's frame, so the plate's pose is explained by the
                # arm's. See docs/develop/tasks/rigid_first_track_zh.md 3.1.
                parent_quat_fn=controller.hand_quat,
            )
            attachment.attach()
            held.append(attachment)
            status["phase"] = "carrying"
            return attachment

        def release_plate():
            status["phase"] = "released"
            for attachment in held:
                attachment.release(sync=False)
            held.clear()

        def trigger_fn():
            decision = rule.decide(*ball_state(ball_scene))
            status["trigger"] = decision.reason
            return decision

        status["phase"] = "fetch"
        result = primitive.run(
            controller,
            plate=plate,
            grasp_xy=layout.gate_parked_center()[:2],
            slot_part_xy=layout.position_to_world(
                (layout.center_x, layout.door_y, 0.0)
            )[:2],
            retreat_xy=layout.gate_parked_center()[:2],
            ee_quat=controller.default_ee_quat,
            attach_fn=attach_plate,
            release_fn=release_plate,
            trigger_fn=trigger_fn,
        )

        # Physical recheck: keep stepping with the arm clear and require the
        # reading to survive. Geometry alone is not task_success.
        status["phase"] = "release_check"
        before = entity_pos(ball_scene.ball_entity())
        pre_state = evaluator.classify(ball_scene, release_stable=True)
        controller.step(int(cfg.task.success.settle_steps))
        drift = float(np.linalg.norm(entity_pos(ball_scene.ball_entity()) - before))
        post_state = evaluator.classify(ball_scene, release_stable=True)
        release_stable = bool(post_state.escape_paths == pre_state.escape_paths)

    state = evaluator.classify(ball_scene, release_stable=release_stable)
    status["phase"] = "done"

    metrics = {
        "motion_success": bool(result.success),
        "escape_paths": int(state.escape_paths),
        "caged": bool(state.caged),
        "ball_inside": bool(state.inside),
        "pinched": bool(state.pinched),
        "gate_blocking": bool(state.gate_blocking),
        "finger_qpos": float(result.finger_qpos),
        "plate_yaw_deg": float(result.plate_yaw_deg),
        "hover_steps": int(result.hover_steps),
        "hover_seconds": float(result.hover_steps * dt),
        "ball_settle_drift": drift,
        "trigger": str(cfg.run.trigger),
        "trigger_reason": result.trigger_reason,
    }

    if state.is_terminal:
        episode_result = EpisodeResult.ok(
            episode_key, metrics=metrics, export_ready=bool(result.success)
        )
    else:
        episode_result = EpisodeResult.failed(
            episode_key,
            result.failure_reason or state.failure_label or "not_caged",
            metrics=metrics,
            stable_ready=False,
        )

    print(
        "gate_cage_ball_physical_gate_demo result "
        f"trigger={cfg.run.trigger} success={episode_result.success} "
        f"escape_paths={state.escape_paths} caged={state.caged} inside={state.inside} "
        f"pinched={state.pinched} gate_blocking={state.gate_blocking} "
        f"hover={result.hover_steps}步/{result.hover_steps * dt:.2f}s "
        f"trigger_reason={result.trigger_reason} "
        f"finger_qpos={result.finger_qpos:.4f} plate_yaw={result.plate_yaw_deg:.2f}deg "
        f"ball_drift={drift:.5f} release_stable={release_stable} "
        f"failure={episode_result.failure_reason} "
        f"phases={len(result.completed_phases)}/{len(GatedInsertPrimitive.NOMINAL_PHASES)}",
        flush=True,
    )
    if cfg.run.verbose:
        print(f"gate_cage_ball topology {state.to_info()}", flush=True)
    return episode_result


@hydra.main(version_base="1.3", config_path="../../configs", config_name="gate_cage_ball_gate")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"gate_cage_ball_config -> {resolved}", flush=True)

    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    show_viewer = bool(cfg.run.viewer and has_display)
    if cfg.run.viewer and not show_viewer:
        print("[warn] no display detected; falling back to headless.", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)], precision=str(cfg.env.genesis.precision))

    builder = GateCageBallSceneBuilder(cfg.env, cfg.task, cfg.robot_control)
    ball_scene = builder.build(show_viewer=show_viewer)

    controller = initialize_franka_controller(
        scene=ball_scene.scene,
        manifest=ball_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=int(cfg.task.physical.settle_steps),
    )
    configure_gripper_contact_friction(
        entities=[ball_scene.gate_entity()],
        robot=controller.robot,
        finger_links=list(cfg.task.motion.finger_links),
        object_friction=float(cfg.task.gate.friction),
        finger_friction=float(cfg.task.motion.finger_friction),
    )
    # The episode starts here, and the ball is free from this instant -- no holding,
    # no staged release. Resetting it after the arm's home settle is what makes
    # "here" well defined: settling costs 40 scene steps and the ball would
    # otherwise already be part-way down the ramp when the first phase begins.
    # Episode reset, before the episode, not a teleport during it.
    ball_scene.ball_entity().set_pos(
        tuple(float(v) for v in ball_scene.layout.ball_release_center()), zero_velocity=True
    )

    episode_key = EpisodeKey(task_id="gate_cage_ball", seed=int(cfg.run.seed))
    status = {"phase": "home", "trigger": "-"}

    layout = ball_scene.layout
    lane_lo, lane_hi = layout.lane_bounds()
    with recording_session_from_config(
        ball_scene.scene, ball_scene.cameras, cfg.recording, hud=_hud(ball_scene, status)
    ), BallShuttle(
        ball_scene.scene,
        ball_scene.ball_entity(),
        speed=layout.ball_speed,
        radius=layout.ball_radius,
        lane_min_y=float(layout.position_to_world((0.0, lane_lo, 0.0))[1]),
        lane_max_y=float(layout.position_to_world((0.0, lane_hi, 0.0))[1]),
        dt=float(cfg.env.sim.dt),
        stall_steps=int(cfg.task.ball.stall_steps),
        offtrack_decel=float(cfg.task.ball.offtrack_decel),
    ):
        run_demo(cfg, ball_scene, controller, episode_key=episode_key, status=status)

    print_recording_saved(cfg.recording)
    while cfg.run.keep_open and show_viewer:
        ball_scene.scene.step()


if __name__ == "__main__":
    main()
