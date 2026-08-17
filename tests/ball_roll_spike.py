"""How does a rigid sphere behave on the TopoGym tabletop?

DIAGNOSTIC TOOL, not a task. `docs/develop/tasks/rigid_first_track_zh.md` §7.2
lists this as the first action for docx 4.1 (`gate_cage_ball`): the repo contains
no `gs.morphs.Sphere` anywhere, so rolling, stopping and bouncing are all
unmeasured, and 4.1's fence size, ball speed and insertion timing all depend on
them.

Two properties are NOT configurable in Genesis' rigid solver and therefore have
to be measured rather than chosen:

- **Rolling resistance.** No knob exists. A sphere may roll until it leaves the
  table. 4.1 needs the ball still moving when the arm reaches the slot, so
  "rolls a long way" is usable and "stops in 10 cm" is not.
- **Restitution between two rigid bodies.** `gs.materials.Rigid.coup_restitution`
  applies to coupling with OTHER solvers (IPC/PBD), not to rigid-vs-rigid. What a
  rigid ball does when dropped is whatever the constraint solver does.

The tabletop preset is used as-is (dt=0.01, substeps=4). Numbers measured under a
different sim configuration cannot size 4.1's fence, which is the point of
measuring. The robot is left out (`include_robot=False`): it takes no part in
rolling and its collision geometry slows every step.

    python -m tests.ball_roll_spike run.verbose=true
    python -m tests.ball_roll_spike run.test=roll run.speed=0.6
    python -m tests.ball_roll_spike run.test=roll run.spin=sliding
    python -m tests.ball_roll_spike run.viewer=true run.keep_open=true
    python -m tests.ball_roll_spike -m task.ball.friction=0.1,0.4,1.0   # sweep

Prints one `ball_roll_spike <test>` summary line per test, plus sampled
trajectory lines under `run.verbose=true`.
"""

from __future__ import annotations

import os

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.world import StandardTabletopSceneBuilder, materials


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def ball_pos(ball) -> np.ndarray:
    return _as_numpy(ball.get_pos()).reshape(-1, 3)[0].astype(float)


def ball_speed(ball) -> float:
    return float(np.linalg.norm(_as_numpy(ball.get_vel()).reshape(-1, 3)[0]))


def table_top_rect(env_cfg) -> tuple[np.ndarray, np.ndarray]:
    """The table's top face as (min_xy, max_xy) in world coordinates."""

    center = np.asarray(list(env_cfg.world.table.pos), dtype=float)
    size = np.asarray(list(env_cfg.world.table.size), dtype=float)
    return center[:2] - 0.5 * size[:2], center[:2] + 0.5 * size[:2]


def place(ball, world_xyz, *, velocity=None) -> None:
    """Put the ball somewhere with a chosen velocity, leaving nothing carried over.

    `set_pos(zero_velocity=True)` clears the previous test's motion; the free body
    has 6 dofs (3 linear, then 3 angular), so a velocity is written as one vector
    over all of them.
    """

    ball.set_pos(tuple(float(v) for v in world_xyz), zero_velocity=True)
    ball.zero_all_dofs_velocity()
    if velocity is not None:
        ball.set_dofs_velocity(np.asarray(velocity, dtype=float))


