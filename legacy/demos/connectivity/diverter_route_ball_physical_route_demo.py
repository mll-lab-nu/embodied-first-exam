"""Turn the diverter so the ball can reach the target (docx 4.3).

The whole episode in one run: the arm pinches the lever knob, sweeps it to the
angle that seals the DEAD branch, lets go and retreats -- and only then is the
ball released, to roll through the fork and out to the target. The robot never
touches the ball; the state change is on the BALL's free space.

One branch is capped, and only the other one leads to the target. That is what
makes this a question about connectivity rather than a choice between two equally
good exits: the ball can only arrive if a route exists, and the flap is what
decides whether it does. Which branch is the dead end varies per episode and has
to be read off the scene -- there is no instruction carrying it, because with one
destination the instruction is a constant.

**The joint has no limit.** "Turn until it stops" is not available, so the angle
the arm leaves the flap at is its own doing, and `target_error` is a hard check.
That is the point of the task: measured 2026-08-19, the ball only makes it out
when the flap is within a few degrees of its seat, while the flood fill calls a
much wider range routable.

Two rules share one interface so the contrast pair is honest:

    run.oracle_mode=oracle            read the instruction, seal the other branch
    run.oracle_mode=fixed_direction   always drive to the same seat

Half the (dead end x initial phase) combinations need no rotation at all -- the
flap already seals the dead branch -- and leaving it alone is the correct action
there. `fixed_direction` gets exactly half of them wrong.

    python -m demos.connectivity.diverter_route_ball_physical_route_demo run.viewer=true
    python -m demos.connectivity.diverter_route_ball_physical_route_demo task.diverter.dead_end_side=right
    python -m demos.connectivity.diverter_route_ball_physical_route_demo run.stage=rotate_only
    python -m demos.connectivity.diverter_route_ball_physical_route_demo run.oracle_mode=fixed_direction
    python -m demos.connectivity.diverter_route_ball_physical_route_demo run.randomize_layout=true run.seed=3
"""

from __future__ import annotations

import os
from dataclasses import replace

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.generation import EpisodeKey, EpisodeResult
from topogym.generation.layout_randomization import randomize_task_cfg

from topogym.planning import make_rule
from topogym.primitives import (
    PivotLeverPrimitive,
    configure_gripper_contact_friction,
    print_collision_il_contract,
)
from topogym.supervision import stop_before_physics
from topogym.tasks_legacy import DiverterRouteBallSceneBuilder
from topogym.tasks_legacy.connectivity._ball_drive import HeadingDrive
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)

TASK_ID = "diverter_route_ball"


def _variant_line(cfg) -> str:
    """One parseable line with every sampled or derived leaf (the variation sweep script reads it)."""
    task = cfg.task
    dead, sealed = str(task.diverter.dead_end_side), str(task.diverter.init_sealed_side)
    return (
        f"{TASK_ID} variant seed={int(cfg.run.seed)} dead_end={dead} init_sealed={sealed} "
        f"rotate_needed={dead != sealed} pad={bool(task.target_pad.enabled)} "
        f"angle_deg={float(task.branch.angle_deg):.2f} lever_r={float(task.diverter.lever.radius):.4f} "
        f"fork_x={float(task.channel.fork_origin_x):+.4f} speed={float(task.ball.speed):.3f} "
        f"release_x={float(task.ball.release_x):+.4f}"
    )


