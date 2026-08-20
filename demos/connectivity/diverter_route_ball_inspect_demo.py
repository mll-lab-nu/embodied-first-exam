"""Look at the Diverter Route Ball fork, and watch one ball run through it.

Stage-1 demo: no robot motion, no lever turn. It answers the geometry questions
the scene has to get right before a primitive is worth writing, and answers them
as numbers rather than by eye:

1. Does the flap actually route the ball? Seated one way the ball has to leave by
   the opposite exit, seated the other way by the other one. A flap that seals
   but does not steer sends the ball into the sealed mouth instead, which is the
   failure mode the guide-vane geometry exists to avoid.
2. What does half-open do? Docx 4.3 wants a distinguishable intermediate state.
   Whether it reads as "wedged at the fork" or as "slipped past on one side"
   decides which failure label step 4 gives it, so it is measured here.
3. How long is the run? Release to exit sizes the timeout the physical S-T
   marble test gets in step 4.

The joint sweep (`run.sweep_joint=true`) writes the joint directly. That is a
kinematic check of the limits and of lever-versus-wall clearance -- it is not an
episode, and nothing in an episode may move the flap that way
(`docs/develop/tasks/rigid_first_track_zh.md` section 3.1).

    python -m demos.connectivity.diverter_route_ball_inspect_demo run.static_only=true run.viewer=true
    python -m demos.connectivity.diverter_route_ball_inspect_demo run.sweep_joint=true run.viewer=true
    python -m demos.connectivity.diverter_route_ball_inspect_demo run.flap_phase=seal_left run.verbose=true
    python -m demos.connectivity.diverter_route_ball_inspect_demo run.flap_phase=half run.viewer=true
    python -m demos.connectivity.diverter_route_ball_inspect_demo run.classify=true run.verbose=true
    python -m demos.connectivity.diverter_route_ball_inspect_demo --cfg job
"""

from __future__ import annotations

import os

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.supervision import stop_before_physics
from topogym.tasks import DiverterRouteBallSceneBuilder, other_side
from topogym.tasks.connectivity._ball_drive import HeadingDrive
from topogym.utils.franka import initialize_franka_controller
from topogym.verification import DiverterRouteBallEvaluator
from topogym.utils.recording import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)

PHASES = ("config", "seal_left", "seal_right", "half")


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def entity_pos(entity) -> np.ndarray:
    return _as_numpy(entity.get_pos()).reshape(-1, 3)[0].astype(float)


def resolve_phase_angle(layout, phase: str, flap_deg=None) -> float:
    """Joint angle for a `run.flap_phase` name, or `run.flap_deg` if given.

    An explicit angle exists because the named phases only cover the seats and
    the midpoint, and the question that needs answering is what happens BETWEEN
    them: the flood fill calls every angle from 16 to 70 degrees routable, but
    whether the ball actually gets out depends on how well the flap aims it,
    which no amount of geometry will tell us.
    """

    if flap_deg is not None:
        return float(np.deg2rad(float(flap_deg)))
    phase = str(phase)
    if phase == "config":
        return layout.seat_angle(layout.initial_sealed_side)
    if phase == "seal_left":
        return layout.seat_angle("left")
    if phase == "seal_right":
        return layout.seat_angle("right")
    if phase == "half":
        return 0.0
    raise ValueError(f"Unknown run.flap_phase={phase!r}; expected one of {PHASES}.")


def _hud(state):
    def render_lines():
        return [
            "task=diverter_route_ball",
            f"phase={state.get('phase', '-')}",
            f"flap={state.get('flap_deg', 0.0):+.1f}deg sealed={state.get('sealed', '-')}",
            f"ball=({state.get('ball_x', 0.0):+.3f},{state.get('ball_y', 0.0):+.3f})",
            f"exit={state.get('exit', '-')}",
        ]

    return render_lines


def task_xy(ball_scene, entity) -> np.ndarray:
    """Entity xy in the task frame, which is what every layout number is in."""

    origin = np.asarray(ball_scene.layout.task_origin, dtype=float)
    return entity_pos(entity)[:2] - origin[:2]