def run_roll(cfg, scene, ball, origin, radius, verbose: bool) -> None:
    """Give the ball a push and watch how far it gets.

    Rolls along +y: the table spans 1.4 m in y against 1.5 m in x, and starting
    at y=-0.30 leaves about 1.0 m of runway before the edge.
    """

    speed = float(cfg.run.speed)
    start = origin + np.array([float(cfg.task.ball.start_xy[0]),
                               float(cfg.task.ball.start_xy[1]), radius])
    # Rolling without slipping along +y needs spin about -x at v/r: the contact
    # point sits one radius below the centre, so its velocity is v + omega_x * r,
    # and that has to vanish. `sliding` starts with no spin at all, which measures
    # how quickly friction converts sliding into rolling -- a ball that never
    # converts would slide to a halt instead of running on.
    omega_x = -speed / radius if str(cfg.run.spin) == "rolling" else 0.0
    place(ball, start, velocity=[0.0, speed, 0.0, omega_x, 0.0, 0.0])

    # The free joint's 6 dofs are written as one vector, and this assumes the
    # linear three come first (the MuJoCo convention Genesis largely follows).
    # That ordering is not stated in the installed source, so it is checked here
    # rather than assumed: `get_vel` is the documented linear-velocity getter, so
    # if the commanded speed comes back on it the layout is linear-first, and if
    # it comes back near zero the two triples are the other way round and every
    # roll number below is measuring a spin in place.
    readback = _as_numpy(ball.get_vel()).reshape(-1, 3)[0]
    print(
        f"ball_roll_spike dof_check commanded_linear=(0.000, {speed:.3f}, 0.000) "
        f"readback_linear=({readback[0]:+.4f}, {readback[1]:+.4f}, {readback[2]:+.4f}) "
        f"layout={'linear_first' if abs(float(readback[1]) - speed) < 1e-3 else 'UNEXPECTED'}",
        flush=True,
    )

    lo, hi = table_top_rect(cfg.env)
    sample_every = max(1, int(cfg.run.sample_every))
    stop_speed = float(cfg.run.stop_speed)
    steps = int(cfg.run.roll_steps)

    stopped_at = None
    left_table_at = None
    for step in range(1, steps + 1):
        scene.step()
        pos = ball_pos(ball)
        vel = ball_speed(ball)
        if verbose and step % sample_every == 0:
            print(
                f"[ball_roll step={step:4d}] t={step * float(cfg.env.sim.dt):5.2f}s "
                f"pos=({pos[0]:+.4f}, {pos[1]:+.4f}, {pos[2]:+.4f}) speed={vel:.4f}",
                flush=True,
            )
        if left_table_at is None and (np.any(pos[:2] < lo) or np.any(pos[:2] > hi)):
            left_table_at = step
            break
        if stopped_at is None and vel <= stop_speed:
            stopped_at = step
            break

    end = ball_pos(ball)
    travelled = float(np.linalg.norm(end[:2] - start[:2]))
    print(
        f"ball_roll_spike roll spin={cfg.run.spin} v0={speed:.3f} "
        f"friction={float(cfg.task.ball.friction):.3f} "
        f"travelled={travelled:.4f}m final_speed={ball_speed(ball):.4f} "
        f"stopped_at_step={stopped_at} left_table_at_step={left_table_at} "
        f"steps_run={steps if (stopped_at or left_table_at) is None else (stopped_at or left_table_at)} "
        f"z={end[2]:.5f} (rest z={radius:.5f})",
        flush=True,
    )


def run_drop(cfg, scene, ball, origin, radius, verbose: bool) -> None:
    """Drop it and record the bounce, plus how far the surface is penetrated.

    `min_z` is the tunnelling check: the centre should never get closer to the
    table than one radius by more than solver penetration. A `min_z` near zero
    means the ball went through.
    """

    height = float(cfg.run.drop_height)
    start = origin + np.array([0.0, 0.0, radius + height])
    place(ball, start)

    sample_every = max(1, int(cfg.run.sample_every))
    table_z = float(origin[2])
    min_z = float("inf")
    apex_after_contact = None
    contacted = False
    for step in range(1, int(cfg.run.drop_steps) + 1):
        scene.step()
        z = float(ball_pos(ball)[2]) - table_z
        min_z = min(min_z, z)
        if not contacted and z <= radius * 1.02:
            contacted = True
            apex_after_contact = z
        elif contacted:
            apex_after_contact = max(apex_after_contact, z)
        if verbose and step % sample_every == 0:
            print(
                f"[ball_drop step={step:4d}] z_above_table={z:.5f} "
                f"speed={ball_speed(ball):.4f}",
                flush=True,
            )

    rebound = None if apex_after_contact is None else (apex_after_contact - radius)
    print(
        f"ball_roll_spike drop height={height:.3f} "
        f"min_z_above_table={min_z:.5f} (rest z={radius:.5f}, "
        f"penetration={max(0.0, radius - min_z) * 1e3:.2f}mm) "
        f"rebound={'n/a' if rebound is None else f'{rebound:.5f}m'} "
        f"rebound_ratio={'n/a' if rebound is None else f'{rebound / height:.3f}'} "
        f"final_speed={ball_speed(ball):.4f}",
        flush=True,
    )


