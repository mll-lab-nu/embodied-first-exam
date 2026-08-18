"""Turn the diverter so the ball leaves by the exit you were told (docx 4.3).

The whole episode in one run: the arm pinches the lever knob, sweeps it to the
angle that seals the branch NOT asked for, lets go and retreats -- and only then
is the ball released, to roll through the fork and out. The robot never touches
the ball; the state change is on the BALL's free space.

**The joint has no limit.** "Turn until it stops" is not available, so the angle
the arm leaves the flap at is its own doing, and `target_error` is a hard check.
That is the point of the task: measured 2026-08-19, the ball only makes it out
when the flap is within a few degrees of its seat, while the flood fill calls a
much wider range routable.

Two rules share one interface so the contrast pair is honest:

    run.oracle_mode=oracle            read the instruction, seal the other branch
    run.oracle_mode=fixed_direction   always drive to the same seat

Half the (instruction x initial phase) combinations need no rotation at all --
the flap already routes the right way -- and leaving it alone is the correct
action there. `fixed_direction` gets exactly half of them wrong, which is docx
4.3's anti-shortcut measured rather than asserted.

    python -m demos.connectivity.diverter_route_ball_physical_route_demo run.viewer=true
    python -m demos.connectivity.diverter_route_ball_physical_route_demo task.command.side=right
    python -m demos.connectivity.diverter_route_ball_physical_route_demo run.stage=rotate_only
    python -m demos.connectivity.diverter_route_ball_physical_route_demo run.oracle_mode=fixed_direction
"""

from __future__ import annotations

import os

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.generation import EpisodeKey, EpisodeResult
from topogym.planning import make_rule
from topogym.primitives import (
    PivotLeverPrimitive,
    configure_gripper_contact_friction,
    print_collision_il_contract,
)
from topogym.supervision import stop_before_physics
from topogym.tasks import DiverterRouteBallSceneBuilder
from topogym.tasks.connectivity._ball_drive import HeadingDrive
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import DiverterRouteBallEvaluator


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def task_xy(ball_scene, entity) -> np.ndarray:
    origin = np.asarray(ball_scene.layout.task_origin, dtype=float)
    return _as_numpy(entity.get_pos()).reshape(-1, 3)[0][:2].astype(float) - origin[:2]


def _hud(ball_scene, status):
    def render_lines():
        layout = ball_scene.layout
        angle = ball_scene.flap_angle()
        return [
            "task=diverter_route_ball",
            f"cmd={status.get('command', '-')}  mode={status.get('mode', '-')}",
            f"phase={status.get('phase', '-')}",
            f"flap={np.rad2deg(angle):+.1f}deg -> {status.get('target_deg', 0.0):+.1f}",
            f"open={layout.open_side_at(angle)}  exit={status.get('exit', '-')}",
        ]

    return render_lines


