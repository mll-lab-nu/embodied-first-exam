"""Does the roll stay on the bar when it is let go? (docx 1.3, gate before anything else)

`cloth_unroll` does not wind its roll -- the spiral is authored into the control
mesh and the dispenser is built around it. That is what makes the scene cheap and
repeatable, and it buys three questions in return. Until they are answered nothing
downstream is worth writing:

1. **Does the cloth start out intersecting the bar?** The innermost turn is
   authored `roll.clearance` outside the bar's surface. Too little and PBD spends
   its first step resolving a collision with a rigid body rather than settling;
   `cloth_unpleat` learned the same lesson about cloth against cloth.
2. **Does the roll stay wound?** Genesis 1.2.1 ignores `bending_compliance`
   entirely (measured 2026-08-23 across seven orders of magnitude), so nothing
   holds a curl. The bar supports the innermost turn, which a free roll has
   nothing to stand on -- but the outer turns can still sag off, and the band can
   slide along the bar or drop off its end.
3. **Does it unwind by itself?** `bending_relaxation` drives the cloth toward a
   FLAT rest angle, which on a roll means the constraint is actively unwinding it.
   1.2 measured a pleat's span growing 199 -> 251 mm in two seconds at 0.5. It is
   0 here for that reason, and this checks the setting took.

Nothing here judges the task. It answers whether the task can exist.

    python -B -m tests.roll_settle_spike
    python -B -m tests.roll_settle_spike run.viewer=true
    python -B -m tests.roll_settle_spike recording=hq \\
        recording.path=runs/videos/cloth_unroll/settle.mp4 \\
        recording.camera=[oblique,front]

The robot is not built: nothing touches the cloth here, and leaving it out keeps
the scene build short. Pass `run.include_robot=true` to see the dispenser next to
the arm at the height it will be reached from.
"""

from __future__ import annotations

import os

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.supervision import stop_before_physics
from topogym.supervision.pbd_probe import probe_particles, probe_velocities
from topogym.tasks import ClothUnrollSceneBuilder
from topogym.tasks.deformation.cloth_unroll import band_particles
from topogym.utils import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification.cloth_fold_verifier import layer_report
from topogym.verification.cloth_unpleat_verifier import single_layer_fraction, spread_span


def on_bar(nodes, layout, reach: float) -> np.ndarray:
    """Indices of particles still wrapped on the bar, within ``reach`` of its axis.

    Distance is measured in the plane perpendicular to the bar, so a particle's
    position along the bar does not matter -- material that has slid sideways is
    still wound.
    """

    nodes = np.asarray(nodes, dtype=float)
    axis = layout.material_axis
    centre = layout.bar_centre()
    offset = np.stack(
        [nodes[:, axis] - centre[axis], nodes[:, 2] - layout.bar_height()], axis=1
    )
    return np.flatnonzero(np.linalg.norm(offset, axis=1) <= float(reach))


def roll_radius(nodes, layout) -> float:
    """How far the outermost wound particle sits from the bar's axis."""

    nodes = np.asarray(nodes, dtype=float)
    axis = layout.material_axis
    centre = layout.bar_centre()
    offset = np.stack(
        [nodes[:, axis] - centre[axis], nodes[:, 2] - layout.bar_height()], axis=1
    )
    radius = np.linalg.norm(offset, axis=1)
    wound = radius <= float(layout.task_cfg.dispenser.bar_radius) + 0.040
    return float(radius[wound].max()) if wound.any() else 0.0


def sample_line(label: str, nodes, velocity, layout, cfg, step: int, reach: float) -> str:
    layers = layer_report(
        nodes,
        layout.table_z,
        float(cfg.task.success.cell),
        float(cfg.task.cloth.particle_size),
    )
    speed = float(np.linalg.norm(np.asarray(velocity, dtype=float), axis=1).max())
    return (
        f"roll_settle_spike {label} step={step} "
        f"on_bar={len(on_bar(nodes, layout, reach))} "
        f"roll_r_mm={roll_radius(nodes, layout) * 1e3:.2f} "
        f"span_mm={spread_span(nodes, layout.material_axis) * 1e3:.1f} "
        f"single_layer_frac={single_layer_fraction(layers):.3f} "
        f"max_layers={layers['max_layers']} "
        f"multi_cells={layers['over_layer_cells']} "
        f"max_speed={speed:.3f} "
        f"lowest_mm={(float(np.asarray(nodes)[:, 2].min()) - layout.table_z) * 1e3:+.2f}"
    )