def run_rest(cfg, scene, ball, origin, radius, verbose: bool) -> None:
    """Does a ball left alone stay put?

    A sphere resting on a plane is the case where a solver's residual jitter shows
    up as drift, and 4.1's timing is meaningless if the ball wanders on its own.
    """

    start = origin + np.array([0.0, 0.0, radius])
    place(ball, start)
    for step in range(1, int(cfg.run.rest_steps) + 1):
        scene.step()
        if verbose and step % max(1, int(cfg.run.sample_every)) == 0:
            pos = ball_pos(ball)
            print(
                f"[ball_rest step={step:4d}] drift_mm="
                f"{float(np.linalg.norm(pos[:2] - start[:2])) * 1e3:.3f} "
                f"speed={ball_speed(ball):.5f}",
                flush=True,
            )
    end = ball_pos(ball)
    print(
        f"ball_roll_spike rest steps={int(cfg.run.rest_steps)} "
        f"drift_mm={float(np.linalg.norm(end[:2] - start[:2])) * 1e3:.3f} "
        f"sink_mm={(radius - (end[2] - float(origin[2]))) * 1e3:.3f} "
        f"final_speed={ball_speed(ball):.5f}",
        flush=True,
    )


TESTS = {"roll": run_roll, "drop": run_drop, "rest": run_rest}


@hydra.main(version_base="1.3", config_path="../configs", config_name="ball_roll_spike")
def main(cfg: DictConfig) -> None:
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"ball_roll_spike_config -> {resolved}", flush=True)

    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    show_viewer = bool(cfg.run.viewer and has_display)
    if cfg.run.viewer and not show_viewer:
        print("[warn] no display detected; falling back to headless.", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)], precision=str(cfg.env.genesis.precision))

    builder = StandardTabletopSceneBuilder(cfg.env, cfg.robot_control)
    tabletop = builder.create(show_viewer=show_viewer, include_robot=False)
    scene = tabletop.scene

    ball_cfg = cfg.task.ball
    radius = float(ball_cfg.radius)
    origin = np.asarray(tabletop.frames.task_origin, dtype=float)
    ball = scene.add_entity(
        gs.morphs.Sphere(
            pos=tuple(origin + np.array([0.0, 0.0, radius])),
            radius=radius,
            fixed=False,
        ),
        material=gs.materials.Rigid(
            rho=float(ball_cfg.rho), friction=float(ball_cfg.friction)
        ),
        surface=materials.plastic("object", list(ball_cfg.color)),
        name="ball",
    )
    tabletop.manifest.add("ball", ball)
    builder.finalize(tabletop)

    selected = str(cfg.run.test)
    names = list(TESTS) if selected == "all" else [selected]
    if any(name not in TESTS for name in names):
        raise SystemExit(f"Unknown run.test={selected!r}; expected one of {list(TESTS)} or 'all'.")

    print(
        f"ball_roll_spike setup radius={radius:.4f} rho={float(ball_cfg.rho):.1f} "
        f"friction={float(ball_cfg.friction):.3f} dt={float(cfg.env.sim.dt):.4f} "
        f"substeps={int(cfg.env.sim.substeps)} tests={names}",
        flush=True,
    )
    for name in names:
        TESTS[name](cfg, scene, ball, origin, radius, bool(cfg.run.verbose))

    while cfg.run.keep_open and show_viewer:
        scene.step()


if __name__ == "__main__":
    main()
