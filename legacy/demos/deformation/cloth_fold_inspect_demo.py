"""Scene inspector for cloth_fold (docx 1.1「折角」): builds it, does not fold it.

Its job is to answer "does the layout make sense" and "does the cloth look and
behave like cloth", without spending a fold on either question.

What to look for:

  - the sheet lands flat on the table and drapes -- watch how it falls. A cloth
    ripples and settles into small wrinkles; a slab of modelling clay drops as
    one piece and stays smooth. This is the most direct read on the material
    there is, which is why the sheet is dropped from a height by default rather
    than spawned at rest;
  - the surface shows a weave, not one flat colour;
  - the GREEN marker is on the corner the gripper takes, and the whole marker
    sits over material rather than half off the edge;
  - the ORANGE marker is on the diagonally opposite corner -- where that corner
    has to end up;
  - the BLUE bar runs along the diagonal between the other two corners. That is
    where the crease has to land, and the judges measure against it.

Recording captures one frame per simulation step, so a still scene records
nothing: the drop and the hold after it are what there is to see. On a machine
with no display this is the only way to look at the scene at all.

`run.show_target` reflects the cloth into its finished pose -- not a simulation,
just the analytic target the primary judge scores against, which is a quick way
to see whether the target itself is sane.

    python -B -m demos.deformation.cloth_fold_inspect_demo run.viewer=true
    python -B -m demos.deformation.cloth_fold_inspect_demo \\
        recording=hq recording.camera=[oblique,topdown]
    python -B -m demos.deformation.cloth_fold_inspect_demo --cfg job
"""

from __future__ import annotations

import time

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig, OmegaConf

from topogym.core import save_resolved_config
from topogym.supervision import stop_before_physics
from topogym.tasks_legacy import ClothFoldSceneBuilder, cloth_particles, settle_cloth
from topogym.utils import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import ClothFoldEvaluator, fold_targets


def _report(label: str, nodes: np.ndarray, table_z: float) -> None:
    heights = nodes[:, 2] - table_z
    print(
        f"cloth_fold_inspect {label} "
        f"lowest_mm={heights.min() * 1e3:.2f} peak_mm={heights.max() * 1e3:.2f} "
        f"flatness_var={float(np.var(heights)):.3e} "
        f"bbox_x=[{nodes[:, 0].min():+.3f},{nodes[:, 0].max():+.3f}] "
        f"bbox_y=[{nodes[:, 1].min():+.3f},{nodes[:, 1].max():+.3f}]",
        flush=True,
    )


@hydra.main(version_base="1.3", config_path="../../configs", config_name="cloth_fold_inspect")
def main(cfg: DictConfig) -> None:
    # Camera resolution has to reach the env before the scene is built.
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"cloth_fold_inspect_config -> {resolved}", flush=True)

    if cfg.run.drop_from is not None:
        # A viewing choice, not a scene change: the task spawns the sheet at its
        # resting height, where nothing moves and there is nothing to watch.
        OmegaConf.set_readonly(cfg, False)
        OmegaConf.set_struct(cfg, False)
        cfg.task.cloth.z = float(cfg.run.drop_from)
        print(
            f"cloth_fold_inspect drop_from={float(cfg.run.drop_from) * 1e3:.0f}mm "
            f"(task default is {2.0:.0f}mm, the resting height)",
            flush=True,
        )

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(
        backend=backends[str(cfg.env.genesis.backend)],
        precision=str(cfg.env.genesis.precision),
    )

    cloth_scene = ClothFoldSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        show_viewer=cfg.run.viewer, markers=True
    )
    layout = cloth_scene.layout
    if stop_before_physics(cfg, cloth_scene.scene, "cloth_fold_inspect"):
        return

    _report("spawned", cloth_particles(cloth_scene), layout.table_z)

    with recording_session_from_config(
        cloth_scene.scene, cloth_scene.cameras, cfg.recording
    ):
        rest = settle_cloth(cloth_scene, int(cfg.task.success.settle_steps))
        _report(f"settled steps={int(cfg.task.success.settle_steps)}", rest, layout.table_z)

        if cfg.run.show_target:
            targets = fold_targets(
                rest,
                layout.fold_point(),
                layout.fold_normal(),
                float(cfg.task.cloth.particle_size),
            )
            indices = list(range(len(targets)))
            cloth_scene.cloth.set_particles_pos(targets, particles_idx_local=indices)
            # Whatever the sheet was doing is not what this pose implies; leaving
            # the old velocities in would have the solver fight the write.
            cloth_scene.cloth.set_particles_vel(
                np.zeros_like(targets), particles_idx_local=indices
            )
            print("cloth_fold_inspect showing the analytic fold target", flush=True)

        # A still tail, so the last frames are a steady shot rather than whatever
        # the sheet happened to be doing when the settle ran out.
        for _ in range(max(0, int(cfg.run.hold_steps))):
            cloth_scene.scene.step()

    # What a judge would say about what is on screen. Before a fold this reads as
    # a failure, and that is the point: it shows the readings the episode starts
    # from, so a finished one has something to be compared with.
    state = ClothFoldEvaluator.from_config(cfg.task).classify(
        rest,
        cloth_particles(cloth_scene),
        table_z=layout.table_z,
        fold_point=layout.fold_point(),
        fold_normal=layout.fold_normal(),
    )
    print(f"cloth_fold_inspect judges {state.summary()}", flush=True)
    print_recording_saved(cfg.recording)

    if cfg.run.keep_open_no_step:
        while True:
            time.sleep(0.05)
    elif cfg.run.keep_open or cfg.run.viewer:
        while True:
            cloth_scene.scene.step()


if __name__ == "__main__":
    main()
