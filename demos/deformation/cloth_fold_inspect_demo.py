"""Scene inspector for cloth_fold (docx 1.1「折角」): builds it, does not move it.

What to look for in the viewer:

  - the sheet lies flat on the table, one particle-radius up, not sagging or
    hovering;
  - the GREEN marker is on the corner the gripper takes, and the whole marker
    sits over material rather than half off the edge;
  - the ORANGE marker is on the diagonally opposite corner -- where that corner
    has to end up;
  - the BLUE bar runs along the diagonal between the other two corners. That is
    where the crease has to land, and the judges measure against it.

`run.settle_steps` drops the sheet for that many steps first, so what is on
screen is the state the fold actually starts from. `run.show_target=true`
additionally reflects the cloth into its finished pose -- not a simulation, just
the analytic target the primary judge scores against, which is a quick way to see
whether the target itself is sane.

    python -B -m demos.deformation.cloth_fold_inspect_demo run.viewer=true
    python -B -m demos.deformation.cloth_fold_inspect_demo run.viewer=true run.show_target=true
    python -B -m demos.deformation.cloth_fold_inspect_demo --cfg job
"""

from __future__ import annotations

import time

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.supervision import stop_before_physics
from topogym.tasks import ClothFoldSceneBuilder, cloth_particles, settle_cloth
from topogym.verification import ClothFoldEvaluator, fold_targets


@hydra.main(version_base="1.3", config_path="../../configs", config_name="cloth_fold_inspect")
def main(cfg: DictConfig) -> None:
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"cloth_fold_inspect_config -> {resolved}", flush=True)

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

    rest = settle_cloth(cloth_scene, int(cfg.task.success.settle_steps))
    heights = rest[:, 2] - layout.table_z
    print(
        f"cloth_fold_inspect settled steps={int(cfg.task.success.settle_steps)} "
        f"lowest_mm={heights.min() * 1e3:.2f} peak_mm={heights.max() * 1e3:.2f} "
        f"flatness_var={float(np.var(heights)):.3e} "
        f"bbox_x=[{rest[:, 0].min():+.3f},{rest[:, 0].max():+.3f}] "
        f"bbox_y=[{rest[:, 1].min():+.3f},{rest[:, 1].max():+.3f}]",
        flush=True,
    )

    if cfg.run.show_target:
        # Not a fold, and not a prediction: the analytic destination the primary
        # judge scores against, put on screen so it can be checked by eye.
        targets = fold_targets(
            rest,
            layout.fold_point(),
            layout.fold_normal(),
            float(cfg.task.cloth.particle_size),
        )
        indices = list(range(len(targets)))
        cloth_scene.cloth.set_particles_pos(targets, particles_idx_local=indices)
        # Whatever the sheet was doing is not what this pose implies; leaving the
        # old velocities in would have the solver fight the write.
        cloth_scene.cloth.set_particles_vel(
            np.zeros_like(targets), particles_idx_local=indices
        )
        print("cloth_fold_inspect showing the analytic fold target", flush=True)

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

    # `show_target` freezes: the pose was written in, not simulated, so stepping
    # would immediately let it fall and there would be nothing left to look at.
    if cfg.run.keep_open_no_step or cfg.run.show_target:
        while True:
            time.sleep(0.05)
    elif cfg.run.keep_open or cfg.run.viewer:
        while True:
            cloth_scene.scene.step()


if __name__ == "__main__":
    main()