def run_episode(cfg, ball_scene, controller, *, episode_key, status) -> EpisodeResult:
    layout = ball_scene.layout
    motion = cfg.task.motion
    dt = float(cfg.env.sim.dt)
    commanded = layout.commanded_side
    status["command"] = commanded
    status["mode"] = str(cfg.run.oracle_mode)

    print_collision_il_contract(
        "diverter_route_ball_physical_route_demo",
        manipulated=["diverter"],
        runtime_attachment=False,
        runtime_set_pose=False,
        success_checks=("target_error", "finger_qpos", "st_reachable", "exit_side"),
    )

    rule = make_rule(cfg.run.oracle_mode)
    plan = rule.decide(layout, ball_scene.flap_angle(), commanded)
    status["target_deg"] = float(np.rad2deg(plan.target_angle))
    print(
        f"diverter_route_ball plan command={commanded} prompt={layout.command_prompt()!r} "
        f"mode={cfg.run.oracle_mode} start={np.rad2deg(plan.start_angle):+.2f}deg "
        f"target={np.rad2deg(plan.target_angle):+.2f}deg rotate={plan.rotate} "
        f"reason={plan.reason}",
        flush=True,
    )

    if stop_before_physics(cfg, ball_scene.scene, "diverter_route_ball_physical_route_demo"):
        raise SystemExit(0)

    primitive = PivotLeverPrimitive(
        approach_z=layout.world_z(float(motion.approach_z)),
        retreat_z=layout.world_z(float(motion.retreat_z)),
        steps_per_phase=int(motion.steps_per_phase),
        steps_arc=int(motion.steps_arc),
        gripper_steps=int(motion.gripper_steps),
        grasp_qpos=float(motion.grasp_qpos),
        close_hold_steps=int(motion.close_hold_steps),
        arc_settle_steps=int(motion.arc_settle_steps),
        release_hold_steps=int(motion.release_hold_steps),
        target_tolerance=float(np.deg2rad(float(motion.target_tolerance_deg))),
        max_follow_error=float(motion.max_follow_error),
        max_release_drift=float(np.deg2rad(float(motion.max_release_drift_deg))),
        min_finger_qpos=(
            None if motion.min_finger_qpos is None else float(motion.min_finger_qpos)
        ),
        verbose=bool(cfg.run.verbose),
    )

    result = None
    if plan.rotate:
        status["phase"] = "rotate"
        result = primitive.run(
            controller,
            entity=ball_scene.diverter_entity(),
            dof=ball_scene.joint_dof,
            pivot_xy=layout.position_to_world((layout.nose_x, 0.0, 0.0))[:2],
            radius=layout.lever_radius,
            grasp_z=float(layout.knob_grasp_world(plan.start_angle)[2]),
            target_angle=plan.target_angle,
        )
        print(
            "diverter_route_ball rotate "
            f"success={result.success} start={np.rad2deg(result.start_angle):+.2f}deg "
            f"target={np.rad2deg(result.target_angle):+.2f}deg "
            f"final={np.rad2deg(result.final_angle):+.2f}deg "
            f"target_error={np.rad2deg(result.target_error):.2f}deg "
            f"follow_error={result.max_follow_error:.4f} "
            f"release_drift={np.rad2deg(result.release_drift):.2f}deg "
            f"finger_qpos={result.finger_qpos:.4f} "
            f"phases={len(result.completed_phases)}/{len(PivotLeverPrimitive.NOMINAL_PHASES)}",
            flush=True,
        )
    else:
        # Leaving it alone IS the action here, and half the instances are like
        # that. Recorded explicitly so the episode is not mistaken for a no-op.
        print(
            "diverter_route_ball rotate skipped: the flap already routes to "
            f"{commanded}; the correct action is to leave it alone.",
            flush=True,
        )

    if str(cfg.run.stage) == "rotate_only":
        status["phase"] = "done"
        metrics = {"rotate_only": True}
        if result is not None:
            metrics.update(
                {
                    "target_error_deg": float(np.rad2deg(result.target_error)),
                    "follow_error": float(result.max_follow_error),
                    "release_drift_deg": float(np.rad2deg(result.release_drift)),
                    "finger_qpos": float(result.finger_qpos),
                }
            )
            return (
                EpisodeResult.ok(episode_key, metrics=metrics, export_ready=False)
                if result.success
                else EpisodeResult.failed(
                    episode_key, result.failure_reason or "rotate_failed",
                    metrics=metrics, stable_ready=False,
                )
            )
        return EpisodeResult.ok(episode_key, metrics=metrics, export_ready=False)

    # ---- the marble test: release the ball and see where it goes -------------
    status["phase"] = "marble_test"
    evaluator = DiverterRouteBallEvaluator()
    ball = ball_scene.ball_entity()
    lo_x, hi_x, lo_y, hi_y = layout.drive_region_world()
    exit_side = None
    exit_step = None

    with HeadingDrive(
        ball_scene.scene,
        ball,
        speed=layout.ball_speed,
        radius=layout.ball_radius,
        region=(lo_x, hi_x, lo_y, hi_y),
        dt=dt,
        stall_steps=int(cfg.task.ball.stall_steps),
        offtrack_decel=float(cfg.task.ball.offtrack_decel),
    ) as drive:
        drive.start()
        budget = int(cfg.run.marble_steps)
        for step in range(1, budget + 1):
            ball_scene.scene.step()
            xy = task_xy(ball_scene, ball)
            if exit_side is None:
                exit_side = layout.exited_side(xy)
                if exit_side is not None:
                    exit_step = step
                    status["exit"] = exit_side
            if exit_side is not None and not drive.running and not drive.coasting:
                break
        # The reading has to survive continued stepping, as in gate_cage_ball's
        # release test: "it left" is only true if it stays left.
        before = task_xy(ball_scene, ball)
        controller.step(int(cfg.task.success.settle_steps))
        drift = float(np.linalg.norm(task_xy(ball_scene, ball) - before))
        jammed = bool(drive.jammed)

    state = evaluator.classify(
        ball_scene,
        commanded_side=commanded,
        exit_side=exit_side,
        ball_stuck=jammed,
        settle_drift=drift,
    )
    status["phase"] = "done"

    metrics = {
        "commanded_side": commanded,
        "exit_side": exit_side,
        "exit_step": exit_step,
        "flap_deg": float(np.rad2deg(ball_scene.flap_angle())),
        "reachable": state.invariant_value,
        "ball_stuck": jammed,
        "settle_drift": drift,
        "rotate_success": None if result is None else bool(result.success),
        "target_error_deg": None if result is None else float(np.rad2deg(result.target_error)),
        "mode": str(cfg.run.oracle_mode),
    }
    if state.is_terminal:
        episode_result = EpisodeResult.ok(
            episode_key, metrics=metrics,
            export_ready=bool(result is None or result.success),
        )
    else:
        episode_result = EpisodeResult.failed(
            episode_key,
            state.failure_label or "not_routed",
            metrics=metrics,
            stable_ready=False,
        )

    print(
        "diverter_route_ball_physical_route_demo result "
        f"mode={cfg.run.oracle_mode} command={commanded} success={episode_result.success} "
        f"exit={exit_side} exit_step={exit_step} "
        f"flap={np.rad2deg(ball_scene.flap_angle()):+.2f}deg "
        f"reachable={state.invariant_value} stuck={jammed} drift={drift:.5f} "
        f"failure={episode_result.failure_reason}",
        flush=True,
    )
    if cfg.run.verbose:
        print(f"diverter_route_ball topology {state.to_info()}", flush=True)
    return episode_result