def run_sweep(cfg, ball_scene, state) -> None:
    """Drive the joint from limit to limit and back, reporting what it reached."""

    layout = ball_scene.layout
    scene = ball_scene.scene
    steps = max(1, int(cfg.run.sweep_steps))
    left = layout.seat_angle("left")
    right = layout.seat_angle("right")
    reached = []
    # Deliberately commanded PAST each limit: the point is to confirm the joint
    # stops where the flap belongs rather than to confirm we can ask for the
    # right number. Overshoot is what a contact-driven arc will do too.
    overshoot = float(np.deg2rad(10.0))
    for target in (right - overshoot, left + overshoot, right - overshoot):
        start = ball_scene.flap_angle()
        for step in range(1, steps + 1):
            alpha = step / steps
            ball_scene.set_flap_angle((1.0 - alpha) * start + alpha * target)
            scene.step()
            state["flap_deg"] = float(np.rad2deg(ball_scene.flap_angle()))
        angle = ball_scene.flap_angle()
        reached.append(angle)
        knob = layout.knob_center_xy(angle)
        tip = layout.flap_tip_xy(angle)
        print(
            f"[sweep] commanded={np.rad2deg(target):+7.2f}deg reached={np.rad2deg(angle):+7.2f}deg "
            f"sealed={layout.sealed_side_at(angle)} "
            f"tip=({tip[0]:+.4f},{tip[1]:+.4f}) knob=({knob[0]:+.4f},{knob[1]:+.4f})",
            flush=True,
        )

    limit = layout.angle
    worst = max(abs(abs(float(a)) - limit) for a in reached)
    print(
        "diverter_route_ball sweep "
        f"limit=±{np.rad2deg(limit):.2f}deg worst_limit_error={np.rad2deg(worst):.3f}deg "
        f"seated_both_ends={worst <= np.deg2rad(1.0)}",
        flush=True,
    )


