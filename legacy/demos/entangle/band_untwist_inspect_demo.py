"""Scene inspector for band_untwist (no robot motion).

Builds the crossed rope on the table (`task.band.shape`), settles it under
gravity, prints the self-crossing reading, then holds the rope still for
``run.hold_steps`` and re-reads it every ``run.hold_every`` steps. That hold is
the question the whole task rests on -- the closed-band version of this scene
sprang flat on its own (`tests/closed_band_spike.py`, 2026-08-21) -- so the line
to look at is ``band_untwist_hold``: the crossing sequence must stay the one the
generator built for the entire hold.

Configuration is Hydra (`configs/band_untwist_inspect.yaml`).

    python -m demos.entangle.band_untwist_inspect_demo run.viewer=true run.keep_open=true
    python -m demos.entangle.band_untwist_inspect_demo task.band.shape=twist
    python -m demos.entangle.band_untwist_inspect_demo run.randomize_layout=true run.seed=3 run.static_only=true recording=default
    python -m demos.entangle.band_untwist_inspect_demo --cfg job
"""

from __future__ import annotations

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.generation.layout_randomization import randomize_task_cfg
from topogym.supervision import rope_blow_ups, stop_before_physics
from topogym.supervision.band_untwist import crossing_lines, variant_line
from topogym.supervision.untangle_continuous import rope_health_lines
from topogym.tasks_legacy import BandUntwistSceneBuilder, settle_scene
from topogym.utils import (
    apply_recording_camera_overrides,
    initialize_franka_controller,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import BandUntwistPuzzleEvaluator

TASK_ID = "band_untwist"


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
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"band_untwist_inspect_config -> {resolved}", flush=True)

    if cfg.run.randomize_layout:
        cfg = randomize_task_cfg(cfg, TASK_ID, cfg.run.seed, difficulty=cfg.run.difficulty)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)])

    builder = BandUntwistSceneBuilder(cfg.env, cfg.task, cfg.robot_control, seed=cfg.run.seed)
    spawn = builder.layout.rope_mesh()
    print(
        f"band_untwist_spawn arc={np.linalg.norm(np.diff(spawn.centerline, axis=0), axis=1).sum() * 1000:.0f}mm "
        f"samples={len(spawn.centerline)} min_bend_radius={_min_bend_radius(spawn.centerline) * 1000:.1f}mm "
        f"end_separation={np.linalg.norm(spawn.endpoint_centers[0][:2] - spawn.endpoint_centers[1][:2]) * 1000:.0f}mm "
        f"shape={builder.layout.shape} declared={builder.layout.declared_sequence()}"
    )
    layout = builder.layout
    print(
        f"{TASK_ID} checks "
        + " ".join(f"{name}={measured:+.4f}/{limit:+.4f}/{'ok' if ok else 'FAIL'}"
                   for name, measured, limit, ok in layout.checks()),
        flush=True,
    )
    if cfg.run.randomize_layout:
        # Same line as the physical demo prints (the variation sweep script reads both).
        print(variant_line(cfg.task, layout, seed=int(cfg.run.seed)), flush=True)

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

    with recording_session_from_config(rope_scene.scene, rope_scene.cameras, cfg.recording):
        if cfg.run.static_only:
            # Build-and-look: no settling, no hold. The scene is inspected exactly
            # as constructed; a few steps only so the recorder has frames to write.
            print(f"{TASK_ID} static_only=true; not settling or holding.", flush=True)
            for _ in range(max(0, int(cfg.run.final_hold_steps))):
                rope_scene.scene.step()
            print_recording_saved(cfg.recording)
            return
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
        declared = tuple(layout.declared_sequence())
        readings = []
        for step in range(1, hold_steps + 1):
            rope_scene.scene.step()
            if step % hold_every == 0 or step == hold_steps:
                state = evaluator.classify(rope_scene)
                readings.append(state.crossing_sequence)
                gaps = " ".join(f"{c.z_gap * 1000:.1f}mm" for c in state.crossings) or "-"
                print(
                    f"band_untwist_hold step={step:>4} self_crossings={state.crossing_count} "
                    f"z_gap={gaps} ends_on_table={state.ends_on_table}"
                )
        if hold_steps:
            held = all(reading == declared for reading in readings)
            print(
                f"band_untwist_hold_verdict {'PASS' if held else 'FAIL'}: "
                f"counts={[len(r) // 2 for r in readings]} declared={declared} over {hold_steps} steps"
            )
        for blow_up in rope_blow_ups(rope_scene, tolerance=float(cfg.task.pinch.blow_up_tolerance)):
            print(f"  BLOW-UP {blow_up}")

    print_recording_saved(cfg.recording)

    if cfg.run.keep_open or cfg.run.viewer:
        while True:
            rope_scene.scene.step()


if __name__ == "__main__":
    main()