@hydra.main(version_base="1.3", config_path="../../configs",
            config_name="diverter_route_ball_route")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"diverter_route_ball_config -> {resolved}", flush=True)

    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    show_viewer = bool(cfg.run.viewer and has_display)
    if cfg.run.viewer and not show_viewer:
        print("[warn] no display detected; falling back to headless.", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)],
            precision=str(cfg.env.genesis.precision))

    builder = DiverterRouteBallSceneBuilder(cfg.env, cfg.task, cfg.robot_control)
    ball_scene = builder.build(show_viewer=show_viewer)
    layout = ball_scene.layout

    controller = initialize_franka_controller(
        scene=ball_scene.scene,
        manifest=ball_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=int(cfg.task.physical.settle_steps),
    )
    configure_gripper_contact_friction(
        entities=[ball_scene.diverter_entity()],
        robot=controller.robot,
        finger_links=list(cfg.task.motion.finger_links),
        object_friction=float(cfg.task.diverter.mechanism.contact_friction),
        finger_friction=float(cfg.task.motion.finger_friction),
    )
    # Episode reset, before anything is measured: the home settle costs scene
    # steps and the ball is a free body from the moment it is added.
    ball_scene.ball_entity().set_pos(
        tuple(float(v) for v in layout.ball_release_center()), zero_velocity=True
    )

    print(
        "diverter_route_ball setup "
        f"nose_x={layout.nose_x:+.4f} flap_len={layout.flap_length:.4f} "
        f"seat=±{np.rad2deg(layout.angle):.1f}deg limited={bool(getattr(cfg.task.diverter.mechanism, 'joint_limited', False))} "
        f"init_sealed={layout.initial_sealed_side} command={layout.commanded_side} "
        f"knob_r={layout.lever_radius:.3f} travel_pred={layout.travel_time():.2f}s",
        flush=True,
    )

    episode_key = EpisodeKey(task_id="diverter_route_ball", seed=int(cfg.run.seed))
    status = {"phase": "home", "command": "-", "mode": "-", "target_deg": 0.0, "exit": "-"}
    with recording_session_from_config(
        ball_scene.scene, ball_scene.cameras, cfg.recording, hud=_hud(ball_scene, status)
    ):
        run_episode(cfg, ball_scene, controller, episode_key=episode_key, status=status)

    print_recording_saved(cfg.recording)
    while cfg.run.keep_open and show_viewer:
        ball_scene.scene.step()


if __name__ == "__main__":
    main()
