"""Look at the Gate Cage Ball chute, and watch one ball run through it.

Stage-0 demo: no robot motion, no gate insertion. It exists to answer the three
geometry questions the scene has to get right before a planner is worth writing,
and it answers them as numbers rather than by eye:

1. Does the ball actually get in? It starts outside on the feed ramp and has to
   cross the doorway plane under gravity alone.
2. Does it come back? The closed end returns it with a ramp, because rigid-vs-rigid
   restitution measured at -0.001 -- a wall would simply stop it.
3. How long is the window? The interval between crossing the doorway inbound and
   crossing it again outbound is the whole time the gate can be sealed in, and
   `T_insert` has to fit inside it.

    python -m demos.connectivity.gate_cage_ball_inspect_demo run.viewer=true run.keep_open=true
    python -m demos.connectivity.gate_cage_ball_inspect_demo run.verbose=true
    python -m demos.connectivity.gate_cage_ball_inspect_demo task.ball.release_y=-0.200
    python -m demos.connectivity.gate_cage_ball_inspect_demo run.randomize_layout=true run.seed=3 run.static_only=true
    python -m demos.connectivity.gate_cage_ball_inspect_demo --cfg job
"""


from __future__ import annotations

import os

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.generation.layout_randomization import randomize_task_cfg
from topogym.supervision import stop_before_physics

from topogym.tasks_legacy import GateCageBallSceneBuilder
from topogym.tasks_legacy.connectivity._ball_drive import BallShuttle, WallRestitution
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def entity_pos(entity) -> np.ndarray:
    return _as_numpy(entity.get_pos()).reshape(-1, 3)[0].astype(float)


def _hud(ball_scene, state):
    def render_lines():
        return [
            "task=gate_cage_ball",
            f"phase={state.get('phase', '-')}",
            f"ball_y={state.get('ball_y', 0.0):+.4f}",
            f"inside={state.get('inside', False)}",
        ]

    return render_lines


def reset_ball(ball_scene) -> None:
    """Put the ball back on its release point after the arm has settled.

    Settling the Franka to its home pose costs scene steps, and the ball is a free
    body from the moment it is added -- so it is already rolling down the feed ramp
    while the arm is still finding its pose, and part of the window would be spent
    before anything measured it. This is episode reset, not a runtime teleport: it
    happens before the episode starts, which is the same status as the pose the
    scene builder gave it.
    """

    ball_scene.ball_entity().set_pos(
        tuple(float(v) for v in ball_scene.layout.ball_release_center()),
        zero_velocity=True,
    )