def _checks_line(layout) -> str:
    return " ".join(
        f"{name}={measured:+.4f}/{limit:+.4f}/{'ok' if ok else 'FAIL'}"
        for name, measured, limit, ok in layout.checks()
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
    commanded = layout.commanded_side  # the live side, derived from the dead end
    status["command"] = f"{commanded}(dead={layout.dead_end_side})"
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
    # Deliberate under- or over-rotation, for the contrast runs. Applied to the
    # rule's answer rather than inside the rule: the rule stays the oracle, and
    # what is being demonstrated is an execution error on top of a correct plan.
    offset = float(np.deg2rad(float(getattr(cfg.run, "target_offset_deg", 0.0) or 0.0)))
    if offset != 0.0:
        plan = replace(
            plan,
            target_angle=plan.target_angle + offset,
            rotate=True,
            reason=f"{plan.reason}+offset{np.rad2deg(offset):+.0f}deg",
        )
    status["target_deg"] = float(np.rad2deg(plan.target_angle))
    print(
        f"diverter_route_ball plan dead_end={layout.dead_end_side} live={commanded} "
        f"prompt={layout.command_prompt()!r} "
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
        steps_arc=layout.steps_arc(plan.target_angle - plan.start_angle),

        gripper_steps=int(motion.gripper_steps),
        grasp_qpos=float(motion.grasp_qpos),
        close_hold_steps=int(motion.close_hold_steps),
        arc_settle_steps=int(motion.arc_settle_steps),
        release_hold_steps=int(motion.release_hold_steps),
        target_tolerance=float(np.deg2rad(float(motion.target_tolerance_deg))),
        max_follow_error=float(motion.max_follow_error),
        max_lag=float(np.deg2rad(float(motion.max_lag_deg))),
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
            f"max_lag={np.rad2deg(result.max_lag):.2f}deg "
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

    # Lock before the ball is anywhere near: the angle the arm left is the angle
    # that gets judged, and the flap stops giving ground under the ball's push.
    mech = cfg.task.diverter.mechanism
    if bool(getattr(mech, "lock_after_turn", False)):
        locked = ball_scene.lock_flap(
            kp=float(mech.lock_kp), kv=float(mech.lock_kv), force=float(mech.lock_force)
        )
        print(
            f"diverter_route_ball flap locked at {np.rad2deg(locked):+.2f}deg",
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
                    "max_lag_deg": float(np.rad2deg(result.max_lag)),
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
    in_dead_end = False

    with HeadingDrive(
        ball_scene.scene,
        ball,
        speed=layout.ball_speed,
        radius=layout.ball_radius,
        # Mass from the sphere's own density and radius: the brake is specified
        # as a deceleration, and a force drive needs the mass to turn it into one.
        mass=float(cfg.task.ball.rho) * (4.0 / 3.0) * np.pi * layout.ball_radius ** 3,
        thrust_gain=float(cfg.task.ball.thrust_gain),
        max_thrust=float(cfg.task.ball.max_thrust),
        region=(lo_x, hi_x, lo_y, hi_y),
        dt=dt,
        stall_steps=int(cfg.task.ball.stall_steps),
        offtrack_decel=float(cfg.task.ball.offtrack_decel),
        brake_rect=(
            layout.target_pad_rect_world(layout.commanded_side)
            if layout.target_pad_enabled()
            else None
        ),
        brake_decel=(
            float(layout.target_pad_cfg.brake_decel)
            if layout.target_pad_enabled()
            else 0.0
        ),
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
            if not in_dead_end:
                # Deep enough into the capped branch to be there on purpose, not
                # just nosing past the fork. Read along that branch's own axis.
                station, across = layout.branch_station(layout.dead_end_side, xy)
                in_dead_end = bool(
                    station > layout.exit_station and abs(across) <= layout.half_width
                )
                if in_dead_end:
                    status["exit"] = "dead_end"
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
        reached_target=bool(exit_side == commanded),
        in_dead_end=in_dead_end,
        ball_stuck=jammed,
        settle_drift=drift,
    )
    status["phase"] = "done"

    metrics = {
        "dead_end_side": layout.dead_end_side,
        "live_side": commanded,
        "exit_side": exit_side,
        "exit_step": exit_step,
        "in_dead_end": in_dead_end,
        "flap_deg": float(np.rad2deg(ball_scene.flap_angle())),
        "target_reachable": state.invariant_value,
        "judge_disagrees": state.judge_disagrees,
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
        f"mode={cfg.run.oracle_mode} dead_end={layout.dead_end_side} live={commanded} "
        f"success={episode_result.success} exit={exit_side} exit_step={exit_step} "
        f"in_dead_end={in_dead_end} "
        f"flap={np.rad2deg(ball_scene.flap_angle()):+.2f}deg "
        f"target_reachable={state.invariant_value} stuck={jammed} drift={drift:.5f} "
        f"failure={episode_result.failure_reason}",
        flush=True,
    )
    if state.judge_disagrees:
        print(
            "[warn] the ball reached the target but the flood fill says it cannot: "
            "the judge is wrong, not the run. Check success.grid_pitch and the "
            "obstacle rectangles before touching the scene.",
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

    if cfg.run.randomize_layout:
        cfg = randomize_task_cfg(cfg, TASK_ID, cfg.run.seed, difficulty=cfg.run.difficulty)
        print(_variant_line(cfg), flush=True)

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
        f"init_sealed={layout.initial_sealed_side} dead_end={layout.dead_end_side} "
        f"knob_r={layout.lever_radius:.3f} knob_reach={layout.knob_reach():.3f} "
        f"travel_pred={layout.travel_time():.2f}s "
        f"budget={int(cfg.run.marble_steps) * float(cfg.env.sim.dt):.2f}s",
        flush=True,
    )
    print(f"diverter_route_ball checks {_checks_line(layout)}", flush=True)

    episode_key = EpisodeKey(
        task_id=TASK_ID, seed=int(cfg.run.seed), variant_id=str(cfg.run.variant_id)
    )

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