@hydra.main(version_base="1.3", config_path="../configs", config_name="roll_settle_spike")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"roll_settle_spike_config -> {resolved}", flush=True)

    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    show_viewer = bool(cfg.run.viewer and has_display)
    if cfg.run.viewer and not show_viewer:
        print("[warn] no display detected; falling back to headless.", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(
        backend=backends[str(cfg.env.genesis.backend)],
        precision=str(cfg.env.genesis.precision),
    )

    # The builder prints the remesh report, the mesh's edge spread and the layout
    # in one line -- the interpenetration question is answered by the first
    # sample below, before any stepping.
    band = ClothUnrollSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        show_viewer=show_viewer, include_robot=bool(cfg.run.include_robot)
    )
    layout = band.layout
    if stop_before_physics(cfg, band.scene, "roll_settle_spike"):
        return

    # What the solver was actually handed. Printed because a sweep that produces
    # identical readings has two explanations -- the parameter does nothing, or
    # the override never arrived -- and they are not separable from the numbers.
    cloth_cfg = cfg.task.cloth
    print(
        f"roll_settle_spike material rho={float(cloth_cfg.rho)} "
        f"bending_compliance={float(cloth_cfg.bending_compliance):.3e} "
        f"bending_relaxation={float(cloth_cfg.bending_relaxation)} "
        f"cloth_mu={float(cloth_cfg.static_friction)}/{float(cloth_cfg.kinetic_friction)} "
        f"particle_size={float(cloth_cfg.particle_size)} "
        f"substeps={int(cfg.env.sim.substeps)} dt={float(cfg.env.sim.dt)}",
        flush=True,
    )
    marks = layout.landmarks()
    print(
        f"roll_settle_spike design roll_dia_mm={2 * marks['roll_radius'] * 1e3:.1f} "
        f"rolled_mm={marks['rolled'] * 1e3:.1f} "
        f"span_mm={marks['plan_span'] * 1e3:.1f} "
        f"material_mm={marks['material_length'] * 1e3:.1f} "
        f"bar_dia_mm={2 * float(cfg.task.dispenser.bar_radius) * 1e3:.1f} "
        f"clearance_mm={float(cloth_cfg.roll.clearance) * 1e3:.1f} "
        f"grid={band.grid[0]}x{band.grid[1]}",
        flush=True,
    )

    reach = float(cfg.task.dispenser.bar_radius) + float(cfg.run.on_bar_margin)
    spawn = band_particles(band)
    print(
        sample_line("spawn", spawn, np.zeros_like(spawn), layout, cfg, 0, reach),
        flush=True,
    )

    steps = max(1, int(cfg.run.settle_steps))
    every = max(1, int(cfg.run.sample_every))
    peak_speed = 0.0
    with recording_session_from_config(band.scene, band.cameras, cfg.recording):
        for step in range(1, steps + 1):
            band.scene.step()
            if step % every == 0 or step == steps:
                nodes = probe_particles(band.cloth)
                velocity = probe_velocities(band.cloth)
                peak_speed = max(
                    peak_speed,
                    float(np.linalg.norm(np.asarray(velocity, dtype=float), axis=1).max()),
                )
                print(
                    sample_line("settle", nodes, velocity, layout, cfg, step, reach),
                    flush=True,
                )
    print_recording_saved(cfg.recording)

    final = band_particles(band)
    layers = layer_report(
        final,
        layout.table_z,
        float(cfg.task.success.cell),
        float(cfg.task.cloth.particle_size),
    )
    span = spread_span(final, layout.material_axis)
    spread = span / float(cfg.task.cloth.material_length)
    stored_ok = spread <= float(cfg.task.grasp.max_start_spread_ratio)
    layers_ok = int(layers["over_layer_cells"]) >= int(
        cfg.task.grasp.min_start_three_layer_cells
    )
    wound = len(on_bar(final, layout, reach))

    # Order matters, and `diverged` comes first: a cloth that has left the scene
    # would otherwise be reported as a perfectly wound roll, since nothing is on
    # the bar and nothing is stored. Same lesson as `pleat_settle_spike`, where
    # a blown-up cloth was called `stands`.
    if peak_speed > float(cfg.run.max_speed) or float(np.asarray(final)[:, 2].min()) - layout.table_z < -float(cfg.task.cloth.particle_size):
        verdict = "diverged"
    elif wound < int(cfg.run.min_on_bar):
        verdict = "fell_off"
    elif not stored_ok:
        verdict = "unwound"
    elif not layers_ok:
        verdict = "layers_lost"
    else:
        verdict = "intact"
    print(
        f"roll_settle_spike verdict={verdict} "
        f"on_bar={wound} min={int(cfg.run.min_on_bar)} "
        f"spread_ratio={spread:.3f} max={float(cfg.task.grasp.max_start_spread_ratio)} "
        f"multi_cells={int(layers['over_layer_cells'])} "
        f"min={int(cfg.task.grasp.min_start_three_layer_cells)} "
        f"roll_r_mm={roll_radius(final, layout) * 1e3:.2f} "
        f"design_r_mm={marks['roll_radius'] * 1e3:.2f} "
        f"peak_speed={peak_speed:.3f}",
        flush=True,
    )

    while cfg.run.keep_open and show_viewer:
        band.scene.step()
    raise SystemExit(0 if verdict == "intact" else 1)


if __name__ == "__main__":
    main()