def run_rollout(cfg, ball_scene, state) -> None:
    """Step and watch. The ball is free and already at its release point."""

    layout = ball_scene.layout
    ball = ball_scene.ball_entity()
    scene = ball_scene.scene
    origin_y = float(layout.task_origin[1])
    dt = float(cfg.env.sim.dt)

    def depth_of(world_y: float) -> float:
        """How far past the doorway the ball is, positive inside.

        Signed depth rather than a raw y: `channel.open_end` mirrors the lane, so
        "inside" is larger y in half the draws and smaller y in the other half.
        """

        return layout.depth(float(world_y) - origin_y)

    entered_step = None
    exited_step = None
    entry_speed = None
    exit_speed = None
    inside_now = None
    passes: list[list] = []
    max_depth = -np.inf
    max_depth_step = 0
    sample_every = max(1, int(cfg.run.sample_every))

    for step in range(1, int(cfg.run.rollout_steps) + 1):
        scene.step()
        pos = entity_pos(ball)
        y = float(pos[1])
        depth = depth_of(y)
        if depth > max_depth:
            max_depth, max_depth_step = depth, step
        vy_now = abs(float(_as_numpy(ball.get_vel()).reshape(-1, 3)[0][1]))
        if entered_step is None and depth > 0.0:
            entered_step = step
            entry_speed = vy_now
        elif entered_step is not None and exited_step is None and depth < 0.0:
            exited_step = step
            exit_speed = vy_now
        # Every pass, not only the first: the free-rolling ball comes back.
        if inside_now is None:
            inside_now = depth > 0.0
        elif depth > 0.0 and not inside_now:
            inside_now = True
            passes.append([step, None, vy_now])
        elif depth <= 0.0 and inside_now:
            inside_now = False
            if passes:
                passes[-1][1] = step
        state["ball_y"] = depth
        state["inside"] = bool(depth > 0.0)
        if cfg.run.verbose and step % sample_every == 0:
            print(
                f"[gate_cage_ball step={step:4d}] t={step * dt:5.2f}s "
                f"depth={depth:+.4f} (rel. door) z={pos[2]:.4f} "
                f"{'inside' if depth > 0.0 else 'outside'}",
                flush=True,
            )

    window = None
    if entered_step is not None and exited_step is not None:
        window = (exited_step - entered_step) * dt

    # Speed in against speed out. The drive holds it constant, so these should
    # agree with `ball.speed` to the step: a shortfall means the shuttle is losing
    # steps to something, most likely reversing against a wall it should not touch.
    print(
        "gate_cage_ball inspect "
        f"entry_speed={'n/a' if entry_speed is None else f'{entry_speed:.4f}'} "
        f"exit_speed={'n/a' if exit_speed is None else f'{exit_speed:.4f}'} "
        f"speed_cmd={layout.ball_speed:.4f} "
        f"entered_step={entered_step} exited_step={exited_step} "
        f"window={'n/a' if window is None else f'{window:.2f}s'} "
        f"window_pred={layout.predicted_window(dt=dt):.2f}s "
        f"entry_delay_pred={layout.entry_delay():.2f}s "

        f"max_depth={max_depth:+.4f} at_step={max_depth_step} "
        f"turn_reach={max_depth:+.4f}/{layout.turn_y() - layout.door_y:+.4f} "
        f"final_depth={depth_of(float(entity_pos(ball)[1])):+.4f}",
        flush=True,
    )
    if passes:
        print("gate_cage_ball passes " + " ".join(
            f"#{i + 1}:t={a * dt:.2f}s v={v:.3f} dwell={((b - a) * dt) if b else float('nan'):.2f}s"
            for i, (a, b, v) in enumerate(passes)), flush=True)
    if window is None and entered_step is None:
        print(
            "[warn] the ball never crossed the doorway: check ball.speed, "
            "ball.release_y, and whether the shuttle is reversing early.",
            flush=True,
        )
    elif window is None:
        print(
            "[warn] the ball went in and did not come out within the rollout: "
            "either it is still inside (raise run.rollout_steps) or the shuttle "
            "never reversed at the far wall (check ball.stall_steps).",
            flush=True,
        )


