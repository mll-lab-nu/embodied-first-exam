"""Does a built-in pleat survive being put down? (docx 1.2, gate before anything else)

`cloth_unpleat` does not fold its pleat -- it is authored into the control mesh,
which is what makes the scene cheap and repeatable. That buys one question in
return, and until it is answered nothing downstream is worth writing:

1. **What does Genesis' remesh do to this mesh?** `cloth_fold` measured 33x33
   flat + particle_size 0.004 as the one combination that keeps vertex order, and
   its config says outright that 「间距等于 particle_size」is not a sufficient
   condition and the combination must not be settled by reasoning. This mesh is
   36x17 and folded, so it is a different question.

   The stakes are LOWER here than in 1.1, and it is worth being exact about why.
   1.1's main judge is a per-particle distance to an analytic target, so it dies
   without vertex order. All three of 1.2's gates -- height, layer count, spread
   length -- read the point cloud and never ask which particle is which. What
   vertex order buys here is the carry-time stretch diagnostic and the exact form
   of `band_shift`; both have honest fallbacks. Measured 2026-08-22: a 36x17
   control mesh came back as 2344 particles where a clean one-level subdivision
   is 71x33 = 2343, so the grid arithmetic is simply unavailable and the demo
   says so on its own line rather than guessing.
2. **Does the pleat stand?** Three ways it can fail: it flattens itself, it
   springs open (PBD's bending constraint taking its rest angle from flat rather
   than from the mesh as built), or the solver diverges where the two arms meet
   at the crest, which is the one place in the mesh where material sits within a
   particle of itself. The first two are visible as the crest's height after
   settling; the third as particle speed and as material below the table.

Nothing here judges the task. It answers whether the task can exist.

    python -B -m tests.pleat_settle_spike
    python -B -m tests.pleat_settle_spike run.viewer=true
    python -B -m tests.pleat_settle_spike recording=hq \\
        recording.path=runs/videos/cloth_unpleat/settle.mp4 \\
        recording.camera=[oblique,front]

The robot is not built: nothing touches the cloth here, and leaving it out keeps
the scene build short. Pass `run.include_robot=true` to see the pleat next to the
arm at the height it will actually be grasped from.
"""

from __future__ import annotations

import os

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.supervision.pbd_probe import probe_particles, probe_velocities
from topogym.supervision import stop_before_physics
from topogym.tasks import ClothUnpleatSceneBuilder, band_particles
from topogym.utils import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification.cloth_fold_verifier import layer_report
from topogym.verification.cloth_unpleat_verifier import single_layer_fraction


def crest_height(nodes, table_z: float) -> float:
    """Highest point of the band above the table.

    The pleat is the only thing standing up, so the peak IS the crest until the
    pleat stops existing -- at which point this reading is the answer.
    """

    return float(np.asarray(nodes, dtype=float)[:, 2].max() - table_z)


def plan_span(nodes, axis: int) -> float:
    """How far the band reaches along its length. Grows if the pleat springs open."""

    values = np.asarray(nodes, dtype=float)[:, int(axis)]
    return float(values.max() - values.min())


def sample_line(
    label: str, nodes, velocity, table_z: float, cfg, step: int, axis: int
) -> str:
    layers = layer_report(
        nodes,
        table_z,
        float(cfg.task.success.cell),
        float(cfg.task.cloth.particle_size),
    )
    speed = float(np.linalg.norm(np.asarray(velocity, dtype=float), axis=1).max())
    return (
        f"pleat_settle_spike {label} step={step} "
        f"crest_mm={crest_height(nodes, table_z) * 1e3:.2f} "
        f"span_mm={plan_span(nodes, axis) * 1e3:.1f} "
        f"single_layer_frac={single_layer_fraction(layers):.3f} "
        f"max_layers={layers['max_layers']} "
        f"three_plus_cells={layers['over_layer_cells']} "
        f"max_speed={speed:.3f} "
        f"lowest_mm={(float(np.asarray(nodes)[:, 2].min()) - table_z) * 1e3:+.2f}"
    )


@hydra.main(version_base="1.3", config_path="../configs", config_name="pleat_settle_spike")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"pleat_settle_spike_config -> {resolved}", flush=True)

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

    # The builder prints the remesh report, the mesh's edge spread and the
    # layout in one line -- question 1 is answered there, before any stepping.
    band = ClothUnpleatSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        show_viewer=show_viewer, include_robot=bool(cfg.run.include_robot)
    )
    layout = band.layout
    table_z = layout.table_z
    if stop_before_physics(cfg, band.scene, "pleat_settle_spike"):
        return

    axis = layout.material_axis
    spawn = band_particles(band)
    print(
        sample_line("spawn", spawn, np.zeros_like(spawn), table_z, cfg, 0, axis),
        flush=True,
    )
    # What the mesh was authored to be, so the settled readings have something to
    # be a change FROM that does not depend on the simulator.
    marks = layout.landmarks()
    print(
        f"pleat_settle_spike design crest_mm={(marks['crest_z'] - float(cfg.task.cloth.z)) * 1e3:.1f} "
        f"span_mm={marks['plan_span'] * 1e3:.1f} "
        f"material_mm={marks['material_length'] * 1e3:.1f} "
        f"stored_mm={marks['stored'] * 1e3:.1f} "
        f"grid={band.grid[0]}x{band.grid[1]}",
        flush=True,
    )

    steps = max(1, int(cfg.run.settle_steps))
    every = max(1, int(cfg.run.sample_every))
    with recording_session_from_config(band.scene, band.cameras, cfg.recording):
        for step in range(1, steps + 1):
            band.scene.step()
            if step % every == 0 or step == steps:
                print(
                    sample_line(
                        "settle",
                        probe_particles(band.cloth),
                        probe_velocities(band.cloth),
                        table_z,
                        cfg,
                        step,
                        axis,
                    ),
                    flush=True,
                )
    print_recording_saved(cfg.recording)

    final = band_particles(band)
    design_crest = marks["crest_z"] - float(cfg.task.cloth.z)
    settled_crest = crest_height(final, table_z)
    kept = settled_crest / max(design_crest, 1e-9)
    # Both directions are failures and they need different fixes, so they are
    # named apart rather than reported as one distance.
    if kept < float(cfg.run.crest_keep_min):
        verdict = "collapsed"
    elif plan_span(final, axis) > marks["plan_span"] * float(cfg.run.span_grow_max):
        verdict = "sprang_open"
    else:
        verdict = "stands"
    print(
        f"pleat_settle_spike verdict={verdict} "
        f"crest_kept={kept:.3f} "
        f"crest_mm={settled_crest * 1e3:.2f} design_mm={design_crest * 1e3:.1f} "
        f"axis={'xy'[axis]} "
        f"span_mm={plan_span(final, axis) * 1e3:.1f} "
        f"design_span_mm={marks['plan_span'] * 1e3:.1f}",
        flush=True,
    )

    while cfg.run.keep_open and show_viewer:
        band.scene.step()
    raise SystemExit(0 if verdict == "stands" else 1)


if __name__ == "__main__":
    main()
