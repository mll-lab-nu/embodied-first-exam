"""Scene inspector for band_untwist (no robot motion).

Builds the figure-8 rope on the table, settles it under gravity, prints the
self-crossing reading, then holds the rope still for ``run.hold_steps`` and
re-reads it every ``run.hold_every`` steps. That hold is the question the whole
task rests on -- the closed-band version of this scene sprang flat on its own
(`tests/closed_band_spike.py`, 2026-08-21) -- so the line to look at is
``band_untwist_hold``: the count must stay 1 for the entire hold.

Configuration is Hydra (`configs/band_untwist_inspect.yaml`).

    python -m demos.entangle.band_untwist_inspect_demo run.viewer=true run.keep_open=true
    python -m demos.entangle.band_untwist_inspect_demo task.figure_eight.half_angle_deg=40
    python -m demos.entangle.band_untwist_inspect_demo --cfg job
"""

from __future__ import annotations

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.supervision import rope_blow_ups, stop_before_physics
from topogym.supervision.band_untwist import crossing_lines
from topogym.supervision.untangle_continuous import rope_health_lines
from topogym.tasks import BandUntwistSceneBuilder, settle_scene
from topogym.utils import initialize_franka_controller
from topogym.verification import BandUntwistPuzzleEvaluator


def _min_bend_radius(centerline: np.ndarray) -> float:
    """Smallest circumradius over consecutive centerline triples, metres."""

    p = np.asarray(centerline, dtype=float)
    a, b, c = p[:-2], p[1:-1], p[2:]
    ab = np.linalg.norm(b - a, axis=1)
    bc = np.linalg.norm(c - b, axis=1)
    ca = np.linalg.norm(a - c, axis=1)
    cross = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        radii = np.where(cross < 1e-12, np.inf, ab * bc * ca / (2.0 * cross))
    return float(np.min(radii))


@hydra.main(version_base="1.3", config_path="../../configs", config_name="band_untwist_inspect")
def main(cfg: DictConfig) -> None:
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"band_untwist_inspect_config -> {resolved}", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)])

    builder = BandUntwistSceneBuilder(cfg.env, cfg.task, cfg.robot_control, seed=cfg.run.seed)
    spawn = builder.layout.rope_mesh()
    print(
        f"band_untwist_spawn arc={np.linalg.norm(np.diff(spawn.centerline, axis=0), axis=1).sum() * 1000:.0f}mm "
        f"samples={len(spawn.centerline)} min_bend_radius={_min_bend_radius(spawn.centerline) * 1000:.1f}mm "
        f"end_separation={np.linalg.norm(spawn.endpoint_centers[0][:2] - spawn.endpoint_centers[1][:2]) * 1000:.0f}mm "
        f"over_end={builder.layout.over_end}"
    )

    rope_scene = builder.build(show_viewer=cfg.run.viewer, include_robot=not cfg.run.no_robot)

    if not cfg.run.no_robot:
        # MUST happen before any stepping: without the controller the arm is an
        # unactuated linkage that collapses onto the table, sweeping the rope.
        initialize_franka_controller(
            scene=rope_scene.scene,
            manifest=rope_scene.manifest,
            robot_cfg=cfg.robot_control,
        )

    for line in rope_health_lines(rope_scene, particle_size=float(cfg.task.rope.particle_size)):
        print(line)

    steps, moved = settle_scene(rope_scene)
    evaluator = BandUntwistPuzzleEvaluator.from_config(cfg.task)
    state = evaluator.classify(rope_scene)
    ok, detail = evaluator.matches_spawn_ground_truth(rope_scene)
    print(
        f"band_untwist_inspect settle_steps={steps} max_particle_step={moved:.6f} "
        f"self_crossings={state.crossing_count} ends_on_table={state.ends_on_table} "
        f"gt_match={ok} {detail}"
    )
    for line in crossing_lines(
        state,
        rope_radius=float(cfg.task.rope.radius),
        d_hat=float(cfg.task.rope.fem.contact_d_hat),
    ):
        print(line)

    if stop_before_physics(cfg, rope_scene.scene, "band_untwist_inspect_demo"):
        return

    hold_steps = int(cfg.run.hold_steps)
    hold_every = max(1, int(cfg.run.hold_every))
    counts = []
    for step in range(1, hold_steps + 1):
        rope_scene.scene.step()
        if step % hold_every == 0 or step == hold_steps:
            state = evaluator.classify(rope_scene)
            counts.append(state.crossing_count)
            gap = state.crossings[0].z_gap * 1000 if state.crossings else float("nan")
            print(
                f"band_untwist_hold step={step:>4} self_crossings={state.crossing_count} "
                f"z_gap={gap:.1f}mm ends_on_table={state.ends_on_table}"
            )
    if hold_steps:
        held = all(count == 1 for count in counts)
        print(
            f"band_untwist_hold_verdict {'PASS' if held else 'FAIL'}: counts={counts} "
            f"over {hold_steps} steps"
        )
    for blow_up in rope_blow_ups(rope_scene, tolerance=float(cfg.task.pinch.blow_up_tolerance)):
        print(f"  BLOW-UP {blow_up}")

    if cfg.run.keep_open or cfg.run.viewer:
        while True:
            rope_scene.scene.step()


if __name__ == "__main__":
    main()