@hydra.main(version_base="1.3", config_path="../../configs", config_name="gate_cage_ball")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"gate_cage_ball_config -> {resolved}", flush=True)

    if cfg.run.randomize_layout:
        cfg = randomize_task_cfg(cfg, "gate_cage_ball", cfg.run.seed, difficulty=cfg.run.difficulty)

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
    layout = ball_scene.layout

    # Hold the arm at its home pose. Without this the Franka is in the scene with
    # no joint targets at all and collapses under gravity on the first step -- it
    # takes no part in this demo, but it still has to be driven.
    initialize_franka_controller(
        scene=ball_scene.scene,
        manifest=ball_scene.manifest,
        robot_cfg=cfg.robot_control,
        # `static_only` promises not to step, and settling steps. Resetting home
        # writes the joint positions directly, so a zero-step settle still leaves
        # the arm standing where it belongs for a build-time look.
        settle_steps=0 if cfg.run.static_only else int(cfg.task.physical.settle_steps),
    )
    reset_ball(ball_scene)

    print(
        "gate_cage_ball setup "
        f"door_y={layout.door_y:+.3f} flat_end_y={layout.flat_end_y:+.3f} "
        f"inner_width={layout.inner_width:.3f} ball_r={layout.ball_radius:.3f} "
        f"release_y={float(cfg.task.ball.release_y):+.3f} "
        f"speed={layout.ball_speed:.3f}m/s entry_delay={layout.entry_delay():.2f}s "
        f"window={layout.predicted_window():.2f}s",
        flush=True,
    )
    if cfg.run.randomize_layout:
        # Same line as the physical demo prints (the variation sweep script reads both).
        task = cfg.task
        print(
            f"gate_cage_ball variant seed={int(cfg.run.seed)} speed={layout.ball_speed:.3f} "
            f"flat_end_y={float(task.channel.flat_end_y):+.4f} release_y={float(task.ball.release_y):+.4f} "
            f"center_x={float(task.channel.center_x):+.4f} rack_x={float(task.gate_rack.center_x):+.4f} "
            f"rack_y={float(task.gate_rack.center_y):+.4f} "
        f"slope={float(task.channel.entry_slope_deg):.1f} drive={int(layout.drive)} open_end={int(task.channel.open_end)} "
        f"rack_side={int(task.gate_rack.side)} entry_delay={layout.entry_delay():.2f} "
            f"window={layout.predicted_window():.2f} hover_wait={layout.hover_wait():+.2f} "
            f"slack={layout.ready_margin():+.2f}",
            flush=True,
        )


    if stop_before_physics(cfg, ball_scene.scene, "gate_cage_ball_inspect_demo"):
        raise SystemExit(0)

    state = {"phase": "settle", "ball_y": 0.0, "inside": False}
    with recording_session_from_config(
        ball_scene.scene, ball_scene.cameras, cfg.recording, hud=_hud(ball_scene, state)
    ):
        if cfg.run.static_only:
            # Build-and-look: no stepping at all, so the scene is inspected exactly
            # as constructed. Anything that interpenetrates at build time shows up
            # here rather than being hidden by the first settle.
            print("gate_cage_ball static_only=true; not stepping.", flush=True)
        else:
            state["phase"] = "rollout"
            lane_lo, lane_hi = layout.lane_bounds()
            world_y = lambda c: float(layout.position_to_world((0.0, layout.lane_y(c), 0.0))[1])
            if layout.drive:
                shuttle = BallShuttle(
                    ball_scene.scene,
                    ball_scene.ball_entity(),
                    speed=layout.ball_speed,
                    radius=layout.ball_radius,
                    lane_min_y=float(layout.position_to_world((0.0, lane_lo, 0.0))[1]),
                    lane_max_y=float(layout.position_to_world((0.0, lane_hi, 0.0))[1]),
                    direction=int(layout.inward),
                    entry_speed=layout.entry_speed(),
                    entry_accel=layout.ramp_accel(),
                    entry_sag=layout.ramp_sag(),
                    ramp_end_y=world_y(layout.ramp_end_y()),
                    door_y=world_y(layout.door_y),
                    dt=float(cfg.env.sim.dt),
                    stall_steps=int(cfg.task.ball.stall_steps),
                    offtrack_decel=float(cfg.task.ball.offtrack_decel),
                )
            else:
                shuttle = WallRestitution(
                    ball_scene.scene,
                    ball_scene.ball_entity(),
                    restitution=layout.wall_restitution,
                    radius=layout.ball_radius,
                    far_wall_y=world_y(layout.turn_y()),
                    door_y=world_y(layout.door_y),
                    inward=int(layout.inward),
                    plate_band=layout.ball_radius + 0.5 * float(cfg.task.gate.thickness),
                    dt=float(cfg.env.sim.dt),
                    impact_speed_floor=float(cfg.task.ball.impact_speed_floor),
                )
            with shuttle:
                run_rollout(cfg, ball_scene, state)
                if layout.drive:
                    print(f"gate_cage_ball shuttle reversals={shuttle.reversals} "
                          f"driving={shuttle.driving}", flush=True)
                else:
                    print(f"gate_cage_ball bounces={shuttle.bounces} impact_speeds="
                          + ",".join(f"{v:.3f}" for v in shuttle.impact_speeds), flush=True)
        # Hold the final scene for the recording: with static_only nothing has
        # stepped yet, and a recorder that saw no frame writes no video.
        state["phase"] = "done"
        for _ in range(max(0, int(cfg.run.final_hold_steps))):
            ball_scene.scene.step()


    print_recording_saved(cfg.recording)
    while cfg.run.keep_open and show_viewer:
        ball_scene.scene.step()


if __name__ == "__main__":
    main()