def run_rollout(cfg, ball_scene, drive, state) -> None:
    """Release the ball and watch which way it goes."""

    layout = ball_scene.layout
    ball = ball_scene.ball_entity()
    scene = ball_scene.scene
    dt = float(cfg.env.sim.dt)
    sample_every = max(1, int(cfg.run.sample_every))

    drive.start()
    exit_side = None
    exit_step = None
    jam_step = None
    jam_xy = None
    max_abs_y_in_lane = 0.0

    for step in range(1, int(cfg.run.rollout_steps) + 1):
        scene.step()
        xy = task_xy(ball_scene, ball)
        state["ball_x"], state["ball_y"] = float(xy[0]), float(xy[1])
        # Only the STRAIGHT lane: past the junction the walls flare and the flap
        # deflects the ball on purpose, so counting that stretch would report the
        # deflection as wander. Measured 2026-08-18: gated at nose_x this read
        # 33.7 mm on a correctly routed run, against 0.0 mm in the straight lane.
        if xy[0] < layout.junction_x:
            max_abs_y_in_lane = max(max_abs_y_in_lane, abs(float(xy[1])))
        if exit_side is None:
            # Station ALONG the branch, not a plane of constant x -- see
            # `DiverterRouteBallLayout.exited_side`.
            exit_side = layout.exited_side(xy)
            if exit_side is not None:
                exit_step = step
                state["exit"] = exit_side
        if jam_step is None and drive.jammed:
            jam_step = step
            jam_xy = xy.copy()
        if cfg.run.verbose and step % sample_every == 0:
            print(
                f"[diverter step={step:4d}] t={step * dt:5.2f}s "
                f"xy=({xy[0]:+.4f},{xy[1]:+.4f}) "
                f"heading=({drive.heading[0]:+.3f},{drive.heading[1]:+.3f}) "
                f"{'jammed' if drive.jammed else ('coasting' if drive.coasting else 'driving')}",
                flush=True,
            )
        if exit_side is not None and not drive.running and not drive.coasting:
            break

    final = task_xy(ball_scene, ball)
    angle = ball_scene.flap_angle()
    sealed = layout.sealed_side_at(angle)
    expected = None if sealed is None else other_side(sealed)
    # How far past the mouth the ball ended up, measured along the branch it took
    # (or, if it never left, the one it would have). `final` alone cannot say:
    # the branches run at an angle, so a distance in x is not a distance along one.
    final_side = exit_side if exit_side is not None else expected
    final_station = (
        layout.branch_station(final_side, final)[0] if final_side is not None else None
    )
    # A jam leaves the ball in the lane, where no branch station means anything.
    station_text = "n/a" if final_station is None else f"{final_station:+.4f}"
    runout_text = (
        "n/a" if final_station is None else f"{final_station - layout.exit_station:+.4f}"
    )
    print(
        "diverter_route_ball inspect "
        f"flap={np.rad2deg(angle):+.2f}deg sealed={sealed} expected_exit={expected} "
        f"exit={exit_side} exit_step={exit_step} "
        f"exit_time={'n/a' if exit_step is None else f'{exit_step * dt:.2f}s'} "
        f"travel_pred={layout.travel_time():.2f}s "
        f"jammed={drive.jammed} jam_step={jam_step} "
        f"jam_xy={'n/a' if jam_xy is None else f'({jam_xy[0]:+.4f},{jam_xy[1]:+.4f})'} "
        f"lane_max_abs_y={max_abs_y_in_lane:.4f} "
        f"final=({final[0]:+.4f},{final[1]:+.4f}) "
        f"final_station={station_text}/{layout.exit_station:.3f} "
        f"runout={runout_text} "
        f"routed_correctly={exit_side is not None and exit_side == expected}",
        flush=True,
    )
    if exit_side is None and not drive.jammed:
        print(
            "[warn] the ball neither exited nor jammed within the rollout: raise "
            "run.rollout_steps, or check task.ball.speed and the drive threshold.",
            flush=True,
        )
    if cfg.run.classify:
        # The geometric judge, read on the same scene the rollout just happened in.
        # The line that matters is `judge_disagrees`: the ball reaching a target
        # the flood fill calls unreachable is the one combination that cannot be
        # true, and it means the judge is wrong rather than the run.
        state = DiverterRouteBallEvaluator().classify(
            ball_scene,
            reached_target=bool(exit_side == layout.live_side),
            ball_stuck=bool(drive.jammed),
        )
        print(
            "diverter_route_ball classify "
            f"dead_end={layout.dead_end_side} live={layout.live_side} "
            f"target_reachable={state.invariant_value} observed_exit={exit_side} "
            f"reached_target={state.reached_target} "
            f"judge_disagrees={state.judge_disagrees} "
            f"seated={state.seated} success={state.is_terminal} "
            f"label={state.failure_label}",
            flush=True,
        )
        if cfg.run.verbose:
            print(f"diverter_route_ball topology {state.to_info()}", flush=True)

    if exit_side is not None and expected is not None and exit_side != expected:
        print(
            f"[warn] the ball left by {exit_side} while the flap seals {sealed}: the "
            "flap is sealing but not steering. Check that the seated flap lies along "
            "a branch's inner boundary (diverter_route_ball.flap_reach), not across a "
            "branch mouth.",
            flush=True,
        )


@hydra.main(version_base="1.3", config_path="../../configs", config_name="diverter_route_ball")
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
    gs.init(backend=backends[str(cfg.env.genesis.backend)], precision=str(cfg.env.genesis.precision))

    builder = DiverterRouteBallSceneBuilder(cfg.env, cfg.task, cfg.robot_control)
    ball_scene = builder.build(show_viewer=show_viewer)
    layout = ball_scene.layout

    # Hold the arm at its home pose. It takes no part in this demo, but a Franka
    # in the scene with no joint targets collapses under gravity on the first step.
    initialize_franka_controller(
        scene=ball_scene.scene,
        manifest=ball_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0 if cfg.run.static_only else int(cfg.task.physical.settle_steps),
    )

    phase_angle = resolve_phase_angle(
        layout, cfg.run.flap_phase, getattr(cfg.run, "flap_deg", None)
    )
    ball_scene.set_flap_angle(phase_angle)
    # Episode reset, before anything is measured: the settle above costs scene
    # steps and the ball is a free body from the moment it is added.
    ball_scene.ball_entity().set_pos(
        tuple(float(v) for v in layout.ball_release_center()), zero_velocity=True
    )

    left_exit = layout.exit_center("left")
    right_exit = layout.exit_center("right")
    print(
        "diverter_route_ball setup "
        f"nose_x={layout.nose_x:+.4f} junction_x={layout.junction_x:+.4f} "
        f"flap_len={layout.flap_length:.4f} (reach={layout.flap_reach:.4f}) "
        f"seat=±{np.rad2deg(layout.angle):.1f}deg "
        f"phase={cfg.run.flap_phase}/{np.rad2deg(phase_angle):+.1f}deg "
        f"sealed={layout.sealed_side_at(phase_angle)} "
        f"exit_plane_x={layout.exit_plane_x:+.4f} "
        f"exit_left=({left_exit[0]:+.4f},{left_exit[1]:+.4f}) "
        f"exit_right=({right_exit[0]:+.4f},{right_exit[1]:+.4f}) "
        f"lane_clear={2.0 * layout.half_width:.3f} ball_dia={2.0 * layout.ball_radius:.3f} "
        f"travel_pred={layout.travel_time():.2f}s",
        flush=True,
    )

    if stop_before_physics(cfg, ball_scene.scene, "diverter_route_ball_inspect_demo"):
        raise SystemExit(0)

    state = {
        "phase": "settle",
        "flap_deg": float(np.rad2deg(phase_angle)),
        "sealed": layout.sealed_side_at(phase_angle),
        "ball_x": 0.0,
        "ball_y": 0.0,
        "exit": "-",
    }
    with recording_session_from_config(
        ball_scene.scene, ball_scene.cameras, cfg.recording, hud=_hud(state)
    ):
        if cfg.run.static_only:
            # Build-and-look: no stepping at all, so the scene is inspected exactly
            # as constructed. Anything that interpenetrates at build time shows up
            # here rather than being hidden by the first settle.
            print("diverter_route_ball static_only=true; not stepping.", flush=True)
        elif cfg.run.sweep_joint:
            state["phase"] = "sweep"
            run_sweep(cfg, ball_scene, state)
        else:
            state["phase"] = "rollout"
            with HeadingDrive(
                ball_scene.scene,
                ball_scene.ball_entity(),
                speed=layout.ball_speed,
                radius=layout.ball_radius,
                # Mass from the sphere's own density and radius: the brake is specified
                # as a deceleration, and a force drive needs the mass to turn it into one.
                mass=float(cfg.task.ball.rho) * (4.0 / 3.0) * np.pi * layout.ball_radius ** 3,
                thrust_gain=float(cfg.task.ball.thrust_gain),
                max_thrust=float(cfg.task.ball.max_thrust),
                region=layout.drive_region_world(),
                dt=float(cfg.env.sim.dt),
                stall_steps=int(cfg.task.ball.stall_steps),
                offtrack_decel=float(cfg.task.ball.offtrack_decel),
                brake_rect=(
                    layout.target_pad_rect_world(layout.live_side)
                    if layout.target_pad_enabled()
                    else None
                ),
                brake_decel=(
                    float(layout.target_pad_cfg.brake_decel)
                    if layout.target_pad_enabled()
                    else 0.0
                ),
            ) as drive:
                run_rollout(cfg, ball_scene, drive, state)
        state["phase"] = "done"

    print_recording_saved(cfg.recording)
    while cfg.run.keep_open and show_viewer:
        ball_scene.scene.step()


if __name__ == "__main__":
    main()
